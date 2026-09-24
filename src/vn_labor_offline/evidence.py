"""Locate derived/legal evidence in the cleaned source coordinate spaces."""
from __future__ import annotations

import re


def _candidate_matches(text: str, phrase: str):
    words = re.split(r"(\s+)", phrase.strip())
    pattern = "".join(r"\s+" if part.isspace() else re.escape(part) for part in words)
    return list(re.finditer(pattern, text, flags=re.I)) if pattern else []


def locate_evidence(provision: dict, phrase: str, segment_text: str,
                    document_text: str = "", page_provenance: list[dict] | None = None) -> tuple[str, dict, str]:
    """Return an exact source substring and its span, or UNRESOLVED.

    A match must be unique within the provision in both source coordinate
    spaces. Whitespace may differ in generated text, but the stored evidence
    is copied from the source, never from a normalized projection.
    """
    start, end = provision.get("char_start"), provision.get("char_end")
    if not phrase or not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(segment_text):
        return phrase, {}, "UNRESOLVED"
    matches = _candidate_matches(segment_text[start:end], phrase)
    if len(matches) != 1:
        return phrase, {}, "AMBIGUOUS" if len(matches) > 1 else "UNRESOLVED"
    match = matches[0]
    segment_start, segment_end = start + match.start(), start + match.end()
    source_phrase = segment_text[segment_start:segment_end]
    span = {
        "segment_id": provision.get("segment_id"), "coordinate_space": "SEGMENT_TEXT",
        "char_start": segment_start, "char_end": segment_end,
        "segment_char_start": segment_start, "segment_char_end": segment_end,
        "document_char_start": None, "document_char_end": None,
        "page_start": None, "page_end": None,
        "page_status": provision.get("page_status", "NOT_APPLICABLE"),
    }
    doc_start, doc_end = provision.get("document_char_start"), provision.get("document_char_end")
    if document_text and isinstance(doc_start, int) and isinstance(doc_end, int) and 0 <= doc_start < doc_end <= len(document_text):
        doc_matches = _candidate_matches(document_text[doc_start:doc_end], source_phrase)
        if len(doc_matches) != 1:
            return source_phrase, span, "AMBIGUOUS" if len(doc_matches) > 1 else "UNRESOLVED"
        doc_match = doc_matches[0]
        absolute_start, absolute_end = doc_start + doc_match.start(), doc_start + doc_match.end()
        if document_text[absolute_start:absolute_end] != source_phrase:
            return source_phrase, span, "UNRESOLVED"
        span["document_char_start"] = absolute_start
        span["document_char_end"] = absolute_end
        if page_provenance:
            pages = [row["page"] for row in page_provenance if
                     row.get("text_start", 0) < absolute_end and row.get("text_end", 0) > absolute_start]
            if not pages:
                return source_phrase, span, "UNRESOLVED"
            span["page_start"], span["page_end"] = min(pages), max(pages)
            span["page_status"] = "RESOLVED"
    elif provision.get("source_unit_type") == "PDF_PAGE":
        return source_phrase, span, "UNRESOLVED"
    if provision.get("source_unit_type") == "PDF_PAGE" and span["page_status"] != "RESOLVED":
        return source_phrase, span, "UNRESOLVED"
    return source_phrase, span, "RESOLVED"


def locate_document_evidence(phrase: str, document_text: str,
                             page_provenance: list[dict] | None = None) -> tuple[str, dict, str]:
    """Find one exact case/annex phrase in a cleaned document, with page span."""
    matches = _candidate_matches(document_text, phrase) if phrase else []
    if len(matches) != 1:
        return phrase, {}, "AMBIGUOUS" if len(matches) > 1 else "UNRESOLVED"
    match = matches[0]
    source_phrase = document_text[match.start():match.end()]
    span = {"coordinate_space": "DOCUMENT_TEXT", "document_char_start": match.start(),
            "document_char_end": match.end(), "page_start": None, "page_end": None,
            "page_status": "NOT_APPLICABLE"}
    if page_provenance:
        pages = [row["page"] for row in page_provenance if
                 row.get("text_start", 0) < match.end() and row.get("text_end", 0) > match.start()]
        if not pages:
            return source_phrase, span, "UNRESOLVED"
        span["page_start"], span["page_end"] = min(pages), max(pages)
        span["page_status"] = "RESOLVED"
    return source_phrase, span, "RESOLVED"
