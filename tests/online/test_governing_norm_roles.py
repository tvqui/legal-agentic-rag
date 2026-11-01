import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.evidence import state_for,select_for_plan
from vn_labor_online.legal_metadata import norm_role
from vn_labor_online.models import Evidence,EvidencePlan,SlotStatus

def source(uid,text,title='Quy định thử nghiệm',score=1):
 return Evidence(unit_id=uid,text=text,document_number='TEST/2099',document_title=title,
  provision_version_id=uid,kind='PROVISION',verified=True,retrieval_method='bm25',score=score)

class GoverningNormRoleTests(unittest.TestCase):
 def test_prohibition_of_monetary_punishment_is_not_a_penalty_schedule(self):
  self.assertEqual(norm_role('TEST/2099','Hành vi bị cấm','Dùng hình thức phạt tiền để xử lý vi phạm.'),'RULE')
 def test_an_actual_penalty_amount_has_sanction_role(self):
  self.assertEqual(norm_role('TEST/2099','Chế tài','Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng.'),'SANCTION')
 def test_unrequested_penalty_is_not_the_only_governing_rule_for_legality(self):
  plan=plan_evidence(analyze(intake('Nơi làm việc bắt tôi nộp một khoản tiền vì vi phạm nội quy. Có được phép không?',[]),'2026-09-15'))
  self.assertEqual(plan.governing_roles,['RULE'])
  penalty=source('p','Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng.','Xử phạt hành chính')
  self.assertIn('governing_rule',state_for([penalty],plan,'2026-09-15',True).gaps)
 def test_explicit_penalty_assessment_can_use_a_penalty_source(self):
  plan=plan_evidence(analyze(intake('Mức xử phạt hành chính trong quyết định này có đúng không?',[]),'2026-09-15'))
  self.assertIn('SANCTION',plan.governing_roles)
 def test_selection_preserves_rule_before_high_scoring_unasked_sanction(self):
  plan=EvidencePlan(mandatory_slots=['governing_rule'],governing_roles=['RULE'])
  penalty=source('penalty','Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng.','Xử phạt hành chính',99)
  rule=source('rule','Người giao việc không được buộc bên nhận việc nộp tiền.','Quy định về nghĩa vụ',1)
  selected,state=select_for_plan([penalty,rule],plan,'2026-09-15',True,1)
  self.assertEqual([e.unit_id for e in selected],['rule'])
  self.assertEqual(state.slots['governing_rule'].status,SlotStatus.FOUND_VERIFIED)
 def test_role_selection_never_approves_unverified_text(self):
  rule=source('rule','Không được yêu cầu nộp tiền.');rule.verified=False
  state=state_for([rule],EvidencePlan(mandatory_slots=['governing_rule'],governing_roles=['RULE']),None)
  self.assertEqual(state.slots['governing_rule'].status,SlotStatus.MISSING)

class PersonalEvidenceScopeTests(unittest.TestCase):
 def test_personal_multi_issue_case_does_not_require_unasked_leave_groups(self):
  q=('Tôi 31 tuổi, không bị khuyết tật, làm việc đủ 12 tháng trong điều kiện bình thường. '
    'Công ty giữ chứng chỉ gốc và chỉ cho 5 ngày phép năm. Hãy kết luận riêng từng việc.')
  p=plan_evidence(analyze(intake(q,[]),'2026-09-15'))
  self.assertEqual([group[0].point for group in p.slot_requirements['leave_base_rule']],['a'])
  self.assertIn('prohibited_contract_acts',p.slot_requirements)
 def test_explicit_group_comparison_retains_all_requested_alternatives(self):
  q='Tôi làm việc trong điều kiện bình thường. Hãy liệt kê và so sánh tất cả các nhóm ngày phép năm.'
  p=plan_evidence(analyze(intake(q,[]),'2026-09-15'))
  self.assertEqual([group[0].point for group in p.slot_requirements['leave_base_rule']],['a','b','c'])
 def test_distinct_special_and_protected_categories_are_not_collapsed(self):
  q='Tôi là người khuyết tật, làm công việc đặc biệt nặng nhọc đủ 12 tháng. Số ngày phép năm là bao nhiêu?'
  p=plan_evidence(analyze(intake(q,[]),'2026-09-15'))
  self.assertEqual([group[0].point for group in p.slot_requirements['leave_base_rule']],['b','c'])
 def test_original_document_order_variants_preserve_the_same_issue(self):
  from vn_labor_online.taxonomy import original_documents
  for q in ['Công ty giữ chứng chỉ gốc của tôi.', 'Tôi phải nộp hộ chiếu bản gốc cho công ty.',
    'Người sử dụng lao động thu căn cước gốc để bảo đảm làm việc.']:
   with self.subTest(q=q):self.assertTrue(original_documents(q))
 def test_copy_only_does_not_establish_retention_of_original(self):
  from vn_labor_online.taxonomy import original_documents
  self.assertFalse(original_documents('Công ty yêu cầu giao bản sao chứng chỉ đã công chứng.'))

if __name__=='__main__':unittest.main()
