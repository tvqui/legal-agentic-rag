"""Ground attribute polarity and expose verbatim user statements, not legal findings."""
import re

def assertion_uncertain(query,start,end):
    prefix=re.split(r'[.;!?,]|\b(?:nhưng|tuy nhiên)\b',query[max(0,start-100):start])[-1]
    suffix=query[end:end+55]
    if re.search(r'(?:không\s+(?:biết|rõ|chắc)|chưa\s+(?:biết|rõ|chắc|được xác nhận)|chưa xác định)[^.;?!]*$',prefix,re.I):
        return True
    if re.match(r'\s*(?:hay|hoặc)\s+không\b',suffix,re.I):return True
    return bool(re.search(r'\b(?:có|liệu|phải chăng)[^.;?!]{0,50}$',prefix,re.I)
                and re.search(r'\bkhông\s*[?!.]',suffix,re.I))


def attribute_polarity(query,terms):
    q=query.lower();values=set()
    for term in sorted(terms,key=len,reverse=True):
        for match in re.finditer(re.escape(term),q):
            prefix=re.split(r'[.;!?,]|\b(?:nhưng|tuy nhiên)\b',q[max(0,match.start()-90):match.start()])[-1]
            suffix=q[match.end():match.end()+40]
            if assertion_uncertain(query,match.start(),match.end()):continue
            negative=bool(re.search(r'\b(?:không|chẳng)(?:\s+(?:hề|phải|là|người|bị|thuộc|nhóm|đối|tượng|có)){0,8}\s*$',prefix))
            values.add(not negative)
    # A contradiction cannot silently choose one fact; the conversation layer
    # must ask for confirmation instead of treating either branch as proved.
    return values.pop() if len(values)==1 else None

def query_statements(query):
    result=[]
    for match in re.finditer(r'[^.;?!]+',query):
        quote=match.group().strip()
        if not quote:continue
        kind='HYPOTHESIS' if re.search(r'\b(?:nếu|giả sử|giả định)\b',quote,re.I) else 'USER_STATEMENT'
        if query[match.end():match.end()+1]=='?' or re.search(r'\b(?:hãy|bao nhiêu|bao lâu|có được|có phải|có quyền|thế nào|đúng không)\b',quote,re.I):
            kind='QUESTION'
        result.append({'quote':quote,'kind':kind})
    return result
