from __future__ import annotations

from bisect import bisect_right
from pathlib import Path
from .util import read_jsonl, write_jsonl


def _align_segment(segment_text: str, document_text: str):
    """Map segment offsets into a document with only whitespace edits.

    Segmentation can collapse a blank line or replace whitespace when it
    repairs a glued heading. Any changed legal character remains unresolved.
    """
    if not segment_text or not document_text:
        return None
    first = document_text.find(segment_text)
    if first >= 0:
        if document_text.find(segment_text, first + 1) >= 0:
            return None
        return first, [(0, 0)]
    anchor = segment_text[:min(120, len(segment_text))]
    first = document_text.find(anchor)
    if first < 0 or document_text.find(anchor, first + 1) >= 0:
        return None
    i, j = 0, first
    shifts = [(0, 0)]
    while i < len(segment_text):
        if j >= len(document_text):
            return None
        if segment_text[i] == document_text[j]:
            i += 1
            j += 1
            continue
        old_i, old_j = i, j
        while i < len(segment_text) and segment_text[i].isspace():
            i += 1
        while j < len(document_text) and document_text[j].isspace():
            j += 1
        if (i == old_i and j == old_j) or (i < len(segment_text) and
                (j >= len(document_text) or segment_text[i] != document_text[j])):
            return None
        shifts.append((i, j - first - i))
    return first, shifts


def _document_offset(alignment, segment_offset: int) -> int:
    start, shifts = alignment
    index = bisect_right([position for position, _ in shifts], segment_offset) - 1
    return start + segment_offset + shifts[index][1]


def enrich_provenance(provisions: list[dict], extracted: list[dict], registry: list[dict], output_dir: Path) -> list[dict]:
    """Add explicit document/page coordinate spaces to parsed provisions."""
    by_id = {row.get("document_id"): row for row in extracted if row.get("document_id")}
    by_file = {row.get("file_id"): row for row in extracted if row.get("file_id")}
    registry_by_document = {row["document_id"]: row for row in registry}
    segments = {row["segment_id"]: row for row in read_jsonl(output_dir / "03_structure" / "segments.jsonl")}
    spans = []
    # Segment-to-document matching is shared by all provisions in a segment.
    # A unique exact match is required so source coordinates never point to an
    # arbitrary repeated passage or to the start of a document with a preamble.
    segment_locations: dict[tuple[str, str], tuple | None] = {}
    for provision in provisions:
        registry_row = registry_by_document.get(provision.get("document_id"), {})
        source = by_id.get(provision.get("document_id"), {})
        if not source and registry_row:
            source = by_file.get(registry_row.get("file_id"), {})
        segment_start = provision.get("char_start")
        segment_end = provision.get("char_end")
        segment_row = segments.get(provision.get("segment_id"), {})
        segment_text = segment_row.get("text", "")
        location_key = (provision.get("document_id"), provision.get("segment_id"))
        if location_key not in segment_locations:
            segment_locations[location_key] = _align_segment(segment_text, source.get("text") or "")
        alignment = segment_locations[location_key]
        document_segment_start = alignment[0] if alignment else None
        segment = next((s for s in source.get("page_provenance", []) if
                        document_segment_start is not None and
                        s.get("text_start", 0) <= document_segment_start < s.get("text_end", -1)), None)
        # parse_all supplies segment-text coordinates; only a unique source
        # match can lift them into document/page coordinates.
        document_start = document_end = None
        page_start = page_end = None
        page_status = "NOT_APPLICABLE"
        source_unit_type = "DOCUMENT"
        valid_segment_span = (isinstance(segment_start, int) and isinstance(segment_end, int)
                              and 0 <= segment_start < segment_end <= len(segment_text))
        if alignment is not None and valid_segment_span:
            document_start = _document_offset(alignment, segment_start)
            document_end = _document_offset(alignment, segment_end)
            document_text = source.get("text") or ""
            if (document_end > len(document_text) or
                    document_text[document_start:document_end] != segment_text[segment_start:segment_end]):
                document_start = document_end = None
        if source.get("page_provenance"):
            source_unit_type = "PDF_PAGE"
            page_status = "UNRESOLVED"
            if segment is not None and document_start is not None and document_end is not None:
                pages = [p["page"] for p in source["page_provenance"]
                         if p.get("text_start", 0) < document_end and p.get("text_end", 0) > document_start]
                if pages:
                    page_start, page_end = min(pages), max(pages)
                    page_status = "RESOLVED"
        provision.update({
            "coordinate_space": "SEGMENT_TEXT",
            "segment_char_start": segment_start, "segment_char_end": segment_end,
            "document_char_start": document_start, "document_char_end": document_end,
            "page_start": page_start, "page_end": page_end,
            "page_status": page_status, "source_unit_type": source_unit_type,
            "provenance_status": "RESOLVED" if segment_start is not None and document_start is not None and
                (page_status in {"RESOLVED", "NOT_APPLICABLE"}) else "UNRESOLVED",
        })
        spans.append({
            "provision_id": provision["provision_id"], "document_id": provision["document_id"],
            "segment_id": provision.get("segment_id"), "coordinate_space": "SEGMENT_TEXT",
            "segment_char_start": segment_start, "segment_char_end": segment_end,
            "document_char_start": document_start, "document_char_end": document_end,
            "page_start": page_start, "page_end": page_end, "page_status": page_status,
            "source_unit_type": source_unit_type, "provenance_status": provision["provenance_status"],
        })
    write_jsonl(output_dir / "03_structure" / "provision_spans.jsonl", spans)
    return provisions
