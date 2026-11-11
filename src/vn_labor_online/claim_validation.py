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
    value=str(text)
    for match in re.finditer(r'\bkhoản\s+([a-zđ])\b',value,re.I):
        prefix=value[max(0,match.start()-50):match.start()]
        if not re.search(r"(?:không\s+(?:có|phải|tồn tại)|ghi\s+sai(?:\s+là)?)\s*['\"“‘]?\s*$",prefix,re.I):
            return True
    for match in re.finditer(r'\bđiểm\s+\d+\s*,?\s*điều\s+\d+\b',value,re.I):
        prefix=value[max(0,match.start()-50):match.start()]
        if not re.search(r"(?:không\s+(?:có|phải|tồn tại)|ghi\s+sai(?:\s+là)?)\s*['\"“‘]?\s*$",prefix,re.I):
            return True
    return False


def _explicit_locators(text):
    content=fold(text)
    article_matches=list(re.finditer(r'\bdieu\s+(\d+)\b',content))
    def locator(pattern,segment,reverse=False):
        matches=list(re.finditer(pattern,segment))
        if reverse:matches.reverse()
        for candidate in matches:
            before=segment[max(0,candidate.start()-45):candidate.start()]
            if not re.search(r'(?:khong\s+(?:co|phai|ton tai)|ghi sai(?:\s+la)?)\s*$',before):
                return candidate
        return None
    for index,match in enumerate(article_matches):
        previous_end=article_matches[index-1].end() if index else 0
        sentence_start=max((content.rfind(mark,previous_end,match.start())+1
            for mark in '.;?!\n'),default=previous_end)
        prefix=content[max(previous_end,sentence_start,match.start()-100):match.start()]
        next_article=article_matches[index+1].start() if index+1<len(article_matches) else len(content)
        punctuation=[position for mark in '.;?!\n'
            if (position:=content.find(mark,match.end(),next_article))>=0]
        suffix_end=min([next_article,match.end()+100,*punctuation])
        suffix=content[match.end():suffix_end]
        prefix_clauses=list(re.finditer(r'\bkhoan\s+(\d+)\b',prefix))
        if len(prefix_clauses)>1:
            for clause_index,clause_match in enumerate(prefix_clauses):
                start=prefix_clauses[clause_index-1].end() if clause_index else 0
                point_match=locator(r'\bdiem\s+([a-z]|\d+)\b',prefix[start:clause_match.start()],reverse=True)
                yield (match.group(1),clause_match.group(1),point_match.group(1) if point_match else None)
            continue
        def nearest(pattern):
            before=locator(pattern,prefix,reverse=True)
            after=locator(pattern,suffix)
            options=[]
            if before:options.append((len(prefix)-before.end(),before))
            if after:options.append((after.start(),after))
            return min(options,key=lambda pair:pair[0])[1] if options else None
        clause_match=nearest(r'\bkhoan\s+(\d+)\b')
        point_match=nearest(r'\bdiem\s+([a-z]|\d+)\b')
        yield (match.group(1),clause_match.group(1) if clause_match else None,
            point_match.group(1) if point_match else None)


def _locator_metadata_mismatch(text,items):
    """Require explicit claim locators to agree with attached evidence metadata."""
    content_locators=list(_explicit_locators(text))
    cited_source_locators={
        locator for item in items
        for locator in _explicit_locators(
            ' '.join(str(value or '') for value in (
                getattr(item,'ancestor_context',None),
                getattr(item,'full_text',None),
                getattr(item,'source_text',None),
                item.text,
            ))
        )
    }
    for article,clause,point in content_locators:
        metadata_present=False
        matched=False
        for item in items:
            item_article=getattr(item,'article',None)
            if item_article is None:item_article=getattr(item,'article_number',None)
            item_clause=getattr(item,'clause',None)
            if item_clause is None:item_clause=getattr(item,'clause_number',None)
            item_point=getattr(item,'point',None)
            if item_point is None:item_point=getattr(item,'point_number',None)
            item_article=str(item_article or '')
            if not item_article:
                continue
            metadata_present=True
            if item_article!=article:
                continue
            if clause is not None and item_clause is not None and str(item_clause)!=clause:
                continue
            if point is not None and item_point is not None and fold(item_point)!=point.lower():
                continue
            matched=True
            break
        # A source may itself refer to another provision. Preserve that
        # source-level cross-reference rather than treating it as the source's
        # own article/clause locator.
        if metadata_present and not matched and (article,clause,point) not in cited_source_locators:
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


