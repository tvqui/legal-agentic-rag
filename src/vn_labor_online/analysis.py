from __future__ import annotations
import calendar,hashlib,json,re,unicodedata
from datetime import date
from .temporal import legal_regime_for
from .taxonomy import classify_subissues,parent_issues,plan_with_profiles,profile_fact_questions,original_documents,relationship_comparison,affirmative_phrase,annual_leave_combination_only
from .taxonomy import probation_cancellation_only,unused_leave_settlement_only
from .query_clock import relative_date_ranges
from .termination_context import explicit_employer_action,protection_clause,stipulated_liability_actor,settlement_deadline_only
from .models import QueryEnvelope,QueryAnalysis,ExplicitReference,Route,EvidencePlan,FactCandidate
from .topics import TOPICS,detect_topics
from .tasks import deterministic_tasks
from .numeric_answers import parse_salary_base,requests_probation_amount,conflicting_salary_bases

ISSUES={"TERMINATION":["chấm dứt","sa thải","thôi việc","nghỉ việc","xin nghỉ","nghỉ ngay","nghỉ sau","nghỉ chính thức","báo trước","cho tôi nghỉ","cho nghỉ việc","cho người lao động nghỉ","buộc nghỉ","đơn phương","trợ cấp mất việc","hết hạn hợp đồng","hợp đồng hết hạn","thay đổi cơ cấu","thay đổi công nghệ","lý do kinh tế","tái cơ cấu","cắt giảm nhân sự","sáp nhập"],"WAGE":["tiền lương","lương"],
 "SOCIAL_INSURANCE":["bảo hiểm xã hội","bhxh"],"SAFETY":["an toàn lao động","tai nạn lao động"],
 "CONTRACT":["hợp đồng lao động","hđlđ","giao kết hợp đồng","thử việc","hợp đồng cộng tác viên"],"LEAVE":["nghỉ tối thiểu","nghỉ 12","nghỉ hằng năm","nghỉ hàng năm","nghỉ phép","phép năm","ngày phép","thâm niên làm việc","ngày thâm niên","ngày cơ bản","thời gian đi đường","nghỉ lễ","ngày lễ","nghỉ tết","quốc khánh","giỗ tổ","nghỉ việc riêng","nghỉ không hưởng lương","nghỉ không lương","kết hôn","đám cưới","cha mất","mẹ mất","bố mất"],
 "DISPUTE":["tranh chấp","tòa án"],"HARASSMENT":["quấy rối tình dục","quấy rối tại nơi làm việc"],
 "DISCIPLINE":["kỷ luật lao động","khiển trách","kéo dài thời hạn nâng lương"],
 "MATERNITY":["thai sản","mang thai","nuôi con dưới 12 tháng"],
 "WORKING_TIME":["thời giờ làm việc","giờ làm việc","nghỉ giữa giờ","làm ban đêm","làm thêm giờ"],
 "UNION":["công đoàn","đoàn phí"],"FOREIGN_WORKER":["lao động nước ngoài","giấy phép lao động"],
 "UNEMPLOYMENT_INSURANCE":["bảo hiểm thất nghiệp","trợ cấp thất nghiệp"],
 "TRAINING":["học nghề","tập nghề","đào tạo","thực tập"],
 "MINOR_WORKER":["lao động chưa thành niên","người chưa đủ 18 tuổi","nlđ chưa thành niên"],
 "RETIREMENT":["nghỉ hưu","tuổi hưu","cao tuổi"], "OVERSEAS_WORKER":["đi làm việc ở nước ngoài"],
 "COLLECTIVE_RELATIONS":["thương lượng tập thể","thỏa ước lao động","đình công","đối thoại tại nơi làm việc"]}
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
DATE=re.compile(r'\b((?:19|20|21)\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b')
DATE_DMY=re.compile(r'\b(\d{1,2})[-/.](\d{1,2})[-/.]((?:19|20|21)\d{2})\b')
MONTH_WORD=re.compile(r'tháng\s*(0?[1-9]|1[0-2])(?:\s*năm\s*|\s*[/\-]\s*)((?:19|20|21)\d{2})',re.I)
MONTH_SLASH=re.compile(r'(?<![\d/])(0?[1-9]|1[0-2])\s*[/\-]\s*((?:19|20|21)\d{2})\b',re.I)
YEAR_WORD=re.compile(r'\bnăm\s*((?:19|20|21)\d{2})\b',re.I)
NOTICE_DAYS=re.compile(
    r'(?:(?:báo|thông báo)\s*trước(?:\s+cho\s+(?:tôi|người lao động))?|(?:muốn|dự định|sẽ)?\s*nghỉ(?:\s+\w+){0,2}\s+sau)\s*(\d+)\s*ngày',
    re.I)
CONTRACT_TERM=re.compile(r'\bhợp đồng(?:\s+lao động)?[^.;?!]{0,80}?(?P<duration>\d+)\s*tháng\b',re.I)
NO_NOTICE=re.compile(r'\b(?:không|chưa)\s+(?:hề\s+)?(?:báo|thông báo)\s*trước(?:\s+\d+\s*ngày)?|\bnghỉ\s+ngay\b',re.I)
MONTH_NUMBER_WORDS={'một':1,'hai':2,'ba':3,'bốn':4,'năm':5,'sáu':6,'bảy':7,'tám':8,'chín':9,'mười':10,'mười một':11,'mười hai':12}
WORKED_MONTHS=re.compile(r'làm(?:\s+việc)?[^.;?!]{0,50}?(\d+|mười hai|mười một|mười|một|hai|ba|bốn|năm|sáu|bảy|tám|chín)\s*tháng',re.I)
_YEAR_NUMBER=r'\d+|mười hai|mười một|mười|một|hai|ba|bốn|năm|sáu|bảy|tám|chín'
_SERVICE_EMPLOYER=r'(?:công\s+ty(?:\s+này)?|doanh\s+nghiệp(?:\s+này)?|người\s+sử\s+dụng\s+lao\s+động|nsdlđ)'
SERVICE_YEARS=re.compile(
    rf'(?:(?:đã\s+)?làm(?:\s+việc)?(?:\s+liên\s+tục)?'
    rf'(?:\s+(?:cho\s+(?:cùng\s+)?|cùng\s+){_SERVICE_EMPLOYER})?'
    rf'\s*(?:được\s+|đủ\s+)*(?P<count>{_YEAR_NUMBER})\s+năm\b'
    rf'|\bthâm\s+niên\s*(?:là\s+|đủ\s+|được\s+)*(?P<tenure>{_YEAR_NUMBER})\s+năm\b'
    rf'|\bnăm\s+thứ\s+(?P<ordinal>{_YEAR_NUMBER})\b)',re.I)


