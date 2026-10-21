import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.evidence import state_for
from vn_labor_online.models import Evidence


class UnemploymentQuestionScopeTests(unittest.TestCase):
    def test_generic_eligibility_question_does_not_require_an_employer_case(self):
        for question in (
            'Chỉ cần đã đóng BHTN là sau khi nghỉ việc chắc chắn được nhận trợ cấp, bất kể lý do và thủ tục, đúng không?',
            'Người đã đóng bảo hiểm thất nghiệp có luôn nhận được trợ cấp sau khi thôi việc không?'):
            with self.subTest(question=question):
                analysis=analyze(intake(question,[]))
                self.assertEqual(analysis.requested_outcome,'EXPLAIN')
                self.assertNotIn('TERMINATION',analysis.legal_issues)
                self.assertFalse(analysis.missing_facts)
                self.assertNotIn('notice_requirement',plan_evidence(analysis).mandatory_slots)
                self.assertFalse(any('TERMINATION' in task.legal_issues for task in analysis.answer_tasks))
                self.assertNotIn('eligible',analysis.facts)

    def test_actual_employee_legality_request_keeps_relevant_facts(self):
        analysis=analyze(intake('Tôi muốn nghỉ việc chỉ báo trước 20 ngày. Việc nghỉ như vậy có trái pháp luật không, và tôi đã đóng BHTN thì có luôn nhận trợ cấp không?',[]))
        self.assertIn('TERMINATION',analysis.legal_issues)
        self.assertEqual(analysis.requested_outcome,'ASSESS_LEGALITY')
        self.assertTrue(analysis.missing_facts)

    def test_a_separate_employer_legality_request_is_preserved(self):
        analysis=analyze(intake('Công ty đơn phương chấm dứt hợp đồng với tôi. Việc đó có hợp pháp không, và chỉ cần đóng BHTN là chắc chắn được trợ cấp đúng không?',[]))
        self.assertEqual(analysis.facts.get('actor'),'EMPLOYER')
        self.assertIn('TERMINATION',analysis.legal_issues)
        self.assertTrue(any('Công ty đã báo trước' in question for question in analysis.missing_facts))

    def test_eligibility_uses_the_dated_employment_act_not_only_a_labour_departure_rule(self):
        query='Chỉ cần đóng BHTN là sau khi nghỉ việc chắc chắn được nhận trợ cấp đúng không?'
        for when,number,article in [('2025-12-31','38/2013/QH13','49'),('2026-01-01','74/2025/QH15','38')]:
            with self.subTest(when=when):
                groups=plan_evidence(analyze(intake(query,[]),when)).slot_requirements['unemployment_eligibility']
                self.assertEqual(len(groups),4)
                self.assertTrue(all(loc.documents==[number] and loc.article==article for group in groups for loc in group))

    def test_old_or_partial_evidence_cannot_satisfy_all_current_conditions(self):
        analysis=analyze(intake('Đã đóng BHTN có luôn được nhận trợ cấp sau khi nghỉ việc không?',[]),'2026-01-01')
        plan=plan_evidence(analysis)
        old=Evidence(unit_id='old',retrieval_method='policy',verified=True,kind='PROVISION',
            document_number='38/2013/QH13',article_number='49',text='Điều kiện hưởng trợ cấp thất nghiệp.')
        self.assertIn('unemployment_eligibility',state_for([old],plan,'2026-01-01').gaps)
        partial=[old.model_copy(update={'unit_id':point,'document_number':'74/2025/QH15','article_number':'38',
            'clause_number':'1','point_number':point}) for point in ('a','b','d')]
        self.assertIn('unemployment_eligibility',state_for(partial,plan,'2026-01-01').gaps)