def _instrument_year_mismatch(text,items):
    """Compare an explicit law-name year with cited enactment metadata.

    No year is inferred from effectiveness or from a consolidation identifier.
    Multiple cited editions may legitimately name different enactment years.
    """
    names={}
    for item in items:
        number=(getattr(item,'original_instrument_number',None) or
                getattr(item,'document_number',None) or getattr(item,'instrument_number',None) or '')
        year=re.search(r'/((?:19|20)\d{2})/(?:QH|UBTVQH)',number,re.I)
        title=fold(getattr(item,'document_title',None))
        title=re.sub(r'^van ban hop nhat\s+','',title)
        title=re.sub(r'\s+(?:nam\s+)?(?:19|20)\d{2}\b.*$','',title).strip()
        if year and re.match(r'^(?:bo luat|luat)\s+',title):
            entry=names.setdefault(title,{'original':set(),'edition':set()})
            entry['original'].add(year.group(1))
            if str(getattr(item,'version_role','')).upper()=='CONSOLIDATED':
                issued=getattr(item,'consolidation_as_of',None) or getattr(item,'promulgated_date',None)
                if issued and re.match(r'^(?:19|20)\d{2}-',issued):entry['edition'].add(issued[:4])
    content=fold(text)
    for title,years in names.items():
        for mention in re.finditer(r'\b'+re.escape(title)+r'\s*(?:\(\s*)?'
                r'(?:(sua doi(?:\s*[,;]?\s*(?:va\s+)?bo sung)?|bo sung)\s*(?:\)\s*)?)?'
                r'(?:nam\s+)?((?:19|20)\d{2})\b',content):
            prefix=content[max(0,mention.start()-35):mention.start()]
            edition=bool(re.search(r'(?:van ban hop nhat|vbhn)\s*$',prefix))
            allowed=years['edition'] if edition else years['original']
            year=mention.group(2)
            if mention.group(1) and not edition:
                # A consolidated edition's date does not establish an
                # amendment in that year. Require an actual amendment citation
                # in the supplied source instead of borrowing its issue year.
                source=' '.join(fold(getattr(item,'full_text',None) or getattr(item,'source_text',None)
                    or getattr(item,'text','')) for item in items)
                amendment=re.search(r'(?:sua doi|bo sung)[^.;]{0,180}\b\d+/'+year+r'/qh\d+\b',source)
                if amendment:continue
            if allowed and year not in allowed:return True
    return False


