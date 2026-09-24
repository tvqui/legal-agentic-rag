from __future__ import annotations

from ..models import ResolverState


def decide(*, authority_ok: bool, identity_ok: bool, binary: dict | None, evidence_complete: bool, secondary: bool = False) -> tuple[ResolverState, list[str]]:
    reasons = []
    if secondary:
        return ResolverState.NEEDS_REVIEW, ["SECONDARY_SOURCE"]
    if not authority_ok:
        return ResolverState.BLOCKED, ["AUTHORITY_FAILED"]
    if not identity_ok:
        return ResolverState.NEEDS_REVIEW, ["IDENTITY_FAILED"]
    if binary is None:
        return ResolverState.FETCH_PENDING, ["BINARY_NOT_FETCHED"]
    reasons.extend(binary.get("reason_codes", []))
    if binary.get("state") == "AUTO_EXACT_SHA" and evidence_complete:
        return ResolverState.AUTO_EXACT_SHA, reasons
    if binary.get("state") == "AUTO_CONTENT_MATCH" and binary.get("content_comparator") == "verified":
        return ResolverState.AUTO_CONTENT_MATCH, reasons
    return ResolverState.NEEDS_REVIEW, reasons or ["EVIDENCE_INCOMPLETE"]
