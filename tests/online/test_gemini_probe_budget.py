"""Bounded cold-start probes, tested without network or real waiting."""
import os
from pathlib import Path
import importlib.util
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from vn_labor_online.providers import GeminiProvider,gemini_probe_timeout
from vn_labor_online.runtime import request_timeout


class GeminiProbeBudgetTests(unittest.TestCase):
    def test_default_and_invalid_budget_configuration(self):
        with patch.dict(os.environ,{},clear=True): self.assertEqual(gemini_probe_timeout(),20)
        for value in ('0','61','-1','nan','60.5','PRIVATE_INVALID_VALUE'):
            with patch.dict(os.environ,{'VN_LABOR_GEMINI_PROBE_TIMEOUT_SECONDS':value}), \
                    self.assertRaises(ValueError) as caught:
                gemini_probe_timeout()
            self.assertNotIn('PRIVATE_INVALID_VALUE',str(caught.exception))

    def test_configured_probe_can_use_sixty_seconds_not_twenty(self):
        provider=GeminiProvider('budget-test-model','fake-key',timeout=90)
        observed=[]
        def generate(*args):
            observed.append(request_timeout(1000))
            return {'ready':True}
        provider.structured=Mock(side_effect=generate)
        with patch.dict(os.environ,{'VN_LABOR_GEMINI_PROBE_TIMEOUT_SECONDS':'60'}), \
                patch('importlib.util.find_spec',return_value=SimpleNamespace()):
            report=provider.readiness()
        self.assertEqual(report['status'],'READY')
        self.assertEqual(report['probe_timeout_seconds'],60)
        self.assertGreater(observed[0],59)
        self.assertLessEqual(observed[0],60)

    def test_provider_timeout_is_still_an_upper_bound(self):
        provider=GeminiProvider('budget-test-model','fake-key',timeout=10)
        provider.structured=Mock(return_value={'ready':True})
        with patch.dict(os.environ,{'VN_LABOR_GEMINI_PROBE_TIMEOUT_SECONDS':'60'}), \
                patch('importlib.util.find_spec',return_value=SimpleNamespace()):
            self.assertEqual(provider.readiness()['probe_timeout_seconds'],10)

    def test_invalid_budget_never_calls_inference_or_marks_ready(self):
        provider=GeminiProvider('budget-test-model','fake-key',timeout=90)
        provider.structured=Mock()
        with patch.dict(os.environ,{'VN_LABOR_GEMINI_PROBE_TIMEOUT_SECONDS':'999'}):
            report=provider.readiness()
        self.assertEqual(report['status'],'DEGRADED')
        self.assertEqual(report['error_code'],'GEMINI_PROBE_TIMEOUT_CONFIGURATION_INVALID')
        provider.structured.assert_not_called()

    def test_launcher_http_timeout_covers_two_sequential_probes(self):
        path=Path(__file__).resolve().parents[2]/'kaggle/online_remote.py'
        spec=importlib.util.spec_from_file_location('probe_budget_launcher',path)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        snapshot={'ready':True,'components':{role:{'status':'READY'} for role in
            ('researcher','auditor','adjudicator','answer_reviewer')}}
        with patch.dict(os.environ,{'VN_LABOR_GEMINI_PROBE_TIMEOUT_SECONDS':'60'}), \
                patch.object(module,'get_json',return_value=snapshot) as get:
            self.assertTrue(module.wait_ready('http://127.0.0.1/ready','fake-token',SimpleNamespace(poll=lambda:None),240)['ready'])
        self.assertEqual(get.call_args.kwargs['timeout'],125)


if __name__=='__main__': unittest.main()
