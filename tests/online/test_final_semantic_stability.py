"""Adversarial semantic tests with synthetic sources, not benchmark answer templates."""
import unittest
from types import SimpleNamespace as NS
from vn_labor_online.claim_validation import semantic_issues,fold,omitted_coupled_reporting_duties
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.models import Claim,AdjudicationDraft,VerifiedEvidenceItem
from vn_labor_online.answer_review import Review,ClaimVerdict,Grounding,CoverageVerdict,reject_invalid_support

class CapAndFormulaTests(unittest.TestCase):
    def cap(self,extra=False):
        text='Khi ký hợp đồng lao động mới thì chỉ được ký thêm 01 lần, sau đó phải ký hợp đồng lao động không xác định thời hạn.'
        sources=[NS(text=text,full_text=text)]
        if extra:sources.append(NS(text='Theo ngoại lệ, hai bên được giao kết nhiều lần hợp đồng.',full_text='Theo ngoại lệ, hai bên được giao kết nhiều lần hợp đồng.'))
        return sources
    def test_ordinal_and_upper_bound_do_not_reset_cap(self):
        for text in ['Sau hợp đồng thứ hai, hai bên được ký thêm tối đa 01 lần.',
          'Sau khi giao kết hợp đồng lao động xác định thời hạn thứ 2 hết hạn, được ký thêm một lần.',
          'Sau hai hợp đồng, được ký thêm tối đa 01 hợp đồng.']:
            with self.subTest(text=text):self.assertIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues(text,self.cap()))
    def test_unrelated_exception_source_does_not_rescue_ordinary_claim(self):
        self.assertIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues('Sau hợp đồng thứ hai, được ký thêm một lần.',self.cap(True)))
    def test_negative_and_valid_first_renewal_survive(self):
        for text in ['Sau hợp đồng thứ hai, không được ký thêm một lần.', 'Sau một hợp đồng, được ký thêm một lần.']:
            self.assertNotIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues(text,self.cap()))
    def test_verbal_formula_needs_explicit_grouping(self):
        source=NS(text='Công thức: Tiền = (Lương giờ + Lương giờ x 30%) x Số giờ.',full_text='Công thức: Tiền = (Lương giờ + Lương giờ x 30%) x Số giờ.')
        bad='Công thức tiền bằng lương giờ cộng lương giờ nhân 30% nhân số giờ.'
        self.assertIn('CLAIM_AMBIGUOUS_FORMULA_GROUPING',semantic_issues(bad,[source]))
        for good in ['Công thức tiền = (lương giờ + lương giờ × 30%) × số giờ.',
          'Công thức lấy tổng của lương giờ và phần trả thêm rồi nhân số giờ.']:
            self.assertNotIn('CLAIM_AMBIGUOUS_FORMULA_GROUPING',semantic_issues(good,[source]))
    def test_literal_source_formula_remains_quoted_data(self):
        text='Công thức tiền = lương giờ + phụ cấp × số giờ.'
        self.assertNotIn('CLAIM_AMBIGUOUS_FORMULA_GROUPING',semantic_issues(text,[NS(text=text,full_text=text)]))

