import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence

class PaymentCycleVsCompensationTests(unittest.TestCase):
    def analysis(self,q):return analyze(intake(q,[]),'2026-09-15')
    def test_compensation_multiplier_is_not_wage_frequency(self):
        for q in ['Người lao động nghỉ trái luật có phải bồi thường nửa tháng tiền lương và tiền của ngày không báo trước không?',
                  'Công ty đã chấm dứt trái pháp luật. Bồi thường hai tháng lương có phải trả không?']:
            a=self.analysis(q)
            self.assertNotIn('WAGE.PAYMENT_CYCLE',a.legal_subissues)
    def test_actual_half_month_payment_schedule_remains(self):
        for q in ['Công ty trả lương nửa tháng một lần có được không?',
                  'Tôi nhận lương theo tháng, có được trả mỗi nửa tháng không?']:
            self.assertIn('WAGE.PAYMENT_CYCLE',self.analysis(q).legal_subissues)
    def test_explicit_schedule_question_is_kept_alongside_compensation(self):
        a=self.analysis('Tôi nghỉ trái luật phải bồi thường nửa tháng lương không? Và kỳ trả lương của công ty được quy định thế nào?')
        self.assertIn('WAGE.PAYMENT_CYCLE',a.legal_subissues)
    def test_specific_stipulated_consequence_does_not_require_other_consequences(self):
        a=self.analysis('Người lao động đã đơn phương nghỉ trái luật. Họ có phải bồi thường nửa tháng lương và tiền ngày không báo trước không?')
        plan=plan_evidence(a)
        locators=[loc for group in plan.slot_requirements['legal_consequences'] for loc in group]
        self.assertEqual({loc.clause for loc in locators},{'2'})
    def test_open_ended_request_retains_all_consequences(self):
        a=self.analysis('Người lao động đã đơn phương nghỉ trái luật. Họ phải chịu những hậu quả gì?')
        plan=plan_evidence(a)
        self.assertEqual({loc.clause for group in plan.slot_requirements['legal_consequences'] for loc in group},{'1','2','3'})

if __name__=='__main__':unittest.main()
