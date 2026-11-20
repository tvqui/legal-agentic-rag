"""Evaluate an ordering-only policy on frozen ranks; NOT a new neural/GPU run.

Predictions receive inference text, candidates and corpus edges only. Gold is
loaded for scoring after predictions. No thresholds are fitted to the qrels.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'đo'))
from eval_core import retrieval_metrics
from vn_labor_online.models import Evidence
from vn_labor_online.reference_selection import post_select_references,reference_intent


def sha(raw): return hashlib.sha256(raw).hexdigest()


def read_edges(artifact):
    if artifact.is_dir():
        files=[p for p in (artifact/'05_graph/edges.jsonl',artifact/'artifacts/05_graph/edges.jsonl') if p.is_file()]
        if len(files)!=1: raise ValueError('Expected one graph edges file')
        return files[0].read_bytes()
    with ZipFile(artifact) as z:
        names=[n for n in z.namelist() if n=='05_graph/edges.jsonl' or n.endswith('/05_graph/edges.jsonl')]
        if len(names)!=1: raise ValueError('Expected one graph edges member')
        return z.read(names[0])


def evaluate(archive,artifact,output):
    if output.exists(): raise FileExistsError('Choose a new output directory')
    with ZipFile(archive) as z:
        manifest=json.loads(z.read('bundle120/manifest.json'))
        raw_questions=z.read('bundle120/questions.jsonl')
        if sha(raw_questions)!=manifest['questions_sha256']: raise ValueError('Gold fingerprint mismatch')
        requests={q['id']:q for q in map(json.loads,z.read('bundle120/inference_questions.jsonl').splitlines())}
        # Strip Gold metrics before the prediction phase.
        frozen=[{'id':r['id'],'repeat':r['repeat'],'method':r['method'],'status':r['status'],
                 'ids':r.get('result',{}).get('retrieved_ids',[])}
                for r in map(json.loads,z.read('retrieval/responses.jsonl').splitlines())
                if r['method'] in {'hybrid_rerank','hybrid_graph_rerank'}]
        run=json.loads(z.read('retrieval/run_manifest.json'));k=run['k']
    edges=read_edges(artifact)
    if sha(edges)!=manifest['artifact_file_hashes']['05_graph/edges.jsonl']:
        raise ValueError('Graph fingerprint differs from frozen run')
    refs=defaultdict(set)
    for line in edges.splitlines():
        e=json.loads(line)
        if e['type']=='REFERENCES': refs[e['source']].add(e['target'])
    del edges
    lookup={(r['method'],r['id'],r['repeat']):r for r in frozen}
    if len(lookup)!=len(frozen) or any(r['status']!='OK' for r in frozen):
        raise ValueError('Frozen run contains duplicate keys or failed attempts')
    expected={(method,qid,repeat) for method in ('hybrid_rerank','hybrid_graph_rerank')
              for qid in run['selected_ids'] for repeat in range(1,run['repeats']+1)}
    if set(lookup)!=expected:
        raise ValueError('Frozen run is not a complete paired schedule')
    predictions=[]; selection_times=[]
    for row in frozen:
        if row['method']!='hybrid_graph_rerank': continue
        q=requests[row['id']]['question']
        if len(set(row['ids']))!=len(row['ids']): raise ValueError('Duplicate candidate IDs')
        for variant in ('reference_closure','routed_reference_closure'):
            use_graph=variant=='reference_closure' or reference_intent(q)
            base=row if use_graph else lookup[('hybrid_rerank',row['id'],row['repeat'])]
            # Scores/text were not archived. This policy uses IDs/order only;
            # placeholders cannot provide semantic or legal verification.
            items=[Evidence(unit_id=uid,text='',score=0,retrieval_method='frozen',rank=i)
                   for i,uid in enumerate(base['ids'],1)]
            start=time.perf_counter()
            selected=post_select_references(items,refs,q,k)
            selection_times.append((time.perf_counter()-start)*1000)
            ids=[e.unit_id for e in selected]
            if set(ids)!=set(base['ids']) or len(ids)!=len(base['ids']): raise AssertionError('Candidate pool changed')
            if ids and ids[0]!=base['ids'][0]: raise AssertionError('Primary seed changed')
            predictions.append({'id':row['id'],'repeat':row['repeat'],'variant':variant,'ids':ids,'graph_path_used':use_graph})
    # Prediction completed; only now use Gold to score the frozen policies.
    gold={q['id']:q for q in map(json.loads,raw_questions.splitlines())}
    results={}
    for variant in ('baseline_graph_rerank','baseline_hybrid_rerank','reference_closure','routed_reference_closure'):
        rows=[{'id':r['id'],'repeat':r['repeat'],'ids':r['ids']} for r in frozen
              if r['method']==('hybrid_graph_rerank' if variant=='baseline_graph_rerank' else 'hybrid_rerank')]
        if not variant.startswith('baseline_'): rows=[r for r in predictions if r['variant']==variant]
        scores=[retrieval_metrics(r['ids'],gold[r['id']]['required_groups'],k) for r in rows]
        results[variant]={name:statistics.mean(s[name] for s in scores) for name in scores[0]}
        results[variant]['all_groups_attempts']=sum(s['group_recall_at_k']==1 for s in scores)
        results[variant]['attempts']=len(rows)
    paired=[]
    for p in predictions:
        key=('hybrid_graph_rerank',p['id'],p['repeat'])
        before=retrieval_metrics(lookup[key]['ids'],gold[p['id']]['required_groups'],k)
        after=retrieval_metrics(p['ids'],gold[p['id']]['required_groups'],k)
        paired.append({'id':p['id'],'repeat':p['repeat'],'variant':p['variant'],
            'before':before,'after':after,'changed_top_k':p['ids'][:k]!=lookup[key]['ids'][:k]})
    details={}
    for variant in ('reference_closure','routed_reference_closure'):
        rows=[r for r in paired if r['variant']==variant and r['repeat']==1]
        details[variant]={'improved_recall':[r['id'] for r in rows if r['after']['group_recall_at_k']>r['before']['group_recall_at_k']],
            'worse_recall':[r['id'] for r in rows if r['after']['group_recall_at_k']<r['before']['group_recall_at_k']],
            'worse_mrr':[r['id'] for r in rows if r['after']['mrr_at_k']<r['before']['mrr_at_k']],
            'changed_head':[r['id'] for r in rows if r['changed_top_k']]}
    summary={'scope':'FROZEN_RANK_REPLAY_NOT_FRESH_NEURAL_INFERENCE','gold_status':manifest['label_status'],
        'evaluation_scope':manifest['evaluation_scope'],'k':k,'results':results,'paired':details,
        'query_count':len({r['id'] for r in predictions}),
        'routed_graph_queries':len({r['id'] for r in predictions if r['variant']=='routed_reference_closure' and r['graph_path_used']}),
        'selection_ms_mean':statistics.mean(selection_times),
        'archive_sha256':sha(archive.read_bytes()),'edge_sha256':manifest['artifact_file_hashes']['05_graph/edges.jsonl'],
        'selector_sha256':sha((ROOT/'src/vn_labor_online/reference_selection.py').read_bytes()),
        'note':'No model inference or latency improvement measured. Development labels, not independent legal QA.'}
    output.mkdir(parents=True)
    (output/'predictions.jsonl').write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in predictions),encoding='utf-8')
    (output/'paired.json').write_text(json.dumps(paired,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--artifact',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(evaluate(a.archive,a.artifact,a.output),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
