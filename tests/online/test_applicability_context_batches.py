import json
import unittest
from unittest.mock import Mock

from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig
from vn_labor_online.models import Evidence,ApplicabilityDecision


class ContextProvider:
    context_tokens=7000
    max_output_tokens=500
    def __init__(self): self.calls=[]
    def structured(self,system,user,schema):
        if len((system+user).encode('utf-8'))+256+self.max_output_tokens>self.context_tokens:
            raise AssertionError('Oversized request must be split before provider invocation')
        candidates=json.loads(user)['candidates']; self.calls.append(candidates)
        return {'decisions':{row['evidence']['id']:{'relevant':True,'supports_claim':True,
            'conditions_status':'NOT_APPLICABLE','exception_status':'NOT_APPLICABLE'} for row in candidates}}


class ApplicabilityContextBatchTests(unittest.TestCase):
    def run_audit(self,sizes,max_batches=6):
        items=[Evidence(unit_id='id'+str(i),retrieval_method='bm25',text='tiền lương '+('x'*size)) for i,size in enumerate(sizes)]
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid',max_items=8,max_batches=max_batches))
        provider=ContextProvider(); auditor.provider=provider
        decisions=[ApplicabilityDecision(evidence_id=item.unit_id,relevant=True,supports_claim=False,
                    audit_status='UNRESOLVED',reasons=['SEMANTIC_SUPPORT_REQUIRES_AUDIT']) for item in items]
        auditor._deterministic=Mock(return_value=([],decisions,[]))
        return items,provider,auditor.audit(items,'Giải thích tiền lương',['WAGE'],{},'EXPLAIN')

    def test_full_sources_are_split_into_fitting_batches_and_all_decisions_kept(self):
        items,provider,(accepted,decisions,warnings)=self.run_audit([2000]*5)
        self.assertGreater(len(provider.calls),1)
        self.assertEqual({item.unit_id for item in accepted},{item.unit_id for item in items})
        sent=[row['evidence'] for batch in provider.calls for row in batch]
        self.assertEqual(len(sent),5)
        self.assertEqual({row['id']:row['text'] for row in sent},{item.unit_id:item.text for item in items})
        self.assertFalse(warnings)

    def test_oversized_single_source_is_unresolved_without_poisoning_other_candidates(self):
        items,provider,(accepted,decisions,warnings)=self.run_audit([15000,100])
        self.assertEqual([item.unit_id for item in accepted],['id1'])
        self.assertEqual(len(decisions),2)
        self.assertEqual(next(d for d in decisions if d.evidence_id=='id0').audit_status,'UNRESOLVED')
        self.assertIn('APPLICABILITY_OUTPUT_INVALID:PROMPT_CONTEXT_BUDGET_EXCEEDED',warnings)
        self.assertEqual(len(provider.calls),1)

    def test_adaptive_splitting_does_not_expand_configured_model_call_limit(self):
        items,provider,(accepted,decisions,warnings)=self.run_audit([2000]*5,max_batches=1)
        self.assertEqual(len(provider.calls),1)
        self.assertLess(len(accepted),5)
        self.assertEqual(len(decisions),5)
        self.assertTrue(any(w.startswith('APPLICABILITY_BATCH_LIMIT:') for w in warnings))


if __name__=='__main__': unittest.main()
