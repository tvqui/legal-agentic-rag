"""Fresh CPU BM25/Graph component diagnostic, not Hybrid/LLM legal QA.

Gold-blind predictions for four fixed arms; only graph expansion and the
reference selector are toggled. It never downloads or calls a model.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
from statistics import mean
import sys
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'đo'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_core import retrieval_metrics
from labor_retrieval import runtime
from graph_role_pilot import paired_ci
from vn_labor_online.graph import GraphExplorer
from vn_labor_online.reference_selection import post_select_references
from vn_labor_online.retrieval import authority_filter, temporal_filter

ARMS = {'no_graph':(False,False), 'graph_expansion':(True,False),
        'reference_selection_only':(False,True), 'graph_and_selection':(True,True)}


def sha(raw): return hashlib.sha256(raw).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')


def inference_request(row):
    """Explicit allowlist so qrels/category/outcomes cannot enter prediction."""
    return {k:row[k] for k in ('id','question','query_date')}


def eligible(items, request):
    values, _ = temporal_filter(items, request['query_date'], strict=False)
    return authority_filter(values, strict=False)[0]


def candidate_union(base, added, cap=10):
    if type(cap) is not int or cap < 0: raise ValueError('Invalid graph addition cap')
    seen={e.unit_id for e in base}; new=[]
    for e in added:
        if e.unit_id not in seen:
            new.append(e);seen.add(e.unit_id)
    return list(base)+new[:cap]


def predict_arm(arm, request, base, graph, k=10):
    use_graph,use_selector=ARMS[arm]
    start=time.perf_counter();values=list(base);stats={};graph_ms=0
    if use_graph:
        gstart=time.perf_counter()
        expanded, stats=graph.expand(values[:5],[],request['question'])
        values=candidate_union(values,eligible(expanded,request),10)
        graph_ms=(time.perf_counter()-gstart)*1000
    selector_started=time.perf_counter()
    if use_selector:
        values=post_select_references(values,graph.references_by_source,request['question'],k)
    selector_ms=(time.perf_counter()-selector_started)*1000 if use_selector else 0
    base_ids={e.unit_id for e in base}
    return {'arm':arm,'ids':[e.unit_id for e in values],
            'graph_expansion':use_graph,'reference_selection':use_selector,
            'new_ids':[e.unit_id for e in values if e.unit_id not in base_ids],
            'graph_paths':{e.unit_id:{'edges':e.graph_path,'relations':e.graph_relations,
                           'directions':e.graph_directions} for e in values if e.unit_id not in base_ids},
            'graph_stats':stats,'graph_and_filter_ms':graph_ms,'selector_ms':selector_ms,
            'arm_transform_ms':(time.perf_counter()-start)*1000}


def arm_order(repeat, query_index):
    order=list(ARMS)
    return order if (repeat+query_index)%2 else order[::-1]


def provenance():
    paths=('src/vn_labor_online/graph.py','src/vn_labor_online/retrieval.py',
           'src/vn_labor_online/reference_selection.py','benchmarks/evaluation_suite/labor_retrieval.py',
           'benchmarks/evaluation_suite/graph_role_pilot.py','đo/eval_core.py')
    packages={}
    for package in ('bm25s','numpy','torch'):
        try: packages[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: packages[package]=None
    return {'source_hashes':{name:sha((ROOT/name).read_bytes()) for name in paths},'packages':packages}


def subgroup_analysis(scored, ids, members, metric_names, repeats):
    expected={(arm,qid,rep) for arm in ARMS for qid in ids for rep in range(1,repeats+1)}
    counts=Counter((r['arm'],r['id'],r['repeat']) for r in scored)
    if set(counts)!=expected or any(n!=1 for n in counts.values()):
        raise ValueError('Incomplete or duplicated scored schedule')
    query_scores={}
    stability={}
    for arm in ARMS:
        changed=[];changed_paths=[]
        for qid in ids:
            rows=[r for r in scored if r['arm']==arm and r['id']==qid]
            query_scores[(arm,qid)]={m:mean(r[m] for r in rows) for m in metric_names}
            if len({tuple(r['ids']) for r in rows})>1: changed.append(qid)
            if len({json.dumps(r.get('graph_paths',{}),sort_keys=True) for r in rows})>1: changed_paths.append(qid)
        stability[arm]={'n_queries':len(ids),'rank_unstable_ids':changed,'path_unstable_ids':changed_paths,
                        'stable':not changed and not changed_paths}
    groups={'all_sample':list(ids)}
    for feature in sorted({f for q in members.values() for f in q.get('features',[])}):
        groups[feature]=[qid for qid in ids if feature in members[qid].get('features',[])]
    tables=[];pairs=[]
    contrasts=(('graph_expansion','no_graph','GRAPH_EXPANSION_WITH_SELECTOR_OFF'),
               ('graph_and_selection','reference_selection_only','GRAPH_EXPANSION_WITH_SELECTOR_ON'),
               ('reference_selection_only','no_graph','SELECTION_WITHOUT_EXPANSION'),
               ('graph_and_selection','graph_expansion','SELECTION_AFTER_EXPANSION'),
               ('graph_and_selection','no_graph','COMBINED_SYSTEM_EFFECT_NOT_GRAPH_ALONE'))
    for group,qids in groups.items():
        for arm in ARMS:
            tables.append({'group':group,'arm':arm,'n_queries':len(qids),
                           **{m:mean(query_scores[(arm,q)][m] for q in qids) if qids else None
                              for m in metric_names}})
        for left,right,contrast in contrasts:
            for metric in ('group_recall_at_k','mrr_at_k','group_ndcg_at_k','all_groups_found','pool_group_recall'):
                delta=[query_scores[(left,q)][metric]-query_scores[(right,q)][metric] for q in qids]
                ci=paired_ci(delta) or {'mean':None,'low':None,'high':None,'n_queries':0,'wins':0,'ties':0,'losses':0}
                pairs.append({'group':group,'contrast':contrast,'left':left,'right':right,
                              'direction':'left_minus_right','metric':metric,**ci})
    return {'subgroup_tables':tables,'paired':pairs,'repeat_stability':stability,
            'query_metrics':[{'arm':arm,'id':qid,**values} for (arm,qid),values in query_scores.items()]}


def evaluate(archive, artifact, selection, output, cache, repeats=3):
    if output.exists(): raise FileExistsError('Choose new output directory')
    if type(repeats) is not int or repeats<1: raise ValueError('Positive repeats required')
    selection_raw=selection.read_bytes();chosen=json.loads(selection_raw)
    ids=chosen['sample_ids']
    if not ids or len(ids)!=len(set(ids)): raise ValueError('Empty/duplicate selected IDs')
    with ZipFile(archive) as z:
        manifest=json.loads(z.read('bundle120/manifest.json'))
        inference_raw=z.read('bundle120/inference_questions.jsonl')
        requests_list=[inference_request(json.loads(s)) for s in inference_raw.splitlines() if s.strip()]
        requests={q['id']:q for q in requests_list}
        if len(requests)!=len(requests_list) or set(ids)-set(requests):
            raise ValueError('Missing/duplicate inference IDs')
        members={q['id']:q for q in chosen['membership']}
        if len(members)!=len(chosen['membership']) or set(ids)-set(members):
            raise ValueError('Missing/duplicate selection membership')
        for qid in ids:
            if inference_request(members[qid])!=requests[qid]:
                raise ValueError('Selection differs from inference text/date')
        required_selection={'archive_sha256':sha(archive.read_bytes()),'inference_sha256':sha(inference_raw),
                            'corpus_sha256':manifest['corpus_jsonl_sha256'],'gold_sha256':manifest['questions_sha256']}
        if any(chosen.get(key)!=value for key,value in required_selection.items()):
            raise ValueError('Selection archive/inference/corpus/Gold fingerprint mismatch')
        gold_raw=z.read('bundle120/questions.jsonl')
        corpus_raw=z.read('bundle120/corpus.jsonl')
        if sha(gold_raw)!=manifest['questions_sha256'] or sha(corpus_raw)!=manifest['corpus_jsonl_sha256']:
            raise ValueError('Bundle fingerprint mismatch')
    cfg,store,retriever,_,hashes=runtime(str(artifact),str(cache),'cpu')
    if hashes!=manifest['artifact_file_hashes']: raise ValueError('Artifact fingerprint mismatch')
    cfg.retrieval.bm25_top_k=30
    graph=GraphExplorer(store,cfg.graph)
    output.mkdir(parents=True)
    dump(output/'selection.json',{'sample_ids':ids,'requests':[requests[q] for q in ids],
                                 'selection_sha256':sha(selection_raw),'selection_source':str(selection)})
    # Unrelated fixed warm-up, excluded from all recorded query timings.
    warm={'id':'warmup','question':'Quy định về hợp đồng lao động','query_date':'2026-09-15'}
    warm_base=eligible(retriever.bm25(warm['question']),warm)
    for arm in ARMS: predict_arm(arm,warm,warm_base,graph)
    predictions=[]
    for repeat in range(1,repeats+1):
        for qi,qid in enumerate(ids):
            request=requests[qid]
            start=time.perf_counter();base=eligible(retriever.bm25(request['question']),request)
            bm25_ms=(time.perf_counter()-start)*1000
            for arm in arm_order(repeat,qi):
                row=predict_arm(arm,request,base,graph)
                row.update(id=qid,repeat=repeat,bm25_shared_ms=bm25_ms,
                           composite_component_ms=bm25_ms+row['arm_transform_ms'])
                predictions.append(row)
    # Predictions are committed before parsing/scoring any Gold labels.
    (output/'predictions.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in predictions),encoding='utf8')
    gold_rows=[json.loads(s) for s in gold_raw.splitlines() if s.strip()]
    gold={q['id']:q for q in gold_rows}
    if len(gold)!=len(gold_rows): raise ValueError('Duplicate Gold IDs')
    corpus={json.loads(s)['unit_id'] for s in corpus_raw.splitlines() if s.strip()}
    for qid in ids:
        if inference_request(gold[qid])!=requests[qid]: raise ValueError('Gold/inference query mismatch')
        groups=gold[qid]['required_groups'];flat=[u for g in groups for u in g]
        if not groups or any(not g for g in groups) or len(flat)!=len(set(flat)) or set(flat)-corpus:
            raise ValueError('Invalid Gold groups')
    scored=[]
    for r in predictions:
        if len(r['ids'])!=len(set(r['ids'])) or set(r['ids'])-corpus: raise ValueError('Invalid prediction IDs')
        groups=gold[r['id']]['required_groups'];m=retrieval_metrics(r['ids'],groups,10)
        m['all_groups_found']=float(m['group_recall_at_k']==1)
        m['pool_group_recall']=sum(bool(set(r['ids'])&set(g)) for g in groups)/len(groups)
        scored.append({**r,**m})
    metric_names=('precision_at_k','recall_at_k','group_recall_at_k','mrr_at_k','ndcg_at_k',
                  'group_ndcg_at_k','all_groups_found','pool_group_recall')
    metrics={}
    for arm in ARMS:
        rows=[r for r in scored if r['arm']==arm]
        metrics[arm]={m:mean(mean(r[m] for r in rows if r['id']==qid) for qid in ids) for m in metric_names}
        metrics[arm].update(mean_composite_component_ms=mean(r['composite_component_ms'] for r in rows),
                           mean_graph_filter_ms=mean(r['graph_and_filter_ms'] for r in rows),
                           mean_selector_ms=mean(r['selector_ms'] for r in rows),
                           mean_pool_size=mean(len(r['ids']) for r in rows))
    subgroup=subgroup_analysis(scored,ids,members,metric_names,repeats)
    summary={'status':'COMPLETE','scope':'FRESH_CPU_BM25_GRAPH_COMPONENT_DIAGNOSTIC_NOT_HYBRID_OR_QA',
        'gold_status':manifest['label_status'],'independent_heldout':False,'queries':len(ids),'repeats':repeats,'k':10,
        'archive_sha256':sha(archive.read_bytes()),'selection_sha256':sha(selection_raw),
        'artifact_file_hashes':hashes,'source_sha256':sha(Path(__file__).read_bytes()),
        'python':platform.python_version(),'graph_config':cfg.graph.model_dump(mode='json'),
        'bm25_candidates':30,'graph_max_additions':10,'arms':ARMS,'metrics':metrics,
        'qa_accuracy':None,'citation_accuracy':None,'qa_status':'NOT_EVALUATED','citation_accuracy_status':'NOT_EVALUATED','llm_calls':0,
        **provenance(),**{k:v for k,v in subgroup.items() if k!='query_metrics'},
        'timing_notes':'Artifact/model index loading and fixed warm-up excluded. One shared BM25 per query/repeat; composite is shared BM25 + independently measured arm transform, not four independent end-to-end runs. Graph and feature caches warmed. Arm order alternates ABCD/DCBA.',
        'limits':['BM25 CPU only; no Dense/reranker/LLM. No QA/citation accuracy inferred.',
                  'reference_selection_only still reads graph REFERENCES edges, but adds no candidates.',
                  'Append-only union with no reranker means Graph-only top10 is unchanged by construction whenever baseline has at least10 candidates. This diagnoses discovery, not intrinsic Graph effectiveness.',
                  'Development sample selected query-only from already exposed questions; not held-out evidence.',
                  'Subgroups overlap; small-sample bootstrap CIs are exploratory and unadjusted for multiple comparisons.']}
    dump(output/'summary.json',summary)
    dump(output/'scored.json',scored)
    dump(output/'query_metrics.json',subgroup['query_metrics'])
    for name,records in [('subgroup_tables',subgroup['subgroup_tables']),('paired',subgroup['paired'])]:
        with (output/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    with (output/'per_query.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['id','repeat','arm',*metric_names,'bm25_shared_ms','graph_and_filter_ms','selector_ms','composite_component_ms']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        writer.writerows({k:r[k] for k in fields} for r in scored)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','artifact','selection','output','cache'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--repeats',type=int,default=3);a=p.parse_args()
    s=evaluate(a.archive,a.artifact,a.selection,a.output,a.cache,a.repeats)
    print(json.dumps({'status':s['status'],'queries':s['queries'],'scope':s['scope'],'metrics':s['metrics']},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
