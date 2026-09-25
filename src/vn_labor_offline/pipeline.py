from __future__ import annotations
from pathlib import Path
import json,subprocess,sys
from .scanner import scan, resolve_source_catalog
from .extract import extract_all
from .metadata import build_registry
from .legal_structure import parse_all
from .cases import build_cases,enrich_case_ontology
from .checklists import build_checklists
from .issues import build_issue_assignments
from .relations import build_relation_edges
from .indexes import build_retrieval_units,build_bm25_index
from .communities import build_case_communities
from .graph_builder import build_graph
from .validation import validate
from .provenance import enrich_provenance
from .provision_versions import materialize_provision_versions
from .hierarchy_headings import build_hierarchy_headings
from .util import read_jsonl,write_jsonl


def load_stage(out,name): return list(read_jsonl(out/name))

def dense_worker(cfg):
    out=cfg['output_dir']; request=out/'reports/dense_request.json'
    request.write_text(json.dumps(cfg,default=str),encoding='utf-8')
    with (out/'reports/dense_build.log').open('w',encoding='utf-8') as log:
        result=subprocess.run([sys.executable,'-m','vn_labor_offline.dense_worker',str(request)],stdout=log,stderr=subprocess.STDOUT)
    if result.returncode: raise RuntimeError(f'Dense subprocess exited {result.returncode}; see reports/dense_build.log')

def saved_embeddings(out,units):
    import numpy as np
    if load_stage(out,'06_indexes/dense/metadata.jsonl')!=units: raise ValueError('Dense metadata does not match current units')
    vectors=np.load(out/'06_indexes/dense/vectors.npy',allow_pickle=False)
    if len(vectors)!=len(units): raise ValueError('Dense row count mismatch')
    return {u['unit_id']:vectors[i] for i,u in enumerate(units)}

def construct_from_extracted(cfg,extracted,checklist_mode=None,build_indexes=True):
    out=cfg['output_dir']; out.mkdir(parents=True,exist_ok=True)
    # A restored checkpoint may contain proof for an older graph build.
    (out/'reports/neo4j_validation.json').unlink(missing_ok=True)
    write_jsonl(out/'reports/build_issues.jsonl',[])
    if not (out/'00_manifest/source_catalog_resolved.jsonl').exists():
        resolve_source_catalog(extracted,cfg['project_root'],out)
    registry=build_registry(extracted,cfg,out)
    provisions=parse_all(registry,extracted,out,cfg)
    provisions=enrich_provenance(provisions,extracted,registry,out)
    segments=load_stage(out,'03_structure/segments.jsonl')
    build_hierarchy_headings(registry,extracted,segments,out)
    identities, provision_versions=materialize_provision_versions(registry,provisions,out,cfg['project_root'])
    cases=build_cases(registry,extracted,out)
    if cfg['knowledge'].get('case_ontology_mode')=='ai': cases=enrich_case_ontology(cases,cfg,out)
    checklists=build_checklists(provisions,cfg,out,mode=checklist_mode)
    issues,issue_edges=build_issue_assignments(provisions,cases,cfg,out)
    relation_candidates=build_relation_edges(registry,provisions,cases,out,extracted,cfg)
    relations=[r for r in relation_candidates if r.get('evidence_status')=='RESOLVED']
    write_jsonl(out/'04_knowledge/accepted_relation_edges.jsonl',relations)
    write_jsonl(out/'04_knowledge/relation_review_queue.jsonl',
                [r for r in relation_candidates if r.get('evidence_status')!='RESOLVED'])
    catalog=load_stage(out,'00_manifest/source_catalog_resolved.jsonl')
    units=build_retrieval_units(provisions,cases,registry,segments,catalog,extracted)
    write_jsonl(out/'06_indexes/retrieval_units.jsonl',units)
    communities={'community_nodes':[],'edges':[],'algorithm':'not_built'}
    nodes,edges=build_graph(registry,provisions,cases,issues,issue_edges,checklists,relations,communities,out,identities)
    # Persist a truthful report before any model/index step can fail.
    validate(registry,extracted,provisions,cases,checklists,nodes,edges,out,cfg)
    failures=[]
    if build_indexes:
        for name,operation in [('BM25',lambda:build_bm25_index(units,cfg,out)),('DENSE',lambda:dense_worker(cfg))]:
            try: operation()
            except Exception as exc: failures.append({'severity':'ERROR','type':name+'_BUILD_FAILED','message':str(exc)})
        try:
            communities=build_case_communities(cases,saved_embeddings(out,units),cfg)
            nodes,edges=build_graph(registry,provisions,cases,issues,issue_edges,checklists,relations,communities,out,identities)
        except Exception as exc:
            failures.append({'severity':'WARN','type':'COMMUNITY_BUILD_SKIPPED','message':str(exc)})
    (out/'04_knowledge/communities.json').write_text(json.dumps(communities,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    write_jsonl(out/'reports/build_issues.jsonl',failures)
    return validate(registry,extracted,provisions,cases,checklists,nodes,edges,out,cfg)

def run_all(cfg,checklist_mode=None):
    manifest=scan(cfg['data_dir'],cfg['output_dir'])
    resolve_source_catalog(manifest,cfg['project_root'],cfg['output_dir'])
    extracted=extract_all(manifest,cfg,cfg['output_dir'])
    return construct_from_extracted(cfg,extracted,checklist_mode)

def rerun_enrichment(cfg,mode='ollama'):
    out=cfg['output_dir']
    (out/'reports/neo4j_validation.json').unlink(missing_ok=True)
    provisions=load_stage(out,'03_structure/provisions.jsonl'); cases=load_stage(out,'03_structure/cases.jsonl'); registry=load_stage(out,'02_registry/documents.jsonl')
    extracted=load_stage(out,'01_extracted/documents.jsonl')
    provisions=enrich_provenance(provisions,extracted,registry,out)
    segments=load_stage(out,'03_structure/segments.jsonl')
    build_hierarchy_headings(registry,extracted,segments,out)
    identities, _=materialize_provision_versions(registry,provisions,out,cfg['project_root'])
    if mode in {'ai','hybrid_ai'}: cases=enrich_case_ontology(cases,cfg,out)
    checklists=build_checklists(provisions,cfg,out,mode=mode)
    issues,issue_edges=build_issue_assignments(provisions,cases,cfg,out)
    relation_candidates=build_relation_edges(registry,provisions,cases,out,extracted,cfg)
    relations=[r for r in relation_candidates if r.get('evidence_status')=='RESOLVED']
    write_jsonl(out/'04_knowledge/accepted_relation_edges.jsonl',relations)
    write_jsonl(out/'04_knowledge/relation_review_queue.jsonl',
                [r for r in relation_candidates if r.get('evidence_status')!='RESOLVED'])
    catalog=load_stage(out,'00_manifest/source_catalog_resolved.jsonl')
    units=build_retrieval_units(provisions,cases,registry,segments,catalog,extracted)
    embeddings=saved_embeddings(out,units)
    communities=build_case_communities(cases,embeddings,cfg)
    nodes,edges=build_graph(registry,provisions,cases,issues,issue_edges,checklists,relations,communities,out,identities)
    (out/'04_knowledge/communities.json').write_text(json.dumps(communities,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    return validate(registry,extracted,provisions,cases,checklists,nodes,edges,out,cfg)
