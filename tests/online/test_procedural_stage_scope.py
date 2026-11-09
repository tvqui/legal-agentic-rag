import unittest
from vn_labor_online.models import Evidence
from vn_labor_online.config import ApplicabilityConfig
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.claim_validation import semantic_issues

class ProceduralStageScopeTests(unittest.TestCase):
    def source(self,kind='PROVISION'):
        text='Đương sự có yêu cầu Tòa án bảo vệ quyền và lợi ích hợp pháp của mình phải thu thập, cung cấp chứng cứ.'
        return Evidence(unit_id='court',kind=kind,retrieval_method='bm25',text=text,source_text=text,document_number='92/2015/QH13',article_number='91')
    def test_court_burden_does_not_become_internal_disciplinary_burden(self):
        source=self.source();q='Ai phải chứng minh lỗi khi công ty xử lý kỷ luật lao động?'
        _,decisions,_=LegalApplicabilityAuditor(ApplicabilityConfig()).audit([source],q,['DISCIPLINE'],{},'EXPLAIN')
        self.assertEqual(decisions[0].audit_status,'FAIL')
        self.assertIn('WRONG_PROCEDURAL_STAGE',decisions[0].reasons)
    def test_final_claim_audit_also_checks_the_procedural_stage(self):
        self.assertIn('CLAIM_WRONG_PROCEDURAL_STAGE',semantic_issues('Người lao động phải tự cung cấp chứng cứ khi công ty xử lý kỷ luật.',[self.source()],context_query='Công ty xử lý kỷ luật lao động thì ai chứng minh lỗi?'))
    def test_requested_court_comparison_keeps_court_sources(self):
        issues=semantic_issues('Đương sự có yêu cầu Tòa án phải cung cấp chứng cứ.',[self.source()],context_query='So sánh chứng minh trong xử lý kỷ luật lao động và khi khởi kiện tại Tòa án.')
        self.assertNotIn('CLAIM_WRONG_PROCEDURAL_STAGE',issues)
    def test_case_kind_survives_verified_pack_and_reviewer_payload(self):
        from vn_labor_online.evidence import build_verified_pack
        from vn_labor_online.models import EvidenceState
        from vn_labor_online.answer_review import source_payload
        item=self.source('CASE').model_copy(update={'verified':True})
        pack=build_verified_pack('Đánh giá xử lý kỷ luật lao động.','2026-09-15',{},EvidenceState(slots={},gaps=[],coverage=1),[item])
        self.assertEqual(pack.evidence[0].kind,'CASE')
        self.assertEqual(source_payload(pack.evidence[0])['kind'],'CASE')
        self.assertNotIn('CLAIM_WRONG_PROCEDURAL_STAGE',semantic_issues('Tình huống tương tự trong vụ án.',pack.evidence,context_query=pack.query))
    def test_case_analogy_channel_is_not_filtered_as_procedural_statute(self):
        _,decisions,_=LegalApplicabilityAuditor(ApplicabilityConfig()).audit([self.source('CASE')],'Đánh giá xử lý kỷ luật lao động trong tình huống tương tự.',['DISCIPLINE'],{},'EXPLAIN')
        self.assertNotIn('WRONG_PROCEDURAL_STAGE',decisions[0].reasons)

if __name__=='__main__':unittest.main()
