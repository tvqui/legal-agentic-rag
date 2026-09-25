from __future__ import annotations
import calendar,hashlib,json,re,unicodedata
from datetime import date
from .models import QueryEnvelope,QueryAnalysis,ExplicitReference,Route,EvidencePlan,FactCandidate

ISSUES={"TERMINATION":["chấm dứt","sa thải","thôi việc","nghỉ việc","nghỉ chính thức","báo trước","cho tôi nghỉ","cho nghỉ việc","buộc nghỉ","đơn phương"],"WAGE":["tiền lương","lương","làm thêm"],
 "SOCIAL_INSURANCE":["bảo hiểm xã hội","bhxh"],"SAFETY":["an toàn lao động","tai nạn lao động"],
 "CONTRACT":["hợp đồng lao động"],"LEAVE":["nghỉ hằng năm","nghỉ hàng năm","nghỉ phép","phép năm"],
 "DISPUTE":["tranh chấp","tòa án"],"HARASSMENT":["quấy rối tình dục","quấy rối tại nơi làm việc"],
 "DISCIPLINE":["kỷ luật lao động","khiển trách","kéo dài thời hạn nâng lương"],
 "MATERNITY":["thai sản","mang thai","nuôi con dưới 12 tháng"],
 "WORKING_TIME":["thời giờ làm việc","giờ làm việc","nghỉ giữa giờ","làm ban đêm","làm thêm giờ"],
 "UNION":["công đoàn","đoàn phí"],"FOREIGN_WORKER":["lao động nước ngoài","giấy phép lao động"],
 "UNEMPLOYMENT_INSURANCE":["bảo hiểm thất nghiệp","trợ cấp thất nghiệp"]}
FACTS={"TERMINATION":{"termination_date":"Ngày chấm dứt là ngày nào?","contract_type":"Loại hợp đồng là gì?","termination_reason":"Lý do chấm dứt là gì?","notice_days":"Công ty đã báo trước bao nhiêu ngày?","protected_status":"Người lao động có đang mang thai, nghỉ thai sản, nuôi con nhỏ hoặc thuộc tình trạng được bảo vệ đặc biệt nào không?"},
 "WAGE":{"work_date":"Thời điểm phát sinh tiền lương là khi nào?"},
 "HARASSMENT":{"incident_date":"Sự việc xảy ra vào thời điểm nào?","workplace_context":"Sự việc xảy ra trong hoàn cảnh công việc nào?"},
 "DISCIPLINE":{"discipline_date":"Quyết định kỷ luật được ban hành khi nào?","discipline_form":"Hình thức kỷ luật là gì?"},
 "MATERNITY":{"event_date":"Sự việc xảy ra vào thời điểm nào?","protected_status":"Tình trạng mang thai, thai sản hoặc nuôi con của người lao động là gì?"}}
REF=re.compile(
    r'(?:(?:điểm)\s*(?P<point>[a-zđ])\s*)?'
    r'(?:(?:khoản)\s*(?P<clause>\d+[a-z]?)\s*)?'
    r'(?:điều)\s*(?P<article>\d+[a-z]?)'
    r'(?:\s+(?:của\s+)?'
    r'(?:(?:nghị\s+định|thông\s+tư|quyết\s+định|nghị\s+quyết|bộ\s+luật|luật)\s*(?:số\s*)?)?'
    r'(?P<instrument>\d{1,4}/\d{4}/[A-ZĐ0-9\-]+))?',
    re.I,
)
DATE=re.compile(r'\b(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b')
DATE_DMY=re.compile(r'\b(0?[1-9]|[12]\d|3[01])[-/](0?[1-9]|1[0-2])[-/](20\d{2})\b')
MONTH_WORD=re.compile(r'tháng\s*(0?[1-9]|1[0-2])(?:\s*năm\s*|\s*[/\-]\s*)(20\d{2})',re.I)
MONTH_SLASH=re.compile(r'(?<![\d/])(0?[1-9]|1[0-2])\s*[/\-]\s*(20\d{2})\b',re.I)
YEAR_WORD=re.compile(r'\bnăm\s*(20\d{2})\b',re.I)
NOTICE_DAYS=re.compile(r'(?:báo|thông báo)\s*trước(?:\s+cho\s+(?:tôi|người lao động))?\s*(\d+)\s*ngày',re.I)
WORKED_MONTHS=re.compile(r'làm\s+việc(?:\s+(?:đủ|được|trong))?\s*(\d+)\s*tháng',re.I)
NOTICE_DATE_DMY=re.compile(r'ngày\s*(0?[1-9]|[12]\d|3[01])[/\-](0?[1-9]|1[0-2])[/\-](20\d{2})[^.]{0,80}(?:gửi|nộp)\s+(?:thông báo|đơn)',re.I)
TERMINATION_DATE_DMY=re.compile(r'(?:nghỉ|chấm dứt)(?:\s+việc|\s+chính thức|\s+hợp đồng)*\s*(?:vào|từ)?\s*ngày\s*(0?[1-9]|[12]\d|3[01])[/\-](0?[1-9]|1[0-2])[/\-](20\d{2})',re.I)
def intake(question:str,context:list[str],explicit_date:str|None=None,facts:dict|None=None)->QueryEnvelope:
    normalized=' '.join(unicodedata.normalize('NFC',question).split())
    identity=json.dumps({'question':normalized,'context':context,'query_date':explicit_date,'facts':facts or {}},ensure_ascii=False,sort_keys=True,default=str)
    return QueryEnvelope(query_id='query_'+hashlib.sha256(identity.encode()).hexdigest()[:16],raw_query=question,normalized_query=normalized,conversation_context=context)
