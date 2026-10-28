"""High-precision, source-driven references to exceptions within the same article.

No article numbers, benchmark question IDs or guessed legal exceptions are
encoded here. A reference creates a retrieval requirement, never a legal PASS.
"""
import re,unicodedata
from .models import LegalLocator

_SAME_ARTICLE=re.compile(
    r'(?:trừ\s+(?:các\s+)?trường\s+hợp|ngoại\s+lệ)[^.;\n]{0,120}?'
    r'\bkhoản\s+(\d+[a-zđ]?)\s+(?:của\s+)?điều\s+này\b',re.I)

def exception_locators(item):
    if item.kind!='PROVISION' or not item.document_number or not item.article_number:
        return []
    source=unicodedata.normalize('NFC',item.source_text or item.text or '')
    clauses=list(dict.fromkeys(_SAME_ARTICLE.findall(source)))
    return [LegalLocator(documents=[item.document_number],article=str(item.article_number),clause=clause)
      for clause in clauses[:8] if clause!=str(item.clause_number or '')]
