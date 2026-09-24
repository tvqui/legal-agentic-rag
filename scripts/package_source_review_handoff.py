"""Build a private, reviewer-friendly source provenance handoff package."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import zipfile
import yaml

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = [
    "relative_path", "source_group", "corpus_sha256", "filename",
    "instrument_number", "document_number", "title", "current_candidate_url",
    "collection_result", "exact_source_url", "direct_download_url",
    "source_provider", "collected_at", "downloaded_sha256", "sha_match",
    "document_number_match", "title_match", "content_match", "official_source",
    "evidence_notes", "collector_name", "collector_checked_at",
    "legal_reviewer", "legal_reviewed_at", "legal_decision", "legal_review_notes",
]


def load_jsonl_from_zip(archive: zipfile.ZipFile, member: str) -> list[dict]:
    return [json.loads(line) for line in archive.read(member).splitlines() if line.strip()]


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError(f"Unsafe corpus path: {value}")
    return path


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(result_zip: Path, target: Path) -> dict:
    draft_path = ROOT / "review/inputs/v8_1/source_catalog_review_draft.yaml"
    catalog_path = ROOT / "config/source_catalog.yaml"
    guide_path = ROOT / "SOURCE_REVIEW_HANDOFF_V8_1.md"
    for path in (result_zip, draft_path, catalog_path, guide_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    draft = (yaml.safe_load(draft_path.read_text(encoding="utf-8")) or {}).get("sources", {})
    catalog = (yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}).get("sources", {})
    with zipfile.ZipFile(result_zip) as archive:
        manifest = load_jsonl_from_zip(archive, "artifacts/00_manifest/files.jsonl")
    if len(manifest) != 95 or len({row["relative_path"] for row in manifest}) != len(manifest):
        raise ValueError("V8.1 manifest must contain exactly 95 unique source files")

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    corpus_bytes = 0
    for row in manifest:
        relative = safe_relative(row["relative_path"])
        source = ROOT / "data" / Path(*relative.parts)
        if not source.is_file():
            raise FileNotFoundError(source)
        digest = sha256_file(source)
        if digest != row["sha256"]:
            raise ValueError(f"Local corpus SHA mismatch: {relative}")
        corpus_bytes += source.stat().st_size
        current = catalog.get(relative.as_posix(), {})
        pending = draft.get(relative.as_posix(), {})
        writer.writerow({
            "relative_path": relative.as_posix(),
            "source_group": row.get("source_group", ""),
            "corpus_sha256": digest,
            "filename": row.get("filename", source.name),
            "instrument_number": current.get("instrument_number", ""),
            "document_number": current.get("document_number", ""),
            "title": current.get("title", ""),
            "current_candidate_url": pending.get("candidate_source_url") or current.get("source_url", ""),
            "collection_result": "NOT_STARTED",
            "sha_match": "NOT_DOWNLOADED",
            "document_number_match": "UNCERTAIN",
            "title_match": "UNCERTAIN",
            "content_match": "UNCERTAIN",
            "official_source": "UNCERTAIN",
        })
    tracking = "\ufeff" + buffer.getvalue()
    manifest_text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest)
    report = {
        "schema": 1,
        "purpose": "Private source provenance collection; no legal approvals are created",
        "baseline": result_zip.name,
        "baseline_sha256": sha256_file(result_zip),
        "corpus_files": len(manifest),
        "corpus_bytes": corpus_bytes,
        "tracking_rows": len(manifest),
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as output:
        output.writestr("README_SOURCE_REVIEW.md", guide_path.read_text(encoding="utf-8"))
        output.writestr("source_review_tracking.csv", tracking.encode("utf-8"))
        output.writestr("corpus_manifest.jsonl", manifest_text.encode("utf-8"))
        output.write(catalog_path, "source_catalog_current_reference.yaml")
        output.write(draft_path, "source_catalog_review_draft_reference.yaml")
        output.writestr("PACKAGE_REPORT.json", json.dumps(report, ensure_ascii=False, indent=2))
        for row in manifest:
            relative = safe_relative(row["relative_path"])
            output.write(ROOT / "data" / Path(*relative.parts), "corpus/" + relative.as_posix())
    with zipfile.ZipFile(temporary) as output:
        bad = output.testzip()
        if bad:
            raise RuntimeError(f"Bad ZIP member: {bad}")
    temporary.replace(target)
    archive_sha = sha256_file(target)
    sha_path = target.with_suffix(target.suffix + ".sha256")
    sha_path.write_text(f"{archive_sha}  {target.name}\n", encoding="ascii")
    final_report = {**report, "archive": target.name, "archive_bytes": target.stat().st_size,
                    "archive_sha256": archive_sha, "zip_crc_check": "PASS",
                    "sha256_file": sha_path.name}
    (target.parent / "source_review_handoff_v8_1_package_report.json").write_text(
        json.dumps(final_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return final_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/review/source_review_handoff_v8_1_full.zip")
    args = parser.parse_args()
    print(json.dumps(build(args.result_zip, args.output), ensure_ascii=False, indent=2))
