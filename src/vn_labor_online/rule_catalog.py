"""Dated statutory retrieval requirements, not question/answer templates.

This catalogue covers mechanisms. Matching a topic never proves applicability
or legal authority. Missing corpus entries remain missing, not invented rules.
"""
import re
from .models import LegalLocator
from .claim_validation import fold

def accident_facets(query):
    """Requested duties only; an injury narrative does not prove entitlement."""
    from .topics import occupational_accident_context
    q=fold(query)
    if (any(t in q for t in ('hoc sinh','sinh vien')) and not any(t in q for t in ('hop dong lao dong','lam viec co tra cong'))
            or not occupational_accident_context(query)):
        return False,False
    aid=any(t in q for t in ('so cuu','cap cuu'))
    medical=any(t in q for t in ('chi phi y te','chi phi dieu tri','chi phi kham','chi phi chua benh')) or (
        aid and any(t in q for t in ('thanh toan','chi phi')) and 'chi phi dieu tra' not in q)
    return aid,medical

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
    temporal_selection=facts.get('query_intent')=='TEMPORAL_LAW_SELECTION'
    if temporal_selection:
        clauses('labour_code_effectiveness',240 if old else 220,[1])
        if has('hop dong','thoa uoc','thoa thuan'):
            clauses('labour_contract_transition',240 if old else 220,[2])
        return out
    from .dispute_context import individual_mediation_requested,mediation_only
    if individual_mediation_requested(analysis.query_text):
        selected=[]
        if has('sa thai','don phuong cham dut'):selected.append('a')
        overseas=has('lam viec o nuoc ngoai','di lam viec o nuoc ngoai') and has('boi thuong','thiet hai')
        if overseas:selected.append('đ')
        elif has('boi thuong','tro cap thoi viec','tro cap mat viec'):selected.append('b')
        if has('giup viec gia dinh'):selected.append('c')
        if has('bao hiem xa hoi','bao hiem y te','bao hiem that nghiep','bhxh','bhyt'):selected.append('d')
        if not old and has('lao dong thue lai','nguoi lao dong thue lai'):selected.append('e')
        article=201 if old else 188
        if selected:points('individual_mediation_rule',article,1,list(dict.fromkeys(selected)))
        else:out['individual_mediation_rule']=[[loc(article,1)]]
    from .topics import occupational_accident_context
    employee_scope=(not has('hoc sinh','sinh vien') or has('hop dong lao dong','lam viec co tra cong'))
    if employee_scope and occupational_accident_context(analysis.query_text) and (not analysis.query_date or analysis.query_date>='2016-07-01'):
        aid,medical=accident_facets(analysis.query_text)
        if aid:clauses('accident_first_aid',38,[1],['84/2015/QH13'])
        if medical:
            clauses('accident_medical_costs',38,[2],['84/2015/QH13'])
            # A request for the complete cost list needs the branches, not just
            # an introductory clause. A narrow payer question must not acquire
            # an unrelated requirement to enumerate every insurance category.
            complete_list=bool(re.search(r'(?:cac|nhung|toan bo|moi)[^.;?!]{0,40}chi phi|chi phi[^.;?!]{0,25}(?:nao|bao gom|gom|nhung gi)',q))
            if complete_list:
                out['accident_medical_costs'] += [[loc(38,2,point,['84/2015/QH13'],exact=True)] for point in ('a','b','c')]
    if has('giao ket','ung vien','tuyen dung') and has('cung cap','thong tin','thong bao') and not facts.get('termination_basis'):
        clauses('employer_information',19 if old else 16,[1])
    from .termination_context import contract_expiry_context,contract_continuation_facets
    expiry=contract_expiry_context(q)
    facets=contract_continuation_facets(q)
    continuation=expiry and has('tiep tuc lam viec','van di lam','van lam','van tiep tuc','ky tiep','hop dong moi','ky moi','hop dong cu','loai hop dong','thuoc loai nao','moc thoi gian')
    renewal='RENEWAL_COUNT' in facets
    if continuation or renewal:
        selected=[]
        if 'RIGHTS' in facets or 'CONVERSION' in facets:selected.append('a')
        if 'CONVERSION' in facets:selected.append('b')
        if renewal:selected.append('c')
        points('term_contract_renewal',22 if old else 20,2,selected if not old else [],docs)
        if old:clauses('term_contract_renewal',22,[2])
        elif renewal:
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
    if has('ky luat') and has('chung minh','loi cua nguoi lao dong','vo toi'):
        points('disciplinary_proof_burden',123 if old else 122,1,['a'])
    if has('thu tuc','trinh tu','quy trinh','cuoc hop') and has('ky luat','sa thai') and not mediation_only(analysis.query_text):
        out['discipline_procedure']=[[loc(123 if old else 122,1)]]
        if not old: out['discipline_implementing_procedure']=[[loc(70,documents=['145/2020/NĐ-CP'])]]
    if has('ky luat','cuoc hop ky luat') and has('danh','bao luc','xam pham','nhuc ma','xuc pham','hanh hung'):
        clauses('discipline_prohibited_acts',128 if old else 127,[1])
    if has('tam dinh chi cong viec'):
        article=129 if old else 128
        # Each facet needs its own operative provision. These are source
        # requirements, not a finding that the employer met the prerequisites.
        payment=has('luong','tam ung','hoan tra','tra lai')
        if payment and has('khong bi xu ly ky luat','khong xu ly ky luat'):
            clauses('work_suspension_full_wage',article,[4])
        elif payment and has('bi xu ly ky luat','van bi ky luat'):
            clauses('work_suspension_advance_return',article,[3])
        elif payment:
            clauses('work_suspension_wage_outcomes',article,[2,3,4])
        if has('thoi han','bao lau','bao nhieu ngay','tam ung'):
            clauses('work_suspension_duration_advance',article,[2])
        if has('dieu kien','thu tuc','co duoc','co quyen','hop phap','dung khong') or not payment:
            clauses('work_suspension_prerequisites',article,[1])
    if ('MINOR_WORKER' in getattr(analysis,'legal_issues',[]) or facts.get('minor') is True) and has('gio','thoi gio','lam them','ban dem','lam dem','tang ca'):
        age=facts.get('age')
        if old:
            # The 2012 code groups both working-hour age bands in clause 2;
            # clause 3 separately covers permitted overtime/night occupations.
            branches=[2]
            if (not isinstance(age,int) or age>=15) and has('lam them','ban dem','lam dem','tang ca'):
                branches.append(3)
        else:
            branches=[1] if isinstance(age,int) and age<15 else [2] if isinstance(age,int) and age<18 else [1,2]
        clauses('minor_working_time',163 if old else 146,branches)
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
    if not old and has('tu choi','roi bo noi lam viec') and has('nguy hiem','nguy co','khong an toan','de doa'):
        out['dangerous_work_refusal_labour_code']=[[loc(5,1,'d')]]
        out['dangerous_work_refusal_safety_law']=[[loc(6,1,'đ',documents=['84/2015/QH13'])]]
    if has('bhtn','bao hiem that nghiep','tro cap that nghiep') and has('huong','nhan','dieu kien','tro cap'):
        if not analysis.query_date or analysis.query_date>='2026-01-01':
            points('unemployment_eligibility',38,1,['a','b','c','d'],['74/2025/QH15'])
        elif analysis.query_date>='2015-01-01':
            out['unemployment_eligibility']=[[loc(49,c,documents=['38/2013/QH13'])] for c in (1,2,3,4)]
    if has('bhyt','bao hiem y te') and not has('chi phi dao tao','trong thoi gian dao tao'):
        # These documents may be absent. Article 13 BLLD cannot fill this slot.
        out['health_insurance_subjects']=[[loc(12,documents=['25/2008/QH12','46/2014/QH13'])]]
        if not analysis.query_date or analysis.query_date>='2025-07-01':
            out['health_insurance_current_amendment']=[[loc(1,documents=['51/2024/QH15'])]]
    personal_data=(has('du lieu ca nhan','thong tin ca nhan','sinh trac','camera') or bool(
        re.search(r'du lieu[^.;?!]{0,55}(?:nguoi lao dong|nhan vien|ung vien)',q)))
    if personal_data and has('nguoi lao dong','nld','nsdld','tuyen dung','nhan vien'):
        if not analysis.query_date or analysis.query_date>='2026-01-01':
            out['employee_data_processing']=[[loc(25,documents=['91/2025/QH15'])]]
            out['data_processing_lawful_basis']=[[loc(19,documents=['91/2025/QH15'])]]
        else: out['data_processing_lawful_basis']=[[loc(11,documents=['13/2023/NĐ-CP'])]]
    if not temporal_selection and has('phien ban luat','phien ban phap luat','citation cu','hieu luc phap ly','van ban cu') and has('thoi diem','nam','hieu luc','van ban moi','chon'):
        out['application_of_normative_documents']=[[loc(58,documents=['64/2025/QH15'])]]
    # False positives are hints, never conclusions; the semantic review still
    # checks question relevance and conditions against the actual source text.
    return out
