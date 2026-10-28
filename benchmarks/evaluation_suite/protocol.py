"""Scoring protocol shared by the published tables; never inference input."""
from __future__ import annotations
from collections import defaultdict
import math,random,statistics,unicodedata

VERSION='labor-evaluation-v2-20261028'
DEFAULT_KS=(1,3,5,10,20)

def average(values):
    values=[v for v in values if v is not None]
    return statistics.mean(values) if values else None

def percentile(values,p):
    return sorted(values)[max(0,math.ceil(p*len(values))-1)] if values else None

def query_macro(records,metric):
    grouped=defaultdict(list)
    for index,r in enumerate(records):
        value=metric(r)
        if value is not None:grouped[r.get('id',f'unidentified_{index}')].append(value)
    return {qid:statistics.mean(v) for qid,v in grouped.items()}

def bootstrap_ci(values,samples=2000,seed=42):
    values=list(values)
    if not values:return {'mean':None,'ci95_low':None,'ci95_high':None,'n_queries':0}
    if len(values)<2:return {'mean':values[0],'ci95_low':None,'ci95_high':None,'n_queries':1}
    rng=random.Random(seed);means=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(samples))
    return {'mean':statistics.mean(values),'ci95_low':means[int(.025*samples)],
            'ci95_high':means[min(samples-1,int(.975*samples))],'n_queries':len(values)}

def paired_delta(records,left,right,metric,variant_key='variant'):
    """Queries, not repeated timings, are the resampling unit."""
    a=query_macro([r for r in records if r.get(variant_key)==left and r.get('status')=='OK'],metric)
    b=query_macro([r for r in records if r.get(variant_key)==right and r.get('status')=='OK'],metric)
    shared=sorted(a.keys()&b.keys())
    return {'left':left,'right':right,'direction':'left_minus_right',
            **bootstrap_ci([a[q]-b[q] for q in shared]),'paired_ids':shared,
            'left_only_ids':sorted(a.keys()-b.keys()),'right_only_ids':sorted(b.keys()-a.keys())}

def norm(text):return ' '.join(unicodedata.normalize('NFC',str(text or '')).split())

def context_metrics(units,annotation=None):
    """Requires explicit fact→source/quote labels; qrels alone are insufficient."""
    texts=[str(u.get('source_text') or u.get('text') or '') for u in units]
    result={'context_units':len(units),'context_chars':sum(len(t) for t in texts),
       'estimated_context_tokens':math.ceil(sum(len(t) for t in texts)/4),
       'fact_coverage':None,'evidence_precision':None,'fact_annotations':0}
    if not annotation or not annotation.get('facts'):return result
    covered=set();supporting=set()
    for fi,fact in enumerate(annotation['facts']):
        for ui,unit in enumerate(units):
            for support in fact.get('supports',[]):
                if unit.get('unit_id')==support['unit_id'] and norm(support['quote']) in norm(texts[ui]):
                    covered.add(fi);supporting.add(ui)
    result.update(fact_coverage=len(covered)/len(annotation['facts']),
       evidence_precision=len(supporting)/len(units) if units else 0.,fact_annotations=len(annotation['facts']))
    return result

def validate_annotation(annotation,units_by_id,corpus_fingerprint):
    if annotation.get('corpus_fingerprint')!=corpus_fingerprint:raise ValueError('Evidence annotation build mismatch')
    facts=annotation.get('facts') or []
    if not facts or len({f['fact_id'] for f in facts})!=len(facts):raise ValueError('Missing or duplicate fact IDs')
    for fact in facts:
        if not fact.get('description') or not fact.get('supports'):raise ValueError('Each fact needs description and supports')
        for support in fact['supports']:
            unit=units_by_id.get(support.get('unit_id'));quote=norm(support.get('quote'))
            if not unit or not quote or quote not in norm(unit.get('source_text') or unit.get('text')):
                raise ValueError('Evidence annotation quote is not in its source unit')
    if annotation.get('review_status')=='APPROVED' and not all(annotation.get(k) for k in ('reviewer','reviewed_at')):
        raise ValueError('Approved annotations require reviewer/date')
    return annotation

def safe_failure(exc):
    """No raw exception messages or URLs/credentials in public benchmark logs."""
    code=getattr(exc,'safe_code',None) or getattr(exc,'reason',None)
    return {'error_type':type(exc).__name__,'error_code':code,
       'quota_kind':getattr(exc,'quota_kind',None),'retry_after_seconds':getattr(exc,'retry_after_seconds',None)}

def capacity_error(exc):
    return type(exc).__name__=='ProviderRateLimited' or getattr(exc,'safe_code',None) in {
        'GEMINI_HTTP_429','GEMINI_HTTP_401','GEMINI_HTTP_403','GEMINI_HTTP_400','GEMINI_HTTP_404'}

def qa_protocol_summary(records,include_ci=False):
    good=[r for r in records if r.get('status')=='OK']
    content=[r for r in good if r.get('claims')]
    judged=[r for r in good if r.get('judge',{}).get('status')=='AI_JUDGED']
    labelled=[r for r in records if r.get('expected_status') and r.get('status_score_eligible',True)]
    answered=[r for r in labelled if r['expected_status']=='ANSWERABLE']
    unavailable={'INSUFFICIENT_EVIDENCE','ABSTAIN','NEED_MORE_FACTS'}
    # These are draft label-based behavior metrics, never legal correctness.
    result={'unique_queries':len({r['id'] for r in records if r.get('id')}),
       'technical_success_rate':len(good)/len(records) if records else None,
       'ai_judge_coverage':len(judged)/len(good) if good else None,
       'ai_judge_errors':sum(r.get('judge',{}).get('status')=='ERROR' for r in good),
       'content_answer_rate':len(content)/len(records) if records else None,
       'draft_false_abstention_count':sum(r.get('status')=='OK' and r.get('answer_status') in unavailable for r in answered),
       'draft_answerable_questions':len(answered),
       'task_parts':sum(len(r.get('task_parts',[])) for r in good),
       'task_answered_rate':average([p.get('answer_status')=='ANSWERED' for r in good for p in r.get('task_parts',[])]),
       'judge_coverage_warning':len(judged)<len([r for r in good if r.get('qa_judge_eligible',True)]),
       'p95_ms':percentile([r['elapsed_ms'] for r in good],.95),
       'content_mean_ms':average([r['elapsed_ms'] for r in content]),
       'content_p95_ms':percentile([r['elapsed_ms'] for r in content],.95)}
    for score in ('correctness','completeness','evidence_support'):
        qvalues=query_macro(judged,lambda r:r['judge'][score])
        result['ai_'+score]=average(qvalues.values())
        result['ai_'+score+'_query_ci95']=bootstrap_ci(qvalues.values()) if include_ci else {'mean':average(qvalues.values()),'n_queries':len(qvalues),'ci95_low':None,'ci95_high':None}
    return result
