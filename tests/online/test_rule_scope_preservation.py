import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from vn_labor_online.claim_validation import semantic_issues
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.config import AdjudicationConfig
from vn_labor_online.models import VerifiedEvidencePack
from tests.online.test_hard_question_regressions import _verified,_state


class RuleScopePreservationTests(unittest.TestCase):
    def test_normal_hours_cannot_be_a_universal_total_hours_prohibition(self):
        source=SimpleNamespace(document_number='45/2019/QH14',article_number='105',
            text='Thời giờ làm việc bình thường không quá 48 giờ trong 01 tuần.')
        claim='Làm 50 giờ/tuần vượt giới hạn 48 giờ/tuần nên công ty vi phạm pháp luật.'
        self.assertIn('CLAIM_NORMAL_HOURS_SCOPE_LOST',semantic_issues(claim,[source],
            context_query='Lịch làm việc tổng cộng 50 giờ/tuần có hợp pháp không?'))
        self.assertEqual(semantic_issues('Nếu đây là thời giờ làm việc bình thường thì 50 giờ/tuần vi phạm giới hạn 48 giờ.',[source]),[])
        self.assertEqual(semantic_issues(claim,[source],context_query='Công ty quy định toàn bộ 50 giờ là giờ làm việc bình thường.'),[])

    def test_light_work_age_range_cannot_expand_to_all_under_fifteen(self):
        source=SimpleNamespace(document_number='45/2019/QH14',article_number='145',
            text='Chỉ được tuyển dụng người từ đủ 13 tuổi đến chưa đủ 15 tuổi vào làm công việc nhẹ.')
        self.assertIn('CLAIM_MINOR_AGE_SCOPE_LOST',semantic_issues('Người dưới 15 tuổi được sử dụng vào làm công việc nhẹ.',[source]))
        self.assertEqual(semantic_issues('Người từ đủ 13 tuổi đến dưới 15 tuổi chỉ được sử dụng vào làm công việc nhẹ.',[source]),[])
        source.document_number='09/2020/TT-BLĐTBXH'; source.article_number='3'
        self.assertIn('CLAIM_MINOR_AGE_SCOPE_LOST',semantic_issues('Người dưới 15 tuổi được làm công việc nhẹ.',[source]))

    def test_minimum_benefit_is_not_a_deduction(self):
        source=SimpleNamespace(document_number='84/2015/QH13',article_number='38',
            text='Trợ cấp cho người lao động bị tai nạn lao động mà do lỗi của chính họ gây ra một khoản tiền ít nhất bằng 40% mức quy định tại khoản 4 Điều này.')
        self.assertIn('CLAIM_BENEFIT_PAYMENT_INVERTED_TO_DEDUCTION',semantic_issues('Người lao động chỉ bị trừ một khoản tiền ít nhất bằng 40% mức quy định.',[source]))
        self.assertEqual(semantic_issues('Người lao động được trợ cấp ít nhất bằng 40% mức quy định tại khoản 4.',[source]),[])
        self.assertEqual(semantic_issues('Người lao động không bị trừ một khoản tiền ở đây.',[source]),[])

    def test_probation_source_identity_composition_does_not_invoke_free_generation(self):
        query='Người thử việc bị trả lương thấp hơn 85% thì ngoài Bộ luật Lao động cần kiểm tra văn bản xử phạt nào?'
        pay=_verified('pay','26',text='Tiền lương thử việc ít nhất bằng 85% mức lương của công việc đó.')
        sanction=_verified('sanction','10','2','c','Trả lương thử việc thấp hơn 85% mức lương của công việc đó;')
        sanction=sanction.model_copy(update={'instrument_number':'12/2022/NĐ-CP'})
        pack=VerifiedEvidencePack(query=query,query_date='2026-09-15',facts={},evidence=[pay,sanction],
            coverage_state=_state(['pay','sanction']))
        generator=LegalAdjudicator(AdjudicationConfig(mode='deterministic'))
        generator.provider=Mock(side_effect=AssertionError('Profile identity needs no free-form generation'))
        generator.provider.structured.side_effect=AssertionError('No free-form generation')
        draft,warnings=generator._generate(pack,True,[])
        self.assertTrue(draft.claims)
        self.assertIn('12/2022/NĐ-CP',' '.join(c.text for c in draft.claims))
        self.assertFalse(any('triệu' in c.text or '5.000.000' in c.text for c in draft.claims))
        generator.provider.structured.assert_not_called()
        self.assertEqual(warnings,[])


if __name__=='__main__': unittest.main()
