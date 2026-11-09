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


def invalid_clause_locator(text):
    for match in re.finditer(r'\bkhoản\s+([a-zđ])\b',str(text),re.I):
        prefix=str(text)[max(0,match.start()-50):match.start()]
        if not re.search(r"(?:không\s+(?:có|phải|tồn tại)|ghi\s+sai(?:\s+là)?)\s*['\"“‘]?\s*$",prefix,re.I):
            return True
    return False


def _renewal_base_shift(claim,source):
    from .durations import _NUMBER,_integer
    if not re.search(r'hop dong(?: lao dong)? moi',source):return False
    if not ('sau do' in source and 'khong xac dinh thoi han' in source):return False
    # An explicit attached exception can defeat the ordinary repetition cap;
    # its factual applicability remains for the independent auditor.
    if re.search(r'nhieu lan[^.;]{0,100}hop dong|hop dong[^.;]{0,100}nhieu lan',source):return False
    limits=[_integer(m.group(1)) for m in re.finditer(rf'\bchi duoc ky them ({_NUMBER})\s+lan\b',source)]
    limits=[value for value in limits if value is not None]
    if len(set(limits))!=1:return False
    prior=re.search(rf'\bsau(?: khi)?\s+({_NUMBER})\s+hop dong\b',claim)
    if not prior:return False
    prior_count=_integer(prior.group(1))
    if prior_count is None:return False
    for addition in re.finditer(rf'\b(?:duoc|co the) ky them ({_NUMBER})\s+lan\b',claim):
        prefix=claim[max(0,addition.start()-35):addition.start()]
        if re.search(r'\b(?:khong|chua)(?:\s+(?:the|co|phai)){0,3}\s*$',prefix):continue
        extra=_integer(addition.group(1))
        if extra is not None and prior_count+extra>1+limits[0]:return True
    return False




def procedural_stage_mismatch(item,query):
    """A court-party procedure is not an employer's internal process.

    Case analogies and explicitly requested judicial comparisons retain their
    channel. This is a scope exclusion, never a proof of a substantive answer.
    """
    if getattr(item,'kind',None)=='CASE':return False
    q=fold(query)
    workplace=bool(re.search(r'xu ly ky luat|ky luat lao dong|cuoc hop ky luat',q))
    if not workplace or re.search(r'toa an|khoi kien|to tung|nguyen don|bi don|khang cao|khang nghi|vu an',q):return False
    source=fold(' '.join(str(v or '') for v in (getattr(item,'ancestor_context',None),
        getattr(item,'full_text',None) or getattr(item,'source_text',None) or item.text)))
    return bool(re.search(r'duong su[^.;]{0,140}toa an|nguyen don[^.;]{0,80}nghia vu[^.;]{0,30}chung minh|co quan tien hanh to tung',source))


def _money_values(text):
    from decimal import Decimal,InvalidOperation
    values=set()
    for match in re.finditer(r'\b(\d[\d.,]*)(?:\s+(nghin|trieu|ty))?\s+dong\b',text):
        raw=match.group(1)
        if re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+',raw):raw=raw.replace('.','').replace(',','')
        else:raw=raw.replace(',','.')
        try:values.add(Decimal(raw)*{'nghin':1000,'trieu':1000000,'ty':1000000000,None:1}[match.group(2)])
        except InvalidOperation:pass
    return values


def _reported_prohibited_fine(claim,source,query):
    """Case facts can contain money without asserting a statutory fine rate."""
    stated=_money_values(claim)
    if not stated or not stated<=_money_values(fold(query)):return False
    if not ('phat tien' in source and re.search(r'nghiem cam|bi cam|khong duoc',source)):return False
    negative_act=(re.search(r'(?:viec|hanh vi)[^.;!?]{0,160}phat tien[^.;!?]{0,160}(?:la|bi coi la)\s+(?:trai phap luat|khong hop phap|hanh vi bi cam)',claim)
        or re.search(r'(?:khong duoc phep|bi nghiem cam)[^.;!?]{0,120}phat tien',claim))
    if not negative_act:return False
    # A case amount must never become a legal sanction against another actor.
    return not re.search(r'xu phat|vi pham hanh chinh|phai nop phat|muc xu phat|phai chiu phat',claim)


