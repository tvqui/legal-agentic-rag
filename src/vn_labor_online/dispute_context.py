"""Separate a dispute's subject matter from the procedure being requested."""
import re


def individual_mediation_requested(query):
    from .claim_validation import fold
    q=fold(query)
    labour=any(term in q for term in ('lao dong','sa thai','tien luong','tro cap thoi viec',
        'tro cap mat viec','giup viec gia dinh','bao hiem xa hoi','bao hiem y te','bhxh','bhyt'))
    return (labour and 'hoa giai' in q and 'tap the' not in q
        and any(term in q for term in ('tranh chap','khoi kien','toa an','hoa giai vien')))


def mediation_only(query):
    if not individual_mediation_requested(query):return False
    from .claim_validation import fold
    q=fold(query)
    # A dispute's subject is not a request to assess the employer's action.
    independent=re.search(r'(?:sa thai|cham dut)[^.;?!]{0,45}co (?:dung|duoc|hop phap|trai)|'
        r'co (?:quyen|duoc(?: phep)?)[^.;?!]{0,35}(?:sa thai|cham dut)|'
        r'(?:dieu kien|thu tuc|trinh tu|can cu)\s+(?:xu ly ky luat|sa thai|cham dut)|'
        r'(?:danh gia|ket luan)\s+(?:viec\s+)?(?:sa thai|cham dut)|'
        r'(?:bao truoc[^.;?!]{0,25}(?:bao nhieu|bao lau)|(?:thoi han|so ngay)[^.;?!]{0,25}bao truoc)|'
        r'co duoc (?:huong|nhan)\s+tro cap',q)
    return independent is None
