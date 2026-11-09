"""Recognize the requested termination task, without deciding a real dispute."""
import re


def explicit_employer_action(query):
    return bool(re.search(r'\b(?:công ty|doanh nghiệp|người sử dụng lao động)\s+'
        r'(?:(?:có|được|thể|muốn|sẽ|quyền|phép|đã|không|chủ động)\s+){0,7}'
        r'(?:đơn phương|chấm dứt|cho thôi việc|cho nghỉ)',query.lower()))


def protection_clause(query,facts):
    q=query.lower()
    if not explicit_employer_action(q) or any(term in q for term in ('hết hạn','giải thể','chấm dứt hoạt động','so sánh')):
        return None
    if facts.get('protected_status')=='MATERNITY':return '3'
    if any(term in q for term in ('nghỉ phép năm','nghỉ hằng năm','nghỉ việc riêng')) and any(
        term in q for term in ('đã được công ty chấp thuận','đã được chấp thuận','được công ty đồng ý')):
        return '2'
    return None


def stipulated_liability_actor(query):
    q=query.lower()
    if not any(term in q for term in ('bồi thường','nghĩa vụ','hậu quả','trợ cấp')):return None
    for clause in re.split(r'[.;?!]',q):
        if not re.search(r'(?:trái pháp luật|trái luật)',clause):continue
        if re.search(r'có\s+(?:bị|phải|trái)|(?:không|chưa)\s+(?:bị coi là\s+)?trái|trái (?:pháp luật|luật)\s+(?:hay\s+)?không|khi nào|hay không',clause):continue
        # A directly stated unlawful premise can support a conditional answer
        # about consequences. It is not an independent finding of illegality.
        if explicit_employer_action(clause):return 'EMPLOYER'
        if re.search(r'\b(?:người lao động|nlđ|tôi)\b[^.;?!]{0,100}(?:đơn phương|nghỉ việc)',clause):return 'EMPLOYEE'
    return None


def settlement_deadline_only(query):
    q=query.lower()
    return (any(term in q for term in ('chấm dứt hợp đồng','thôi việc'))
        and any(term in q for term in ('thanh toán','trả các khoản','chi trả quyền lợi'))
        and any(term in q for term in ('thời hạn','bao nhiêu ngày','chậm nhất','tối đa'))
        and not any(term in q for term in ('báo trước','trái pháp luật','trái luật','có đúng','có hợp pháp')))


def contract_expiry_context(query):
    from .claim_validation import fold
    q=fold(query)
    return bool(re.search(r'\b(?:het (?:han|thoi han) (?:hop dong|hdld)|'
        r'(?:hop dong(?: lao dong)?|hdld)(?:\s+(?:co|xac dinh))?\s*(?:thoi han)?'
        r'(?:\s+(?:cua toi|nay|do)){0,2}\s+(?:(?:vua|da|sap)\s+)?het(?:\s+(?:han|thoi han))?)\b',q))


def contract_continuation_facets(query):
    """Requested facets, not conclusions about renewal or contract validity."""
    from .claim_validation import fold
    q=fold(query)
    repeat=bool(re.search(r'\b(?:hai|ba|2|3)\s+hop dong(?: lao dong)?[^.;?!]{0,35}(?:lien tiep|xac dinh thoi han)|'
        r'\b(?:so lan|may lan|ky them|ky lai|tai ky|hop dong thu ba|lan thu ba|lan thu 3|ky 3 lan)\b',q))
    continued=any(term in q for term in ('tiep tuc lam','van lam','van di lam','ky tiep','ky moi','hop dong moi','hop dong cu','loai hop dong','tro thanh','thuoc loai'))
    if not repeat and not (contract_expiry_context(q) and continued):return []
    rights=any(t in q for t in ('quyen loi','hop dong cu','tien luong trong','luong trong thoi gian'))
    conversion=any(t in q for t in ('loai hop dong','hop dong nao','tro thanh','chuyen thanh','chuyen sang','khong xac dinh thoi han'))
    facets=[]
    if rights:facets.append('RIGHTS')
    if conversion and (not repeat or re.search(r'\b(?:30|ba muoi)\s+ngay\b|thoi han ky moi|truoc va sau',q)):facets.append('CONVERSION')
    if repeat:facets.append('RENEWAL_COUNT')
    return facets or ['RIGHTS','CONVERSION','RENEWAL_COUNT']