def semantic_issues(text, items, *, context_query=''):
    q=fold(text); problems=[]
    if invalid_clause_locator(text): problems.append('CLAIM_CLAUSE_POINT_CONFUSION')
    invalidity_pattern=r'khong co gia tri phap ly|\bvo hieu\b|khong phat sinh quyen|khong co hieu luc|chi co hieu luc (?:neu|khi|trong truong hop|doi voi)'
    invalidity=re.search(invalidity_pattern,q)
    form_source=' '.join(fold(' '.join((str(getattr(item,'ancestor_context','') or ''),
        str(getattr(item,'full_text',None) or getattr(item,'source_text',None) or item.text)))) for item in items)
    if _renewal_base_shift(q,form_source):problems.append('CLAIM_RENEWAL_COUNT_BASE_SHIFT')
    no_change=re.search(r'\bkhong (?:co (?:bat ky |bat cu )?(?:quy dinh )?)?(?:thay doi|sua doi|bo sung)',q)
    interval_scope=re.search(r'trong (?:suot|khoang)|tu \d[^.;]{0,30}den \d',q)
    if no_change and interval_scope and q not in form_source:
        problems.append('CLAIM_UNPROVED_CHANGE_ABSENCE')
    penalty=re.search(r'(?:bi\s+phat\s+tien|muc\s+phat\s+tien|phat\s+tien\s+(?:tu|bang))',q)
    money=r'\d[\d.,]*(?:\s+(?:nghin|trieu|ty))?\s+dong\b'
    if penalty and re.search(money,q):
        negated=re.search(r'(?:khong|chua)(?:\s+(?:co|du|the|phai|duoc|can|cu|xac|dinh|ket|luan|khang)){0,8}\s*$',q[max(0,penalty.start()-55):penalty.start()])
        if (not negated and not ('phat tien' in form_source and re.search(money,form_source))
                and not _reported_prohibited_fine(q,form_source,context_query)):
            problems.append('CLAIM_MONETARY_PENALTY_WITHOUT_SANCTION_SOURCE')
    unknown=re.search(r'chua (?:duoc )?xac nhan|chua xac minh|chua ro|chua biet|khong biet|khong ro',q)
    if unknown:
        adverse=re.search(r'khong thuoc (?:nhom|truong hop)|khong co quyen|khong duoc huong|khong dap ung',q[unknown.end():])
        qualified=re.search(r'chua the (?:ket luan|khang dinh)|khong the (?:ket luan|khang dinh)',q)
        if adverse and not qualified and q not in form_source:
            problems.append('CLAIM_UNCERTAINTY_AS_NEGATIVE_FACT')
    universal=r'\b(?:trong moi truong hop|trong bat ky truong hop nao|khong co bat ky ngoai le nao|khong co ngoai le|luon luon)\b'
    # A source about a qualified act cannot prove an absolute statement about
    # all situations. Prefer its actual scope to an unnecessary universal.
    absolute=re.search(universal,q)
    if absolute and not re.search(universal,form_source):
        qualified=re.search(r'(?:khong the (?:ket luan|khang dinh)|chua the khang dinh|khong dong nghia)[^.;]{0,100}$',q[:absolute.start()])
        if not qualified:problems.append('CLAIM_UNSUPPORTED_UNIVERSAL_SCOPE')
    form_context=any(term in form_source for term in ('bang van ban','bang loi noi','thoa thuan mieng','hinh thuc','thong diep du lieu','hop dong dien tu'))
    if invalidity and form_context:
        qualified=re.search(r'(?:khong (?:dong nghia|co nghia|the coi|duoc coi)|(?:khong|chua) the (?:ket luan|khang dinh))[^.;]{0,80}$',q[:invalidity.start()])
        explicit=bool(re.search(invalidity_pattern,form_source))
        if not qualified and not explicit:problems.append('CLAIM_FORM_VIOLATION_AS_INVALIDITY')
    # A duty triggered at an event does not establish an earlier deadline.
    # Compare the event itself, not an article number or a canned legal rule.
    for advance in re.finditer(r'\btruoc khi ([^.;,!]{3,100})',q):
        prefix=q[max(0,advance.start()-120):advance.start()]
        caution=re.search(r'(?:chua|khong) (?:co|du) can cu|khong the (?:ket luan|khang dinh)',prefix)
        if caution:continue
        stop={'thoi','gian','viec','nay','do','mot','cac','da','duoc','phai'}
        event=set(re.findall(r'\w+',advance.group(1)))-stop
        triggered=[set(re.findall(r'\w+',m.group(1)))-stop for m in re.finditer(r'\bkhi ((?:da )?(?:ket thuc|hoan thanh|het thoi han|cham dut)[^,.;]{3,140})[,.;]',form_source)]
        prior=[set(re.findall(r'\w+',m.group(1)))-stop for m in re.finditer(r'\btruoc khi ([^,.;]{3,140})',form_source)]
        advance_rule=bool(re.search(r'(?<!khong )(?<!khong can )\bbao truoc\b',form_source))
        if (len(event)>=2 and any(event<=condition for condition in triggered)
                and not any(event<=condition for condition in prior) and not advance_rule):
            problems.append('CLAIM_UNSUPPORTED_ADVANCE_DEADLINE')
    absence=re.search(r'\bkhong (?:phai(?: duoc quy dinh)?|duoc quy dinh|co quy dinh|nam) (?:trong|tai) (?:bo luat|luat|nghi dinh|thong tu)\b',q)
    if absence and not any(q in fold(getattr(item,'full_text',None) or getattr(item,'source_text',None) or item.text) for item in items):
        # A positive finding in one statute cannot prove absence from another.
        # Prefer a supported positive answer to an ungrounded universal negative.
        problems.append('CLAIM_STATUTORY_ABSENCE_NOT_GROUNDED')
    for item in items:
        if procedural_stage_mismatch(item,context_query):problems.append('CLAIM_WRONG_PROCEDURAL_STAGE')
        number=getattr(item,'document_number',None) or getattr(item,'instrument_number',None)
        title=getattr(item,'document_title',None)
        typ=document_type(number,title,getattr(item,'document_type',None))
        source=fold(getattr(item,'source_text',None) or item.text)
        full_source=fold(' '.join((str(getattr(item,'ancestor_context','') or ''),
            str(getattr(item,'full_text',None) or getattr(item,'source_text',None) or item.text))))
        # A subgroup in an instrument's application scope is not a universal
        # definition of the employment relationship or contract category.
        scoped_population=('doi tuong ap dung' in full_source and any(term in full_source
            for term in ('lam cong viec sau','thuoc cac doi tuong','thuoc cac truong hop','cac nganh nghe sau')))
        general_contract=bool(re.search(r'\bhop dong(?: lao dong)? xac dinh thoi han\s+(?:la|co thoi han|co thoi gian)',q))
        explicit_definition='la hop dong ma' in full_source or 'duoc hieu la' in full_source
        scoped_claim=any(term in q for term in ('doi tuong ap dung','thuoc pham vi','trong pham vi','doi voi nhom','lam cong viec sau'))
        if scoped_population and general_contract and not explicit_definition and not scoped_claim:
            problems.append('CLAIM_SPECIAL_POPULATION_AS_GENERAL_DEFINITION')
        # Judicial review of a decision is a different procedural phase from
        # exercising the underlying workplace right. A lexical match on the
        # right's name cannot turn appeal procedure into its precondition.
        if re.search(r'thu tuc[^.;]{0,50}(?:khang cao|khang nghi)',full_source):
            primary=re.search(r'\b(?:viec )?(?:dinh cong|sa thai|don phuong cham dut hop dong(?: lao dong)?)\s+'
                r'(?:phai|can|bat buoc)[^.;]{0,100}thu tuc[^.;]{0,60}(?:khang cao|khang nghi)',q)
            if primary and not re.search(r'(?:khong the coi|khong duoc coi|khong phai)\s*$',q[max(0,primary.start()-45):primary.start()]):
                problems.append('CLAIM_JUDICIAL_REVIEW_AS_PRIMARY_PROCEDURE')
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
        if number in {'45/2019/QH14','18/VBHN-VPQH'} and article=='97':
            permission=bool(re.search(r'(?<!khong )(?<!chua )\bduoc(?: phep)?\s+cham\b',q))
            remedy_condition='bien phap khac phuc' in full_source
            qualified=any(term in q for term in ('bien phap khac phuc','cac dieu kien khac',
                'dap ung du dieu kien','kiem tra day du dieu kien'))
            if permission and 'bat kha khang' in q and remedy_condition and not qualified:
                problems.append('CLAIM_LATE_WAGE_REMEDY_CONDITION_LOST')
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