def _conditional_consequence_lost(claim,source,query):
    """Reject an exact statutory consequence stripped of its antecedent.

    This deliberately checks a narrow source-text relationship, not general
    entailment. Numeric-only conditions and free paraphrases stay for review.
    """
    stop=set('nguoi lao dong su dung ben cac mot nhung thi neu truong hop cua duoc phai co la khi tu tro len den du it nhat trong theo quy dinh gio ngay thang nam bang ve tai'.split())
    pairs=[match.groups() for match in re.finditer(
        r'\b(?:truong hop|neu)\s+([^.;]{8,220}?)\s+thi\s+([^.;]{8,220})',source)]
    # A statutory subject can carry the condition without the word "nếu":
    # "Người ... [qualified category] thì Y" still does not grant Y to all.
    pairs.extend(match.groups() for match in re.finditer(
        r'\b((?:nguoi lao dong|nguoi su dung lao dong|cac ben)\s+[^.;]{8,180}?)\s+thi\s+([^.;]{8,220})',source))
    # Restrictive scope can follow the consequence rather than precede it:
    # "Y applies to cases X" is not an unconditional entitlement to Y.
    for match in re.finditer(r'(?:^|[.;])\s*([^.;]{14,220}?)\s+doi voi truong hop\s+'
            r'([^.;,]{8,180}?)(?=\s+quy dinh tai|\s+it nhat|[,.;]|$)',source):
        consequence,condition=match.groups()
        if re.search(r'\b(?:duoc|phai|co quyen)\b',consequence):pairs.append((condition,consequence))
    # Relative clauses may qualify an operative duty after its main phrase.
    for match in re.finditer(r'([^.;]{14,220}?)\s+ma\s+([^.;]{8,180}?)(?=[;,.]|$)',source):
        consequence,condition=match.groups()
        if re.match(r'(?:van|duoc|phai|co quyen|co nghia vu)\b',condition.strip()):continue
        consequence=re.split(r':|(?:^|\s)[a-z]\)\s*',consequence)[-1].strip()
        consequence=re.sub(r'^(?:[a-z]\)|\d+[.)])\s*','',consequence.strip())
        if re.search(r'\b(?:phai|duoc|co quyen|khong duoc|co nghia vu)\b',consequence):
            pairs.append((condition,consequence))
    for condition,consequence in pairs:
        consequence=consequence.strip(' ,:')
        # Omitting the nominal prefix "thời gian" does not turn a conditional
        # time entitlement into an unconditional one. This comparison only
        # detects omitted scope; it never rewrites the published/source text.
        consequence_form=re.sub(r'\bthoi gian\s+','',consequence)
        claim_form=re.sub(r'\bthoi gian\s+','',claim)
        predicate_form=re.sub(r'^(?:phai|duoc|co quyen|co nghia vu)\s+','',consequence_form)
        inherited_duty=bool(re.search(r'\b(?:phai|duoc|co quyen|co nghia vu)\b',claim_form)
            and predicate_form in claim_form)
        if len(consequence.split())<7 or not (consequence_form in claim_form or inherited_duty):continue
        # Citation boilerplate is a locator, not an additional case fact.
        # Likewise, a paraphrase can state the agreement without repeating the
        # grammatical subject "hai bên". Keep the actual agreement predicate.
        condition=re.sub(r'\b(?:quy dinh tai|theo)\s+(?:(?:diem\s+[a-z]\b|(?:khoan|dieu)\s+\d+\b)[\s,]*(?:va\s+)?)+(?:cua\s+(?:bo luat|luat|nghi dinh|thong tu)\s+nay)?',' ',condition)
        condition=re.sub(r'^hai ben\s+','',condition)
        anchors=set(re.findall(r'[a-z]+',condition))-stop
        if len(anchors)<3:continue
        claim_words=set(re.findall(r'[a-z]+',claim))
        if anchors<=claim_words:continue
        if re.search(r'(?:neu|khi)\s+(?:dap ung|thoa man|du)\s+(?:day du\s+)?(?:cac\s+)?dieu kien',claim):continue
        # A stated personal case can establish either a positive or negative
        # antecedent, but the polarity must match the source condition.
        def negative_targets(sentence):
            targets=set()
            for negation in re.finditer(r'\b(?:khong|chua|chang)\b',sentence):
                words=re.findall(r'[a-z]+',sentence[negation.end():])
                target=next((word for word in words if word not in stop),None)
                if target:targets.add(target)
            return targets
        condition_negative=bool(negative_targets(condition)&anchors)
        context_ok=False
        for sentence in re.split(r'[.;?!]|\b(?:nhung|tuy nhien)\b',query):
            if not anchors<=set(re.findall(r'[a-z]+',sentence)):continue
            if re.search(r'\b(?:khong|chua)\s+(?:biet|ro|chac|xac nhan|xac dinh)|'
                         r'\b(?:khong dung la|khong phai la|gia su|gia dinh|neu)\b',sentence):continue
            if bool(negative_targets(sentence)&anchors)==condition_negative:
                context_ok=True;break
        if not context_ok:return True
    return False


