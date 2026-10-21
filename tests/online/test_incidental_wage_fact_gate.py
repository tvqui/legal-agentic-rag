import unittest
from vn_labor_online.analysis import analyze,intake


class IncidentalWageFactGateTests(unittest.TestCase):
    def test_suspension_legality_is_not_blocked_by_an_unrelated_salary_date(self):
        for query in (
            'Doanh nghiệp gọi việc cho NLĐ nghỉ không lương sáu tháng là tạm hoãn hợp đồng, dù NLĐ không đồng ý. Có hợp pháp không?',
            'Tạm hoãn HĐLĐ không hưởng lương do công ty tự quyết định có đúng không?',
            'Vì làm hỏng máy, công ty khấu trừ 70% lương để bồi thường tài sản, có hợp pháp không?'):
            with self.subTest(query=query):
                result=analyze(intake(query,[]))
                self.assertNotIn('Thời điểm phát sinh tiền lương là khi nào?',result.missing_facts)
                self.assertIsNone(result.facts.get('work_date'))

    def test_actual_minimum_wage_issue_in_a_mixed_question_retains_its_fact_gate(self):
        result=analyze(intake('Công ty tạm hoãn HĐLĐ và trả lương tối thiểu 3 triệu đồng. Như vậy có hợp pháp không?',[]))
        self.assertIn('Thời điểm phát sinh tiền lương là khi nào?',result.missing_facts)

    def test_an_unclassified_actual_pay_dispute_is_not_silently_approved(self):
        result=analyze(intake('Công ty trả lương cho tôi ba triệu đồng thì có đúng pháp luật không?',[]))
        self.assertIn('Thời điểm phát sinh tiền lương là khi nào?',result.missing_facts)
