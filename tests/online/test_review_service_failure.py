import unittest
from unittest.mock import Mock

from online.test_semantic_answer_review import sample
from vn_labor_online.answer_review import review_answer,review_service_unavailable
from vn_labor_online.errors import StructuredOutputError


class ReviewServiceFailureTests(unittest.TestCase):
    def partial_then_repair(self, failure):
        pack,draft,review=sample()
        review.update(question_fully_addressed=False,missing_requirements=['Thiếu hậu quả'])
        unchecked={'claims':[{'text':'Một kết luận mới chưa kiểm tra.', 'evidence_ids':['source']}]}
        provider=Mock()
        provider.structured.side_effect=[review,unchecked,failure]
        result,warnings=review_answer(provider,draft,pack)
        return result,warnings,draft

    def test_failed_second_review_keeps_only_previously_checked_claims(self):
        result,warnings,original=self.partial_then_repair(TimeoutError())
        self.assertEqual(result.claims,original.claims)
        self.assertNotIn('claim_001',{c.claim_id for c in result.claims})
        self.assertEqual(result.semantic_review['status'],'PARTIAL')
        self.assertEqual(result.semantic_review['missing'],['Thiếu hậu quả'])
        self.assertEqual(result.semantic_review['retained_review_index'],0)
        self.assertIn('answer_coverage',result.limitations)
        self.assertNotIn('ANSWER_QUALITY_BLOCKED',warnings)

    def test_invalid_second_review_cannot_replace_checked_meaning(self):
        result,_,original=self.partial_then_repair(StructuredOutputError('unsupported semantic PASS'))
        self.assertEqual(result.claims,original.claims)
        self.assertEqual(result.semantic_review['error_code'],'UNSUPPORTED_SEMANTIC_PASS')

    def test_first_review_failure_cannot_create_supported_claims(self):
        pack,draft,_=sample()
        provider=Mock(); provider.structured.side_effect=TimeoutError()
        result,warnings=review_answer(provider,draft,pack)
        self.assertFalse(result.claims)
        self.assertEqual(result.semantic_review['status'],'ERROR')
        self.assertIn('ANSWER_QUALITY_BLOCKED',warnings)

    def test_service_failure_is_distinct_from_semantic_rejection_and_rate_limit(self):
        for code in ('GEMINI_HTTP_504','GEMINI_HTTP_503','GEMINI_TIMEOUT','TimeoutError'):
            self.assertTrue(review_service_unavailable({'error_code':code}))
        for code in ('UNSUPPORTED_SEMANTIC_PASS','GEMINI_HTTP_429','GEMINI_HTTP_400',''):
            self.assertFalse(review_service_unavailable({'error_code':code}))


if __name__=='__main__':
    unittest.main()
