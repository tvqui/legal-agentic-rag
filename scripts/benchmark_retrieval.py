from __future__ import annotations
import argparse,json,time
from pathlib import Path
from vn_labor_online.config import load_config
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_online.analysis import intake,analyze
from vn_labor_offline.gold import validate_gold_record
def rows(path): return [json.loads(x) for x in path.read_text(encoding='utf-8-sig').splitlines() if x]
def main():
    p=argparse.ArgumentParser(); p.add_argument('--config',type=Path,default=Path('config/online.yaml')); p.add_argument('--gold',type=Path,required=True); p.add_argument('--out',type=Path,default=Path('artifacts/online_evaluation/retrieval_benchmark.json')); a=p.parse_args()
    pipe=OnlinePipeline(load_config(a.config)); gold=rows(a.gold); results={}
    for method in ('bm25','dense','hybrid'):
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
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(report,ensure_ascii=True,indent=2))
if __name__=='__main__': main()
