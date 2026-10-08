"""Render complete, dated rule chains from vetted source text without inference.

These profiles explain rules, not disputed facts. Current-law templates cannot
run on historical evidence. Every listed branch has its own source/locator.
"""
from __future__ import annotations
import re
from .analysis import analyze,intake,plan_evidence
from .claim_validation import fold
from .models import Claim,AdjudicationDraft,LegalLocator,RuleProposition
from .taxonomy import locator_matches

PROFILE_KEYS={
    'CONTRACT.PROBATION_DURATION','TRAINING.APPRENTICESHIP',
    'TRAINING.COST_REPAYMENT','WORKING_TIME.OVERTIME_LIMITS',
    'WAGE.OVERTIME_PAY','WAGE.NIGHT_PAY',
}

def _matches(item, locator):
    return locator_matches({'kind':'PROVISION','document_number':item.instrument_number,
      'article_number':item.article,'clause_number':item.clause,'point_number':item.point,
      'source_text':item.text,'text':item.text},locator)

def render_profile(pack,partial,assumptions):
    analysis=analyze(intake(pack.query,[],pack.query_date,pack.facts),pack.query_date,pack.facts)
    keys=set(analysis.legal_subissues)
    if not keys.intersection(PROFILE_KEYS): return None
    # Do not shortcut a question with a separate issue needing adjudication.
    allowed=PROFILE_KEYS|{'TERMINATION.ILLEGAL_TERMINATION','TERMINATION.EMPLOYEE_LIABILITY'}
    if keys-allowed: return None
    plan=plan_evidence(analysis)
    used=[]
    for groups in plan.slot_requirements.values():
        for group in groups:
            matches=[item for item in pack.evidence if any(_matches(item,loc) for loc in group)]
            if not matches: return None
            matches.sort(key=lambda item:(item.instrument_number!='18/VBHN-VPQH',
              sum(bool(value) for value in (item.clause,item.point)),len(item.text),item.evidence_id))
            chosen=matches[0]
            if chosen.evidence_id not in {item.evidence_id for item in used}: used.append(chosen)
    if not used: return None
    claims=[]
    query=fold(pack.query)
    explain_chain=(all(word not in query for word in ('cong thuc','tinh tien','tinh luong','bao nhieu'))
      and any(word in query for word in ('ket hop','quy dinh nao','can cu nao')))
    for item in used:
        text=' '.join(item.text.split())
        if not text: return None
        location=' '.join(x for x in (f'Điều {item.article}' if item.article else '',
          f'khoản {item.clause}' if item.clause else '',f'điểm {item.point}' if item.point else '') if x)
        # A known V8.1 extraction joins the amended fee clause to clause 2.
        # Disclose the stored boundary; never silently relabel it as clause 3.
        if item.article=='61' and item.clause=='2' and re.search(r'\b3\.\d+\s+Người sử dụng lao động',text):
            location='Điều 61 (đoạn nguồn đang gộp khoản 2–3; cần kiểm tra lại ranh giới khoản)'
        claim=Claim(claim_id=f'claim_profile_{len(claims)+1:03d}',
          text=f'{location} ({item.instrument_number}): “{text}”',evidence_ids=[item.evidence_id])
        if explain_chain and item.instrument_number=='145/2020/NĐ-CP' and item.article=='57':
            # Rule-chain queries need the role of each provision, rather than
            # a flattened PDF formula. Formula/calculation requests retain it.
            explanation={
              ('1',''): 'hướng dẫn cách tính tiền lương làm thêm giờ vào ban đêm đối với người lao động hưởng lương theo thời gian.',
              ('1','b'): 'xác định tiền lương giờ vào ban ngày theo từng loại ngày làm căn cứ tính tiền lương làm thêm vào ban đêm; với ngày lễ, tết, ngày nghỉ có hưởng lương, mức ít nhất bằng 300% tiền lương giờ thực trả của ngày làm việc bình thường.',
              ('2',''): 'hướng dẫn cách tính tiền lương làm thêm giờ vào ban đêm đối với người lao động hưởng lương theo sản phẩm, theo đơn giá và số sản phẩm làm thêm vào ban đêm.',
            }.get((item.clause or '',item.point or ''))
            if explanation: claim=claim.model_copy(update={'text':f'{location} ({item.instrument_number}) {explanation}'})
        if keys=={'CONTRACT.PROBATION_DURATION'}:
            m=re.search(r'khong qua (\d+) (ngay lam viec|ngay)',fold(text))
            if not m: return None
            claim=claim.model_copy(update={'proposition':RuleProposition(predicate='PROBATION_LIMIT',
              value=int(m.group(1)),unit='ngày làm việc' if m.group(2)=='ngay lam viec' else 'ngày',
              locator=LegalLocator(documents=[item.instrument_number],article=item.article,clause=item.clause))})
        claims.append(claim)
    if keys=={'CONTRACT.PROBATION_DURATION'}:
        historical=all(item.instrument_number=='10/2012/QH13' for item in used)
        expected={60,30,6} if historical else {180,60,30,6}
        if {claim.proposition.value for claim in claims}!=expected: return None
        intro='Thời gian thử việc tối đa theo từng nhóm công việc được quy định như sau. Chỉ mức 06 ngày được tính theo ngày làm việc; các mức còn lại là ngày:'
    elif 'TRAINING.COST_REPAYMENT' in keys:
        liability_article='43' if pack.query_date and pack.query_date<'2021-01-01' else '40'
        intro=(f'Với giả định người lao động đã đơn phương chấm dứt trái pháp luật, cần đối chiếu nghĩa vụ tại Điều {liability_article} và các nội dung, chi phí có chứng từ trong Điều 62:'
          if pack.facts.get('query_intent')=='STIPULATED_EMPLOYEE_LIABILITY' else
          'Không thể khẳng định cứ nghỉ trước thời hạn cam kết là phải trả mọi khoản công ty yêu cầu. Cần đối chiếu hợp đồng đào tạo, trách nhiệm hoàn trả và chi phí có chứng từ theo các quy định dưới đây:')
    elif 'TRAINING.APPRENTICESHIP' in keys:
        intro='Học nghề và tập nghề để làm việc cho người sử dụng lao động khác với thực tập theo chương trình của trường. Các quy định trực tiếp trong bộ dữ liệu gồm:'
    elif 'WORKING_TIME.OVERTIME_LIMITS' in keys:
        intro='Giới hạn làm thêm giờ gồm điều kiện đồng ý, giới hạn theo ngày/tháng/năm và điều kiện áp dụng mức đến 300 giờ/năm. Đây là quy tắc trong phiên bản dữ liệu được tra cứu:'
    elif 'WAGE.NIGHT_PAY' in keys and 'WAGE.OVERTIME_PAY' in keys:
        intro='Phải kết hợp tiền lương làm thêm giờ, khoản trả thêm khi làm ban đêm và khoản trả thêm khi làm thêm vào ban đêm; không chỉ áp dụng một trong các khoản. Nếu là ngày lễ thì dùng mức dành cho ngày lễ trong công thức:'
    elif 'WAGE.OVERTIME_PAY' in keys:
        intro='Tiền lương làm thêm giờ là nghĩa vụ theo các mức tối thiểu dưới đây. Việc đồng ý làm thêm không tự thay thế nghĩa vụ trả tiền lương làm thêm:'
    else:
        intro='Tiền lương khi làm việc ban đêm được trả thêm theo quy định dưới đây:'
    lines=[intro]+[f'- {claim.text} [{claim.evidence_ids[0]}]' for claim in claims]
    if partial: lines.append('Metadata nguồn hoặc hiệu lực điều khoản còn chờ duyệt; kết quả hỗ trợ tra cứu theo bộ dữ liệu hiện có.')
    from .generation import _versions
    return AdjudicationDraft(answer_summary='\n'.join(lines),claims=claims,
      applicable_law_versions=_versions(used),assumptions=assumptions or [],limitations=pack.coverage_state.gaps)
