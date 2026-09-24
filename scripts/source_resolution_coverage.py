from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

from vn_labor_offline.source_resolver.reason_codes import (
    CODE_ERROR_REASONS, RETRYABLE_REASONS, is_known_reason,
)


TERMINAL_RECORD_STATES = {"AUTO_EXACT_SHA", "AUTO_CONTENT_MATCH", "NEEDS_REVIEW", "BLOCKED"}
NONTERMINAL_CANDIDATE_STATES = {"DISCOVERED", "FETCH_PENDING"}


def build_report(db: Path, export_dir: Path, output: Path | None = None) -> dict:
    connection = sqlite3.connect(db)
    try:
        records = connection.execute("SELECT record_id,state,metadata_json FROM records ORDER BY record_id").fetchall()
        candidates = connection.execute(
            "SELECT candidate_id,record_id,provider_id,state,reason_codes_json,metadata_json "
            "FROM candidates ORDER BY candidate_id"
        ).fetchall()
        evidence = connection.execute("SELECT candidate_id FROM evidence ORDER BY evidence_id").fetchall()
        evidence_records = {row[0] for row in connection.execute(
            "SELECT DISTINCT c.record_id FROM candidates c JOIN evidence e ON e.candidate_id=c.candidate_id")}
    finally:
        connection.close()
    export_rows = [
        json.loads(line) for line in (export_dir / "source_catalog_auto.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] if (export_dir / "source_catalog_auto.jsonl").exists() else []
    record_states = Counter(state for _, state, _ in records)
    provider_states = Counter((provider, state) for _, _, provider, state, _, _ in candidates)
    reasons = Counter()
    reason_candidates: dict[str, set[str]] = {}
    required_pending = []
    for candidate_id, record_id, _, state, raw, metadata_json in candidates:
        metadata = json.loads(metadata_json or "{}")
        if metadata.get("required", False) and state in NONTERMINAL_CANDIDATE_STATES:
            required_pending.append(candidate_id)
        reasons.update(json.loads(raw or "[]"))
        for code in json.loads(raw or "[]"):
            reason_candidates.setdefault(code, set()).add(candidate_id)
    attempted = {
        record_id for record_id, _, metadata_json in records
        if json.loads(metadata_json).get("resolution_attempted_at")
    }
    succeeded = {record_id for record_id, state, _ in records if state == "AUTO_EXACT_SHA"}
    nonterminal_records = [record_id for record_id, state, _ in records
                           if state not in TERMINAL_RECORD_STATES]
    code_errors = sorted({candidate_id for code in CODE_ERROR_REASONS
                          for candidate_id in reason_candidates.get(code, set())})
    retryable = sorted({candidate_id for code in RETRYABLE_REASONS
                        for candidate_id in reason_candidates.get(code, set())})
    unclassified = sorted({candidate_id for code, ids in reason_candidates.items()
                           if not is_known_reason(code) for candidate_id in ids})
    candidate_records = {record_id for _, record_id, _, _, _, _ in candidates}
    unsupported_terminal = []
    for record_id, state, metadata_json in records:
        metadata = json.loads(metadata_json or "{}")
        if state in {"AUTO_EXACT_SHA", "AUTO_CONTENT_MATCH"}:
            supported = record_id in evidence_records
        else:
            supported = record_id in candidate_records or bool(metadata.get("reason_codes"))
        if state in TERMINAL_RECORD_STATES and not supported:
            unsupported_terminal.append(record_id)
    actions = []
    if len(records) != len(attempted):
        actions.append("Resolve unattempted records")
    if nonterminal_records:
        actions.append("Resolve nonterminal records")
    if required_pending:
        actions.append("Process required pending candidates")
    if retryable:
        actions.append("Retry transient fetch failures")
    if code_errors or unclassified:
        actions.append("Fix resolver code or unclassified errors")
    if unsupported_terminal:
        actions.append("Add evidence or reasons for unsupported terminal records")
    complete = bool(records) and not actions and len(export_rows) == len(records)
    report = {
        "schema_version": 1,
        "records": len(records),
        "attempted": len(attempted),
        "unattempted": len(records) - len(attempted),
        "candidates": len(candidates),
        "evidence": len(evidence),
        "export_records": len(export_rows),
        "succeeded_exact_sha": len(succeeded),
        "review_required": sum(state == "NEEDS_REVIEW" for _, state, _ in records),
        "blocked": sum(state == "BLOCKED" for _, state, _ in records),
        "terminal_records": len(records) - len(nonterminal_records),
        "nonterminal_records": len(nonterminal_records),
        "nonterminal_record_ids": sorted(nonterminal_records),
        "required_candidates_pending": len(required_pending),
        "required_pending_candidate_ids": sorted(required_pending),
        "retryable_failures": len(retryable),
        "retryable_candidate_ids": retryable,
        "code_errors": len(code_errors),
        "code_error_candidate_ids": code_errors,
        "unclassified_reason_codes": sum(not is_known_reason(code) for code in reasons),
        "unclassified_candidate_ids": unclassified,
        "unsupported_terminal_records": len(unsupported_terminal),
        "unsupported_terminal_record_ids": sorted(unsupported_terminal),
        "external_blocked": sum(state == "BLOCKED" for _, state, _ in records),
        "state_distribution": dict(sorted(record_states.items())),
        "provider_state_distribution": {
            f"{provider}|{state}": count for (provider, state), count in sorted(provider_states.items())
        },
        "reason_distribution": dict(sorted(reasons.items())),
        "resolution_complete": complete,
        "automation_action_remaining": actions,
        "evidence_paths": [str(db), str(export_dir)],
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_report(args.db, args.export_dir, args.out), ensure_ascii=False, sort_keys=True))
