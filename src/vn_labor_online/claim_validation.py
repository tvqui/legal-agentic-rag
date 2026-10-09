"""Fail-closed guards for observed semantic failures, not a universal legal proof.

Lexical overlap is only a relevance screen. These checks reject known wrong
document types, inverted omission duties and ungrounded employee-exit grounds.
"""
from __future__ import annotations
import re
import unicodedata
from .legal_metadata import document_type, norm_role

def fold(value):
    value=unicodedata.normalize('NFD',str(value or '').lower()).replace('đ','d')
    return ' '.join(''.join(c for c in value if unicodedata.category(c)!='Mn').split())

def semantic_issues(text, items):
    q=fold(text); problems=[]
    for item in items:
        number=getattr(item,'document_number',None) or getattr(item,'instrument_number',None)
        title=getattr(item,'document_title',None)
        typ=document_type(number,title,getattr(item,'document_type',None))
        source=fold(getattr(item,'source_text',None) or item.text)
        if number and typ:
            # Match the type next to this specific number, not an unrelated law
            # title that happens to occur elsewhere in a multi-source claim.
            pattern=r'(nghi dinh|thong tu|van ban hop nhat|bo luat|luat)(?:\s+so)?\s+'+re.escape(fold(number))
            for match in re.finditer(pattern,q):
                label=match.group(1)
                if label!=fold(typ) and not (label=='luat' and fold(typ)=='bo luat'):
                    problems.append('CLAIM_DOCUMENT_TYPE_MISMATCH')
        if norm_role(number,title,source)=='SANCTION':
            for action in ('dao tao','ky hop dong dao tao','ky ket hop dong lao dong'):
                if 'khong '+action in source and 'khong duoc '+action in q and 'khong duoc '+action not in source:
                    problems.append('CLAIM_OMISSION_DUTY_INVERTED')
        article=str(getattr(item,'article_number',None) or getattr(item,'article',None) or '')
        if number in {'45/2019/QH14','18/VBHN-VPQH'} and article=='35':
            if re.search(r'(?<!khong )(?:neu|phai|can)\s+co\s+ly do chinh dang',q):
                problems.append('CLAIM_EMPLOYEE_EXIT_INVENTED_REASON_REQUIREMENT')
            if 'dao tao' in q and 'khong can bao truoc' in q and 'dao tao' not in source:
                problems.append('CLAIM_EMPLOYEE_EXIT_INVENTED_EXCEPTION')
        if number in {'45/2019/QH14','18/VBHN-VPQH','10/2012/QH13'} and article in {'25','27'}:
            # 180/60/30 are calendar days. Only 06 is stated as working days.
            for days in (180,60,30):
                if re.search(rf'\b{days}\s+ngay lam viec\b',q) and not re.search(rf'\b{days}\s+ngay lam viec\b',source):
                    problems.append('CLAIM_PROBATION_DAY_UNIT_MISMATCH')
    # A citation to an unrelated clause cannot justify this universal negative.
    # Keep conditional descriptions of genuinely different work or situations.
    for sentence in re.split(r'[.!?;\n]+',q):
        repeated=bool(re.search(r'thu viec[^.]{0,80}(?:hai lan|2 lan|nhieu lan|lan thu hai)',sentence))
        same_work=any(term in sentence for term in ('cung mot cong viec','cung cong viec','mot cong viec'))
        permits=(bool(re.search(r'khong co[^.]{0,80}(?:cam|han che)|duoc phep[^.]{0,50}thu viec',sentence)) or
          'la hop phap' in sentence or 'van hop phap' in sentence)
        if repeated and same_work and permits and not any(term in sentence for term in ('khong hop phap','khong duoc phep','khong dung')):
            problems.append('CLAIM_PROBATION_REPEAT_NOT_SUPPORTED')
    return list(dict.fromkeys(problems))

def proposition_issues(claim, items):
    proposition=getattr(claim,'proposition',None)
    if proposition is None: return []
    from .taxonomy import locator_matches
    matches=[item for item in items if locator_matches(item,proposition.locator)]
    if not matches: return ['CLAIM_PROPOSITION_LOCATOR_MISMATCH']
    if proposition.predicate!='PROBATION_LIMIT': return ['CLAIM_UNKNOWN_PROPOSITION']
    for item in matches:
        source=fold(item.source_text or item.text)
        suffix=r'(?!\s+lam viec)' if proposition.unit=='ngày' else ''
        expression=rf'khong qua 0?{proposition.value}\s+{re.escape(fold(proposition.unit))}\b'+suffix
        if re.search(expression,source) and re.search(rf'\b0?{proposition.value}\s+{re.escape(fold(proposition.unit))}\b'+suffix,fold(claim.text)):
            return []
    return ['CLAIM_PROPOSITION_NOT_SUPPORTED']
