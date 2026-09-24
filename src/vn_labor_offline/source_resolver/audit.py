from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .provider_registry import ProviderRegistry
from .reason_codes import CODE_ERROR_REASONS, is_known_reason


def _load_export(export_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(export_dir) / "source_catalog_auto.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_audit(db: str | Path, export_dir: str | Path,
              registry_path: str | Path = "config/source_provider_registry.yaml",
              overrides_path: str | Path = "config/source_candidate_overrides.yaml") -> dict[str, Any]:
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    registry = ProviderRegistry.load(registry_path)
    gates: dict[str, dict[str, Any]] = {}

    def gate(name: str, observed: int, expected: int = 0, details: str = "",
             record_ids: list[str] | None = None, candidate_ids: list[str] | None = None) -> None:
        gates[name] = {
            "name": name, "passed": observed == expected, "observed": observed,
            "expected": expected, "record_ids": sorted(record_ids or []),
            "candidate_ids": sorted(candidate_ids or []), "details": details,
        }

    mismatches: list[str] = []
    for row in connection.execute("SELECT * FROM candidates ORDER BY candidate_id"):
        metadata = json.loads(row["metadata_json"] or "{}")
        for column, key in (("role", "role"), ("requested_url", "requested_url"),
                            ("final_url", "final_url"), ("state", "state")):
            if metadata.get(key, "") != row[column]:
                mismatches.append(row["candidate_id"])
                break
        if sorted(json.loads(row["reason_codes_json"] or "[]")) != sorted(metadata.get("reason_codes", [])):
            mismatches.append(row["candidate_id"])
    gate("candidate_column_metadata_mismatches", len(set(mismatches)),
         candidate_ids=list(set(mismatches)))

    bad_identity = connection.execute(
        """SELECT candidate_id FROM candidates
           WHERE role IN ('IDENTITY','STATUS_HISTORY') AND state='FETCHED'
           AND (reason_codes_json LIKE '%IDENTITY_NOT_FOUND%'
                OR reason_codes_json LIKE '%IDENTITY_MISMATCH%'
                OR reason_codes_json LIKE '%VBPL_HOME_SHELL%'
                OR reason_codes_json LIKE '%DOCUMENT_NOT_FOUND%')"""
    ).fetchall()
    gate("identity_or_status_mismatch_saved_as_fetched", len(bad_identity),
         candidate_ids=[row["candidate_id"] for row in bad_identity])

    shell = connection.execute(
        """SELECT candidate_id FROM candidates WHERE state='FETCHED'
           AND (reason_codes_json LIKE '%VBPL_HOME_SHELL%'
                OR metadata_json LIKE '%VBPL_HOME_SHELL%')"""
    ).fetchall()
    gate("home_shell_saved_as_fetched", len(shell),
         candidate_ids=[row["candidate_id"] for row in shell])

    exported = _load_export(export_dir)
    html_urls = [row["record_id"] for row in exported
                 if str(row.get("final_binary_url", "")).lower().split("?", 1)[0]
                 .endswith((".htm", ".html"))]
    gate("html_final_binary_urls", len(html_urls), record_ids=html_urls)

    no_authority = [row["record_id"] for row in exported
                    if row.get("state") == "AUTO_EXACT_SHA"
                    and row.get("binary_authority_verified") is False]
    gate("auto_exact_without_authority", len(no_authority), record_ids=no_authority)
    no_identity = [row["record_id"] for row in exported
                   if row.get("state") == "AUTO_EXACT_SHA"
                   and row.get("identity_match") != "YES"]
    gate("auto_exact_without_identity", len(no_identity), record_ids=no_identity)

    field_mismatch = []
    for row in exported:
        if row.get("binary_candidate_id") and row.get("binary_candidate_id") not in {
            candidate["candidate_id"] for candidate in connection.execute(
                "SELECT candidate_id FROM candidates WHERE record_id=?", (row["record_id"],)
            ).fetchall()
        }:
            field_mismatch.append(row["record_id"])
    gate("best_binary_field_mismatches", len(field_mismatch), record_ids=field_mismatch)

    conflicting_sha = [row["record_id"] for row in exported
                       if row.get("resolved_sha_match") == "NO" and
                       not row.get("resolved_downloaded_sha256")]
    gate("conflicting_sha_semantics", len(conflicting_sha), record_ids=conflicting_sha)

    satisfied_alternative = [row["record_id"] for row in exported
                             if row.get("resolved_sha_match") in {"YES", "NO"}
                             and row.get("blocking_reason_codes")]
    gate("blocking_reasons_from_satisfied_alternatives", len(satisfied_alternative),
         record_ids=satisfied_alternative)

    orphans = connection.execute(
        """SELECT c.candidate_id FROM candidates c
           WHERE c.parent_candidate_id <> ''
           AND NOT EXISTS (SELECT 1 FROM candidates p WHERE p.candidate_id=c.parent_candidate_id)"""
    ).fetchall()
    gate("browser_derived_orphans", len(orphans),
         candidate_ids=[row["candidate_id"] for row in orphans])

    duplicates = connection.execute(
        """SELECT record_id, role, requested_url, COUNT(*) AS n FROM candidates
           GROUP BY record_id, role, requested_url HAVING n > 1"""
    ).fetchall()
    gate("duplicate_candidates", sum(row["n"] - 1 for row in duplicates))
    duplicate_evidence = connection.execute(
        "SELECT evidence_id, COUNT(*) AS n FROM evidence GROUP BY evidence_id HAVING n > 1"
    ).fetchall()
    gate("duplicate_evidence_events", sum(row["n"] - 1 for row in duplicate_evidence))

    invalid_overrides = 0
    try:
        from .resolver import SourceResolver
        SourceResolver(registry, None, overrides_path=overrides_path)  # type: ignore[arg-type]
    except (ValueError, KeyError, TypeError):
        invalid_overrides = 1
    gate("invalid_override_entries", invalid_overrides)

    route_violations = []
    for row in connection.execute(
            "SELECT candidate_id, requested_url, role, state, reason_codes_json FROM candidates"):
        reasons = json.loads(row["reason_codes_json"] or "[]")
        if row["state"] == "BLOCKED" and "PROVIDER_NOT_ALLOWED" in reasons:
            continue
        if row["role"] in {"IDENTITY", "BINARY", "STATUS_HISTORY"} and registry.match(
                row["requested_url"], row["role"], None) is None:
            route_violations.append(row["candidate_id"])
    gate("provider_role_route_violations", len(route_violations), candidate_ids=route_violations)
    unclassified_candidates: list[str] = []
    code_error_candidates: list[str] = []
    nonterminal_records = [row["record_id"] for row in connection.execute(
        "SELECT record_id FROM records WHERE state NOT IN "
        "('AUTO_EXACT_SHA','AUTO_CONTENT_MATCH','NEEDS_REVIEW','BLOCKED')"
    )]
    required_pending: list[str] = []
    for row in connection.execute(
            "SELECT candidate_id,state,reason_codes_json,metadata_json FROM candidates"):
        codes = json.loads(row["reason_codes_json"] or "[]")
        if any(not is_known_reason(code) for code in codes):
            unclassified_candidates.append(row["candidate_id"])
        if any(code in CODE_ERROR_REASONS for code in codes):
            code_error_candidates.append(row["candidate_id"])
        metadata = json.loads(row["metadata_json"] or "{}")
        if metadata.get("required", False) and row["state"] in {"DISCOVERED", "FETCH_PENDING"}:
            required_pending.append(row["candidate_id"])
    gate("unclassified_reason_codes", len(set(unclassified_candidates)),
         candidate_ids=list(set(unclassified_candidates)))
    gate("resolver_code_errors", len(set(code_error_candidates)),
         candidate_ids=list(set(code_error_candidates)))
    gate("nonterminal_records", len(nonterminal_records), record_ids=nonterminal_records)
    gate("required_candidates_pending", len(required_pending), candidate_ids=required_pending)
    result = {
        "schema_version": 1,
        "passed": all(item["passed"] for item in gates.values()),
        "database_user_version": connection.execute("PRAGMA user_version").fetchone()[0],
        "gates": gates,
    }
    connection.close()
    return result
