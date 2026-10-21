import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence


class ScopedFactQuestionTests(unittest.TestCase):
    def analysis(self,query): return analyze(intake(query,[]))

    def test_property_compensation_does_not_ask_for_disciplinary_sanction(self):
        result=self.analysis('Tôi vô ý làm hỏng thiết bị của công ty. Công ty có được khấu trừ toàn bộ vào lương không?')
        self.assertNotIn('Hình thức kỷ luật là gì?',result.missing_facts)
        # This requests the deduction rule, not a dated minimum-wage amount.
        # Independent wage disputes below must still keep their own fact gate.
        self.assertNotIn('Thời điểm phát sinh tiền lương là khi nào?',result.missing_facts)

    def test_explicit_discipline_alongside_damage_keeps_relevant_facts(self):
        result=self.analysis('Tôi làm hỏng tài sản công ty và bị xử lý kỷ luật. Công ty có được làm vậy không?')
        self.assertTrue(any('kỷ luật' in question for question in result.missing_facts))

    def test_relationship_qualification_does_not_require_wage_event_date(self):
        result=self.analysis('Tôi là cộng tác viên, làm việc có trả công, chịu sự quản lý của công ty. Công ty cho rằng tôi không có quyền của người lao động. Có đúng không?')
        self.assertIn('CONTRACT.RELATIONSHIP_QUALIFICATION',result.legal_subissues)
        self.assertNotIn('Thời điểm phát sinh tiền lương là khi nào?',result.missing_facts)

    def test_independent_minimum_wage_request_still_needs_date(self):
        result=self.analysis('Tôi là cộng tác viên có trả công và chịu quản lý. Mức lương thấp hơn lương tối thiểu thì có đúng không?')
        self.assertIn('Thời điểm phát sinh tiền lương là khi nào?',result.missing_facts)

    def test_abstract_mechanism_comparison_does_not_ask_employer_resignation_facts(self):
        result=self.analysis('Khi người giúp việc chấm dứt trái pháp luật, có thể áp dụng hậu quả giống lao động doanh nghiệp không?')
        self.assertEqual(result.requested_outcome,'COMPARE')
        self.assertEqual(result.missing_facts,[])

    def test_concrete_employer_termination_still_requires_case_facts(self):
        result=self.analysis('Công ty đơn phương chấm dứt hợp đồng với tôi. Có hợp pháp không?')
        self.assertEqual(result.requested_outcome,'ASSESS_LEGALITY')
        self.assertTrue(result.missing_facts)

    def test_rule_framework_request_is_not_an_applied_verdict(self):
        query='Khi hợp đồng lao động hết hạn mà NLĐ vẫn tiếp tục làm việc, cần kiểm tra những mốc thời gian và hậu quả pháp lý nào?'
        result=self.analysis(query)
        self.assertEqual(result.requested_outcome,'EXPLAIN')
        self.assertEqual(result.missing_facts,[])
        self.assertIn('term_contract_renewal',plan_evidence(result).slot_requirements)

    def test_framework_request_does_not_hide_separate_personal_verdict(self):
        result=self.analysis('Công ty đơn phương cho tôi nghỉ. Tôi có được bồi thường không và cần kiểm tra những điều kiện nào?')
        self.assertEqual(result.requested_outcome,'ASSESS_LEGALITY')
        self.assertTrue(result.missing_facts)


if __name__=='__main__': unittest.main()
