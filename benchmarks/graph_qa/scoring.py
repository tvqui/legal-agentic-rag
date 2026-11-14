"""Pure, outcome-blind scoring/reporting for the paired Graph QA experiment.

Retrieval/metadata checks are NOT legal correctness or semantic entailment.
Missing judge/human reviews remain N/A; incomplete schedules remain visible.
"""
from __future__ import annotations
import csv,json,math,random,statistics
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit

ARMS=('graph_off','graph_on')
METRICS=('seed_recall_at_k','seed_mrr_at_k','seed_ndcg_at_k',
 'seed_group_precision_at_k','selected_group_precision','selected_group_recall','selected_all_groups','citation_group_recall',
 'citation_metadata_accuracy','citation_temporal_metadata_consistency',
 'ai_correctness','ai_completeness','ai_evidence_support','ai_task_addressed_fraction','ai_task_supported_fraction',
 'human_correctness','human_completeness','human_semantic_citation_accuracy',
 'self_reported_part_answered_fraction')


def average(values):
    values=[v for v in values if v is not None]
    return statistics.mean(values) if values else None


def norm(value):return str(value or '').strip()


def normalized_url(value):
    if not isinstance(value,str) or not value:return None
    try:
        parts=urlsplit(value)
        if parts.scheme not in {'http','https'} or not parts.hostname or parts.username or parts.password:return None
        # Preserve query: official document IDs often live in it.
        return urlunsplit((parts.scheme.lower(),parts.netloc.lower(),parts.path.rstrip('/'),parts.query,parts.fragment))
    except ValueError:return None


def citation_check(citation,corpus,query_date):
    uid=citation.get('evidence_id');unit=corpus.get(uid)
    if unit is None:return {'evidence_id':uid,'metadata_valid':False,'errors':['UNKNOWN_EVIDENCE_ID'],'temporal_consistent':None}
    errors=[]
    for cited,source in [('article','article_number'),('clause','clause_number'),('point','point_number'),
                          ('instrument_number','instrument_number'),('document_number','document_number')]:
        expected=unit.get(source)
        if source=='instrument_number':expected=expected or unit.get('document_number')
        if norm(citation.get(cited))!=norm(expected):errors.append(cited.upper()+'_MISMATCH')
    expected_url=normalized_url(unit.get('source_url') or unit.get('official_url'))
    if expected_url is None or normalized_url(citation.get('official_url'))!=expected_url:errors.append('URL_MISMATCH_OR_MISSING')
    temporal=None
    try:
        day=date.fromisoformat(query_date)
        start=unit.get('valid_from');end=unit.get('valid_to')
        # Open/unknown intervals alone do not prove a matching effective version.
        if start:
            temporal=date.fromisoformat(start)<=day and (not end or day<date.fromisoformat(end))
    except (ValueError,TypeError):pass
    return {'evidence_id':uid,'metadata_valid':not errors,'errors':errors,
            'temporal_consistent':temporal,'interval_human_verified':bool(unit.get('provision_temporal_verified'))}


def ir(ids,groups,k):
    mapping={uid:i for i,g in enumerate(groups) for uid in g};seen=set();gains=[];first=None
    for pos,uid in enumerate(ids[:k],1):
        group=mapping.get(uid);hit=group is not None and group not in seen
        if hit:
            seen.add(group)
            if first is None:first=pos
        gains.append(int(hit))
    ideal=sum(1/math.log2(i+2) for i in range(min(k,len(groups))))
    return (len(seen)/len(groups),1/first if first else 0.,
            sum(g/math.log2(i+2) for i,g in enumerate(gains))/ideal if ideal else 0.)


def group_coverage(ids,groups):
    ids=set(ids)
    return sum(bool(ids&set(g)) for g in groups)/len(groups)


def selected_ids(response):
    trace=response.get('trace')
    if not isinstance(trace,dict):return None
    for event in reversed(trace.get('events',[])):
        if event.get('event')=='selection' and isinstance(event.get('evidence_ids'),list):
            return list(dict.fromkeys(event['evidence_ids']))
    # Early-gated response can legitimately have no selection stage.
    return [] if trace.get('verified_evidence_count') == 0 else None


