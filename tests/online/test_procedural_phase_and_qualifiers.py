"""Keep procedural stages and permission prerequisites distinct."""
import unittest
from types import SimpleNamespace
from vn_labor_online.claim_validation import semantic_issues


class ProceduralPhaseAndQualifierTests(unittest.TestCase):
    def source(self,text,number='01/VBHN-VPQH',article='413'):
        return SimpleNamespace(text=text,full_text=text,source_text=text,
            instrument_number=number,article=article)

    def appeal(self):
        item=self.source('Trong thời hạn 05 ngày làm việc, Hội đồng phúc thẩm phải tiến hành xét kháng cáo, kháng nghị.')
        item.ancestor_context='Trình tự, thủ tục giải quyết kháng cáo, kháng nghị quyết định về tính hợp pháp của cuộc đình công.'
        return item

    def wage(self):
        return self.source('Trường hợp vì lý do bất khả kháng mà người sử dụng lao động đã tìm mọi biện pháp khắc phục '
            'nhưng không thể trả lương đúng hạn thì không được chậm quá 30 ngày.',number='45/2019/QH14',article='97')

    def test_appeal_cannot_become_a_precondition_to_strike(self):
        issues=semantic_issues('Việc đình công phải tuân thủ trình tự, thủ tục giải quyết kháng cáo, kháng nghị quyết định về tính hợp pháp của cuộc đình công.',[self.appeal()])
        self.assertIn('CLAIM_JUDICIAL_REVIEW_AS_PRIMARY_PROCEDURE',issues)

    def test_same_error_for_another_workplace_action_is_rejected(self):
        self.assertIn('CLAIM_JUDICIAL_REVIEW_AS_PRIMARY_PROCEDURE',semantic_issues(
            'Sa thải phải thực hiện thủ tục giải quyết kháng cáo trước.',[self.appeal()]))

    def test_actual_appeal_phase_remains_available(self):
        self.assertFalse(semantic_issues('Thủ tục giải quyết kháng cáo quyết định về tính hợp pháp của cuộc đình công được quy định tại điều này.',[self.appeal()]))

    def test_explicit_correction_is_not_mistaken_for_permission(self):
        self.assertFalse(semantic_issues('Không thể coi việc đình công phải tuân thủ thủ tục giải quyết kháng cáo.',[self.appeal()]))

    def test_force_majeure_permission_cannot_omit_remedies(self):
        self.assertIn('CLAIM_LATE_WAGE_REMEDY_CONDITION_LOST',semantic_issues(
            'Trường hợp bất khả kháng thì được phép chậm không quá 30 ngày.',[self.wage()]))

    def test_complete_conditional_permission_is_retained(self):
        self.assertFalse(semantic_issues('Nếu bất khả kháng và đã tìm mọi biện pháp khắc phục nhưng không thể trả đúng hạn thì được chậm không quá 30 ngày.',[self.wage()]))

    def test_upper_bound_alone_does_not_assert_permission(self):
        for claim in ('Không được chậm quá 30 ngày trong trường hợp bất khả kháng.',
            'Dù bất khả kháng, chưa được phép chậm trả lương khi chưa đủ điều kiện.'):
            with self.subTest(claim=claim):
                self.assertFalse(semantic_issues(claim,[self.wage()]))

    def test_explicitly_unresolved_conditions_are_preserved(self):
        self.assertFalse(semantic_issues('Trường hợp bất khả kháng được chậm tối đa 30 ngày khi đáp ứng đủ điều kiện của quy định.',[self.wage()]))


if __name__=='__main__': unittest.main()
