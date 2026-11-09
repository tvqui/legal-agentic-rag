import unittest
from vn_labor_online.analysis import analyze,intake

class RequestedLeaveScopeTests(unittest.TestCase):
    def analysis(self,q):return analyze(intake(q,[]),'2026-09-15')
    def test_base_only_excludes_explicitly_deferred_seniority(self):
        for end in ['chưa tính ngày tăng thêm do thâm niên','chưa xét phần tăng thêm theo thâm niên','chỉ hỏi mức cơ sở, chưa tính thâm niên']:
            with self.subTest(end=end):
                a=self.analysis('Người làm nghề nặng nhọc đủ 12 tháng được nghỉ phép năm cơ sở bao nhiêu ngày, '+end+'?')
                self.assertNotIn('LEAVE.SENIORITY_BONUS',a.legal_subissues)
                self.assertFalse(any('SENIORITY' in key for t in a.answer_tasks for key in t.legal_subissues))
    def test_dispute_about_employer_excluding_seniority_is_not_silenced(self):
        a=self.analysis('Tôi làm đủ 10 năm nhưng công ty không tính thâm niên vào phép năm. Như vậy có đúng không?')
        self.assertIn('LEAVE.SENIORITY_BONUS',a.legal_subissues)
    def test_later_explicit_request_can_add_seniority_again(self):
        a=self.analysis('Tôi hỏi mức phép năm cơ sở chưa tính thâm niên. Ngoài ra hãy giải thích ngày nghỉ tăng do thâm niên.')
        self.assertIn('LEAVE.SENIORITY_BONUS',a.legal_subissues)
    def test_settled_exit_is_context_of_unused_leave_payment(self):
        a=self.analysis('Người lao động đã thôi việc, còn dư phép năm thì có được thanh toán tiền ngày chưa nghỉ không?')
        self.assertIn('LEAVE.UNUSED_LEAVE_PAYMENT',a.legal_subissues)
        self.assertFalse(any('termination_grounds' in t.topic_ids for t in a.answer_tasks))
    def test_independent_exit_legality_request_remains(self):
        a=self.analysis('Tôi nghỉ việc chỉ báo trước 10 ngày có đúng không, và ngày phép năm chưa nghỉ được thanh toán thế nào?')
        self.assertTrue(any(key.startswith('TERMINATION.') for key in a.legal_subissues) or any('termination_grounds' in t.topic_ids for t in a.answer_tasks))

    def test_intervening_duration_does_not_hide_unpaid_leave(self):
        for q in ['Chị ruột của tôi mất, tôi được nghỉ một ngày không hưởng lương không?',
                  'Ông ngoại qua đời, tôi có quyền nghỉ 1 ngày không hưởng lương không?',
                  'Em ruột kết hôn thì nghỉ một ngày không hưởng lương có được không?']:
            with self.subTest(q=q):
                a=self.analysis(q)
                self.assertIn('LEAVE.UNPAID_LEAVE',a.legal_subissues)
                self.assertNotIn('LEAVE.PERSONAL_LEAVE',a.legal_subissues)

if __name__=='__main__':unittest.main()
