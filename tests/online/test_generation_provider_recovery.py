import unittest
from unittest.mock import Mock,patch
from vn_labor_online.config import AdjudicationConfig
from vn_labor_online.errors import LLMProviderError,ProviderRateLimited,StructuredOutputError
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.runtime import RequestBudget,RequestStopped,request_budget,request_timeout,OperationBudgetExceeded
from vn_labor_online.models import EvidenceState,VerifiedEvidenceItem,VerifiedEvidencePack


class GenerationProviderRecoveryTests(unittest.TestCase):
    def engine(self,**kwargs):
        engine=LegalAdjudicator(AdjudicationConfig(mode='ollama',**kwargs))
        engine.provider=Mock()
        engine._review_provider=Mock()
        engine._review_provider.structured.return_value={'claims':[{'text':'Kết luận có căn cứ','evidence_ids':['e']}]}
        return engine

    def test_transient_draft_failure_uses_the_same_payload_and_schema(self):
        engine=self.engine()
        engine.provider.structured.side_effect=LLMProviderError(safe_code='OLLAMA_TIMEOUT')
        raw,warnings=engine._generation_structured('system','payload',{'required':['claims']})
        engine._review_provider.structured.assert_called_once_with('system','payload',{'required':['claims']})
        self.assertTrue(raw['claims'])
        self.assertIn('ADJUDICATION_ALTERNATE_DRAFT_USED',warnings)
        self.assertIn('ADJUDICATION_PRIMARY_UNAVAILABLE:OLLAMA_TIMEOUT',warnings)

    def test_successful_primary_never_makes_an_extra_call(self):
        engine=self.engine();engine.provider.structured.return_value={'claims':[]}
        self.assertEqual(engine._generation_structured('s','u',{}),({'claims':[]},[]))
        engine._review_provider.structured.assert_not_called()

    def test_malformed_primary_output_can_be_redrafted_without_relaxing_the_schema(self):
        engine=self.engine()
        engine.provider.structured.side_effect=StructuredOutputError('Malformed model JSON')
        _,warnings=engine._generation_structured('source-limited system','same sources',{'required':['claims']})
        engine._review_provider.structured.assert_called_once_with('source-limited system','same sources',{'required':['claims']})
        self.assertIn('ADJUDICATION_PRIMARY_INVALID_OUTPUT',warnings)
        self.assertIn('ADJUDICATION_ALTERNATE_DRAFT_USED',warnings)

    def test_bad_configuration_quota_or_cancel_does_not_switch_provider(self):
        for error in (LLMProviderError(safe_code='HTTP_JSON_HTTP_400'),ProviderRateLimited(),RequestStopped('REQUEST_CANCELLED')):
            engine=self.engine();engine.provider.structured.side_effect=error
            with self.assertRaises(type(error)):engine._generation_structured('s','u',{})
            engine._review_provider.structured.assert_not_called()

    def test_recovery_respects_the_reserved_reviewer_window(self):
        engine=self.engine();clock=[0.0];seen=[]
        def failed(*args):
            clock[0]=45
            raise LLMProviderError(safe_code='OLLAMA_TIMEOUT')
        engine.provider.structured.side_effect=failed
        engine._review_provider.structured.side_effect=lambda *args:seen.append(request_timeout(120)) or {'claims':[]}
        with patch('vn_labor_online.runtime.time.monotonic',side_effect=lambda:clock[0]),request_budget(110,existing=RequestBudget(110,started=0)):
            engine._generation_structured('s','u',{})
        self.assertEqual(seen,[20])

    def test_no_room_for_recovery_leaves_the_reviewer_time_untouched(self):
        engine=self.engine();clock=[140.0]
        with patch('vn_labor_online.runtime.time.monotonic',side_effect=lambda:clock[0]),request_budget(180,existing=RequestBudget(180,started=0)):
            with self.assertRaises(OperationBudgetExceeded):engine._generation_structured('s','u',{})
        engine.provider.structured.assert_not_called()
        engine._review_provider.structured.assert_not_called()

    def test_ablation_and_disabled_recovery_do_not_add_a_hidden_provider(self):
        for settings in ({'semantic_review':False},{'recovery_budget_seconds':0}):
            engine=self.engine(**settings)
            engine.provider.structured.side_effect=LLMProviderError(safe_code='OLLAMA_HTTP_503')
            with self.assertRaises(LLMProviderError):engine._generation_structured('s','u',{})
            engine._review_provider.structured.assert_not_called()

    def test_quota_failure_is_not_swallowed_by_the_outer_generation_fallback(self):
        engine=self.engine()
        engine.provider.structured.side_effect=ProviderRateLimited()
        pack=VerifiedEvidencePack(query='Giải thích quy định bàn giao hồ sơ.',
            evidence=[VerifiedEvidenceItem(evidence_id='e',text='Bên giao hồ sơ phải lập danh mục tài liệu bàn giao.')],
            coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
        with self.assertRaises(ProviderRateLimited):engine.generate(pack,False)
        engine._review_provider.structured.assert_not_called()

    def test_recovered_draft_is_independently_reviewed_before_publication(self):
        for supported,malformed in ((True,False),(False,False),(True,True),(False,True)):
            engine=self.engine(semantic_repair_attempts=0)
            engine.provider.structured.side_effect=(StructuredOutputError('Malformed JSON') if malformed
                else LLMProviderError(safe_code='OLLAMA_TIMEOUT'))
            source='Bên giao hồ sơ phải lập danh mục tài liệu bàn giao.'
            pack=VerifiedEvidencePack(query='Giải thích quy định bàn giao hồ sơ.',
                evidence=[VerifiedEvidenceItem(evidence_id='e',text=source,full_text=source)],
                coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
            draft={'claims':[{'text':source,'evidence_ids':['e']}]}
            review={'claims':[{'claim_id':'claim_001','verdict':'SUPPORTED' if supported else 'UNSUPPORTED',
                'grounding':[{'evidence_id':'e','quote':source}] if supported else [],'reason':'Đối chiếu nguồn'}],
                'coverage':[{'task_id':'question','status':'ANSWERED' if supported else 'MISSING',
                    'claim_ids':['claim_001'] if supported else [],'missing':'' if supported else 'Chưa xác minh nội dung'}],
                'question_fully_addressed':supported,'missing_requirements':[] if supported else ['Chưa xác minh nội dung']}
            engine._review_provider.structured.side_effect=[draft,review]
            result,warnings=engine.generate(pack,False)
            self.assertEqual(engine._review_provider.structured.call_count,2)
            self.assertEqual(bool(result.claims),supported)
            self.assertIn('ADJUDICATION_ALTERNATE_DRAFT_USED',warnings)


if __name__=='__main__':unittest.main()
