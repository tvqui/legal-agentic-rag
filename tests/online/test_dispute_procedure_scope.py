import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence


class DisputeProcedureScopeTests(unittest.TestCase):
    def analyze(self,q,day='2026-09-15'):
        a=analyze(intake(q,[]),day)
        return a,plan_evidence(a)

    def test_dismissal_as_dispute_subject_does_not_request_employer_procedure(self):
        for kind in ('sa thải','đơn phương chấm dứt hợp đồng'):
            a,p=self.analyze(f'Tranh chấp lao động cá nhân về {kind} có bắt buộc hòa giải trước khi yêu cầu tòa án giải quyết không?')
            self.assertFalse(any(k.startswith('TERMINATION.') for k in a.legal_subissues))
            self.assertNotIn('discipline_procedure',p.slot_requirements)
            self.assertNotIn('dismissal_procedure_rule',p.slot_requirements)
            loc=p.slot_requirements['individual_mediation_rule'][0][0]
            self.assertEqual((loc.article,loc.clause,loc.point),('188','1','a'))
            self.assertTrue(all(t.description!='Sa thải theo kỷ luật' for t in a.answer_tasks))

    def test_historical_mediation_uses_the_old_code(self):
        _,p=self.analyze('Tranh chấp về sa thải có cần hòa giải viên lao động trước khi khởi kiện không?','2020-07-11')
        loc=p.slot_requirements['individual_mediation_rule'][0][0]
        self.assertEqual((loc.article,loc.documents),('201',['10/2012/QH13']))

    def test_other_exception_subjects_keep_their_distinct_branches(self):
        for subject,point in [('trợ cấp thôi việc','b'),('giúp việc gia đình','c'),('bảo hiểm xã hội','d'),('người lao động thuê lại','e')]:
            with self.subTest(subject=subject):
                _,p=self.analyze(f'Tranh chấp lao động cá nhân về {subject} có bắt buộc hòa giải trước khi ra tòa án không?')
                self.assertEqual(p.slot_requirements['individual_mediation_rule'][0][0].point,point)

    def test_mixed_request_retains_dismissal_legality_and_dispute_procedure(self):
        a,p=self.analyze('Công ty có quyền sa thải tôi không? Nếu khởi kiện tranh chấp lao động cá nhân thì có cần hòa giải trước không?')
        self.assertIn('TERMINATION.DISMISSAL',a.legal_subissues)
        self.assertIn('dismissal_ground_rule',p.slot_requirements)
        self.assertIn('individual_mediation_rule',p.slot_requirements)

    def test_collective_dispute_is_not_mapped_to_individual_procedure(self):
        _,p=self.analyze('Tranh chấp lao động tập thể có phải hòa giải trước khi yêu cầu tòa án không?')
        self.assertNotIn('individual_mediation_rule',p.slot_requirements)

    def test_nonemployment_mediation_does_not_acquire_labour_law_anchors(self):
        from vn_labor_online.dispute_context import individual_mediation_requested
        for subject in ('đất đai','ly hôn','mua bán căn hộ'):
            self.assertFalse(individual_mediation_requested(f'Tranh chấp {subject} có cần hòa giải trước khi kiện ra tòa án không?'))

    def test_notice_question_is_not_erased_by_an_additional_dispute_question(self):
        a,p=self.analyze('Tôi muốn đơn phương nghỉ việc, phải báo trước bao lâu? Tranh chấp lao động cá nhân về việc chấm dứt này có cần hòa giải trước khi khởi kiện không?')
        self.assertIn('TERMINATION.EMPLOYEE_UNILATERAL',a.legal_subissues)
        self.assertIn('individual_mediation_rule',p.slot_requirements)


if __name__=='__main__':unittest.main()
