"""High-precision, source-driven references to exceptions within the same article.

No article numbers, benchmark question IDs or guessed legal exceptions are
encoded here. A reference creates a retrieval requirement, never a legal PASS.
"""
import re,unicodedata
from .models import LegalLocator

_SAME_ARTICLE=re.compile(
    r'(?:trừ\s+(?:các\s+)?trường\s+hợp|ngoại\s+lệ)[^.;\n]{0,120}?'
    r'\bkhoản\s+(\d+[a-zđ]?)\s+(?:của\s+)?điều\s+này\b',re.I)

_LOCAL_ARTICLE=re.compile(
    r'(?:trừ\s+(?:các\s+)?trường\s+hợp|ngoại\s+lệ)[^.;\n]{0,100}?'
    r'(?:\bđiểm\s+(?P<point>[a-zđ])\s+)?'
    r'(?:\bkhoản\s+(?P<clause>\d+[a-zđ]?)\s+)?'
    r'\bđiều\s+(?P<article>\d+[a-zđ]?)\s+(?:của\s+)?'
    r'(?:bộ\s+luật|luật|nghị\s+định|thông\s+tư|văn\s+bản)\s+này\b',re.I)


def exception_locators(item):
    if item.kind!='PROVISION' or not item.document_number or not item.article_number:
        return []
    source=unicodedata.normalize('NFC',item.source_text or item.text or '')
    clauses=list(dict.fromkeys(_SAME_ARTICLE.findall(source)))
    locators=[LegalLocator(documents=[item.document_number],article=str(item.article_number),clause=clause)
      for clause in clauses[:8] if clause!=str(item.clause_number or '')]
    # Cross-article links require explicit local-document wording. A reference
    # to an unnamed 'other law' cannot be silently rebound to this document.
    for match in _LOCAL_ARTICLE.finditer(source):
        locator=LegalLocator(documents=[item.document_number],article=match.group('article'),
            clause=match.group('clause'),point=match.group('point'))
        own=(str(item.article_number),str(item.clause_number or ''),str(item.point_number or ''))
        target=(locator.article,str(locator.clause or ''),str(locator.point or ''))
        if target!=own and locator not in locators:locators.append(locator)
    return locators[:8]
