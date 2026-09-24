from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ResolverState(StrEnum):
    DISCOVERED = "DISCOVERED"
    FETCH_PENDING = "FETCH_PENDING"
    FETCHED = "FETCHED"
    AUTO_EXACT_SHA = "AUTO_EXACT_SHA"
    AUTO_CONTENT_MATCH = "AUTO_CONTENT_MATCH"
    NEEDS_DISCOVERY = "NEEDS_DISCOVERY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"
    APPROVED = "APPROVED"


@dataclass(frozen=True)
class SeedRecord:
    relative_path: str
    source_group: str
    corpus_sha256: str
    filename: str
    instrument_number: str = ""
    document_number: str = ""
    title: str = ""
    current_candidate_url: str = ""
    collection_result: str = ""
    exact_source_url: str = ""
    direct_download_url: str = ""
    source_provider: str = ""
    collected_at: str = ""
    downloaded_sha256: str = ""
    sha_match: str = ""
    document_number_match: str = ""
    title_match: str = ""
    content_match: str = ""
    official_source: str = ""
    evidence_notes: str = ""

    @property
    def canonical_identifier(self) -> str:
        return canonical_identifier(self.source_group, self.instrument_number, self.document_number)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["canonical_identifier"] = self.canonical_identifier
        return data


@dataclass
class Candidate:
    record_id: str
    role: str
    requested_url: str
    final_url: str = ""
    provider_id: str = ""
    source_class: str = "SECONDARY"
    state: ResolverState = ResolverState.DISCOVERED
    reason_codes: list[str] = field(default_factory=list)
    downloaded_sha256: str = ""
    mime_type: str = ""
    size_bytes: int | None = None
    evidence_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    required: bool = True
    parent_candidate_id: str = ""
    alternative_group: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data


def canonical_identifier(source_group: str, instrument_number: str = "", document_number: str = "") -> str:
    if source_group in {"LEGAL_DOCUMENT", "CONSOLIDATED"}:
        return normalize_identifier(instrument_number or document_number)
    if source_group == "JUDICIAL":
        return normalize_identifier(document_number or instrument_number)
    return normalize_identifier(instrument_number or document_number)


def normalize_identifier(value: str) -> str:
    return " ".join((value or "").replace("\u00a0", " ").split()).strip()
