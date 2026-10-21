import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.answer_quality import language_issues
from vn_labor_online.answer_review import hard_issues
from vn_labor_online.claim_validation import invalid_clause_locator,semantic_issues
from vn_labor_online.models import Claim,VerifiedEvidenceItem


class LocatorAndStatuteScopeTests(unittest.TestCase):
    def test_a_point_letter_cannot_be_presented_as_a_numbered_clause(self):
        text='Quyền được quy định tại Điều 6, khoản đ của Luật An toàn, vệ sinh lao động.'
        source=VerifiedEvidenceItem(evidence_id='safety',instrument_number='84/2015/QH13',article='6',clause='1',point='đ',
            text='Người lao động được từ chối công việc khi có nguy cơ đe dọa nghiêm trọng sức khỏe.')
        claim=Claim(claim_id='claim',text=text,evidence_ids=['safety'])
        self.assertTrue(invalid_clause_locator(text))
        self.assertIn('SUSPECT_LEGAL_LOCATOR',language_issues(text))
        self.assertIn('CLAIM_CLAUSE_POINT_CONFUSION',hard_issues(claim,[source]))

    def test_a_real_point_and_an_explicit_correction_are_preserved(self):
        for text in ('Điểm đ khoản 1 Điều 6 quy định quyền của người lao động.',
            'Không có “khoản đ”; đây là điểm đ khoản 1 Điều 6.',
            'Ghi sai là khoản a, đúng phải là điểm a khoản 2.'):
            self.assertFalse(invalid_clause_locator(text),text)

    def test_a_positive_rule_in_one_statute_does_not_prove_absence_from_another(self):
        source=VerifiedEvidenceItem(evidence_id='s',instrument_number='84/2015/QH13',article='6',text='Người lao động có quyền từ chối công việc nguy hiểm.')
        bad='Quyền từ chối công việc nguy hiểm nằm trong Luật An toàn, vệ sinh lao động, không phải trong Bộ luật Lao động.'
        self.assertIn('CLAIM_STATUTORY_ABSENCE_NOT_GROUNDED',semantic_issues(bad,[source]))
        self.assertNotIn('CLAIM_STATUTORY_ABSENCE_NOT_GROUNDED',semantic_issues('Luật An toàn, vệ sinh lao động quy định quyền từ chối công việc nguy hiểm.',[source]))

    def test_refusal_mechanism_has_both_dated_authorities_without_assuming_the_case(self):
        for question in ('Quyền từ chối công việc nguy hiểm được quy định ở đâu?',
            'Tôi được rời bỏ nơi làm việc khi có nguy cơ đe dọa sức khỏe không?'):
            analysis=analyze(intake(question,[]),'2026-01-01')
            groups=plan_evidence(analysis).slot_requirements
            self.assertEqual(groups['dangerous_work_refusal_labour_code'][0][0].article,'5')
            self.assertEqual(groups['dangerous_work_refusal_labour_code'][0][0].point,'d')
            self.assertEqual(groups['dangerous_work_refusal_safety_law'][0][0].documents,['84/2015/QH13'])
            self.assertNotIn('conditions_satisfied',analysis.facts)
        old=plan_evidence(analyze(intake('Quyền từ chối công việc nguy hiểm?',[]),'2020-01-01'))
        self.assertNotIn('dangerous_work_refusal_labour_code',old.slot_requirements)
