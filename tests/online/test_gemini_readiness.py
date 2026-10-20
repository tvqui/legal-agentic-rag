from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from vn_labor_online.errors import LLMProviderError, ProviderRateLimited
from vn_labor_online.gemini_quota import GeminiRateLimiter
from vn_labor_online.providers import GeminiProvider
from vn_labor_online.runtime import RequestStopped


class GeminiReadinessTests(unittest.TestCase):
    def provider(self):
        value = GeminiProvider('readiness-only-unit-model', 'PRIVATE_KEY_NOT_FOR_OUTPUT')
        value.rate_limiter = GeminiRateLimiter(13)
        value.structured = Mock()
        self.patcher = patch('importlib.util.find_spec', return_value=SimpleNamespace())
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        return value

    def test_missing_key_and_sdk_have_actionable_codes_without_inference(self):
        p = self.provider()
        p.api_key = None
        self.assertEqual(p.readiness()['error_code'], 'GEMINI_API_KEY_MISSING')
        p.structured.assert_not_called()
        p.api_key = 'PRIVATE_KEY_NOT_FOR_OUTPUT'
        with patch('importlib.util.find_spec', return_value=None):
            self.assertEqual(p.readiness()['error_code'], 'GEMINI_SDK_MISSING')
        p.structured.assert_not_called()

    def test_success_is_cached_only_after_a_real_probe_result(self):
        p = self.provider()
        p.structured.return_value = {'ready': True}
        self.assertEqual(p.readiness()['status'], 'READY')
        self.assertEqual(p.readiness()['status'], 'READY')
        self.assertEqual(p.structured.call_count, 1)

    def test_false_probe_result_is_never_marked_ready(self):
        p = self.provider()
        p.structured.return_value = {'ready': False}
        result = p.readiness()
        self.assertEqual(result['status'], 'DEGRADED')
        self.assertEqual(result['error_code'], 'GEMINI_PROBE_RESPONSE_MISMATCH')

    def test_auth_failure_is_diagnostic_and_private_message_is_not_exposed(self):
        p = self.provider()
        p.structured.side_effect = LLMProviderError('PRIVATE_KEY_NOT_FOR_OUTPUT request details', safe_code='GEMINI_HTTP_401')
        result = p.readiness()
        self.assertEqual(result['error_code'], 'GEMINI_HTTP_401')
        self.assertEqual(result['status'], 'DEGRADED')
        self.assertNotIn('PRIVATE_KEY_NOT_FOR_OUTPUT', json.dumps(result))
        self.assertEqual(p.readiness()['error_code'], 'GEMINI_HTTP_401')
        self.assertEqual(p.structured.call_count, 1)

    def test_rate_limit_failure_is_cached_then_can_recover(self):
        p = self.provider()
        p.structured.side_effect = ProviderRateLimited(quota_kind='RPM', retry_after_seconds=30)
        result = p.readiness()
        self.assertEqual(result['error_code'], 'GEMINI_HTTP_429')
        self.assertEqual(result['quota_kind'], 'RPM')
        self.assertEqual(result['retry_after_seconds'], 30)
        p.readiness()
        self.assertEqual(p.structured.call_count, 1)
        p._probe_next_at = 0  # expire without waiting in a test
        p.structured.side_effect = None
        p.structured.return_value = {'ready': True}
        self.assertEqual(p.readiness()['status'], 'READY')
        self.assertEqual(p.structured.call_count, 2)

    def test_probe_deadline_does_not_hide_active_upstream_429_cooldown(self):
        p = self.provider()
        p.rate_limiter.defer(45, 'RPM')
        p.structured.side_effect = RequestStopped('REQUEST_DEADLINE_EXCEEDED')
        result = p.readiness()
        self.assertEqual(result['error_code'], 'GEMINI_HTTP_429')
        self.assertEqual(result['quota_kind'], 'RPM')
        self.assertGreaterEqual(result['retry_after_seconds'], 44)

    def test_network_probe_deadline_without_cooldown_is_reported_as_timeout(self):
        p = self.provider()
        p.structured.side_effect = RequestStopped('REQUEST_DEADLINE_EXCEEDED')
        self.assertEqual(p.readiness()['error_code'], 'GEMINI_PROBE_TIMEOUT')

    def test_overlapping_ready_requests_do_not_duplicate_inference(self):
        p = self.provider()
        p._probe_lock.acquire()
        try:
            result = p.readiness()
        finally:
            p._probe_lock.release()
        self.assertEqual(result['error_code'], 'GEMINI_PROBE_IN_PROGRESS')
        p.structured.assert_not_called()


