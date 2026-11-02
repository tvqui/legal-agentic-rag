import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence

class OperatingRulePlanTests(unittest.TestCase):
    def plan(self,q,date='2026-09-15'):
        a=analyze(intake(q,[]),date)
        return a,plan_evidence(a)
    def test_week_based_actual_schedules_require_the_week_based_rule(self):
        for q in ['Tôi làm 9 giờ mỗi ngày, công ty bố trí thời giờ làm việc theo tuần, không làm thêm. Có vi phạm không?',
                  'Bố trí theo tuần, làm 10 giờ trong 1 ngày và 48 giờ một tuần thì có đúng luật không?',
                  'Lịch làm việc tính theo tuần, mỗi ngày 9 giờ thì có thể kết luận vi phạm không?']:
            with self.subTest(q=q):
                a,p=self.plan(q)
                self.assertIn('WORKING_TIME.NORMAL_HOURS',a.legal_subissues)
                self.assertEqual({loc.clause for group in p.slot_requirements['normal_working_hours'] for loc in group},{'2'})
    def test_historical_week_rule_uses_the_historical_document(self):
        a,p=self.plan('Thời giờ làm việc bình thường tính theo tuần tối đa bao nhiêu giờ?','2020-07-04')
        for group in p.slot_requirements['normal_working_hours']:
            self.assertEqual(group[0].documents,['10/2012/QH13'])
            self.assertEqual((group[0].article,group[0].clause),('104','2'))
    def test_overtime_pay_does_not_become_a_normal_hour_assessment(self):
        a,p=self.plan('Làm thêm 3 giờ thì được trả tiền lương thế nào?')
        self.assertNotIn('WORKING_TIME.NORMAL_HOURS',a.legal_subissues)
    def test_no_discipline_wage_branch_does_not_require_all_outcomes(self):
        _,p=self.plan('Không bị xử lý kỷ luật sau khi tạm đình chỉ công việc, người lao động được trả lương thế nào?')
        groups=p.slot_requirements['work_suspension_full_wage']
        self.assertEqual([(loc.article,loc.clause) for group in groups for loc in group],[('128','4')])
        self.assertNotIn('work_suspension_wage_outcomes',p.slot_requirements)
    def test_uncertain_disciplinary_outcome_preserves_both_wage_branches(self):
        _,p=self.plan('Các trường hợp trả lương khi tạm đình chỉ công việc được quy định thế nào?')
        self.assertEqual([g[0].clause for g in p.slot_requirements['work_suspension_wage_outcomes']],['2','3','4'])
    def test_procedure_is_an_independent_required_facet(self):
        _,p=self.plan('Điều kiện tạm đình chỉ công việc và tiền lương tạm ứng là gì?')
        self.assertIn('work_suspension_prerequisites',p.slot_requirements)
        self.assertIn('work_suspension_duration_advance',p.slot_requirements)
    def test_old_suspension_wage_does_not_use_current_article(self):
        _,p=self.plan('Không bị xử lý kỷ luật sau khi tạm đình chỉ công việc thì tiền lương thế nào?','2019-08-02')
        loc=p.slot_requirements['work_suspension_full_wage'][0][0]
        self.assertEqual((loc.documents,loc.article,loc.clause),(['10/2012/QH13'],'129','4'))
if __name__=='__main__':unittest.main()
