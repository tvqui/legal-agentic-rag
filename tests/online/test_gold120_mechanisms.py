"""Behavioral regressions and unseen wording; no model network calls."""
import json,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from vn_labor_online.analysis import analyze,intake
from vn_labor_online.taxonomy import probation_duration_clauses
from vn_labor_online.answer_review import reviewer_call,accounting_schema,Review
from tests.online.test_semantic_answer_review import sample

class FactAndTaskRegressions(unittest.TestCase):
    def analysis(self,q):return analyze(intake(q,[],'2026-09-15',{}),'2026-09-15',{})
    def test_negated_disability_wordings(self):
        for phrase in ['không phải người khuyết tật','không bị khuyết tật','không là người khuyết tật','chẳng phải người khuyết tật']:
            with self.subTest(phrase=phrase):
                a=self.analysis('Tôi 32 tuổi, '+phrase+', làm việc đủ 12 tháng trong điều kiện bình thường. Tôi được bao nhiêu ngày phép năm?')
                self.assertIs(a.facts.get('disabled'),False)
    def test_affirmed_disability_and_question_not_fact(self):
        self.assertIs(self.analysis('Tôi là người khuyết tật, làm đủ 12 tháng. Tôi có bao nhiêu ngày phép?').facts.get('disabled'),True)
        self.assertNotEqual(self.analysis('Tôi có phải là người khuyết tật không?').facts.get('disabled'),True)
    def test_negated_manager_does_not_expand_job_scope(self):
        for words in ['không phải người quản lý doanh nghiệp','không là người quản lý doanh nghiệp']:
            q='Tôi làm vị trí chuyên môn yêu cầu cao đẳng, '+words+'. Công ty thử việc tôi 75 ngày và trả 79% lương công việc. Đánh giá riêng thời gian và lương.'
            a=self.analysis(q)
            self.assertEqual(a.facts.get('probation_work_group'),'COLLEGE')
            self.assertEqual(probation_duration_clauses(a,False),(2,))
    def test_overview_still_keeps_all_groups(self):
        a=self.analysis('So sánh các nhóm thời gian thử việc của quản lý doanh nghiệp, cao đẳng và trung cấp.')
        self.assertEqual(probation_duration_clauses(a,False),(1,2,3,4))
    def test_employer_notice_rule_does_not_require_already_given_notice(self):
        a=self.analysis('Nhân viên ký hợp đồng 30 tháng, không làm công việc đặc thù, không thuộc trường hợp được bảo vệ tại Điều 37, thường xuyên không hoàn thành công việc theo tiêu chí đánh giá hợp lệ. Công ty có quyền đơn phương chấm dứt và phải báo trước bao lâu?')
        self.assertFalse(any('đã báo trước' in q or 'Lý do' in q or 'mang thai' in q for q in a.missing_facts),a.missing_facts)
    def test_no_notice_employer_ground_does_not_need_contract_term(self):
        a=self.analysis('Người lao động không thuộc các trường hợp bảo vệ tại Điều 37, tự ý bỏ việc không có lý do chính đáng đủ 5 ngày làm việc liên tục. Nếu công ty chấm dứt theo điểm e khoản 1 Điều 36 thì có phải báo trước không?')
        self.assertFalse(any('đã báo trước' in q or 'Loại hợp đồng' in q or 'mang thai' in q for q in a.missing_facts),a.missing_facts)
    def test_uncertain_disability_is_not_an_affirmative_fact(self):
        for wording in ['Tôi chưa biết mình có phải người khuyết tật không.', 'Tôi chưa được xác nhận là người khuyết tật.']:
            a=self.analysis(wording+' Nghỉ phép năm tính thế nào?')
            self.assertNotEqual(a.facts.get('disabled'),True)
    def test_negative_fact_quote_contains_its_negation(self):
        a=self.analysis('Tôi không phải người khuyết tật, làm đủ 12 tháng trong điều kiện bình thường. Tôi nghỉ phép bao nhiêu ngày?')
        candidate=next(c for c in a.fact_candidates if c.field=='disabled')
        self.assertIs(candidate.value,False)
        self.assertIn('không',candidate.source_quote)
    def test_protection_conflict_does_not_assert_unprotected(self):
        a=self.analysis('Tôi đang mang thai, nhưng công ty nói tôi không thuộc trường hợp bảo vệ tại Điều 37. Công ty có quyền đơn phương chấm dứt không?')
        self.assertNotEqual(a.facts.get('protected_status'),'NONE')
    def test_question_about_pregnancy_is_not_confirmed_pregnancy(self):
        a=self.analysis('Người lao động có đang mang thai không?')
        self.assertNotEqual(a.facts.get('protected_status'),'MATERNITY')
    def test_weekly_overlap_does_not_require_unasked_holiday_list(self):
        from vn_labor_online.analysis import plan_evidence
        a=self.analysis('Ngày nghỉ hằng tuần trùng ngày lễ, người lao động có được nghỉ bù không?')
        plan=plan_evidence(a)
        self.assertIn('weekly_rest',plan.slot_requirements)
        self.assertNotIn('public_holiday_rule',plan.slot_requirements)
    def test_named_holiday_uses_its_branch_and_date_authority(self):
        from vn_labor_online.analysis import plan_evidence
        a=self.analysis('Quốc khánh được nghỉ mấy ngày và ai quyết định ngày liền kề?')
        plan=plan_evidence(a)
        points={loc.point for group in plan.slot_requirements['public_holiday_rule'] for loc in group}
        self.assertEqual(points,{'đ'})
        self.assertIn('holiday_date_authority',plan.slot_requirements)
    def test_negated_overtime_is_not_a_second_wage_task(self):
        a=self.analysis('Tôi làm việc ban đêm nhưng không làm thêm giờ. Khoản trả thêm tối thiểu là bao nhiêu?')
        self.assertNotIn('WAGE.OVERTIME_PAY',a.legal_subissues)
        self.assertIn('WAGE.NIGHT_PAY',a.legal_subissues)

