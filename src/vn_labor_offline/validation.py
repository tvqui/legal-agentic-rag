from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from .util import read_jsonl, write_jsonl


def validate(registry, extracted, provisions, cases, checklists, graph_nodes, graph_edges, output_dir: Path, cfg=None) -> dict:
    issues=[]
    by_file={x['file_id']:x for x in extracted}
    for d in registry:
        x=by_file.get(d['file_id'],{})
        if x.get('text_chars',0) < 100:
            issues.append({'severity':'ERROR','type':'NO_MACHINE_TEXT','document_id':d['document_id'],'path':d['relative_path']})
        elif x.get('text_chars',0) < 1200:
            issues.append({'severity':'WARN','type':'LOW_MACHINE_TEXT','document_id':d['document_id'],'path':d['relative_path']})
        if d['source_group']=='LEGAL_DOCUMENT' and not d.get('document_number'):
            issues.append({'severity':'WARN','type':'MISSING_DOCUMENT_NUMBER','document_id':d['document_id'],'path':d['relative_path']})
        if d['source_group']=='LEGAL_DOCUMENT' and not d.get('effective_from'):
            issues.append({'severity':'WARN','type':'MISSING_EFFECTIVE_FROM','document_id':d['document_id'],'path':d['relative_path']})
        if d['source_group']=='LEGAL_DOCUMENT' and d.get('status') in {None, '', 'UNKNOWN'}:
            issues.append({'severity':'WARN','type':'UNKNOWN_LEGAL_STATUS','document_id':d['document_id'],'path':d['relative_path']})
    for label, rows, key in [('DOCUMENT', registry, 'document_id'), ('PROVISION', provisions, 'provision_id')]:
        for identifier, count in Counter(row[key] for row in rows).items():
            if count > 1:
                issues.append({'severity':'ERROR','type':f'DUPLICATE_{label}_ID','id':identifier,'count':count})
    docs={d['document_id'] for d in registry}
    provs={p['provision_id']:p for p in provisions}
    for p in provisions:
        parent=provs.get(p['parent_id'])
        expected={'CLAUSE':'ARTICLE','POINT':'CLAUSE'}.get(p['level'])
        valid=(p['document_id'] in docs and
               ((p['level']=='ARTICLE' and p['parent_id']==p['document_id']) or
                (expected is not None and parent is not None and parent['level']==expected and parent['document_id']==p['document_id'])))
        if not valid:
            issues.append({'severity':'ERROR','type':'INVALID_PROVISION_PARENT','provision_id':p['provision_id']})
        if not p.get('provision_identity_id'):
            issues.append({'severity':'ERROR','type':'MISSING_PROVISION_IDENTITY','provision_id':p['provision_id']})
        if p.get('provenance_status') == 'UNRESOLVED':
            issues.append({'severity':'ERROR','type':'UNRESOLVED_PROVISION_PROVENANCE','provision_id':p['provision_id']})
    legal_docs={d['document_id'] for d in registry if d['document_type'] in {'LAW','DECREE','CIRCULAR','RESOLUTION','CONSOLIDATED','HISTORICAL'}}
    parsed_docs={p['document_id'] for p in provisions}
    for did in legal_docs-parsed_docs:
        d=next(x for x in registry if x['document_id']==did)
        issues.append({'severity':'ERROR','type':'NO_ARTICLE_PARSED','document_id':did,'path':d['relative_path']})
    if len(cases) < 30:
        issues.append({'severity':'INFO','type':'CASE_CORPUS_SMALL','message':f'{len(cases)} judicial items; enough for pipeline development, expand before evaluation.'})
    node_ids={n['id'] for n in graph_nodes}
    bad_edges=[e for e in graph_edges if e['source'] not in node_ids or e['target'] not in node_ids]
    for e in bad_edges: issues.append({'severity':'ERROR','type':'DANGLING_EDGE','edge_id':e['id']})
    for kind, names in {
        'DENSE': ['06_indexes/dense/faiss.index', '06_indexes/dense/vectors.npy', '06_indexes/dense/metadata.jsonl'],
        'BM25': ['06_indexes/bm25/params.index.json', '06_indexes/bm25/corpus.jsonl'],
    }.items():
        missing=[name for name in names if not (output_dir/name).is_file() or (output_dir/name).stat().st_size == 0]
        if missing:
            issues.append({'severity':'ERROR','type':f'MISSING_{kind}_INDEX','paths':missing})
    from .quality import quality_issues
    issues.extend(quality_issues(registry,extracted,provisions,graph_nodes,graph_edges,output_dir,cfg))
    summary={
        'documents':len(registry),'provisions':len(provisions),'cases':len(cases),'diagnostic_items':len(checklists),
        'graph_nodes':len(graph_nodes),'graph_edges':len(graph_edges),
        'issues_by_type':dict(Counter(i['type'] for i in issues)),
        'ready_for_offline_v1': bool(registry and provisions and graph_nodes and graph_edges) and not any(i['severity']=='ERROR' or i['type'] in {'MISSING_EFFECTIVE_FROM','UNKNOWN_LEGAL_STATUS'} for i in issues),
        'note':'This checks local construction only. Run scripts/validate_outputs.py --neo4j for index queries and live Graph DB verification. Temporal QA coverage also depends on historical corpus completeness.'
    }
    from .scanner import source_catalog_gate
    catalog_path=output_dir/'00_manifest/source_catalog_resolved.jsonl'
    catalog=[]
    if catalog_path.exists():
        catalog=list(read_jsonl(catalog_path))
        if len(catalog)!=len(registry) or len({r.get('file_id') for r in catalog})!=len(catalog):
            issues.append({'severity':'ERROR','type':'SOURCE_CATALOG_COVERAGE_MISMATCH'})
        if any(r.get('catalog_status')=='VERIFIED' and (not r.get('source_url') or not r.get('source_provider')) for r in catalog):
            issues.append({'severity':'ERROR','type':'AUTHORITATIVE_SOURCE_MISSING_PROVIDER_OR_URL'})
    else:
        issues.append({'severity':'ERROR','type':'MISSING_SOURCE_CATALOG_RESOLVED'})
    summary['source_catalog_quality']=source_catalog_gate(catalog,registry)
    from .readiness import semantic_readiness_gate
    summary['semantic_quality']=semantic_readiness_gate(output_dir,registry)
    summary['issues_by_type']=dict(Counter(i['type'] for i in issues))
    summary['ready_for_offline_v1']=bool(registry and provisions and graph_nodes and graph_edges) and not any(
        i['severity']=='ERROR' or i['type'] in {'MISSING_EFFECTIVE_FROM','UNKNOWN_LEGAL_STATUS'} for i in issues)
    # Technical smoke tests are not a gold-standard legal retrieval evaluation.
    from .evaluation import reviewed_quality_gate
    evaluation=reviewed_quality_gate(output_dir,graph_nodes,graph_edges)
    summary['offline_ready_for_online']=(summary['ready_for_offline_v1'] and evaluation['passed'] and
        summary['source_catalog_quality']['passed'] and summary['semantic_quality']['passed'])
    summary['legal_quality_evaluation']=evaluation
    from .gold import evaluate_gold
    gold_evaluation=evaluate_gold(output_dir)
    summary['gold_evaluation']=gold_evaluation
    summary['offline_ready_for_online']=summary['offline_ready_for_online'] and gold_evaluation['passed']
    rdir=output_dir/'reports'; rdir.mkdir(parents=True,exist_ok=True)
    write_jsonl(rdir/'validation_issues.jsonl',issues)
    (rdir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    md=['# Offline construction summary','']+[f'- **{k}**: {v}' for k,v in summary.items()]
    (rdir/'summary.md').write_text('\n'.join(md),encoding='utf-8')
    return summary
