from __future__ import annotations
import calendar,hashlib,json,re,unicodedata
from datetime import date
from .temporal import legal_regime_for
from .taxonomy import classify_subissues,parent_issues,plan_with_profiles,profile_fact_questions
from .models import QueryEnvelope,QueryAnalysis,ExplicitReference,Route,EvidencePlan,FactCandidate

ISSUES={"TERMINATION":["chấm dứt","sa thải","thôi việc","nghỉ việc","nghỉ ngay","nghỉ sau","nghỉ chính thức","báo trước","cho tôi nghỉ","cho nghỉ việc","buộc nghỉ","đơn phương","trợ cấp mất việc","hết hạn hợp đồng","hợp đồng hết hạn","thay đổi cơ cấu","thay đổi công nghệ","lý do kinh tế","tái cơ cấu","cắt giảm nhân sự","sáp nhập"],"WAGE":["tiền lương","lương","làm thêm"],
 "SOCIAL_INSURANCE":["bảo hiểm xã hội","bhxh"],"SAFETY":["an toàn lao động","tai nạn lao động"],
 "CONTRACT":["hợp đồng lao động","giao kết hợp đồng"],"LEAVE":["nghỉ hằng năm","nghỉ hàng năm","nghỉ phép","phép năm","ngày phép","thâm niên làm việc","ngày thâm niên","ngày cơ bản","thời gian đi đường","nghỉ lễ","ngày lễ","nghỉ tết","quốc khánh","giỗ tổ","nghỉ việc riêng","nghỉ không hưởng lương","nghỉ không lương","kết hôn","đám cưới","cha mất","mẹ mất","bố mất"],
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
NOTICE_DAYS=re.compile(
    r'(?:(?:báo|thông báo)\s*trước(?:\s+cho\s+(?:tôi|người lao động))?|(?:muốn|dự định|sẽ)?\s*nghỉ(?:\s+\w+){0,2}\s+sau)\s*(\d+)\s*ngày',
    re.I)
NO_NOTICE=re.compile(r'\b(?:không|chưa)\s+(?:hề\s+)?(?:báo|thông báo)\s*trước(?:\s+\d+\s*ngày)?|\bnghỉ\s+ngay\b',re.I)
WORKED_MONTHS=re.compile(r'làm(?:\s+việc)?[^.]{0,50}?(\d+)\s*tháng',re.I)
SERVICE_YEARS=re.compile(r'(?:(?:đã\s+)?làm(?:\s+việc)?(?:\s+liên\s+tục)?(?:\s+cho\s+(?:cùng\s+)?(?:công\s+ty(?:\s+này)?|người\s+sử\s+dụng\s+lao\s+động))?\s*(?:được\s*)?(\d+)\s*năm|năm\s+thứ\s+(\d+))',re.I)
AGE=re.compile(r'(?<!\d)(\d{1,2})\s*tuổi',re.I)
TRAVEL_DAYS=re.compile(r'(?:tổng\s+)?thời\s+gian\s+đi\s+và\s+về\s+(?:là\s+)?(\d+)\s*ngày',re.I)
NOTICE_DATE_DMY=re.compile(r'ngày\s*(0?[1-9]|[12]\d|3[01])[/\-](0?[1-9]|1[0-2])[/\-](20\d{2})[^.]{0,80}(?:gửi|nộp)\s+(?:thông báo|đơn)',re.I)
TERMINATION_DATE_DMY=re.compile(r'(?:nghỉ|chấm dứt)(?:\s+việc|\s+chính thức|\s+hợp đồng)*\s*(?:vào|từ|là)?\s*(?:ngày\s*)?(0?[1-9]|[12]\d|3[01])[/\-](0?[1-9]|1[0-2])[/\-](20\d{2})',re.I)
CONTRACT_START_YEAR=re.compile(r'(?:ký|giao kết|bắt đầu)\s+(?:hợp đồng[^.]{0,50}?|làm việc[^.]{0,30}?)(?:từ\s+)?năm\s*(20\d{2})',re.I)
OUT_OF_SCOPE_TERMS=('hình sự','tội phạm','giết người','ma túy','đất đai','bất động sản','ly hôn','hôn nhân gia đình','thuế doanh nghiệp')
CRIMINAL_QUESTION_TERMS=('báo công an','khởi tố','truy cứu','phạm tội','tội gì','mức án','phạt tù','cấu thành tội','cố ý gây thương tích','trộm cắp')
LAND_QUESTION_TERMS=('quyền sử dụng đất','giấy chứng nhận quyền sử dụng đất','cấp giấy chứng nhận','tranh chấp đất','thửa đất')
LABOR_SCOPE_TERMS=('lao động','người lao động','người sử dụng lao động','hợp đồng','tiền lương','nghỉ việc','bảo hiểm xã hội','công đoàn','thai sản')
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
    issues=[name for name,words in ISSUES.items() if any(w in lower and not (name=='TERMINATION' and w=='nghỉ việc' and 'nghỉ việc riêng' in lower and not re.search(r'nghỉ việc(?!\s+riêng)',lower)) for w in words)] or ['GENERAL']
    subissues=classify_subissues(q,facts,issues)
    issues=parent_issues(issues,subissues)
    outcome='LOOKUP' if refs and any(w in lower for w in ('quy định gì','nội dung','tra cứu')) else 'FIND_CASE' if 'bản án' in lower or 'án lệ' in lower else 'COMPARE' if any(term in lower for term in ('so sánh','phân biệt','khác nhau')) else 'ASSESS_LEGALITY' if any(w in lower for w in ('đúng luật','trái luật','trái pháp luật','có được','có quyền','đúng quy định','có đúng','đúng không','hậu quả pháp lý','đánh giá yêu cầu','phải bồi thường bao nhiêu','bồi thường bao nhiêu','có phải báo trước','phải báo trước không')) else 'EXPLAIN'
    historical=legal_regime_for(query_date)=='BLLD_2012' if query_date else False
    temporal='HISTORICAL' if historical else 'EXPLICIT_DATE' if query_date else 'CURRENT' if any(w in lower for w in ('hiện nay','bây giờ','mới nhất')) else 'NONE'
    # A date constraint alone does not make a lookup or a single-issue question complex.
    # Complexity is driven by multiple legal issues or a request to reason across versions.
    complexity_issues=[issue for issue in issues if not (issue=='CONTRACT' and 'TERMINATION' in issues)]
    # A date in the previous legal regime is handled by temporal filtering. It
    # does not by itself turn a single issue into a cross-version graph query.
    complex_query=len(complexity_issues)>1 or any(w in lower for w in ('sửa đổi','bãi bỏ','thay thế','so sánh','phân biệt','khác nhau','qua các thời kỳ'))
    exact_ref=any(ref.article for ref in refs)
    route=Route.DIRECT if exact_ref and outcome=='LOOKUP' else Route.COMPLEX if complex_query else Route.STANDARD
    missing=missing_fact_questions(issues,outcome,facts,lower,query_date)
    if route==Route.DIRECT and refs and all(not ref.instrument_number for ref in refs):
        missing.append('Bạn đang hỏi Điều/Khoản/Điểm của văn bản pháp luật nào?')
    return QueryAnalysis(legal_issues=issues,legal_subissues=subissues,facts=facts,explicit_references=refs,event_dates=dates+month_dates+years,query_date=query_date,query_date_end=query_date_end,
      requested_outcome=outcome,temporal_intent=temporal,missing_facts=sorted(set(missing)),route=route,
      route_reason='explicit legal citation' if route==Route.DIRECT else 'multi-issue/change query' if route==Route.COMPLEX else 'single-issue query',query_date_precision=precision,fact_candidates=fact_candidates,
      in_scope=not _clearly_out_of_scope(lower,issues,refs))

def _clearly_out_of_scope(query:str,issues:list[str],refs:list[ExplicitReference])->bool:
    if refs: return False
    # The requested legal conclusion controls scope.  Incidental words such as
    # "công ty", "đồng nghiệp" or "giờ làm việc" must not turn a criminal or
    # land-law question into a labour-law question.
    if any(term in query for term in CRIMINAL_QUESTION_TERMS+LAND_QUESTION_TERMS): return True
    return any(term in query for term in OUT_OF_SCOPE_TERMS) and not any(term in query for term in LABOR_SCOPE_TERMS)

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
    patterns={'worked_months':WORKED_MONTHS,'service_years':SERVICE_YEARS,
      'age':AGE,'travel_days':TRAVEL_DAYS,'notice_date':NOTICE_DATE_DMY,
      'termination_date':TERMINATION_DATE_DMY,'contract_start_year':CONTRACT_START_YEAR}
    needles={
      'contract_type':('không xác định thời hạn','xác định thời hạn','thử việc'),
      'protected_status':('mang thai','thai sản','nuôi con dưới 12 tháng'),
      'actor':('tôi gửi thông báo nghỉ','tôi chỉ báo trước','tôi báo trước','tôi muốn nghỉ','người lao động chấm dứt','người lao động đơn phương','công ty đơn phương','người sử dụng lao động đơn phương','công ty cho tôi nghỉ','người sử dụng lao động chấm dứt'),
      'notice_exception':('không thuộc trường hợp được nghỉ không cần báo trước','được nghỉ không cần báo trước'),
      'special_occupation':('không thuộc ngành nghề đặc thù','không thuộc ngành, nghề, công việc đặc thù',
        'không làm ngành nghề đặc thù','không làm ngành, nghề, công việc đặc thù','không làm công việc đặc thù',
        'ngành, nghề, công việc đặc thù','ngành nghề đặc thù'),
      'termination_basis':('trả lương không đúng thời hạn','trả lương chậm','trả lương trễ','quấy rối tình dục','cung cấp sai thông tin','cung cấp thông tin không trung thực'),
      'mutual_termination_agreement':('đồng ý cho','hai bên thỏa thuận','công ty đồng ý'),
      'work_category':('đặc biệt nặng nhọc','nặng nhọc','điều kiện bình thường','công việc văn phòng'),
      'disabled':('người khuyết tật','khuyết tật'),
      'training_costs':('không có chi phí đào tạo','có chi phí đào tạo','chi phí đào tạo')}
    result=[]
    for field,value in facts.items():
        if field=='notice_days':
            match=NO_NOTICE.search(query) if value==0 else NOTICE_DAYS.search(query)
        else:
            match=patterns[field].search(query) if field in patterns else _needle_match(query,needles.get(field,()))
        if match: result.append(_fact_candidate(field,value,query,match))
    return result

def missing_fact_questions(issues:list[str],outcome:str,facts:dict,query:str,query_date:str|None)->list[str]:
    missing=[]
    if 'LEAVE' in issues and facts.get('query_intent')=='ANNUAL_LEAVE_CALC':
        if not isinstance(facts.get('worked_months'),int):
            missing.append('Trong năm đang xét, người lao động đã làm việc thực tế bao nhiêu tháng?')
        if not facts.get('work_category') and not facts.get('minor') and not facts.get('disabled'):
            missing.append('Công việc thuộc điều kiện bình thường, nặng nhọc/độc hại/nguy hiểm hay đặc biệt nặng nhọc/độc hại/nguy hiểm; người lao động có chưa thành niên hoặc khuyết tật không?')
    if outcome!='ASSESS_LEGALITY': return sorted(set(missing))
    subissues=classify_subissues(query,facts,issues)
    alternate={'TERMINATION.EXPIRY','TERMINATION.DISMISSAL','TERMINATION.ECONOMIC_RESTRUCTURING',
      'TERMINATION.ENTERPRISE_TRANSFER','TERMINATION.SEVERANCE','TERMINATION.JOB_LOSS_ALLOWANCE'}
    unilateral={'TERMINATION.EMPLOYEE_UNILATERAL','TERMINATION.EMPLOYER_UNILATERAL'}
    if alternate.intersection(subissues) and not unilateral.intersection(subissues):
        return sorted(set(missing+profile_fact_questions(subissues,facts,query_date)))
    if facts.get('query_intent') in {'UNLAWFUL_DEFINITION_CONSEQUENCES','WITHDRAW_TERMINATION','MUTUAL_TERMINATION'}:
        return sorted(set(missing))
    if 'TERMINATION' in issues and facts.get('actor')=='EMPLOYEE':
        basis=facts.get('termination_basis')
        if facts.get('mutual_termination_agreement') is True: return sorted(set(missing))
        if basis=='LATE_WAGE':
            if facts.get('force_majeure_exception') is None:
                missing.append('Việc trả lương chậm có do bất khả kháng, sau khi người sử dụng lao động đã tìm mọi biện pháp khắc phục, và có nằm trong giới hạn khoản 4 Điều 97 không?')
            return sorted(set(missing))
        if basis in {'SEXUAL_HARASSMENT','EMPLOYER_MISINFORMATION'}: return sorted(set(missing))
        required={'contract_type':'Loại hợp đồng là gì?',
          'notice_days':'Người lao động đã báo trước bao nhiêu ngày?',
          'notice_exception':'Lý do nghỉ có thuộc một trường hợp được chấm dứt không cần báo trước tại khoản 2 Điều 35 không?',
          'special_occupation':'Công việc có thuộc ngành, nghề hoặc công việc đặc thù theo Điều 7 Nghị định 145/2020/NĐ-CP không?'}
        for field,prompt in required.items():
            if not _fact_present(field,query,query_date,facts): missing.append(prompt)
        if any(term in query for term in ('bao nhiêu tiền','tính tiền','mức bồi thường')) and facts.get('monthly_salary') is None:
            missing.append('Mức tiền lương theo hợp đồng dùng để tính bồi thường là bao nhiêu?')
        if any(term in query for term in ('bao nhiêu tiền','tính tiền','mức bồi thường')) and facts.get('training_costs') is None:
            missing.append('Có chi phí đào tạo phải hoàn trả theo Điều 62 hay không; nếu có thì số tiền và thỏa thuận đào tạo là gì?')
    else:
        for issue in issues:
            for field,prompt in FACTS.get(issue,{}).items():
                if not _fact_present(field,query,query_date,facts): missing.append(prompt)
    return sorted(set(missing))

def _extract_facts(q:str,query_date:str|None,month_date:str|None)->dict:
    facts={}
    # query_date is the date on which the user wants the law evaluated.  It is
    # not necessarily a factual event date, so keep it in QueryAnalysis instead
    # of presenting it to users as a fact of their case.
    no_notice=NO_NOTICE.search(q)
    notice=NOTICE_DAYS.search(q)
    if no_notice: facts['notice_days']=0
    elif notice: facts['notice_days']=int(notice.group(1))
    worked=WORKED_MONTHS.search(q)
    if worked: facts['worked_months']=int(worked.group(1))
    service=SERVICE_YEARS.search(q)
    if service: facts['service_years']=int(service.group(1) or service.group(2))
    age=AGE.search(q)
    if age:
        facts['age']=int(age.group(1)); facts['minor']=int(age.group(1))<18
    travel=TRAVEL_DAYS.search(q)
    if travel: facts['travel_days']=int(travel.group(1))
    if 'đặc biệt nặng nhọc' in q: facts['work_category']='SPECIAL_HEAVY'
    elif any(term in q for term in ('nặng nhọc, độc hại, nguy hiểm','nghề nặng nhọc','công việc nặng nhọc')): facts['work_category']='HEAVY'
    elif any(term in q for term in ('điều kiện bình thường','công việc bình thường','nhân viên văn phòng','công việc văn phòng')): facts['work_category']='NORMAL'
    if 'khuyết tật' in q: facts['disabled']=True
    if 'không xác định thời hạn' in q: facts['contract_type']='INDEFINITE'
    elif 'xác định thời hạn' in q: facts['contract_type']='FIXED_TERM'
    elif 'thử việc' in q: facts['contract_type']='PROBATION'
    if any(x in q for x in ('mang thai','thai sản','nuôi con dưới 12 tháng')): facts['protected_status']='MATERNITY'
    notice_date=NOTICE_DATE_DMY.search(q)
    if notice_date: facts['notice_date']=f'{notice_date.group(3)}-{notice_date.group(2).zfill(2)}-{notice_date.group(1).zfill(2)}'
    termination_date=TERMINATION_DATE_DMY.search(q)
    if termination_date: facts['termination_date']=f'{termination_date.group(3)}-{termination_date.group(2).zfill(2)}-{termination_date.group(1).zfill(2)}'
    contract_start=CONTRACT_START_YEAR.search(q)
    if contract_start: facts['contract_start_year']=int(contract_start.group(1))
    if any(term in q for term in ('công ty cho tôi nghỉ','người sử dụng lao động chấm dứt','công ty chấm dứt','công ty đơn phương','người sử dụng lao động đơn phương','tôi bị công ty cho nghỉ','công ty sa thải')): facts['actor']='EMPLOYER'
    elif (re.search(r'\b(?:tôi|người lao động)\b[^.]{0,160}\b(?:nghỉ việc|chấm dứt hợp đồng|gửi thông báo nghỉ|muốn nghỉ|dự định nghỉ|sẽ nghỉ|(?:chỉ\s+)?báo trước)',q)
      or any(term in q for term in ('người lao động đơn phương','gửi thông báo đơn phương nghỉ','gửi thông báo','gửi email chấm dứt','gửi đơn chỉ báo trước','báo trước 1 ngày rồi nghỉ','báo trước 30 ngày'))): facts['actor']='EMPLOYEE'
    if any(term in q for term in ('không thuộc trường hợp được nghỉ không cần báo trước','không thuộc trường hợp không cần báo trước','không có bất kỳ tình tiết nào thuộc trường hợp được nghỉ không cần báo trước')):
        facts['notice_exception']=False
    elif any(term in q for term in ('được nghỉ không cần báo trước','được quyền nghỉ không cần báo trước')):
        facts['notice_exception']=True
    if any(term in q for term in ('không thuộc ngành nghề đặc thù','không thuộc ngành, nghề, công việc đặc thù','không thuộc công việc đặc thù',
      'không làm ngành nghề đặc thù','không làm ngành, nghề, công việc đặc thù','không làm công việc đặc thù')): facts['special_occupation']=False
    elif any(term in q for term in ('ngành nghề đặc thù','ngành, nghề, công việc đặc thù')): facts['special_occupation']=True
    if any(term in q for term in ('không có chi phí đào tạo','không phải hoàn trả chi phí đào tạo')): facts['training_costs']=False
    elif any(term in q for term in ('có chi phí đào tạo','phải hoàn trả chi phí đào tạo')): facts['training_costs']=True
    if any(term in q for term in ('trả lương không đúng thời hạn','trả lương chậm','trả lương trễ','trả lương cho tôi trễ')):
        facts['termination_basis']='LATE_WAGE'
        if any(term in q for term in ('không có sự kiện bất khả kháng','không có lý do bất khả kháng','không có sự kiện bất khả kháng hay lý do thuộc trường hợp ngoại lệ')):
            facts['force_majeure_exception']=False; facts['notice_exception']=True
    if 'quấy rối tình dục tại nơi làm việc' in q:
        facts['termination_basis']='SEXUAL_HARASSMENT'; facts['notice_exception']=True; facts['actor']='EMPLOYEE'
    if any(term in q for term in ('cung cấp sai thông tin','cung cấp thông tin không trung thực','cung cấp khi giao kết là không trung thực')) and any(term in q for term in ('giao kết','ảnh hưởng trực tiếp','không thể thực hiện công việc')):
        facts['termination_basis']='EMPLOYER_MISINFORMATION'; facts['notice_exception']=True; facts['actor']='EMPLOYEE'
    if any(term in q for term in ('công ty đồng ý cho','giám đốc trả lời bằng văn bản rằng công ty đồng ý','hai bên thỏa thuận chấm dứt')):
        facts['mutual_termination_agreement']=True
    if any(term in q for term in ('hủy bỏ việc đơn phương','đổi ý trước khi hết thời hạn báo trước')): facts['query_intent']='WITHDRAW_TERMINATION'
    elif 'trái pháp luật' in q and 'nghĩa vụ' in q and ('hai điều luật khác nhau' in q or 'định nghĩa' in q): facts['query_intent']='UNLAWFUL_DEFINITION_CONSEQUENCES'
    elif facts.get('mutual_termination_agreement'): facts['query_intent']='MUTUAL_TERMINATION'
    elif 'thời gian đi và về' in q or 'thời gian đi đường' in q: facts['query_intent']='TRAVEL_TIME'
    elif (any(term in q for term in ('bao nhiêu ngày nghỉ','bao nhiêu ngày phép','bao nhiêu ngày','số ngày nghỉ hằng năm','tính quyền nghỉ','tính:','cách tính này')) or bool(re.search(r'\b\d+\s+ngày\b',q)) and any(term in q for term in ('có đúng','đúng không','có được'))) and any(term in q for term in ('nghỉ hằng năm','nghỉ hàng năm','nghỉ phép','phép năm','ngày phép','thâm niên','ngày cơ bản')):
        specific=bool(facts.get('service_years') or facts.get('work_category') or facts.get('minor') or facts.get('disabled') or re.search(r'\b(?:tôi|[a-e])\b',q))
        facts['query_intent']='ANNUAL_LEAVE_CALC' if specific else 'ANNUAL_LEAVE_OVERVIEW'
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
    return plan_with_profiles(analysis,_legacy_plan_evidence(analysis))

def _legacy_plan_evidence(analysis:QueryAnalysis)->EvidencePlan:
    mandatory=['governing_rule','official_source']
    conditional=['implementing_regulation','amendment_history','case_law']
    if analysis.query_date or analysis.temporal_intent=='CURRENT': mandatory.append('applicable_version')
    if 'TERMINATION' in analysis.legal_issues:
        intent=analysis.facts.get('query_intent'); basis=analysis.facts.get('termination_basis')
        if intent=='WITHDRAW_TERMINATION': mandatory+=['termination_conditions','withdrawal_rule']
        elif intent=='UNLAWFUL_DEFINITION_CONSEQUENCES': mandatory+=['legal_classification','legal_consequences']
        elif intent=='MUTUAL_TERMINATION': mandatory+=['agreement_rule']
        elif basis=='LATE_WAGE': mandatory+=['termination_conditions','notice_requirement','exception_rule','wage_delay_reference']
        elif basis=='EMPLOYER_MISINFORMATION': mandatory+=['termination_conditions','notice_requirement','exception_rule','disclosure_reference']
        elif basis=='SEXUAL_HARASSMENT': mandatory+=['termination_conditions','notice_requirement','exception_rule']
        else: mandatory+=['termination_conditions','notice_requirement','exceptions']
        if analysis.facts.get('actor')=='EMPLOYEE' and analysis.requested_outcome=='ASSESS_LEGALITY':
            threshold=120 if analysis.facts.get('special_occupation') is True else 45
            if analysis.facts.get('notice_exception') is False and isinstance(analysis.facts.get('notice_days'),int) and analysis.facts['notice_days']<threshold:
                mandatory+=['legal_classification','legal_consequences']
    if 'LEAVE' in analysis.legal_issues:
        mandatory+=['conditions','exceptions']
        intent=analysis.facts.get('query_intent')
        if intent=='TRAVEL_TIME': mandatory+=['travel_time_rule']
        elif intent=='ANNUAL_LEAVE_CALC':
            mandatory+=['leave_base_rule']
            if int(analysis.facts.get('service_years') or 0)>=5: mandatory+=['seniority_rule']
            if isinstance(analysis.facts.get('worked_months'),int) and analysis.facts['worked_months']<12: mandatory+=['proportional_leave_rule','leave_calculation_rule']
    elif analysis.requested_outcome=='ASSESS_LEGALITY': mandatory+=['conditions','exceptions']
    if analysis.route==Route.COMPLEX and not analysis.facts.get('termination_basis') and not analysis.facts.get('query_intent'):
        mandatory.append('mandatory_reference')
    return EvidencePlan(mandatory_slots=list(dict.fromkeys(mandatory)),conditional_slots=conditional)
