from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter
from datetime import date
from pathlib import Path

from vn_labor_online.config import load_config
from vn_labor_online.models import QueryRequest, Stop
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_offline.gold import validate_gold_record


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def version_is_wrong(unit: dict, query_date: str | None) -> bool:
    if not query_date:
        return False
    try:
        when = date.fromisoformat(query_date)
        start = date.fromisoformat(unit["valid_from"]) if unit.get("valid_from") else None
        end = date.fromisoformat(unit["valid_to"]) if unit.get("valid_to") else None
    except (KeyError, TypeError, ValueError):
        return True
    return not start or when < start or bool(end and when >= end)


def evaluate_variant(pipe: OnlinePipeline, gold: list[dict]) -> dict:
    recalls: list[float] = []
    precisions: list[float] = []
    latencies: list[float] = []
    nodes: list[float] = []
    edges: list[float] = []
    rounds: list[float] = []
    evidence_chars: list[float] = []
    wrong_versions = 0
    dated_citations = 0
    fabricated = 0
    reference_pass = 0
    evaluated = 0
    no_answer_total = 0
    no_answer_correct = 0
    status_counts: Counter[str] = Counter()
    stop_reasons: Counter[str] = Counter()
    critical_edges: Counter[str] = Counter()

    for row in gold:
        started = time.perf_counter()
        answer = pipe.ask(
            QueryRequest(
                question=row["question"],
                query_date=row.get("query_date"),
                facts=row.get("facts") or {},
                conversation_context=row.get("conversation_context") or [],
            )
        )
        latencies.append((time.perf_counter() - started) * 1000)
        status_counts[str(answer.status.value)] += 1
        stop_reasons[str(answer.trace.stop_reason or answer.status.value)] += 1
        nodes.append(answer.trace.nodes_visited)
        edges.append(answer.trace.edges_visited)
        rounds.append(answer.trace.retrieval_rounds)
        critical_edges.update(answer.trace.critical_edges_followed)
        reference_pass += int(answer.trace.reference_audit == "PASS")
        pack_event = next((event for event in reversed(answer.trace.events) if event.get("event") == "verified_evidence_pack"), None)
        if pack_event is not None:
            evidence_chars.append(float(pack_event.get("characters") or 0))

        expected_no_answer = bool(row.get("expected_no_answer")) or row.get("query_type") == "INSUFFICIENT_FACTS"
        if expected_no_answer:
            no_answer_total += 1
            no_answer_correct += int(
                answer.status in {Stop.NEED_MORE_FACTS, Stop.INSUFFICIENT_EVIDENCE}
            )

        truth = set(row.get("gold_unit_ids") or row.get("candidate_unit_ids") or [])
        if not truth:
            continue
        evaluated += 1
        got = {citation.evidence_id for citation in answer.citations}
        hit = len(got & truth)
        recalls.append(hit / len(truth))
        precisions.append(hit / len(got) if got else 0.0)
        for evidence_id in got:
            unit = pipe.store.units_by_id.get(evidence_id)
            if unit is None:
                fabricated += 1
                continue
            if row.get("query_date"):
                dated_citations += 1
                wrong_versions += int(version_is_wrong(unit, row["query_date"]))

    return {
        "queries": len(gold),
        "queries_with_qrels": evaluated,
        "citation_recall": mean(recalls),
        "citation_precision": mean(precisions),
        "wrong_version_rate": wrong_versions / dated_citations if dated_citations else None,
        "fabricated_citations": fabricated,
        "abstention_accuracy": no_answer_correct / no_answer_total if no_answer_total else None,
        "reference_audit_pass_rate": reference_pass / len(gold) if gold else None,
        "status_counts": dict(status_counts),
        "stop_reason_counts": dict(stop_reasons),
        "critical_edges_followed": dict(critical_edges),
        "average_evidence_characters": mean(evidence_chars),
        "estimated_average_evidence_tokens": mean([value / 4 for value in evidence_chars]),
        "average_latency_ms": mean(latencies),
        "median_latency_ms": statistics.median(latencies) if latencies else None,
        "p95_latency_ms": percentile(latencies, 0.95),
        "average_nodes_visited": mean(nodes),
        "average_edges_visited": mean(edges),
        "average_graph_rounds": mean(rounds),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config/online.yaml"))
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument(
        "--out", type=Path, default=Path("artifacts/online_evaluation/ablation.json")
    )
    args = parser.parse_args()
    gold = load_jsonl(args.gold)
    base = load_config(args.config)
    variants = {
        "flat_bm25": {"dense": False, "issue": False, "case": False, "graph": False, "mode": "adaptive", "hops": 0, "hub": base.graph.hub_penalty},
        "flat_hybrid": {"dense": True, "issue": True, "case": True, "graph": False, "mode": "adaptive", "hops": 0, "hub": base.graph.hub_penalty},
        "fixed_1hop": {"dense": True, "issue": True, "case": True, "graph": True, "mode": "fixed", "hops": 1, "hub": base.graph.hub_penalty},
        "fixed_2hop": {"dense": True, "issue": True, "case": True, "graph": True, "mode": "fixed", "hops": 2, "hub": base.graph.hub_penalty},
        "adaptive": {"dense": True, "issue": True, "case": True, "graph": True, "mode": "adaptive", "hops": base.graph.max_hops, "hub": base.graph.hub_penalty},
        "adaptive_no_hub": {"dense": True, "issue": True, "case": True, "graph": True, "mode": "adaptive", "hops": base.graph.max_hops, "hub": 0.0},
    }
    results = {}
    expected_gold_build_id = None
    for name, options in variants.items():
        config = base.model_copy(deep=True)
        config.retrieval.dense_enabled = options["dense"]
        config.retrieval.issue_anchor_enabled = options["issue"]
        config.retrieval.case_law_enabled = options["case"]
        config.graph.enabled = options["graph"]
        config.graph.mode = options["mode"]
        config.graph.max_hops = options["hops"]
        config.graph.max_rounds = max(config.graph.max_rounds, options["hops"])
        config.graph.hub_penalty = options["hub"]
        pipeline = OnlinePipeline(config)
        expected_gold_build_id = pipeline.store.report.gold_build_id
        results[name] = evaluate_variant(pipeline, gold)

    supplied_build_ids = sorted({str(row.get("build_id")) for row in gold if row.get("build_id")})
    structurally_approved = bool(gold) and all(
        row.get("review_status") == "APPROVED" and not validate_gold_record(row)
        for row in gold
    )
    gold_build_compatible = bool(expected_gold_build_id) and supplied_build_ids == [expected_gold_build_id]
    approved = structurally_approved and gold_build_compatible
    report = {
        "status": "OFFICIAL" if approved else "PROVISIONAL_DRAFT_GOLD",
        "warning": None if approved else "Metrics must not be reported as official until Gold is human-approved and pinned to this evaluation build.",
        "graph_build_id": base.expected_build_id,
        "gold_build_id": expected_gold_build_id,
        "supplied_gold_build_ids": supplied_build_ids,
        "gold_build_compatible": gold_build_compatible,
        "gold_records": len(gold),
        "variants": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