def _service_duration(query):
    """Return completed whole service years and their actual source span.

    Being in year N establishes N-1 completed years, not N. Approximate or
    negated durations cannot become exact calculation operands.
    """
    for match in SERVICE_YEARS.finditer(query):
        prefix=query[max(0,match.start()-45):match.start()]
        if re.search(r'\b(?:chưa|không)(?:\s+(?:hề|từng|đủ|được|có)){0,3}\s*$',prefix,re.I):
            continue
        value=next(value for value in match.groups() if value is not None).lower()
        years=int(value) if value.isdigit() else MONTH_NUMBER_WORDS[value]
        if match.group('ordinal') is not None: years-=1
        if years>=0: return years,match
    return None,None
AGE=re.compile(r'(?<!\d)(\d{1,2})\s*tuổi',re.I)
TRAVEL_DAYS=re.compile(r'(?:tổng\s+)?thời\s+gian\s+đi\s+và\s+về\s+(?:là\s+)?(\d+)\s*ngày',re.I)
NOTICE_DATE_DMY=re.compile(r'ngày\s*(0?[1-9]|[12]\d|3[01])[/\-](0?[1-9]|1[0-2])[/\-](20\d{2})[^.]{0,80}(?:gửi|nộp)\s+(?:thông báo|đơn)',re.I)
TERMINATION_DATE_DMY=re.compile(r'(?:nghỉ|chấm dứt)(?:\s+việc|\s+chính thức|\s+hợp đồng)*\s*(?:vào|từ|là)?\s*(?:ngày\s*)?(0?[1-9]|[12]\d|3[01])[/\-](0?[1-9]|1[0-2])[/\-](20\d{2})',re.I)
CONTRACT_START_YEAR=re.compile(r'(?:ký|giao kết|bắt đầu)\s+(?:hợp đồng[^.]{0,50}?|làm việc[^.]{0,30}?)(?:từ\s+)?năm\s*(20\d{2})',re.I)
OUT_OF_SCOPE_TERMS=('hình sự','tội phạm','giết người','ma túy','đất đai','bất động sản','ly hôn','hôn nhân gia đình','thuế doanh nghiệp','thừa kế','bộ luật dân sự')
CRIMINAL_QUESTION_TERMS=('báo công an','khởi tố','truy cứu','phạm tội','tội gì','mức án','phạt tù','cấu thành tội','cố ý gây thương tích','trộm cắp')
LAND_QUESTION_TERMS=('quyền sử dụng đất','giấy chứng nhận quyền sử dụng đất','cấp giấy chứng nhận','tranh chấp đất','thửa đất')
LABOR_SCOPE_TERMS=('lao động','người lao động','người sử dụng lao động','hợp đồng','tiền lương','lương','nghỉ việc','nghỉ làm','thử việc','tăng ca','làm thêm','bảo hiểm xã hội','công đoàn','thai sản')
ENGLISH_QUESTION_TERMS=('how','what','when','where','why','who','can','could','do','does','is','are','should','please')
ENGLISH_LABOR_TERMS=('labor','labour','employee','employer','employment','job','salary','wage',
  'contract','termination','resign','quit','notice period','overtime','probation','workplace')
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
    invalid_dates=[];valid_dates=[]
    for value in dates:
        try:valid_dates.append(date.fromisoformat(value).isoformat())
        except ValueError:invalid_dates.append(value)
    dates=valid_dates
    month_matches=[*MONTH_WORD.finditer(analysis_text),*MONTH_SLASH.finditer(analysis_text)]
    month_dates=list(dict.fromkeys(f'{m.group(2)}-{m.group(1).zfill(2)}' for m in month_matches))
    years=[m.group(1) for m in YEAR_WORD.finditer(analysis_text)]
    precision='DAY' if explicit_date or dates else 'MONTH' if month_dates else 'YEAR' if years else 'NONE'
    query_date=explicit_date or (dates[0] if dates else f'{month_dates[0]}-01' if month_dates else f'{years[0]}-01-01' if years else None)
    if precision=='MONTH':
        year,month=map(int,month_dates[0].split('-')); query_date_end=f'{year:04d}-{month:02d}-{calendar.monthrange(year,month)[1]:02d}'
    elif precision=='YEAR': query_date_end=f'{years[0]}-12-31'
    else: query_date_end=query_date
    relative=relative_date_ranges(q)
    temporal_ambiguous=bool(invalid_dates)
    if not explicit_date and not dates and not month_dates and not years and relative:
        if len(relative)==1:
            query_date,query_date_end,precision=relative[0]
        else:
            query_date=query_date_end=None
            temporal_ambiguous=True
    if (not explicit_date and not dates and not month_dates and not years and not relative
            and re.search(r'cách đây|vừa rồi|trước tết|sau tết|hồi trước',lower)):
        temporal_ambiguous=True
    imprecise_date=month_dates[0] if month_dates else years[0] if years else None
    facts=dict(supplied_facts or {})
    # Facts explicitly stated in the current turn override older confirmed state.
    extracted_facts=_extract_facts(lower,query_date,imprecise_date)
    for field in ('notice_date','termination_date'):
        value=extracted_facts.get(field)
        if value:
            try:date.fromisoformat(value)
            except ValueError:
                extracted_facts.pop(field);facts.pop(field,None);temporal_ambiguous=True
    facts.update(extracted_facts)
    fact_candidates=_deterministic_fact_candidates(q,extracted_facts)
    if (not explicit_date and not dates and not month_dates and len(relative)==1
            and years and facts.get('contract_start_year') and
            set(years)=={str(facts['contract_start_year'])}):
        query_date,query_date_end,precision=relative[0]
    if (not explicit_date and not dates and not month_dates and not relative
            and years and facts.get('contract_start_year')
            and set(years)=={str(facts['contract_start_year'])}
            and any(term in lower for term in ('muốn nghỉ','muốn đơn phương','dự định nghỉ','sắp nghỉ','báo trước bao lâu'))):
        # Signing a contract in an earlier year is background, not the date of
        # a newly proposed resignation. Let the request-day default apply.
        query_date=query_date_end=None;precision='NONE'
    # For a planned termination, the applicable-date check belongs to the
    # termination date rather than the earlier notification date.
    if not explicit_date and facts.get('termination_date'):
        query_date=facts['termination_date']; query_date_end=query_date; precision='DAY'
    from .event_time import resolve_event_dates
    dated_events,event_date,event_ambiguous=resolve_event_dates(q,explicit_date)
    if not explicit_date and event_ambiguous:
        query_date=query_date_end=None;precision='NONE';temporal_ambiguous=True
    elif not explicit_date and event_date:
        query_date=query_date_end=event_date;precision='DAY'
    elif not explicit_date and dated_events and all(e['role']=='CONTRACT_SIGNED_AT' for e in dated_events):
        if re.search(r'muốn nghỉ|dự định nghỉ|sắp nghỉ|bây giờ|hiện nay',lower):
            query_date=query_date_end=None;precision='NONE'
        elif re.search(r'sa thải|đơn phương chấm dứt|đã nghỉ việc',lower):
            query_date=query_date_end=None;precision='NONE';temporal_ambiguous=True
    elif not explicit_date and dated_events and all(e['role'] in {'BIRTH_DATE','SOURCE_PROMULGATED_AT'} for e in dated_events):
        query_date=query_date_end=None;precision='NONE'
    issues=[name for name,words in ISSUES.items() if any(w in lower and not (name=='TERMINATION' and w=='nghỉ việc' and 'nghỉ việc riêng' in lower and not re.search(r'nghỉ việc(?!\s+riêng)',lower)) for w in words)] or ['GENERAL']
    if 'nghỉ' in lower and re.search(r'\b(?:cha|mẹ|bố|vợ|chồng|con)(?:\s+(?:đẻ|nuôi|ruột|tôi|của|vợ|chồng)){0,4}\s+(?:chết|mất|qua đời)',lower):
        issues=[key for key in issues if key!='GENERAL']+(['LEAVE'] if 'LEAVE' not in issues else [])
    topics=detect_topics(q)
    issues=list(dict.fromkeys([item for item in issues if item!='GENERAL']+[topic.issue for topic in topics])) or ['GENERAL']
    if ('job_transfer' in {topic.key for topic in topics}
            and not any(term in lower for term in ('nghỉ việc','chấm dứt','đơn phương','xin nghỉ','sa thải'))):
        # Notice about temporary reassignment is not resignation notice.
        issues=[issue for issue in issues if issue!='TERMINATION']
        topics=[topic for topic in topics if topic.issue!='TERMINATION']
    if 'occupational_accident' in {topic.key for topic in topics} and not any(topic.issue=='WORKING_TIME' for topic in topics):
        issues=[issue for issue in issues if issue!='WORKING_TIME']
    unemployment_framework=('unemployment' in {topic.key for topic in topics}
        and facts.get('actor') is None
        and not re.search(r'\b(?:tôi|của tôi|trường hợp của|anh [a-z]|chị [a-z])\b',lower)
        and any(term in lower for term in ('chỉ cần','chắc chắn','bất kể','có luôn','mọi người','tất cả')))
    if unemployment_framework:
        # Departure is background to a benefits-policy question, not a request
        # to adjudicate an employer's termination of a specific worker.
        issues=[issue for issue in issues if issue!='TERMINATION']
        topics=[topic for topic in topics if topic.issue!='TERMINATION']
    subissues=classify_subissues(q,facts,issues)
    # A retention deadline is not a request to assess an employee's resignation.
    if original_documents(lower) and not re.search(r'(?:tôi|người lao động|nlđ)\s+(?:muốn|xin|sẽ|đơn phương|chỉ báo|báo trước)|thời hạn báo trước|hậu quả.*(?:nghỉ|chấm dứt)',lower):
        issues=[issue for issue in issues if issue!='TERMINATION']
        subissues=classify_subissues(q,facts,issues)
    issues=parent_issues(issues,subissues)
    if 'CONTRACT.PROBATION_CANCELLATION' in subissues and probation_cancellation_only(q):
        issues=[issue for issue in issues if issue!='TERMINATION']
        topics=[topic for topic in topics if topic.issue!='TERMINATION']
    termination_compensation_question='TERMINATION' in issues and any(
      term in lower for term in ('bồi thường','đền bù','hoàn trả chi phí')) and any(
      term in lower for term in ('có phải','phải trả','có trách nhiệm','chịu trách nhiệm'))
    outcome='LOOKUP' if refs and any(w in lower for w in ('quy định gì','nội dung','tra cứu')) else 'FIND_CASE' if 'bản án' in lower or 'án lệ' in lower else 'COMPARE' if any(term in lower for term in ('so sánh','phân biệt','khác nhau')) else 'ASSESS_LEGALITY' if termination_compensation_question or any(w in lower for w in ('đúng luật','trái luật','trái pháp luật','có hợp pháp','có được','có quyền','đúng quy định','có đúng','đúng không','hậu quả pháp lý','đánh giá yêu cầu','phải bồi thường','có phải bồi thường','bồi thường bao nhiêu','có phải báo trước','phải báo trước không')) else 'EXPLAIN'
    if re.search(r'^(?:khi nào|thế nào là|định nghĩa|khái niệm|trường hợp nào)',lower):
        outcome='EXPLAIN'
    framework=re.search(r'(?:kiểm tra|đối chiếu|kết hợp)[^.?!]{0,120}(?:quy định|điều luật|điều khoản|mốc thời gian|điều kiện|thủ tục)[^.?!]{0,100}(?:nào|ra sao|như thế nào)\s*[?!.]*$',lower)
    concrete_verdict=any(term in lower for term in ('có hợp pháp','có đúng luật','có đúng quy định',
        'đúng hay sai','phải bồi thường bao nhiêu','tôi có được','tôi có quyền'))
    if framework and not concrete_verdict: outcome='EXPLAIN'
    if re.search(r'(?:áp dụng|xử lý)[^.?!]{0,100}(?:giống|như)[^.?!]{0,100}(?:không|hay không)\s*[?!.]*$',lower):
        outcome='COMPARE'
    if annual_leave_combination_only(lower): outcome='EXPLAIN'
    if unemployment_framework: outcome='EXPLAIN'
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
    if temporal_ambiguous:
        missing.append('Mốc thời gian trong câu hỏi chưa xác định rõ hoặc không hợp lệ. Bạn muốn áp dụng quy định tại ngày hoặc khoảng thời gian nào?')
    if route==Route.DIRECT and refs and all(not ref.instrument_number for ref in refs):
        missing.append('Bạn đang hỏi Điều/Khoản/Điểm của văn bản pháp luật nào?')
    result=QueryAnalysis(query_text=env.normalized_query,legal_issues=issues,legal_subissues=subissues,facts=facts,explicit_references=refs,event_dates=dates+month_dates+years,query_date=query_date,query_date_end=query_date_end,
      requested_outcome=outcome,temporal_intent=temporal,missing_facts=sorted(set(missing)),route=route,
      route_reason='explicit legal citation' if route==Route.DIRECT else 'multi-issue/change query' if route==Route.COMPLEX else 'single-issue query',query_date_precision=precision,fact_candidates=fact_candidates,
      in_scope=not _clearly_out_of_scope(lower,issues,refs),
      temporal_resolution='AMBIGUOUS' if temporal_ambiguous else 'RESOLVED' if query_date else 'UNSPECIFIED')
    from .taxonomy import SUBISSUES
    result.routing_topics=[topic.key for topic in topics]
    result.temporal_events=dated_events
    result.query_received_at=env.received_at.isoformat()
    result.answer_tasks=deterministic_tasks(q,subissues,topics,SUBISSUES,route,outcome)
    return result