def analyze(env:QueryEnvelope,explicit_date:str|None=None,supplied_facts:dict|None=None)->QueryAnalysis:
    # Classify the current turn from the current question.  Previous assistant
    # answers can contain many unrelated legal topics and must never broaden a
    # fresh query into a multi-issue request.
    q=env.normalized_query; analysis_text=q; lower=q.lower(); refs=[]
    for m in REF.finditer(q):
        refs.append(ExplicitReference(instrument_number=m.group('instrument'),article=m.group('article'),clause=m.group('clause'),point=m.group('point')))
    dates=['-'.join((m.group(1),m.group(2).zfill(2),m.group(3).zfill(2))) for m in DATE.finditer(analysis_text)]
    dates+=['-'.join((m.group(3),m.group(2).zfill(2),m.group(1).zfill(2))) for m in DATE_DMY.finditer(analysis_text)]
    month_matches=[*MONTH_WORD.finditer(analysis_text),*MONTH_SLASH.finditer(analysis_text)]
    month_dates=list(dict.fromkeys(f'{m.group(2)}-{m.group(1).zfill(2)}' for m in month_matches))
    years=[m.group(1) for m in YEAR_WORD.finditer(analysis_text)]
    precision='DAY' if explicit_date or dates else 'MONTH' if month_dates else 'YEAR' if years else 'NONE'
    query_date=explicit_date or (dates[0] if dates else f'{month_dates[0]}-01' if month_dates else f'{years[0]}-01-01' if years else None)
    if precision=='MONTH':
        year,month=map(int,month_dates[0].split('-')); query_date_end=f'{year:04d}-{month:02d}-{calendar.monthrange(year,month)[1]:02d}'
    elif precision=='YEAR': query_date_end=f'{years[0]}-12-31'
    else: query_date_end=query_date
    imprecise_date=month_dates[0] if month_dates else years[0] if years else None
    facts=dict(supplied_facts or {})
    # Facts explicitly stated in the current turn override older confirmed state.
    extracted_facts=_extract_facts(lower,query_date,imprecise_date)
    facts.update(extracted_facts)
    fact_candidates=_deterministic_fact_candidates(q,extracted_facts)
    # For a planned termination, the applicable-date check belongs to the
    # termination date rather than the earlier notification date.
    if not explicit_date and facts.get('termination_date'):
        query_date=facts['termination_date']; query_date_end=query_date; precision='DAY'
    issues=[name for name,words in ISSUES.items() if any(w in lower for w in words)] or ['GENERAL']
    outcome='LOOKUP' if refs and any(w in lower for w in ('quy định gì','nội dung','tra cứu')) else 'FIND_CASE' if 'bản án' in lower or 'án lệ' in lower else 'COMPARE' if 'so sánh' in lower else 'ASSESS_LEGALITY' if any(w in lower for w in ('đúng luật','trái luật','có được','đúng quy định','có đúng','hậu quả pháp lý')) else 'EXPLAIN'
    historical=bool(query_date) and query_date<date.today().isoformat()
    temporal='HISTORICAL' if historical else 'EXPLICIT_DATE' if query_date else 'CURRENT' if any(w in lower for w in ('hiện nay','bây giờ','mới nhất')) else 'NONE'
    # A date constraint alone does not make a lookup or a single-issue question complex.
    # Complexity is driven by multiple legal issues or a request to reason across versions.
    complexity_issues=[issue for issue in issues if not (issue=='CONTRACT' and 'TERMINATION' in issues)]
    complex_query=len(complexity_issues)>1 or historical and outcome=='ASSESS_LEGALITY' or any(w in lower for w in ('sửa đổi','bãi bỏ','thay thế','so sánh','qua các thời kỳ'))
    exact_ref=any(ref.article for ref in refs)
    route=Route.DIRECT if exact_ref and outcome=='LOOKUP' else Route.COMPLEX if complex_query else Route.STANDARD
    missing=missing_fact_questions(issues,outcome,facts,lower,query_date)
    if route==Route.DIRECT and refs and all(not ref.instrument_number for ref in refs):
        missing.append('Bạn đang hỏi Điều/Khoản/Điểm của văn bản pháp luật nào?')
    return QueryAnalysis(legal_issues=issues,facts=facts,explicit_references=refs,event_dates=dates+month_dates+years,query_date=query_date,query_date_end=query_date_end,
      requested_outcome=outcome,temporal_intent=temporal,missing_facts=sorted(set(missing)),route=route,
      route_reason='explicit legal citation' if route==Route.DIRECT else 'multi-issue/temporal/change query' if route==Route.COMPLEX else 'single-issue query',query_date_precision=precision,fact_candidates=fact_candidates)

