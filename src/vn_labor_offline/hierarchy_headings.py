"""Preserve independent heading spans for Chapter and Section graph nodes."""
from __future__ import annotations

from pathlib import Path
from .legal_structure import CHAPTER_RE, SECTION_RE, ARTICLE_RE
from .segmentation import structural_line
from .provenance import _align_segment, _document_offset
from .util import stable_id, write_jsonl


def build_hierarchy_headings(registry: list[dict], extracted: list[dict], segments: list[dict],
                             output_dir: Path) -> list[dict]:
    by_file = {r["file_id"]: r for r in extracted}
    docs = {r["document_id"]: r for r in registry}
    current_chapter: dict[str, str] = {}
    headings = {}
    for segment in segments:
        if segment["segment_type"] not in {"PREAMBLE", "MAIN_BODY"}:
            continue
        document_id = segment["document_id"]
        text = segment["text"]
        lines = text.splitlines(keepends=True)
        source = by_file.get(docs.get(document_id, {}).get("file_id"), {})
        document_text = source.get("text") or ""
        alignment = _align_segment(text, document_text)
        offset = 0
        for i, raw in enumerate(lines):
            line = raw.rstrip("\r\n")
            structural = structural_line(line)
            chapter = CHAPTER_RE.match(structural)
            section = SECTION_RE.match(structural)
            if chapter:
                current_chapter[document_id] = chapter.group(1)
                kind, number = "Chapter", chapter.group(1)
                node_id = stable_id(document_id, "chapter", number, prefix="hier")
            elif section:
                kind, number = "Section", section.group(1)
                parent_chapter = current_chapter.get(document_id, "")
                node_id = stable_id(document_id, "section", parent_chapter, number, prefix="hier")
            else:
                offset += len(raw)
                continue
            title = ""
            if i + 1 < len(lines):
                following = lines[i + 1].strip()
                if (following and not CHAPTER_RE.match(structural_line(following)) and
                        not SECTION_RE.match(structural_line(following)) and
                        not ARTICLE_RE.match(structural_line(following))):
                    title = following
            start = offset + len(line) - len(line.lstrip())
            end = offset + len(line.rstrip())
            if title:
                end = offset + len(raw) + len(lines[i + 1].rstrip("\r\n"))
            record = {"id": node_id, "label": kind, "number": number, "title": title,
                      "document_id": document_id, "segment_id": segment["segment_id"],
                      "coordinate_space": "SEGMENT_TEXT", "segment_char_start": start,
                      "segment_char_end": end, "line_start": segment["line_start"] + i,
                      "line_end": segment["line_start"] + i + int(bool(title)),
                      "document_char_start": None, "document_char_end": None,
                      "page_start": None, "page_end": None, "page_status": "NOT_APPLICABLE"}
            if alignment and 0 <= start < end <= len(text):
                doc_start = _document_offset(alignment, start)
                doc_end = _document_offset(alignment, end)
                if document_text[doc_start:doc_end] == text[start:end]:
                    record["document_char_start"] = doc_start
                    record["document_char_end"] = doc_end
                    pages = [p["page"] for p in source.get("page_provenance", []) if
                             p.get("text_start", 0) < doc_end and p.get("text_end", 0) > doc_start]
                    if pages:
                        record["page_start"], record["page_end"] = min(pages), max(pages)
                        record["page_status"] = "RESOLVED"
                    elif source.get("page_provenance"):
                        record["page_status"] = "UNRESOLVED"
            record["provenance_status"] = ("RESOLVED" if record["document_char_start"] is not None and
                                          record["page_status"] != "UNRESOLVED" else "UNRESOLVED")
            headings.setdefault(node_id, record)
            offset += len(raw)
    rows = list(headings.values())
    write_jsonl(output_dir / "03_structure" / "hierarchy_headings.jsonl", rows)
    return rows
