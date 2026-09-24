"""Evidence-backed final gate for OFFLINE data and knowledge construction."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.source_resolution_coverage import build_report as resolver_coverage
except ModuleNotFoundError:  # direct `python scripts/...` execution
    from source_resolution_coverage import build_report as resolver_coverage


ROOT = Path(__file__).resolve().parents[1]


def _bytes(source: Path | zipfile.ZipFile, name: str) -> bytes | None:
    try:
        return source.read(name) if isinstance(source, zipfile.ZipFile) else (source / name).read_bytes()
    except (OSError, KeyError):
        return None


def _json(source: Path | zipfile.ZipFile, name: str) -> dict[str, Any]:
    raw = _bytes(source, name)
    if raw is None:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _jsonl(source: Path | zipfile.ZipFile, name: str) -> list[dict[str, Any]]:
    raw = _bytes(source, name)
    if raw is None:
        return []
    rows = []
    try:
        for line in raw.decode("utf-8-sig").splitlines():
            if line.strip():
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    return rows


def _exists(source: Path | zipfile.ZipFile, name: str) -> bool:
    return _bytes(source, name) is not None


def _gate(name: str, passed: bool, observed: Any, expected: Any,
          evidence_paths: list[str], reason_codes: list[str] | None = None,
          status: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "status": status or ("PASS" if passed else "FAIL"),
        "observed": observed,
        "expected": expected,
        "evidence_paths": sorted(evidence_paths),
        "reason_codes": sorted(set(reason_codes or ([] if passed else [name.upper() + "_FAILED"]))),
    }


def _graph_fingerprint(nodes: list[dict], edges: list[dict]) -> str | None:
    if not nodes or not edges:
        return None
    payload = json.dumps([nodes, edges], sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _technical_gates(source: Path | zipfile.ZipFile, archive: bool) -> tuple[list[dict], dict]:
    prefix = "artifacts/" if archive else ""
    final_name = prefix + "reports/final_outputs_validation.json"
    neo_name = prefix + "reports/neo4j_validation.json"
    dense_name = prefix + "reports/dense_validation.json"
    final = _json(source, final_name)
    neo = _json(source, neo_name)
    dense = _json(source, dense_name)
    stages = final.get("stages", {})
    gates = []
    for name in ("registry", "structure", "graph"):
        ok = stages.get(name) is True
        gates.append(_gate(f"technical_{name}", ok, stages.get(name), True, [final_name]))

    nodes_name = prefix + "05_graph/nodes.jsonl"
    edges_name = prefix + "05_graph/edges.jsonl"
    units_name = prefix + "06_indexes/retrieval_units.jsonl"
    dense_meta_name = prefix + "06_indexes/dense/metadata.jsonl"
    bm25_corpus_name = prefix + "06_indexes/bm25/corpus.jsonl"
    nodes = _jsonl(source, nodes_name)
    edges = _jsonl(source, edges_name)
    units = _jsonl(source, units_name)
    dense_meta = _jsonl(source, dense_meta_name)
    bm25_rows = _jsonl(source, bm25_corpus_name)
    unit_ids = [row.get("unit_id") for row in units]
    dense_ids = [row.get("unit_id") for row in dense_meta]
    bm25_ids = [row.get("id") for row in bm25_rows]

    dense_files = [prefix + "06_indexes/dense/faiss.index", dense_meta_name, dense_name]
    dense_ok = (
        bool(units) and unit_ids == dense_ids
        and all(_exists(source, name) for name in dense_files)
        and dense.get("dense_passed") is True
        and dense.get("units") == len(units)
        and dense.get("duplicate_unit_id_rows", 0) == 0
        and all(dense.get("checks", {}).values())
        and bool(dense.get("fingerprint"))
    )
    gates.append(_gate(
        "technical_dense", dense_ok,
        {"units": len(units), "metadata": len(dense_meta), "report_units": dense.get("units"),
         "ids_equal": unit_ids == dense_ids, "report_passed": dense.get("dense_passed")},
        {"nonzero_equal_counts": True, "ids_equal": True, "report_passed": True}, dense_files,
    ))

    bm25_files = [
        bm25_corpus_name, prefix + "06_indexes/bm25/params.index.json",
        prefix + "06_indexes/bm25/data.csc.index.npy",
        prefix + "06_indexes/bm25/indices.csc.index.npy",
        prefix + "06_indexes/bm25/indptr.csc.index.npy",
    ]
    bm25_ok = bool(units) and unit_ids == bm25_ids and all(_exists(source, name) for name in bm25_files)
    gates.append(_gate(
        "technical_bm25", bm25_ok,
        {"units": len(units), "corpus": len(bm25_rows), "ids_equal": unit_ids == bm25_ids,
         "files_present": sum(_exists(source, name) for name in bm25_files)},
        {"nonzero_equal_counts": True, "ids_equal": True, "files_present": len(bm25_files)}, bm25_files,
    ))

    graph_id = _graph_fingerprint(nodes, edges)
    same_build = bool(
        graph_id and neo.get("passed") is True and neo.get("build_id") == graph_id
        and neo.get("nodes") == len(nodes) and neo.get("edges") == len(edges)
        and final.get("semantic_quality", {}).get("neo4j_build_id") == graph_id
    )
    gates.append(_gate(
        "technical_same_graph_aura_build", same_build,
        {"computed_graph_build_id": graph_id, "neo4j_build_id": neo.get("build_id"),
         "semantic_build_id": final.get("semantic_quality", {}).get("neo4j_build_id"),
         "graph_counts": [len(nodes), len(edges)], "neo4j_counts": [neo.get("nodes"), neo.get("edges")]},
        {"all_build_ids_equal": True, "counts_equal": True}, [nodes_name, edges_name, neo_name, final_name],
    ))
    error_checks = [check for check in final.get("checks", [])
                    if not check.get("passed") and check.get("stage") in
                    {"registry", "structure", "graph", "indexes"}]
    gates.append(_gate("technical_validation_errors", not error_checks,
                       {"count": len(error_checks), "checks": error_checks}, {"count": 0}, [final_name]))
    return gates, {
        "final": final, "neo4j": neo, "dense": dense, "graph_build_id": graph_id,
        "counts": {"nodes": len(nodes), "edges": len(edges), "retrieval_units": len(units)},
    }


def _valid_date(value: str) -> bool:
    try:
        date.fromisoformat(str(value)[:10])
        return True
    except (TypeError, ValueError):
        return False


def _source_review_stats(seed: Path) -> dict[str, Any]:
    if not seed.exists():
        return {"records": 0, "approved_or_rejected": 0, "pending": 0,
                "invalid": 1, "groups": {}, "invalid_paths": [str(seed)],
                "unresolved_sha_mismatches": 0}
    with seed.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    groups = Counter(row.get("source_group", "") for row in rows)
    complete = 0
    pending = 0
    invalid_paths = []
    unresolved_sha = 0
    seen = set()
    for row in rows:
        path = row.get("relative_path", "")
        decision = row.get("legal_decision", "").strip()
        problems = []
        if not path or path in seen:
            problems.append("duplicate_or_missing_path")
        seen.add(path)
        if decision not in {"APPROVED", "REJECTED"}:
            pending += 1
            if decision and decision != "NEEDS_MORE_EVIDENCE":
                problems.append("invalid_decision")
        else:
            required = ("legal_reviewer", "legal_reviewed_at", "legal_review_notes",
                        "corpus_sha256", "source_provider")
            if any(not row.get(key, "").strip() for key in required):
                problems.append("missing_review_fields")
            if not _valid_date(row.get("legal_reviewed_at", "")):
                problems.append("invalid_review_date")
            sha_match = row.get("sha_match", "").strip()
            downloaded = row.get("downloaded_sha256", "").strip().lower()
            corpus = row.get("corpus_sha256", "").strip().lower()
            if decision == "APPROVED" and sha_match not in {"YES", "NO"}:
                problems.append("missing_sha_decision")
            if sha_match == "YES" and (not downloaded or downloaded != corpus):
                problems.append("false_sha_match")
            if sha_match == "NO":
                unresolved_sha += 1
            if not problems:
                complete += 1
        if problems:
            invalid_paths.append({"relative_path": path, "problems": problems})
    return {
        "records": len(rows), "approved_or_rejected": complete, "pending": pending,
        "invalid": len(invalid_paths), "invalid_paths": invalid_paths,
        "groups": dict(sorted(groups.items())), "unresolved_sha_mismatches": unresolved_sha,
    }


def _review_queue_stats(path: Path, kind: str) -> dict[str, Any]:
    if not path.exists():
        return {"records": 0, "final": 0, "pending": 0, "invalid": 1,
                "invalid_ids": [str(path)], "statuses": {}}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    statuses = Counter(str(row.get("review_status", "MISSING")) for row in rows)
    final = 0
    invalid = []
    seen = set()
    id_keys = {"legal_change": "change_id", "quarantine": "case_id"}
    key = id_keys.get(kind, "id")
    for index, row in enumerate(rows):
        item_id = row.get(key) or (row.get("quarantine_case_id") if kind == "quarantine" else None) \
            or (row.get("provision_id") if kind == "quarantine" else None)
        problems = []
        if not item_id or item_id in seen:
            problems.append("duplicate_or_missing_id")
        seen.add(item_id)
        status = row.get("review_status")
        if status in {"APPROVED", "EXCLUDED", "REJECTED"}:
            if not row.get("reviewer") or not _valid_date(row.get("reviewed_at", "")):
                problems.append("missing_reviewer_or_date")
            evidence = row.get("review_evidence") or row.get("review_note")
            if not evidence:
                problems.append("missing_review_evidence")
            if status == "EXCLUDED" and not row.get("exclusion_reason"):
                problems.append("missing_exclusion_reason")
            if kind == "legal_change" and status == "APPROVED" and (
                    not row.get("target_provision_identity_id") or not row.get("effective_from")):
                problems.append("incomplete_legal_change")
            if not problems:
                final += 1
        elif status != "DRAFT":
            problems.append("invalid_review_status")
        if problems:
            invalid.append({"id": item_id or index, "problems": problems})
    return {
        "records": len(rows), "final": final, "pending": len(rows) - final,
        "invalid": len(invalid), "invalid_ids": invalid,
        "statuses": dict(sorted(statuses.items())),
    }


def _package_gate(report_path: Path, build_id: str | None) -> dict[str, Any]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        report = {}
    passed = report.get("passed") is True and report.get("build_id") == build_id
    return _gate(
        "human_review_package_ready", passed, report or {"present": False},
        {"passed": True, "build_id": build_id}, [str(report_path)],
        [] if passed else ["HUMAN_REVIEW_PACKAGE_NOT_READY"], "PASS" if passed else "NOT_RUN",
    )


def audit_completion(artifacts: Path, seed: Path, archive: Path | None = None,
                     resolver_db: Path | None = None, resolver_export: Path | None = None,
                     package_report: Path | None = None) -> dict[str, Any]:
    archive_handle = zipfile.ZipFile(archive) if archive else None
    source: Path | zipfile.ZipFile = archive_handle or artifacts
    try:
        technical_gates, technical_data = _technical_gates(source, bool(archive_handle))
        resolver_db = resolver_db or artifacts / "00_manifest/source_resolution_p2_3_full_v3.sqlite"
        resolver_export = resolver_export or artifacts / "00_manifest/source_resolution_p2_3_full_v3_export"
        resolver = resolver_coverage(resolver_db, resolver_export, None) if resolver_db.exists() else {
            "resolution_complete": False, "records": 0, "automation_action_remaining": ["resolver not run"]}
        resolver_ok = resolver.get("resolution_complete") is True and resolver.get("records") == 95
        resolver_gate = _gate(
            "source_resolver_resolution_complete", resolver_ok, resolver,
            {"records": 95, "resolution_complete": True, "nonterminal_records": 0,
             "required_candidates_pending": 0, "retryable_failures": 0, "code_errors": 0},
            [str(resolver_db), str(resolver_export)],
        )
        package_report = package_report or artifacts / "reports/offline_human_review_package_validation.json"
        package_gate = _package_gate(package_report, technical_data["graph_build_id"])
        automation_gates = technical_gates + [resolver_gate, package_gate]
        automation_remaining = sum(not gate["passed"] for gate in automation_gates)

        review_root = seed.parent.parent if (seed.parent.parent / "legal_change_review_queue.jsonl").exists() else seed.parent
        source_review = _source_review_stats(seed)
        legal_review = _review_queue_stats(review_root / "legal_change_review_queue.jsonl", "legal_change")
        grouped_quarantine = review_root / "quarantine_review_cases.jsonl"
        quarantine_review = _review_queue_stats(
            grouped_quarantine if grouped_quarantine.exists() else review_root / "quarantine_review_queue.jsonl",
            "quarantine")
        final = technical_data["final"]
        gold = final.get("gold_evaluation", {})
        semantic = final.get("semantic_quality", {})
        source_done = source_review["records"] == 95 and source_review["approved_or_rejected"] == 95 \
            and source_review["invalid"] == 0 and source_review["unresolved_sha_mismatches"] == 0
        legal_done = legal_review["records"] > 0 and legal_review["pending"] == 0 and legal_review["invalid"] == 0
        quarantine_done = quarantine_review["records"] > 0 and quarantine_review["pending"] == 0 \
            and quarantine_review["invalid"] == 0
        gold_done = gold.get("passed") is True and int(gold.get("approved_queries", 0) or 0) > 0
        human_pending = []
        if not source_done:
            human_pending.append("Complete validated source decisions for all 95 records.")
        if not legal_done:
            human_pending.append("Review all grouped legal-change cases.")
        if not quarantine_done:
            human_pending.append("Review all grouped quarantine cases.")
        if not gold_done:
            human_pending.append("Approve Gold queries/qrels and quality thresholds.")
        if int(semantic.get("unreviewed_provision_versions", 0) or 0):
            human_pending.append("Approve temporal coverage and provision-version exceptions.")

        if automation_remaining:
            status = "FAILED_CODE"
        elif human_pending:
            status = "WAITING_FOR_HUMAN_REVIEW"
        elif final.get("offline_ready_for_online") is not True:
            status = "WAITING_FOR_REMOTE_EXECUTION"
        else:
            status = "COMPLETE"
        technical = {gate["name"].removeprefix("technical_"): gate["status"]
                     for gate in technical_gates}
        technical["error_count"] = next(
            gate["observed"]["count"] for gate in technical_gates
            if gate["name"] == "technical_validation_errors")
        artifact_ref = {
            "kind": "archive" if archive else "directory", "name": archive.name if archive else str(artifacts),
            "sha256": _sha256_file(archive) if archive and archive.exists() else None,
        }
        remaining = [gate["name"] for gate in automation_gates if not gate["passed"]] + human_pending
        return {
            "schema_version": 2, "status": status, "offline_ready_for_online": status == "COMPLETE",
            "generated_at": datetime.now(timezone.utc).isoformat(), "build_id": technical_data["graph_build_id"],
            "gold_build_id": final.get("gold_build_id"),
            "same_build_verified": next(g["passed"] for g in technical_gates
                                        if g["name"] == "technical_same_graph_aura_build"),
            "technical": technical,
            "automation": {"remaining": automation_remaining,
                           "all_prerequisite_gates_passed": automation_remaining == 0},
            "gates": sorted(automation_gates, key=lambda item: item["name"]),
            "source_resolution": resolver, "source_catalog": source_review,
            "temporal": {"pending_legal_changes": legal_review["pending"],
                         "unreviewed_provision_versions": int(semantic.get("unreviewed_provision_versions", 0) or 0),
                         "invalid_or_overlapping_intervals": None},
            "provenance": {"missing_required_spans": 0 if final.get("stages", {}).get("structure") is True else None,
                           "pending_quarantine_decisions": quarantine_review["pending"],
                           "derived_records_missing_evidence": sum(semantic.get("evidence_issues", {}).values())},
            "gold": {"approved_records": int(gold.get("approved_queries", 0) or 0),
                     "required_query_groups_present": bool(gold.get("required_query_types")),
                     "all_required_metrics_pass": gold.get("passed") is True,
                     "status": gold.get("status", "NOT_EVALUATED")},
            "review_queues": {"source": source_review, "legal_changes": legal_review,
                              "quarantine": quarantine_review},
            "artifacts": {"technical": artifact_ref, "resolver_db": str(resolver_db),
                          "resolver_export": str(resolver_export),
                          "review_package_validation": str(package_report)},
            "remaining_actions": remaining,
        }
    finally:
        if archive_handle:
            archive_handle.close()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_fingerprint(result: dict[str, Any]) -> str:
    stable = {key: value for key, value in result.items() if key != "generated_at"}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _write_iteration(path: Path, result: dict[str, Any], command: str) -> None:
    fingerprint = _content_fingerprint(result)
    existing = []
    if path.exists():
        existing = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(row.get("input_fingerprint") == fingerprint and row.get("decision") == result["status"]
           for row in existing):
        return
    entry = {
        "timestamp": result["generated_at"], "phase": "H", "iteration": len(existing) + 1,
        "input_fingerprint": fingerprint, "commands": [command],
        "exit_code": 0 if result["status"] == "COMPLETE" else 1,
        "failed_gates": result["remaining_actions"],
        "files_changed": ["artifacts/reports/offline_completion_contract.json",
                          "artifacts/reports/offline_completion_iterations.jsonl"],
        "decision": result["status"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--seed", type=Path,
                        default=ROOT / "review/inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--resolver-db", type=Path)
    parser.add_argument("--resolver-export", type=Path)
    parser.add_argument("--package-report", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "artifacts/reports/offline_completion_contract.json")
    args = parser.parse_args(argv)
    result = audit_completion(args.artifacts, args.seed, args.archive, args.resolver_db,
                              args.resolver_export, args.package_report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    automation_path = args.out.parent / "automation_remaining.json"
    automation_path.write_text(json.dumps({
        "schema_version": 1, "build_id": result["build_id"], **result["automation"],
        "failed_gates": [gate for gate in result["gates"] if not gate["passed"]],
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_iteration(args.out.parent / "offline_completion_iterations.jsonl", result,
                     "python scripts/audit_offline_completion.py --strict")
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] == "COMPLETE" or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
