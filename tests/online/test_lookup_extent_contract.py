import unittest
from unittest.mock import Mock
from vn_labor_online.answer_review import Review,validate_review,review_answer
from vn_labor_online.models import *

class LookupExtentContractTests(unittest.TestCase):
    def fixture(self,complete):
        text='Người lao động có quyền nhận thông tin về công việc.'
        claim=Claim(claim_id='c',text=text,evidence_ids=['e'])
        task=AnswerTask(task_id='question',request_quote='Trình bày đầy đủ quy định.',description='Toàn bộ quy định',retrieval_query='Quy định')
        pack=VerifiedEvidencePack(query='Trình bày đầy đủ quy định.',lookup_scope_complete=complete,
            evidence=[VerifiedEvidenceItem(evidence_id='e',text=text,full_text=text)],
            answer_tasks=[task],coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
        draft=AdjudicationDraft(answer_summary=text,claims=[claim],applicable_law_versions=[])
        raw={'claims':[{'claim_id':'c','verdict':'SUPPORTED','grounding':[{'evidence_id':'e','quote':text}],'reason':'Khớp nguồn'}],
            'coverage':[{'task_id':'question','status':'ANSWERED','claim_ids':['c'],'missing':''}],
            'question_fully_addressed':True,'missing_requirements':[]}
        return pack,draft,raw
    def test_complete_claims_do_not_prove_the_unseen_source_extent(self):
        pack,draft,raw=self.fixture(False);review=Review.model_validate(raw)
        self.assertEqual(validate_review(review,draft,pack,pack.answer_tasks),{'c'})
        self.assertFalse(review.question_fully_addressed)
        self.assertEqual(review.coverage[0].status,'PARTIAL')
        self.assertTrue(review.missing_requirements)
    def test_exhaustive_source_does_not_lose_coverage(self):
        pack,draft,raw=self.fixture(True);review=Review.model_validate(raw)
        self.assertEqual(validate_review(review,draft,pack,pack.answer_tasks),{'c'})
        self.assertTrue(review.question_fully_addressed)
    def test_known_missing_extent_does_not_trigger_a_pointless_model_repair(self):
        pack,draft,raw=self.fixture(False);provider=Mock();provider.structured.return_value=raw
        result,warnings=review_answer(provider,draft,pack,repair_attempts=1)
        self.assertEqual(provider.structured.call_count,1)
        self.assertEqual(result.semantic_review['status'],'PARTIAL')
        self.assertEqual(len(result.claims),1)
    def test_legacy_nonlookup_pack_keeps_its_existing_review_contract(self):
        pack,draft,raw=self.fixture(None);review=Review.model_validate(raw)
        validate_review(review,draft,pack,pack.answer_tasks)
        self.assertTrue(review.question_fully_addressed)

if __name__=='__main__':unittest.main()