def _fact_candidate(field,value,query,match):
    start,end=match.span()
    return FactCandidate(field=field,value=value,source_quote=query[start:end],char_start=start,char_end=end,
      origin='DETERMINISTIC',verified=True)

def _needle_match(query,needles):
    for needle in needles:
        found=re.search(re.escape(needle),query,re.I)
        if found: return found
    return None

def _deterministic_fact_candidates(query:str,facts:dict)->list[FactCandidate]:
    """Attach exact current-turn spans to facts produced by deterministic parsing."""
    patterns={'notice_days':NOTICE_DAYS,'worked_months':WORKED_MONTHS,'notice_date':NOTICE_DATE_DMY,
      'termination_date':TERMINATION_DATE_DMY}
    needles={
      'contract_type':('không xác định thời hạn','xác định thời hạn','thử việc'),
      'protected_status':('mang thai','thai sản','nuôi con dưới 12 tháng'),
      'actor':('tôi gửi thông báo nghỉ','người lao động chấm dứt','công ty cho tôi nghỉ','người sử dụng lao động chấm dứt'),
      'notice_exception':('không thuộc trường hợp được nghỉ không cần báo trước','được nghỉ không cần báo trước'),
      'special_occupation':('không thuộc ngành nghề đặc thù','ngành, nghề, công việc đặc thù','ngành nghề đặc thù')}
    result=[]
    for field,value in facts.items():
        match=patterns[field].search(query) if field in patterns else _needle_match(query,needles.get(field,()))
        if match: result.append(_fact_candidate(field,value,query,match))
    return result

def missing_fact_questions(issues:list[str],outcome:str,facts:dict,query:str,query_date:str|None)->list[str]:
    missing=[]
    if outcome!='ASSESS_LEGALITY': return missing
    for issue in issues:
        required=FACTS.get(issue,{})
        if issue=='TERMINATION' and facts.get('actor')=='EMPLOYEE':
            required={'termination_date':'Ngày dự kiến nghỉ chính thức là ngày nào?',
              'contract_type':'Loại hợp đồng là gì?','notice_days':'Người lao động báo trước bao nhiêu ngày?',
              'notice_exception':'Người lao động có thuộc trường hợp được nghỉ không cần báo trước không?'}
        for field,prompt in required.items():
            if not _fact_present(field,query,query_date,facts): missing.append(prompt)
    return sorted(set(missing))

