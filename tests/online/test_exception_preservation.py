import unittest
from types import SimpleNamespace

from vn_labor_online.claim_validation import semantic_issues


class ExceptionPreservationTests(unittest.TestCase):
    def source(self):
        return SimpleNamespace(document_number='45/2019/QH14',article_number='35',
            text='b) Không được trả đủ lương hoặc trả lương không đúng thời hạn, trừ trường hợp quy định tại khoản 4 Điều 97 của Bộ luật này.')

    def test_late_payment_alone_does_not_prove_no_notice_entitlement(self):
        for text in ('A có quyền đơn phương chấm dứt hợp đồng không cần báo trước vì công ty trả lương chậm.',
                     'Công ty không có căn cứ đòi tiền do A chấm dứt hợp đồng không cần báo trước theo pháp luật.'):
            with self.subTest(text=text):
                self.assertIn('CLAIM_LATE_WAGE_EXCEPTION_LOST',semantic_issues(text,[self.source()],
                    context_query='Công ty trả lương chậm 20 ngày. A nghỉ ngay. Có phải bồi thường không?'))

    def test_general_rule_retains_referenced_exception(self):
        text='Điểm b khoản 2 Điều 35 cho phép nghỉ không cần báo trước do chậm trả lương, trừ trường hợp tại khoản 4 Điều 97.'
        self.assertEqual(semantic_issues(text,[self.source()]),[])

    def test_explicit_nontriggered_exception_can_support_applied_conclusion(self):
        text='Người lao động được nghỉ không cần báo trước do công ty chậm trả lương.'
        query='Công ty trả lương trễ và không có sự kiện bất khả kháng. Tôi nghỉ ngay có được không?'
        self.assertEqual(semantic_issues(text,[self.source()],context_query=query),[])

    def test_positive_force_majeure_is_not_read_as_absent(self):
        text='Người lao động được nghỉ không cần báo trước.'
        query='Công ty có sự kiện bất khả kháng, đã tìm mọi biện pháp khắc phục và trả lương chậm 20 ngày.'
        self.assertIn('CLAIM_LATE_WAGE_EXCEPTION_LOST',semantic_issues(text,[self.source()],context_query=query))

    def test_guard_does_not_apply_to_unrelated_exception(self):
        item=SimpleNamespace(document_number='45/2019/QH14',article_number='35',
            text='d) Bị quấy rối tình dục tại nơi làm việc;')
        self.assertEqual(semantic_issues('Người lao động có quyền nghỉ không cần báo trước do quấy rối tình dục.',[item]),[])


if __name__=='__main__': unittest.main()
