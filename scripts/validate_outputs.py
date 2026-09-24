"""Audit actual offline artifacts; exit nonzero unless all four outputs pass.

Run with .venv/Scripts/python.exe scripts/validate_outputs.py [--neo4j].
The optional flag verifies live database IDs as well as local exports.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"


def audit(check_neo4j=False, output_dir=None, config_path=None):
    from vn_labor_offline.config import load_yaml, resolve_paths
    from vn_labor_offline.graph_builder import graph_parent_id
    from vn_labor_offline.quality import quality_issues
    from vn_labor_offline.evaluation import reviewed_quality_gate
    from vn_labor_offline.gold import evaluate_gold
    from vn_labor_offline.gold_evaluator import evaluation_fingerprint
    from vn_labor_offline.scanner import source_catalog_gate
    from vn_labor_offline.readiness import semantic_readiness_gate
    config_path = config_path or ROOT / 'config/pipeline.yaml'
    cfg = resolve_paths(load_yaml(config_path), config_path)
    OUT = Path(output_dir).resolve() if output_dir else cfg['output_dir']
    checks = []

    def check(stage, name, ok, detail=""):
        checks.append(dict(stage=stage, check=name, passed=bool(ok), detail=detail))

    def rows(path, stage, allow_empty=False):
        try:
            result = [json.loads(line) for line in (OUT / path).read_text(encoding="utf-8").splitlines() if line.strip()]
            check(stage, path, allow_empty or bool(result), f"{len(result)} rows")
            return result
        except Exception as exc:
            check(stage, path, False, str(exc))
            return []

    def unique(items, key, stage):
        counts = Counter(item.get(key) for item in items)
        bad = [value for value, count in counts.items() if not value or count > 1]
        check(stage, f"unique {key}", bool(items) and not bad, f"{len(bad)} missing/duplicate IDs; examples: {bad[:5]}")

    manifest = rows("00_manifest/files.jsonl", "registry")
    registry = rows("02_registry/documents.jsonl", "registry")
    unique(registry, "document_id", "registry")
    check("registry", "manifest coverage", bool(manifest) and Counter(x.get("file_id") for x in manifest) == Counter(x.get("file_id") for x in registry))
    metadata_gaps = [{"document_id": d.get("document_id"), "path": d.get("relative_path"), "field": field}
                     for d in registry for field in ("document_type", "source_group")
                     if d.get(field) in (None, "", "UNKNOWN")]
    metadata_gaps += [{"document_id": d.get("document_id"), "path": d.get("relative_path"), "field": field}
                      for d in registry if d.get("source_group") == "LEGAL_DOCUMENT"
                      for field in ("document_number", "effective_from", "status")
                      if d.get(field) in (None, "", "UNKNOWN")]
    check("registry", "legal metadata completeness", not metadata_gaps, f"{len(metadata_gaps)} unresolved fields")
    extracted = rows("01_extracted/documents.jsonl", "registry")
    check("registry", "machine text coverage", bool(extracted) and all(d.get("text_chars", 0) >= 100 for d in extracted))
    provisions = rows("03_structure/provisions.jsonl", "structure")
    unique(provisions, "provision_id", "structure")
    docs = {d.get("document_id"): d for d in registry}
    provs = {p.get("provision_id"): p for p in provisions}
    invalid_parents = []
    for p in provisions:
        parent = p.get("parent_id")
        level = p.get("level")
        valid = p.get("document_id") in docs
        if level == "ARTICLE":
            valid &= parent == p.get("document_id")
        else:
            expected = {"CLAUSE": "ARTICLE", "POINT": "CLAUSE"}.get(level)
            valid &= expected is not None and parent in provs and provs[parent].get("level") == expected and provs[parent].get("document_id") == p.get("document_id")
        if not valid:
            invalid_parents.append(p.get("provision_id"))
    check("structure", "Document/Article/Clause/Point parents", not invalid_parents, f"{len(invalid_parents)} invalid parents")
    expected_docs = {d.get("document_id") for d in registry if d.get("document_type") in {"LAW", "DECREE", "CIRCULAR", "RESOLUTION", "CONSOLIDATED", "HISTORICAL"}}
    parsed_docs = {p.get("document_id") for p in provisions if p.get("level") == "ARTICLE"}
    check("structure", "legal document article coverage", bool(expected_docs) and expected_docs <= parsed_docs, f"{len(expected_docs - parsed_docs)} documents without articles")
    nodes = rows("05_graph/nodes.jsonl", "graph")
    edges = rows("05_graph/edges.jsonl", "graph")
    unique(nodes, "id", "graph")
    unique(edges, "id", "graph")
    node_ids = {n.get("id") for n in nodes}
    check("graph", "all documents and provisions exported", bool(node_ids) and set(docs) | set(provs) <= node_ids)
    check("graph", "edge endpoints", bool(edges) and all(e.get("source") in node_ids and e.get("target") in node_ids for e in edges))
    hierarchy = {(e.get("source"), e.get("target")) for e in edges if e.get("type") == "PART_OF"}
    check("graph", "all hierarchy edges exported", bool(provisions) and all((p.get("provision_id"), graph_parent_id(p)) in hierarchy for p in provisions))
    versioned = {e.get("source") for e in edges if e.get("type") == "VERSION_OF"}
    required_versions = {d.get("document_id") for d in registry if d.get("source_group") == "LEGAL_DOCUMENT" or d.get("document_type") == "CONSOLIDATED"}
    check("graph", "version anchors", bool(required_versions) and required_versions <= versioned)
    units = rows("06_indexes/retrieval_units.jsonl", "indexes")
    unique(units, "unit_id", "indexes")
    check("indexes", "retrieval units resolve to graph", bool(units) and all(u.get("unit_id") in node_ids for u in units))
    try:
        import numpy as np
        import faiss
        dense = OUT / "06_indexes/dense"
        index = faiss.deserialize_index(np.frombuffer((dense / "faiss.index").read_bytes(), dtype="uint8").copy())
        vectors = np.load(dense / "vectors.npy", allow_pickle=False)
        metas = rows("06_indexes/dense/metadata.jsonl", "indexes")
        check("indexes", "dense counts/dimensions", index.ntotal == len(units) == len(metas) == len(vectors) and vectors.shape[1] == index.d)
        check("indexes", "dense ID order", [u.get("unit_id") for u in units] == [m.get("unit_id") for m in metas])
        check("indexes", "dense finite normalized vectors", np.isfinite(vectors).all() and np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-3))
        scores, ids = index.search(vectors[:1], min(3, index.ntotal))
        check("indexes", "dense query", ids.size > 0 and (ids >= 0).all() and np.isfinite(scores).all())
    except Exception as exc:
        check("indexes", "dense load/query", False, str(exc))
    try:
        import bm25s
        bm25 = bm25s.BM25.load(str(OUT / "06_indexes/bm25"), load_corpus=True)
        corpus = bm25.corpus
        check("indexes", "BM25 ID order", [c["id"] for c in corpus] == [u.get("unit_id") for u in units] and bool(units))
        query = bm25s.tokenize([units[0]["text"].lower()], stopwords=None, stemmer=None)
        result, scores = bm25.retrieve(query, k=min(3, len(units)))
        check("indexes", "BM25 query", result.size > 0)
    except Exception as exc:
        check("indexes", "BM25 load/query", False, str(exc))
    validation = rows("reports/validation_issues.jsonl", "graph", allow_empty=True)
    check("graph", "pipeline validation has no ERROR", not any(i.get("severity") == "ERROR" for i in validation))
    semantic = quality_issues(registry, extracted, provisions, nodes, edges, OUT, cfg)
    semantic_counts = dict(Counter(i['type'] for i in semantic if i.get('severity') == 'ERROR'))
    check('graph', 'current semantic validation', not semantic_counts, json.dumps(semantic_counts))
    if check_neo4j:
        try:
            import os
            from dotenv import load_dotenv
            from neo4j import GraphDatabase
            load_dotenv(ROOT / ".env")
            with GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://localhost:7687"), auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "change_me")), connection_timeout=10) as driver:
                db = os.getenv("NEO4J_DATABASE", "neo4j")
                records, _, _ = driver.execute_query("MATCH (n:Entity) RETURN n.id AS id", database_=db)
                actual = {r["id"] for r in records}
                check("indexes", "Neo4j node coverage", bool(node_ids) and node_ids == actual and len(records)==len(node_ids))
                records, _, _ = driver.execute_query("MATCH (:Entity)-[r]->(:Entity) RETURN r.id AS id", database_=db)
                check("indexes", "Neo4j edge coverage", bool(edges) and {e["id"] for e in edges} == {r["id"] for r in records} and len(records)==len(edges))
        except Exception as exc:
            check("indexes", "Neo4j live verification", False, str(exc))
    else:
        check("indexes", "Neo4j live verification", False, "Not requested; rerun with --neo4j to verify Graph DB.")
    stages = {stage: all(c["passed"] for c in checks if c["stage"] == stage) for stage in ("registry", "structure", "graph", "indexes")}
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(), ready_for_offline_v1=all(stages.values()), stages=stages, checks=checks, metadata_gaps=metadata_gaps)
    report['legal_quality_evaluation'] = reviewed_quality_gate(OUT, nodes, edges)
    catalog = rows('00_manifest/source_catalog_resolved.jsonl', 'registry')
    report['source_catalog_quality'] = source_catalog_gate(catalog, registry)
    report['semantic_quality'] = semantic_readiness_gate(OUT, registry)
    # Reviewer-authored Gold/qrels must pin this graph + retrieval + index build.
    report['gold_build_id'] = evaluation_fingerprint(OUT) if all(
        c['passed'] for c in checks if c['stage'] in {'graph', 'indexes'} and
        c['check'] != 'Neo4j live verification') else None
    report['gold_evaluation'] = evaluate_gold(OUT)
    report['offline_ready_for_online'] = (report['ready_for_offline_v1'] and
        report['source_catalog_quality']['passed'] and report['semantic_quality']['passed'] and
        report['legal_quality_evaluation']['passed'] and report['gold_evaluation']['passed'])
    report_dir = OUT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "final_outputs_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Four-output validation", "", f"Ready for offline v1: **{report['ready_for_offline_v1']}**", ""]
    lines += [f"- {stage}: {'PASS' if passed else 'FAIL'}" for stage, passed in stages.items()]
    lines += ["", "Failed checks:", ""]
    lines += [f"- {c['stage']} / {c['check']}: {c['detail']}" for c in checks if not c["passed"]]
    (report_dir / "final_outputs_validation.md").write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neo4j", action="store_true")
    parser.add_argument('--output', type=Path, help='Audit an isolated artifact directory')
    parser.add_argument('--config', type=Path, default=ROOT / 'config/pipeline.yaml')
    args = parser.parse_args()
    result = audit(args.neo4j, args.output, args.config)
    print(json.dumps({"ready_for_offline_v1": result["ready_for_offline_v1"], "stages": result["stages"]}, indent=2))
    sys.exit(0 if result["ready_for_offline_v1"] else 1)