class CoupledDutyTests(unittest.TestCase):
    text='Người lao động được từ chối làm việc khi thấy nguy hiểm nhưng phải báo ngay cho người quản lý trực tiếp.'
    def source(self):return VerifiedEvidenceItem(evidence_id='s',text=self.text,full_text=self.text)
    def right(self):return Claim(claim_id='right',text='Người lao động có quyền từ chối làm việc khi thấy nguy hiểm.',evidence_ids=['s'])
    def test_omission_and_negation_are_detected(self):
        self.assertIn('right',omitted_coupled_reporting_duties([self.right()],[self.source()]))
        denied=Claim(claim_id='duty',text='Không cần báo ngay cho người quản lý.',evidence_ids=['s'])
        self.assertIn('right',omitted_coupled_reporting_duties([self.right(),denied],[self.source()]))
    def test_separate_cited_duty_is_allowed(self):
        duty=Claim(claim_id='duty',text='Phải báo ngay cho người quản lý trực tiếp.',evidence_ids=['s'])
        self.assertFalse(omitted_coupled_reporting_duties([self.right(),duty],[self.source()]))
    def test_no_duty_is_invented_for_unqualified_source(self):
        source=self.source().model_copy(update={'full_text':'Người lao động được từ chối làm việc khi nguy hiểm.'})
        self.assertFalse(omitted_coupled_reporting_duties([self.right()],[source]))
    def test_final_task_selection_cannot_drop_a_supported_duty(self):
        from vn_labor_online.answer_review import retain_task_grounded_claims
        duty=Claim(claim_id='duty',text='Phải báo ngay cho người quản lý trực tiếp.',evidence_ids=['s'])
        draft=AdjudicationDraft(answer_summary='',claims=[self.right(),duty],applicable_law_versions=[])
        review=Review(claims=[ClaimVerdict(claim_id=c.claim_id,verdict='SUPPORTED',grounding=[Grounding(evidence_id='s',quote=self.text)],reason='fixture') for c in draft.claims],
            coverage=[CoverageVerdict(task_id='t',status='ANSWERED',claim_ids=['right'],missing='')],question_fully_addressed=True,missing_requirements=[])
        checked,removed=retain_task_grounded_claims(draft,review,NS(evidence=[self.source()]))
        self.assertEqual([c.claim_id for c in checked.claims],['right','duty']);self.assertFalse(removed)
    def test_full_review_repairs_a_false_pass_before_publishing(self):
        from unittest.mock import Mock
        from vn_labor_online.answer_review import review_answer
        from vn_labor_online.models import VerifiedEvidencePack,EvidenceState,AnswerTask
        task=AnswerTask(task_id='t',request_quote='Quyền và nghĩa vụ?',description='Quyền và nghĩa vụ',retrieval_query='Quyền và nghĩa vụ')
        pack=VerifiedEvidencePack(query='Quyền và nghĩa vụ?',requested_outcome='EXPLAIN',evidence=[self.source()],answer_tasks=[task],coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
        draft=AdjudicationDraft(answer_summary='',claims=[self.right()],applicable_law_versions=[])
        def verdict(cid):
            return {'claims':[{'claim_id':cid,'verdict':'SUPPORTED','grounding':[{'evidence_id':'s','quote':self.text}],'reason':'fixture'}],
                'coverage':[{'task_id':'t','status':'ANSWERED','claim_ids':[cid],'missing':''}],'question_fully_addressed':True,'missing_requirements':[]}
        provider=Mock();provider.structured.side_effect=[verdict('right'),{'claims':[{'text':self.text,'evidence_ids':['s']}]},verdict('claim_001')]
        result,_=review_answer(provider,draft,pack,1)
        self.assertEqual(result.semantic_review['status'],'PASS')
        self.assertIn('phải báo ngay',result.claims[0].text)
        self.assertEqual(provider.structured.call_count,3)
    def test_false_model_pass_is_demoted_for_repair(self):
        draft=AdjudicationDraft(answer_summary='',claims=[self.right()],applicable_law_versions=[])
        review=Review(claims=[ClaimVerdict(claim_id='right',verdict='SUPPORTED',grounding=[Grounding(evidence_id='s',quote=self.text)],reason='fixture')],
            coverage=[CoverageVerdict(task_id='t',status='ANSWERED',claim_ids=['right'],missing='')],question_fully_addressed=True,missing_requirements=[])
        checked,rejected=reject_invalid_support(review,draft,NS(evidence=[self.source()],query=''))
        self.assertIn('right',rejected);self.assertFalse(checked.question_fully_addressed)
        self.assertEqual(checked.claims[0].verdict,'UNSUPPORTED');self.assertEqual(checked.coverage[0].status,'MISSING')

class IndependentSourceGroupsTests(unittest.TestCase):
    def requirements(self,q):return plan_evidence(analyze(intake(q,[],'2026-09-15'),'2026-09-15')).slot_requirements
    def test_payment_principles_and_disposal_both_present(self):
        slots=self.requirements('Về nguyên tắc trả lương, có phải trả trực tiếp, đầy đủ và đúng hạn không? Doanh nghiệp có được can thiệp cách tôi chi tiêu lương không?')
        self.assertIn('wage_payment_principles',slots);self.assertIn('payment_disposal',slots)
    def test_bonus_basis_and_procedure_are_distinct(self):
        slots=self.requirements('Tiền thưởng dựa trên yếu tố nào? Công ty cần làm gì trước khi công bố quy chế thưởng?')
        self.assertEqual(slots['bonus_basis'][0][0].clause,'1')
        self.assertEqual(slots['bonus_regulation_procedure'][0][0].clause,'2')
    def test_explicit_discipline_reference_list_has_both_clauses(self):
        slots=self.requirements('Khi đang chờ xác minh thì có được kỷ luật không? Những nhóm hành vi được dẫn chiếu gồm những gì?')
        self.assertEqual([g[0].clause for g in slots['pending_discipline_cross_reference']],['1','2'])
    def test_incidental_full_salary_does_not_add_payment_principles(self):
        slots=self.requirements('Tôi đã cung cấp đầy đủ hồ sơ để hỏi về lương thử việc tối thiểu.')
        self.assertNotIn('wage_payment_principles',slots)

if __name__=='__main__':unittest.main()
