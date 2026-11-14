"""Regression from actual log: 3s component remainder with 181s root remainder."""
import json,unittest
from unittest.mock import Mock
from auditor import GraphQAAuditor
from vn_labor_online.models import Evidence,ApplicabilityDecision
from vn_labor_online.config import ApplicabilityConfig
from vn_labor_online.runtime import request_budget,OperationBudgetExceeded
class AdmissionTests(unittest.TestCase):
    def auditor(self):
        return GraphQAAuditor(ApplicabilityConfig(mode='deterministic',budget_seconds=180,call_timeout_seconds=120,reserve_seconds=120))
    def test_three_seconds_blocks_network_without_borrowing_root_budget(self):
        provider=Mock()
        with request_budget(360) as budget:
            budget.operation_spent['applicability']=177
            with self.assertRaises(OperationBudgetExceeded):self.auditor()._structured(provider,'s','{}',{})
            self.assertGreater(budget.remaining(),300)
            self.assertEqual(budget.operation_spent['applicability'],177)
        provider.structured.assert_not_called()
    def test_full_budget_uses_original_provider_contract(self):
        provider=Mock();provider.structured.return_value={'fixture':True}
        with request_budget(360):self.assertEqual(self.auditor()._structured(provider,'s','{}',{}),{'fixture':True})
        provider.structured.assert_called_once_with('s','{}',{})
    def test_downstream_reserve_is_preserved(self):
        provider=Mock()
        with request_budget(125):
            with self.assertRaises(OperationBudgetExceeded):self.auditor()._structured(provider,'s','{}',{})
        provider.structured.assert_not_called()

    def batch_fixture(self,max_items=10):
        items=[Evidence(unit_id='u'+str(i),retrieval_method='bm25',text='Căn cứ thử nghiệm '+str(i)) for i in range(4)]
        auditor=GraphQAAuditor(ApplicabilityConfig(mode='hybrid',max_items=max_items,max_batches=4,budget_seconds=180,call_timeout_seconds=120,reserve_seconds=120))
        decisions=[ApplicabilityDecision(evidence_id=i.unit_id,relevant=True,supports_claim=False,audit_status='UNRESOLVED',reasons=['SEMANTIC_SUPPORT_REQUIRES_AUDIT']) for i in items]
        auditor._deterministic=Mock(return_value=([],decisions,[]))
        provider=Mock(context_tokens=16384,max_output_tokens=1536)
        def answer(system,user,schema):
            return {'decisions':{i['evidence']['id']:{'relevant':True,'supports_claim':True,'conditions_status':'NOT_APPLICABLE','exception_status':'NOT_APPLICABLE'} for i in json.loads(user)['candidates']}}
        provider.structured.side_effect=answer;auditor.provider=provider
        return auditor,items,provider,answer
    def test_hybrid_audits_four_sources_with_one_call(self):
        auditor,items,provider,_=self.batch_fixture()
        with request_budget(360):accepted,decisions,warnings=auditor.audit(items,'Giải thích quy định',['WAGE'],{},'EXPLAIN')
        self.assertEqual(provider.structured.call_count,1);self.assertEqual(len(accepted),4)
        self.assertFalse(warnings)
    def test_budget_stop_keeps_checked_sources_and_does_not_approve_remaining(self):
        auditor,items,provider,answer=self.batch_fixture(1)
        with request_budget(360) as budget:
            def spend(*args):
                result=answer(*args);budget.operation_spent['applicability']=177;return result
            provider.structured.side_effect=spend
            accepted,decisions,warnings=auditor.audit(items,'Giải thích quy định',['WAGE'],{},'EXPLAIN')
        self.assertEqual(provider.structured.call_count,1)
        self.assertEqual([i.unit_id for i in accepted],['u0'])
        self.assertTrue(all(d.audit_status=='UNRESOLVED' for d in decisions if d.evidence_id!='u0'))
        self.assertIn('APPLICABILITY_COMPONENT_BUDGET_EXHAUSTED',warnings)

if __name__=='__main__':unittest.main()
