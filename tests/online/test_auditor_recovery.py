"""Recover unassessed candidates without turning infrastructure errors into proof."""
import json,unittest
from unittest.mock import Mock,patch
import httpx
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig
from vn_labor_online.errors import LLMProviderError,StructuredOutputError
from vn_labor_online.gemini_quota import GeminiRatePolicy
from vn_labor_online.models import Evidence,ApplicabilityDecision,EvidencePlan,LegalLocator
from vn_labor_online.providers import OllamaProvider,HttpJsonProvider
from vn_labor_online.runtime import request_budget,request_timeout,OperationBudgetExceeded,RequestStopped
from vn_labor_online.demo_progress import public_error

def source(uid='synthetic_a',article='701'):
 return Evidence(unit_id=uid,text='Quy định thử nghiệm: bên giao việc phải lập biên bản.',
  document_number='TEST/2099',article_number=article,retrieval_method='bm25',verified=True)

def judgment(relevant=True,conditions='NOT_APPLICABLE'):
 return {'relevant':relevant,'supports_claim':relevant,'conditions_status':conditions,
  'exception_status':'NOT_APPLICABLE'}

class AuditorRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict('os.environ',{'GEMINI_MODEL':'synthetic-unit-model','GEMINI_API_KEY':'FAKE_TEST_ONLY'})
  self.env.start();self.addCleanup(self.env.stop)
 def auditor(self,**kw):
  cfg=ApplicabilityConfig(mode='hybrid',unresolved_provider='gemini',max_items=1,max_batches=4,**kw)
  a=LegalApplicabilityAuditor(cfg);a.provider=Mock()
  a._deterministic=Mock(return_value=([],[],[]))
  return a
 def secondary(self,data):
  p=Mock();p.rate_policy=GeminiRatePolicy();p.structured.return_value=data
  return p
 def test_transport_failure_is_independently_reassessed(self):
  a=self.auditor();a.provider.structured.side_effect=LLMProviderError(safe_code='OLLAMA_TIMEOUT')
  p=self.secondary({'decisions':{'synthetic_a':judgment()}})
  with patch('vn_labor_online.applicability.GeminiProvider',return_value=p):
   accepted,decisions,warnings=a.audit([source()],'Giải thích nghĩa vụ lập biên bản.',['GENERAL'],{})
  self.assertEqual([e.unit_id for e in accepted],['synthetic_a'])
  self.assertIn('SECOND_OPINION_APPLICABILITY_PASS',decisions[0].reasons)
  self.assertIn('APPLICABILITY_PROVIDER_ERROR:OLLAMA_TIMEOUT',warnings)
  self.assertIn('APPLICABILITY_SECOND_OPINION_USED',warnings)
  self.assertNotIn('APPLICABILITY_UNRESOLVED:synthetic_a',warnings)
 def test_failed_transport_is_not_repeated_for_every_batch(self):
  a=self.auditor();a.provider.structured.side_effect=LLMProviderError(safe_code='OLLAMA_CONNECTION_ERROR')
  p=self.secondary({'decisions':{e.unit_id:judgment() for e in [source('a'),source('b')]}})
  with patch('vn_labor_online.applicability.GeminiProvider',return_value=p):
   accepted,_,_=a.audit([source('a'),source('b')],'Giải thích nghĩa vụ.',['GENERAL'],{})
  self.assertEqual(a.provider.structured.call_count,1)
  self.assertEqual({e.unit_id for e in accepted},{'a','b'})
 def test_secondary_failure_never_approves_evidence(self):
  a=self.auditor();a.provider.structured.side_effect=LLMProviderError(safe_code='OLLAMA_TIMEOUT')
  p=self.secondary({});p.structured.side_effect=LLMProviderError(safe_code='GEMINI_HTTP_503')
  with patch('vn_labor_online.applicability.GeminiProvider',return_value=p):
   accepted,decisions,warnings=a.audit([source()],'Giải thích nghĩa vụ.',['GENERAL'],{})
  self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
  self.assertTrue(any(w.startswith('APPLICABILITY_SECOND_OPINION_ERROR') for w in warnings))
 def test_secondary_missing_candidate_id_is_rejected(self):
  a=self.auditor();a.provider.structured.side_effect=LLMProviderError(safe_code='OLLAMA_TIMEOUT')
  with patch('vn_labor_online.applicability.GeminiProvider',return_value=self.secondary({'decisions':{}})):
   accepted,decisions,_=a.audit([source()],'Giải thích nghĩa vụ.',['GENERAL'],{})
  self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
 def test_unknown_prerequisite_in_secondary_still_blocks_case_conclusion(self):
  a=self.auditor();a.provider.structured.side_effect=LLMProviderError(safe_code='OLLAMA_TIMEOUT')
  with patch('vn_labor_online.applicability.GeminiProvider',return_value=self.secondary({'decisions':{'synthetic_a':judgment(conditions='UNKNOWN')}})):
   accepted,decisions,_=a.audit([source()],'Trường hợp của tôi có đúng không?',['GENERAL'],{},'ASSESS_LEGALITY')
  self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
 def test_explicit_model_failure_is_not_overridden(self):
  a=self.auditor();a.provider.structured.return_value={'decisions':{'synthetic_a':judgment(False)}}
  with patch('vn_labor_online.applicability.GeminiProvider') as factory:
   accepted,decisions,_=a.audit([source()],'Giải thích nghĩa vụ.',['GENERAL'],{})
  self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'FAIL');factory.assert_not_called()
 def test_hard_failure_never_reaches_any_provider(self):
  a=self.auditor();a._deterministic.return_value=([],[ApplicabilityDecision(evidence_id='synthetic_a',
   relevant=False,supports_claim=False,audit_status='FAIL',reasons=['WRONG_VERSION'])],[])
  with patch('vn_labor_online.applicability.GeminiProvider') as factory:
   accepted,decisions,_=a.audit([source()],'Giải thích nghĩa vụ.',['GENERAL'],{})
  self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'FAIL')
  a.provider.structured.assert_not_called();factory.assert_not_called()
 def test_resolved_primary_does_not_retain_stale_warning(self):
  a=self.auditor();a._deterministic.return_value=([],[ApplicabilityDecision(evidence_id='synthetic_a',relevant=True,
   supports_claim=False,audit_status='UNRESOLVED')],['APPLICABILITY_UNRESOLVED:synthetic_a'])
  a.provider.structured.return_value={'decisions':{'synthetic_a':judgment()}}
  accepted,_,warnings=a.audit([source()],'Giải thích nghĩa vụ.',['GENERAL'],{})
  self.assertTrue(accepted);self.assertNotIn('APPLICABILITY_UNRESOLVED:synthetic_a',warnings)
 def test_second_task_can_recover_without_replacing_first_valid_decision(self):
  a=self.auditor();a.provider.structured.side_effect=[{'decisions':{'a':judgment()}},LLMProviderError(safe_code='OLLAMA_TIMEOUT')]
  p=self.secondary({'decisions':{'b':judgment()}})
  plan=EvidencePlan(mandatory_slots=['governing_rule'],slot_requirements={'governing_rule':[
   [LegalLocator(documents=['TEST/2099'],article='701')],[LegalLocator(documents=['TEST/2099'],article='702')]]})
  with patch('vn_labor_online.applicability.GeminiProvider',return_value=p):
   accepted,decisions,_=a.audit([source('a','701'),source('b','702')],'Giải thích hai nghĩa vụ.',['GENERAL'],{},plan=plan)
  self.assertEqual({e.unit_id for e in accepted},{'a','b'})
  self.assertEqual(decisions[0].reasons,['MODEL_APPLICABILITY_PASS'])
 def test_primary_reserves_component_and_request_time_for_fallback(self):
  a=self.auditor();clock=[100.0]
  def primary(*args):
   self.assertEqual(request_timeout(300),40)
   clock[0]+=40
   raise LLMProviderError(safe_code='OLLAMA_TIMEOUT')
  a.provider.structured.side_effect=primary
  p=self.secondary({'decisions':{'synthetic_a':judgment()}})
  def secondary(*args):
   self.assertEqual(request_timeout(300),20)
   clock[0]+=10
   return {'decisions':{'synthetic_a':judgment()}}
  p.structured.side_effect=secondary
  with patch('vn_labor_online.runtime.time.monotonic',side_effect=lambda:clock[0]),request_budget(120) as budget:
   budget.started=100
   with patch('vn_labor_online.applicability.GeminiProvider',return_value=p):
    accepted,_,_=a.audit([source()],'Giải thích nghĩa vụ.',['GENERAL'],{})
   self.assertTrue(accepted);self.assertGreaterEqual(budget.remaining(),60)
   self.assertEqual(budget.operation_spent['applicability'],50)
 def test_cancellation_is_not_replaced_with_secondary_inference(self):
  a=self.auditor();a.provider.structured.side_effect=RequestStopped('REQUEST_CANCELLED')
  with patch('vn_labor_online.applicability.GeminiProvider') as factory,self.assertRaises(RequestStopped):
   a.audit([source()],'Giải thích nghĩa vụ.',['GENERAL'],{})
  factory.assert_not_called()