def reviewed_scores(record):
    result={'human_correctness':None,'human_completeness':None,'human_semantic_citation_accuracy':None}
    review=record.get('human_review') or {}
    if review.get('status')!='REVIEWED' or not review.get('reviewer') or not review.get('reviewed_at'):return result
    for name in result:
        value=review.get(name.removeprefix('human_'))
        if type(value) in (int,float) and math.isfinite(value) and 0<=value<=1:result[name]=value
    return result


def score_record(record,gold,corpus,k=10):
    if type(k) is not int or k<1:raise ValueError('k must be positive')
    groups=gold.get('required_groups') or []
    flat=[uid for g in groups for uid in g]
    if not groups or any(not g for g in groups) or len(flat)!=len(set(flat)) or set(flat)-set(corpus):
        raise ValueError('Invalid Gold relevance groups')
    result={m:None for m in METRICS}
    result.update(citations_count=0,valid_citations_count=0,temporal_checked_citations=0,
                  graph_rounds=None,graph_used=None,citation_details=[],selection_ids=[],
                  source_interval_human_verified_count=0,missing_citation_groups=[],
                  semantic_citation_accuracy_status='NOT_EVALUATED')
    if record.get('status')!='OK':return result
    response=record.get('response') or {};trace=response.get('trace') or {}
    candidates=trace.get('retrieval_candidates')
    if isinstance(candidates,list):
        seeds=list(dict.fromkeys(r.get('unit_id') for r in candidates if isinstance(r,dict) and r.get('unit_id')))
        recall,mrr,ndcg=ir(seeds,groups,k)
        result.update(seed_recall_at_k=recall,seed_mrr_at_k=mrr,seed_ndcg_at_k=ndcg,
            seed_group_precision_at_k=recall*len(groups)/min(k,len(seeds)) if seeds else 0.)
    chosen=selected_ids(response)
    if chosen is not None:
        result['selection_ids']=chosen
        result['selected_group_recall']=group_coverage(chosen,groups)
        result['selected_all_groups']=float(result['selected_group_recall']==1)
        result['selected_group_precision']=result['selected_group_recall']*len(groups)/len(chosen) if chosen else 0.
    citations=response.get('citations') or []
    details=[citation_check(c,corpus,gold.get('query_date')) for c in citations]
    cited=list(dict.fromkeys(c.get('evidence_id') for c in citations if c.get('evidence_id')))
    result.update(citation_details=details,citations_count=len(details),
                  valid_citations_count=sum(c['metadata_valid'] for c in details),
                  citation_group_recall=group_coverage(cited,groups),
                  missing_citation_groups=[g for g in groups if not set(cited)&set(g)],
                  citation_metadata_accuracy=average(float(c['metadata_valid']) for c in details),
                  citation_temporal_metadata_consistency=average(float(c['temporal_consistent']) for c in details if c['temporal_consistent'] is not None),
                  temporal_checked_citations=sum(c['temporal_consistent'] is not None for c in details),
                  source_interval_human_verified_count=sum(c.get('interval_human_verified',False) for c in details))
    rounds=trace.get('retrieval_rounds')
    if type(rounds) is int:result.update(graph_rounds=rounds,graph_used=rounds>0)
    judge=record.get('judge') or {}
    if judge.get('status')=='AI_JUDGED':
        for field in ('correctness','completeness','evidence_support'):
            value=judge.get(field)
            if type(value) in (int,float) and math.isfinite(value) and 0<=value<=1:result['ai_'+field]=value
        tasks=judge.get('tasks') or []
        expected={t['task_id'] for t in gold.get('expected_tasks',[])}
        if expected and len(tasks)==len(expected) and {t.get('task_id') for t in tasks}==expected:
            result['ai_task_addressed_fraction']=average(float(t.get('addressed') is True) for t in tasks)
            result['ai_task_supported_fraction']=average(float(t.get('evidence_supported') is True) for t in tasks)
    parts=response.get('parts') or []
    result['self_reported_part_answered_fraction']=average(float(p.get('answer_status')=='ANSWERED') for p in parts)
    result.update(reviewed_scores(record))
    if result['human_semantic_citation_accuracy'] is not None:result['semantic_citation_accuracy_status']='HUMAN_REVIEWED'
    return result


