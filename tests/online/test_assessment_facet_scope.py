import unittest
from vn_labor_online.claim_validation import semantic_issues
from vn_labor_online.models import VerifiedEvidenceItem


class AssessmentFacetScopeTests(unittest.TestCase):
    item=VerifiedEvidenceItem(evidence_id='notice',text='Người lao động phải báo trước ít nhất 17 ngày đối với hợp đồng loại A.')
    query='Chỉ xét thời hạn báo trước: tôi đã báo trước 21 ngày thì đủ chưa?'

    def test_a_notice_comparison_is_not_an_overall_legality_finding(self):
        text='Người lao động đã báo trước 21 ngày nên việc chấm dứt hợp đồng là hợp pháp.'
        self.assertIn('CLAIM_LIMITED_FACET_AS_OVERALL_LEGALITY',semantic_issues(text,[self.item],context_query=self.query))

    def test_merely_mentioning_the_notice_period_does_not_bound_a_global_verdict(self):
        text='Đã vượt thời hạn báo trước 17 ngày, nên việc chấm dứt hợp đồng là hợp pháp.'
        self.assertIn('CLAIM_LIMITED_FACET_AS_OVERALL_LEGALITY',semantic_issues(text,[self.item],context_query=self.query))

    def test_the_actual_facet_and_a_caution_remain_valid(self):
        for text in ('Thời hạn báo trước 21 ngày đáp ứng mức tối thiểu 17 ngày.',
                     'Chỉ xét thời hạn báo trước, yêu cầu đã được đáp ứng.',
                     'Chưa thể kết luận việc chấm dứt hợp đồng là hợp pháp chỉ từ số ngày báo trước.'):
            self.assertNotIn('CLAIM_LIMITED_FACET_AS_OVERALL_LEGALITY',semantic_issues(text,[self.item],context_query=self.query))

    def test_a_single_rule_cannot_prove_absence_of_all_legal_exceptions(self):
        text='Không có điều kiện đặc biệt hoặc ngoại lệ được nêu trong hợp đồng lao động hoặc quy định pháp luật.'
        self.assertIn('CLAIM_STATUTORY_ABSENCE_NOT_GROUNDED',semantic_issues(text,[self.item]))
        self.assertNotIn('CLAIM_STATUTORY_ABSENCE_NOT_GROUNDED',semantic_issues('Chưa thể khẳng định không có ngoại lệ theo pháp luật.',[self.item]))


if __name__=='__main__':unittest.main()