def semantic_issues(text, items, *, context_query=''):
    q=fold(text); problems=[]
    if _instrument_year_mismatch(text,items):problems.append('CLAIM_INSTRUMENT_YEAR_MISMATCH')
    if invalid_clause_locator(text): problems.append('CLAIM_CLAUSE_POINT_CONFUSION')
    if _locator_metadata_mismatch(text,items):
        problems.append('CLAIM_LOCATOR_METADATA_MISMATCH')
    invalidity_pattern=r'khong co gia tri phap ly|\bvo hieu\b|khong phat sinh quyen|khong co hieu luc|chi co hieu luc (?:neu|khi|trong truong hop|doi voi)'
    invalidity=re.search(invalidity_pattern,q)
    form_source=' '.join(fold(' '.join((str(getattr(item,'ancestor_context','') or ''),
        str(getattr(item,'full_text',None) or getattr(item,'source_text',None) or item.text)))) for item in items)
    scoped_query=fold(context_query)
    notice_only=re.search(r'\b(?:chi\s+(?:xet|danh gia|hoi)|rieng)\s+(?:ve\s+)?(?:thoi han|so ngay)[^.;?!]{0,25}bao truoc',scoped_query)
    limited_facet=re.search(r'\b(?:chi\s+(?:xet|hoi|vi|theo)|rieng\s+(?:ve|xet)|xet rieng)\b[^.;?!]{0,100}',scoped_query)
    global_exit=re.search(r'\b(?:viec|hanh vi|quyet dinh|cong ty|nguoi su dung lao dong)\b[^.;?!]{0,100}\b(?:la|van|deu|khong)\s+(?:hop phap|trai phap luat|dung phap luat|vi pham|khong vi pham)',q)
    bounded=re.search(r'\b(?:chi\s+(?:xet|ve)|rieng\s+(?:ve|xet)|xet rieng)[^.;?!]{0,50}bao truoc|(?:khong|chua) the (?:ket luan|khang dinh)',q)
    if not bounded and limited_facet:
        statements=[statement for statement in re.split(r'[.;?!]',q) if re.search(global_exit.re.pattern,statement)] if global_exit else []
        bounded=bool(statements) and all(re.search(
            r'\b(?:chi xet|chi ve|rieng ve|xet rieng)\b[^.;?!]{0,140}'
            r'\b(?:gioi han|thoi han|thoi luong|ty le|muc luong|hinh thuc|so ngay)\b',statement)
            and not re.search(r'hoan toan hop phap|hop phap ve moi mat|toan bo[^.;?!]*hop phap',statement)
            for statement in statements)
    if (notice_only or limited_facet) and global_exit and not bounded:
        problems.append('CLAIM_LIMITED_FACET_AS_OVERALL_LEGALITY')
    legal_absence=re.search(r'\bkhong co(?:\s+bat ky)?(?:\s+dieu kien dac biet hoac)?\s+ngoai le\b[^.;?!]{0,110}\b(?:phap luat|bo luat|luat|nghi dinh)\b',q)
    if legal_absence and q not in form_source and not re.search(r'(?:khong|chua) the (?:ket luan|khang dinh)',q):
        problems.append('CLAIM_STATUTORY_ABSENCE_NOT_GROUNDED')
    if any(_conditional_consequence_lost(q,fold(' '.join((
            str(getattr(item,'ancestor_context','') or ''),
            str(getattr(item,'full_text',None) or getattr(item,'source_text',None) or item.text)))),
            fold(context_query)) for item in items):
        problems.append('CLAIM_CONDITIONAL_ANTECEDENT_LOST')
    # A duty to notify does not itself prove an advance-notification deadline.
    notification=re.search(r'\b(?:phai|can|co nghia vu)[^.;?!]{0,60}\bthong bao\b[^.;?!]{0,90}\btruoc khi\b',q)
    if notification and 'thong bao' in form_source:
        prefix=q[max(0,notification.start()-70):notification.start()]
        caution=re.search(r'(?:chua|khong) (?:co|du) can cu|khong the (?:ket luan|khang dinh)|\b(?:khong|chua)(?:\s+bat buoc)?\s*$',prefix)
        explicit_advance=re.search(r'thong bao truoc|bao truoc|truoc khi|truoc (?:it nhat|toi thieu|cham nhat)|truoc\s+\d+\s+ngay',form_source)
        if not caution and not explicit_advance:problems.append('CLAIM_NOTIFICATION_ADVANCE_NOT_GROUNDED')
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
        clause=str(getattr(item,'clause_number',None) or getattr(item,'clause',None) or '')
        single_act_source=any(
            (getattr(other,'original_instrument_number',None) or getattr(other,'document_number',None)
                or getattr(other,'instrument_number',None)) in {'45/2019/QH14','18/VBHN-VPQH'}
            and str(getattr(other,'article_number',None) or getattr(other,'article',None) or '')=='122'
            and str(getattr(other,'clause_number',None) or getattr(other,'clause',None) or '')=='2'
            for other in items)
        if number in {'45/2019/QH14','18/VBHN-VPQH'} and article=='122' and clause=='3' and not single_act_source and re.search(
            r'\b(?:mot hanh vi|cung mot hanh vi|cung hanh vi)\b',q):
            problems.append('CLAIM_DISCIPLINE_SINGLE_ACT_CITATION_MISMATCH')
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
