"""Exploratory, query-stratified audit of frozen retrieval outputs; no inference.

Groups are transparent textual proxies, NOT difficulty labels or held-out tests.
Do not use the development results as independent evidence of legal QA quality.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import re
from statistics import mean
import sys
import unicodedata
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'đo'))
from eval_core import retrieval_metrics

VERSION = 'graph-role-pilot-v1'

sys.path.insert(0, str(Path(__file__).resolve().parent))
METRICS = ('group_recall_at_k', 'mrr_at_k', 'group_ndcg_at_k', 'all_groups_found')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def classify(question):
    """No IDs, Gold, category labels, candidates, or retrieval scores accepted."""
    text = unicodedata.normalize('NFD', question.casefold())
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn').replace('đ', 'd')
    text = ' '.join(text.split())
    groups = []
    if re.search(r'\b(dan chieu|duoc dan|duoc vien dan|cross[ -]references?|referred to)\b', text):
        groups.append('explicit_cross_reference')
    if re.search(r'\b(ngoai le|ngoai tru|tru truong hop|exceptions?)\b', text):
        groups.append('exception_mentioned_not_requested' if re.search(
            r'\b(khong thuoc|khong nam trong|khong xet|khong ban ve)\b.{0,65}\bngoai le\b', text)
            and not (re.search(r'\b(liet ke|phan tich|giai thich)\b.{0,30}\bngoai le\b', text)
                     or re.search(r'\bnêu\b.{0,30}\bngoại lệ\b', unicodedata.normalize('NFC', question.casefold())))
            else 'exception_language')
    if (re.search(r'\b(danh gia rieng|hai van de|tung van de|dong thoi|va hau qua|hau qua phap ly)\b', text)
            or len(re.findall(r'\?', text)) >= 2):
        groups.append('multi_requirement_proxy')
    if re.search(r'\b(nguyen van|trich nguyen|quy dinh gi|pham vi dieu chinh)\b', text):
        groups.append('literal_lookup_proxy')
    if not groups:
        groups.append('ordinary_or_unclassified')
    return groups


def paired_ci(values, samples=2000, seed=42):
    """Bootstrap queries, never the repeated attempts as independent samples."""
    rng = random.Random(seed)
    values = list(values)
    if not values:
        return None
    boot = sorted(mean(rng.choices(values, k=len(values))) for _ in range(samples))
    return {'mean': mean(values), 'low': boot[int(.025 * samples)] if len(values) >= 2 else None,
            'high': boot[min(samples - 1, int(.975 * samples))] if len(values) >= 2 else None, 'n_queries': len(values),
            'wins': sum(v > 1e-12 for v in values), 'ties': sum(abs(v) <= 1e-12 for v in values),
            'losses': sum(v < -1e-12 for v in values)}


def validate_schedule(rows, methods, ids, repeats):
    expected = {(m, q, r) for m in methods for q in ids for r in range(1, repeats + 1)}
    seen = Counter((r['method'], r['id'], r['repeat']) for r in rows)
    if set(seen) != expected or any(n != 1 for n in seen.values()):
        raise ValueError('Incomplete/duplicate/unexpected paired schedule')
    if any(r['status'] != 'OK' for r in rows):
        raise ValueError('Failed attempts: no complete-case deletion is allowed')


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def evaluate(archive, output, replay=None, artifact=None):
    if output.exists():
        raise FileExistsError('Use a new pilot output directory')
    with ZipFile(archive) as z:
        manifest = json.loads(z.read('bundle120/manifest.json'))
        run = json.loads(z.read('retrieval/run_manifest.json'))
        inference_raw = z.read('bundle120/inference_questions.jsonl')
        inference_rows = [json.loads(s) for s in inference_raw.splitlines() if s.strip()]
        requests = {q['id']:q for q in inference_rows}
        selected = run['selected_ids']
        if len(requests) != len(inference_rows) or len(selected) != len(set(selected)) or set(selected)-set(requests):
            raise ValueError('Duplicate or missing inference query IDs')
        # Freeze membership before reading Gold or the measured outcomes.
        membership = [{'id':qid, 'question':requests[qid]['question'],
                       'groups': classify(requests[qid]['question'])} for qid in selected]
        output.mkdir(parents=True)
        write_json(output/'membership.json', {'protocol':VERSION, 'overlapping_groups':True,
                   'selection_basis':'QUERY_TEXT_ONLY_NOT_OUTCOMES', 'rows':membership,
                   'inference_sha256':digest(inference_raw),
                   'classifier_source_sha256':digest(Path(__file__).read_bytes())})
        rows = [json.loads(s) for s in z.read('retrieval/responses.jsonl').splitlines() if s.strip()]
        selection_rows = []
        edge_hash = None
        if artifact is not None:
            from replay_graph_selection import read_edges
            from vn_labor_online.models import Evidence
            from vn_labor_online.reference_selection import post_select_references
            edge_raw = read_edges(artifact)
            edge_hash = digest(edge_raw)
            if edge_hash != manifest['artifact_file_hashes']['05_graph/edges.jsonl']:
                raise ValueError('Graph fingerprint mismatch')
            refs = defaultdict(set)
            for line in edge_raw.splitlines():
                edge = json.loads(line)
                if edge['type'] == 'REFERENCES':
                    refs[edge['source']].add(edge['target'])
            # Same selector, but no graph-discovered candidates: isolates selection.
            for r in rows:
                if r['method'] == 'hybrid_rerank' and r['status'] == 'OK':
                    items = [Evidence(unit_id=uid, text='', score=0, rank=i, retrieval_method='frozen')
                             for i, uid in enumerate(r['result']['retrieved_ids'], 1)]
                    chosen = post_select_references(items, refs, requests[r['id']]['question'], run['k'])
                    selection_rows.append({'method':'selection_without_expansion','id':r['id'],
                        'repeat':r['repeat'],'status':'OK','result':{'retrieved_ids':[e.unit_id for e in chosen]}})
        gold_raw = z.read('bundle120/questions.jsonl')
        corpus_raw = z.read('bundle120/corpus.jsonl')
        if digest(gold_raw) != manifest['questions_sha256'] or digest(corpus_raw) != manifest['corpus_jsonl_sha256']:
            raise ValueError('Bundle fingerprint mismatch')
        gold_rows = [json.loads(s) for s in gold_raw.splitlines() if s.strip()]
        gold = {q['id']:q for q in gold_rows}
        if len(gold) != len(gold_rows):
            raise ValueError('Duplicate Gold IDs')
        for qid in selected:
            if any(requests[qid].get(k) != gold[qid].get(k) for k in ('question','query_date')):
                raise ValueError('Inference/Gold question or date mismatch')
        corpus = {json.loads(s)['unit_id'] for s in corpus_raw.splitlines() if s.strip()}
    required_methods = {'hybrid','hybrid_graph','hybrid_rerank','hybrid_graph_rerank'}
    if not required_methods.issubset(run['methods']) or not selected or run['repeats'] < 1:
        raise ValueError('Missing required methods, queries or repeats')
    validate_schedule(rows, run['methods'], selected, run['repeats'])
    for row in rows:
        ids = row['result']['retrieved_ids']
        if len(ids)!=len(set(ids)) or set(ids)-corpus:
            raise ValueError('Duplicate or unknown retrieved candidate ID')
    rows += selection_rows
    replay_hash = None
    if replay is not None:
        replay_meta = json.loads(replay.with_name('summary.json').read_text(encoding='utf-8'))
        selector_hash = digest((ROOT/'src/vn_labor_online/reference_selection.py').read_bytes())
        if (replay_meta.get('archive_sha256') != digest(archive.read_bytes())
                or replay_meta.get('selector_sha256') != selector_hash
                or replay_meta.get('edge_sha256') != manifest.get('artifact_file_hashes',{}).get('05_graph/edges.jsonl')):
            raise ValueError('Replay provenance mismatch')
        replay_hash = digest(replay.read_bytes())
        replay_rows = [json.loads(s) for s in replay.read_text(encoding='utf-8').splitlines() if s.strip()]
        if not replay_rows:
            raise ValueError('Empty replay schedule')
        variants = set(r['variant'] for r in replay_rows)
        if not variants.issubset({'reference_closure','routed_reference_closure'}):
            raise ValueError('Unknown replay policy variant')
        rp = [{'method':'replay_'+r['variant'], 'id':r['id'],'repeat':r['repeat'],'status':'OK',
               'result':{'retrieved_ids':r['ids']}} for r in replay_rows]
        validate_schedule(rp, ['replay_'+v for v in variants], selected, run['repeats'])
        source = {(r['method'],r['id'],r['repeat']):r['result']['retrieved_ids'] for r in rows}
        for r, p in zip(replay_rows, rp):
            from vn_labor_online.reference_selection import reference_intent
            expected_graph = r['variant']=='reference_closure' or reference_intent(requests[r['id']]['question'])
            if type(r['graph_path_used']) is not bool or r['graph_path_used'] != expected_graph:
                raise ValueError('Replay routing differs from named policy')
            base = source[('hybrid_graph_rerank' if r['graph_path_used'] else 'hybrid_rerank',r['id'],r['repeat'])]
            if len(p['result']['retrieved_ids']) != len(base) or set(p['result']['retrieved_ids']) != set(base):
                raise ValueError('Replay changes frozen candidate pool')
            if artifact is not None:
                items = [Evidence(unit_id=uid, text='', score=0, rank=i, retrieval_method='frozen')
                         for i, uid in enumerate(base, 1)]
                expected_ids = [e.unit_id for e in post_select_references(items, refs, requests[r['id']]['question'], run['k'])]
                if expected_ids != p['result']['retrieved_ids']:
                    raise ValueError('Replay ordering differs from recomputed selector')
        rows += rp
    scores = defaultdict(list)
    for r in rows:
        qid = r['id']; ids = r['result']['retrieved_ids']; groups = gold[qid]['required_groups']
        if not groups or any(not g for g in groups) or set(x for g in groups for x in g)-corpus:
            raise ValueError('Missing/unknown Gold groups')
        m = retrieval_metrics(ids, groups, run['k'])
        m['all_groups_found'] = float(m['group_recall_at_k'] == 1)
        m['pool_group_recall'] = sum(bool(set(ids)&set(g)) for g in groups)/len(groups)
        scores[(r['method'],qid)].append(m)
    query_scores = {key:{m:mean(s[m] for s in vals) for m in (*METRICS,'pool_group_recall')}
                    for key, vals in scores.items()}
    subsets = {'all_queries':selected}
    for q in membership:
        for group in q['groups']:
            subsets.setdefault(group,[]).append(q['id'])
    methods = sorted({m for m,_ in scores})
    tables = []; pairs = []
    for group, qids in subsets.items():
        for method in methods:
            tables.append({'group':group,'method':method,'n_queries':len(qids),
                **{m:mean(query_scores[(method,q)][m] for q in qids) for m in (*METRICS,'pool_group_recall')}})
        for method in methods:
            if method not in ('hybrid_graph_rerank','selection_without_expansion') and not method.startswith('replay_'):
                continue
            for metric in METRICS:
                delta = [query_scores[(method,q)][metric]-query_scores[('hybrid_rerank',q)][metric] for q in qids]
                pairs.append({'group':group,'baseline':'hybrid_rerank','method':method,'metric':metric,
                              **paired_ci(delta)})
    summary = {'protocol':VERSION,'scope':'EXPLORATORY_FROZEN_OUTPUT_AUDIT_NOT_FRESH_INFERENCE',
        'gold_status':manifest['label_status'], 'test_exposed':True,'independent_heldout':False,
        'groups_overlap':True, 'group_labels_are_textual_proxies':True,
        'n_queries':len(selected),'repeats':run['repeats'],'k':run['k'],
        'archive_sha256':digest(archive.read_bytes()), 'edge_sha256':edge_hash,
        'protocol_status':'POSTHOC_DEVELOPMENT_PILOT_NOT_PREREGISTERED', 'questions_sha256':manifest['questions_sha256'],
        'corpus_sha256':manifest['corpus_jsonl_sha256'],'replay_sha256':replay_hash,
        'warnings':['Not legal QA quality or response latency.',
                    'Candidate-pool coverage uses varying pool sizes; not an equal-K result.',
                    'Exploratory CIs are unadjusted for multiple overlapping subgroup comparisons.',
                    'Small textual subgroups cannot establish broad Graph superiority.'],
        'tables':tables, 'paired_vs_hybrid_rerank':pairs}
    write_json(output/'summary.json',summary)
    write_json(output/'per_query.json',[{'method':m,'id':q,**v} for (m,q),v in query_scores.items()])
    for name, records in [('tables',tables),('paired',pairs)]:
        with (output/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0])); writer.writeheader();writer.writerows(records)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--replay',type=Path)
    parser.add_argument('--artifact',type=Path, help='Optional matching artifact for selection-only counterfactual')
    args=parser.parse_args()
    result=evaluate(args.archive,args.output,args.replay,args.artifact)
    print(json.dumps({'output':str(args.output),'queries':result['n_queries'],'scope':result['scope']}))


if __name__=='__main__':
    main()
