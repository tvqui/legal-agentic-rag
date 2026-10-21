"""Synthetic SDK failures; no requests, keys, downloads or real quota use."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from vn_labor_online.errors import LLMProviderError
from vn_labor_online.gemini_diagnostics import classify_error, public_diagnostics
from vn_labor_online.providers import GeminiProvider


PRIVATE = 'PRIVATE_KEY_PROMPT_AND_URL_MUST_NOT_BE_PRINTED'


def sdk_error(message, status='INVALID_ARGUMENT', details=None):
    error = Exception(PRIVATE)
    error.code = 400
    error.message = message
    error.status = status
    error.details = {'error': {'status':status,'message':message,'details':details or []}}
    return error


def load_checker():
    root=Path(__file__).resolve().parents[2]
    path=root/'kaggle/check_gemini.py'
    spec=importlib.util.spec_from_file_location('gemini_diagnostic_checker_test',path)
    module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'online_remote':SimpleNamespace(secret=lambda *a,**kw:PRIVATE)}):
        spec.loader.exec_module(module)
    return module


class GeminiDiagnosticTests(unittest.TestCase):
    def test_known_reasons_have_fixed_labels_and_never_echo_error(self):
        cases=[('API key not valid. '+PRIVATE,'API_KEY_REJECTED'),
            ('User location is not supported for the API use. '+PRIVATE,'REGION_UNSUPPORTED'),
            ('Please enable billing on your project. '+PRIVATE,'BILLING_REQUIRED'),
            ('Model is not available for this API version. '+PRIVATE,'MODEL_UNAVAILABLE'),
            ('Invalid response_json_schema: '+PRIVATE,'SCHEMA_REJECTED'),
            ('temperature is not supported: '+PRIVATE,'PARAMETER_REJECTED')]
        for message,reason in cases:
            with self.subTest(reason=reason):
                result=classify_error(sdk_error(message))
                self.assertEqual(result['error_reason'],reason)
                self.assertNotIn(PRIVATE,json.dumps(result))

    def test_structured_bad_request_field_is_reduced_to_a_known_parameter(self):
        result=classify_error(sdk_error(PRIVATE,details=[{
            '@type':'type.googleapis.com/google.rpc.BadRequest',
            'fieldViolations':[{'field':'generation_config.max_output_tokens.'+PRIVATE,
                                'description':'Invalid limit '+PRIVATE}]}]))
        self.assertEqual(result['error_fields'],['max_output_tokens'])
        self.assertNotIn(PRIVATE,json.dumps(result))

    def test_unknown_bad_request_does_not_guess_schema_or_quota(self):
        result=classify_error(sdk_error('Request contains an invalid argument. '+PRIVATE))
        self.assertEqual(result['error_reason'],'INVALID_ARGUMENT')
        self.assertNotIn('error_fields',result)
        self.assertNotIn('quota_kind',result)

    def test_failed_precondition_without_specific_evidence_stays_generic(self):
        result=classify_error(sdk_error(PRIVATE,'FAILED_PRECONDITION'))
        self.assertEqual(result['error_reason'],'FAILED_PRECONDITION')
        self.assertNotEqual(result['error_reason'],'BILLING_REQUIRED')

    def test_only_allowlisted_fields_status_and_hint_are_published(self):
        result=public_diagnostics({'error_reason':'INVALID_ARGUMENT','action_hint':PRIVATE,
            'api_status':PRIVATE,'error_fields':['temperature',PRIVATE,{}],'message':PRIVATE})
        self.assertEqual(result['error_fields'],['temperature'])
        self.assertNotIn(PRIVATE,json.dumps(result))
        self.assertEqual(public_diagnostics({'error_reason':{'secret':PRIVATE}}),{})

    def test_provider_preserves_safe_diagnostic_and_does_not_retry_400(self):
        try: from google import genai
        except ImportError: self.skipTest('Optional google-genai SDK unavailable')
        sdk=Mock(); sdk.__enter__=Mock(return_value=sdk); sdk.__exit__=Mock(return_value=False)
        sdk.models.generate_content.side_effect=sdk_error('response_json_schema invalid '+PRIVATE)
        provider=GeminiProvider('gemini-3.1-flash-lite',PRIVATE)
        provider.rate_limiter=Mock(); provider.rate_limiter.acquire.return_value=0
        with patch('google.genai.Client',return_value=sdk), self.assertRaises(LLMProviderError) as caught:
            provider.structured('system','user',{'type':'object'})
        self.assertEqual(sdk.models.generate_content.call_count,1)
        self.assertEqual(caught.exception.safe_code,'GEMINI_HTTP_400')
        self.assertEqual(caught.exception.safe_diagnostics['error_reason'],'SCHEMA_REJECTED')
        self.assertNotIn(PRIVATE,str(caught.exception))

    def test_readiness_passes_safe_reason_without_raw_message(self):
        provider=GeminiProvider('gemini-3.1-flash-lite',PRIVATE)
        provider.rate_limiter=Mock(); provider.rate_limiter.cooldown_snapshot.return_value={}
        provider.rate_limiter.rpm=13
        provider.structured=Mock(side_effect=LLMProviderError(PRIVATE,safe_code='GEMINI_HTTP_400',
            safe_diagnostics={'error_reason':'SCHEMA_REJECTED','action_hint':PRIVATE}))
        with patch('importlib.util.find_spec',return_value=SimpleNamespace()):
            report=provider.readiness()
        self.assertEqual(report['status'],'DEGRADED')
        self.assertEqual(report['error_reason'],'SCHEMA_REJECTED')
        self.assertNotIn(PRIVATE,json.dumps(report))

    def test_plain_probe_uses_same_gate_once_and_keeps_actual_content_private(self):
        try: from google import genai
        except ImportError: self.skipTest('Optional google-genai SDK unavailable')
        checker=load_checker(); sdk=Mock()
        sdk.__enter__=Mock(return_value=sdk); sdk.__exit__=Mock(return_value=False)
        sdk.models.generate_content.return_value=SimpleNamespace(text=PRIVATE)
        provider=GeminiProvider('gemini-3.1-flash-lite',PRIVATE)
        provider.rate_limiter=Mock()
        with patch('google.genai.Client',return_value=sdk): report=checker.plain_probe(provider)
        self.assertEqual(report['status'],'READY')
        provider.rate_limiter.acquire.assert_called_once()
        kwargs=sdk.models.generate_content.call_args.kwargs
        self.assertEqual(kwargs['contents'],'Reply OK.')
        self.assertIsNone(kwargs['config'].response_json_schema)
        self.assertIsNone(kwargs['config'].temperature)
        self.assertNotIn(PRIVATE,json.dumps(report))

    def test_plain_success_never_turns_failed_structured_readiness_into_success(self):
        checker=load_checker(); provider=Mock()
        provider.readiness.return_value={'status':'DEGRADED','error_code':'GEMINI_HTTP_400'}
        cfg=SimpleNamespace()
        output=io.StringIO()
        with patch.object(checker,'load_config',return_value=cfg), \
                patch.object(checker,'GeminiProvider',return_value=provider), \
                patch.object(checker,'plain_probe',return_value={'status':'READY','check':'PLAIN_PROBE'}) as probe, \
                patch.object(sys,'argv',['check_gemini.py','--model','gemini-3.1-flash-lite','--diagnose']), \
                contextlib.redirect_stdout(output):
            code=checker.main()
        self.assertEqual(code,1)
        provider.close.assert_called_once()
        probe.assert_called_once_with(provider)
        lines=[json.loads(s) for s in output.getvalue().splitlines()]
        self.assertEqual(lines[1]['comparison'],'STRUCTURED_REQUEST_CONFIGURATION_DIFFERS')
        self.assertTrue(lines[1]['structured_readiness_unchanged'])

    def test_429_does_not_trigger_extra_probe(self):
        checker=load_checker(); provider=Mock()
        provider.readiness.return_value={'status':'DEGRADED','error_code':'GEMINI_HTTP_429'}
        with patch.object(checker,'load_config',return_value=SimpleNamespace()), \
                patch.object(checker,'GeminiProvider',return_value=provider), \
                patch.object(checker,'plain_probe') as probe, \
                patch.object(sys,'argv',['check_gemini.py','--model','gemini-3.1-flash-lite','--diagnose']), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(checker.main(),1)
        probe.assert_not_called()

    def test_launcher_keeps_diagnostic_reason_but_rebuilds_hint(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('gemini400_launcher',root/'kaggle/online_remote.py')
        launcher=importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)
        result=launcher.readiness_diagnostics({'components':{'answer_reviewer':{
            'status':'DEGRADED','error_code':'GEMINI_HTTP_400','error_reason':'BILLING_REQUIRED',
            'action_hint':PRIVATE,'message':PRIVATE,'api_status':PRIVATE}}})
        self.assertEqual(result['answer_reviewer']['error_reason'],'BILLING_REQUIRED')
        self.assertNotIn(PRIVATE,json.dumps(result))


if __name__=='__main__': unittest.main()