def _extract_facts(q:str,query_date:str|None,month_date:str|None)->dict:
    facts={}
    # query_date is the date on which the user wants the law evaluated.  It is
    # not necessarily a factual event date, so keep it in QueryAnalysis instead
    # of presenting it to users as a fact of their case.
    notice=NOTICE_DAYS.search(q)
    if notice: facts['notice_days']=int(notice.group(1))
    worked=WORKED_MONTHS.search(q)
    if worked: facts['worked_months']=int(worked.group(1))
    if 'không xác định thời hạn' in q: facts['contract_type']='INDEFINITE'
    elif 'xác định thời hạn' in q: facts['contract_type']='FIXED_TERM'
    elif 'thử việc' in q: facts['contract_type']='PROBATION'
    if any(x in q for x in ('mang thai','thai sản','nuôi con dưới 12 tháng')): facts['protected_status']='MATERNITY'
    notice_date=NOTICE_DATE_DMY.search(q)
    if notice_date: facts['notice_date']=f'{notice_date.group(3)}-{notice_date.group(2).zfill(2)}-{notice_date.group(1).zfill(2)}'
    termination_date=TERMINATION_DATE_DMY.search(q)
    if termination_date: facts['termination_date']=f'{termination_date.group(3)}-{termination_date.group(2).zfill(2)}-{termination_date.group(1).zfill(2)}'
    if re.search(r'\b(?:tôi|người lao động)\b[^.]{0,100}\b(?:nghỉ việc|chấm dứt hợp đồng|gửi thông báo nghỉ)',q): facts['actor']='EMPLOYEE'
    elif any(term in q for term in ('công ty cho tôi nghỉ','người sử dụng lao động chấm dứt','công ty chấm dứt')): facts['actor']='EMPLOYER'
    if any(term in q for term in ('không thuộc trường hợp được nghỉ không cần báo trước','không thuộc trường hợp không cần báo trước')):
        facts['notice_exception']=False
    elif any(term in q for term in ('được nghỉ không cần báo trước','được quyền nghỉ không cần báo trước')):
        facts['notice_exception']=True
    if any(term in q for term in ('không thuộc ngành nghề đặc thù','không thuộc ngành, nghề, công việc đặc thù')): facts['special_occupation']=False
    elif any(term in q for term in ('ngành nghề đặc thù','ngành, nghề, công việc đặc thù')): facts['special_occupation']=True
    return facts
def _fact_present(field:str,q:str,query_date:str|None,facts:dict)->bool:
    if field in facts:
        value=facts[field]
        if value in (None,''): return False
        if isinstance(value,str) and value.strip().upper() in {'UNKNOWN','UNVERIFIED','N/A','KHÔNG BIẾT','CHƯA RÕ'}: return False
        return True
    if field.endswith('date'): return bool(query_date or DATE.search(q))
    if field=='contract_type': return any(w in q for w in ('xác định thời hạn','không xác định thời hạn','thử việc'))
    if field=='termination_reason': return any(w in q for w in ('vì','do ','lý do'))
    if field=='workplace_context': return any(w in q for w in ('nơi làm việc','công ty','cơ quan','trong công việc'))
    if field=='protected_status': return any(w in q for w in ('mang thai','thai sản','nuôi con'))
    if field=='discipline_form': return any(w in q for w in ('khiển trách','sa thải','kỷ luật','nâng lương','cách chức'))
    if field=='notice_exception': return 'notice_exception' in facts
    return False
def evidence_slots(analysis:QueryAnalysis)->list[str]:
    return plan_evidence(analysis).mandatory_slots
def plan_evidence(analysis:QueryAnalysis)->EvidencePlan:
    mandatory=['governing_rule','official_source']
    conditional=['implementing_regulation','amendment_history','case_law']
    if analysis.query_date or analysis.temporal_intent=='CURRENT': mandatory.append('applicable_version')
    if 'TERMINATION' in analysis.legal_issues:
        mandatory+=['termination_conditions','notice_requirement','exceptions']
        if analysis.facts.get('actor')=='EMPLOYEE' and analysis.requested_outcome=='ASSESS_LEGALITY':
            mandatory+=['legal_classification','legal_consequences']
    elif 'LEAVE' in analysis.legal_issues:
        mandatory+=['conditions','exceptions']
    elif analysis.requested_outcome=='ASSESS_LEGALITY': mandatory+=['conditions','exceptions']
    if analysis.route==Route.COMPLEX: mandatory.append('mandatory_reference')
    return EvidencePlan(mandatory_slots=list(dict.fromkeys(mandatory)),conditional_slots=conditional)
