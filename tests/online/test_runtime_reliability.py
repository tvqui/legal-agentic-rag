import unittest
from unittest.mock import Mock,patch
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.answer_review import review_error_code
from vn_labor_online.config import AdjudicationConfig
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.generation import LegalAdjudicator,literal_lookup_draft
from vn_labor_online.models import EvidenceState,ExplicitReference,VerifiedEvidenceItem,VerifiedEvidencePack

def lookup():
    text='Điều 9. Nội dung nguồn gồm các quy định về quyền và nghĩa vụ của các bên.'
    evidence=VerifiedEvidenceItem(evidence_id='source',instrument_number='99/2024/NĐ-CP',article='9',
      text=text,full_text=text,official_source=True,official_url='https://vbpl.vn/official',
      provenance_span={'char_start':0,'char_end':len(text)},valid_from='2024-01-01')
    return VerifiedEvidencePack(query='Điều 9 Nghị định 99/2024/NĐ-CP quy định gì?',requested_outcome='LOOKUP',
      coverage_state=EvidenceState(slots={},gaps=['applicable_version'],coverage=.5),evidence=[evidence],
      lookup_reference=ExplicitReference(instrument_number='99/2024/NĐ-CP',article='9'))

class LiteralSourceTests(unittest.TestCase):
    def test_literal_lookup_is_source_copy_not_a_model_completion(self):
        pack=lookup(); engine=LegalAdjudicator(AdjudicationConfig(mode='ollama'))
        engine.provider=Mock()
        draft,warnings=engine.generate(pack,True)
        engine.provider.structured.assert_not_called()
        self.assertEqual(draft.claims[0].text,pack.evidence[0].full_text)
        self.assertEqual(draft.claims[0].evidence_ids,['source'])
        self.assertEqual(draft.semantic_review['status'],'LITERAL_SOURCE_MATCH')
        self.assertIn('LITERAL_SOURCE_QUOTATION',warnings)
        self.assertIn('applicable_version',draft.limitations)

    def test_quote_does_not_silently_change_document_article_or_scope(self):
        for update in ({'instrument_number':'1/2024/NĐ-CP'},{'article':'10'},{'clause':'2'}):
            pack=lookup(); pack.lookup_reference=pack.lookup_reference.model_copy(update=update)
            with self.subTest(update=update): self.assertIsNone(literal_lookup_draft(pack,True))

    def test_no_quote_shortcut_without_pipeline_marker_or_source_proof(self):
        pack=lookup(); pack.lookup_reference=None
        self.assertIsNone(literal_lookup_draft(pack,True))
        for update in ({'official_source':False},{'official_url':None},{'provenance_span':{}},
          {'full_text':''},{'full_text':'----'},{'audit_status':'FAIL'}):
            pack=lookup(); pack.evidence[0]=pack.evidence[0].model_copy(update=update)
            with self.subTest(update=update): self.assertIsNone(literal_lookup_draft(pack,True))

    def test_interpretation_and_case_assessment_cannot_use_quote_shortcut(self):
        for update in ({'requested_outcome':'ASSESS_LEGALITY'},{'facts':{'actor':'EMPLOYEE'}},
          {'query':'Điều 9 quy định gì và tôi có được bồi thường không?'}):
            pack=lookup().model_copy(update=update)
            with self.subTest(update=update): self.assertIsNone(literal_lookup_draft(pack,True))

    def test_unreviewed_traceable_source_remains_partial_not_authority_pass(self):
        pack=lookup()
        pack.evidence[0]=pack.evidence[0].model_copy(update={'official_source':False,'authority_rank':100,'binding':True})
        pack.coverage_state=pack.coverage_state.model_copy(update={'gaps':['official_source','applicable_version']})
        draft=literal_lookup_draft(pack,True)
        self.assertIsNotNone(draft)
        self.assertFalse(draft.semantic_review['source_authority_approved'])
        self.assertIn('official_source',draft.limitations)
        self.assertIsNone(literal_lookup_draft(pack,False))

    def test_semantic_error_codes_are_actionable_without_credentials(self):
        self.assertEqual(review_error_code(StructuredOutputError('OUTPUT_TOKEN_LIMIT')),'OUTPUT_TOKEN_LIMIT')
        self.assertEqual(review_error_code(StructuredOutputError('semantic review must judge each claim exactly once')),'CLAIM_ACCOUNTING_MISMATCH')
        self.assertEqual(review_error_code(StructuredOutputError('secret unknown data')),'REVIEW_STRUCTURED_OUTPUT_INVALID')


