import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence

class AgeScopedWorkingTimeTests(unittest.TestCase):
    def analysis(self,q,date='2026-09-15'):return analyze(intake(q,[]),date)
    def test_numeric_worker_age_drives_minor_rule_without_category_keyword(self):
        a=self.analysis('Người lao động 13 tuổi được bố trí làm 5 giờ/ngày và làm thêm vào ban đêm có được không?')
        self.assertIn('MINOR_WORKER',a.legal_issues)
        plan=plan_evidence(a)
        self.assertTrue(any(loc.article=='146' and loc.clause=='1' for groups in plan.slot_requirements.values() for group in groups for loc in group))
        self.assertNotIn('WAGE.NIGHT_PAY',a.legal_subissues)
        self.assertNotIn('WAGE.OVERTIME_PAY',a.legal_subissues)
    def test_older_minor_uses_its_own_age_branch(self):
        a=self.analysis('Nhân viên 17 tuổi làm việc 9 giờ mỗi ngày, không hỏi về tiền lương. Giới hạn thời giờ áp dụng ra sao?')
        plan=plan_evidence(a)
        self.assertTrue(any(loc.article=='146' and loc.clause=='2' for groups in plan.slot_requirements.values() for group in groups for loc in group))
    def test_historical_question_uses_historical_minor_hours(self):
        a=self.analysis('Người lao động 14 tuổi được làm thêm hoặc làm ban đêm không?','2020-05-03')
        plan=plan_evidence(a)
        self.assertTrue(any(loc.article=='163' for groups in plan.slot_requirements.values() for group in groups for loc in group))
    def test_age_alone_does_not_turn_passport_question_into_labour(self):
        a=self.analysis('Tôi 17 tuổi xin hộ chiếu phổ thông thì nộp hồ sơ ở đâu?')
        self.assertFalse(a.in_scope)
        self.assertNotIn('MINOR_WORKER',a.legal_issues)
    def test_explicitly_excluded_pay_is_not_reintroduced_as_another_task(self):
        a=self.analysis('Người lao động 14 tuổi có được làm thêm vào ban đêm không? Chỉ hỏi giới hạn thời giờ, không hỏi tiền lương.')
        self.assertNotIn('WAGE.NIGHT_PAY',a.legal_subissues)
        self.assertNotIn('WAGE.OVERTIME_PAY',a.legal_subissues)
        self.assertFalse(any('wage_payment' in t.topic_ids for t in a.answer_tasks))
    def test_pay_request_still_keeps_night_and_overtime_pay(self):
        a=self.analysis('Tôi làm thêm vào ban đêm. Tiền lương phải được trả theo tỷ lệ nào?')
        self.assertIn('WAGE.NIGHT_PAY',a.legal_subissues)
        self.assertIn('WAGE.OVERTIME_PAY',a.legal_subissues)

if __name__=='__main__':unittest.main()
