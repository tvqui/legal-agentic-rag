import unittest
from types import SimpleNamespace as NS
from vn_labor_online.analysis import analyze,intake
from vn_labor_online.taxonomy import probation_duration_clauses
from vn_labor_online.claim_validation import semantic_issues

class ScopedJobAndTriggerTimeTests(unittest.TestCase):
    def test_negated_other_category_cannot_erase_confirmed_qualification(self):
        for q in ['Vị trí chuyên môn yêu cầu trình độ cao đẳng, không phải công việc của người quản lý doanh nghiệp. Thử việc 78 ngày có vượt giới hạn không?',
                  'Công việc yêu cầu trình độ trung cấp, không phải công việc của người quản lý doanh nghiệp; thử việc 34 ngày có được không?']:
            with self.subTest(q=q):
                a=analyze(intake(q,[]),'2026-09-15')
                self.assertEqual(len(probation_duration_clauses(a,False)),1)
    def test_negated_group_membership_is_not_a_request_for_every_group(self):
        q='Một công việc phổ thông không thuộc các nhóm yêu cầu trình độ khác, thử việc bốn ngày làm việc có đúng không?'
        a=analyze(intake(q,[]),'2026-09-15')
        self.assertEqual(a.facts['probation_work_group'],'OTHER')
        self.assertEqual(probation_duration_clauses(a,False),(4,))
    def test_an_actual_overview_still_preserves_all_categories(self):
        a=analyze(intake('Hãy so sánh thời gian thử việc tối đa của tất cả các nhóm công việc.',[]),'2026-09-15')
        self.assertEqual(probation_duration_clauses(a,False),(1,2,3,4))
    def test_at_event_notification_cannot_be_shifted_before_the_event(self):
        source=NS(text='Khi kết thúc kiểm tra, bên nhận phải thông báo kết quả cho bên giao.',full_text='Khi kết thúc kiểm tra, bên nhận phải thông báo kết quả cho bên giao.')
        self.assertIn('CLAIM_UNSUPPORTED_ADVANCE_DEADLINE',semantic_issues('Bên nhận phải thông báo kết quả trước khi kết thúc kiểm tra.',[source]))
    def test_source_with_an_explicit_advance_notice_is_not_blocked(self):
        source=NS(text='Bên nhận phải thông báo trước khi kết thúc kiểm tra.',full_text='Bên nhận phải thông báo trước khi kết thúc kiểm tra.')
        self.assertNotIn('CLAIM_UNSUPPORTED_ADVANCE_DEADLINE',semantic_issues('Bên nhận phải thông báo trước khi kết thúc kiểm tra.',[source]))
    def test_contract_formation_process_is_not_a_completed_event_deadline(self):
        source=NS(text='Khi giao kết hợp đồng, người sử dụng lao động phải cung cấp thông tin trung thực cho người lao động.',full_text='Khi giao kết hợp đồng, người sử dụng lao động phải cung cấp thông tin trung thực cho người lao động.')
        self.assertNotIn('CLAIM_UNSUPPORTED_ADVANCE_DEADLINE',semantic_issues('Người sử dụng lao động phải cung cấp thông tin trước khi giao kết hợp đồng.',[source]))
    def test_caution_against_an_unsupported_advance_deadline_is_allowed(self):
        source=NS(text='Khi kết thúc kiểm tra, bên nhận thông báo kết quả.',full_text='Khi kết thúc kiểm tra, bên nhận thông báo kết quả.')
        self.assertNotIn('CLAIM_UNSUPPORTED_ADVANCE_DEADLINE',semantic_issues('Chưa có căn cứ để yêu cầu bên nhận phải thông báo trước khi kết thúc kiểm tra.',[source]))

if __name__=='__main__':unittest.main()
