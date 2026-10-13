from __future__ import annotations
from .models import Evidence
from .answer_quality import clean_source_excerpt

def compress_evidence(item:Evidence,query:str,max_chars:int=700)->str:
    # Preserve inherited norm polarity/scope and every sentence. Selection
    # controls context size; sentence ranking cannot discard legal conditions.
    body=clean_source_excerpt(item.source_text or item.text,query)
    context=item.ancestor_context or ''
    text=' '.join((context+'\n'+body if context and context not in body else body).split())
    return text
