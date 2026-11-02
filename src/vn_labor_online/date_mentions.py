"""Calendar mentions with exact spans and without overlapping precision guesses.

Invalid full dates occupy their spans too: '31 tháng 4 năm 2020' must never
silently become April 2020 or the whole year. This module selects no law.
"""
from dataclasses import dataclass
from datetime import date
import calendar
import re

_FULL = re.compile(
    r"\b(?:(?P<y>(?:19|20|21)\d{2})[-/.](?P<m>\d{1,2})[-/.](?P<d>\d{1,2})"
    r"|(?P<dd>\d{1,2})[-/.](?P<mm>\d{1,2})[-/.](?P<yy>(?:19|20|21)\d{2})"
    r"|(?:ngày\s+)?(?P<wd>\d{1,2})\s+tháng\s+(?P<wm>\d{1,2})\s+(?:năm\s+)?(?P<wy>(?:19|20|21)\d{2}))\b", re.I)
_MONTH = re.compile(
    r"\btháng\s*(?P<m>\d{1,2})(?:\s*năm\s*|\s*[/\-]\s*)(?P<y>(?:19|20|21)\d{2})\b"
    r"|(?<![\w/.-])(?P<sm>\d{1,2})\s*[/\-]\s*(?P<sy>(?:19|20|21)\d{2})\b", re.I)
_YEAR = re.compile(r"\bnăm\s*((?:19|20|21)\d{2})\b", re.I)

@dataclass(frozen=True)
class DateMention:
    char_start: int
    char_end: int
    source_quote: str
    precision: str
    start: str | None
    end: str | None

    @property
    def valid(self):
        return self.start is not None


def date_mentions(query):
    mentions=[]
    def overlaps(match):
        return any(match.start()<m.char_end and m.char_start<match.end() for m in mentions)
    def add(match,precision,year,month=1,day=1):
        try:
            start=date(int(year),int(month),int(day))
            end=(start.replace(month=12,day=31) if precision=='YEAR' else
                 start.replace(day=calendar.monthrange(start.year,start.month)[1]) if precision=='MONTH' else start)
            start,end=start.isoformat(),end.isoformat()
        except ValueError:
            start=end=None
        mentions.append(DateMention(match.start(),match.end(),match.group(),precision,start,end))
    for match in _FULL.finditer(query):
        add(match,'DAY',match.group('y') or match.group('yy') or match.group('wy'),
            match.group('m') or match.group('mm') or match.group('wm'),
            match.group('d') or match.group('dd') or match.group('wd'))
    for match in _MONTH.finditer(query):
        if not overlaps(match):
            add(match,'MONTH',match.group('y') or match.group('sy'),match.group('m') or match.group('sm'))
    for match in _YEAR.finditer(query):
        if not overlaps(match):add(match,'YEAR',match.group(1))
    return sorted(mentions,key=lambda m:m.char_start)
