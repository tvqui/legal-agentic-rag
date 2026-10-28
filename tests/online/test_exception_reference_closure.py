import unittest
from types import SimpleNamespace
from vn_labor_online.models import Evidence,EvidencePlan
from vn_labor_online.config import OnlineConfig
from vn_labor_online.retrieval import Retriever,as_evidence
from vn_labor_online.exception_references import exception_locators
from vn_labor_online.evidence import extend_plan_for_evidence,state_for

def seed(**changes):
    return Evidence(unit_id='intro',document_id='edition',document_number='DEMO',article_number='87',clause_number='1',kind='PROVISION',retrieval_method='bm25',text='Quy tắc chung, trừ trường hợp quy định tại khoản 3 Điều này.',verified=True,**changes)

class ExceptionClosureTests(unittest.TestCase):
    def retriever(self):
        units=[dict(unit_id='exception',document_id='edition',document_number='DEMO',article_number='87',clause_number='3',point_number='',kind='PROVISION',level='CLAUSE',text='Quy định ngoại lệ nguyên vẹn.'),
          dict(unit_id='wrong-edition',document_id='different',document_number='DEMO',article_number='87',clause_number='3',kind='PROVISION',text='Phiên bản khác.'),
          dict(unit_id='unrelated',document_id='edition',document_number='DEMO',article_number='87',clause_number='2',kind='PROVISION',text='Nội dung khác.')]
        return Retriever(SimpleNamespace(units=units),OnlineConfig(artifact_source='unused'))
    def test_generic_same_article_reference_adds_only_referenced_edition(self):
        extra,report=self.retriever().exception_context([seed()],8)
        self.assertEqual([e.unit_id for e in extra],['exception'])
        self.assertEqual(extra[0].text,'Quy định ngoại lệ nguyên vẹn.')
        self.assertFalse(extra[0].verified);self.assertEqual(report['explicit_exception_references'],1)
    def test_same_article_exception_becomes_a_real_required_locator(self):
        plan=EvidencePlan(mandatory_slots=['governing_rule']);updated=extend_plan_for_evidence(plan,[seed()],{},'2026-01-01')
        self.assertNotIn('exceptions',plan.mandatory_slots)
        self.assertIn('exceptions',updated.mandatory_slots)
        self.assertEqual(updated.slot_requirements['exceptions'][0][0].article,'87')
        self.assertEqual(updated.slot_requirements['exceptions'][0][0].clause,'3')
        self.assertIn('exceptions',state_for([seed()],updated,'2026-01-01').gaps)
    def test_exception_keyword_in_the_general_rule_cannot_fill_its_reference(self):
        p=extend_plan_for_evidence(EvidencePlan(mandatory_slots=[]),[seed()],{},None)
        self.assertIn('exceptions',state_for([seed()],p,None).gaps)
        extra,_=self.retriever().exception_context([seed()],8)
        checked=extra[0].model_copy(update={'verified':True})
        self.assertNotIn('exceptions',state_for([seed(),checked],p,None).gaps)
    def test_no_guess_from_external_or_self_reference(self):
        for text in ['Trừ trường hợp quy định tại khoản 3 Điều 88 của luật khác.','Quy định tại khoản 3 Điều này.','Trừ trường hợp quy định tại khoản 1 Điều này.']:
            self.assertFalse(exception_locators(seed().model_copy(update={'text':text})))
    def test_limit_and_no_blind_sibling_sweep(self):
        r=self.retriever();self.assertFalse(r.exception_context([seed()],0)[0])
        plain=seed().model_copy(update={'text':'Quy tắc không có dẫn chiếu.'})
        self.assertFalse(r.exception_context([plain],8)[0])
    def test_only_source_audited_references_extend_the_plan_and_no_duplicate_groups(self):
        plan=EvidencePlan(mandatory_slots=[])
        self.assertEqual(extend_plan_for_evidence(plan,[seed().model_copy(update={'verified':False})],{},None),plan)
        once=extend_plan_for_evidence(plan,[seed()],{},None)
        self.assertEqual(extend_plan_for_evidence(once,[seed()],{},None),once)
    def test_source_text_has_precedence_over_display_summary(self):
        s=seed().model_copy(update={'source_text':'Quy định không dẫn chiếu.'})
        self.assertFalse(exception_locators(s))
