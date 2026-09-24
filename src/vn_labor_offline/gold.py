from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from .util import read_jsonl

QUERY_TYPES = {"DIRECT_PROVISION", "SCENARIO", "CROSS_REFERENCE", "MULTI_HOP",
               "TEMPORAL", "AMENDMENT_REPEAL", "CASE_LAW", "ANNEX_TABLE", "INSUFFICIENT_FACTS"}
REVIEW_STATES = {"DRAFT", "REVIEWED", "APPROVED"}


def fingerprint_json(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def validate_gold_record(record: dict) -> list[str]:
    required = ("query_id", "question", "query_type", "review_status")
    errors = [f"missing:{key}" for key in required if not record.get(key)]
    if record.get("query_type") not in QUERY_TYPES:
        errors.append("invalid:query_type")
    if record.get("review_status") not in REVIEW_STATES:
        errors.append("invalid:review_status")
    if record.get("review_status") == "APPROVED":
        for key in ("reviewer", "reviewed_at", "gold_source", "build_id"):
            if not record.get(key): errors.append(f"missing:{key}")
        if record.get("query_type") == "INSUFFICIENT_FACTS":
            if record.get("expected_no_answer") is not True:
                errors.append("missing:expected_no_answer")
        elif not isinstance(record.get("gold_unit_ids"), list) or not record["gold_unit_ids"]:
            errors.append("missing:gold_unit_ids")
        if record.get("query_type") in {"TEMPORAL", "AMENDMENT_REPEAL"} and not record.get("query_date"):
            errors.append("missing:query_date")
        for field in ("query_date", "reviewed_at"):
            if record.get(field):
                try: date.fromisoformat(str(record[field]))
                except (TypeError, ValueError): errors.append(f"invalid:{field}")
    return errors


def load_gold(path: Path) -> tuple[list[dict], list[dict]]:
    records = list(read_jsonl(path)) if path.exists() else []
    problems = []
    for record in records:
        problems.extend({"query_id": record.get("query_id"), "error": error}
                        for error in validate_gold_record(record))
    if len({r.get("query_id") for r in records}) != len(records):
        problems.append({"error": "duplicate:query_id"})
    return records, problems


def evaluate_gold(output_dir: Path) -> dict:
    gold_path = output_dir / "07_evaluation" / "gold_queries.jsonl"
    records, problems = load_gold(gold_path)
    approved = [r for r in records if r.get("review_status") == "APPROVED" and not
                validate_gold_record(r)]
    if problems or not approved:
        return {"status": "NOT_EVALUATED", "passed": False,
                "approved_queries": len(approved), "validation_errors": problems,
                "reason": "APPROVED gold records with reviewer are required"}
    from .gold_evaluator import evaluate_approved_gold
    return evaluate_approved_gold(output_dir, approved)