class RealSourceApplicationTests(unittest.TestCase):
    def test_trial_time_and_pay_get_separate_conclusions(self):
        from vn_labor_online.models import VerifiedEvidenceItem,VerifiedEvidencePack,EvidenceState
        from vn_labor_online.profile_generation import render_profile
        raw=json.loads((Path(__file__).parent/'fixtures/gold120_source_excerpts.json').read_text(encoding='utf-8'))
        items=[VerifiedEvidenceItem(evidence_id=u['unit_id'],instrument_number=u['document_number'],
            article=u['article_number'],clause=u['clause_number'],point=u['point_number'],
            text=u['source_text'],full_text=u['source_text'],ancestor_context=u['ancestor_context'] or '') for u in raw]
        for days in (70,83,90):
            query=f'Tôi làm vị trí chuyên môn yêu cầu cao đẳng, không phải người quản lý doanh nghiệp; công ty yêu cầu thử việc {days} ngày và trả 80% lương của công việc. Đánh giá riêng thời gian và tiền lương.'
            a=analyze(intake(query,[],'2026-09-15',{}),'2026-09-15',{})
            pack=VerifiedEvidencePack(query=query,query_date='2026-09-15',facts=a.facts,
                evidence=items,coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
            draft=render_profile(pack,False,[])
            self.assertIsNotNone(draft)
            text=' '.join(c.text for c in draft.claims)
            self.assertIn(f'{days} ngày vượt mức tối đa 60 ngày',text)
            self.assertIn('80% thấp hơn tối thiểu 85%',text)
    def test_synonym_relevance_does_not_require_verbatim_wording(self):
        from vn_labor_online.audit import _claim_supported
        from vn_labor_online.models import Evidence
        raw=json.loads((Path(__file__).parent/'fixtures/gold120_source_excerpts.json').read_text(encoding='utf-8'))
        unit=next(u for u in raw if u['article_number']=='94')
        e=Evidence(unit_id=unit['unit_id'],retrieval_method='test',text=unit['source_text'])
        self.assertTrue(_claim_supported('Công ty không được ép nhân viên dùng lương mua sản phẩm do chính công ty bán.',e))

class AuditorPayloadTests(unittest.TestCase):
    def test_shared_facts_once_and_hypothesis_is_not_confirmed(self):
        from vn_labor_online.applicability import LegalApplicabilityAuditor
        from vn_labor_online.config import ApplicabilityConfig
        from vn_labor_online.models import Evidence,ApplicabilityDecision
        provider=Mock();provider.context_tokens=None;provider.max_output_tokens=500
        def structured(system,user,schema):
            payload=json.loads(user)
            self.assertIn('user_statements',payload)
            self.assertTrue(any(s['kind']=='HYPOTHESIS' for s in payload['user_statements']))
            self.assertTrue(all(set(c)=={'evidence'} for c in payload['candidates']))
            return {'decisions':{c['evidence']['id']:{'relevant':True,'supports_claim':True,
                'conditions_status':'UNKNOWN','exception_status':'UNKNOWN'} for c in payload['candidates']}}
        provider.structured.side_effect=structured
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid'))
        auditor.provider=provider
        items=[Evidence(unit_id='s',retrieval_method='bm25',text='Quy định pháp luật cần kiểm tra.')]
        auditor._deterministic=Mock(return_value=([],[ApplicabilityDecision(evidence_id='s',relevant=True,supports_claim=False,audit_status='UNRESOLVED')],[]))
        accepted,decisions,_=auditor.audit(items,'Giả sử công ty áp dụng biện pháp này. Có hợp pháp không?',['GENERAL'],{},'ASSESS_LEGALITY')
        self.assertFalse(accepted)
        self.assertEqual(decisions[0].audit_status,'UNRESOLVED')

class SecondOpinionSafetyTests(unittest.TestCase):
    def test_pipeline_reuses_configured_gemini_model(self):
        from types import SimpleNamespace
        from vn_labor_online.config import ApplicabilityConfig,ResearcherConfig,AdjudicationConfig
        from vn_labor_online.pipeline import OnlinePipeline
        cfg=SimpleNamespace(applicability=ApplicabilityConfig(unresolved_provider='gemini'),
            researcher=ResearcherConfig(mode='gemini',model='configured-gemini'),adjudication=AdjudicationConfig(),graph=None)
        with patch('vn_labor_online.pipeline.ArtifactStore'),patch('vn_labor_online.pipeline.Retriever'),patch('vn_labor_online.pipeline.GraphExplorer'),patch('vn_labor_online.pipeline.LegalResearcher'),patch('vn_labor_online.pipeline.LegalAdjudicator'),patch('vn_labor_online.pipeline.LegalApplicabilityAuditor') as auditor:
            OnlinePipeline(cfg)
        self.assertEqual(auditor.call_args.args[0].unresolved_model,'configured-gemini')
    def setup_auditor(self,hard=False):
        from vn_labor_online.applicability import LegalApplicabilityAuditor
        from vn_labor_online.config import ApplicabilityConfig
        from vn_labor_online.models import Evidence,ApplicabilityDecision
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid',unresolved_provider='gemini',max_items=4,max_batches=1))
        auditor.provider=Mock();auditor.provider.context_tokens=None;auditor.provider.max_output_tokens=500
        auditor.provider.structured.return_value={'decisions':{'s':{'relevant':True,'supports_claim':True,'conditions_status':'UNKNOWN','exception_status':'UNKNOWN'}}}
        item=Evidence(unit_id='s',retrieval_method='bm25',text='Nguồn quy định về quyền của người lao động.')
        auditor._deterministic=Mock(return_value=([],[ApplicabilityDecision(evidence_id='s',relevant=True,
            supports_claim=False,audit_status='FAIL' if hard else 'UNRESOLVED')],[]))
        return auditor,item
    def run_second(self,value,hard=False):
        auditor,item=self.setup_auditor(hard)
        with patch.dict('os.environ',{'GEMINI_API_KEY':'fixture-only','GEMINI_MODEL':'fixture-model'}),patch(
            'vn_labor_online.applicability.GeminiProvider.structured',return_value=value) as provider:
            result=auditor.audit([item],'Công ty áp dụng biện pháp này. Có hợp pháp không?',['GENERAL'],{},'ASSESS_LEGALITY')
            return result,provider.call_count
    def test_unknown_requires_an_independent_resolved_verdict(self):
        (accepted,decisions,warnings),calls=self.run_second({'decisions':{'s':{'relevant':True,'supports_claim':True,'conditions_status':'NOT_APPLICABLE','exception_status':'NOT_APPLICABLE'}}})
        self.assertEqual([x.unit_id for x in accepted],['s']);self.assertEqual(calls,1)
        self.assertIn('SECOND_OPINION_APPLICABILITY_PASS',decisions[0].reasons)
    def test_unknown_stays_unknown_if_second_model_is_also_uncertain(self):
        (accepted,decisions,_),calls=self.run_second({'decisions':{'s':{'relevant':True,'supports_claim':True,'conditions_status':'UNKNOWN','exception_status':'NOT_APPLICABLE'}}})
        self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'UNRESOLVED');self.assertEqual(calls,1)
    def test_hard_exclusion_never_reaches_second_model(self):
        (accepted,decisions,_),calls=self.run_second({},hard=True)
        self.assertFalse(accepted);self.assertEqual(calls,0);self.assertEqual(decisions[0].audit_status,'FAIL')
    def test_foreign_id_never_replaces_original_evidence(self):
        (accepted,decisions,warnings),calls=self.run_second({'decisions':{'foreign':{'relevant':True,'supports_claim':True,'conditions_status':'SATISFIED','exception_status':'NOT_APPLICABLE'}}})
        self.assertFalse(accepted);self.assertEqual(calls,1);self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
        self.assertTrue(any(w.startswith('APPLICABILITY_SECOND_OPINION_ERROR') for w in warnings))
    def test_exhausted_budget_is_not_extended_for_second_opinion(self):
        from vn_labor_online.runtime import request_budget
        auditor,item=self.setup_auditor()
        with request_budget(1),patch('vn_labor_online.applicability.GeminiProvider') as provider:
            accepted,decisions,warnings=auditor.audit([item],'Câu hỏi về điều kiện áp dụng.',['GENERAL'],{},'ASSESS_LEGALITY')
        self.assertFalse(accepted);provider.assert_not_called()
        self.assertIn('APPLICABILITY_SECOND_OPINION_BUDGET_RESERVED',warnings)
    def test_disqualifying_condition_still_fails(self):
        (accepted,decisions,_),calls=self.run_second({'decisions':{'s':{'relevant':True,'supports_claim':True,'conditions_status':'NOT_SATISFIED','exception_status':'NOT_APPLICABLE'}}})
        self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'FAIL');self.assertEqual(calls,1)
    def test_second_provider_failure_keeps_original_unresolved_result(self):
        auditor,item=self.setup_auditor()
        with patch.dict('os.environ',{'GEMINI_API_KEY':'fixture-only','GEMINI_MODEL':'fixture-model'}),patch(
            'vn_labor_online.applicability.GeminiProvider.structured',side_effect=TimeoutError()):
            accepted,decisions,warnings=auditor.audit([item],'Câu hỏi kiểm tra áp dụng.',['GENERAL'],{},'ASSESS_LEGALITY')
        self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
        self.assertIn('APPLICABILITY_SECOND_OPINION_ERROR:TimeoutError',warnings)

