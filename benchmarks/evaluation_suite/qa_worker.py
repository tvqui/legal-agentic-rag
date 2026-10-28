"""Resumable, quota-aware generation and deferred judging for benchmark workers."""
from __future__ import annotations
import gc,json,time
from pathlib import Path
from common import jsonl,save,answer_summary,redact
from gold import status_comparison
from protocol import VERSION,capacity_error,safe_failure,paired_delta

def write_records(path,records):
    temp=path.with_suffix('.tmp')
    temp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    temp.replace(path)

def summarise(out,records,rows,names,repeats,scope,label,stop_reason=None,final=False):
    expected=len(rows)*len(names)*repeats
    result={'protocol_version':VERSION,'scope':scope,'label_status':label,'expected_attempts':expected,
       'complete':len(records)==expected and all(r['status']=='OK' and r.get('judge',{}).get('status') not in {'PENDING','ERROR','NOT_CONFIGURED'} for r in records),
       'generation_complete':len(records)==expected,'stop_reason':stop_reason,
       'scheduled_queries':len(rows),'scheduled_variants':list(names),'variants':{},
       'notes':['Generation finishes before AI judging; judge latency excluded from answer latency.',
        'No gold facts, answers, qrels or support labels are given to inference.',
        'Exact/profile shortcuts disabled equally; deployment latency is a separate experiment.']}
    for name in names:
        subset=[r for r in records if r['variant']==name]
        result['variants'][name]={**answer_summary(subset,include_ci=final),'expected_attempts':len(rows)*repeats,
              'not_run':len(rows)*repeats-len(subset)}
    comparisons={}
    for name in names:
        if name=='full' or not final:continue
        comparisons[name]={}
        for score in ('correctness','completeness','evidence_support'):
            comparisons[name][score]=paired_delta(records,'full',name,
                lambda r:r.get('judge',{}).get(score) if r.get('judge',{}).get('status')=='AI_JUDGED' else None)
    result['paired_deltas']=comparisons
    save(out/'summary.json',result)
    return result

