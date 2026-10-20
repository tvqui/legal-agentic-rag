"""Virtual-clock regression checks; no real requests, quota use or minute sleeps."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from vn_labor_online.errors import LLMProviderError, ProviderRateLimited
from vn_labor_online.gemini_quota import (
    GeminiRateLimiter, GeminiRatePolicy, get_gemini_limiter, quota_info,
)
from vn_labor_online.providers import GeminiProvider
from vn_labor_online.runtime import RequestStopped, request_budget


class Clock:
    def __init__(self):
        self.now = 0.0
        self.after_sleep = None

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.after_sleep:
            self.after_sleep()


class UpstreamError(Exception):
    def __init__(self, kind='RPM', delay=None, headers=None, code=429):
        super().__init__('private provider message must never reach client')
        self.code = code
        self.message = 'private provider message'
        quota = {'RPM': 'GenerateRequestsPerMinutePerProjectPerModel',
                 'TPM': 'GenerateInputTokensPerMinutePerProjectPerModel',
                 'DAILY': 'GenerateRequestsPerDayPerProjectPerModel',
                 'UNKNOWN': 'UnknownQuota', 'QUOTA_DISABLED': 'RequestsPerMinute'}[kind]
        violation = {'quotaId': quota}
        if kind == 'QUOTA_DISABLED':
            violation['quotaValue'] = '0'
        details = [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [violation]}]
        if delay is not None:
            details.append({'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': delay})
        self.details = {'error': {'code': code, 'details': details}}
        self.response = SimpleNamespace(headers=headers or {})


class GeminiPacingTests(unittest.TestCase):
    def test_thirteen_per_rolling_minute_with_no_initial_burst(self):
        clock = Clock()
        gate = GeminiRateLimiter(13, clock=clock.time, sleep=clock.sleep)
        starts = []
        for _ in range(40):
            gate.acquire(70)
            starts.append(clock.time())
        for now in starts:
            self.assertLessEqual(sum(now - 60 < start <= now for start in starts), 13)
        self.assertTrue(all(b - a >= 60 / 13 for a, b in zip(starts, starts[1:])))

    def test_roles_and_different_api_keys_share_the_same_project_model_gate(self):
        a = GeminiProvider('rate-sharing-unit-model', 'key-one')
        b = GeminiProvider('models/rate-sharing-unit-model', 'key-two')
        self.assertIs(a.rate_limiter, b.rate_limiter)
        another = get_gemini_limiter('rate-sharing-unit-model', replace(a.rate_policy, rpm=12))
        self.assertIs(another, a.rate_limiter)
        self.assertEqual(another.rpm, 12)

    def test_simultaneous_calls_cannot_bypass_the_gate(self):
        clock = Clock()
        gate = GeminiRateLimiter(13, clock=clock.time, sleep=clock.sleep)
        def attempt(_):
            try:
                gate.acquire(0)
                return True
            except ProviderRateLimited:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(attempt, range(30)))
        self.assertEqual(sum(accepted), 1)

    def test_wait_budget_does_not_truncate_upstream_cooldown(self):
        clock = Clock()
        gate = GeminiRateLimiter(13, clock=clock.time, sleep=clock.sleep)
        gate.defer(100, 'RPM')
        with self.assertRaises(ProviderRateLimited) as caught:
            gate.acquire(70)
        self.assertEqual(caught.exception.retry_after_seconds, 100)
        self.assertEqual(clock.now, 0)

    def test_rate_wait_honors_request_deadline_and_cancellation(self):
        clock = Clock()
        gate = GeminiRateLimiter(13, clock=clock.time, sleep=clock.sleep)
        gate.defer(5, 'RPM')
        with request_budget(.5), self.assertRaises(RequestStopped) as caught:
            gate.acquire(70)
        self.assertEqual(caught.exception.reason, 'REQUEST_DEADLINE_EXCEEDED')
        self.assertEqual(clock.now, 0)
        with self.assertRaises(RequestStopped) as caught:
            with request_budget(120) as budget:
                clock.after_sleep = budget.cancelled.set
                gate.acquire(70)
        self.assertEqual(caught.exception.reason, 'REQUEST_CANCELLED')
        self.assertLessEqual(clock.now, .25)

    def test_configuration_rejects_disabled_unbounded_or_invalid_limits(self):
        for key, value in [('VN_LABOR_GEMINI_RPM', '0'), ('VN_LABOR_GEMINI_RATE_RETRIES', '99'),
                           ('VN_LABOR_GEMINI_RATE_MAX_WAIT_SECONDS', 'nan')]:
            with patch.dict('os.environ', {key: value}), self.assertRaises(ValueError):
                GeminiRatePolicy.from_env()


class GeminiRetryTests(unittest.TestCase):
    def invoke(self, results, *, wait=70, retries=2, run=None):
        try:
            from google import genai
        except ImportError:
            self.skipTest('Optional Gemini SDK is not installed')
        self.clock = Clock()
        self.starts = []
        self.gate = GeminiRateLimiter(13, clock=self.clock.time, sleep=self.clock.sleep)
        self.sdk = Mock()
        self.sdk.__enter__ = Mock(return_value=self.sdk)
        self.sdk.__exit__ = Mock(return_value=False)
        outcomes = iter(results)
        def generate(**kwargs):
            self.starts.append(self.clock.now)
            value = next(outcomes)
            if isinstance(value, Exception):
                raise value
            return SimpleNamespace(text='{"ok":true}', candidates=[])
        self.sdk.models.generate_content.side_effect = generate
        with patch('vn_labor_online.providers.get_gemini_limiter', return_value=self.gate), \
                patch('google.genai.Client', return_value=self.sdk):
            provider = GeminiProvider('fake-rpm-model', 'fake-key')
            provider.rate_policy = replace(provider.rate_policy, max_retries=retries, max_wait_seconds=wait)
            if run:
                return run(provider)
            return provider.structured('system', 'user', {'type':'object', 'properties':{'ok':{'type':'boolean'}}, 'required':['ok']})

    def test_minute_limit_retries_then_returns_schema_valid_result(self):
        result = self.invoke([UpstreamError('RPM', '2s', {'retry-after':'3'}), True])
        self.assertEqual(result, {'ok': True})
        self.assertEqual(len(self.starts), 2)
        self.assertGreaterEqual(self.starts[1], 60 / 13)
        self.assertGreaterEqual(self.starts[1], 3)
        options = self.sdk.models.generate_content.call_args.kwargs['config']
        self.assertEqual(options.response_mime_type, 'application/json')

    def test_unknown_429_does_not_become_a_daily_quota_claim(self):
        result = self.invoke([UpstreamError('UNKNOWN'), True])
        self.assertTrue(result['ok'])
        self.assertGreaterEqual(self.starts[1], 60)
        self.assertEqual(quota_info(UpstreamError('UNKNOWN')).kind, 'UNKNOWN')

    def test_token_limit_honors_retryinfo_and_header_together(self):
        error = UpstreamError('TPM', {'seconds':2, 'nanos':500000000}, {'Retry-After':'7'})
        self.assertEqual(quota_info(error).kind, 'TPM')
        result = self.invoke([error, True])
        self.assertTrue(result['ok'])
        self.assertGreaterEqual(self.starts[1], 7)

    def test_daily_or_zero_quota_is_not_retried_as_a_minute_limit(self):
        for kind in ('DAILY', 'QUOTA_DISABLED'):
            with self.subTest(kind=kind), self.assertRaises(ProviderRateLimited) as caught:
                self.invoke([UpstreamError(kind, '1s'), True])
            self.assertEqual(caught.exception.quota_kind, kind)
            self.assertIsNone(caught.exception.retry_after_seconds)
            self.assertEqual(len(self.starts), 1)
            self.assertEqual(self.clock.now, 0)

    def test_repeated_429_is_bounded_and_credential_safe(self):
        with self.assertRaises(ProviderRateLimited) as caught:
            self.invoke([UpstreamError('RPM', '1s')] * 4)
        self.assertEqual(len(self.starts), 3)
        self.assertEqual(caught.exception.quota_kind, 'RPM')
        self.assertNotIn('private', str(caught.exception))
        self.assertNotIn('fake-key', str(caught.exception))

    def test_excessive_retryafter_returns_without_waiting_hundreds_of_seconds(self):
        with self.assertRaises(ProviderRateLimited) as caught:
            self.invoke([UpstreamError('RPM', '300s'), True])
        self.assertEqual(len(self.starts), 1)
        self.assertGreaterEqual(caught.exception.retry_after_seconds, 300)
        self.assertEqual(self.clock.now, 0)

    def test_schema_400_is_not_retried_or_misclassified_as_rpm(self):
        with self.assertRaises(LLMProviderError) as caught:
            self.invoke([UpstreamError(code=400), True])
        self.assertEqual(caught.exception.safe_code, 'GEMINI_HTTP_400')
        self.assertEqual(len(self.starts), 1)


class QuotaPropagationTests(unittest.TestCase):
    def test_researcher_does_not_swallow_typed_exhausted_rate_limits(self):
        from vn_labor_online.analysis import analyze, intake
        from vn_labor_online.config import ResearcherConfig
        from vn_labor_online.researcher import LegalResearcher
        researcher = LegalResearcher(ResearcherConfig(mode='gemini', adaptive=False, model='no-call', api_key='fake'))
        researcher.provider = Mock()
        researcher.provider.structured.side_effect = ProviderRateLimited(quota_kind='RPM', retry_after_seconds=17)
        analysis = analyze(intake('Tôi muốn hỏi các quyền và nghĩa vụ về tiền lương lao động.', []))
        with self.assertRaises(ProviderRateLimited) as caught:
            researcher.enrich(analysis, analysis.query_text, [])
        self.assertEqual(caught.exception.retry_after_seconds, 17)

    def test_semantic_auditor_preserves_quota_details_without_publishing_unchecked_draft(self):
        from tests.online.test_semantic_answer_review import sample
        from vn_labor_online.answer_review import review_answer
        pack, draft, _ = sample()
        provider = Mock()
        provider.structured.side_effect = ProviderRateLimited(quota_kind='RPM', retry_after_seconds=23)
        with self.assertRaises(ProviderRateLimited) as caught:
            review_answer(provider, draft, pack)
        self.assertEqual(caught.exception.retry_after_seconds, 23)
        self.assertEqual(provider.structured.call_count, 1)

    def test_api_preserves_retry_delay_and_distinguishes_daily(self):
        from fastapi.testclient import TestClient
        from vn_labor_online.api import create_app
        from vn_labor_online.config import OnlineConfig
        pipe = Mock()
        pipe.cfg = OnlineConfig(artifact_source='test')
        for kind, delay in [('RPM', 17.2), ('TPM', 3), ('DAILY', None)]:
            pipe.ask.side_effect = ProviderRateLimited(quota_kind=kind, retry_after_seconds=delay)
            with patch('vn_labor_online.api.OnlinePipeline', return_value=pipe), \
                    patch('vn_labor_online.api.load_config'), patch.dict('os.environ', {'VN_LABOR_API_KEY':''}):
                with TestClient(create_app()) as client:
                    response = client.post('/v1/answer', json={'question':'Câu hỏi kiểm tra hạn mức AI'})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['details']['quota_kind'], kind)
            if kind == 'DAILY':
                self.assertNotIn('retry-after', response.headers)
            else:
                self.assertEqual(response.headers['retry-after'], '18' if kind == 'RPM' else '3')


if __name__ == '__main__':
    unittest.main()
