from __future__ import annotations
import re
from .models import Evidence

CRITICAL=('không','trừ','chỉ khi','điều kiện','ngoại lệ','báo trước','tham chiếu','theo quy định tại')

def compress_evidence(item:Evidence,query:str,max_chars:int=700)->str:
    text=' '.join((item.source_text or item.text).split())
    if len(text)<=max_chars: return text
    query_terms={x for x in re.findall(r'\w+',query.lower()) if len(x)>3}
    sentences=[x.strip() for x in re.split(r'(?<=[.;:!?])\s+',text) if x.strip()]
    scored=[]
    for index,sentence in enumerate(sentences):
        lower=sentence.lower(); overlap=len(query_terms.intersection(re.findall(r'\w+',lower)))
        critical=sum(1 for x in CRITICAL if x in lower); scored.append((overlap+2*critical,-index,index,sentence))
    chosen=[]; used=0
    for _,_,index,sentence in sorted(scored,reverse=True):
        if used+len(sentence)+1>max_chars: continue
        chosen.append((index,sentence)); used+=len(sentence)+1
    chosen.sort(); result=' '.join(x[1] for x in chosen)
    return result or text[:max_chars].rstrip()+'…'
