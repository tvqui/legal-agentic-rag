from __future__ import annotations
import json, csv, re, unicodedata
from pathlib import Path
from .util import stable_id, write_jsonl, read_jsonl
from .temporal import instrument_key, instrument_id


def node(nid: str, label: str, **props):
    return {"id": nid, "label": label, "properties": props}


def edge(s: str, t: str, typ: str, **props):
    return {"id": stable_id(s,t,typ,json.dumps(props,sort_keys=True,ensure_ascii=False),prefix="edge"), "source":s,"target":t,"type":typ,"properties":props}


def abstract_law_key(d: dict) -> str:
    return instrument_key(d)


def hierarchy_ids(p: dict) -> tuple[str | None, str | None]:
    """Return stable Chapter/Section IDs for an Article provision."""
    document_id=p["document_id"]
    chapter=p.get("chapter") or ""
    section=p.get("section") or ""
    chapter_id=stable_id(document_id,"chapter",chapter,prefix="hier") if chapter else None
    section_id=stable_id(document_id,"section",chapter,section,prefix="hier") if section else None
    return chapter_id,section_id


def graph_parent_id(p: dict) -> str:
    """Return the parent represented by PART_OF in the exported graph."""
    if p.get("level") != "ARTICLE":
        return p["parent_id"]
    chapter_id,section_id=hierarchy_ids(p)
    return section_id or chapter_id or p["document_id"]


