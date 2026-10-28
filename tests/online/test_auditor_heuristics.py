import unittest
from unittest.mock import Mock,patch
from contextlib import ExitStack
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig
from vn_labor_online.models import Evidence,LegalLocator

def item(article='99',clause='',point='',text='Quy định liên quan quyền của người lao động.'):
    return Evidence(unit_id='unit',retrieval_method='bm25',text=text,document_number='45/2019/QH14',article_number=article,clause_number=clause,point_number=point)

class AuditorHeuristicTests(unittest.TestCase):
    def run_profile(self,value,provider=None,issues=None,facts=None,outcome='EXPLAIN'):
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid' if provider else 'deterministic'))
        auditor.provider=provider
        with ExitStack() as stack:
            stack.enter_context(patch('vn_labor_online.applicability.classify_subissues',return_value=[]))
            stack.enter_context(patch('vn_labor_online.applicability.profile_covers_issues',return_value=True))
            stack.enter_context(patch('vn_labor_online.applicability.profile_requirements',return_value={'rule':[[LegalLocator(documents=['45/2019/QH14'],article='88')]]}))
            return auditor.audit([value],'Hỏi về một căn cứ bổ sung',issues or [],facts or {},outcome)
    def model(self,**updates):
        model=Mock();model.context_tokens=None;model.max_output_tokens=1000
        model.structured.return_value={'decisions':{'unit':{'relevant':True,'supports_claim':True,'conditions_status':'NOT_APPLICABLE','exception_status':'NOT_APPLICABLE',**updates}}}
        return model
    def test_off_profile_is_not_a_proven_failure_or_a_pass(self):
        accepted,decisions,_=self.run_profile(item())
        self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
        self.assertIn('PROFILE_LOCATION_MISMATCH',decisions[0].reasons)
    def test_hybrid_can_examine_but_must_independently_approve_off_profile(self):
        model=self.model();accepted,decisions,_=self.run_profile(item(),model)
        self.assertEqual(len(accepted),1);self.assertEqual(model.structured.call_count,1)
        self.assertEqual(decisions[0].reasons,['MODEL_APPLICABILITY_PASS'])
    def test_model_rejection_is_not_promoted_by_reranker_or_profile(self):
        model=self.model(supports_claim=False);accepted,decisions,_=self.run_profile(item(),model)
        self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'FAIL')
    def test_contract_fact_contradiction_remains_hard_even_outside_profile(self):
        model=self.model();accepted,decisions,_=self.run_profile(item('35','1','b'),model,['TERMINATION'],{'actor':'EMPLOYEE','contract_type':'INDEFINITE'},'ASSESS_LEGALITY')
        self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'FAIL')
        self.assertIn('CONTRACT_TYPE_MISMATCH',decisions[0].reasons);model.structured.assert_not_called()
    def test_full_year_fact_contradiction_remains_hard(self):
        model=self.model();accepted,decisions,_=self.run_profile(item(text='Người lao động làm đủ 12 tháng.'),model,['LEAVE'],{'worked_months':4})
        self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'FAIL');model.structured.assert_not_called()
    def test_relevant_and_supporting_but_unknown_conditions_cannot_decide_case(self):
        model=self.model(conditions_status='UNKNOWN',exception_status='UNKNOWN')
        accepted,decisions,_=self.run_profile(item(),model,outcome='ASSESS_LEGALITY')
        self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
    def test_failed_model_does_not_promote_heuristic_unknowns(self):
        model=self.model();model.structured.side_effect=TimeoutError()
        accepted,decisions,_=self.run_profile(item(),model)
        self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
