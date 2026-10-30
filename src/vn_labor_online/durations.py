"""Conservative trial-duration reading; never convert calendar units or ranges."""
import re
import unicodedata


def _fold(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD',value.lower())
                           if unicodedata.category(c)!='Mn').replace('đ','d').split())


_DIGITS={'khong':0,'mot':1,'hai':2,'ba':3,'bon':4,'tu':4,'nam':5,'lam':5,
         'sau':6,'bay':7,'tam':8,'chin':9}
_TOKEN=r'(?:khong|mot|hai|ba|bon|tu|nam|lam|sau|bay|tam|chin|muoi|tram|linh|le)'
_NUMBER=rf'(?:\d+|{_TOKEN}(?:\s+{_TOKEN}){{0,5}})'
_DURATION=re.compile(rf'\bthu viec(?P<prefix>[^.;?!]{{0,50}}?)\b(?P<number>{_NUMBER})\s*(?P<unit>ngay lam viec|ngay|thang|tuan|nam)\b')


def _integer(text):
    if text.isdigit():return int(text)
    words=text.split();hundreds=0
    if 'tram' in words:
        if len(words)<2 or words[1]!='tram' or words[0] not in _DIGITS or not _DIGITS[words[0]]:return None
        hundreds=_DIGITS[words[0]]*100;words=words[2:]
        if words and words[0] in {'linh','le'}:words=words[1:]
    if not words:return hundreds or None
    if len(words)==1 and words[0] in _DIGITS:return hundreds+_DIGITS[words[0]]
    if words[0]=='muoi':
        rest=words[1:];tens=10
    elif len(words)>=2 and words[0] in _DIGITS and _DIGITS[words[0]]>=2 and words[1]=='muoi':
        rest=words[2:];tens=_DIGITS[words[0]]*10
    else:return None
    if not rest:return hundreds+tens
    if len(rest)==1 and rest[0] in _DIGITS:return hundreds+tens+_DIGITS[rest[0]]
    return None


def probation_duration(query):
    """Return an explicit count and its original unit, or None if ambiguous."""
    text=_fold(query)
    matches=list(_DURATION.finditer(text))
    if len(matches)!=1:return None
    match=matches[0];prefix=match.group('prefix')
    if re.search(r'\b(?:tu|den|khoang|gan|hon|hay|it nhat|toi da|khong qua|luong|dong)\b|%',prefix):return None
    count=_integer(match.group('number'))
    return (count,match.group('unit')) if count is not None and count>0 else None
