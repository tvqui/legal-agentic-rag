import unittest
from vn_labor_online.answer_review import audit_in_batches
from vn_labor_online.errors import StructuredOutputError
from tests.online import test_review_claim_batches as fixtures

class BatchMemoryTests(unittest.TestCase):
 def fixture(self):return fixtures.ReviewClaimBatchTests().fixture(10)
 def test_later_batch_receives_validated_earlier_propositions(self):
  pack,draft,payload=self.fixture();provider=fixtures.BatchProvider()
  audit_in_batches(provider,payload,draft,pack,pack.answer_tasks)
  self.assertEqual([len(call['previously_supported_claims']) for call in provider.calls[:-1]],[0,4,8])
  self.assertEqual([c['claim_id'] for c in provider.calls[1]['previously_supported_claims']],['claim_0','claim_1','claim_2','claim_3'])
 def test_rejected_claims_do_not_become_validated_context(self):
  class RejectFirst(fixtures.BatchProvider):
   def structured(self,system,user,schema):
    result=super().structured(system,user,schema)
    if 'claims' in result:
     for claim in result['claims']:
      if claim['claim_id']=='claim_0':claim.update(verdict='UNSUPPORTED',grounding=[])
    return result
  pack,draft,payload=self.fixture();provider=RejectFirst()
  audit_in_batches(provider,payload,draft,pack,pack.answer_tasks)
  self.assertNotIn('claim_0',{c['claim_id'] for c in provider.calls[1]['previously_supported_claims']})
  self.assertEqual(len(provider.calls[1]['previously_supported_claims']),3)
 def test_old_supported_context_cannot_justify_new_fabricated_grounding(self):
  class BadLater(fixtures.BatchProvider):
   def structured(self,system,user,schema):
    result=super().structured(system,user,schema)
    if len(self.calls)>1 and 'claims' in result:
     result['claims'][0]['grounding'][0]['quote']='This quotation is not present in any legal source.'
    return result
  pack,draft,payload=self.fixture();provider=BadLater()
  with self.assertRaises(StructuredOutputError):audit_in_batches(provider,payload,draft,pack,pack.answer_tasks)
  self.assertEqual(len(provider.calls),2)

if __name__=='__main__':unittest.main()
