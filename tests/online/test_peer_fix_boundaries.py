"""Counterexamples for the peer changes: preserve scope and observed failures."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from vn_labor_online.analysis import analyze, intake
from vn_labor_online.claim_validation import semantic_issues
from vn_labor_online.demo_progress import observe_model
from vn_labor_online.errors import LLMProviderError
from vn_labor_online.models import VerifiedEvidenceItem, QueryRequest
from vn_labor_online.period_answers import rule_periods
from vn_labor_online.runtime import request_budget


class PeerFixBoundaryTests(unittest.TestCase):
    def test_explicit_first_year_does_not_need_seniority_clarification(self):
        query=('Tôi 30 tuổi, không phải người khuyết tật, làm công việc trong điều kiện bình thường '
               'và vừa đủ 12 tháng cho cùng một công ty. Trong kỳ 12 tháng đó tôi được hưởng '
               'bao nhiêu ngày nghỉ hằng năm có lương?')
        analysis=analyze(intake(query,[]),'2026-09-15')
        self.assertFalse(analysis.missing_facts,analysis.missing_facts)

    def test_leave_base_only_does_not_need_seniority(self):
        query=('Tôi 30 tuổi, không khuyết tật, làm đủ 12 tháng trong điều kiện bình thường. '
               'Chỉ hỏi mức cơ sở, chưa tính thâm niên: tôi được bao nhiêu ngày nghỉ phép năm?')
        analysis=analyze(intake(query,[]),'2026-09-15')
        self.assertFalse(any('thâm niên' in question for question in analysis.missing_facts))

    def test_uncertain_negative_antecedent_is_not_established(self):
        item=VerifiedEvidenceItem(evidence_id='condition',text=(
            'Trường hợp hồ sơ không bị thất lạc thì bên nhận phải trả đủ chứng từ cho bên giao.'))
        issues=semantic_issues('Bên nhận phải trả đủ chứng từ cho bên giao.',[item],
            context_query='Tôi không biết hồ sơ không bị thất lạc hay không.')
        self.assertIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',issues)

    def test_unrelated_negative_does_not_negate_asserted_condition(self):
        item=VerifiedEvidenceItem(evidence_id='condition',text=(
            'Trường hợp hồ sơ đã được tiếp nhận thì bên nhận phải trả đủ chứng từ cho bên giao.'))
        issues=semantic_issues('Bên nhận phải trả đủ chứng từ cho bên giao.',[item],
            context_query='Hồ sơ đã được tiếp nhận nhưng tôi không giữ bản sao.')
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',issues)

    def test_bounded_hours_assessment_remains_allowed(self):
        item=VerifiedEvidenceItem(evidence_id='hours',article='105',clause='2',text=(
            'Thời giờ làm việc bình thường theo tuần không quá 10 giờ trong 01 ngày '
            'và không quá 48 giờ trong 01 tuần.'))
        issues=semantic_issues('Xét riêng giới hạn giờ làm trong ngày và tuần, '
            'công ty không vi phạm các giới hạn này.',[item],context_query=(
            'Tôi làm 10 giờ/ngày và 48 giờ/tuần theo chế độ theo tuần. '
            'Chỉ xét giới hạn thời giờ thì công ty có vi phạm không?'))
        self.assertNotIn('CLAIM_LIMITED_FACET_AS_OVERALL_LEGALITY',issues)

    def test_valid_comparison_can_cite_single_and_multiple_act_rules(self):
        sources=[VerifiedEvidenceItem(evidence_id='single',instrument_number='45/2019/QH14',
            article='122',clause='2',text='Không được áp dụng nhiều hình thức kỷ luật đối với một hành vi vi phạm.'),
            VerifiedEvidenceItem(evidence_id='multiple',instrument_number='45/2019/QH14',
            article='122',clause='3',text='Khi có nhiều hành vi vi phạm thì áp dụng hình thức cao nhất tương ứng hành vi nặng nhất.')]
        issues=semantic_issues('Khoản 2 Điều 122 cấm áp dụng nhiều hình thức cho cùng một hành vi; '
            'khoản 3 Điều 122 điều chỉnh nhiều hành vi đồng thời.',sources)
        self.assertNotIn('CLAIM_DISCIPLINE_SINGLE_ACT_CITATION_MISMATCH',issues)

    def test_discipline_guard_does_not_use_unrelated_instrument_number(self):
        source=VerifiedEvidenceItem(evidence_id='other',instrument_number='99/2024/TEST',
            article='122',clause='3',text='Một hành vi chỉ được áp dụng một hình thức xử lý.')
        issues=semantic_issues('Một hành vi chỉ được áp dụng một hình thức xử lý.',[source])
        self.assertNotIn('CLAIM_DISCIPLINE_SINGLE_ACT_CITATION_MISMATCH',issues)

    def test_shared_article_number_does_not_attach_point_to_every_clause(self):
        sources=[VerifiedEvidenceItem(evidence_id='ground',article='36',clause='1',point='e',
            text='Người lao động tự ý bỏ việc không có lý do chính đáng từ 05 ngày làm việc liên tục trở lên.'),
            VerifiedEvidenceItem(evidence_id='notice',article='36',clause='3',point='',
            text='Khi đơn phương chấm dứt trong trường hợp quy định tại điểm d và điểm e khoản 1 Điều này thì không phải báo trước.')]
        issues=semantic_issues('Theo điểm e khoản 1 và khoản 3 Điều 36, '
            'người sử dụng lao động không phải báo trước.',sources)
        self.assertNotIn('CLAIM_LOCATOR_METADATA_MISMATCH',issues)

    def test_second_article_does_not_inherit_first_articles_clause(self):
        source=VerifiedEvidenceItem(evidence_id='training',article='40',clause='3',
            text='Phải hoàn trả chi phí đào tạo cho người sử dụng lao động theo quy định tại Điều 62 của Bộ luật này.')
        issues=semantic_issues('Khoản 3 Điều 40 và Điều 62 quy định về hoàn trả chi phí đào tạo.',[source])
        self.assertNotIn('CLAIM_LOCATOR_METADATA_MISMATCH',issues)

    def test_conjunction_ma_van_is_not_an_antecedent(self):
        source=VerifiedEvidenceItem(evidence_id='leave',article='115',clause='1',point='a',
            ancestor_context='Người lao động được nghỉ việc riêng mà vẫn hưởng nguyên lương và phải thông báo với người sử dụng lao động:',
            text='a) Kết hôn: nghỉ 03 ngày;')
        issues=semantic_issues('Khi kết hôn, người lao động được nghỉ việc riêng 03 ngày '
            'mà vẫn hưởng nguyên lương và phải thông báo với người sử dụng lao động.',[source],
            context_query='Tôi kết hôn thì được nghỉ mấy ngày?')
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',issues)

    def test_qualifier_guard_works_in_a_compound_duty_claim(self):
        sources=[VerifiedEvidenceItem(evidence_id='proof',text='Người sử dụng lao động phải chứng minh được lỗi của người lao động;'),
            VerifiedEvidenceItem(evidence_id='representation',
                ancestor_context='Điều 122. Nguyên tắc xử lý kỷ luật. 1. Việc xử lý kỷ luật được quy định như sau:',
                text='b) Phải có sự tham gia của tổ chức đại diện người lao động tại cơ sở mà người lao động đang bị xử lý kỷ luật là thành viên;')]
        issues=semantic_issues('Khi xử lý kỷ luật, người sử dụng lao động phải chứng minh được lỗi '
            'của người lao động, có sự tham gia của tổ chức đại diện người lao động tại cơ sở.',sources,
            context_query='Cần xem những điều kiện xử lý kỷ luật nào?')
        self.assertIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST',issues)

    def test_published_amount_query_is_not_authority_question(self):
        analysis=analyze(intake('Mức lương tối thiểu tháng được công bố là bao nhiêu?',[]),'2026-09-15')
        self.assertNotIn('WAGE.MINIMUM_WAGE_AUTHORITY',analysis.legal_subissues)

    def test_authority_task_does_not_acquire_unasked_amount_tasks(self):
        from vn_labor_online.analysis import plan_evidence
        analysis=analyze(intake('Cơ quan nào quyết định mức lương tối thiểu, dựa trên khuyến nghị của ai?',[]),'2026-09-15')
        plan=plan_evidence(analysis)
        self.assertIn('minimum_wage_authority',plan.slot_requirements)
        self.assertNotIn('minimum_wage_operative_rule',plan.slot_requirements)
        self.assertNotIn('minimum_wage_salary_base',plan.slot_requirements)
        self.assertEqual(len(analysis.answer_tasks),1)

    def test_single_act_profile_retains_source_without_model_invented_condition(self):
        from vn_labor_online.applicability import LegalApplicabilityAuditor
        from vn_labor_online.config import ApplicabilityConfig
        from vn_labor_online.models import Evidence
        query='Cùng một hành vi vi phạm kỷ luật, công ty vừa khiển trách vừa kéo dài thời hạn nâng lương. Có được không?'
        analysis=analyze(intake(query,[]),'2026-09-15')
        item=Evidence(unit_id='single',kind='PROVISION',retrieval_method='fixture',document_number='45/2019/QH14',article_number='122',clause_number='2',
            text='Không được áp dụng nhiều hình thức xử lý kỷ luật lao động đối với một hành vi vi phạm kỷ luật lao động.',verified=True)
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid'))
        auditor.provider=Mock(side_effect=AssertionError('A proved scope does not need another model verdict'))
        kept,decisions,_=auditor.audit([item],query,analysis.legal_issues,analysis.facts,'ASSESS_LEGALITY')
        self.assertEqual([item.unit_id for item in kept],['single'])
        self.assertIn('DETERMINISTIC_DISCIPLINE_SCOPE',decisions[0].reasons)
        auditor.provider.structured.assert_not_called()
        uncertain='Tôi không biết hai quyết định có xử lý cùng một hành vi hay không. Công ty có vi phạm không?'
        _,decisions,_=auditor._deterministic([item],uncertain,['DISCIPLINE'],{},'ASSESS_LEGALITY')
        self.assertNotEqual(decisions[0].audit_status,'PASS')

    def test_composition_outage_can_only_publish_independently_reviewed_original(self):
        from .test_semantic_answer_review import sample
        from vn_labor_online.generation import LegalAdjudicator
        from vn_labor_online.config import AdjudicationConfig
        pack,draft,verdict=sample()
        engine=LegalAdjudicator(AdjudicationConfig(mode='ollama',semantic_repair_attempts=0))
        engine._generate_with_layout=Mock(return_value=(draft,[]))
        engine._review_provider=Mock()
        engine._review_provider.structured.return_value=verdict
        outage=LLMProviderError('private-details',safe_code='GEMINI_HTTP_503')
        with patch('vn_labor_online.answer_review.compose_answer',side_effect=outage):
            result,_=engine.generate(pack,False)
        self.assertEqual(result.semantic_review['status'],'PASS')
        self.assertEqual(result.claims,draft.claims)
        engine._review_provider.structured.assert_called_once()
        engine._review_provider.structured.side_effect=LLMProviderError('private-details',safe_code='GEMINI_HTTP_503')
        with patch('vn_labor_online.answer_review.compose_answer',side_effect=outage):
            result,_=engine.generate(pack,False)
        self.assertFalse(result.claims)
        self.assertEqual(result.semantic_review['status'],'ERROR')

    def test_period_scoping_preserves_substantive_conditional_task(self):
        request=QueryRequest(question=('Từ 20/12/2020 đến 10/01/2021, thời gian thử việc tối đa '
            'cho công việc yêu cầu cao đẳng là bao lâu? Nếu công việc yêu cầu trình độ khác nhau '
            'thì có cùng giới hạn thử việc không?'))
        store=SimpleNamespace(units=[{'valid_from':'2021-01-01'}])
        periods=rule_periods(request,store)
        self.assertEqual(len(periods),2)
        for period in periods:self.assertIn('trình độ khác nhau',period.question)

    def test_model_observation_is_not_an_extra_provider_failure(self):
        class CountingFailure:
            model='fixture'
            def count_prompt_tokens(self,*_):raise ValueError('private-tokenizer-data')
            @observe_model
            def structured(self,*_):return {'ok':True}
        self.assertEqual(CountingFailure().structured('system','user',{}),{'ok':True})

    def test_timeout_event_retains_safe_budget_metadata(self):
        class TimedFailure:
            model='fixture'
            timeout=0.25
            @observe_model
            def structured(self,*_):raise LLMProviderError('private-provider-data',safe_code='OLLAMA_TIMEOUT')
        with request_budget(10):
            from vn_labor_online.demo_progress import execution_snapshot
            with self.assertRaises(LLMProviderError):TimedFailure().structured('private prompt','private query',{})
            event=execution_snapshot()['steps'][-1]
        self.assertEqual(event['status'],'ERROR')
        self.assertIn('effective_timeout_seconds',event['output'])
        self.assertLessEqual(event['output']['effective_timeout_seconds'],0.25)
        self.assertNotIn('private',str(event))


if __name__=='__main__':unittest.main()