def load_launcher():
    path = Path(__file__).resolve().parents[2] / 'kaggle/online_remote.py'
    spec = importlib.util.spec_from_file_location('online_ready_retry_tests', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(ready, code=None, kind=None):
    components = {name:{'status':'READY', 'provider':'ollama'}
                  for name in ('researcher','auditor','adjudicator','answer_reviewer')}
    if not ready:
        components['answer_reviewer'] = {'status':'DEGRADED', 'provider':'gemini'}
        if code:
            components['answer_reviewer']['error_code'] = code
        if kind:
            components['answer_reviewer']['quota_kind'] = kind
    return {'ready':ready, 'components':components, 'UNSAFE_PRIVATE_CONFIG':'DO_NOT_PRINT'}


class LauncherReadinessTests(unittest.TestCase):
    def setUp(self):
        self.launcher = load_launcher()
        self.clock = 0.0
        self.process = SimpleNamespace(poll=lambda: None)

    def advance(self, seconds):
        self.clock += seconds

    def run_wait(self, results, timeout=12):
        with patch.object(self.launcher, 'get_json', side_effect=results) as request, \
                patch.object(self.launcher.time, 'monotonic', side_effect=lambda:self.clock), \
                patch.object(self.launcher.time, 'sleep', side_effect=self.advance), patch('builtins.print'):
            result = self.launcher.wait_ready('http://127.0.0.1:8000/ready', 'SECRET_TOKEN', self.process, timeout)
            return result, request

    def test_transient_degraded_snapshot_is_retried_instead_of_aborting(self):
        result, request = self.run_wait([snapshot(False, 'GEMINI_HTTP_429', 'RPM'), snapshot(True)])
        self.assertTrue(result['ready'])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(self.clock, 2)

    def test_reviewer_must_be_ready_even_if_top_level_flag_is_wrong(self):
        bad = snapshot(False, 'GEMINI_PROBE_IN_PROGRESS')
        bad['ready'] = True
        result, request = self.run_wait([bad, snapshot(True)])
        self.assertTrue(result['ready'])
        self.assertEqual(request.call_count, 2)

    def test_daily_and_invalid_credentials_fail_with_safe_actionable_diagnostics(self):
        for code, kind in [('GEMINI_HTTP_401',None), ('GEMINI_HTTP_429','DAILY'),
                           ('GEMINI_HTTP_429','QUOTA_DISABLED')]:
            with self.subTest(code=code, kind=kind), self.assertRaises(RuntimeError) as caught:
                self.run_wait([snapshot(False, code, kind)])
            self.assertNotIn('DO_NOT_PRINT', str(caught.exception))
            self.assertNotIn('SECRET_TOKEN', str(caught.exception))
            self.assertIn(code, str(caught.exception))

    def test_startup_timeout_is_bounded_and_keeps_component_diagnostics(self):
        with self.assertRaisesRegex(RuntimeError, 'GEMINI_PROBE_TIMEOUT'):
            self.run_wait([snapshot(False, 'GEMINI_PROBE_TIMEOUT')] * 5, timeout=4)
        self.assertEqual(self.clock, 4)

    def test_temporary_transport_error_can_recover(self):
        result, request = self.run_wait([TimeoutError('PRIVATE_REQUEST_URL'), snapshot(True)])
        self.assertTrue(result['ready'])
        self.assertEqual(request.call_count, 2)

    def test_backend_exit_is_not_hidden_by_readiness_retry(self):
        self.process = SimpleNamespace(poll=lambda:1)
        with self.assertRaisesRegex(RuntimeError, 'Backend exited'):
            self.run_wait([snapshot(True)])


if __name__ == '__main__':
    unittest.main()
