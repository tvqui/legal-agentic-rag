"""Query BM25 and FAISS against reviewed relevance labels for the current build."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from .util import read_jsonl


def graph_fingerprint(output_dir: Path) -> str | None:
    paths = [output_dir / "05_graph" / name for name in ("nodes.jsonl", "edges.jsonl")]
    if not all(path.exists() for path in paths):
        return None
    rows = [list(read_jsonl(path)) for path in paths]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def evaluation_fingerprint(output_dir: Path) -> str | None:
    graph=graph_fingerprint(output_dir)
    units_path=output_dir/'06_indexes/retrieval_units.jsonl'
    dense_path=output_dir/'reports/dense_validation.json'
    bm25_path=output_dir/'06_indexes/bm25/corpus.jsonl'
    if not graph or not all(p.exists() for p in (units_path,dense_path,bm25_path)):
        return None
    dense=json.loads(dense_path.read_text(encoding='utf-8'))
    if not dense.get('dense_passed') or not dense.get('fingerprint'):
        return None
    data={'graph':graph,'units':list(read_jsonl(units_path)),
          'dense_fingerprint':dense['fingerprint'],'bm25':list(read_jsonl(bm25_path))}
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def approved_thresholds(output_dir: Path, build_id: str) -> tuple[dict | None, str]:
    path = output_dir / "07_evaluation" / "quality_thresholds.json"
    if not path.exists():
        return None, "Approved quality_thresholds.json required"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        if cfg.get("review_status") != "APPROVED" or not cfg.get("reviewer") or cfg.get("build_id") != build_id:
            return None, "Threshold approval/build mismatch"
        date.fromisoformat(str(cfg["reviewed_at"]))
        k, minimum = cfg.get("k"), cfg.get("minimum_union_recall_at_k")
        if not isinstance(k, int) or k < 1 or not isinstance(minimum, (int, float)) or not 0 <= minimum <= 1:
            return None, "Invalid k or recall threshold"
        if not isinstance(cfg.get("minimum_approved_queries"), int) or cfg["minimum_approved_queries"] < 1:
            return None, "Invalid minimum approved query count"
        if not isinstance(cfg.get("minimum_retrieval_queries"), int) or cfg["minimum_retrieval_queries"] < 1:
            return None, "Invalid minimum retrieval query count"
        if not isinstance(cfg.get("required_query_types"), list) or not cfg["required_query_types"]:
            return None, "Required query type coverage missing"
        return cfg, ""
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return None, str(exc)


def query_indexes(output_dir: Path, queries: list[dict], k: int, units: list[dict]) -> list[dict]:
    import bm25s
    import faiss
    import numpy as np
    import torch
    from FlagEmbedding import BGEM3FlagModel
    from .temporal import temporal_eligible

    dense = output_dir / "06_indexes" / "dense"
    indexed_units = list(read_jsonl(dense / "metadata.jsonl"))
    bm25_rows = list(read_jsonl(output_dir / "06_indexes" / "bm25" / "corpus.jsonl"))
    if indexed_units != units or [r.get("id") for r in bm25_rows] != [u.get("unit_id") for u in units]:
        raise ValueError("STALE_INDEX_UNITS")
    index = faiss.deserialize_index(np.frombuffer((dense / "faiss.index").read_bytes(), dtype="uint8").copy())
    if index.ntotal != len(units):
        raise ValueError("STALE_DENSE_INDEX_COUNT")
    report_path = output_dir / "reports" / "dense_validation.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    model_path = report.get("model_path")
    model_name = model_path if model_path and Path(model_path).exists() else report.get("model", "BAAI/bge-m3")
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    model = BGEM3FlagModel(model_name, use_fp16=device != "cpu", devices=device)
    retriever = bm25s.BM25.load(str(output_dir / "06_indexes" / "bm25"), load_corpus=True)
    vectors = np.asarray(model.encode([r['question'] for r in queries], batch_size=int(report.get("batch_size") or 4),
                                      max_length=int(report.get("max_length") or 1024),
                                      return_dense=True, return_sparse=False,
                                      return_colbert_vecs=False)["dense_vecs"], dtype="float32")
    faiss.normalize_L2(vectors)
    candidate_k=min(max(k*20,100),len(units))
    _, positions = index.search(vectors, candidate_k)
    by_id={u['unit_id']:u for u in units}
    results = []
    for i, query in enumerate(queries):
        tokens = bm25s.tokenize([query['question'].lower()], stopwords=None, stemmer=None)
        lexical, _ = retriever.retrieve(tokens, k=candidate_k)
        dense_ids = [units[int(pos)]["unit_id"] for pos in positions[i] if pos >= 0]
        lexical_ids = [row["id"] for row in lexical[0]]
        if query.get('query_date'):
            eligible=lambda uid:temporal_eligible(by_id[uid],query['query_date'])
            dense_ids=[uid for uid in dense_ids if eligible(uid)]
            lexical_ids=[uid for uid in lexical_ids if eligible(uid)]
        dense_ids=dense_ids[:k]
        lexical_ids=lexical_ids[:k]
        results.append({"dense": dense_ids, "bm25": lexical_ids,
                        "union": list(dict.fromkeys(dense_ids + lexical_ids))})
    return results


def evaluate_approved_gold(output_dir: Path, approved: list[dict]) -> dict:
    build_id = evaluation_fingerprint(output_dir)
    if not build_id or any(r.get("build_id") != build_id for r in approved):
        return {"status": "STALE_GOLD_BUILD", "passed": False,
                "reason": "Gold approval must refer to the current graph build"}
    thresholds, problem = approved_thresholds(output_dir, build_id)
    if problem:
        return {"status": "NOT_EVALUATED", "passed": False, "reason": problem}
    types = {r["query_type"] for r in approved}
    missing_types = sorted(set(thresholds["required_query_types"]) - types)
    if len(approved) < thresholds["minimum_approved_queries"] or missing_types:
        return {"status": "INSUFFICIENT_GOLD_COVERAGE", "passed": False,
                "approved_queries": len(approved), "missing_query_types": missing_types,
                "required_queries": thresholds["minimum_approved_queries"]}
    units = list(read_jsonl(output_dir / "06_indexes" / "retrieval_units.jsonl"))
    unit_ids = {u.get("unit_id") for u in units}
    evaluated = [r for r in approved if r["query_type"] != "INSUFFICIENT_FACTS"]
    if len(evaluated)<thresholds['minimum_retrieval_queries']:
        return {"status":"INSUFFICIENT_RETRIEVAL_GOLD","passed":False,
                "retrieval_queries":len(evaluated),"required":thresholds['minimum_retrieval_queries']}
    missing = sorted({uid for r in evaluated for uid in r["gold_unit_ids"] if uid not in unit_ids})
    if not evaluated or missing:
        return {"status": "INVALID_GOLD_QRELS", "passed": False,
                "missing_unit_ids": missing, "reason": "Gold qrels must resolve to current retrieval units"}
    if any(r.get('query_date') for r in evaluated):
        from .temporal import temporal_eligible
        by_id={u['unit_id']:u for u in units}
        invalid_temporal_qrels=sorted({uid for r in evaluated if r.get('query_date') for uid in
            r['gold_unit_ids'] if not temporal_eligible(by_id[uid],r['query_date'])})
        if invalid_temporal_qrels:
            return {"status":"INVALID_TEMPORAL_QRELS","passed":False,
                    "invalid_unit_ids":invalid_temporal_qrels}
    try:
        retrieved = query_indexes(output_dir, evaluated, thresholds["k"], units)
    except Exception as exc:
        return {"status": "EVALUATION_FAILED", "passed": False, "reason": str(exc)}
    details = []
    for record, result in zip(evaluated, retrieved):
        gold = set(record["gold_unit_ids"])
        details.append({"query_id": record["query_id"], "query_type": record["query_type"],
                        "recall_at_k": len(gold.intersection(result["union"])) / len(gold),
                        "gold_unit_ids": sorted(gold), "dense_ids": result["dense"],
                        "bm25_ids": result["bm25"], "union_ids": result["union"]})
    mean_recall = sum(row["recall_at_k"] for row in details) / len(details)
    return {"status": "EVALUATED", "passed": mean_recall >= thresholds["minimum_union_recall_at_k"],
            "build_id": build_id, "approved_queries": len(approved), "evaluated_queries": len(details),
            "k": thresholds["k"], "minimum_union_recall_at_k": thresholds["minimum_union_recall_at_k"],
            "mean_union_recall_at_k": mean_recall, "queries": details,
            "note": "Offline retrieval relevance only; separately reviewed legal/citation quality remains required."}
