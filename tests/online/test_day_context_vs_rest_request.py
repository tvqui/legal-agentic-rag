import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence


class DayContextVsRestRequestTests(unittest.TestCase):
    def test_day_category_selects_the_requested_wage_branch(self):
        for day,point in (('ngày làm việc bình thường','a'),('ngày nghỉ hằng tuần','b'),('ngày lễ','c')):
            a=analyze(intake(f'Tiền lương làm thêm vào {day} thấp nhất bằng bao nhiêu phần trăm?',[]),'2026-09-15')
            groups=plan_evidence(a).slot_requirements['overtime_pay']
            points={loc.point for group in groups for loc in group if loc.point}
            self.assertEqual(points,{point})
            self.assertNotIn('WORKING_TIME.WEEKLY_REST',a.legal_subissues)
            self.assertFalse(any('normal_hours' in task.topic_ids for task in a.answer_tasks))

    def test_comparison_keeps_all_explicitly_requested_day_categories(self):
        a=analyze(intake('So sánh tiền lương làm thêm ngày thường và ngày nghỉ hằng tuần.',[]),'2026-09-15')
        points={loc.point for group in plan_evidence(a).slot_requirements['overtime_pay'] for loc in group if loc.point}
        self.assertEqual(points,{'a','b'})

    def test_general_overview_keeps_all_day_branches(self):
        a=analyze(intake('Tiền lương làm thêm giờ được tính thế nào?',[]),'2026-09-15')
        points={loc.point for group in plan_evidence(a).slot_requirements['overtime_pay'] for loc in group if loc.point}
        self.assertEqual(points,{'a','b','c'})

    def test_distinct_rest_question_remains_a_required_task(self):
        a=analyze(intake('Làm thêm ngày nghỉ hằng tuần được trả lương thế nào? Đồng thời mỗi tuần được nghỉ bao nhiêu giờ liên tục?',[]),'2026-09-15')
        self.assertIn('WORKING_TIME.WEEKLY_REST',a.legal_subissues)
        self.assertIn('WAGE.OVERTIME_PAY',a.legal_subissues)

    def test_permission_for_a_stated_hour_quantity_is_a_limits_question(self):
        for question in ('Luật có cho phép làm thêm đến 280 giờ một năm trong một ngành sản xuất không?',
                         'Công ty cho tăng ca 47 giờ một tháng có hợp pháp không?'):
            a=analyze(intake(question,[]),'2026-09-15')
            self.assertIn('WORKING_TIME.OVERTIME_LIMITS',a.legal_subissues)
            self.assertIn('overtime_limits',plan_evidence(a).slot_requirements)

    def test_stated_overtime_used_only_for_pay_does_not_add_a_legality_task(self):
        a=analyze(intake('Tôi làm thêm 3 giờ, được trả bao nhiêu phần trăm tiền lương?',[]),'2026-09-15')
        self.assertIn('WAGE.OVERTIME_PAY',a.legal_subissues)
        self.assertNotIn('WORKING_TIME.OVERTIME_LIMITS',a.legal_subissues)


if __name__=='__main__':unittest.main()