def paired_ci(values,samples=2000,seed=42):
    values=list(values)
    if not values:return {'mean_delta':None,'ci95_low':None,'ci95_high':None,'n_queries':0,'wins':0,'ties':0,'losses':0}
    rng=random.Random(seed);boot=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(samples))
    return {'mean_delta':statistics.mean(values),'ci95_low':boot[int(.025*samples)] if len(values)>1 else None,
            'ci95_high':boot[min(samples-1,int(.975*samples))] if len(values)>1 else None,
            'n_queries':len(values),'wins':sum(v>1e-12 for v in values),'ties':sum(abs(v)<=1e-12 for v in values),
            'losses':sum(v< -1e-12 for v in values)}


def build_report(gold_rows,records,corpus,manifest,k=10):
    gold={q['id']:q for q in gold_rows}
    if len(gold)!=len(gold_rows):raise ValueError('Duplicate Gold IDs')
    selected=manifest.get('selected_ids',list(gold))
    repeats=manifest.get('repetitions',manifest.get('repeats',1));arms=manifest.get('arms',ARMS)
    if type(repeats) is not int or repeats<1 or not selected or len(selected)!=len(set(selected)) or set(selected)-set(gold):raise ValueError('Invalid report schedule')
    if tuple(arms)!=ARMS:raise ValueError('Expected paired graph_off/graph_on arms')
    expected={(qid,arm,rep) for qid in selected for arm in arms for rep in range(1,repeats+1)}
    keys=[(r['id'],r['arm'],r['repeat']) for r in records]
    if len(keys)!=len(set(keys)) or set(keys)-expected:raise ValueError('Duplicate or unexpected response schedule')
    if any(r.get('status') not in {'OK','ERROR','TIMEOUT'} for r in records):raise ValueError('Unknown response status')
    missing=sorted(expected-set(keys));scored=[{**r,'metrics':score_record(r,gold[r['id']],corpus,k)} for r in records]
    subsets={'all':selected}
    for qid in selected:subsets.setdefault(gold[qid].get('group','UNCLASSIFIED'),[]).append(qid)
    tables=[];paired=[]
    for group,qids in subsets.items():
        for arm in arms:
            rows=[r for r in scored if r['id'] in qids and r['arm']==arm];ok=[r for r in rows if r.get('status')=='OK']
            item={'group':group,'arm':arm,'queries':len(qids),'expected_attempts':len(qids)*repeats,
                  'completed_attempts':len(rows),'successful_attempts':len(ok),'errors':len(rows)-len(ok),
                  'missing_attempts':len(qids)*repeats-len(rows),'error_rate_over_completed':(len(rows)-len(ok))/len(rows) if rows else None,
                  'mean_ms_all_completed':average(r.get('elapsed_ms') for r in rows if type(r.get('elapsed_ms')) in (int,float) and math.isfinite(r['elapsed_ms'])),
                  'p50_ms_all_completed':None,'p95_ms_all_completed':None,
                  'ai_judged_attempts':sum((r.get('judge') or {}).get('status')=='AI_JUDGED' for r in rows),
                  'human_reviewed_attempts':sum((r.get('human_review') or {}).get('status')=='REVIEWED' and bool((r.get('human_review') or {}).get('reviewer')) and bool((r.get('human_review') or {}).get('reviewed_at')) for r in rows),
                  'graph_used_attempts':sum(r['metrics']['graph_used'] is True for r in ok)}
            for outcome in ('SUFFICIENT','PARTIAL_ALLOWED','NEED_MORE_FACTS','INSUFFICIENT_EVIDENCE','CONFLICTING_EVIDENCE','ABSTAIN','ERROR'):
                item['answer_'+outcome.lower()]=sum((r.get('response') or {}).get('status')==outcome for r in ok)
            times=sorted(r['elapsed_ms'] for r in rows if type(r.get('elapsed_ms')) in (int,float) and math.isfinite(r['elapsed_ms']))
            if times:
                item['p50_ms_all_completed']=times[max(0,math.ceil(.5*len(times))-1)]
                item['p95_ms_all_completed']=times[max(0,math.ceil(.95*len(times))-1)]
            for metric in METRICS:
                query_values=[average(r['metrics'][metric] for r in ok if r['id']==qid) for qid in qids]
                item[metric]=average(query_values)
                item[metric+'_n_queries']=sum(v is not None for v in query_values)
            tables.append(item)
        for metric in METRICS:
            delta=[];ids=[]
            for qid in qids:
                # Use only SAME successful repeats; do not compare unrelated subsets.
                left={r['repeat']:r['metrics'][metric] for r in scored if r['id']==qid and r['arm']=='graph_off' and r.get('status')=='OK' and r['metrics'][metric] is not None}
                right={r['repeat']:r['metrics'][metric] for r in scored if r['id']==qid and r['arm']=='graph_on' and r.get('status')=='OK' and r['metrics'][metric] is not None}
                common=set(left)&set(right)
                if common:delta.append(statistics.mean(right[r]-left[r] for r in common));ids.append(qid)
            paired.append({'group':group,'metric':metric,'direction':'graph_on_minus_graph_off',
                           'paired_query_ids':ids,**paired_ci(delta)})
    success_keys={(r['id'],r['arm'],r['repeat']) for r in records if r.get('status')=='OK'}
    complete_pairs=sum((q,'graph_off',r) in success_keys and (q,'graph_on',r) in success_keys for q in selected for r in range(1,repeats+1))
    return {'protocol':'graph-qa-paired-v1','execution_status':('INCOMPLETE' if missing else 'COMPLETE_WITH_ERRORS' if any(r.get('status')!='OK' for r in records) else 'COMPLETE'),
            'all_attempts_successful':not missing and all(r.get('status')=='OK' for r in records),
            'gold_status':manifest.get('gold_status','ARTIFACT_VERIFIED_DRAFT'),
            'expected_attempts':len(expected),'completed_attempts':len(records),'missing_schedule':missing,
            'successful_pairs':complete_pairs,'expected_pairs':len(selected)*repeats,
            'tables':tables,'paired':paired,'records':scored,
            'warnings':['Small per-group samples limit inference; bootstrap unit is the query, not repeat.',
                'Paired metric deltas use matched successful repeats only; inspect errors and pair coverage before interpretation.',
                'Citation metadata validity and interval consistency do not establish legal correctness or semantic entailment.',
                'Gold/reference answers are development annotations; no automatic human approval.',
                'AI judge scores, when present, are model evaluations and not legal certification.']}


