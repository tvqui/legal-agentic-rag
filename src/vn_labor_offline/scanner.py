from __future__ import annotations
from pathlib import Path
import re
from datetime import date
from .util import sha256_file, stable_id, write_jsonl

SUPPORTED = {".pdf", ".doc", ".docx", ".html", ".htm", ".txt", ".json"}


def classify_source(rel: Path) -> tuple[str, str, bool]:
    s = rel.as_posix().lower()
    if "/laws/" in s: return "LEGAL_DOCUMENT", "LAW", True
    if "/decrees/" in s: return "LEGAL_DOCUMENT", "DECREE", True
    if "/circulars/" in s: return "LEGAL_DOCUMENT", "CIRCULAR", True
    if "/resolutions/" in s: return "LEGAL_DOCUMENT", "RESOLUTION", True
    if "/consolidated/" in s: return "CONSOLIDATED", "CONSOLIDATED", False
    if "/historical/" in s: return "LEGAL_DOCUMENT", "HISTORICAL", True
    if "/judgments/" in s: return "JUDICIAL", "JUDGMENT", False
    if "/cassation_decisions/" in s: return "JUDICIAL", "CASSATION", False
    if "/precedents/" in s: return "JUDICIAL", "PRECEDENT", False
    if "/official_guidance/" in s: return "SUPPLEMENTARY", "OFFICIAL_GUIDANCE", False
    if "/social_insurance_guidance/" in s: return "SUPPLEMENTARY", "SOCIAL_INSURANCE_GUIDANCE", False
    if "/ilo/" in s: return "SUPPLEMENTARY", "ILO", False
    return "UNKNOWN", "UNKNOWN", False


def scan(data_dir: Path, output_dir: Path) -> list[dict]:
    rows = []
    for p in sorted(data_dir.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in SUPPORTED:
            continue
        # Sidecar authority/config JSON is metadata, not a retrievable legal document.
        if p.name.upper() in {"SOURCE_AUTHORITY.JSON", "SOURCE_METADATA.JSON"}:
            continue
        rel = p.relative_to(data_dir)
        source_group, doc_type, binding = classify_source(rel)
        rows.append({
            "file_id": stable_id(rel.as_posix(), sha256_file(p), prefix="file"),
            "path": str(p.resolve()),
            "relative_path": rel.as_posix(),
            "filename": p.name,
            "extension": p.suffix.lower(),
            "size_bytes": p.stat().st_size,
            "sha256": sha256_file(p),
            "source_group": source_group,
            "document_type_hint": doc_type,
            "binding_default": binding,
        })
    write_jsonl(output_dir / "00_manifest" / "files.jsonl", rows)
    return rows


def resolve_source_catalog(manifest: list[dict], project_root: Path, output_dir: Path) -> list[dict]:
    """Resolve explicit source metadata without inferring provenance.

    Every manifest file receives exactly one record. A catalog SHA mismatch is
    fatal before extraction; absent provider/URL/date remains reviewable.
    """
    import yaml
    catalog_path = project_root / "config" / "source_catalog.yaml"
    catalog = (yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}).get("sources", {}) if catalog_path.exists() else {}
    resolved = []
    review = []
    seen_paths = set()
    for row in manifest:
        path = row["relative_path"]
        if path in seen_paths:
            raise ValueError(f"Duplicate manifest relative_path: {path}")
        seen_paths.add(path)
        entry = catalog.get(path) or catalog.get(row["filename"]) or {}
        if entry.get("sha256") and entry["sha256"] != row["sha256"]:
            raise ValueError(f"Source catalog SHA mismatch: {path}")
        missing = []
        for field in ("sha256", "source_provider", "source_url", "collected_at", "reviewer", "reviewed_at", "review_evidence"):
            if not entry.get(field):
                missing.append(field)
        authoritative = row["source_group"] in {"LEGAL_DOCUMENT", "CONSOLIDATED"}
        if authoritative and entry.get("official_source") is not True:
            missing.append("official_source")
        valid_dates = True
        parsed_dates = {}
        for field in ("collected_at", "reviewed_at"):
            if entry.get(field):
                try:
                    parsed_dates[field]=date.fromisoformat(str(entry[field]))
                except (TypeError, ValueError):
                    valid_dates = False
                    missing.append("valid_" + field)
        if (all(k in parsed_dates for k in ('collected_at','reviewed_at')) and
                parsed_dates['reviewed_at']<parsed_dates['collected_at']):
            missing.append('review_before_collection')
        if entry.get('source_url') and not str(entry['source_url']).startswith('https://'):
            missing.append('https_source_url')
        explicit_verified = entry.get("metadata_verified") is True and not missing and valid_dates
        official = entry.get("official_source") is True and explicit_verified
        binding = bool(entry.get("binding", row.get("binding_default", False))) and authoritative and official
        status = "VERIFIED" if explicit_verified else "UNVERIFIED"
        record = {
            "file_id": row["file_id"], "relative_path": path, "sha256": row["sha256"],
            "source_group": row["source_group"], "source_provider": entry.get("source_provider"),
            "source_url": entry.get("source_url"), "collected_at": entry.get("collected_at"),
            "official_source": official, "binding": binding,
            "reviewer": entry.get("reviewer"), "reviewed_at": entry.get("reviewed_at"),
            "review_evidence": entry.get("review_evidence"),
            "language": entry.get("language", "vi"), "catalog_status": status,
            "missing_fields": missing,
        }
        resolved.append(record)
        if status != "VERIFIED" or missing:
            review.append({**record, "review_reason": "explicit provenance metadata required"})
    if len(resolved) != len(manifest):
        raise ValueError("Source catalog resolution coverage mismatch")
    write_jsonl(output_dir / "00_manifest" / "source_catalog_resolved.jsonl", resolved)
    write_jsonl(output_dir / "00_manifest" / "source_review_queue.jsonl", review)
    return resolved


def source_catalog_gate(records: list[dict], registry: list[dict]) -> dict:
    """Independent provenance gate; local construction may still be inspected."""
    files = {d["file_id"]: d for d in registry}
    seen = {r.get("file_id") for r in records}
    problems = []
    if len(records) != len(files) or len(seen) != len(records) or seen != set(files):
        problems.append("SOURCE_CATALOG_COVERAGE_MISMATCH")
    for row in records:
        doc = files.get(row.get("file_id"), {})
        if row.get("sha256") != doc.get("sha256"):
            problems.append("SOURCE_CATALOG_SHA_MISMATCH")
        if row.get("catalog_status") != "VERIFIED":
            problems.append("UNVERIFIED_SOURCE")
        if doc.get("source_group") in {"LEGAL_DOCUMENT", "CONSOLIDATED"} and not row.get("official_source"):
            problems.append("UNVERIFIED_AUTHORITATIVE_SOURCE")
    return {"passed": bool(records) and not problems,
            "verified": sum(r.get("catalog_status") == "VERIFIED" for r in records),
            "total": len(records), "issues_by_type": {kind: problems.count(kind) for kind in sorted(set(problems))}}
