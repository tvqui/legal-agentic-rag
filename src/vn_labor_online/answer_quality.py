"""Conservative display cleanup and a bounded, evidence-preserving language check.

Original artifacts and source spans are never changed. This is not a proof of
legal correctness and deliberately does not guess OCR letters or legal numbers.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from .models import AdjudicationDraft

_SEPARATOR = re.compile(r"^[\s\-—–_=*•·.]+$")
_ADMIN = re.compile(r"^(?:[-*•]\s*)?(?:kính\s+gửi\s*:|nơi\s+nhận\s*:)", re.I)
_QUOTE = re.compile(r'“[^”]*”|"[^"\n]*"|^\s*>[^\n]*', re.M)
_URL = re.compile(r"https?://[^\s)\]>]+")
_OCR_WORD = re.compile(r"\b[^\W\d_]+[1|][^\W\d_]+\b", re.UNICODE)
_OCR_START = re.compile(r"\b1(?:ao|ương|àm|uật|ại|à)\b", re.I)
_MOJIBAKE = re.compile(r"á[»º]|Ä[‘‘đ]|Æ[°¡]|Ã[¡¢£©ª³´µ¶º¼½]")
_POLARITY = re.compile(
    r"\b(?:không|chưa|trừ|nếu|chỉ|ít nhất|nhiều nhất|tối đa|tối thiểu|"
    r"phải|được|có thể|hoặc|và)(?:\s+\w+){0,2}", re.I)
_ADMIN_QUERY = re.compile(r"kính\s+gửi|nơi\s+nhận", re.I)


def clean_display(text: str, *, allow_admin: bool = False) -> str:
    """Remove layout-only lines/control bytes; leave quoted text untouched."""
    quotes = []
    def protect(match):
        quotes.append(match.group())
        return f"\ue000{len(quotes)-1}\ue001"
    value = _QUOTE.sub(protect, text)
    value = ''.join(c for c in value if c in '\n\t' or unicodedata.category(c) != 'Cc')
    value = value.replace('\u200b', '').replace('\ufeff', '')
    lines = []
    for line in value.splitlines():
        line = re.sub(r'[ \t]+', ' ', line).strip()
        if line and _SEPARATOR.fullmatch(line):
            continue
        if not allow_admin and _ADMIN.match(line):
            continue
        lines.append(line)
    value = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
    for index, quote in enumerate(quotes):
        value = value.replace(f"\ue000{index}\ue001", quote)
    return value


def clean_source_excerpt(text: str, query: str) -> str:
    return clean_display(text, allow_admin=bool(_ADMIN_QUERY.search(query)))


def language_issues(text: str, *, allow_admin: bool = False) -> list[str]:
    """Detect observable defects, not arbitrary grammar or OCR substitutions."""
    issues = []
    # Quotes are immutable but still need a warning if their source is corrupt.
    if not re.search(r'[^\W\d_]', text, re.UNICODE):
        issues.append('EMPTY_OR_DECORATIVE_TEXT')
    if '\ufffd' in text or _MOJIBAKE.search(text):
        issues.append('CORRUPTED_CHARACTERS')
    if _OCR_WORD.search(text) or _OCR_START.search(text):
        issues.append('SUSPECT_OCR_WORD')
    if re.search(r'(?i)\b(?:điều|khoản)\s+[lI]\b', text):
        issues.append('SUSPECT_LEGAL_LOCATOR')
    unquoted = _QUOTE.sub('', text)
    if not allow_admin and re.search(r'(?i)\bkính\s+gửi\s*:', unquoted):
        issues.append('ADMINISTRATIVE_BOILERPLATE')
    if re.search(r'(?i)\b(\w{2,})(?:[ \t]+\1){2,}\b', unquoted):
        issues.append('REPEATED_WORD')
    for line in text.splitlines():
        if line.strip() and _SEPARATOR.fullmatch(line):
            issues.append('DECORATIVE_LINE')
        # Quoted administrative language can be legitimate evidence.
        if not allow_admin and _ADMIN.match(line):
            issues.append('ADMINISTRATIVE_BOILERPLATE')
    return list(dict.fromkeys(issues))


def clean_draft(draft: AdjudicationDraft, query: str) -> AdjudicationDraft:
    allow_admin = bool(_ADMIN_QUERY.search(query))
    claims = [claim.model_copy(update={'text': clean_display(claim.text, allow_admin=allow_admin)})
              for claim in draft.claims]
    answer = clean_display(draft.answer_summary, allow_admin=allow_admin)
    # Keep summary and public claim excerpts in sync.
    for old, new in zip(draft.claims, claims):
        if old.text != new.text and old.text in answer:
            answer = answer.replace(old.text, new.text)
    return draft.model_copy(update={'claims': claims, 'answer_summary': answer})


def draft_issues(draft: AdjudicationDraft, query: str) -> list[str]:
    allow_admin = bool(_ADMIN_QUERY.search(query))
    issues = language_issues(draft.answer_summary, allow_admin=allow_admin)
    for claim in draft.claims:
        issues.extend(f'{issue}:{claim.claim_id}' for issue in language_issues(claim.text, allow_admin=allow_admin))
    return list(dict.fromkeys(issues))


def _invariants(text: str) -> tuple:
    folded = ' '.join(unicodedata.normalize('NFC', text).lower().split())
    return (
        Counter(re.findall(r'\d+(?:[.,/]\d+)*', text)),
        Counter(_URL.findall(text)),
        Counter(_QUOTE.findall(text)),
        Counter(re.findall(r'(?i)\bđiểm\s+[a-zđ]\b', text)),
        Counter(re.findall(r'(?i)\b\d{1,4}/(?:\d{4}|VBHN)/[\w-]+', text)),
        Counter(_POLARITY.findall(folded)),
        Counter(re.findall(r'\b\d+(?:[.,/]\d+)*\s*(?:ngày làm việc|ngày|tháng|năm|giờ|phút|đồng|%)', folded)),
        Counter(re.findall(r'đặc thù|nặng nhọc|độc hại|nguy hiểm|bình thường|khuyết tật|chưa thành niên', folded)),
        folded.count('người lao động'), folded.count('người sử dụng lao động'),
    )


def guarded_language_edit(original: AdjudicationDraft, edited: AdjudicationDraft) -> bool:
    """Reject invented claims, locators, numbers, quotes, polarity and metadata.