def read_rows(path):return [json.loads(s) for s in path.read_text(encoding='utf-8-sig').splitlines() if s.strip()] if path.exists() else []

def write_csv(path,rows):
    if not rows:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(dict.fromkeys(key for row in rows for key in row)));writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in rows)

def show(value):return 'N/A' if value is None else f'{value:.4f}' if isinstance(value,float) else str(value)


def import_reviews(records,path):
    if not path.exists():return records
    with path.open(encoding='utf-8-sig',newline='') as f:reviews=list(csv.DictReader(f))
    by_key={}
    for row in reviews:
        key=(row.get('id'),row.get('arm'),int(row.get('repeat',0)))
        if key in by_key:raise ValueError('Duplicate manual review key')
        by_key[key]=row
    result=[]
    for record in records:
        r=dict(record);row=by_key.get((r['id'],r['arm'],r['repeat']))
        if row and row.get('review_status')=='REVIEWED':
            review={'status':'REVIEWED','reviewer':row.get('reviewer'),'reviewed_at':row.get('reviewed_at')}
            for field in ('correctness','completeness','semantic_citation_accuracy'):
                value=row.get(field,'').strip()
                if value:
                    try:review[field]=float(value)
                    except ValueError:raise ValueError('Invalid manual review numeric score') from None
            r['human_review']=review
        result.append(r)
    return result