class ProviderMetadataTests(unittest.TestCase):
 def test_component_deadline_survives_gemini_boundary(self):
  from tests.online import test_gemini_rate_limits as rates
  with self.assertRaises(OperationBudgetExceeded):rates.GeminiRetryTests.invoke(self,[OperationBudgetExceeded()])
 def test_component_deadline_survives_provider_boundary(self):
  for provider in [OllamaProvider(),HttpJsonProvider('http://localhost/unit','fake')]:
   with self.subTest(provider=type(provider).__name__):
    provider._post=Mock(side_effect=OperationBudgetExceeded())
    with self.assertRaises(OperationBudgetExceeded):provider.structured('s','u',{'type':'object'})
 def test_transport_timeout_has_safe_provider_code_and_no_message(self):
  for provider,prefix in [(OllamaProvider(),'OLLAMA'),(HttpJsonProvider('http://localhost/unit','fake'),'HTTP_JSON')]:
   with self.subTest(provider=prefix):
    provider._post=Mock(side_effect=httpx.ReadTimeout('PRIVATE_QUERY_AND_TOKEN'))
    with self.assertRaises(LLMProviderError) as caught:provider.structured('s','u',{'type':'object'})
    self.assertEqual(caught.exception.safe_code,prefix+'_TIMEOUT')
    self.assertNotIn('PRIVATE_QUERY_AND_TOKEN',str(caught.exception))
    self.assertEqual(public_error(caught.exception)['ma_loi'],prefix+'_TIMEOUT')
 def test_http_error_code_is_safe_without_provider_body(self):
  provider=OllamaProvider();request=httpx.Request('POST','http://localhost/private')
  provider._post=Mock(side_effect=httpx.HTTPStatusError('PRIVATE_BODY',request=request,response=httpx.Response(503,request=request)))
  with self.assertRaises(LLMProviderError) as caught:provider.structured('s','u',{'type':'object'})
  self.assertEqual(public_error(caught.exception)['ma_loi'],'OLLAMA_HTTP_503')
  self.assertNotIn('PRIVATE_BODY',str(caught.exception))
 def test_unknown_http_error_strings_still_not_public(self):
  self.assertNotIn('ma_loi',public_error(LLMProviderError('OLLAMA_HTTP_503 PRIVATE_BODY')))
  self.assertNotIn('ma_loi',public_error(LLMProviderError(safe_code='OLLAMA_HTTP_200')))

if __name__=='__main__':unittest.main()