def _clearly_out_of_scope(query:str,issues:list[str],refs:list[ExplicitReference])->bool:
    # The requested legal conclusion controls scope.  Incidental words such as
    # "công ty", "đồng nghiệp" or "giờ làm việc" must not turn a criminal or
    # land-law question into a labour-law question.
    if any(term in query for term in LAND_QUESTION_TERMS): return True
    criminal_conclusion=bool(re.search(r'mức án|cấu thành tội|phạt\s+(?:(?:bao nhiêu|mấy)\s+năm\s+)?tù|(?:có(?:\s+(?:thể|bị|được|phải)){0,2}|thủ tục)\s+(?:khởi tố|truy cứu)',query))
    labour_conclusion=any(term in query for term in ('kỷ luật lao động','cuộc họp kỷ luật','xử lý kỷ luật','quyền của người lao động','sa thải'))
    foreign_instrument=any(term in query for term in ('bộ luật hình sự','bộ luật dân sự','luật đất đai','luật hôn nhân và gia đình','91/2015/qh13','100/2015/qh13','31/2024/qh15'))
    specific_labour=labour_conclusion or any(term in query for term in LABOR_SCOPE_TERMS if term!='hợp đồng')
    if foreign_instrument and not specific_labour:return True
    if any(term in query for term in CRIMINAL_QUESTION_TERMS) and (criminal_conclusion or not labour_conclusion): return True
    # Vietnamese "do" is a causal connective, not the English auxiliary.
    # Require an English question signal rather than one ambiguous token.
    english_question=(bool(re.search(r'\b(?:how|what|when|where|why|who|does|should|please)\b',query,re.I))
        or bool(re.match(r'^\s*(?:do|can|could|is|are)\s+(?:i|you|we|he|she|they|the|a|an|it)\b',query,re.I)))
    if english_question and not any(
      term in query for term in ENGLISH_LABOR_TERMS+LABOR_SCOPE_TERMS): return True
    if any(term in query for term in OUT_OF_SCOPE_TERMS) and not labour_conclusion and not any(term in query for term in LABOR_SCOPE_TERMS):return True
    # An unqualified labour-code lookup can still pass; the presence of a
    # locator never overrides a clearly identified non-labour legal conclusion.
    return False

