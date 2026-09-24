from __future__ import annotations
import re
from datetime import date
from .artifact_store import ArtifactStore
from .models import Evidence,Citation,Claim

def deterministic_audit(store:ArtifactStore,items:list[Evidence],query_date:str|None,allow_document_temporal_fallback:bool=False,query_date_end:str|None=None)->list[Evidence]:
    out=[]
    for item in items:
        issues=[]; warnings=list(item.audit_warnings); source=store.units_by_id.get(item.unit_id)
        if not source: issues.append('UNKNOWN_UNIT_ID')
        if item.document_id and item.document_id not in store.nodes_by_id: issues.append('UNKNOWN_DOCUMENT_NODE')
        if source and item.source_url!=(source.get('source_url') or None): issues.append('SOURCE_URL_NOT_FROM_UNIT')
        if item.kind in {'PROVISION','CASE'} and not item.source_url: issues.append('MISSING_SOURCE_URL')
        for field in ('document_id','document_number','article_number','clause_number','point_number','valid_from','valid_to'):
            if source and str(getattr(item,field) or '')!=str(source.get(field) or ''): issues.append('UNIT_FIELD_MISMATCH:'+field)
        provenance=(source or {}).get('provenance') or {}; file_id=provenance.get('file_id'); catalog=store.catalog_by_file_id.get(file_id)
        if not file_id or not catalog: issues.append('SOURCE_NOT_IN_CATALOG')
        elif catalog.get('source_url') and item.source_url!=catalog.get('source_url'): issues.append('SOURCE_URL_NOT_FROM_CATALOG')
        elif catalog.get('catalog_status')!='VERIFIED': warnings.append('SOURCE_CATALOG_RECORD_UNVERIFIED')
        if catalog and provenance.get('sha256') and catalog.get('sha256') and provenance['sha256']!=catalog['sha256']:
            issues.append('SOURCE_SHA_MISMATCH')
        span=(source or {}).get('provenance_span') or {}
        if source and item.provenance_span!=span: issues.append('SOURCE_SPAN_MISMATCH')
        if item.kind=='PROVISION' and not span: issues.append('MISSING_SOURCE_SPAN')
        if item.kind=='PROVISION' and span and not (
          span.get('char_start') is not None and span.get('char_end') is not None or
          span.get('line_start') is not None and span.get('line_end') is not None): issues.append('INCOMPLETE_SOURCE_SPAN')
        if span and span.get('char_start') is not None and span.get('char_end') is not None and span['char_end']<span['char_start']: issues.append('INVALID_SOURCE_SPAN')
        node=store.nodes_by_id.get(item.unit_id); props=(node or {}).get('properties') or {}
        for field in ('article_number','clause_number','point_number'):
            if source and str(source.get(field) or '')!=str(props.get(field) or ''): issues.append('GRAPH_STRUCTURE_MISMATCH:'+field)
        start=end=None; temporal_interval_valid=True
        try:
            start=date.fromisoformat(item.valid_from) if item.valid_from else None
            end=date.fromisoformat(item.valid_to) if item.valid_to else None
        except ValueError:
            issues.append('INVALID_TEMPORAL_INTERVAL'); temporal_interval_valid=False
        if (item.provision_temporal_verified or item.temporal_verified) and not start:
            issues.append('MISSING_VALID_FROM'); temporal_interval_valid=False
        if temporal_interval_valid and start and end and end<=start:
            issues.append('INVALID_TEMPORAL_INTERVAL'); temporal_interval_valid=False
        if query_date:
            if not item.provision_temporal_verified and not (allow_document_temporal_fallback and item.temporal_verified):
                issues.append('UNREVIEWED_PROVISION_INTERVAL')
            else:
                try:
                    range_start=date.fromisoformat(query_date); range_end=date.fromisoformat(query_date_end or query_date)
                except ValueError:
                    issues.append('INVALID_TEMPORAL_INTERVAL')
                else:
                    if range_end<range_start: issues.append('INVALID_TEMPORAL_INTERVAL')
                    if temporal_interval_valid and (not start or start>range_end or end and end<=range_start): issues.append('WRONG_VERSION')
                    else:
                        if temporal_interval_valid and range_start!=range_end and (start>range_start or end and end<=range_end): warnings.append('IMPRECISE_QUERY_DATE_OVERLAPS_VERSION_BOUNDARY')
                        if temporal_interval_valid and not item.provision_temporal_verified: warnings.append('DOCUMENT_LEVEL_TEMPORAL_FALLBACK')
        authority_verified=bool(catalog and catalog.get('catalog_status')=='VERIFIED' and item.official_source and item.source_url)
        out.append(item.model_copy(update={'verified':not issues,'authority_verified':authority_verified,
          'audit_issues':list(dict.fromkeys(issues)),'audit_warnings':list(dict.fromkeys(warnings))}))
    return out
