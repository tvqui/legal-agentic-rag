"""Dated statutory retrieval requirements, not question/answer templates.

This catalogue covers mechanisms. Matching a topic never proves applicability
or legal authority. Missing corpus entries remain missing, not invented rules.
"""
from .models import LegalLocator
from .claim_validation import fold

def extra_requirements(analysis):
    q=fold(analysis.query_text); facts=analysis.facts
    old=bool(analysis.query_date and analysis.query_date<'2021-01-01')
    docs=['10/2012/QH13'] if old else ['45/2019/QH14','18/VBHN-VPQH']
    out={}
    def loc(article,clause=None,point=None,documents=None,exact=False):
        return LegalLocator(documents=documents or docs,article=str(article),
            clause=str(clause) if clause is not None else None,point=point,exact_level=exact)
    def clauses(slot,article,values,documents=None):
        out[slot]=[[loc(article,c,documents=documents,exact=True)] for c in values]
    def points(slot,article,clause,values,documents=None):
        out[slot]=[[loc(article,clause,p,documents)] for p in values]
    def has(*terms): return any(term in q for term in terms)
    if has('giao ket','ung vien','tuyen dung') and has('cung cap','thong tin','thong bao') and not facts.get('termination_basis'):
        clauses('employer_information',19 if old else 16,[1])
    expiry=has('hop dong het han','hop dong lao dong het han','hdld het han','het han hop dong','het han hdld')
    renewal=has('hop dong thu ba','ba lan lien tiep','ky lai','tai ky','gia han hop dong','hdld xac dinh thoi han 24 thang ba lan') or (
        expiry and has('tiep tuc lam viec','van di lam','van tiep tuc','ky tiep','hop dong moi','loai hop dong','thuoc loai nao','moc thoi gian'))
    if renewal:
        points('term_contract_renewal',22 if old else 20,2,['a','b','c'] if not old else [],docs)
        if old: clauses('term_contract_renewal',22,[2])
        else:
            # Exception targets are part of the rule, not proof that they apply.
            out['renewal_exceptions']=[[loc(149,1)],[loc(151,2)],[loc(177,4)]]
    if expiry and has('mang thai','thai san','nuoi con'):
        out['expiry_rule']=[[loc(36 if old else 34,1)]]
        out['maternity_expiry_protection']=[[loc(155 if old else 137,3)]]
    if has('hop dong dao tao') and has('noi dung','phai co','bao gom','nhung gi'):
        points('training_contract_contents',62,2,['a','b','c','d','đ','e'])
        # Do not replace the contents question with repayment obligations.
        out['training_contract']=[[loc(62,1)]]
    if has('luong toi thieu') and has('phu cap','luong co ban','muc luong','ap dung','thap hon','dap ung'):
        out['minimum_wage_salary_base']=[[loc(90,1)]]
        instruments=['90/2019/NĐ-CP'] if old else ['90/2019/NĐ-CP'] if analysis.query_date and analysis.query_date<'2022-07-01' else ['38/2022/NĐ-CP'] if analysis.query_date and analysis.query_date<'2024-07-01' else ['74/2024/NĐ-CP'] if analysis.query_date and analysis.query_date<'2026-01-01' else ['293/2025/NĐ-CP']
        # The 2019 and 2022 decrees use a different structural location.
        out['minimum_wage_operative_rule']=[[loc(5 if instruments==['90/2019/NĐ-CP'] else 4,1,documents=instruments)]]
    if has('hinh thuc') and has('ky luat'):
        clauses('discipline_forms',125 if old else 124,[1,2,3] if old else [1,2,3,4])
    if has('thu tuc','trinh tu','quy trinh','cuoc hop') and has('ky luat','sa thai'):
        out['discipline_procedure']=[[loc(123 if old else 122,1)]]
        if not old: out['discipline_implementing_procedure']=[[loc(70,documents=['145/2020/NĐ-CP'])]]
    if has('ky luat','cuoc hop ky luat') and has('danh','bao luc','xam pham','nhuc ma','xuc pham','hanh hung'):
        clauses('discipline_prohibited_acts',128 if old else 127,[1])
    if has('cao tuoi') and has('the nao','dinh nghia','khai niem','duoc hieu','la gi'):
        clauses('elderly_definition',166 if old else 148,[1])
        if not old: clauses('retirement_age_reference',169,[2])
    if has('chua thanh nien','chua du 18','duoi 18') and has('nhom tuoi','do tuoi','chia','bao nhieu tuoi'):
        clauses('minor_age_groups',161 if old else 143,[1] if old else [1,2,3,4])
    if has('dinh cong') and has('hop phap','dieu kien','quyen dinh cong'):
        if old:
            out['strike_definition']=[[loc(209)]]
            out['strike_procedure']=[[loc(211)],[loc(212)],[loc(213)]]
            out['illegal_strike_conditions']=[[loc(215)]]
        else:
            out['strike_definition']=[[loc(198,exact=True)]]
            clauses('strike_entitlement',199,[1,2])
            clauses('strike_procedure',200,[1,2,3])
            out['strike_consultation']=[[loc(201)]]
            out['strike_decision_notice']=[[loc(202)]]
            clauses('illegal_strike_conditions',204,[1,2,3,4,5,6])
    if has('tranh chap') and has('quyen','loi ich','phan loai','cac loai','phan biet'):
        out['dispute_definitions']=[[loc(179 if not old else 3,exact=True)]]
        if not old: clauses('collective_dispute_types',179,[2,3])
    if has('bhxh','bao hiem xa hoi') and has('bat buoc','tham gia','thuoc dien','quyen ve','khong co quyen'):
        after=not analysis.query_date or analysis.query_date>='2025-07-01'
        insurance=['41/2024/QH15'] if after else ['58/2014/QH13']
        out['social_insurance_subjects']=[[loc(2,1,documents=insurance,exact=True)],
            [loc(2,1,'a',insurance)]]
    if has('bhyt','bao hiem y te') and not has('chi phi dao tao','trong thoi gian dao tao'):
        # These documents may be absent. Article 13 BLLD cannot fill this slot.
        out['health_insurance_subjects']=[[loc(12,documents=['25/2008/QH12','46/2014/QH13'])]]
        if not analysis.query_date or analysis.query_date>='2025-07-01':
            out['health_insurance_current_amendment']=[[loc(1,documents=['51/2024/QH15'])]]
    if has('du lieu','thong tin ca nhan','sinh trac','camera','giam sat') and has('nguoi lao dong','nld','nsdld','tuyen dung','nhan vien'):
        if not analysis.query_date or analysis.query_date>='2026-01-01':
            out['employee_data_processing']=[[loc(25,documents=['91/2025/QH15'])]]
            out['data_processing_lawful_basis']=[[loc(19,documents=['91/2025/QH15'])]]
        else: out['data_processing_lawful_basis']=[[loc(11,documents=['13/2023/NĐ-CP'])]]
    if has('phien ban luat','phien ban phap luat','citation cu','hieu luc phap ly','van ban cu') and has('thoi diem','nam','hieu luc','van ban moi','chon'):
        out['application_of_normative_documents']=[[loc(58,documents=['64/2025/QH15'])]]
    # False positives are hints, never conclusions; the semantic review still
    # checks question relevance and conditions against the actual source text.
    return out
