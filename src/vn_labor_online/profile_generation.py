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
    'CONTRACT.PROBATION_DURATION','CONTRACT.PROBATION_REPEAT','CONTRACT.PROBATION_SANCTION',
    'TRAINING.RELATIONSHIP_COMPARISON','TRAINING.APPRENTICESHIP',
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
    if keys.intersection({'CONTRACT.PROBATION_SANCTION','CONTRACT.PROBATION_DURATION'}): allowed.add('CONTRACT.PROBATION_PAY')
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
    if keys=={'CONTRACT.PROBATION_REPEAT'}:
        item=used[0]
        if 'mot lan' not in fold(item.text) or 'mot cong viec' not in fold(item.text): return None
        text=(f'Điều {item.article} ({item.instrument_number}): chỉ được thử việc một lần đối với một công việc. '
          'Nếu thực chất thử việc lần thứ hai cho cùng một công việc thì không phù hợp quy định này.')
        from .generation import _versions
        return AdjudicationDraft(answer_summary=f'{text} [{item.evidence_id}]',claims=[Claim(claim_id='claim_probation_once',text=text,evidence_ids=[item.evidence_id])],
          applicable_law_versions=_versions(used),assumptions=assumptions or [],limitations=pack.coverage_state.gaps)
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
        if item.instrument_number=='12/2022/NĐ-CP' and item.article=='6' and item.clause=='1':
            # Cite the needed sentence, not a chapter numeral corrupted by OCR.
            match=re.search(r'Mức phạt tiền đối với tổ chức[^.]*\.',text,re.I)
            if not match or '02 lan' not in fold(match.group()) and '2 lan' not in fold(match.group()): return None
            text=match.group()
        claim=Claim(claim_id=f'claim_profile_{len(claims)+1:03d}',
          text=f'{location} ({item.instrument_number}): “{text}”',evidence_ids=[item.evidence_id])
        if item.instrument_number=='12/2022/NĐ-CP' and (item.article,item.clause,item.point)==('10','3','a') and 'tra du tien luong' in fold(text):
            claim=claim.model_copy(update={'text':f'{location} ({item.instrument_number}): buộc người sử dụng lao động trả đủ tiền lương của công việc đó cho người lao động khi có hành vi vi phạm tại điểm a khoản 1 hoặc điểm a, b, c khoản 2 Điều 10.'})
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
        duration=re.search(r'thu viec[^.]{0,50}\b(\d+)\s*(ngay|thang)\b',query)
        if duration:
            intro=('Chưa thể kết luận chỉ từ thời gian '+duration.group(1)+' '+('tháng' if duration.group(2)=='thang' else 'ngày')+'. '
              'Cần biết nhóm công việc và công việc đó yêu cầu trình độ nào; bằng cấp của cá nhân không tự xác định nhóm công việc. '
              'Ví dụ 60 ngày không vượt mức 60 ngày của nhóm từ cao đẳng trở lên hoặc mức 180 ngày của quản lý doanh nghiệp, '
              'nhưng vượt mức 30 ngày và 06 ngày làm việc của các nhóm còn lại. '+intro) if not historical else (
              'Cần xác định nhóm công việc theo pháp luật có hiệu lực tại ngày hỏi; không dùng mức 180 ngày của luật bắt đầu áp dụng năm 2021. '+intro)
        group=pack.facts.get('probation_work_group')
        limit={'MANAGER':180,'COLLEGE':60,'INTERMEDIATE':30,'OTHER':6}.get(group)
        if historical and group=='MANAGER': limit=None
        if duration and duration.group(2)=='ngay' and limit is not None:
            working=bool(re.search(r'thu viec[^.]{0,50}\b\d+\s*ngay lam viec\b',query))
            comparable=(group=='OTHER' and working or group!='OTHER' and not working)
            if comparable:
                count=int(duration.group(1)); unit='ngày làm việc' if group=='OTHER' else 'ngày'
                intro=(f'Về thời gian: với nhóm công việc bạn nêu, {count} {unit} '+
                  (f'vượt mức tối đa {limit} {unit}.' if count>limit else f'không vượt mức tối đa {limit} {unit}.')+
                  ' Kết luận này chỉ xét giới hạn thời gian, không xác nhận các điều kiện thử việc khác. Các căn cứ là:')
    elif 'CONTRACT.PROBATION_DURATION' in keys and 'CONTRACT.PROBATION_PAY' in keys:
        from .generation import probation_pay_application
        application=probation_pay_application(pack.query)
        intro=('Phải kiểm tra riêng tiền lương và thời gian thử việc. Điều 26 yêu cầu ít nhất 85% mức lương của công việc đó. '+application+
          ' Thời gian thử việc còn phụ thuộc nhóm công việc; không tự chuyển tháng thành một số ngày cố định hoặc kết luận thời gian hợp pháp khi chưa rõ nhóm. Các căn cứ cho cả hai phần là:')
    elif 'CONTRACT.PROBATION_SANCTION' in keys:
        intro=('Quy định về thử việc nằm trong Bộ luật Lao động; chế tài và khắc phục là vấn đề khác, tại Nghị định 12/2022/NĐ-CP. '
          'Đọc mức phạt ở Điều 10 cùng khoản 1 Điều 6: mức phạt đối với tổ chức bằng hai lần mức phạt đối với cá nhân. '
          'Cần xác định hành vi, chủ thể và thời điểm vi phạm, không chỉ nêu mức phạt của cá nhân cho một công ty:')
    elif 'TRAINING.RELATIONSHIP_COMPARISON' in keys:
        historical=bool(pack.query_date and pack.query_date<'2021-01-01')
        intro=('Phải phân biệt theo bản chất quan hệ, không chỉ theo tên gọi: thực tập theo chương trình của trường cần kiểm tra chương trình và thỏa thuận thực tập, '
          'không tự động đồng nhất với tập nghề để làm việc cho công ty. Tập nghề do công ty tuyển để hướng dẫn thực hành theo Điều 61; '
          'thử việc là thỏa thuận đánh giá công việc theo Điều 24 và có mức lương tối thiểu theo Điều 26; '
          'nếu quan hệ thực tế có việc làm trả công và sự quản lý, điều hành, giám sát thì cần đối chiếu Điều 13. Các căn cứ cho từng nhánh là:')
        if historical:
            intro=('Theo Bộ luật Lao động 2012 tại ngày tra cứu, cần phân biệt thỏa thuận lao động ở Điều 15, thỏa thuận thử việc ở Điều 26, tiền lương thử việc ở Điều 28, và học nghề/tập nghề để làm việc cho người sử dụng lao động ở Điều 61. Thực tập theo chương trình của trường cần kiểm tra chương trình và thỏa thuận, không tự đồng nhất với học/tập nghề do công ty tuyển. Các căn cứ là:')
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
