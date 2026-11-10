import json
import unittest
from unittest.mock import Mock, patch

from vn_labor_online.analysis import analyze, intake, plan_evidence
from vn_labor_online.answer_quality import render_claims
from vn_labor_online.answer_review import compose_answer
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.claim_validation import semantic_issues
from vn_labor_online.config import AdjudicationConfig, ApplicabilityConfig
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.models import AdjudicationDraft, Claim, EvidenceState, VerifiedEvidenceItem, VerifiedEvidencePack
from tests.online.test_runtime_reliability import lookup


def sample():
    text='Bên nhận được kiểm tra hồ sơ và phải thông báo cho bên giao.'
    item=VerifiedEvidenceItem(evidence_id='source', text=text, full_text=text)
    pack=VerifiedEvidencePack(query='Bên nhận có được kiểm tra hồ sơ không?',
        evidence=[item], coverage_state=EvidenceState(slots={}, gaps=[], coverage=1))
    draft=AdjudicationDraft(answer_summary='', applicable_law_versions=[],
        claims=[Claim(claim_id='old', text=text, evidence_ids=['source'])])
    return pack,draft


class AnswerCompositionTests(unittest.TestCase):
    def test_composed_text_still_requires_an_independent_review(self):
        pack,draft=sample()
        engine=LegalAdjudicator(AdjudicationConfig(mode='ollama'))
        engine._review_provider=Mock()
        text='Bên nhận được kiểm tra hồ sơ.'
        engine._review_provider.structured.return_value={'claims':[{'text':text,'evidence_ids':['source']}]}
        def checked(provider,candidate,*args):
            self.assertEqual(candidate.claims[0].text,text)
            self.assertFalse(candidate.semantic_review)
            return candidate.model_copy(update={'semantic_review':{'status':'PASS'}}),[]
        with patch.object(engine,'_generate_with_layout',return_value=(draft,[])), patch('vn_labor_online.answer_review.review_answer',side_effect=checked) as reviewer:
            result,warnings=engine.generate(pack,False)
        reviewer.assert_called_once()
        self.assertIn(text,result.answer_summary)
        self.assertIn('ANSWER_COMPOSED_FOR_REVIEW',warnings)

    def test_foreign_citation_is_never_accepted_by_composer(self):
        pack,draft=sample(); provider=Mock()
        provider.structured.return_value={'claims':[{'text':'Nội dung mới.','evidence_ids':['invented']}]}
        with self.assertRaises(StructuredOutputError):compose_answer(provider,draft,pack)

    def test_composer_receives_original_source_and_does_not_mutate_it(self):
        pack,draft=sample(); original=pack.model_dump(); provider=Mock()
        provider.structured.return_value={'claims':[{'text':draft.claims[0].text,'evidence_ids':['source']}]}
        result=compose_answer(provider,draft,pack)
        payload=json.loads(provider.structured.call_args.args[1])
        self.assertEqual(payload['evidence'][0]['full_text'],pack.evidence[0].full_text)
        self.assertEqual(pack.model_dump(),original)
        self.assertFalse(result.semantic_review)

    def test_gemini_composition_failure_blocks_unverified_conclusions(self):
        pack,draft=sample(); engine=LegalAdjudicator(AdjudicationConfig(mode='ollama'))
        engine._review_provider=Mock(); engine._review_provider.structured.side_effect=RuntimeError('unavailable')
        with patch.object(engine,'_generate_with_layout',return_value=(draft,[])):
            result,warnings=engine.generate(pack,False)
        self.assertFalse(result.claims)
        self.assertEqual(result.semantic_review['status'],'ERROR')
        self.assertIn('ANSWER_QUALITY_BLOCKED',warnings)

    def test_literal_answer_also_reaches_gemini_when_configured(self):
        pack=lookup(); engine=LegalAdjudicator(AdjudicationConfig(mode='ollama'))
        engine._review_provider=Mock()
        def checked(provider,draft,*args):
            self.assertIs(provider,engine._review_provider)
            self.assertEqual(draft.claims[0].text,pack.evidence[0].full_text)
            return draft.model_copy(update={'semantic_review':{'status':'PASS'}}),[]
        with patch('vn_labor_online.answer_review.review_answer',side_effect=checked) as review:
            result,_=engine.generate(pack,True)
        review.assert_called_once()
        engine._review_provider.structured.assert_not_called()  # No rewriting of a quotation.
        self.assertEqual(result.semantic_review['status'],'PASS')

    def test_literal_gemini_failure_cannot_restore_the_unchecked_quote(self):
        engine=LegalAdjudicator(AdjudicationConfig(mode='ollama'))
        engine._review_provider=Mock();engine._review_provider.structured.side_effect=RuntimeError('unavailable')
        result,warnings=engine.generate(lookup(),True)
        self.assertFalse(result.claims)
        self.assertEqual(result.semantic_review['status'],'ERROR')
        self.assertIn('ANSWER_QUALITY_BLOCKED',warnings)

    def test_rendering_keeps_markers_on_the_claim_line_and_separates_paragraphs(self):
        _,draft=sample()
        draft.claims.append(Claim(claim_id='second',text='Phải thông báo.',evidence_ids=['source']))
        text=render_claims(draft,False).answer_summary
        self.assertIn('bên giao. [source]\n\n- Phải thông báo. [source]',text)
        self.assertNotIn('Các quy định liên quan tìm được',text)

    def test_rejected_composition_still_requires_review_of_the_unchanged_draft(self):
        pack,draft=sample(); engine=LegalAdjudicator(AdjudicationConfig(mode='ollama'))
        engine._review_provider=Mock()
        checked=draft.model_copy(update={'claims':[],'semantic_review':{'status':'FAIL'}})
        with patch.object(engine,'_generate_with_layout',return_value=(draft,[])), patch(
                'vn_labor_online.answer_review.compose_answer',side_effect=StructuredOutputError('invalid edit')), patch(
                'vn_labor_online.answer_review.review_answer',return_value=(checked,['ANSWER_QUALITY_BLOCKED'])) as review:
            result,warnings=engine.generate(pack,False)
        self.assertEqual(review.call_args.args[1],draft)
        self.assertFalse(result.claims)
        self.assertIn('ANSWER_COMPOSITION_REJECTED_FOR_REVIEW',warnings)

    def test_composition_preserves_large_task_sets_by_batching(self):
        from vn_labor_online.models import AnswerTask
        pack,draft=sample()
        nouns=['hồ sơ','chứng từ','bản sao','danh mục','phiếu giao','biên nhận','văn bản','giấy phép','tài liệu']
        evidence=[VerifiedEvidenceItem(evidence_id=f'e{i}',text=f'Bên nhận phải kiểm tra {noun}.')
            for i,noun in enumerate(nouns)]
        tasks=[AnswerTask(task_id=f't{i}',request_quote='Cần kiểm tra những nội dung nào?',
            description=noun,retrieval_query=noun) for i,noun in enumerate(nouns)]
        pack=pack.model_copy(update={'evidence':evidence,'answer_tasks':tasks})
        provider=Mock()
        provider.structured.side_effect=[{'claims':[{'text':e.text,'evidence_ids':[e.evidence_id]} for e in group]}
            for group in (evidence[:8],evidence[8:])]
        composed=compose_answer(provider,draft,pack)
        self.assertEqual(provider.structured.call_count,2)
        self.assertEqual(len(composed.claims),9)
        self.assertEqual([c.claim_id for c in composed.claims],[f'claim_{i:03d}' for i in range(1,10)])
        self.assertFalse(composed.semantic_review)


