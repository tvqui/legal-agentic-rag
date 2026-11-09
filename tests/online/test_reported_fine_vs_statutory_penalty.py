import unittest
from types import SimpleNamespace as NS
from vn_labor_online.claim_validation import semantic_issues

class ReportedFineVsStatutoryPenaltyTests(unittest.TestCase):
    def source(self):return NS(text='Nghiêm cấm phạt tiền, cắt lương thay việc xử lý kỷ luật lao động.',full_text='Nghiêm cấm phạt tiền, cắt lương thay việc xử lý kỷ luật lao động.')
    def issues(self,text,q):return semantic_issues(text,[self.source()],context_query=q)
    def test_user_reported_amount_is_not_a_statutory_penalty_claim(self):
        q='Cửa hàng buộc nhân viên nộp phạt 420.000 đồng khi đi trễ thay kỷ luật, có đúng không?'
        text='Việc nhân viên bị phạt tiền 420000 đồng thay cho xử lý kỷ luật là trái pháp luật.'
        self.assertNotIn('CLAIM_MONETARY_PENALTY_WITHOUT_SANCTION_SOURCE',self.issues(text,q))
    def test_unprovided_case_amount_still_cannot_be_invented(self):
        q='Cửa hàng buộc nhân viên nộp phạt 420.000 đồng thay kỷ luật có được không?'
        text='Việc nhân viên bị phạt tiền 900.000 đồng thay cho xử lý kỷ luật là trái pháp luật.'
        self.assertIn('CLAIM_MONETARY_PENALTY_WITHOUT_SANCTION_SOURCE',self.issues(text,q))
    def test_same_amount_cannot_be_repurposed_as_a_state_penalty(self):
        q='Cửa hàng buộc nhân viên nộp phạt 420.000 đồng thay kỷ luật có được không?'
        text='Vì hành vi trái pháp luật này, cửa hàng bị xử phạt vi phạm hành chính với mức phạt tiền 420.000 đồng.'
        self.assertIn('CLAIM_MONETARY_PENALTY_WITHOUT_SANCTION_SOURCE',self.issues(text,q))
    def test_adverse_legal_penalty_cannot_hide_behind_an_unlawful_cause(self):
        q='Cửa hàng buộc nhân viên nộp phạt 420.000 đồng thay kỷ luật có được không?'
        text='Cửa hàng bị phạt tiền 420.000 đồng vì hành vi trái pháp luật của mình.'
        self.assertIn('CLAIM_MONETARY_PENALTY_WITHOUT_SANCTION_SOURCE',self.issues(text,q))
    def test_no_query_fact_is_not_a_blanket_permission(self):
        self.assertIn('CLAIM_MONETARY_PENALTY_WITHOUT_SANCTION_SOURCE',self.issues('Nhân viên bị phạt tiền 420.000 đồng là trái pháp luật.',''))

if __name__=='__main__':unittest.main()
