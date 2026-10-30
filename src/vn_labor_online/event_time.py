"""Ground explicit dates in event roles; ambiguity is never legal certainty."""
from __future__ import annotations
import re
from datetime import date

DATES=re.compile(r'\b(?:(?P<y>(?:19|20|21)\d{2})[-/.](?P<m>\d{1,2})[-/.](?P<d>\d{1,2})|(?P<dd>\d{1,2})[-/.](?P<mm>\d{1,2})[-/.](?P<yy>(?:19|20|21)\d{2}))\b')
MARKERS=[
    ('BIRTH_DATE',r'\bsinh(?: vào| ngày)?\b'),
    ('CONTRACT_SIGNED_AT',r'(?:ký|giao kết|bắt đầu)[^,;.!?]{0,45}hợp đồng|hợp đồng[^,;.!?]{0,35}(?:ký|giao kết|bắt đầu)'),
    ('LAW_APPLICABLE_AT',r'(?:quy định|pháp luật|luật)[^,;.!?]{0,25}(?:áp dụng|hiệu lực|tại ngày)|(?:áp dụng|tra cứu|tính đến|xét theo luật tại)'),
    ('DECISION_ISSUED_AT',r'(?:ban hành|ra|ký|nhận)[^,;.!?]{0,30}quyết định'),
    ('SOURCE_PROMULGATED_AT',r'(?:luật|nghị định|thông tư)[^,;.!?]{0,50}ban hành'),
    ('NOTICE_GIVEN_AT',r'(?:gửi|nộp)[^,;.!?]{0,25}(?:thông báo|đơn nghỉ)|thông báo nghỉ'),
    ('TERMINATION_AT',r'sa thải|chấm dứt(?: hợp đồng)?|nghỉ(?: việc| chính thức)(?! riêng)|cho (?:tôi|người lao động) nghỉ'),
    ('VIOLATION_OCCURRED_AT',r'tai nạn|xảy ra|trả lương|nợ lương|tăng ca|làm thêm|điều chuyển|chuyển công việc|kỷ luật'),
]


def resolve_event_dates(query,explicit_date=None):
    events=[]
    for match in DATES.finditer(query):
        y=match.group('y') or match.group('yy');m=match.group('m') or match.group('mm');d=match.group('d') or match.group('dd')
        try:value=date(int(y),int(m),int(d)).isoformat()
        except ValueError:continue
        # Consider only the nearest clause/event marker. Do not attach a later
        # date to a contract verb in an earlier comma-separated clause.
        prefix=query[max(0,match.start()-130):match.start()]
        clause=re.split(r'[,;!?\n]|(?<!\d)\.(?!\d)',prefix)[-1]
        found=[]
        for role,pattern in MARKERS:
            for marker in re.finditer(pattern,clause,re.I):found.append((marker.end(),role))
        role=max(found,key=lambda x:x[0])[1] if found else 'UNASSIGNED'
        if re.search(r'(?:ban hành|ra|ký|nhận)[^,;.!?]{0,30}quyết định',clause,re.I):role='DECISION_ISSUED_AT'
        # Issuing a dismissal decision and its effective date are distinct.
        if re.search(r'có hiệu lực|hiệu lực từ',clause,re.I):role='LAW_APPLICABLE_AT'
        events.append({'role':role,'date':value,'source_quote':match.group(),
            'char_start':match.start(),'char_end':match.end()})
    if explicit_date or not events:return events,None,False
    applicable={e['date'] for e in events if e['role']=='LAW_APPLICABLE_AT'}
    actual={e['date'] for e in events if e['role'] in {'TERMINATION_AT','VIOLATION_OCCURRED_AT'}}
    decision={e['date'] for e in events if e['role']=='DECISION_ISSUED_AT'}
    if applicable:return events,next(iter(applicable)) if len(applicable)==1 else None,len(applicable)>1
    if actual:return events,next(iter(actual)) if len(actual)==1 else None,len(actual)>1
    if decision:return events,next(iter(decision)) if len(decision)==1 else None,len(decision)>1
    unique={e['date'] for e in events}
    if len(unique)>1:return events,None,True
    # Single-date cases are left with the existing precise date parser. A role
    # cannot be invented from a bare date alone.
    return events,None,False
