from __future__ import annotations
import re
from .models import Evidence
from .answer_quality import clean_source_excerpt

def compress_evidence(item:Evidence,query:str,max_chars:int=700)->str:
    # Preserve inherited norm polarity/scope and every sentence. Selection
    # controls context size; sentence ranking cannot discard legal conditions.
    body=clean_source_excerpt(item.source_text or item.text,query)
    context=item.ancestor_context or ''
    combined=context+'\n'+body if context and context not in body else body
    # A standalone equality sign commonly comes from PDF formula layout.
    # Do not flatten it into prose or guess missing mathematical grouping.
    if re.search(r'(?m)^\s*=\s*$',body):return combined
    return ' '.join(combined.split())