class NormEffectSafetyTests(unittest.TestCase):
    def test_form_rule_does_not_prove_invalidity(self):
        from vn_labor_online.claim_validation import semantic_issues
        from vn_labor_online.models import Evidence
        source=Evidence(unit_id='source',retrieval_method='test',text='Hợp đồng phải được giao kết bằng văn bản, trừ trường hợp hợp đồng dưới một tháng.')
        self.assertIn('CLAIM_FORM_VIOLATION_AS_INVALIDITY',semantic_issues('Hợp đồng miệng sáu tháng không có giá trị pháp lý.',[source]))
        self.assertNotIn('CLAIM_FORM_VIOLATION_AS_INVALIDITY',semantic_issues('Không đúng hình thức bằng văn bản.',[source]))
        self.assertNotIn('CLAIM_FORM_VIOLATION_AS_INVALIDITY',semantic_issues('Việc sai hình thức không đồng nghĩa hợp đồng vô hiệu.',[source]))

class GroundingContractRegressions(unittest.TestCase):
    def test_keyed_grounding_includes_every_attached_source(self):
        pack,draft,legacy=sample();provider=Mock()
        def response(system,user,schema):
            entry=schema['properties']['claims']['properties']['claim']['properties']['grounding']
            self.assertEqual(entry['required'],['source'])
            self.assertIn('source_spans',json.loads(user)['evidence'][0])
            return {'claims':{'claim':{'verdict':'SUPPORTED','grounding':{'source':'span_000'},'reason':'matches'}},
                'coverage':{'entitlement':{'status':'ANSWERED','claim_ids':['claim'],'missing':''}},
                'question_fully_addressed':True,'missing_requirements':[]}
        provider.structured.side_effect=response
        payload={'claims':[c.model_dump() for c in draft.claims],'required_claim_ids':['claim'],'required_task_ids':['entitlement'],
            'evidence':[{'evidence_id':'source','full_text':pack.evidence[0].text}]}
        raw=reviewer_call(provider,'review',payload,accounting_schema(Review,['claim'],['entitlement']))
        from vn_labor_online.answer_review import validate_review
        self.assertEqual(validate_review(Review.model_validate(raw),draft,pack,pack.answer_tasks),{'claim'})
    def test_unsupported_does_not_invent_grounding(self):
        pack,draft,_=sample();provider=Mock()
        provider.structured.return_value={'claims':{'claim':{'verdict':'UNSUPPORTED','grounding':{'source':''},'reason':'not supported'}},
            'coverage':{'entitlement':{'status':'MISSING','claim_ids':[],'missing':'No proved conclusion'}},
            'question_fully_addressed':False,'missing_requirements':['No proved conclusion']}
        payload={'claims':[c.model_dump() for c in draft.claims],'required_claim_ids':['claim'],'required_task_ids':['entitlement']}
        raw=reviewer_call(provider,'review',payload,accounting_schema(Review,['claim'],['entitlement']))
        self.assertEqual(raw['claims'][0]['grounding'],[])

class SourceSpanSafetyTests(unittest.TestCase):
    def test_all_norm_text_remains_available_and_each_span_is_exact(self):
        from vn_labor_online.grounding_spans import source_spans
        original='Điều 999. Quy định\n1. Không được thực hiện hành vi A;\ntrừ trường hợp B.\n2. Phải thực hiện nghĩa vụ C.'
        spans=source_spans(original)
        self.assertTrue(spans)
        for value in spans.values():self.assertIn(value,original)
        self.assertEqual(''.join(''.join(spans.values()).split()),''.join(original.split()))
    def test_long_source_keeps_both_first_and_last_qualifications(self):
        from vn_labor_online.grounding_spans import source_spans
        original='\n'.join(f'Điều kiện {i}: không được bỏ ngoại lệ này.' for i in range(150))
        spans=source_spans(original)
        self.assertLessEqual(len(spans),48)
        self.assertEqual(''.join(''.join(spans.values()).split()),''.join(original.split()))

if __name__=='__main__':unittest.main()