def build_graph(registry, provisions, cases, issues, issue_edges, checklists, relation_edges, communities, output_dir: Path, provision_identities=None):
    nodes=[]; edges=[]
    hierarchy_headings={r['id']:r for r in read_jsonl(output_dir/'03_structure/hierarchy_headings.jsonl')}
    def heading_properties(nid):
        return {k:v for k,v in hierarchy_headings.get(nid,{}).items() if k not in {'id','label','number','document_id'}}
    # Documents + AbstractLaw/Version layer. Legal documents are version/provenance-bearing
    # source nodes; AbstractLaw provides a stable timeless anchor for temporal retrieval.
    abstract_seen = {}
    for d in registry:
        label = "DocumentVersion"
        if d["document_type"] == "CONSOLIDATED": label="ConsolidatedDocumentVersion"
        elif d["source_group"] == "JUDICIAL": label="SourceDocument"
        elif d["source_group"] == "SUPPLEMENTARY": label="SupplementaryDocument"
        props = dict(d); props["layer"] = "document"
        nodes.append(node(d["document_id"], label, **props))
        if d.get('instrument_number') and (d["source_group"] == "LEGAL_DOCUMENT" or d["document_type"] == "CONSOLIDATED"):
            key = abstract_law_key(d)
            aid = instrument_id(d)
            if aid not in abstract_seen:
                abstract_seen[aid] = True
                nodes.append(node(aid, "LegalInstrument", canonical_key=key, instrument_number=d['instrument_number'], layer="rule"))
            edges.append(edge(d["document_id"], aid, "VERSION_OF"))
        if d.get('policy_series'):
            sid=stable_id(d['policy_series'],prefix='policy')
            if sid not in abstract_seen:
                nodes.append(node(sid,'PolicySeries',name=d['policy_series'],layer='ontology')); abstract_seen[sid]=True
            edges.append(edge(d['document_id'],sid,'BELONGS_TO_POLICY_SERIES'))
    for s in read_jsonl(output_dir/'03_structure'/'segments.jsonl'):
        if s['segment_type'] in {'ANNEX','FORM','ATTACHED_REGULATION'}:
            nodes.append(node(s['segment_id'],{'FORM':'Form','ANNEX':'Annex','ATTACHED_REGULATION':'AttachedRegulation'}[s['segment_type']],layer='document',**s))
            edges.append(edge(s['segment_id'],s['document_id'],'PART_OF'))
    # Natural legal hierarchy. Chapter/Section nodes are materialized once in
    # first-appearance order, then Articles point at their structural parent.
    hierarchy_seen=set(); hierarchy_siblings={}
    for p in provisions:
        if p["level"] != "ARTICLE":
            continue
        chapter_id,section_id=hierarchy_ids(p)
        if chapter_id and chapter_id not in hierarchy_seen:
            nodes.append(node(chapter_id,"Chapter",number=p["chapter"],document_id=p["document_id"],
                              layer="rule",**heading_properties(chapter_id)))
            edges.append(edge(chapter_id,p["document_id"],"PART_OF"))
            hierarchy_siblings.setdefault(p["document_id"],[]).append(chapter_id)
            hierarchy_seen.add(chapter_id)
        if section_id and section_id not in hierarchy_seen:
            parent_id=chapter_id or p["document_id"]
            nodes.append(node(section_id,"Section",number=p["section"],chapter=p.get("chapter","") or "",
                              document_id=p["document_id"],layer="rule",**heading_properties(section_id)))
            edges.append(edge(section_id,parent_id,"PART_OF"))
            hierarchy_siblings.setdefault(parent_id,[]).append(section_id)
            hierarchy_seen.add(section_id)
    for siblings_at_level in hierarchy_siblings.values():
        for a,b in zip(siblings_at_level,siblings_at_level[1:]):
            edges.append(edge(a,b,"NEXT"))

    for p in provisions:
        label={"ARTICLE":"Article","CLAUSE":"Clause","POINT":"Point"}.get(p["level"],"Provision")
        pp = dict(p); pp["layer"] = "rule"
        nodes.append(node(p["provision_id"], label, **pp))
        edges.append(edge(p["provision_id"],graph_parent_id(p),"PART_OF"))
        if p.get("provision_identity_id"):
            edges.append(edge(p["provision_identity_id"],p["provision_id"],"HAS_PROVISION_VERSION"))
    for identity in provision_identities or []:
        nodes.append(node(identity["provision_identity_id"],"ProvisionIdentity",layer="rule",**identity))
    # NEXT at each parent level.
    siblings={}
    for p in provisions: siblings.setdefault(graph_parent_id(p),[]).append(p)
    for parent, arr in siblings.items():
        arr=sorted(arr,key=lambda x:x.get("order",0))
        for a,b in zip(arr,arr[1:]): edges.append(edge(a["provision_id"], b["provision_id"], "NEXT"))
    # Cases
    for c in cases:
        cc = dict(c); cc["layer"] = "fact"
        nodes.append(node(c["case_id"], {"JUDGMENT":"Judgment","CASSATION":"CassationDecision","PRECEDENT":"Precedent"}.get(c["case_type"],"Case"), **cc))
        edges.append(edge(c["case_id"], c["document_id"], "DERIVED_FROM"))
        for i,f in enumerate(c.get("features",[]),1):
            fid=stable_id(c["case_id"],str(i),f.get("type",""),f.get("value",""),prefix="feat")
            nodes.append(node(fid,"CaseFeature",layer="ontology",**f))
            edges.append(edge(c["case_id"],fid,"HAS_FEATURE"))
    # Issues
    for i in issues: nodes.append(node(i["issue_id"],"LegalIssue",layer="ontology",**i))
    for e in issue_edges: edges.append(edge(e["source_id"],e["target_id"],e["type"],score=e.get("score"),evidence=e.get("evidence"),
                                             evidence_text=e.get("evidence_text"),evidence_span=e.get("evidence_span"),
                                             provenance_status=e.get("provenance_status")))
    # Diagnostic checklist -> Rule Graph support
    for d in checklists:
        nodes.append(node(d["checklist_id"],"DiagnosticItem",layer="derived",**d))
        edges.append(edge(d["provision_id"],d["checklist_id"],"HAS_DIAGNOSTIC_ITEM",confidence=d.get("confidence"),
                          evidence_text=d.get("evidence_text"),evidence_span=d.get("evidence_span"),
                          provenance_status=d.get("provenance_status")))
    # Legal/citation relations
    for e in relation_edges: edges.append(edge(e["source_id"],e["target_id"],e["type"],confidence=e.get("confidence"),
                                               evidence=e.get("evidence"),evidence_text=e.get("evidence_text"),
                                               evidence_span=e.get("evidence_span"),evidence_status=e.get("evidence_status"),
                                               resolution_scope=e.get("resolution_scope"),method=e.get("method")))
    # Communities / similar cases
    for c in communities.get("community_nodes",[]): nodes.append(node(c["id"],"Community",layer="ontology",**c))
    for e in communities.get("edges",[]): edges.append(edge(e["source"],e["target"],e["type"],**e.get("properties",{})))

    if len({n['id'] for n in nodes})!=len(nodes):
        raise ValueError('Duplicate graph node IDs; refusing to overwrite legal content.')
    # Keep dangling edges visible to validation instead of silently deleting them.
    edges=list({e['id']:e for e in edges}.values())
    gdir=output_dir/"05_graph"; gdir.mkdir(parents=True,exist_ok=True)
    write_jsonl(gdir/"nodes.jsonl",nodes); write_jsonl(gdir/"edges.jsonl",edges)
    # CSV exports with JSON properties are convenient for inspection and import.
    with (gdir/"nodes.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["id","label","properties_json"]); w.writeheader()
        for n in nodes: w.writerow({"id":n["id"],"label":n["label"],"properties_json":json.dumps(n["properties"],ensure_ascii=False)})
    with (gdir/"edges.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["id","source","target","type","properties_json"]); w.writeheader()
        for e in edges: w.writerow({"id":e["id"],"source":e["source"],"target":e["target"],"type":e["type"],"properties_json":json.dumps(e["properties"],ensure_ascii=False)})
    return nodes,edges