This is intentionally restrictive: prefer an unchanged answer to a risky edit.
The normal reference audit still runs on every accepted edit afterwards.
"""
    if (original.applicable_law_versions != edited.applicable_law_versions or
        original.assumptions != edited.assumptions or original.limitations != edited.limitations or
        len(original.claims) != len(edited.claims)):
        return False
    for before, after in zip(original.claims, edited.claims):
        if before.claim_id != after.claim_id or before.evidence_ids != after.evidence_ids:
            return False
        if _invariants(before.text) != _invariants(after.text):
            return False
        words = lambda value: Counter(re.findall(r'\w+', value.lower()))
        old, new = words(before.text), words(after.text)
        shared = sum((old & new).values())
        if shared / max(sum(old.values()), sum(new.values()), 1) < .9:
            return False
    return True


def render_claims(draft: AdjudicationDraft, partial: bool) -> AdjudicationDraft:
    lines = ['Các quy định liên quan tìm được:']
    for claim in draft.claims:
        markers = ' '.join(f'[{evidence_id}]' for evidence_id in claim.evidence_ids)
        lines.append(f'- {claim.text} {markers}')
    if partial:
        lines.append('Kết quả còn giới hạn vì một số bằng chứng bắt buộc chưa đầy đủ.')
    return draft.model_copy(update={'answer_summary': '\n'.join(lines)})