class CompleteExecutionRegressionTests(unittest.TestCase):
    def test_minor_profile_audit_receives_outcome_and_never_crashes(self):
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig())
        for age in (12,14,16):
            query=f'Người lao động {age} tuổi có được bố trí làm 5 giờ mỗi ngày hoặc làm thêm ban đêm không?'
            a=analyze(intake(query,[]),'2026-11-10')
            with self.subTest(age=age):
                self.assertIn('minor_working_time',plan_evidence(a).slot_requirements)
                self.assertEqual(auditor._deterministic([],query,a.legal_issues,a.facts,a.requested_outcome)[0],[])

    def test_rest_question_has_no_unrequested_night_pay_task(self):
        for query in ('Tôi làm ca đêm 7 giờ. Được nghỉ giữa giờ ít nhất bao lâu?',
                      'Một người làm ban đêm theo thời giờ bình thường 7 giờ trong ngày được nghỉ giữa giờ ít nhất bao lâu?'):
            a=analyze(intake(query,[]))
            self.assertIn('WORKING_TIME.REST_BREAK',a.legal_subissues)
            self.assertFalse(any('night_work' in task.topic_ids for task in a.answer_tasks))

    def test_explicit_pay_and_break_requests_both_survive(self):
        a=analyze(intake('Tôi làm ban đêm 7 giờ. Được nghỉ giữa giờ bao lâu và tiền lương ban đêm được trả thêm thế nào?',[]))
        self.assertIn('WORKING_TIME.REST_BREAK',a.legal_subissues)
        self.assertIn('WAGE.NIGHT_PAY',a.legal_subissues)

    def test_subject_qualified_consequence_cannot_be_generalized(self):
        source='Người lao động làm việc theo ca liên tục từ 06 giờ trở lên thì thời gian nghỉ giữa giờ được tính vào giờ làm việc.'
        item=VerifiedEvidenceItem(evidence_id='break',text=source)
        self.assertIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',semantic_issues(
            'Thời gian nghỉ giữa giờ được tính vào giờ làm việc.',[item],context_query='Tôi làm ban đêm 7 giờ.'))
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',semantic_issues(source,[item]))

    def test_independent_medical_cost_task_survives_unusable_first_aid_source(self):
        from vn_labor_online.models import Evidence
        from vn_labor_online.tasks import independent_partial_plan
        q='Tôi bị thương khi làm nhiệm vụ tại xưởng. Công ty phải sơ cứu và thanh toán các chi phí y tế nào?'
        a=analyze(intake(q,[]),'2026-11-10')
        self.assertEqual({key for t in a.answer_tasks for key in t.legal_subissues},
            {'SAFETY.ACCIDENT_FIRST_AID','SAFETY.ACCIDENT_MEDICAL_COSTS'})
        medical=Evidence(unit_id='medical',kind='PROVISION',retrieval_method='policy',
            provision_version_id='medical',source_catalog_status='VERIFIED',
            document_number='84/2015/QH13',article_number='38',clause_number='2',
            text='Thanh toán chi phí y tế từ khi sơ cứu, cấp cứu đến khi điều trị ổn định.',
            verified=True,official_source=True,authority_rank=100,binding=True,
            source_url='https://vbpl.vn/official',valid_from='2016-07-01',
            provision_temporal_verified=True,temporal_verified=True)
        plan,ids=independent_partial_plan(a,[medical],True)
        self.assertIsNotNone(plan)
        self.assertEqual(ids,['medical'])
        self.assertIn('accident_medical_costs',plan.slot_requirements)
        self.assertNotIn('accident_first_aid',plan.slot_requirements)


if __name__=='__main__':unittest.main()
