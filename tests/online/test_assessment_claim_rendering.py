import unittest
from vn_labor_online.answer_quality import render_claims
from vn_labor_online.generation import _chain_answer
from vn_labor_online.models import EvidenceState,VerifiedEvidenceItem,VerifiedEvidencePack


def pack(facts,items):
    return VerifiedEvidencePack(query='Hãy đánh giá việc nghỉ việc.',facts=facts,
        coverage_state=EvidenceState(slots={},gaps=[],coverage=1),evidence=[
            VerifiedEvidenceItem(evidence_id=uid,instrument_number='45/2019/QH14',article=article,
                clause=clause,point=point,text=text) for uid,article,clause,point,text in items])


class AssessmentClaimRenderingTests(unittest.TestCase):
    def test_mutual_assessment_survives_checked_claim_rendering(self):
        p=pack({'query_intent':'MUTUAL_TERMINATION','mutual_termination_agreement':True},
            [('agreement','34','3','','Hai bên thỏa thuận chấm dứt hợp đồng lao động.')])
        draft=_chain_answer(p,True,[])
        rendered=render_claims(draft,True)
        self.assertIn('không tự động coi đây',rendered.answer_summary)
        self.assertTrue(any(c.claim_id=='claim_mutual_assessment' and c.evidence_ids==['agreement'] for c in draft.claims))

    def test_mutual_intent_without_confirmed_agreement_does_not_add_case_conclusion(self):
        p=pack({'query_intent':'MUTUAL_TERMINATION'},
            [('agreement','34','3','','Hai bên thỏa thuận chấm dứt hợp đồng lao động.')])
        draft=_chain_answer(p,True,[])
        self.assertFalse(any(c.claim_id=='claim_mutual_assessment' for c in draft.claims))

    def test_late_pay_assessment_retains_exception_and_grounding(self):
        items=[('rule','35','2','b','Không được trả đủ lương hoặc trả lương không đúng thời hạn, trừ trường hợp quy định tại khoản 4 Điều 97.'),
            ('exception','97','4','','Trường hợp vì lý do bất khả kháng thì không được chậm quá 30 ngày.')]
        p=pack({'termination_basis':'LATE_WAGE','force_majeure_exception':False},items)
        draft=_chain_answer(p,True,[])
        conclusion=next(c for c in draft.claims if c.claim_id=='claim_notice_assessment')
        self.assertIn('khoản 4 Điều 97',conclusion.text)
        self.assertEqual(set(conclusion.evidence_ids),{'rule','exception'})
        self.assertIn('không thể chỉ dựa',render_claims(draft,True).answer_summary)
        p.facts.pop('force_majeure_exception')
        draft=_chain_answer(p,True,[])
        self.assertFalse(any(c.claim_id=='claim_notice_assessment' for c in draft.claims))
