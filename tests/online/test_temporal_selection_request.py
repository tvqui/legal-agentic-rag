import unittest
from unittest.mock import Mock
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

    def test_researcher_cannot_reintroduce_dismissal_into_a_date_selection_only_task(self):
        from vn_labor_online.researcher import LegalResearcher
        from vn_labor_online.config import ResearcherConfig
        q='Hợp đồng ký ngày 11/03/2017; công ty chấm dứt ngày 09/08/2026. Phải đánh giá theo thời điểm nào?'
        a=analyze(intake(q,[]))
        researcher=LegalResearcher(ResearcherConfig(mode='ollama',adaptive=False))
        researcher.provider=Mock()
        researcher.provider.structured.return_value={'legal_issues':['TERMINATION'],
            'retrieval_queries':['Điều kiện chấm dứt hợp đồng'],'ontology':{},'fact_candidates':[],
            'answer_tasks':[{'task_id':'unrequested','request_quote':q,'description':'Đánh giá việc chấm dứt hợp đồng',
                'retrieval_query':'Điều kiện chấm dứt hợp đồng'}]}
        enriched,warnings=researcher.enrich(a,q,[])
        self.assertFalse(warnings)
        self.assertEqual(enriched.legal_subissues,[])
        self.assertEqual(enriched.answer_tasks,a.answer_tasks)
        p=plan_evidence(enriched)
        self.assertNotIn('exceptions',p.mandatory_slots)
        self.assertNotIn('termination_conditions',p.mandatory_slots)
        self.assertIn('labour_code_effectiveness',p.slot_requirements)
        self.assertIn('labour_contract_transition',p.slot_requirements)
        self.assertEqual(set(p.slot_requirements),{'labour_code_effectiveness','labour_contract_transition'})

    def test_effectiveness_and_transition_requirements_are_dated(self):
        for event_day,article,docs in [('18/08/2026','220',['45/2019/QH14','18/VBHN-VPQH']),
                                      ('18/08/2020','240',['10/2012/QH13'])]:
            a=analyze(intake(f'Hợp đồng ký ngày 11/03/2009; công ty chấm dứt ngày {event_day}. Phải đánh giá theo thời điểm nào?',[]))
            p=plan_evidence(a)
            loc=p.slot_requirements['labour_code_effectiveness'][0][0]
            self.assertEqual((loc.article,loc.clause,loc.documents),(article,'1',docs))
            self.assertEqual(p.slot_requirements['labour_contract_transition'][0][0].clause,'2')

if __name__=='__main__':unittest.main()
