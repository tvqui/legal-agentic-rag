from __future__ import annotations
import argparse,json,time,statistics,math
from pathlib import Path
from vn_labor_online.config import load_config
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_online.analysis import intake,analyze
from vn_labor_offline.gold import validate_gold_record
from vn_labor_online.runtime import request_budget,measured_timings
from vn_labor_online.retrieval import temporal_filter,authority_filter
def rows(path): return [json.loads(x) for x in path.read_text(encoding='utf-8-sig').splitlines() if x]

def pool_sweep(pipe,gold):
    """Measure candidates; never change deployment defaults or approve draft Gold."""
    results={}; original=pipe.retriever.cfg
    for name,values in (('baseline_30_30_20_30',(30,30,20,30)),('candidate_12_12_8_12',(12,12,8,12))):
        retrieval=original.retrieval.model_copy(update=dict(zip(
          ('bm25_top_k','dense_top_k','issue_anchor_top_k','fusion_top_k'),values)))
        cfg=original.model_copy(update={'retrieval':retrieval})
        pipe.retriever.cfg=cfg
        measured_rows=[]
        try:
            for row in gold:
                truth=set(row.get('gold_unit_ids') or row.get('candidate_unit_ids') or [])
                if not truth or row.get('query_type')=='INSUFFICIENT_FACTS': continue
                analysis=analyze(intake(row['question'],[]),row.get('query_date'),row.get('facts'))
                started=time.perf_counter()
                with request_budget(cfg.request_timeout_seconds):
                    channels=[]
                    if retrieval.bm25_enabled: channels.append(pipe.retriever.bm25(row['question']))
                    if retrieval.dense_enabled: channels.append(pipe.retriever.dense(row['question']))
                    if retrieval.issue_anchor_enabled: channels.append(pipe.retriever.issue_anchor(analysis.legal_issues))
                    got=pipe.retriever.fusion(channels)
                    got,_=temporal_filter(got,analysis.query_date,strict=not (cfg.provisional_mode and cfg.allow_document_temporal_fallback))
                    got,_=authority_filter(got,strict=not cfg.provisional_mode)
                    if cfg.reranker.enabled: got=pipe.retriever.neural_rerank(got,row['question'])
                    timing=measured_timings()
                cold=any(key.endswith(('model_init','index_load')) for key in timing)
                measured_rows.append({'query_id':row.get('query_id',row.get('id')),'cold':cold,
                  'elapsed_ms':round((time.perf_counter()-started)*1000,3),'timings_ms':timing,
                  'required_evidence_recall_at_10':len(truth&{x.unit_id for x in got[:10]})/len(truth),
                  'required_evidence_recall_at_pool':len(truth&{x.unit_id for x in got})/len(truth)})
        finally: pipe.retriever.cfg=original
        warm=sorted(row['elapsed_ms'] for row in measured_rows if not row['cold'])
        results[name]={'settings':retrieval.model_dump(),'queries':len(measured_rows),
          'cold_rows':[row for row in measured_rows if row['cold']],
          'warm_p50_ms':statistics.median(warm) if warm else None,
          'warm_p95_ms':warm[max(0,math.ceil(len(warm)*.95)-1)] if warm else None,
          'mean_required_recall_at_10':statistics.mean(row['required_evidence_recall_at_10'] for row in measured_rows) if measured_rows else None,
          'mean_required_recall_at_pool':statistics.mean(row['required_evidence_recall_at_pool'] for row in measured_rows) if measured_rows else None,
          'rows':measured_rows}
    return results
def main():
    p=argparse.ArgumentParser(); p.add_argument('--config',type=Path,default=Path('config/online.yaml')); p.add_argument('--gold',type=Path,required=True); p.add_argument('--out',type=Path,default=Path('artifacts/online_evaluation/retrieval_benchmark.json')); p.add_argument('--pool-sweep',action='store_true'); a=p.parse_args()
    pipe=OnlinePipeline(load_config(a.config)); gold=rows(a.gold); results={}
    methods=() if a.pool_sweep else ('bm25','dense','hybrid')
    for method in methods:
        recalls=[]; lat=[]
        for q in gold:
            truth=set(q.get('gold_unit_ids') or q.get('candidate_unit_ids') or [])
            if not truth or q.get('query_type')=='INSUFFICIENT_FACTS': continue
            t=time.perf_counter(); lists=[]
            if method in ('bm25','hybrid'): lists.append(pipe.retriever.bm25(q['question']))
            if method in ('dense','hybrid'): lists.append(pipe.retriever.dense(q['question']))
            got=lists[0] if len(lists)==1 else pipe.retriever.fusion(lists); lat.append((time.perf_counter()-t)*1000)
            recalls.append(len(truth&{x.unit_id for x in got[:10]})/len(truth))
        results[method]={'queries':len(recalls),'mean_recall_at_10':sum(recalls)/len(recalls) if recalls else None,'avg_latency_ms':sum(lat)/len(lat) if lat else None}
    expected=pipe.store.report.gold_build_id; supplied=sorted({str(x.get('build_id')) for x in gold if x.get('build_id')})
    approved=bool(gold) and all(x.get('review_status')=='APPROVED' and not validate_gold_record(x) for x in gold)
    compatible=bool(expected) and supplied==[expected]
    report={'status':'OFFICIAL' if approved and compatible else 'PROVISIONAL_DRAFT_GOLD',
      'warning':None if approved and compatible else 'Metrics require human-approved Gold pinned to this evaluation build.',
      'gold_build_id':expected,'supplied_gold_build_ids':supplied,'gold_build_compatible':compatible,'results':results}
    if a.pool_sweep:
        report['pool_sweep']=pool_sweep(pipe,gold)
        report['deployment_defaults_changed']=False
        report['scope']='Hybrid retrieval and optional reranking only; not full legal-answer accuracy or TTFT'
        report['recommendation']=None
        report['recommendation_note']='Human-approved build-matched Gold, adequate samples and end-to-end checks are required before changing Top-K.'
    pipe.close()
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(report,ensure_ascii=True,indent=2))
if __name__=='__main__': main()
