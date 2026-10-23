"""Experimental interventions confined to this standalone evaluation process."""
from __future__ import annotations
import gc,json,time
from pathlib import Path
from common import jsonl,save,answer_summary,score_judge,redact
from gold import status_comparison

VARIANTS=('full','without_graph','without_reranker','without_auditor','without_review')

class DisabledAuditor:
    """Admit candidates experimentally, WITHOUT fabricating a PASS decision."""
    provider=None
    def audit(self,items,*args,**kwargs):
        from vn_labor_online.models import ApplicabilityDecision
        return list(items),[ApplicabilityDecision(evidence_id=e.unit_id,relevant=True,
          supports_claim=False,audit_status='UNRESOLVED',reasons=['EXPERIMENT_AUDITOR_DISABLED']) for e in items],['EXPERIMENT_AUDITOR_DISABLED']
    _deterministic=audit

def variant_config(base,name):
    if name not in VARIANTS:raise ValueError(name)
    cfg=base.model_copy(deep=True)
    # Otherwise easy exact/profile routes may skip the component being measured.
    cfg.retrieval.profile_fast_path=False;cfg.retrieval.exact_lookup=False
    cfg.graph.enabled=name!='without_graph'
    cfg.reranker.enabled=name!='without_reranker'
    if name=='without_auditor':cfg.applicability.mode='deterministic'
    if name=='without_review':cfg.adjudication.semantic_review=False
    return cfg

