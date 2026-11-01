import copy,unittest
from vn_labor_online.answer_review import Review,reject_invalid_support,validate_review
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.models import Claim
from tests.online import test_semantic_answer_review as fixtures

class IndependentSemanticRecoveryTests(unittest.TestCase):
 def fixture(self):
  pack,draft,value=fixtures.sample()
  bad=Claim(claim_id='bad',text='Người lao động được nghỉ 12 ngày trong mọi trường hợp.',evidence_ids=['source'])
  draft=draft.model_copy(update={'claims':draft.claims+[bad]})
  value=copy.deepcopy(value);verdict=copy.deepcopy(value['claims'][0]);verdict['claim_id']='bad'
  value['claims'].append(verdict);value['coverage'][0]['claim_ids'].append('bad')
  return pack,draft,Review.model_validate(value)
 def test_local_contradiction_cannot_poison_independent_valid_claim(self):
  pack,draft,review=self.fixture()
  checked,rejections=reject_invalid_support(review,draft,pack)
  self.assertEqual(set(rejections),{'bad'})
  self.assertEqual(validate_review(checked,draft,pack,pack.answer_tasks),{'claim'})
  self.assertEqual(checked.claims[1].verdict,'UNSUPPORTED')
  self.assertEqual(checked.coverage[0].claim_ids,['claim'])
  self.assertFalse(checked.question_fully_addressed)
 def test_original_reviewer_response_is_not_rewritten(self):
  pack,draft,review=self.fixture();before=review.model_dump()
  reject_invalid_support(review,draft,pack)
  self.assertEqual(review.model_dump(),before)
 def test_all_bad_claims_cannot_become_partial_legal_proof(self):
  pack,draft,review=self.fixture()
  draft=draft.model_copy(update={'claims':[draft.claims[1]]})
  review.claims=[review.claims[1]];review.coverage[0].claim_ids=['bad']
  checked,_=reject_invalid_support(review,draft,pack)
  self.assertFalse(validate_review(checked,draft,pack,pack.answer_tasks))
  self.assertEqual(checked.coverage[0].status,'MISSING')
 def test_decorative_citation_is_rejected_not_silently_removed_and_approved(self):
  pack,draft,review=self.fixture()
  extra=pack.evidence[0].model_copy(update={'evidence_id':'extra'})
  pack=pack.model_copy(update={'evidence':pack.evidence+[extra]})
  draft.claims[0].evidence_ids.append('extra')
  checked,rejections=reject_invalid_support(review,draft,pack)
  self.assertIn('claim',rejections)
  self.assertEqual(draft.claims[0].evidence_ids,['source','extra'])
  self.assertEqual(checked.claims[0].verdict,'UNSUPPORTED')
 def test_fabricated_quote_still_rejects_the_review(self):
  pack,draft,review=self.fixture()
  review.claims[0].grounding[0].quote='Đây là một đoạn trích không có trong nguồn.'
  with self.assertRaisesRegex(StructuredOutputError,'exact cited-source quotation'):
   reject_invalid_support(review,draft,pack)
 def test_duplicate_or_missing_review_ids_are_not_tolerated(self):
  for missing in [True,False]:
   pack,draft,review=self.fixture()
   review.claims=review.claims[:-1] if missing else review.claims+[review.claims[0]]
   with self.subTest(missing=missing),self.assertRaises(StructuredOutputError):reject_invalid_support(review,draft,pack)
 def test_unrelated_provider_accounting_error_cannot_be_hidden_by_local_rejection(self):
  pack,draft,review=self.fixture()
  review.coverage[0].claim_ids.append('invented_claim')
  checked,_=reject_invalid_support(review,draft,pack)
  with self.assertRaisesRegex(StructuredOutputError,'unproved claim'):
   validate_review(checked,draft,pack,pack.answer_tasks)

if __name__=='__main__':unittest.main()