class InterpretationTests(unittest.TestCase):
    def test_under_one_year_routes_to_proportion_without_inventing_month_count(self):
        for duration in ('chưa đủ một năm','dưới 1 năm','chưa đủ mười hai tháng'):
            analysis=analyze(intake('Tôi làm cho công ty '+duration+'. Nghỉ phép năm được bao nhiêu ngày?',[]))
            with self.subTest(duration=duration):
                self.assertIn('LEAVE.PRO_RATA_LEAVE',analysis.legal_subissues)
                self.assertIn('leave_calculation_rule',plan_evidence(analysis).slot_requirements)
                self.assertNotIn('worked_months',analysis.facts)

    def test_pro_rata_formula_retains_annual_rate_without_certifying_full_year(self):
        from vn_labor_online.applicability import LegalApplicabilityAuditor
        from vn_labor_online.config import ApplicabilityConfig
        from vn_labor_online.models import Evidence
        from vn_labor_online.evidence import state_for
        query='Tôi làm công việc nặng nhọc, độc hại, nguy hiểm được 7 tháng, tính nghỉ phép năm như thế nào?'
        analysis=analyze(intake(query,[]))
        base=Evidence(unit_id='base',retrieval_method='policy',verified=True,kind='PROVISION',
          document_number='18/VBHN-VPQH',article_number='113',clause_number='1',point_number='b',
          text='Người lao động làm việc đủ 12 tháng được nghỉ 14 ngày làm việc đối với công việc nặng nhọc, độc hại, nguy hiểm.',
          source_text='Người lao động làm việc đủ 12 tháng được nghỉ 14 ngày làm việc đối với công việc nặng nhọc, độc hại, nguy hiểm.')
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid'))
        accepted,decisions,_=auditor.audit([base],query,analysis.legal_issues,analysis.facts,analysis.requested_outcome)
        self.assertEqual([item.unit_id for item in accepted],['base'])
        self.assertEqual(decisions[0].conditions_status,'NOT_APPLICABLE')
        self.assertIn('DETERMINISTIC_PRO_RATA_BASE_PARAMETER',decisions[0].reasons)
        state=state_for(accepted,plan_evidence(analysis),None,True)
        self.assertIn('proportional_leave_rule',state.gaps)
        self.assertIn('leave_calculation_rule',state.gaps)

    def test_case_verdict_waits_for_material_facts_even_when_rule_explanations_are_enabled(self):
        import tempfile
        from pathlib import Path
        from tests.online.test_online_core import fixture
        from vn_labor_online.config import OnlineConfig,RetrievalConfig
        from vn_labor_online.pipeline import OnlinePipeline
        from vn_labor_online.models import QueryRequest
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); build=fixture(root)
            cfg=OnlineConfig(artifact_source=str(root),expected_build_id=build,trace_dir=str(root/'traces'),
              cache_dir=str(root/'cache'),retrieval=RetrievalConfig(dense_enabled=False),answer_while_clarifying=True)
            pipe=OnlinePipeline(cfg)
            try:
                pipe.adjudicator.generate=Mock(side_effect=AssertionError('Cannot generate a verdict before material facts'))
                result=pipe.ask(QueryRequest(question='Tôi ký hợp đồng không xác định thời hạn, chỉ báo trước 18 ngày rồi nghỉ. Việc nghỉ có trái pháp luật không?'))
                self.assertEqual(result.status,'NEED_MORE_FACTS')
                self.assertTrue(result.questions)
                self.assertFalse(result.claims)
                pipe.adjudicator.generate.assert_not_called()
            finally: pipe.close()

    def test_negated_agreement_cannot_replace_unilateral_termination_chain(self):
        base='Tôi ký hợp đồng lao động không xác định thời hạn, nghỉ ngày 30/09/2026 và chỉ báo trước 20 ngày. Tôi không làm công việc đặc thù, không thuộc trường hợp được nghỉ không cần báo trước. '
        for wording in ('Công ty chưa đồng ý cho nghỉ sớm.',
          'Hai bên không có thỏa thuận chấm dứt hợp đồng.',
          'Hai bên chưa thỏa thuận chấm dứt hợp đồng.'):
            with self.subTest(wording=wording):
                a=analyze(intake(base+wording+' Việc nghỉ như vậy có đúng quy định không và hậu quả là gì?',[]))
                self.assertNotIn('TERMINATION.MUTUAL_AGREEMENT',a.legal_subissues)
                self.assertIn('TERMINATION.EMPLOYEE_UNILATERAL',a.legal_subissues)
                self.assertIn('TERMINATION.EMPLOYEE_LIABILITY',a.legal_subissues)
                self.assertNotIn('agreement_rule',plan_evidence(a).slot_requirements)

    def test_affirmative_agreement_is_not_negated_by_contract_type(self):
        a=analyze(intake('Tôi ký hợp đồng không xác định thời hạn. Công ty đồng ý cho nghỉ sớm bằng văn bản. Có đúng quy định không?',[]))
        self.assertTrue(a.facts['mutual_termination_agreement'])
        self.assertIn('TERMINATION.MUTUAL_AGREEMENT',a.legal_subissues)

    def test_relative_conditional_followup_retains_only_user_context(self):
        from vn_labor_online.conversation import resolve_context
        from vn_labor_online.models import QueryRequest
        question='Nếu hết thời gian đó mà công ty yêu cầu tôi thử việc thêm một lần nữa cho chính công việc ấy thì có được không?'
        previous='Tôi thử việc cho công việc yêu cầu trình độ cao đẳng. Công ty yêu cầu thử việc 90 ngày và trả 80% mức lương của công việc đó.'
        result=resolve_context(QueryRequest(question=question,conversation_turns=[{'turn_id':'previous','content':previous}]))
        self.assertEqual(result.used_turns,['previous'])
        self.assertEqual(result.facts['probation_work_group'],'COLLEGE')
        self.assertNotIn('conditions_satisfied',result.facts)

    def test_probation_repeat_paraphrases_do_not_turn_into_duration_overview(self):
        for question in ('Hết thời gian đó, công ty bắt thử việc thêm một lần nữa có được không?',
          'Công ty yêu cầu thử việc thêm một đợt cho cùng công việc, được không?',
          'Tôi phải thử việc lần nữa cho cùng vị trí có đúng không?'):
            with self.subTest(question=question):
                analysis=analyze(intake(question,[]))
                self.assertIn('CONTRACT.PROBATION_REPEAT',analysis.legal_subissues)
                self.assertNotIn('CONTRACT.PROBATION_DURATION',analysis.legal_subissues)
        analysis=analyze(intake('Công ty yêu cầu thử việc lại 40 ngày cho cùng công việc, được không?',[]))
        self.assertIn('CONTRACT.PROBATION_REPEAT',analysis.legal_subissues)
        self.assertIn('CONTRACT.PROBATION_DURATION',analysis.legal_subissues)

    def test_known_job_group_scopes_duration_but_comparisons_retain_all_groups(self):
        question='Công việc yêu cầu trình độ cao đẳng, thử việc 75 ngày và trả 82% mức lương của công việc đó có đúng không?'
        analysis=analyze(intake(question,[]))
        groups=plan_evidence(analysis).slot_requirements['probation_duration']
        self.assertEqual([loc.clause for group in groups for loc in group],['2'])
        analysis=analyze(intake(question+' Hãy so sánh các nhóm công việc.',[]))
        self.assertEqual(len(plan_evidence(analysis).slot_requirements['probation_duration']),4)

    def test_supported_probation_composition_applies_source_limits_without_generation(self):
        question='Công việc yêu cầu trình độ cao đẳng, thử việc 75 ngày và trả 82% mức lương của công việc đó có đúng không?'
        analysis=analyze(intake(question,[]))
        items=[VerifiedEvidenceItem(evidence_id='duration',instrument_number='45/2019/QH14',article='25',clause='2',
          text='Không quá 60 ngày đối với công việc có chức danh nghề nghiệp cần trình độ chuyên môn, kỹ thuật từ cao đẳng trở lên;'),
          VerifiedEvidenceItem(evidence_id='pay',instrument_number='45/2019/QH14',article='26',
          text='Tiền lương thử việc ít nhất phải bằng 85% mức lương của công việc đó.')]
        pack=VerifiedEvidencePack(query=question,facts=analysis.facts,query_date='2026-09-15',
          coverage_state=EvidenceState(slots={},gaps=[],coverage=1),evidence=items)
        engine=LegalAdjudicator(AdjudicationConfig(mode='ollama',semantic_review=False))
        engine.provider=Mock()
        draft,_=engine.generate(pack,True)
        engine.provider.structured.assert_not_called()
        public=' '.join(claim.text for claim in draft.claims)
        self.assertIn('75 ngày vượt mức tối đa 60 ngày',public)
        self.assertIn('82% thấp hơn tối thiểu 85%',public)
        self.assertEqual({eid for c in draft.claims for eid in c.evidence_ids},{'duration','pay'})

    def test_explicit_gemini_reviewer_is_separate_and_default_tracks_generator(self):
        from tests.online.test_semantic_answer_review import sample
        pack,draft,_=sample()
        default=LegalAdjudicator(AdjudicationConfig(mode='ollama'))
        default.provider=Mock()
        self.assertIs(default.review_provider,default.provider)
        reviewer=Mock()
        with patch('vn_labor_online.generation.GeminiProvider',return_value=reviewer):
            engine=LegalAdjudicator(AdjudicationConfig(mode='ollama',review_provider='gemini',review_model='test-gemini'))
        engine.provider=Mock(); engine._generate_with_layout=Mock(return_value=(draft,[]))
        checked=draft.model_copy(update={'semantic_review':{'status':'PASS'}})
        with patch('vn_labor_online.answer_review.review_answer',return_value=(checked,[])) as audit:
            engine.generate(pack,False)
        self.assertIs(audit.call_args.args[0],reviewer)
        self.assertIsNot(engine.review_provider,engine.provider)