def report(run_dir):
    path=Path(run_dir);manifest=json.loads((path/'run_manifest.json').read_text(encoding='utf8'))
    gold=read_rows(path/'gold.jsonl');corpus={u['unit_id']:u for u in read_rows(path/'corpus.jsonl')}
    records=import_reviews(read_rows(path/'responses.jsonl'),path/'human_review.csv')
    result=build_report(gold,records,corpus,manifest,manifest.get('k',10))
    (path/'comparison.json').write_text(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    write_csv(path/'comparison.csv',result['tables']);write_csv(path/'paired.csv',result['paired'])
    write_csv(path/'per_attempt_metrics.csv',[{'id':r['id'],'arm':r['arm'],'repeat':r['repeat'],'status':r['status'],
        **{k:v for k,v in r['metrics'].items() if k not in {'citation_details','selection_ids','missing_citation_groups'}}} for r in result['records']])
    text=['# Đối chứng Graph QA','',f"Trạng thái thực thi: {result['execution_status']}; cặp thành công {result['successful_pairs']}/{result['expected_pairs']}.",'',
        'Các điểm retrieval/metadata không phải độ đúng pháp lý. N/A là chưa có đánh giá tương ứng.','',
        '| Nhóm | Nhánh | Lượt OK / dự kiến | Lỗi | Selected group recall | Citation group recall | Citation metadata | AI correctness | Human correctness | Mean ms |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in result['tables']:
        text.append('| '+ ' | '.join([str(r['group']),r['arm'],f"{r['successful_attempts']}/{r['expected_attempts']}",str(r['errors']),show(r['selected_group_recall']),show(r['citation_group_recall']),show(r['citation_metadata_accuracy']),show(r['ai_correctness']),show(r['human_correctness']),show(r['mean_ms_all_completed'])])+' |')
    text+=['','## Giới hạn']+['- '+w for w in result['warnings']]
    (path/'comparison.md').write_text('\n'.join(text)+'\n',encoding='utf8')
    gold_by_id={q['id']:q for q in gold};detail=['# Câu hỏi và câu trả lời từng lượt','']
    for r in result['records']:
        q=gold_by_id[r['id']];answer=r.get('response') or {}
        detail += [f"## {r['id']} — {r['arm']} — lượt {r['repeat']}",'',q['question'],'',
            f"Trạng thái {r['status']}; thời gian {show(r.get('elapsed_ms'))} ms; trả lời {answer.get('status','N/A')}.",'',
            answer.get('answer') or 'Không có câu trả lời; xem lỗi ở responses.jsonl.','',
            'Citations: `'+json.dumps(answer.get('citations',[]),ensure_ascii=False)+'`','',
            'Selected evidence: `'+json.dumps(r['metrics']['selection_ids'],ensure_ascii=False)+'`','',
            'Metadata check: `'+json.dumps(r['metrics']['citation_details'],ensure_ascii=False)+'`','',
            'Trace: `'+str(r.get('trace_path') or answer.get('trace_id') or 'embedded in responses.jsonl')+'`','']
    (path/'responses.md').write_text('\n'.join(detail)+'\n',encoding='utf8')
    # Preserve completed manual reviews and add rows appearing after resume.
    review_path=path/'human_review.csv';review=[]
    if review_path.exists():
        with review_path.open(encoding='utf-8-sig',newline='') as f:review=list(csv.DictReader(f))
    known={(r['id'],r['arm'],int(r['repeat'])) for r in review}
    for r in result['records']:
        if (r['id'],r['arm'],r['repeat']) in known:continue
        review.append({'id':r['id'],'arm':r['arm'],'repeat':r['repeat'],'question':gold_by_id[r['id']]['question'],
            'correctness':'','completeness':'','semantic_citation_accuracy':'','per_task_review':'',
            'reviewer':'','reviewed_at':'','notes':'','review_status':''})
    write_csv(review_path,review)
    return result