def evaluate(run_dir,settings,vlsp=False):
    from vn_labor_online.config import load_config
    from vn_labor_online.models import QueryRequest
    from vn_labor_online.pipeline import OnlinePipeline
    run_dir=Path(run_dir);config=load_config(run_dir/'online_pinned.yaml')
    if Path(config.artifact_source).resolve()!=Path(settings['artifact']).resolve():
        raise ValueError('Environment changed the pinned artifact')
    if config.adjudication.mode=='deterministic':raise ValueError('QA evaluation requires a generative model; deterministic mode is not a model benchmark')
    source=run_dir/('vlsp/questions.jsonl' if vlsp else 'labor_gold.jsonl')
    rows=jsonl(source)
    if not rows:raise ValueError('No eligible QA questions; see selection report')
    out=run_dir/('vlsp_qa' if vlsp else 'ablation');out.mkdir(exist_ok=True)
    summary={'scope':'adapted_vlsp_free_qa_not_official_protocol' if vlsp else 'isolated_end_to_end_component_ablation',
      'label_status':'EXTERNAL_REFERENCE_DATE_ASSUMPTION' if vlsp else
         'REVIEWED_LABELS' if all(r.get('review_status')=='APPROVED' and r.get('reviewer') and r.get('reviewed_at') for r in rows) else 'DRAFT',
      'variants':{},'notes':['No synthetic PASS for disabled Auditor. Source/time/reference/wording gates remain.',
        'AI-judge means are not human-approved legal accuracy. Compare judged counts too.',
        'Exact/profile shortcuts disabled for all ablations; results are not deployment latency.']}
    names=('full',) if vlsp else VARIANTS
    records=[]
    with (out/'responses.jsonl').open('w',encoding='utf-8') as f:
        # Each variant releases its pipeline before the next one. Run repetition
        # order reverses on alternate repetitions to reduce persistent bias.
        repeats=settings.get('qa_repeats',settings['repeats'])
        for repeat in range(repeats):
            order=names if repeat%2==0 else tuple(reversed(names))
            for name in order:
                pipe=None
                try:
                    cfg=variant_config(config,name);cfg.trace_dir=str(out/'traces'/name)
                    cfg.request_timeout_seconds=settings['case_timeout_seconds']
                    pipe=OnlinePipeline(cfg)
                    if name=='without_auditor':pipe.applicability=DisabledAuditor()
                    save(out/(name+'_config.json'),redact(cfg.model_dump(mode='json')))
                    for row in rows:
                        started=time.perf_counter()
                        record={'id':row['id'],'question':row['question'],'variant':name,'repeat':repeat+1,
                            'query_date':row.get('query_date'),'status':'OK','experimental':True,
                            'expected_status':row.get('expected_status'),'reference_answer':row.get('reference_answer'),
                            'expected_missing_facts':row.get('missing_facts',[]),
                            'status_score_eligible':row.get('status_score_eligible',True),
                            'annotation_review':row.get('annotation_review',{}),
                            'query_after_corpus_snapshot':row.get('query_after_corpus_snapshot'),
                            'review_status':row.get('review_status')}
                        try:
                            response=pipe.ask(QueryRequest(question=row['question'],query_date=row.get('query_date'),
                                facts=row.get('facts') or {},conversation_context=row.get('conversation_context') or []))
                            record.update(answer=response.answer,answer_status=response.status.value,
                                claims=[c.model_dump(mode='json') for c in response.claims],
                                citations=[c.model_dump(mode='json') for c in response.citations],
                                warnings=response.warnings,reference_audit=response.trace.reference_audit,
                                timings_ms=response.trace.timings_ms,trace_id=response.trace.trace_id,
                                task_parts=[p.model_dump(mode='json') for p in response.parts])
                            events=response.trace.events
                            execution=next((e for e in events if e.get('event')=='retrieval_execution'),{})
                            record['component_exposure']={'graph_exercised':response.trace.retrieval_rounds>0,
                                'reranker_requested':bool(execution.get('reranker_requested')),
                                'reviewer_exercised':any(e.get('event')=='semantic_answer_audit' for e in events)}
                            record['elapsed_ms']=round((time.perf_counter()-started)*1000,3)
                            record['draft_disposition_match']=status_comparison(row.get('expected_status'),record['answer_status']) if row.get('status_score_eligible',True) else None
                            # Only positive answerable qrels define citation recall.
                            groups=row.get('required_groups',[]) if row.get('retrieval_eligible',True) else []
                            cited={c.get('evidence_id') for c in record['citations']}
                            record['gold_citation_group_recall']=sum(bool(cited.intersection(g)) for g in groups)/len(groups) if groups else None
                            reference=row.get('reference_answer')
                            reference_kind='REFERENCE_ANSWER'
                            if not reference:
                                reference='\n'.join(pipe.store.units_by_id[group[0]]['text'] for group in row.get('required_groups',[]))
                                reference_kind='SOURCE_RULES_NOT_REFERENCE_ANSWER'
                            record['reference_kind']=reference_kind
                            judge_reference=json.dumps({'reference':reference,'expected_status':row.get('expected_status'),
                                'missing_facts':row.get('missing_facts',[]),'query_date':row.get('query_date'),
                                'corpus_snapshot_as_of':row.get('corpus_snapshot_as_of'),
                                'gold_source_texts':[pipe.store.units_by_id[group[0]].get('source_text') or pipe.store.units_by_id[group[0]]['text']
                                    for group in row.get('required_groups',[])],
                                'cited_source_texts':[{ 'id':uid,
                                    'text':(pipe.store.units_by_id[uid].get('source_text') or pipe.store.units_by_id[uid]['text'])[:12000],
                                    'truncated':len(pipe.store.units_by_id[uid].get('source_text') or pipe.store.units_by_id[uid]['text'])>12000}
                                    for uid in sorted(cited) if uid in pipe.store.units_by_id],
                                'qualification':'DRAFT; conditional answer plus clarification may be appropriate. Do not penalize a supported qualification merely for differing wording.'},ensure_ascii=False)
                            record['judge']=score_judge(row['question'],judge_reference,response.answer,record['citations'],settings['judge']) if row.get('qa_judge_eligible',True) else {'status':'NOT_EVALUATED_REFERENCE_REVIEW'}
                            record['evaluation_including_judge_ms']=round((time.perf_counter()-started)*1000,3)
                        except Exception as exc:
                            record.update(status='ERROR',error_type=type(exc).__name__,elapsed_ms=round((time.perf_counter()-started)*1000,3))
                        records.append(record);f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush()
                        for variant in names:summary['variants'][variant]=answer_summary([r for r in records if r['variant']==variant])
                        summary['expected_attempts']=len(rows)*len(names)*repeats
                        summary['complete']=len(records)==summary['expected_attempts']
                        save(out/'summary.json',summary)
                        print(f"QA {name} {row['id']} {record['status']} {record['elapsed_ms']} ms",flush=True)
                finally:
                    if pipe:pipe.close()
                    pipe=None;gc.collect()
                    try:
                        import torch
                        if torch.cuda.is_available():torch.cuda.empty_cache()
                    except ImportError:pass
    return summary