def _fact_candidate(field,value,query,match):
    start,end=match.span()
    return FactCandidate(field=field,value=value,source_quote=query[start:end],char_start=start,char_end=end,
      origin='DETERMINISTIC',verified=True)

def _needle_match(query,needles):
    for needle in needles:
        found=re.search(re.escape(needle),query,re.I)
        if found: return found
    return None

SPECIAL_OCCUPATION = re.compile(
    r'\b(?P<negative>không\s+(?:(?:phải\s+)?(?:thuộc|làm)|phải)'
    r'(?:\s+(?:trong|nhóm|các|những)){0,3}\s+)?'
    r'(?:ngành|nghề|công\s+việc)'
    r'(?:(?:\s*[,/]\s*(?:(?:hoặc|hay|và)\s+)?|\s+(?:hoặc|hay|và)\s+|\s+)'
    r'(?:ngành|nghề|công\s+việc)){0,2}\s+đặc\s+thù\b', re.I)


def _special_occupation_fact(query):
    """Read an explicit category statement and retain its complete negation."""
    for match in SPECIAL_OCCUPATION.finditer(query):
        prefix=re.split(r'[.;?!\n]',query[:match.start()])[-1]
        suffix=re.split(r'[.;!\n]',query[match.end():],maxsplit=1)[0]
        if re.search(r'\b(?:không\s+(?:biết|rõ)|chưa\s+(?:biết|rõ)|chưa\s+xác\s+định|'
                     r'không\s+chắc|chưa\s+chắc|nếu|giả\s+sử|giả\s+định)\b',prefix,re.I):
            continue
        if '?' in suffix and (re.search(r'\bcó\s+(?:phải\s+)?(?:thuộc|làm)\b',prefix,re.I)
                              or re.match(r'\s*[,;]?\s*(?:phải|đúng)\s+không\s*\?',suffix,re.I)):
            continue
        return not bool(match.group('negative')),match
    return None,None


def _deterministic_fact_candidates(query:str,facts:dict)->list[FactCandidate]:
    """Attach exact current-turn spans to facts produced by deterministic parsing."""
    patterns={'worked_months':WORKED_MONTHS,
      'age':AGE,'travel_days':TRAVEL_DAYS,'notice_date':NOTICE_DATE_DMY,
      'termination_date':TERMINATION_DATE_DMY,'contract_start_year':CONTRACT_START_YEAR,
      'contract_duration_months':CONTRACT_TERM}
    needles={
      'contract_type':('không xác định thời hạn','xác định thời hạn','thử việc'),
      'protected_status':('mang thai','thai sản','nuôi con dưới 12 tháng'),
      'actor':('tôi gửi thông báo nghỉ','tôi chỉ báo trước','tôi báo trước','tôi muốn nghỉ','tôi chủ động xin nghỉ','tôi xin nghỉ','chủ động xin nghỉ','người lao động xin nghỉ','người lao động chấm dứt','người lao động đơn phương','công ty chủ động chấm dứt','công ty đơn phương','công ty muốn đơn phương','người sử dụng lao động đơn phương','người sử dụng lao động muốn đơn phương','công ty cho tôi nghỉ','người sử dụng lao động chấm dứt'),
      'notice_exception':('không thuộc trường hợp được nghỉ không cần báo trước',
        'không thuộc trường hợp được miễn báo trước','được nghỉ không cần báo trước','được miễn báo trước'),
      'special_occupation':('không thuộc ngành nghề đặc thù','không thuộc ngành, nghề, công việc đặc thù',
        'không làm ngành nghề đặc thù','không làm ngành, nghề, công việc đặc thù','không làm công việc đặc thù',
        'ngành, nghề, công việc đặc thù','ngành nghề đặc thù'),
      'termination_basis':('trả lương không đúng thời hạn','trả lương chậm','trả lương trễ','không trả lương đúng hạn','không được trả lương đúng hạn','không trả đủ lương','không được trả đủ lương','đánh đập','nhục mạ','ngược đãi','cưỡng bức lao động','không bố trí đúng công việc','không được bố trí đúng công việc','quấy rối tình dục','cung cấp sai thông tin','cung cấp thông tin không trung thực'),
      'work_reassignment_exception':('không thuộc trường hợp điều chuyển','không thuộc điều 29'),
      'mutual_termination_agreement':('đồng ý cho','hai bên thỏa thuận','công ty đồng ý'),
      'work_category':('đặc biệt nặng nhọc','nặng nhọc','điều kiện bình thường','công việc văn phòng'),
      'disabled':('người khuyết tật','khuyết tật'),
      'minor':('chưa thành niên','chưa đủ 18 tuổi'),
      'employment_paid_work':('nhận lương cố định','làm việc có trả công','làm công việc có trả công'),
      'employment_management':('chịu KPI','chịu sự quản lý','chịu sự điều hành','được quản lý như nhân viên'),
      'probation_work_group':('công việc quản lý doanh nghiệp','công việc của người quản lý doanh nghiệp','thuộc diện người quản lý doanh nghiệp','cần trình độ cao đẳng','yêu cầu trình độ cao đẳng','đòi hỏi trình độ cao đẳng','cần trình độ trung cấp','yêu cầu trình độ trung cấp','đòi hỏi trình độ trung cấp','công nhân kỹ thuật','nhân viên nghiệp vụ','công việc khác','công việc phổ thông','công việc không yêu cầu trình độ'),
      'training_costs':('không có chi phí đào tạo','có chi phí đào tạo','chi phí đào tạo'),
      'misinformation_material_effect':('ảnh hưởng trực tiếp đến việc thực hiện hđlđ','ảnh hưởng đến việc thực hiện hđlđ','ảnh hưởng trực tiếp đến việc thực hiện hợp đồng','ảnh hưởng tới thực hiện hợp đồng')}
    result=[]
    salary_base=parse_salary_base(query)
    if salary_base:
        for field,value in (('salary_base_amount',salary_base.amount),('salary_base_unit',salary_base.unit)):
            result.append(FactCandidate(field=field,value=value,source_quote=salary_base.source_quote,
                char_start=salary_base.char_start,char_end=salary_base.char_end,
                origin='DETERMINISTIC',verified=True))
    for field,value in facts.items():
        if field=='service_years':
            _,match=_service_duration(query)
        elif field=='notice_days':
            match=NO_NOTICE.search(query) if value==0 else NOTICE_DAYS.search(query)
        elif field=='special_occupation':
            extracted,match=_special_occupation_fact(query)
            if extracted is not value: match=None
        elif field=='contract_type' and value=='FIXED_TERM' and 'xác định thời hạn' not in query.lower():
            match=CONTRACT_TERM.search(query)
        elif field=='mutual_termination_agreement' and value is False:
            match=re.search(r'\b(?:chưa|không|chẳng)(?:\s+(?:hề|có|được|từng|phải|hai|bên)){0,4}\s+(?:đồng ý|thỏa thuận|thoả thuận)[^.;?!]{0,45}',query,re.I)
        else:
            match=patterns[field].search(query) if field in patterns else _needle_match(query,needles.get(field,()))
        if match: result.append(_fact_candidate(field,value,query,match))
    return result