def evaluate(qa,run_dir,settings,vlsp=False):
    from vn_labor_online.config import load_config
    from vn_labor_online.models import QueryRequest
    from vn_labor_online.pipeline import OnlinePipeline
    run_dir=Path(run_dir);config=load_config(run_dir/'online_pinned.yaml')
    if Path(config.artifact_source).resolve()!=Path(settings['artifact']).resolve():raise ValueError('Pinned artifact changed')
    if config.adjudication.mode=='deterministic':raise ValueError('QA benchmark requires a generative provider')
    rows=jsonl(run_dir/('vlsp/questions.jsonl' if vlsp else 'labor_gold.jsonl'))
    if not rows:raise ValueError('No QA questions')
    out=run_dir/('vlsp_qa' if vlsp else 'ablation');out.mkdir(exist_ok=True)
    names=('full',) if vlsp else qa.VARIANTS
    repeats=settings.get('qa_repeats',settings['repeats']);block_size=settings.get('qa_block_size',10)
    if type(block_size) is not int or block_size<1:raise ValueError('qa_block_size must be positive')
    label='EXTERNAL_REFERENCE_DATE_ASSUMPTION' if vlsp else 'REVIEWED_LABELS' if all(r.get('review_status')=='APPROVED' and r.get('reviewer') and r.get('reviewed_at') for r in rows) else 'DRAFT'
    scope='adapted_vlsp_free_qa_not_official_protocol' if vlsp else 'isolated_end_to_end_component_ablation'
    path=out/'responses.jsonl';records=jsonl(path) if path.exists() else []
    key=lambda r:(r['id'],r['variant'],r['repeat'])
    if len({key(r) for r in records})!=len(records):raise ValueError('Duplicate QA resume keys')
    expected={(r['id'],name,repeat+1) for r in rows for name in names for repeat in range(repeats)}
    if any(key(r) not in expected for r in records):raise ValueError('Resume records do not match frozen inputs')
    # Never rerun a successful refusal/partial answer to cherry-pick a nicer result.
    retry=[r for r in records if r.get('status')=='ERROR']
    if retry:
        with (out/'attempt_history.jsonl').open('a',encoding='utf-8') as f:
            for r in retry:f.write(json.dumps(r,ensure_ascii=False)+'\n')
        records=[r for r in records if r.get('status')=='OK']
        write_records(path,records)
    completed={key(r) for r in records}
    stop_reason=None
    def checkpoint(final=False):
        write_records(path,records)
        return summarise(out,records,rows,names,repeats,scope,label,stop_reason,final)
    try:
        for repeat in range(repeats):
            for block_start in range(0,len(rows),block_size):
                rotation=(repeat+block_start//block_size)%len(names)
                order=names[rotation:]+names[:rotation]
                for name in order:
                    pending=[r for r in rows[block_start:block_start+block_size] if (r['id'],name,repeat+1) not in completed]
                    if not pending:continue
                    pipe=None
                    try:
                        cfg=qa.variant_config(config,name);cfg.trace_dir=str(out/'traces'/name)
                        cfg.request_timeout_seconds=settings['case_timeout_seconds']
                        pipe=OnlinePipeline(cfg)
                        if name=='without_auditor':pipe.applicability=qa.DisabledAuditor()
                        save(out/(name+'_config.json'),redact(cfg.model_dump(mode='json')))
                        # Artifact-only warmup outside measured answer latency. No LLM or gold input.
                        if settings.get('qa_warmup',True) and hasattr(pipe,'retriever'):
                            from labor_retrieval import pin_models
                            pins=pin_models(cfg,pipe.store,['hybrid_rerank'] if cfg.reranker.enabled else ['hybrid'],settings['cache'])
                            save(out/'model_pins.json',pins)
                            warm='Quy định về hợp đồng lao động'
                            candidates=pipe.retriever.bm25(warm)
                            if cfg.retrieval.dense_enabled:pipe.retriever.dense(warm)
                            if cfg.reranker.enabled:pipe.retriever.neural_rerank(candidates[:2],warm)
                        for row in pending:
                            record={k:row.get(k) for k in ('id','question','query_date','expected_status','reference_answer','review_status','query_after_corpus_snapshot')}
                            record.update(variant=name,repeat=repeat+1,status='OK',experimental=True,
                              status_score_eligible=row.get('status_score_eligible',True),qa_judge_eligible=row.get('qa_judge_eligible',True),
                              expected_missing_facts=row.get('missing_facts',[]))
                            started=time.perf_counter()
                            try:
                                response=pipe.ask(QueryRequest(question=row['question'],query_date=row.get('query_date'),
                                    facts=row.get('facts') or {},conversation_context=row.get('conversation_context') or [],
                                    conversation_turns=row.get('conversation_turns') or []))
                                elapsed=round((time.perf_counter()-started)*1000,3)
                                events=response.trace.events
                                execution=next((e for e in events if e.get('event')=='retrieval_execution'),{})
                                record.update(answer=response.answer,answer_status=response.status.value,
                                  claims=[c.model_dump(mode='json') for c in response.claims],citations=[c.model_dump(mode='json') for c in response.citations],
                                  warnings=response.warnings,reference_audit=response.trace.reference_audit,
                                  timings_ms=response.trace.timings_ms,trace_id=response.trace.trace_id,
                                  task_parts=[p.model_dump(mode='json') for p in response.parts],elapsed_ms=elapsed,
                                  component_exposure={'graph_exercised':response.trace.retrieval_rounds>0,
                                    'reranker_requested':bool(execution.get('reranker_requested')),
                                    'reviewer_exercised':any(e.get('event')=='semantic_answer_audit' for e in events),
                                    'auditor_disabled':name=='without_auditor'})
                                record['draft_disposition_match']=status_comparison(row.get('expected_status'),record['answer_status']) if row.get('status_score_eligible',True) else None
                                groups=row.get('required_groups',[]) if row.get('retrieval_eligible',True) else []
                                cited={c.get('evidence_id') for c in record['citations']}
                                record['gold_citation_group_recall']=sum(bool(cited.intersection(g)) for g in groups)/len(groups) if groups else None
                                # Stored after inference, reserved only for the independent evaluation pass.
                                record['judge_reference']={'reference':row.get('reference_answer'),
                                  'expected_status':row.get('expected_status'),'missing_facts':row.get('missing_facts',[]),
                                  'query_date':row.get('query_date'),'corpus_snapshot_as_of':row.get('corpus_snapshot_as_of'),
                                  'gold_source_texts':[(pipe.store.units_by_id[g[0]].get('source_text') or pipe.store.units_by_id[g[0]]['text']) for g in groups],
                                  'cited_source_texts':[{'id':uid,'text':(pipe.store.units_by_id[uid].get('source_text') or pipe.store.units_by_id[uid]['text'])[:12000]} for uid in sorted(cited) if uid in pipe.store.units_by_id],
                                  'qualification':'Reference may be DRAFT; assess qualifications and missing evidence independently.'}
                                record['judge']={'status':'PENDING' if record['qa_judge_eligible'] else 'NOT_EVALUATED_REFERENCE_REVIEW'}
                            except Exception as exc:
                                record.update(status='ERROR',elapsed_ms=round((time.perf_counter()-started)*1000,3),**safe_failure(exc))
                                if capacity_error(exc):stop_reason='UPSTREAM_CAPACITY_OR_CONFIGURATION'
                            records.append(record);completed.add(key(record));checkpoint()
                            print(f"QA {name} {row['id']} {record['status']} {record['elapsed_ms']} ms",flush=True)
                            if stop_reason:return checkpoint(final=True)
                    finally:
                        if pipe:pipe.close()
                        pipe=None;gc.collect()
                        try:
                            import torch
                            if torch.cuda.is_available():torch.cuda.empty_cache()
                        except ImportError:pass
        # Complete all generation first. The judge cannot consume quota ahead of later variants.
        for record in sorted(records,key=lambda r:(r['repeat'],r['id'],r['variant'])):
            if record.get('status')!='OK' or not record.get('qa_judge_eligible',True) or record.get('judge',{}).get('status')=='AI_JUDGED':continue
            begin=time.perf_counter()
            result=qa.score_judge(record['question'],json.dumps(record['judge_reference'],ensure_ascii=False),record.get('answer',''),record.get('citations',[]),settings['judge']) if settings['judge'].get('enabled') else {'status':'NOT_REQUESTED'}
            record['judge']=result;record['judge_ms']=round((time.perf_counter()-begin)*1000,3)
            if result.get('status')=='ERROR' and (result.get('error_type')=='ProviderRateLimited' or result.get('error_code') in {'GEMINI_HTTP_429','GEMINI_HTTP_401','GEMINI_HTTP_403','GEMINI_HTTP_400','GEMINI_HTTP_404'}):
                stop_reason='JUDGE_CAPACITY_OR_CONFIGURATION';return checkpoint(final=True)
            checkpoint()
        return checkpoint(final=True)
    finally:
        write_records(path,records)
