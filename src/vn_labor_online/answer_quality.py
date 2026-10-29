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


def _notice_claim_signature(text: str):
    folded=unicodedata.normalize('NFD',text.lower()).replace('đ','d')
    folded=''.join(char for char in folded if unicodedata.category(char)!='Mn')
    folded=' '.join(folded.split())
    if 'nguoi su dung lao dong' in folded or re.search(r'\bcong ty\b',folded):
        actor='EMPLOYER'
    elif 'nguoi lao dong' in folded or re.search(r'\btoi\b',folded):
        actor='EMPLOYEE'
    else:
        return None
    if 'khong xac dinh thoi han' in folded:
        contract='INDEFINITE'
    elif 'xac dinh thoi han' in folded:
        contract='FIXED_TERM'
    else:
        return None
    if any(term in folded for term in ('khong can bao truoc','khong phai bao truoc','khong phai thong bao truoc')):
        notice='NOT_REQUIRED'
    elif 'phai bao truoc' in folded or 'can bao truoc' in folded:
        notice='REQUIRED'
    else:
        return None
    quantities=tuple(re.findall(r'\b\d+(?:[.,]\d+)*\s*(?:ngay lam viec|ngay|thang)\b',folded))
    if not quantities:
        return None
    # Only collapse the narrow, unqualified notice paraphrases understood here.
    # Anything beyond this vocabulary stays a separate claim for legal review.
    neutral_notice_words=set(('theo quy dinh tai dieu khoan diem a b c d cua bo luat '
        'van ban hop nhat lao dong nguoi su dung lam viec hop dong khong xac dinh '
        'thoi han co quyen don phuong cham dut nhung phai can thong bao truoc it '
        'nhat toi thieu ngay khi nghi').split())
    if set(re.findall(r'[a-z]+',folded))-neutral_notice_words:
        return None
    # The *contents* of a qualification matter, not just the presence of 'if'.
    # In particular, 'đã' and 'chưa' must never collapse into the same claim.
    qualification_text=re.sub(
        r'\btruoc khi don phuong (?:nghi viec|cham dut(?: hop dong(?: lao dong)?)?)\b',
        '',folded)
    conditions=tuple(re.findall(
        r'\b(?:neu|tru truong hop|ngoai tru|chi khi|khong thuoc truong hop|'
        r'ke tu|tu ngay|truoc khi|sau khi)\b[^.;]*',qualification_text))
    bound='MAXIMUM' if 'toi da' in folded or 'khong qua' in folded else (
        'MINIMUM' if 'it nhat' in folded or 'toi thieu' in folded else 'UNQUALIFIED')
    # Preserve extra assertions and qualifications outside the narrow notice
    # paraphrases. Shared source IDs do not establish semantic equivalence.
    protected=tuple(term for term in ('khong hop phap','trai phap luat','duoc boi thuong',
        'khong duoc boi thuong','da thanh toan','chua thanh toan','nganh nghe dac thu',
        'cong viec dac thu','khong ap dung','khong phai','chi ap dung') if term in folded)
    return actor,contract,notice,quantities,conditions,bound,protected


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
    folded=''.join(c for c in unicodedata.normalize('NFD',text).lower().replace('đ','d') if unicodedata.category(c)!='Mn')
    if re.search(r'(?i)\b(?:điều|khoản)\s+[lI]\b', text) or re.search(
      r'\b(?:dieu|khoan)\s+(?:\d+[il|]\d+|[il|]+\d+)\b',folded):
        issues.append('SUSPECT_LEGAL_LOCATOR')
    from .claim_validation import invalid_clause_locator
    if invalid_clause_locator(text): issues.append('SUSPECT_LEGAL_LOCATOR')
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
    unique=[]; by_text={}; by_notice={}
    for claim in claims:
        key=' '.join(claim.text.lower().split())
        # A neutral connective adds no legal proposition. All remaining words,
        # numbers and qualifications must still match exactly to deduplicate.
        key=re.sub(r'^ngoài ra,\s*','',key)
        signature=_notice_claim_signature(claim.text)
        notice_key=(signature,tuple(sorted(claim.evidence_ids))) if signature else None
        index=by_text.get(key)
        if index is None and notice_key is not None: index=by_notice.get(notice_key)
        if index is not None:
            previous=unique[index]
            unique[index]=previous.model_copy(update={'evidence_ids':list(dict.fromkeys(previous.evidence_ids+claim.evidence_ids))})
        else:
            index=len(unique)
            by_text[key]=index
            if notice_key is not None: by_notice[notice_key]=index
            unique.append(claim)
    answer = clean_display(draft.answer_summary, allow_admin=allow_admin)
    # Keep summary and public claim excerpts in sync.
    for old, new in zip(draft.claims, claims):
        if old.text != new.text and old.text in answer:
            answer = answer.replace(old.text, new.text)
    result=draft.model_copy(update={'claims': unique, 'answer_summary': answer})
    if len(unique)!=len(claims):
        # Regenerate from the retained claims, keeping every supporting ID.
        return render_claims(result, bool(draft.limitations))
    return result


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
        if before.claim_id != after.claim_id or before.evidence_ids != after.evidence_ids or before.proposition != after.proposition:
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
