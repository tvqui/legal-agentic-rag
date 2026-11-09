import unittest
from types import SimpleNamespace as NS
from vn_labor_online.claim_validation import semantic_issues
from vn_labor_online.answer_review import Review,reject_invalid_support,validate_review
from vn_labor_online.models import Claim,AdjudicationDraft,VerifiedEvidencePack,VerifiedEvidenceItem,EvidenceState,AnswerTask

class FormValidityBoundaryTests(unittest.TestCase):
    def source(self,text):return NS(text=text,full_text=text)
    def test_oral_permission_is_not_a_source_of_automatic_invalidity(self):
        source=self.source('Hai bên có thể giao kết hợp đồng bằng lời nói với thời hạn dưới một tháng, trừ các trường hợp được quy định riêng.')
        issues=semantic_issues('Hợp đồng lao động bằng miệng trong thời hạn 7 tháng không có giá trị pháp lý.',[source])
        self.assertIn('CLAIM_FORM_VIOLATION_AS_INVALIDITY',issues)
    def test_exclusive_effect_wording_is_also_a_legal_consequence(self):
        source=self.source('Hai bên có thể giao kết hợp đồng bằng lời nói với thời hạn dưới một tháng.')
        for claim in ['Hợp đồng miệng chỉ có hiệu lực trong trường hợp thời hạn dưới một tháng.',
                      'Hợp đồng miệng không có hiệu lực nếu kéo dài hai tháng.']:
            with self.subTest(claim=claim):
                self.assertIn('CLAIM_FORM_VIOLATION_AS_INVALIDITY',semantic_issues(claim,[source]))
    def test_stated_commencement_date_is_not_automatic_invalidity(self):
        source=self.source('Hợp đồng bằng văn bản có hiệu lực từ ngày các bên thỏa thuận.')
        self.assertNotIn('CLAIM_FORM_VIOLATION_AS_INVALIDITY',semantic_issues('Hợp đồng chỉ có hiệu lực từ ngày các bên thỏa thuận.',[source]))
    def test_electronic_form_duty_cannot_prove_a_contract_void(self):
        source=self.source('Hợp đồng giao kết dưới hình thức thông điệp dữ liệu được công nhận theo quy định.')
        self.assertIn('CLAIM_FORM_VIOLATION_AS_INVALIDITY',semantic_issues('Hợp đồng đó vô hiệu.',[source]))
    def test_an_explicit_invalidity_rule_is_still_usable(self):
        source=self.source('Hợp đồng bằng lời nói thuộc trường hợp này bị vô hiệu theo quyết định của cơ quan có thẩm quyền.')
        self.assertNotIn('CLAIM_FORM_VIOLATION_AS_INVALIDITY',semantic_issues('Hợp đồng thuộc trường hợp này vô hiệu.',[source]))
    def test_a_warning_against_automatic_invalidity_is_not_blocked(self):
        source=self.source('Hợp đồng phải giao kết bằng lời nói hoặc bằng văn bản tùy trường hợp.')
        for claim in ['Vi phạm hình thức không đồng nghĩa hợp đồng vô hiệu.',
                      'Chưa thể kết luận hợp đồng vô hiệu chỉ từ việc vi phạm hình thức.']:
            with self.subTest(claim=claim):
                self.assertNotIn('CLAIM_FORM_VIOLATION_AS_INVALIDITY',semantic_issues(claim,[source]))
    def test_a_false_reviewer_pass_rejects_only_the_unsupported_consequence(self):
        text='Hai bên có thể giao kết hợp đồng bằng lời nói với thời hạn dưới một tháng.'
        source=VerifiedEvidenceItem(evidence_id='s',text=text,full_text=text)
        claims=[Claim(claim_id='rule',text=text,evidence_ids=['s']),
                Claim(claim_id='consequence',text='Hợp đồng bằng miệng trong thời hạn 8 tháng không có giá trị pháp lý.',evidence_ids=['s'])]
        draft=AdjudicationDraft(answer_summary='',claims=claims,applicable_law_versions=[])
        pack=VerifiedEvidencePack(query='Hợp đồng 8 tháng chỉ thỏa thuận miệng có đúng không?',evidence=[source],coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
        review=Review.model_validate({'claims':[{'claim_id':c.claim_id,'verdict':'SUPPORTED','grounding':[{'evidence_id':'s','quote':text}],'reason':'Được hỗ trợ'} for c in claims],
            'coverage':[],'question_fully_addressed':False,'missing_requirements':[]})
        checked,rejections=reject_invalid_support(review,draft,pack)
        self.assertIn('consequence',rejections)
        supported=validate_review(checked,draft,pack,[])
        self.assertEqual(supported,{'rule'})

if __name__=='__main__':unittest.main()