class ReviewRecoveryTests(unittest.TestCase):
    def test_invalid_quotation_can_be_rechecked_but_never_accepted_as_is(self):
        import copy
        from tests.online.test_semantic_answer_review import sample
        from vn_labor_online.answer_review import review_answer
        pack,draft,valid=sample()
        invalid=copy.deepcopy(valid)
        invalid['claims'][0]['grounding'][0]['quote']='Nội dung này không có trong nguồn.'
        provider=Mock(); provider.structured.side_effect=[invalid,valid]
        result,_=review_answer(provider,draft,pack,repair_attempts=1)
        self.assertEqual(result.semantic_review['status'],'PASS')
        self.assertEqual(provider.structured.call_count,2)
        self.assertEqual(result.claims,draft.claims)
        self.assertIn('GROUNDING_QUOTE_MISMATCH',provider.structured.call_args.args[1])

    def test_failed_recheck_and_rate_limits_do_not_publish_unverified_claims(self):
        from tests.online.test_semantic_answer_review import sample
        from vn_labor_online.answer_review import review_answer
        from vn_labor_online.errors import LLMProviderError
        pack,draft,valid=sample()
        provider=Mock(); provider.structured.side_effect=LLMProviderError('private message',safe_code='GEMINI_HTTP_429')
        result,_=review_answer(provider,draft,pack)
        self.assertFalse(result.claims)
        self.assertEqual(result.semantic_review['error_code'],'GEMINI_HTTP_429')
        self.assertEqual(provider.structured.call_count,1)
        self.assertNotIn('private message',str(result.semantic_review))

    def test_diagnostic_codes_cannot_publish_arbitrary_provider_messages(self):
        from vn_labor_online.errors import LLMProviderError
        self.assertEqual(review_error_code(LLMProviderError('private',safe_code='GEMINI_HTTP_400')),'GEMINI_HTTP_400')
        self.assertEqual(review_error_code(LLMProviderError('private',safe_code='token-is-secret')),'LLMProviderError')