ISSUE_TERMS={
    'TERMINATION':('chấm dứt','sa thải','thôi việc'),
    'WAGE':('tiền lương','lương','làm thêm'),
    'SOCIAL_INSURANCE':('bảo hiểm xã hội','bhxh'),
    'SAFETY':('an toàn lao động','tai nạn lao động'),
    'CONTRACT':('hợp đồng lao động',),
    'LEAVE':('nghỉ hằng năm','nghỉ hàng năm','nghỉ năm','phép năm','ngày nghỉ hằng năm'),
    'DISPUTE':('tranh chấp','tòa án'),
    'HARASSMENT':('quấy rối tình dục','quấy rối tại nơi làm việc'),
    'DISCIPLINE':('kỷ luật lao động','khiển trách','sa thải'),
    'MATERNITY':('thai sản','mang thai','nuôi con'),
    'WORKING_TIME':('thời giờ làm việc','giờ làm việc','nghỉ giữa giờ','làm ban đêm','làm thêm giờ'),
    'UNION':('công đoàn','đoàn phí'),
    'FOREIGN_WORKER':('lao động nước ngoài','giấy phép lao động'),
    'UNEMPLOYMENT_INSURANCE':('bảo hiểm thất nghiệp','trợ cấp thất nghiệp'),
}

def applicability(items:list[Evidence],query:str,issues:list[str]|None=None)->list[Evidence]:
    terms={x for x in re.findall(r'\w+',query.lower()) if len(x)>3}
    issue_terms=tuple(term for issue in (issues or []) if issue!='GENERAL' for term in ISSUE_TERMS.get(issue,()))
    result=[]
    for item in items:
        haystack=' '.join(x for x in (item.text,item.source_text,item.breadcrumb) if x).lower()
        overlap=len(terms.intersection(re.findall(r'\w+',haystack)))
        issue_match=not issue_terms or any(term in haystack for term in issue_terms)
        if item.retrieval_method.startswith('exact') or overlap and issue_match: result.append(item)
    return result
def citations(items:list[Evidence])->list[Citation]:
    return [Citation(evidence_id=x.unit_id,title=x.document_title,document_number=x.document_number,
      article=x.article_number,clause=x.clause_number,point=x.point_number,
      law_version=' → '.join(v for v in (x.valid_from,x.valid_to) if v) or None,official_url=x.source_url,
      instrument_number=x.document_number,source_span=x.provenance_span) for x in items]
def _norm_reference(value:str)->str:
    return re.sub(r'[^0-9A-ZĐ]','',value.upper())
def _claim_supported(text:str,evidence:Evidence)->bool:
    stop={'theo','được','của','và','hoặc','một','những','các','trong','tại','điều','khoản','điểm'}
    claim={x for x in re.findall(r'\w+',text.lower()) if len(x)>2 and x not in stop}
    source={x for x in re.findall(r'\w+',' '.join(y for y in (evidence.source_text,evidence.text,evidence.breadcrumb) if y).lower()) if len(x)>2 and x not in stop}
    return bool(claim) and len(claim&source)/len(claim)>=.35
