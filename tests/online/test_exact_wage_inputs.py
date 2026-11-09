import unittest
from vn_labor_online.analysis import analyze,intake

class ExactWageInputsTests(unittest.TestCase):
    def analysis(self,q):return analyze(intake(q,[]),'2026-09-15')
    def test_exact_mixed_night_holiday_amount_needs_operands(self):
        a=self.analysis('Tôi làm việc ngày lễ và có cả giờ ban đêm. Công ty phải trả cho tôi chính xác bao nhiêu tiền?')
        self.assertTrue(any('lương' in q and ('căn cứ' in q or 'giờ' in q) for q in a.missing_facts))
        self.assertTrue(any('giờ' in q and ('số' in q or 'bao nhiêu' in q) for q in a.missing_facts))
    def test_generic_rates_do_not_require_personal_wage_operands(self):
        a=self.analysis('Làm thêm giờ ban đêm vào ngày lễ được hưởng những tỷ lệ lương nào?')
        self.assertFalse(a.missing_facts)
    def test_formula_question_can_be_answered_without_personal_operands(self):
        a=self.analysis('Cách tính tiền làm thêm giờ ban đêm theo luật như thế nào?')
        self.assertFalse(a.missing_facts)
    def test_supplied_hourly_base_and_hours_are_not_requested_again(self):
        a=self.analysis('Tôi làm thêm 3 giờ ban đêm vào ngày lễ. Lương giờ của công việc là 60.000 đồng/giờ. Hãy tính số tiền được trả.')
        self.assertFalse(any('căn cứ' in q or 'Số giờ' in q for q in a.missing_facts))

    def test_holiday_work_selects_the_payment_rule_without_magic_overtime_word(self):
        a=self.analysis('Tôi đi làm vào một ngày nghỉ lễ và có cả giờ làm ban đêm. Tôi được trả bao nhiêu tiền?')
        self.assertIn('WAGE.OVERTIME_PAY',a.legal_subissues)
        self.assertIn('WAGE.NIGHT_PAY',a.legal_subissues)
    def test_negated_holiday_work_does_not_create_overtime_task(self):
        a=self.analysis('Tôi không đi làm vào ngày lễ. Tôi hỏi tiền lương làm ban đêm tính theo tỷ lệ nào?')
        self.assertNotIn('WAGE.OVERTIME_PAY',a.legal_subissues)

if __name__=='__main__':unittest.main()
