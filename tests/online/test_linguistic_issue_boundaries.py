import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.durations import probation_duration
from vn_labor_online.topics import detect_topics,_surface_phrase_matches

class LinguisticIssueBoundaryTests(unittest.TestCase):
 def test_supplied_tone_cannot_be_erased_into_an_unrequested_strike(self):
  for q in ['Có thể khẳng định công ty vi phạm giờ làm việc không?',
    'Cần xác định công việc và số giờ làm để đánh giá.']:
   with self.subTest(q=q):self.assertNotIn('strike',{t.key for t in detect_topics(q)})
 def test_actual_strike_remains_recognized_with_or_without_accents(self):
  for q in ['Điều kiện tiến hành đình công là gì?', 'dieu kien dinh cong la gi?',
    'Tôi muốn dinh cong có được không?']:
   with self.subTest(q=q):self.assertIn('strike',{t.key for t in detect_topics(q)})
 def test_orthographic_tone_position_variants_remain_equivalent(self):
  self.assertTrue(_surface_phrase_matches('Thủ tục hoà giải lao động là gì?','hòa giải'))
  self.assertTrue(_surface_phrase_matches('Nội dung thoả ước lao động tập thể.','thỏa ước lao động tập thể'))
 def test_later_contract_form_is_not_erased_by_earlier_probation(self):
  q=('Tôi thử việc ở công việc yêu cầu cao đẳng. Công ty cho thử 74 ngày; '
    'sau đó chỉ ký hợp đồng bằng lời nói trong thời hạn 22 tháng. Đánh giá riêng hai việc.')
  a=analyze(intake(q,[]),'2026-09-15');p=plan_evidence(a)
  self.assertIn('CONTRACT.PROBATION_DURATION',a.legal_subissues)
  self.assertIn('CONTRACT.FORM',a.legal_subissues)
  self.assertEqual(a.facts.get('probation_duration_value'),74)
  self.assertEqual(len(a.answer_tasks),2)
  self.assertIn('probation_duration',p.slot_requirements)
  self.assertIn('contract_form',p.slot_requirements)
 def test_oral_trial_agreement_is_not_automatically_an_oral_employment_contract(self):
  a=analyze(intake('Công ty và tôi thỏa thuận hợp đồng thử việc bằng lời nói thì có được không?',[]),'2026-09-15')
  self.assertNotIn('CONTRACT.FORM',a.legal_subissues)
 def test_short_trial_duration_requires_an_employment_anchor(self):
  self.assertEqual(probation_duration('Công ty cho thử trong 43 ngày.'),(43,'ngay'))
  self.assertIsNone(probation_duration('Cho thử món ăn trong 43 ngày.'))
  self.assertIsNone(probation_duration('Công ty cho thử máy trong 43 ngày.'))
 def test_short_durations_do_not_convert_calendar_units(self):
  self.assertEqual(probation_duration('Công ty cho thử hai tháng.'),(2,'thang'))
  self.assertIsNone(probation_duration('Công ty cho thử khoảng 43 ngày.'))
 def test_system_data_word_is_not_a_personal_data_processing_task(self):
  q=('Hãy nêu rõ nếu thiếu dữ liệu và không bịa số điều. Người sử dụng lao động '
    'giữ căn cước bản chính của nhân viên để bảo đảm tiếp tục làm việc có được không?')
  a=analyze(intake(q,[]),'2026-09-15');p=plan_evidence(a)
  self.assertIn('CONTRACT.PROHIBITED_ACTS',a.legal_subissues)
  self.assertIn('prohibited_contract_acts',p.slot_requirements)
  self.assertNotIn('employee_data_processing',p.slot_requirements)
 def test_actual_personal_data_processing_keeps_its_own_required_basis(self):
  q='Công ty thu thập dữ liệu vị trí của người lao động và thông tin cá nhân thì cần căn cứ nào?'
  p=plan_evidence(analyze(intake(q,[]),'2026-09-15'))
  self.assertIn('employee_data_processing',p.slot_requirements)
 def test_employment_supervision_criterion_is_not_a_privacy_processing_request(self):
  q='Người lao động làm việc có trả công và chịu sự giám sát thì quan hệ đó là gì?'
  p=plan_evidence(analyze(intake(q,[]),'2026-09-15'))
  self.assertNotIn('employee_data_processing',p.slot_requirements)
 def test_regular_work_hours_can_be_context_to_a_night_pay_question(self):
  q='Làm vào ban đêm trong giờ làm việc bình thường thì được trả thêm tối thiểu bao nhiêu?'
  a=analyze(intake(q,[]),'2026-09-15')
  self.assertIn('WAGE.NIGHT_PAY',a.legal_subissues)
  self.assertEqual(len(a.answer_tasks),1)
 def test_independent_night_hours_request_is_retained(self):
  q='Làm ban đêm được trả thêm bao nhiêu và được làm tối đa bao nhiêu giờ theo chế độ tuần?'
  a=analyze(intake(q,[]),'2026-09-15')
  self.assertGreaterEqual(len(a.answer_tasks),2)

if __name__=='__main__':unittest.main()
