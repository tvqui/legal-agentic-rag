import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence

class WorkplaceInjuryFacetTests(unittest.TestCase):
    def analysis(self,q,date='2026-09-15'):return analyze(intake(q,[]),date)
    def test_injury_narrative_routes_to_accident_sources_without_magic_label(self):
        q='Tôi bị chấn thương khi làm nhiệm vụ tại công trường. Công ty phải sơ cứu và thanh toán chi phí nào? Chưa hỏi tính mức bồi thường.'
        a=self.analysis(q);plan=plan_evidence(a)
        self.assertIn('occupational_accident',a.routing_topics)
        self.assertIn('accident_first_aid',plan.mandatory_slots)
        self.assertIn('accident_medical_costs',plan.mandatory_slots)
        self.assertTrue(all(loc.documents==['84/2015/QH13'] and loc.article=='38' for slot in ['accident_first_aid','accident_medical_costs'] for group in plan.slot_requirements[slot] for loc in group))
    def test_investigation_expenses_do_not_become_medical_expenses(self):
        a=self.analysis('Ai thanh toán chi phí điều tra tai nạn lao động?')
        self.assertNotIn('accident_medical_costs',plan_evidence(a).mandatory_slots)
    def test_domestic_injury_does_not_establish_a_workplace_accident(self):
        a=self.analysis('Tôi bị thương ở nhà, cần sơ cứu như thế nào?')
        self.assertNotIn('occupational_accident',a.routing_topics)
    def test_student_placement_does_not_force_an_employee_entitlement(self):
        a=self.analysis('Một sinh viên thực hành tại xưởng bị tai nạn, ai phải sơ cứu và thanh toán chi phí y tế?')
        self.assertNotIn('accident_medical_costs',plan_evidence(a).mandatory_slots)
    def test_historical_query_does_not_require_the_later_safety_act(self):
        a=self.analysis('Người lao động bị tai nạn tại nơi làm việc thì ai thanh toán chi phí y tế?','2015-05-02')
        self.assertNotIn('accident_medical_costs',plan_evidence(a).mandatory_slots)

if __name__=='__main__':unittest.main()
