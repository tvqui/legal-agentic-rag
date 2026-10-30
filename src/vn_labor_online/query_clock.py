"""Vietnamese request-day semantics, independent of the server's timezone."""
import calendar
import re
from datetime import datetime,timedelta,timezone

VIETNAM=timezone(timedelta(hours=7))


def today_vietnam(now=None):
    instant=now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:raise ValueError('Request clock requires an aware datetime')
    return instant.astimezone(VIETNAM).date()


def relative_date_ranges(query,today=None):
    anchor=today or today_vietnam()
    text=' '.join(query.lower().split())
    values=[]
    def add(start,end,precision):
        value=(start.isoformat(),end.isoformat(),precision)
        if value not in values:values.append(value)
    for phrase,days in [('hôm kia',-2),('hôm qua',-1),('hôm nay',0),('ngày mai',1),
                        ('hiện nay',0),('bây giờ',0),('lúc này',0)]:
        if re.search(r'(?<!\w)'+re.escape(phrase)+r'(?!\w)',text):
            day=anchor+timedelta(days=days);add(day,day,'DAY')
    for phrase,offset in [('tháng trước',-1),('tháng này',0),('tháng sau',1)]:
        if phrase in text:
            absolute=anchor.year*12+anchor.month-1+offset
            year,month=divmod(absolute,12);month+=1
            start=anchor.replace(year=year,month=month,day=1)
            add(start,start.replace(day=calendar.monthrange(year,month)[1]),'MONTH')
    for phrase,offset in [('năm ngoái',-1),('năm trước',-1),('năm nay',0),('năm sau',1)]:
        if phrase in text:
            start=anchor.replace(year=anchor.year+offset,month=1,day=1)
            add(start,start.replace(month=12,day=31),'YEAR')
    for phrase,offset in [('tuần trước',-1),('tuần này',0),('tuần sau',1)]:
        if phrase in text:
            start=anchor-timedelta(days=anchor.weekday())+timedelta(weeks=offset)
            add(start,start+timedelta(days=6),'RANGE')
    return values


def unpublished_change_prediction(query,query_date,today=None):
    """A hypothetical future amendment is not an enacted prospective rule."""
    from datetime import date
    if not query_date:return False
    try:future=date.fromisoformat(query_date)>(today or today_vietnam())
    except ValueError:return False
    q=query.lower()
    hypothetical=bool(re.search(r'nếu\s+(?:có\s+)?(?:thay đổi|sửa đổi)(?:\s+(?:luật|quy định))?|dự đoán|chưa ban hành',q))
    forecast=bool(re.search(r'sẽ\s+(?:nâng|hạ|sửa đổi|thay đổi|ban hành)',q))
    published=any(term in q for term in ('đã ban hành','đã được quy định','theo nghị định','theo luật số','theo quyết định'))
    mixed=any(term in q for term in ('so sánh','quy định hiện hành','hiện nay là'))
    return future and hypothetical and forecast and not published and not mixed
