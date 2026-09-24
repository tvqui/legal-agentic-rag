from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

from .models import ResolverState, SeedRecord

REQUIRED_HEADERS = {
    "relative_path", "source_group", "corpus_sha256", "filename", "instrument_number",
    "document_number", "title", "current_candidate_url", "collection_result", "exact_source_url",
    "direct_download_url", "source_provider", "collected_at", "downloaded_sha256", "sha_match",
    "document_number_match", "title_match", "content_match", "official_source", "evidence_notes",
    "collector_name", "collector_checked_at", "legal_reviewer", "legal_reviewed_at",
    "legal_decision", "legal_review_notes",
}


def _safe_relative_path(value: str) -> str:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts or value.startswith(("/", "\\")):
        raise ValueError(f"unsafe relative_path: {value!r}")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or normalized == "." or normalized.endswith("/"):
        raise ValueError(f"unsafe relative_path: {value!r}")
    return normalized


def read_seed(path: str | Path) -> list[SeedRecord]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED_HEADERS - headers
        if missing:
            raise ValueError(f"seed CSV missing required headers: {sorted(missing)}")
        rows = []
        for raw in reader:
            values = {field: (raw.get(field) or "").strip() for field in SeedRecord.__dataclass_fields__}
            values["relative_path"] = _safe_relative_path(values["relative_path"])
            rows.append(SeedRecord(**values))
    paths = [row.relative_path for row in rows]
    if len(rows) != len(set(paths)):
        raise ValueError("seed contains duplicate relative_path values")
    if len(rows) != 95:
        raise ValueError(f"expected 95 seed records, found {len(rows)}")
    return rows


def _catalog_rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return raw.get("sources", {})
    return {row["relative_path"]: row for row in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if row.get("relative_path")}


def validate_against_catalog(records: Iterable[SeedRecord], catalog_path: str | Path | None,
                            corpus_root: str | Path | None = None) -> None:
    if not catalog_path:
        return
    catalog = _catalog_rows(Path(catalog_path))
    missing = [row.relative_path for row in records if row.relative_path not in catalog]
    if missing:
        raise ValueError(f"catalog missing seed records: {missing[:3]}{'...' if len(missing) > 3 else ''}")
    for row in records:
        existing = catalog.get(row.relative_path)
        if existing and (existing.get("sha256") or existing.get("corpus_sha256")) not in {None, "", row.corpus_sha256}:
            raise ValueError(f"corpus SHA mismatch for {row.relative_path}")
        if existing and existing.get("source_group") and existing["source_group"] != row.source_group:
            raise ValueError(f"source_group mismatch for {row.relative_path}")
        if corpus_root:
            corpus_path = Path(corpus_root) / Path(row.relative_path)
            if not corpus_path.is_file():
                raise ValueError(f"corpus file missing for {row.relative_path}: {corpus_path}")
            digest = hashlib.sha256()
            with corpus_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != row.corpus_sha256:
                raise ValueError(f"corpus file SHA mismatch for {row.relative_path}")


def initial_state(row: SeedRecord) -> ResolverState:
    if row.collection_result == "SOURCE_NOT_FOUND":
        return ResolverState.NEEDS_DISCOVERY
    if row.collection_result == "MULTIPLE_CANDIDATES":
        return ResolverState.NEEDS_REVIEW
    if row.direct_download_url or row.exact_source_url or row.current_candidate_url:
        return ResolverState.FETCH_PENDING
    return ResolverState.NEEDS_DISCOVERY


def import_records(csv_path: str | Path, catalog_path: str | Path | None = None,
                   corpus_root: str | Path | None = None) -> list[dict]:
    records = read_seed(csv_path)
    validate_against_catalog(records, catalog_path, corpus_root)
    result = []
    for row in records:
        data = row.to_dict()
        data["record_id"] = hashlib.sha256(row.relative_path.encode()).hexdigest()[:16]
        data["state"] = initial_state(row).value
        data["source_class"] = "OFFICIAL_CANDIDATE" if row.official_source.upper() == "YES" else "SECONDARY"
        data["seed_collection_result"] = row.collection_result
        data["seed_sha_match"] = row.sha_match
        data["seed_downloaded_sha256"] = row.downloaded_sha256
        data["resolution_state"] = data["state"]
        data["resolved_downloaded_sha256"] = ""
        data["resolved_sha_match"] = ""
        data["resolved_at"] = ""
        data["identity_match"] = ""
        data["identity_source"] = ""
        data["final_identity_url"] = ""
        data["final_binary_url"] = ""
        data["legal_reviewer"] = ""
        data["legal_reviewed_at"] = ""
        data["legal_decision"] = ""
        result.append(data)
    return result
