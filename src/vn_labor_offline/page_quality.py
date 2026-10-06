"""Deterministic page-level extraction audit.

The audit never invents legal text and never chooses OCR merely because it is
longer.  It records measurable signals, compares native and OCR-selected text
when both exist, and creates a bounded visual-review queue.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from .util import write_jsonl


PAGE_QUALITY_SCHEMA = "page-quality-v1"
TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ỹĐđ]+", re.UNICODE)


def _normalized_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    return TOKEN_RE.findall(normalized)


def text_layer_metrics(text: str) -> dict:
    value = text or ""
    visible = [char for char in value if not char.isspace()]
    alnum = sum(char.isalnum() for char in visible)
    controls = sum(unicodedata.category(char) == "Cc" for char in value if char not in "\n\r\t")
    replacements = value.count("\ufffd") + value.count("\x00")
    repeated = Counter(visible).most_common(1)[0][1] if visible else 0
    lines = [" ".join(line.split()) for line in value.splitlines() if line.strip()]
    duplicate_lines = len(lines) - len(set(lines))
    return {
        "chars": len(value),
        "nonspace_chars": len(visible),
        "alnum_fraction": round(alnum / max(len(visible), 1), 4),
        "control_fraction": round(controls / max(len(value), 1), 4),
        "replacement_fraction": round(replacements / max(len(value), 1), 4),
        "dominant_character_fraction": round(repeated / max(len(visible), 1), 4),
        "duplicate_line_fraction": round(duplicate_lines / max(len(lines), 1), 4),
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
    }


def compare_native_ocr(native_text: str, selected_text: str) -> dict:
    """Compare content without treating extra OCR length as proof of quality."""
    native = Counter(_normalized_tokens(native_text))
    selected = Counter(_normalized_tokens(selected_text))
    common = sum((native & selected).values())
    total = sum(native.values()) + sum(selected.values())
    dice = 2 * common / total if total else 1.0
    native_chars = len("".join((native_text or "").split()))
    selected_chars = len("".join((selected_text or "").split()))
    ratio = min(native_chars, selected_chars) / max(native_chars, selected_chars, 1)
    return {
        "token_dice": round(dice, 4),
        "length_ratio": round(ratio, 4),
        "native_token_count": sum(native.values()),
        "selected_token_count": sum(selected.values()),
    }


def initial_page_reasons(native_text: str, selected_text: str, *, used_ocr: bool,
                         blank: bool, settings: dict) -> tuple[list[str], dict, dict | None]:
    native = text_layer_metrics(native_text)
    reasons: list[str] = []
    if not blank and native["nonspace_chars"]:
        if native["replacement_fraction"] > float(settings.get("page_max_replacement_fraction", .02)):
            reasons.append("TEXT_LAYER_REPLACEMENT_CHARACTERS")
        if native["control_fraction"] > float(settings.get("page_max_control_fraction", .01)):
            reasons.append("TEXT_LAYER_CONTROL_CHARACTERS")
        if (native["nonspace_chars"] >= 80 and
                native["alnum_fraction"] < float(settings.get("page_min_alnum_fraction", .45))):
            reasons.append("TEXT_LAYER_LOW_ALNUM_RATIO")
        if (native["nonspace_chars"] >= 80 and
                native["dominant_character_fraction"] > float(settings.get("page_max_dominant_character_fraction", .35))):
            reasons.append("TEXT_LAYER_REPEATED_GLYPH")
        if (len((native_text or "").splitlines()) >= 8 and
                native["duplicate_line_fraction"] > float(settings.get("page_max_duplicate_line_fraction", .60))):
            reasons.append("TEXT_LAYER_DUPLICATE_LINES")
    agreement = None
    if used_ocr:
        agreement = compare_native_ocr(native_text, selected_text)
        minimum = int(settings.get("page_compare_min_chars", 80))
        if (native["nonspace_chars"] >= minimum and
                len("".join((selected_text or "").split())) >= minimum and
                agreement["token_dice"] < float(settings.get("page_min_native_ocr_token_dice", .35))):
            reasons.append("NATIVE_OCR_LOW_AGREEMENT")
    return sorted(set(reasons)), native, agreement


def finalize_page_quality(page: dict, cleaned_text: str, selected_text: str) -> None:
    reasons = set(page.get("quality_reason_codes", []))
    cleaned_chars = len(cleaned_text)
    selected_nonspace = len("".join((selected_text or "").split()))
    if not page.get("blank") and selected_nonspace and not cleaned_text.strip():
        reasons.add("EMPTY_AFTER_CLEANING")
    if (not page.get("blank") and selected_nonspace >= 80 and
            cleaned_chars / max(len(selected_text), 1) < .10):
        reasons.add("CONTENT_DROPPED_BY_CLEANING")
    if page.get("ocr_status") in {"FAILED", "DISABLED"}:
        reasons.add("OCR_" + str(page["ocr_status"]))
    page["cleaned_chars"] = cleaned_chars
    page["selected_text_sha256"] = hashlib.sha256((selected_text or "").encode("utf-8")).hexdigest()
    page["cleaned_text_sha256"] = hashlib.sha256((cleaned_text or "").encode("utf-8")).hexdigest()
    page["quality_reason_codes"] = sorted(reasons)
    blocking = reasons & {"EMPTY_AFTER_CLEANING", "CONTENT_DROPPED_BY_CLEANING", "OCR_FAILED", "OCR_DISABLED"}
    if blocking:
        page["page_quality_status"] = "ERROR"
    elif reasons:
        page["page_quality_status"] = "REVIEW_REQUIRED"
    elif page.get("page_review"):
        page["page_quality_status"] = "REVIEWED"
    else:
        page["page_quality_status"] = "PASS"
    page["page_quality_schema"] = PAGE_QUALITY_SCHEMA


def write_page_quality_artifacts(extracted: list[dict], output_dir: Path) -> dict:
    audit: list[dict] = []
    queue: list[dict] = []
    reason_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for document in extracted:
        for page in document.get("page_provenance", []):
            reasons = list(page.get("quality_reason_codes", []))
            if not reasons:
                if page.get("ocr_status") in {"FAILED", "DISABLED"}:
                    reasons.append("OCR_" + str(page["ocr_status"]))
                if (not page.get("blank") and page.get("chars", 0) and
                        page.get("cleaned_chars", page.get("chars", 0)) == 0):
                    reasons.append("EMPTY_AFTER_CLEANING")
            status = page.get("page_quality_status")
            if not status:
                status = "REVIEWED" if page.get("page_review") else "REVIEW_REQUIRED" if reasons else "PASS"
            row = {
                "schema": PAGE_QUALITY_SCHEMA,
                "file_id": document.get("file_id"),
                "relative_path": document.get("relative_path"),
                "document_sha256": document.get("sha256"),
                "page": page.get("page"),
                "page_source_sha256": page.get("sha256"),
                "status": status,
                "reason_codes": sorted(set(reasons)),
                "method": page.get("method"),
                "ocr_status": page.get("ocr_status"),
                "native_chars": page.get("native_chars"),
                "selected_chars": page.get("chars"),
                "cleaned_chars": page.get("cleaned_chars"),
                "image_coverage": page.get("image_coverage"),
                "native_quality": page.get("native_quality"),
                "native_ocr_agreement": page.get("native_ocr_agreement"),
                "preview_path": page.get("preview_path"),
                "page_review": page.get("page_review"),
            }
            audit.append(row)
            status_counts[status] += 1
            reason_counts.update(row["reason_codes"])
            if status in {"ERROR", "REVIEW_REQUIRED"}:
                queue.append(row)
    write_jsonl(output_dir / "01_extracted/page_audit.jsonl", audit)
    write_jsonl(output_dir / "review_queues/page_extraction_review.jsonl", queue)
    summary = {
        "schema": PAGE_QUALITY_SCHEMA,
        "documents": len(extracted),
        "pages": len(audit),
        "status_counts": dict(sorted(status_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "review_queue_pages": len(queue),
        "error_pages": status_counts.get("ERROR", 0),
        "passed": status_counts.get("ERROR", 0) == 0,
        "note": "REVIEW_REQUIRED is intentionally not auto-approved; ERROR blocks technical validation.",
    }
    path = output_dir / "reports/page_extraction_quality.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return summary
