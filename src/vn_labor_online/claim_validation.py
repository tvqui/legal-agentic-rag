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

def _continued_work_context(query):
    q=fold(query)
    expression=r'\b(?:toi|nld|nguoi lao dong)\s+(?:van\s+(?:tiep tuc lam viec|di lam)|tiep tuc lam viec)\b'
    for match in re.finditer(expression,q):
        prefix=q[max(0,match.start()-50):match.start()]
        if not re.search(r'(?:khong phai|khong dung la|chua the noi|khong the noi)\s*$',prefix): return True
    return False

def semantic_issues(text, items, *, context_query=''):
    q=fold(text); problems=[]
    for item in items:
        number=getattr(item,'document_number',None) or getattr(item,'instrument_number',None)
        title=getattr(item,'document_title',None)
        typ=document_type(number,title,getattr(item,'document_type',None))
        source=fold(getattr(item,'source_text',None) or item.text)
        payment_minimum=('tro cap' in source and 'it nhat bang' in source and
            bool(re.search(r'\d+\s*%',source)))
        deduction=bool(re.search(r'(?<!khong )\b(?:bi tru|bi khau tru|bi giam)\b',q))
        if payment_minimum and deduction and not any(term in source for term in ('khau tru','bi tru','bi giam')):
            problems.append('CLAIM_BENEFIT_PAYMENT_INVERTED_TO_DEDUCTION')
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
        if number in {'45/2019/QH14','18/VBHN-VPQH'} and article=='105':
            source_context=fold(' '.join(str(value or '') for value in (getattr(item,'full_text',None),source)))
            numeric_hours=bool(re.search(r'\b\d+\s+gio',q))
            adverse=any(term in q for term in ('vi pham','trai phap luat','khong hop phap'))
            scoped='binh thuong' in q or 'binh thuong' in fold(context_query)
            if 'thoi gio lam viec binh thuong' in source_context and numeric_hours and adverse and not scoped:
                problems.append('CLAIM_NORMAL_HOURS_SCOPE_LOST')
        source_context=fold(' '.join(str(value or '') for value in (getattr(item,'full_text',None),source)))
        age_band=re.search(r'tu du (\d+) tuoi den (?:chua du|duoi) (\d+) tuoi',source_context)
        if age_band and 'cong viec nhe' in source_context:
            lower,upper=age_band.groups()
            broad=f'duoi {upper} tuoi' in q and 'cong viec nhe' in q
            if broad and not re.search(r'\b'+re.escape(lower)+r'\b',q):
                problems.append('CLAIM_MINOR_AGE_SCOPE_LOST')
        if number in {'45/2019/QH14','18/VBHN-VPQH','10/2012/QH13'} and article in {'20','22'}:
            context=fold(' '.join(str(value or '') for value in (getattr(item,'full_text',None),
                getattr(item,'ancestor_context',None),getattr(item,'source_text',None),item.text)))
            continued='van tiep tuc lam viec' in context
            conversion=bool(re.search(r'\b30\s+ngay\b',q)) and bool(re.search(r'tro thanh|chuyen thanh|phai ky ket[^.;]{0,40}hop dong',q))
            if continued and conversion and not _continued_work_context(context_query) and not any(term in q for term in ('tiep tuc lam viec','van di lam','tiep tuc thuc hien cong viec')):
                problems.append('CLAIM_CONTRACT_CONTINUATION_CONDITION_LOST')
        if number in {'45/2019/QH14','18/VBHN-VPQH'} and article=='35':
            if re.search(r'(?<!khong )(?:neu|phai|can)\s+co\s+ly do chinh dang',q):
                problems.append('CLAIM_EMPLOYEE_EXIT_INVENTED_REASON_REQUIREMENT')
            if 'dao tao' in q and 'khong can bao truoc' in q and 'dao tao' not in source:
                problems.append('CLAIM_EMPLOYEE_EXIT_INVENTED_EXCEPTION')
            context=fold(' '.join(str(value or '') for value in (getattr(item,'full_text',None),
                getattr(item,'ancestor_context',None),source)))
            late_wage_rule=('tra luong khong dung thoi han' in context or 'khong duoc tra du luong' in context)
            linked_exception=bool(re.search(r'khoan\s+4\s+dieu\s+97',context))
            no_notice=any(term in q for term in ('khong can bao truoc','khong phai bao truoc','duoc nghi ngay'))
            qualified=any(term in q for term in ('bat kha khang','khoan 4 dieu 97','tru truong hop',
                'kiem tra ngoai le','xac minh ngoai le','chua the ket luan'))
            # Absence of the exception must be stated, never inferred from a
            # 20-day delay alone (the referenced rule permits some delays).
            query=fold(context_query)
            excluded=bool(re.search(r'khong co\s+(?:(?:su kien|ly do)\s+)?bat kha khang',query))
            negative=any(term in q for term in ('khong co quyen nghi','khong duoc nghi ngay',
                'khong duoc cham dut','khong duoc don phuong'))
            if late_wage_rule and linked_exception and no_notice and not (qualified or excluded or negative):
                problems.append('CLAIM_LATE_WAGE_EXCEPTION_LOST')
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
