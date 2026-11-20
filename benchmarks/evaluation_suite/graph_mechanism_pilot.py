"""Development-only mechanism audit; frozen comparisons are not fresh QA inference."""
from __future__ import annotations
import argparse,csv,hashlib,json,random,re,sys,unicodedata
from collections import Counter,defaultdict,deque
from pathlib import Path
from statistics import mean
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'đo'));sys.path.insert(0,str(Path(__file__).resolve().parent))
from eval_core import retrieval_metrics
from graph_role_pilot import paired_ci,validate_schedule
from replay_graph_selection import read_edges
from vn_labor_online.models import Evidence
from vn_labor_online.reference_selection import post_select_references
VERSION='graph-mechanism-development-v2'
FEATURES=('crossref_requested_proxy','exception_requested_proxy','exception_excluded_proxy','multi_issue_proxy_not_graph_necessity','multi_document_proxy','time_specific_or_transition_proxy','literal_lookup_proxy','ordinary_or_unclassified')
METRICS=('precision_at_k','group_recall_at_k','mrr_at_k','group_ndcg_at_k','all_groups_found')
ARMS=('expansion_off_selector_off','expansion_on_selector_off','expansion_off_selector_on','expansion_on_selector_on')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def dump(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def lines(raw):return [json.loads(s) for s in raw.splitlines() if s.strip()]

def features(question):
    """Textual proxies, not labels proving that Graph is necessary; no qrels/IDs."""
    original=unicodedata.normalize('NFC',question.casefold())
    s=''.join(c for c in unicodedata.normalize('NFD',original) if unicodedata.category(c)!='Mn').replace('đ','d')
    s=' '.join(s.split());tags=[]
    if re.search(r'\b(dan chieu|duoc dan|duoc vien dan|cross[ -]references?|referred to)\b',s):tags.append('crossref_requested_proxy')
    if re.search(r'\b(ngoai le|ngoai tru|exceptions?)\b',s):
        excluded=bool(re.search(r'\b(khong thuoc|khong nam trong|khong xet|khong ban ve)\b.{0,65}\bngoai le\b',s))
        request=bool(re.search(r'\bnêu\b.{0,40}\bngoại lệ\b',original) or re.search(r'\b(liet ke|phan tich|giai thich)\b.{0,40}\bngoai le\b',s))
        tags.append('exception_excluded_proxy' if excluded and not request else 'exception_requested_proxy')
    if re.search(r'\b(danh gia rieng|hai van de|tung van de|dong thoi|va hau qua|hau qua phap ly)\b',s) or s.count('?')>=2:tags.append('multi_issue_proxy_not_graph_necessity')
    if len(set(re.findall(r'\d{1,3}/(?:19|20)\d{2}/[a-z0-9-]+',s)))>=2 or re.search(r'\b(nhieu van ban|giua cac van ban|giua hai van ban)\b',s):tags.append('multi_document_proxy')
    time_text=re.sub(r'\d{1,3}/(?:19|20)\d{2}/[a-z0-9-]+','DOCUMENT_IDENTIFIER',s)
    if re.search(r'\b\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2}\b|\bnam (?:19|20)\d{2}\b|\b(chuyen tiep|het hieu luc|thay doi hieu luc|sua doi)\b',time_text):tags.append('time_specific_or_transition_proxy')
    if re.search(r'\b(nguyen van|trich nguyen|quy dinh gi|pham vi dieu chinh)\b',s):tags.append('literal_lookup_proxy')
    return tags or ['ordinary_or_unclassified']

def outcome(deltas):
    positive=any(v>1e-12 for v in deltas.values());negative=any(v< -1e-12 for v in deltas.values())
    return 'MIXED' if positive and negative else 'IMPROVED' if positive else 'HARMED' if negative else 'UNCHANGED'

def sample_membership(membership,per_feature=2,controls=3,seed=42):
    if type(per_feature) is not int or per_feature<1 or type(controls) is not int or controls<1:raise ValueError('Sample sizes must be positive integers')
    buckets=defaultdict(list)
    for row in membership:
        for f in row['features']:buckets[f].append(row['id'])
    rng=random.Random(seed);selected=set()
    for tag in sorted(buckets):
        ids=sorted(buckets[tag]);rng.shuffle(ids)
        selected.update(ids[:controls if tag=='ordinary_or_unclassified' else per_feature])
    return sorted(selected)

def structural_paths(seeds,targets,adj,max_hops=2):
    """Potential bounded graph connectivity, NOT reconstruction of the actual trace."""
    queue=deque((s,[]) for s in seeds);seen=set(seeds);found={}
    targets=set(targets)
    while queue:
        uid,path=queue.popleft()
        if uid in targets:found[uid]=path
        if len(path)>=max_hops:continue
        for e,target,direction in adj.get(uid,[]):
            if target not in seen:
                seen.add(target);queue.append((target,path+[{'edge_id':e.get('id'),'type':e['type'],'direction':direction,'from':uid,'to':target}]))
    return found

def evaluate(archive,artifact,output,per_feature=2,controls=3,seed=42):
    if output.exists():raise FileExistsError('Choose a new output directory')
    with ZipFile(archive) as z:
        manifest=json.loads(z.read('bundle120/manifest.json'));run=json.loads(z.read('retrieval/run_manifest.json'))
        request_raw=z.read('bundle120/inference_questions.jsonl');request_rows=lines(request_raw)
        requests={q['id']:q for q in request_rows};selected=run['selected_ids']
        if len(requests)!=len(request_rows) or len(selected)!=len(set(selected)) or set(selected)-set(requests) or not selected:raise ValueError('Missing/duplicate inference IDs')
        membership=[{'id':qid,'question':requests[qid]['question'],'query_date':requests[qid]['query_date'],'features':features(requests[qid]['question'])} for qid in sorted(selected)]
        sampled=sample_membership(membership,per_feature,controls,seed)
        output.mkdir(parents=True)
        dump(output/'selection.json',{'version':VERSION,'basis':'QUERY_ONLY_BEFORE_OUTCOMES','status':'POSTHOC_DEVELOPMENT_NOT_PREREGISTERED','seed':seed,'per_feature':per_feature,'ordinary_controls':controls,'sample_ids':sampled,'membership':membership,'source_sha256':sha(Path(__file__).read_bytes()),'inference_sha256':sha(request_raw),'archive_sha256':sha(archive.read_bytes()),'corpus_sha256':manifest['corpus_jsonl_sha256'],'gold_sha256':manifest['questions_sha256']})
        frozen_rows=lines(z.read('retrieval/responses.jsonl'))
        # Do not allow missing/error attempts to disappear from paired statistics.
        validate_schedule(frozen_rows,run['methods'],selected,run['repeats'])
        if not {'hybrid','hybrid_graph','hybrid_rerank','hybrid_graph_rerank'}.issubset(run['methods']):raise ValueError('Missing controlled arms')
        raw_gold=z.read('bundle120/questions.jsonl');raw_corpus=z.read('bundle120/corpus.jsonl')
        if sha(raw_gold)!=manifest['questions_sha256'] or sha(raw_corpus)!=manifest['corpus_jsonl_sha256']:raise ValueError('Bundle fingerprint mismatch')
        corpus_rows=lines(raw_corpus);corpus={u['unit_id']:u for u in corpus_rows}
        if len(corpus)!=len(corpus_rows):raise ValueError('Duplicate corpus IDs')
    edge_raw=read_edges(artifact)
    if sha(edge_raw)!=manifest['artifact_file_hashes']['05_graph/edges.jsonl']:raise ValueError('Graph fingerprint mismatch')
    refs=defaultdict(set);adj=defaultdict(list)
    effective=run.get('comparison_controls',{}).get('effective_online',{})
    allowed=effective.get('graph',{}).get('allowed_relations')
    edge_types=Counter()
    for e in lines(edge_raw):
        edge_types[e['type']]+=1
        if e['type']=='REFERENCES':refs[e['source']].add(e['target'])
        if allowed is None or e['type'] in allowed:
            adj[e['source']].append((e,e['target'],'OUT'));adj[e['target']].append((e,e['source'],'IN'))
    rows={(r['method'],r['id'],r['repeat']):r for r in frozen_rows}
    for r in frozen_rows:
        ids=r['result']['retrieved_ids']
        if len(ids)!=len(set(ids)) or set(ids)-set(corpus):raise ValueError('Duplicate/unknown ranked IDs')
    # Selection sees ONLY frozen order, query and graph, never Gold.
    predictions=[]
    for qid in sorted(selected):
        for repeat in range(1,run['repeats']+1):
            for graph_on in (False,True):
                base=rows[('hybrid_graph_rerank' if graph_on else 'hybrid_rerank',qid,repeat)]
                for selector_on in (False,True):
                    ids=base['result']['retrieved_ids']
                    if selector_on:
                        ev=[Evidence(unit_id=uid,text='',score=0,rank=i,retrieval_method='frozen') for i,uid in enumerate(ids,1)]
                        ids=[e.unit_id for e in post_select_references(ev,refs,requests[qid]['question'],run['k'])]
                    arm=f"expansion_{'on' if graph_on else 'off'}_selector_{'on' if selector_on else 'off'}"
                    predictions.append({'id':qid,'repeat':repeat,'arm':arm,'ids':ids,'observed_frozen_latency_ms':base.get('elapsed_ms') if not selector_on else None})
    (output/'predictions.jsonl').write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in predictions),encoding='utf8')
    gold_rows=lines(raw_gold);gold={q['id']:q for q in gold_rows}
    if len(gold)!=len(gold_rows):raise ValueError('Duplicate Gold IDs')
    for qid in selected:
        q=gold[qid]
        if any(q.get(f)!=requests[qid].get(f) for f in ('question','query_date')):raise ValueError('Inference/Gold mismatch')
        groups=q['required_groups'];flat=[u for g in groups for u in g]
        if not groups or any(not g for g in groups) or len(flat)!=len(set(flat)) or set(flat)-set(corpus):raise ValueError('Invalid Gold groups')
    attempt_metrics=defaultdict(list)
    for p in predictions:
        groups=gold[p['id']]['required_groups'];ids=p['ids'];m=retrieval_metrics(ids,groups,run['k'])
        m['all_groups_found']=float(m['group_recall_at_k']==1)
        m['pool_group_recall']=sum(bool(set(ids)&set(g)) for g in groups)/len(groups)
        attempt_metrics[(p['arm'],p['id'])].append(m)
    query_metrics={key:{k:mean(x[k] for x in vals) for k in (*METRICS,'pool_group_recall')} for key,vals in attempt_metrics.items()}
    subgroups={'all_queries':sorted(selected),'small_query_only_sample':sampled}
    for row in membership:
        for f in row['features']:subgroups.setdefault('feature:'+f,[]).append(row['id'])
    coverage=[{'feature':f,'population_count':sum(f in q['features'] for q in membership),'sample_count':sum(f in q['features'] and q['id'] in sampled for q in membership),
        'status':'SAMPLED' if any(f in q['features'] and q['id'] in sampled for q in membership) else 'NOT_SAMPLED',
        'metric_status':'AVAILABLE_EXPLORATORY' if any(f in q['features'] for q in membership) else 'NOT_EVALUATED_NO_QUESTIONS'} for f in FEATURES]
    tables=[];pairs=[]
    contrasts=[('expansion_off_selector_off','expansion_on_selector_off','GRAPH_ONLY_STORED'),('expansion_off_selector_on','expansion_on_selector_on','GRAPH_EXPANSION_WITH_SAME_REFERENCE_SELECTOR')]
    for subgroup,qids in subgroups.items():
        for arm in ARMS:
            tables.append({'group':subgroup,'arm':arm,'n_queries':len(qids),**{m:mean(query_metrics[(arm,q)][m] for q in qids) for m in (*METRICS,'pool_group_recall')}})
        for left,right,label in contrasts:
            for metric in METRICS:
                delta=[query_metrics[(right,q)][metric]-query_metrics[(left,q)][metric] for q in qids]
                pairs.append({'group':subgroup,'contrast':label,'metric':metric,'left':left,'right':right,**paired_ci(delta)})
    evidence=[];cases=[]
    first={(p['arm'],p['id']):p for p in predictions if p['repeat']==1}
    for qid in sorted(selected):
        group_ids={u for g in gold[qid]['required_groups'] for u in g};k=run['k']
        base=first[(ARMS[0],qid)]['ids'];expanded=first[(ARMS[1],qid)]['ids']
        seeds=rows[('hybrid',qid,1)]['result']['retrieved_ids'][:5]
        novel=set(expanded)-set(base);targets=group_ids|novel
        paths=structural_paths(seeds,targets,adj,run.get('settings',{}).get('graph_hops',2))
        before=query_metrics[(ARMS[0],qid)];after=query_metrics[(ARMS[1],qid)]
        changed={metric:after[metric]-before[metric] for metric in METRICS}
        same_selector_changed={metric:query_metrics[(ARMS[3],qid)][metric]-query_metrics[(ARMS[2],qid)][metric] for metric in METRICS}
        selector_before=first[(ARMS[2],qid)]['ids'];selector_after=first[(ARMS[3],qid)]['ids']
        cases.append({'id':qid,'question':requests[qid]['question'],'sampled':qid in sampled,'features':features(requests[qid]['question']),
            'graph_only_deltas':changed,'graph_only_outcome':outcome(changed),
            'expansion_same_selector_deltas':same_selector_changed,'expansion_same_selector_outcome':outcome(same_selector_changed),
            'same_selector_before_missing_groups':[g for g in gold[qid]['required_groups'] if not set(selector_before[:k])&set(g)],
            'same_selector_after_missing_groups':[g for g in gold[qid]['required_groups'] if not set(selector_after[:k])&set(g)],
            'baseline_missing_groups':[g for g in gold[qid]['required_groups'] if not set(base[:k])&set(g)],'graph_missing_groups':[g for g in gold[qid]['required_groups'] if not set(expanded[:k])&set(g)],
            'new_graph_pool_gold_ids':sorted(novel&group_ids),'candidate_counts':{'off':len(base),'on':len(expanded)},
            'qa_correctness':None,'citation_accuracy':None,'qa_status':'NOT_EVALUATED_NO_ANSWER_INFERENCE'})
        for uid in sorted(set(base[:k])|set(expanded[:k])|group_ids|novel):
            u=corpus[uid]
            evidence.append({'query_id':qid,'unit_id':uid,'gold_group_indexes':[i for i,g in enumerate(gold[qid]['required_groups']) if uid in g],
                'ranks':{arm:(first[(arm,qid)]['ids'].index(uid)+1 if uid in first[(arm,qid)]['ids'] else None) for arm in ARMS},
                'new_in_graph_pool':uid in novel,'source_text':u.get('source_text') or u.get('text',''),
                'locator':{f:u.get(f) for f in ('instrument_number','document_number','article_number','clause_number','point_number')},
                'source_url':u.get('source_url'),'valid_from':u.get('valid_from'),'valid_to':u.get('valid_to'),'temporal_reviewed':u.get('provision_temporal_verified'),
                'structural_path':paths.get(uid),'path_status':('POTENTIAL_CONNECTIVITY_ALLOWED_RELATIONS_NOT_ACTUAL_TRAVERSAL_TRACE' if allowed is not None else 'POTENTIAL_CONNECTIVITY_UNCONSTRAINED_NOT_ACTUAL_TRAVERSAL_TRACE')})
    frozen_times=[]
    for group,qids in subgroups.items():
        for method in ('hybrid_rerank','hybrid_graph_rerank'):
            vals=[mean(rows[(method,q,r)]['elapsed_ms'] for r in range(1,run['repeats']+1)) for q in qids if all(isinstance(rows[(method,q,r)].get('elapsed_ms'),(float,int)) for r in range(1,run['repeats']+1))]
            frozen_times.append({'group':group,'method':method,'query_mean_ms':mean(vals) if vals else None,'n_queries':len(vals),'scope':'OBSERVED_PRIOR_KAGGLE_NOT_LOCAL_NOT_SELECTOR_LATENCY'})
    summary={'version':VERSION,'scope':'POSTHOC_DEVELOPMENT_FROZEN_COMPONENT_AUDIT_NOT_FRESH_QA','gold_status':manifest['label_status'],'held_out':False,
        'archive_sha256':sha(archive.read_bytes()),'edge_sha256':sha(edge_raw),'corpus_sha256':sha(raw_corpus),'gold_sha256':sha(raw_gold),'source_sha256':sha(Path(__file__).read_bytes()),
        'selector_sha256':sha((ROOT/'src/vn_labor_online/reference_selection.py').read_bytes()),'run_source':run.get('source_tree'),'environment':run.get('environment'),'path_allowed_relations':allowed,
        'query_count':len(selected),'sample_count':len(sampled),'repeat_count':run['repeats'],'k':run['k'],'graph_edge_type_counts':dict(edge_types),
        'coverage_catalog':coverage,
        'capabilities':{'IMPLEMENTS_edge_count':edge_types.get('IMPLEMENTS',0),'cross_document_rule':'No claim of implementing-regulation traversal if the required edges are absent; cross-document REFERENCES may still exist.',
            'case_channel':'Not requested by these BM25/Dense/Hybrid frozen retrieval variants; not a test of Fact Graph case retrieval.',
            'temporal_filter_shared':True,'temporal_rule':'Date/authority filtering is shared by both retrieval arms; interval validity alone is not evidence of a unique Graph benefit.'},
        'selector_warning':'Both selector_on arms use REFERENCES. This contrast isolates candidate EXPANSION, not all graph usage.',
        'limitations':['Textual features are not expert-reviewed Graph-necessity labels.','All questions are development-exposed; small groups and unadjusted overlapping CIs do not prove general superiority.','Graph arms can contain more candidates: discovery benefit includes candidate-compute budget.','Paths show potential connectivity, not observed traversal causality.','Stored Graph only contrast is not a fresh local experiment.'],
        'unmeasured':{'qa_accuracy':'NOT_EVALUATED','qa_completeness':'NOT_EVALUATED','citation_accuracy':'NOT_EVALUATED','local_end_to_end_latency':'NOT_EVALUATED'},
        'tables':tables,'pairs':pairs,'observed_prior_latency':frozen_times}
    dump(output/'summary.json',summary);dump(output/'cases.json',cases);dump(output/'evidence.json',evidence)
    for name,items in [('tables',tables),('paired',pairs),('observed_prior_latency',frozen_times),('coverage_catalog',coverage)]:
        with (output/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--artifact',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--per-feature',type=int,default=2);p.add_argument('--controls',type=int,default=3);p.add_argument('--seed',type=int,default=42);a=p.parse_args()
    result=evaluate(a.archive,a.artifact,a.output,a.per_feature,a.controls,a.seed)
    print(json.dumps({k:result[k] for k in ('scope','query_count','sample_count','gold_status')}))
if __name__=='__main__':main()
