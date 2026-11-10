import unittest
from vn_labor_online.claim_validation import semantic_issues
from vn_labor_online.models import VerifiedEvidenceItem


class ConditionalConsequenceGroundingTests(unittest.TestCase):
    source='Trường hợp người giao sử dụng hồ sơ bản chính thì thời gian kiểm đếm được tính vào thời gian bàn giao.'
    consequence='Thời gian kiểm đếm được tính vào thời gian bàn giao.'

    def check(self,text,query=''):
        item=VerifiedEvidenceItem(evidence_id='rule',text=self.source,full_text=self.source)
        return semantic_issues(text,[item],context_query=query)

    def test_exact_consequence_is_not_unconditionally_generalized(self):
        self.assertIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',self.check(self.consequence))

    def test_wrong_antecedent_is_not_a_substitute(self):
        self.assertIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',self.check(self.consequence+' Quy định này áp dụng cho hồ sơ điện tử.'))

    def test_source_qualification_or_an_explicit_condition_remains_supported(self):
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',self.check(self.source))
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',self.check(self.consequence+' nếu đáp ứng đầy đủ điều kiện đã nêu.'))

    def test_context_can_supply_a_confirmed_antecedent_but_not_its_negation(self):
        context='Người giao sử dụng hồ sơ bản chính.'
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',self.check(self.consequence,context))
        self.assertIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',self.check(self.consequence,'Người giao không sử dụng hồ sơ bản chính.'))

    def test_notification_duty_does_not_invent_an_advance_deadline(self):
        item=VerifiedEvidenceItem(evidence_id='n',text='Bên giao hồ sơ có quyền yêu cầu kiểm đếm và phải thông báo cho bên nhận.')
        issues=semantic_issues('Bên giao phải thông báo cho bên nhận trước khi bàn giao hồ sơ.',[item])
        self.assertIn('CLAIM_NOTIFICATION_ADVANCE_NOT_GROUNDED',issues)
        self.assertNotIn('CLAIM_NOTIFICATION_ADVANCE_NOT_GROUNDED',semantic_issues('Bên giao phải thông báo cho bên nhận.',[item]))

    def test_explicit_advance_notification_remains_supported(self):
        item=VerifiedEvidenceItem(evidence_id='n',text='Bên giao phải thông báo trước khi bàn giao hồ sơ.')
        self.assertNotIn('CLAIM_NOTIFICATION_ADVANCE_NOT_GROUNDED',semantic_issues(item.text,[item]))

    def test_negative_notification_claim_is_not_mistaken_for_a_new_duty(self):
        item=VerifiedEvidenceItem(evidence_id='n',text='Không phải thông báo cho bên nhận.')
        self.assertNotIn('CLAIM_NOTIFICATION_ADVANCE_NOT_GROUNDED',semantic_issues('Không cần thông báo trước khi bàn giao hồ sơ.',[item]))

    def test_postposed_restriction_cannot_be_replaced_with_a_different_condition(self):
        item=VerifiedEvidenceItem(evidence_id='r',text='Thời gian kiểm đếm được tính vào thời gian bàn giao đối với trường hợp người giao sử dụng hồ sơ bản chính quy định tại Điều 77.')
        claim=self.consequence[:-1]+' đối với trường hợp hồ sơ điện tử.'
        self.assertIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',semantic_issues(claim,[item]))
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',semantic_issues(item.text,[item]))

    def test_postposed_restriction_can_be_established_by_confirmed_context(self):
        item=VerifiedEvidenceItem(evidence_id='r',text='Thời gian kiểm đếm được tính vào thời gian bàn giao đối với trường hợp người giao sử dụng hồ sơ bản chính.')
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',semantic_issues(self.consequence,[item],context_query='Người giao sử dụng hồ sơ bản chính.'))

    def test_a_shorter_citation_does_not_remove_the_substantive_condition(self):
        item=VerifiedEvidenceItem(evidence_id='r',text='Nếu hồ sơ thuộc nhóm kiểm đếm quy định tại khoản 2 Điều 77 của Bộ luật này thì thời gian kiểm đếm được tính vào thời gian bàn giao.')
        claim='Nếu hồ sơ thuộc nhóm kiểm đếm tại khoản 2 Điều 77 thì thời gian kiểm đếm được tính vào thời gian bàn giao.'
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',semantic_issues(claim,[item]))

    def test_grammatical_paraphrase_keeps_the_agreement_and_its_condition(self):
        item=VerifiedEvidenceItem(evidence_id='r',text='Trường hợp hai bên thỏa thuận bằng hồ sơ bản chính nhưng có nội dung thể hiện về việc bàn giao thì thời gian kiểm đếm được tính vào thời gian bàn giao.')
        claim='Nếu thỏa thuận sử dụng hồ sơ bản chính có nội dung thể hiện việc bàn giao thì thời gian kiểm đếm được tính vào thời gian bàn giao.'
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',semantic_issues(claim,[item]))

    def test_time_subject_shortening_does_not_erase_its_qualification(self):
        item=VerifiedEvidenceItem(evidence_id='r',text='Thời gian nghỉ giữa giờ được tính vào giờ làm việc đối với trường hợp làm việc theo ca liên tục quy định tại khoản 3 Điều 63 Nghị định này ít nhất 30 phút.')
        self.assertIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',semantic_issues(
            'Nghỉ giữa giờ được tính vào giờ làm việc theo Điều 64.',[item],context_query='Tôi làm ban đêm 7 giờ.'))
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',semantic_issues(
            'Đối với trường hợp làm việc theo ca liên tục, thời gian nghỉ giữa giờ được tính vào giờ làm việc.',[item]))


if __name__=='__main__':unittest.main()