def reference_audit(answer:str,items:list[Evidence],refs:list[Citation],claims:list[Claim]|None=None)->tuple[bool,list[str]]:
    ids={x.unit_id for x in items if x.verified}; problems=[]
    raw_markers=set(re.findall(r'\[([^\[\]]+)\]',answer))
    # Legal text may contain formulae in brackets. Treat only known evidence IDs
    # or ID-shaped labels as citation markers.
    markers={x for x in raw_markers if x in ids or re.fullmatch(r'(?i)(?:prov|case|diag|unit|article)[_ -][A-Za-z0-9_-]+',x)}
    if (refs or claims) and not markers: problems.append('ANSWER_HAS_NO_EVIDENCE_MARKERS')
    for marker in markers:
        if marker not in ids: problems.append('UNSUPPORTED_CITATION:'+marker)
    ref_ids={x.evidence_id for x in refs}
    if ref_ids-ids: problems.append('CITATION_NOT_VERIFIED')
    if ref_ids-markers: problems.append('CITATION_NOT_MARKED')
    by_id={e.unit_id:e for e in items}
    for ref in refs:
        item=by_id.get(ref.evidence_id)
        if not item: continue
        if ref.official_url!=item.source_url: problems.append('FABRICATED_URL')
        if (ref.document_number,ref.article,ref.clause,ref.point)!=(item.document_number,item.article_number,item.clause_number,item.point_number): problems.append('CITATION_STRUCTURE_MISMATCH')
        expected_version=' → '.join(v for v in (item.valid_from,item.valid_to) if v) or None
        if ref.law_version!=expected_version: problems.append('CITATION_VERSION_MISMATCH')
        if ref.source_span!=item.provenance_span: problems.append('CITATION_SOURCE_SPAN_MISMATCH')
    allowed_urls={x.source_url for x in items if x.source_url}
    for url in re.findall(r'https?://[^\s)\]>]+',answer):
        if url.rstrip('.,;') not in allowed_urls: problems.append('FABRICATED_URL_IN_ANSWER:'+url.rstrip('.,;'))
    evidence_text=' '.join(' '.join(y for y in (x.source_text,x.text,x.breadcrumb) if y) for x in items)
    allowed_numbers={_norm_reference(x.document_number) for x in items if x.document_number}
    for number in re.findall(r'\b\d{1,4}/\d{4}/[A-ZĐ0-9-]+\b',answer,re.I):
        if _norm_reference(number) not in allowed_numbers and _norm_reference(number) not in _norm_reference(evidence_text):
            problems.append('UNSUPPORTED_INSTRUMENT_REFERENCE:'+number)
    allowed_articles={str(x.article_number) for x in items if x.article_number}
    for article in re.findall(r'(?i)\bđiều\s+(\d+[a-z]?)\b',answer):
        if article not in allowed_articles and not re.search(rf'(?i)\bđiều\s+{re.escape(article)}\b',evidence_text):
            problems.append('UNSUPPORTED_ARTICLE_REFERENCE:'+article)
    allowed_clauses={str(x.clause_number).lower() for x in items if x.clause_number}
    for clause in re.findall(r'(?i)\bkhoản\s+(\d+[a-z]?)\b',answer):
        if clause.lower() not in allowed_clauses and not re.search(rf'(?i)\bkhoản\s+{re.escape(clause)}\b',evidence_text):
            problems.append('UNSUPPORTED_CLAUSE_REFERENCE:'+clause)
    allowed_points={str(x.point_number).lower() for x in items if x.point_number}
    for point in re.findall(r'(?i)\bđiểm\s+([a-zđ])\b',answer):
        if point.lower() not in allowed_points and not re.search(rf'(?i)\bđiểm\s+{re.escape(point)}\b',evidence_text):
            problems.append('UNSUPPORTED_POINT_REFERENCE:'+point)
    for claim in claims or []:
        if not claim.evidence_ids: problems.append('CLAIM_WITHOUT_EVIDENCE:'+claim.claim_id)
        elif set(claim.evidence_ids)-ids: problems.append('CLAIM_UNSUPPORTED:'+claim.claim_id)
        elif not any(_claim_supported(claim.text,by_id[evidence_id]) for evidence_id in claim.evidence_ids):
            problems.append('CLAIM_CONTENT_UNSUPPORTED:'+claim.claim_id)
    return not problems,list(dict.fromkeys(problems))
