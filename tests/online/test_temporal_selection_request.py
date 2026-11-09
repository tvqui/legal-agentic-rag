import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence

class TemporalSelectionRequestTests(unittest.TestCase):
    def test_selecting_governing_date_does_not_require_resignation_notice_facts(self):
        q='Hợp đồng ký ngày 12/04/2017, công ty chấm dứt ngày 03/08/2026. Phải đánh giá theo thời điểm nào? Công ty bảo chỉ dùng luật lúc ký hợp đồng, có đúng không?'
        a=analyze(intake(q,[]))
        self.assertEqual(a.query_date,'2026-08-03')
        self.assertEqual(a.requested_outcome,'EXPLAIN')
        self.assertFalse(a.missing_facts)
        self.assertFalse(a.legal_subissues)
        plan=plan_evidence(a)
        self.assertNotIn('notice_requirement',plan.mandatory_slots)
        self.assertNotIn('termination_conditions',plan.mandatory_slots)
    def test_declared_applicable_date_is_not_a_selection_only_question(self):
        a=analyze(intake('Tại thời điểm áp dụng luật năm 2026, công ty có được sa thải tôi khi đang nghỉ ốm không?',[]))
        self.assertEqual(a.requested_outcome,'ASSESS_LEGALITY')
        self.assertNotEqual(a.facts.get('query_intent'),'TEMPORAL_LAW_SELECTION')
    def test_independent_legality_request_preserves_its_fact_gate(self):
        q='Hợp đồng ký năm 2017, công ty chấm dứt ngày 03/08/2026. Đánh giá theo thời điểm nào và việc công ty chấm dứt như vậy có đúng luật không?'
        a=analyze(intake(q,[]))
        self.assertEqual(a.requested_outcome,'ASSESS_LEGALITY')
        self.assertTrue(a.missing_facts)

if __name__=='__main__':unittest.main()
