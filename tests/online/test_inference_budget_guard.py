"""Deterministic deadline and batching regressions; no live inference."""
import json
import unittest
from unittest.mock import Mock,patch
from vn_labor_online.runtime import request_budget,operation_budget,request_timeout,OperationBudgetExceeded,RequestStopped
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig,AdjudicationConfig
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.models import Evidence

class BudgetAdmissionTests(unittest.TestCase):
    def test_short_remainder_never_reaches_provider_or_consumes_budget(self):
        clock=[100.0];provider=Mock()
        with patch('vn_labor_online.runtime.time.monotonic',side_effect=lambda:clock[0]),request_budget(180) as budget:
            budget.started=100;budget.operation_spent['audit']=55
            with self.assertRaises(OperationBudgetExceeded):
                with operation_budget('audit',70,45,80,minimum_call_seconds=25):provider()
            provider.assert_not_called();self.assertEqual(budget.operation_spent['audit'],55)
            self.assertEqual(budget.remaining(),180)

    def test_minimum_never_expands_call_cap(self):
        with request_budget(180):
            with self.assertRaises(OperationBudgetExceeded):
                with operation_budget('audit',90,2,0,minimum_call_seconds=25):self.fail('short call admitted')

    def test_cancellation_wins_over_local_admission(self):
        with request_budget(180) as budget:
            budget.cancelled.set()
            with self.assertRaises(RequestStopped):
                with operation_budget('audit',90,45,0,minimum_call_seconds=25):pass
            budget.cancelled.clear()

    def test_nested_operation_and_reserved_root_time_are_not_borrowed(self):
        with request_budget(180):
            with operation_budget('outer',10,10):
                with self.assertRaises(OperationBudgetExceeded):
                    with operation_budget('inner',90,45,0,minimum_call_seconds=25):pass
        clock=[100.0]
        with patch('vn_labor_online.runtime.time.monotonic',side_effect=lambda:clock[0]),request_budget(90) as budget:
            budget.started=100
            with self.assertRaises(OperationBudgetExceeded):
                with operation_budget('audit',90,45,80,minimum_call_seconds=25):pass

    def test_legacy_budget_without_minimum_still_allows_short_call(self):
        with request_budget(180):
            with operation_budget('legacy',2,2):self.assertLessEqual(request_timeout(180),2)

class AuditorBatchAdmissionTests(unittest.TestCase):
    def auditor(self,**options):
        cfg=ApplicabilityConfig(mode='hybrid',max_items=4,max_batches=4,**options)
        a=LegalApplicabilityAuditor(cfg);a.provider=Mock()
        a.provider.context_tokens=16384;a.provider.max_output_tokens=1536;a.provider.count_prompt_tokens=None
        a._deterministic=Mock(return_value=([],[],[]))
        return a

    def source(self,uid,text):
        return Evidence(unit_id=uid,text=text,source_text=text,ancestor_context='A complete parent rule.',
                        document_number='SYNTHETIC',article_number='801',retrieval_method='bm25')

    def responder(self,seen):
        def call(system,user,schema):
            self.assertEqual(user,json.dumps(json.loads(user),ensure_ascii=False,separators=(',',':')))
            body=json.loads(user);seen.extend(body['candidates'])
            return {'decisions':{e['evidence']['id']:{'relevant':True,'supports_claim':True,
                'conditions_status':'NOT_APPLICABLE','exception_status':'NOT_APPLICABLE'} for e in body['candidates']}}
        return call

    def test_time_target_splits_without_truncating_any_candidate(self):
        a=self.auditor(batch_prompt_tokens=5500);seen=[]
        items=[self.source(str(i),'Full source including its exception. '*45) for i in range(3)]
        a.provider.structured.side_effect=self.responder(seen)
        accepted,decisions,warnings=a.audit(items,'Explain every duty.',['GENERAL'],{})
        self.assertGreater(a.provider.structured.call_count,1)
        self.assertEqual({e.unit_id for e in accepted},{e.unit_id for e in items})
        self.assertEqual({e['evidence']['id']:e['evidence']['text'] for e in seen},{e.unit_id:e.source_text for e in items})
        self.assertTrue(all(e['evidence']['ancestor_context']=='A complete parent rule.' for e in seen))

    def test_single_source_above_soft_target_is_preserved_if_context_fits(self):
        a=self.auditor(batch_prompt_tokens=1024);seen=[]
        a.provider.structured.side_effect=self.responder(seen)
        source=self.source('single','All complete conditions and exceptions. '*60)
        accepted,_,_=a.audit([source],'Explain duty.',['GENERAL'],{})
        self.assertEqual([e.unit_id for e in accepted],['single'])
        self.assertEqual(seen[0]['evidence']['text'],source.source_text)

    def test_admission_skip_keeps_unaudited_candidate_unresolved(self):
        a=self.auditor(minimum_call_seconds=25);clock=[100.0]
        with patch('vn_labor_online.runtime.time.monotonic',side_effect=lambda:clock[0]),request_budget(180) as budget:
            budget.started=100;budget.operation_spent['applicability']=75
            accepted,decisions,warnings=a.audit([self.source('u','Complete source.')],'Explain.',['GENERAL'],{})
        a.provider.structured.assert_not_called()
        self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
        self.assertIn('APPLICABILITY_COMPONENT_BUDGET_EXHAUSTED',warnings)

    def test_configured_auditor_context_reaches_ollama(self):
        a=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid',provider='ollama',context_tokens=32768))
        self.assertEqual(a.provider.context_tokens,32768)
        a.provider.close()

    def test_primary_admission_preserves_semantic_review_window(self):
        engine=LegalAdjudicator(AdjudicationConfig(mode='ollama',minimum_call_seconds=20))
        engine.provider=Mock();clock=[165.0]
        with patch('vn_labor_online.runtime.time.monotonic',side_effect=lambda:clock[0]),request_budget(180) as budget:
            budget.started=100
            # 115s left, of which 45s are reserved: primary still has its 45s cap.
            engine.provider.structured.side_effect=lambda *args:request_timeout(300)
            self.assertEqual(engine._primary_structured('s','u',{}),45)
            clock[0]=220
            with self.assertRaises(OperationBudgetExceeded):engine._primary_structured('s','u',{})
            self.assertEqual(engine.provider.structured.call_count,1)

if __name__=='__main__':unittest.main()