def missing_fact_questions(issues:list[str],outcome:str,facts:dict,query:str,query_date:str|None)->list[str]:
    missing=[]
    subissues=classify_subissues(query,facts,issues)
    if 'LEAVE' in issues and facts.get('query_intent')=='ANNUAL_LEAVE_CALC' and 'LEAVE.ANNUAL_LEAVE' in subissues:
        if not isinstance(facts.get('worked_months'),int) and not annual_leave_combination_only(query):
            missing.append('Trong năm đang xét, người lao động đã làm việc thực tế bao nhiêu tháng?')
        if not facts.get('work_category') and not facts.get('minor') and not facts.get('disabled'):
            missing.append('Công việc thuộc điều kiện bình thường, nặng nhọc/độc hại/nguy hiểm hay đặc biệt nặng nhọc/độc hại/nguy hiểm; người lao động có chưa thành niên hoặc khuyết tật không?')
    # A personal oral-contract assessment depends on its term. A generic
    # explanation of available forms can instead present both legal branches.
    oral=affirmative_phrase(query,('thỏa thuận miệng','hợp đồng miệng','bằng lời nói'))
    duration_words=r'(?:\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)(?:\s+(?:mươi|mười|một|hai|ba|bốn|năm|lăm|sáu|bảy|tám|chín)){0,2}'
    stated_term=bool(re.search(r'(?:hợp đồng|thời hạn)[^.;?!]{0,60}?'+duration_words+r'\s*(?:ngày|tuần|tháng|năm)\b',query,re.I))
    personal=bool(re.search(r'\b(?:tôi|chúng tôi|trường hợp của)\b',query,re.I))
    if personal and 'WAGE.OVERTIME_PAY' in subissues and any(day in query for day in ('thứ bảy','thứ 7','chủ nhật')) and not any(
        term in query for term in ('ngày nghỉ hằng tuần','ngày nghỉ hàng tuần','ngày làm việc bình thường','ngày lễ','lịch nghỉ của tôi')):
        missing.append('Ngày đó là ngày làm việc bình thường, ngày nghỉ hằng tuần theo lịch của bạn, hay ngày lễ?')
    if personal and 'WORKING_TIME.OVERTIME_LIMITS' in subissues and re.search(r'chưa (?:rõ|biết)|không (?:rõ|biết)',query):
        missing.append('Số giờ làm bình thường và làm thêm trong ngày, tháng, năm là bao nhiêu; bạn đã đồng ý và có thuộc trường hợp đặc biệt không?')
    if personal and outcome=='ASSESS_LEGALITY' and 'job_transfer' in {topic.key for topic in detect_topics(query)}:
        if not facts.get('transfer_reason') and not any(term in query for term in ('thiên tai','hỏa hoạn','hoả hoạn','dịch bệnh','nhu cầu sản xuất','nhu cầu kinh doanh')):
            missing.append('Lý do tạm chuyển công việc là gì; nếu do nhu cầu sản xuất, kinh doanh thì nội quy có quy định trường hợp đó không?')
        if facts.get('transfer_total_days') is None and not any(term in query for term in ('cộng dồn','tổng số ngày trong năm')):
            missing.append('Tổng số ngày làm việc bị tạm chuyển cộng dồn trong năm là bao nhiêu?')
        if facts.get('transfer_notice_days') is None and not re.search(r'báo trước\s+\d+\s+ngày',query):
            missing.append('Công ty báo trước bao nhiêu ngày làm việc và đã thông báo thời hạn tạm chuyển chưa?')
        if not facts.get('transfer_pay') and not any(term in query for term in ('giữ nguyên lương','giữ nguyên mức lương','tiền lương công việc mới','lương công việc mới')):
            missing.append('Công việc mới có phù hợp sức khỏe và tiền lương khi tạm chuyển được bảo đảm thế nào?')
    money=bool(re.search(r'\d[\d.,]*\s*(?:triệu|nghìn|đồng|vnd)',query,re.I))
    if personal and money and 'lương tối thiểu' in query:
        if not re.search(r'\bvùng\s*(?:IV|III|II|I|[1-4])\b',query,re.I) and not facts.get('wage_region'):
            missing.append('Nơi làm việc cụ thể hoặc vùng lương tối thiểu áp dụng là ở đâu?')
        if not any(term in query for term in ('lương theo công việc','lương chức danh','lương của công việc','trước khấu trừ','lương gross')):
            missing.append('Khoản đã nêu là lương theo công việc/chức danh trước khấu trừ, tổng thu nhập gồm phụ cấp, hay tiền thực nhận?')
        if not any(term in query for term in ('đủ thời giờ','đủ giờ','toàn thời gian','full-time','fulltime')):
            missing.append('Bạn có làm đủ thời giờ bình thường và hoàn thành công việc, hay đang làm không trọn thời gian?')
    if (personal and money and 'CONTRACT.PROBATION_PAY' in subissues
            and facts.get('salary_base_amount') is None
            and not re.search(r'\d+\s*%|phần trăm',query)):
        missing.append('Mức lương của chính công việc đó khi làm chính thức là bao nhiêu, theo cùng kỳ trả lương?')
    if personal and 'CONTRACT.PROBATION_DURATION' in subissues and facts.get('probation_work_group') is None:
        missing.append('Công việc thuộc nhóm quản lý doanh nghiệp, cần trình độ từ cao đẳng, trung cấp/công nhân kỹ thuật/nhân viên nghiệp vụ, hay công việc khác?')
    if personal and not facts.get('contract_type') and 'TERMINATION.EMPLOYEE_UNILATERAL' in subissues and re.search(r'báo trước[^.;?!]{0,35}(?:bao nhiêu|bao lâu|mấy ngày)',query,re.I):
        if not facts.get('contract_type'):missing.append('Loại hợp đồng và thời hạn hợp đồng của bạn là gì?')
        if facts.get('special_occupation') is None:missing.append('Công việc có thuộc ngành, nghề hoặc công việc đặc thù không?')
        if facts.get('notice_exception') is None and facts.get('termination_basis') is None:
            missing.append('Bạn nghỉ vì lý do gì; có thuộc trường hợp được nghỉ không cần báo trước không?')
    if ('CONTRACT.FORM' in subissues and oral and personal and not stated_term
            and facts.get('contract_duration_months') is None and not facts.get('contract_type')):
        missing.append('Hợp đồng được thỏa thuận trong bao lâu, hay không xác định thời hạn?')
    if 'CONTRACT.PROBATION_PAY' in subissues and requests_probation_amount(query):
        if conflicting_salary_bases(query):
            missing.append('Bạn đã nêu các mức lương công việc khác nhau. Mức nào và đơn vị thời gian nào áp dụng cho lần thử việc đang hỏi?')
        elif re.search(r'bao nhiêu\s+(?:tiền|đồng)|số tiền|tính tiền thử việc',query,re.I) and (
            facts.get('salary_base_amount') is None or facts.get('salary_base_unit') not in {'tháng','ngày','giờ'}):
            missing.append('Mức lương của công việc dùng làm căn cứ tính lương thử việc là bao nhiêu đồng và theo tháng, ngày hay giờ?')
    employee_basis_terms=(
        'tôi nghỉ việc','người lao động nghỉ việc','nghỉ không báo trước',
        'chi phí đào tạo','thỏa thuận đào tạo','thoả thuận đào tạo',
        'hợp đồng đào tạo','vi phạm nghĩa vụ','gây thiệt hại',
    )
    if ('TERMINATION.EMPLOYEE_LIABILITY' in subissues
        and facts.get('actor')=='EMPLOYER'
        and facts.get('termination_basis') is None
        and facts.get('training_costs') is None
        and not any(term in query.lower() for term in employee_basis_terms)):
        missing.append('Công ty dựa trên hành vi hoặc nghĩa vụ cụ thể nào của người lao động để yêu cầu bồi thường?')
        return sorted(set(missing))
    independent_wage=any(term in query for term in ('lương tối thiểu','trả lương chậm','trả lương trễ',
        'đòi lương','tính lương','tính tiền lương'))
    if 'TRAINING.INTERN_PAY' not in subissues and outcome!='ASSESS_LEGALITY': return sorted(set(missing))
    handled_termination=(bool(protection_clause(query,facts)) or settlement_deadline_only(query)
        or 'LEAVE.UNUSED_LEAVE_PAYMENT' in subissues and unused_leave_settlement_only(query)
        or facts.get('query_intent') in {'STIPULATED_EMPLOYEE_LIABILITY','STIPULATED_EMPLOYER_LIABILITY'})
    if 'TRAINING.INTERN_PAY' in subissues and not (facts.get('employment_paid_work') and facts.get('employment_management')):
        return sorted(set(missing+['Bạn thực tập theo chương trình của trường, học/tập nghề để làm việc cho công ty, thử việc, hay đang làm việc có trả công và chịu sự quản lý của công ty?']))
    contract_parents={'CONTRACT','WAGE','GENERAL'}
    if 'CONTRACT.PROBATION_CANCELLATION' in subissues:contract_parents.add('TERMINATION')
    if subissues and all(key.startswith('CONTRACT.') for key in subissues) and set(issues)<=contract_parents and not independent_wage:
        return sorted(set(missing))
    if facts.get('query_intent') in {'STIPULATED_EMPLOYEE_LIABILITY','STIPULATED_EMPLOYER_LIABILITY'}:
        # A hypothetical premise is not a finding about a real dispute.
        if any(term in query for term in ('bao nhiêu tiền','tính số tiền','tính tiền cụ thể')) and facts.get('monthly_salary') is None:
            missing.append('Mức tiền lương theo hợp đồng dùng để tính bồi thường là bao nhiêu?')
    if 'WAGE.OVERTIME_PAY' in subissues and not ('TERMINATION' in issues or 'MATERNITY' in issues):
        # Explain mandatory remuneration, not an amount for an unstated event.
        if not any(term in query for term in ('tính số tiền','bao nhiêu tiền','tính tiền cụ thể')):
            return sorted(set(missing))
    alternate={'TERMINATION.EXPIRY','TERMINATION.DISMISSAL','TERMINATION.ECONOMIC_RESTRUCTURING',
      'TERMINATION.ENTERPRISE_TRANSFER','TERMINATION.SEVERANCE','TERMINATION.JOB_LOSS_ALLOWANCE'}
    unilateral={'TERMINATION.EMPLOYEE_UNILATERAL','TERMINATION.EMPLOYER_UNILATERAL'}
    if alternate.intersection(subissues) and not unilateral.intersection(subissues):
        return sorted(set(missing+profile_fact_questions(subissues,facts,query_date)))
    if facts.get('query_intent') in {'UNLAWFUL_DEFINITION_CONSEQUENCES','WITHDRAW_TERMINATION','MUTUAL_TERMINATION'}:
        return sorted(set(missing))
    if 'TERMINATION' in issues and facts.get('actor')=='EMPLOYEE' and not handled_termination:
        basis=facts.get('termination_basis')
        if facts.get('mutual_termination_agreement') is True: return sorted(set(missing))
        if basis=='LATE_WAGE':
            if facts.get('force_majeure_exception') is None:
                missing.append('Việc trả lương chậm có do bất khả kháng, sau khi người sử dụng lao động đã tìm mọi biện pháp khắc phục, và có nằm trong giới hạn khoản 4 Điều 97 không?')
            return sorted(set(missing))
        if basis=='EMPLOYER_MISINFORMATION':
            if facts.get('misinformation_material_effect') is not True:
                missing.append('Thông tin không trung thực khi giao kết đã ảnh hưởng như thế nào đến việc thực hiện hợp đồng lao động?')
            return sorted(set(missing))
        if basis in {'SEXUAL_HARASSMENT','MISTREATMENT'}: return sorted(set(missing))
        if basis=='WRONG_WORK':
            if facts.get('work_reassignment_exception') is None:
                missing.append('Việc bố trí công việc khác có thuộc trường hợp điều chuyển hợp pháp theo Điều 29 không?')
            return sorted(set(missing))
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
        topics={topic.key for topic in detect_topics(query)}
        material_only=('material_liability' in topics and not any(term in query for term in
            ('kỷ luật','sa thải','khiển trách','cách chức','nâng lương')))
        relationship_only=('CONTRACT.RELATIONSHIP_QUALIFICATION' in subissues and
            not any(term in query for term in ('lương tối thiểu','mức lương','bao nhiêu tiền',
                'trả lương chậm','trả lương trễ','đòi lương','tính lương','tính tiền lương')))
        incidental_wage=bool(topics.intersection({'suspension','job_transfer','material_liability'})) and not independent_wage
        for issue in issues:
            if issue=='TERMINATION' and handled_termination:continue
            # Broad routing parents are not procedural findings: property
            # compensation is not automatically a disciplinary sanction, and
            # paid work can be a relationship criterion rather than a wage claim.
            if issue=='DISCIPLINE' and material_only: continue
            if issue=='WAGE' and (relationship_only or incidental_wage): continue
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
    duration_prefix=q[worked.start():worked.start(1)] if worked else ''
    approximate=bool(re.search(r'(?:chưa\s+(?:đủ|tới)|dưới|hơn|trên|khoảng|gần|ít\s+nhất|tối\s+đa)\s*$',duration_prefix))
    if worked and not approximate:
        number=worked.group(1).lower()
        facts['worked_months']=int(number) if number.isdigit() else MONTH_NUMBER_WORDS[number]
    service_years,service=_service_duration(q)
    if service is not None: facts['service_years']=service_years
    age=AGE.search(q)
    if age:
        facts['age']=int(age.group(1)); facts['minor']=int(age.group(1))<18
    travel=TRAVEL_DAYS.search(q)
    if travel: facts['travel_days']=int(travel.group(1))
    contract_term=CONTRACT_TERM.search(q)
    if contract_term: facts['contract_duration_months']=int(contract_term.group('duration'))
    salary_base=parse_salary_base(q)
    if salary_base:
        facts['salary_base_amount']=salary_base.amount
        facts['salary_base_unit']=salary_base.unit
    if 'đặc biệt nặng nhọc' in q: facts['work_category']='SPECIAL_HEAVY'
    elif any(term in q for term in ('nặng nhọc, độc hại, nguy hiểm','nghề nặng nhọc','công việc nặng nhọc')): facts['work_category']='HEAVY'
    elif any(term in q for term in ('điều kiện bình thường','công việc bình thường','nhân viên văn phòng','công việc văn phòng')): facts['work_category']='NORMAL'
    if 'chưa thành niên' in q: facts['minor']=True
    if any(t in q for t in ('nhận lương cố định','làm việc có trả công','làm công việc có trả công')): facts['employment_paid_work']=True
    if any(t in q for t in ('chịu kpi','chịu sự quản lý','chịu sự điều hành','được quản lý như nhân viên')): facts['employment_management']=True
    if 'khuyết tật' in q: facts['disabled']=True
    if 'thử việc' in q and not relationship_comparison(q):
        # The required qualification of the job, not the applicant's diploma.
        for group,pattern in (
          ('MANAGER',r'(?:công việc|vị trí) (?:của người )?quản lý doanh nghiệp|thuộc diện người quản lý doanh nghiệp'),
          ('COLLEGE',r'(?:công việc|chức danh|vị trí)(?:\s+(?:nghề nghiệp|chuyên môn|này|của tôi)){0,2}\s+(?:cần|yêu cầu|đòi hỏi) (?:trình độ )?(?:chuyên môn,? kỹ thuật )?(?:từ )?cao đẳng(?: trở lên)?'),
          ('INTERMEDIATE',r'(?:công việc|chức danh|vị trí)(?:\s+(?:nghề nghiệp|chuyên môn|này|của tôi)){0,2}\s+(?:cần|yêu cầu|đòi hỏi) (?:trình độ )?trung cấp|công nhân kỹ thuật|nhân viên nghiệp vụ'),
          ('OTHER',r'công việc khác|công việc phổ thông')):
            match=re.search(pattern,q)
            if match and not re.search(r'không(?:\s+(?:làm|là|thuộc|phải)){0,2}\s*$',q[max(0,match.start()-30):match.start()]):
                facts['probation_work_group']=group; break
    premise=re.search(r'(?:khi|nếu)\s+(?:nlđ|người lao động)[^.]{0,100}đơn phương[^.]{0,100}trái pháp luật',q)
    if premise and not re.search(r'có bị|có phải|bị coi|khi nào|(?:không|chưa)\s+(?:bị coi là\s+)?trái pháp luật',premise.group()):
        facts['query_intent']='STIPULATED_EMPLOYEE_LIABILITY'
        facts['actor']='EMPLOYEE'
    if 'không xác định thời hạn' in q: facts['contract_type']='INDEFINITE'
    elif 'xác định thời hạn' in q: facts['contract_type']='FIXED_TERM'
    elif contract_term and 'thử việc' not in q: facts['contract_type']='FIXED_TERM'
    elif 'thử việc' in q and not relationship_comparison(q): facts['contract_type']='PROBATION'
    if any(x in q for x in ('mang thai','thai sản','nuôi con dưới 12 tháng')): facts['protected_status']='MATERNITY'
    notice_date=NOTICE_DATE_DMY.search(q)
    if notice_date: facts['notice_date']=f'{notice_date.group(3)}-{notice_date.group(2).zfill(2)}-{notice_date.group(1).zfill(2)}'
    termination_date=TERMINATION_DATE_DMY.search(q)
    if termination_date: facts['termination_date']=f'{termination_date.group(3)}-{termination_date.group(2).zfill(2)}-{termination_date.group(1).zfill(2)}'
    contract_start=CONTRACT_START_YEAR.search(q)
    if contract_start: facts['contract_start_year']=int(contract_start.group(1))
    if explicit_employer_action(q) or any(term in q for term in ('công ty cho tôi nghỉ','công ty cho người lao động nghỉ','người sử dụng lao động cho người lao động nghỉ','người sử dụng lao động chấm dứt','công ty chấm dứt','công ty chủ động chấm dứt','công ty đơn phương','công ty muốn đơn phương','người sử dụng lao động đơn phương','người sử dụng lao động muốn đơn phương','tôi bị công ty cho nghỉ','công ty sa thải')): facts['actor']='EMPLOYER'
    elif (re.search(r'\b(?:tôi|người lao động)\b[^.]{0,160}\b(?:nghỉ việc|xin nghỉ|chấm dứt hợp đồng|gửi thông báo nghỉ|muốn nghỉ|dự định nghỉ|sẽ nghỉ|(?:chỉ\s+)?báo trước)',q)
      or any(term in q for term in ('người lao động đơn phương','gửi thông báo đơn phương nghỉ','gửi thông báo','gửi email chấm dứt','gửi đơn chỉ báo trước','báo trước 1 ngày rồi nghỉ','báo trước 30 ngày'))): facts['actor']='EMPLOYEE'
    if any(term in q for term in ('không thuộc trường hợp được nghỉ không cần báo trước',
        'không thuộc trường hợp được miễn báo trước','không thuộc trường hợp không cần báo trước',
        'không có bất kỳ tình tiết nào thuộc trường hợp được nghỉ không cần báo trước')):
        facts['notice_exception']=False
    elif (any(term in q for term in ('được nghỉ không cần báo trước','được quyền nghỉ không cần báo trước','được miễn báo trước'))
          and not re.search(r'có\s+(?:được|quyền)|(?:được nghỉ|miễn báo trước)[^.;?!]{0,35}(?:không|hay không)\s*[?!.]*$',q)):
        facts['notice_exception']=True
    special_occupation,_=_special_occupation_fact(q)
    if special_occupation is not None: facts['special_occupation']=special_occupation
    if any(term in q for term in ('không có chi phí đào tạo','không phải hoàn trả chi phí đào tạo')): facts['training_costs']=False
    elif any(term in q for term in ('có chi phí đào tạo','phải hoàn trả chi phí đào tạo')): facts['training_costs']=True
    late_wage_terms = (
        'trả lương không đúng thời hạn', 'trả lương chậm', 'trả lương trễ',
        'trả lương cho tôi trễ', 'bị chậm trả lương', 'lương bị trả chậm',
        'không trả lương đúng hạn', 'không được trả lương đúng hạn',
        'không trả đủ lương', 'không được trả đủ lương',
    )
    if any(affirmative_phrase(q, (term,)) for term in late_wage_terms):
        facts['termination_basis']='LATE_WAGE'
        if any(term in q for term in ('không có sự kiện bất khả kháng','không có lý do bất khả kháng','không thuộc ngoại lệ bất khả kháng','không có sự kiện bất khả kháng hay lý do thuộc trường hợp ngoại lệ')):
            facts['force_majeure_exception']=False; facts['notice_exception']=True
    mistreatment=re.search(r'(?:bị|có hành vi)[^.;?!]{0,60}(?:đánh đập|nhục mạ|ngược đãi|cưỡng bức lao động)',q)
    if mistreatment and affirmative_phrase(q,(mistreatment.group(),)):
        facts['termination_basis']='MISTREATMENT';facts['actor']='EMPLOYEE'
    if re.search(r'(?:không|chưa)(?:\s+được)?\s+bố trí\s+(?:đúng\s+)?công việc',q):
        facts['termination_basis']='WRONG_WORK';facts['actor']='EMPLOYEE'
        if re.search(r'không thuộc[^.;?!]{0,60}(?:điều chuyển|điều 29)',q):
            facts['work_reassignment_exception']=False
    if 'quấy rối tình dục tại nơi làm việc' in q:
        facts['termination_basis']='SEXUAL_HARASSMENT'; facts['notice_exception']=True; facts['actor']='EMPLOYEE'
    if any(term in q for term in ('cung cấp sai thông tin','cung cấp thông tin sai','cung cấp sai địa điểm','cung cấp thông tin không trung thực','cung cấp khi giao kết là không trung thực')) and any(term in q for term in ('giao kết','tuyển dụng','ảnh hưởng trực tiếp','không thể thực hiện công việc')) and any(term in q for term in ('nghỉ','chấm dứt')):
        facts['termination_basis']='EMPLOYER_MISINFORMATION'; facts['actor']='EMPLOYEE'
        material_effect=re.search(r'ảnh hưởng(?: trực tiếp)? (?:đến|tới) (?:việc )?thực hiện (?:hợp đồng(?: lao động)?|hđlđ)',q)
        if material_effect and not re.search(r'(?:không|chưa)\s+ảnh hưởng|có\s+ảnh hưởng[^.?!]{0,100}không\s*\?',q):
            facts['misinformation_material_effect']=True; facts['notice_exception']=True
    agreement_terms=('đồng ý cho nghỉ','đồng ý chấm dứt','thỏa thuận chấm dứt','thoả thuận chấm dứt')
    if any(term in q for term in agreement_terms) and not affirmative_phrase(q,agreement_terms):
        facts['mutual_termination_agreement']=False
    elif affirmative_phrase(q,('công ty đồng ý cho','giám đốc trả lời bằng văn bản rằng công ty đồng ý','hai bên thỏa thuận chấm dứt')):
        facts['mutual_termination_agreement']=True
    if any(term in q for term in ('hủy bỏ việc đơn phương','đổi ý trước khi hết thời hạn báo trước')): facts['query_intent']='WITHDRAW_TERMINATION'
    elif 'trái pháp luật' in q and 'nghĩa vụ' in q and ('hai điều luật khác nhau' in q or 'định nghĩa' in q): facts['query_intent']='UNLAWFUL_DEFINITION_CONSEQUENCES'
    elif facts.get('mutual_termination_agreement'): facts['query_intent']='MUTUAL_TERMINATION'
    elif 'thời gian đi và về' in q or 'thời gian đi đường' in q: facts['query_intent']='TRAVEL_TIME'
    elif (any(term in q for term in ('bao nhiêu ngày nghỉ','bao nhiêu ngày phép','bao nhiêu ngày','số ngày nghỉ hằng năm','tính quyền nghỉ','tính:','cách tính này')) or bool(re.search(r'\b\d+\s+ngày\b',q)) and any(term in q for term in ('có đúng','đúng không','có được')) or bool(re.search(r'(?:tổng\s+)?số\s+ngày\s+(?:nghỉ|phép)[^.?;]{0,80}bao\s+nhiêu',q))) and (any(term in q for term in ('nghỉ hằng năm','nghỉ hàng năm','nghỉ phép','phép năm','ngày phép','thâm niên','ngày cơ bản')) or 'service_years' in facts and 'số ngày nghỉ' in q):
        specific=bool(facts.get('service_years') or facts.get('work_category') or facts.get('minor') or facts.get('disabled') or re.search(r'\b(?:tôi|[a-e])\b',q))
        facts['query_intent']='ANNUAL_LEAVE_CALC' if specific else 'ANNUAL_LEAVE_OVERVIEW'
    if re.search(r'\b(?:người lao động|nlđ|tôi)\s+phải báo trước',q): facts.setdefault('actor','EMPLOYEE')
    if facts.get('termination_basis')=='LATE_WAGE': facts.setdefault('actor','EMPLOYEE')
    stipulated=stipulated_liability_actor(q)
    if stipulated:
        facts['actor']=stipulated
        facts['query_intent']='STIPULATED_'+stipulated+'_LIABILITY'
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
    plan=plan_with_profiles(analysis,_legacy_plan_evidence(analysis))
    resolved=getattr(analysis,'resolved_rule_requirements',{})
    queries={task.task_id:task.retrieval_query for task in analysis.answer_tasks if not task.legal_subissues} if len(analysis.answer_tasks)>1 else {}
    return plan.model_copy(update={'task_queries':queries,'slot_requirements':{slot:resolved.get(slot,groups)
        for slot,groups in plan.slot_requirements.items()}})

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
