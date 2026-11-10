"""A source quotation is useful evidence, not a completed factual assessment."""
import unittest
from vn_labor_online.answer_review import Review,validate_review
from vn_labor_online.models import AnswerTask,AdjudicationDraft,Claim,EvidenceState,VerifiedEvidenceItem,VerifiedEvidencePack


class ApplicationCoverageContractTests(unittest.TestCase):
    def fixture(self,claim,*,outcome='ASSESS_LEGALITY'):
        source='Người nhận hồ sơ phải gửi xác nhận trong thời hạn 07 ngày làm việc.'
        item=VerifiedEvidenceItem(evidence_id='source',instrument_number='TEST/2024',article='9',text=source,full_text=source)
        task=AnswerTask(task_id='question',request_quote='Đã qua 12 ngày làm việc chưa xác nhận, việc này có đúng không?',description='Đánh giá thời hạn gửi xác nhận',retrieval_query='Thời hạn xác nhận')
        pack=VerifiedEvidencePack(query=task.request_quote,requested_outcome=outcome,facts={'elapsed_days':12},
            evidence=[item],answer_tasks=[task],coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
        draft=AdjudicationDraft(answer_summary=claim,claims=[Claim(claim_id='c',text=claim,evidence_ids=['source'])],applicable_law_versions=[])
        review=Review.model_validate(dict(claims=[dict(claim_id='c',verdict='SUPPORTED',grounding=[dict(evidence_id='source',quote=source)],reason='Được nguồn hỗ trợ')],
            coverage=[dict(task_id='question',status='ANSWERED',claim_ids=['c'],missing='')],question_fully_addressed=True,missing_requirements=[]))
        return pack,draft,review,[task]

    def test_verbatim_rule_alone_does_not_complete_case_application(self):
        for text in ('Người nhận hồ sơ phải gửi xác nhận trong thời hạn 07 ngày làm việc.',
                     'TEST/2024 Điều 9: Người nhận hồ sơ phải gửi xác nhận trong thời hạn 07 ngày làm việc.'):
            pack,draft,review,tasks=self.fixture(text)
            validate_review(review,draft,pack,tasks)
            self.assertFalse(review.question_fully_addressed)
            self.assertEqual(review.coverage[0].status,'PARTIAL')
            self.assertTrue(review.coverage[0].missing)
            self.assertEqual(review.coverage[0].claim_ids,['c'])

    def test_supported_direct_application_can_be_complete(self):
        pack,draft,review,tasks=self.fixture('Nếu đã qua 12 ngày làm việc mà chưa xác nhận thì đã vượt thời hạn 07 ngày làm việc trong quy định.')
        validate_review(review,draft,pack,tasks)
        self.assertTrue(review.question_fully_addressed)

    def test_literal_rule_explanation_is_not_forced_to_invent_personal_facts(self):
        pack,draft,review,tasks=self.fixture('Người nhận hồ sơ phải gửi xác nhận trong thời hạn 07 ngày làm việc.',outcome='EXPLAIN')
        validate_review(review,draft,pack,tasks)
        self.assertTrue(review.question_fully_addressed)


if __name__=='__main__':unittest.main()
