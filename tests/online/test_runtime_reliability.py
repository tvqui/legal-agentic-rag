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
