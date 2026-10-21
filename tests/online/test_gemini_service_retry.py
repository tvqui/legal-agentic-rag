"""Bounded retries with a virtual clock; no cloud calls or model loading."""
import unittest
from unittest.mock import patch
from tests.online import test_gemini_rate_limits as rates
from vn_labor_online.errors import LLMProviderError,ProviderRateLimited
from vn_labor_online.providers import _wait_service_retry
from vn_labor_online.runtime import RequestStopped,request_budget


class GeminiServiceRetryTests(unittest.TestCase):
    invoke=rates.GeminiRetryTests.invoke

    def virtual_wait(self,delay):
        self.clock.sleep(delay)

    def test_transient_service_error_retries_through_same_rpm_gate(self):
        with patch('vn_labor_online.providers._wait_service_retry',side_effect=self.virtual_wait):
            result=self.invoke([rates.UpstreamError(code=503),True])
        self.assertTrue(result['ok'])
        self.assertEqual(len(self.starts),2)
        self.assertGreaterEqual(self.starts[1]-self.starts[0],60/13)
        self.assertFalse(self.gate.cooldown_snapshot())

    def test_repeated_service_failure_is_bounded_and_is_not_misreported_as_quota(self):
        with patch('vn_labor_online.providers._wait_service_retry',side_effect=self.virtual_wait):
            with self.assertRaises(LLMProviderError) as caught:
                self.invoke([rates.UpstreamError(code=503)]*4)
        self.assertNotIsInstance(caught.exception,ProviderRateLimited)
        self.assertEqual(caught.exception.safe_code,'GEMINI_HTTP_503')
        self.assertEqual(len(self.starts),3)
        self.assertNotIn('private',str(caught.exception))

    def test_long_retry_after_retains_original_service_error_without_waiting(self):
        with patch('vn_labor_online.providers._wait_service_retry') as wait:
            with self.assertRaises(LLMProviderError) as caught:
                self.invoke([rates.UpstreamError(code=503,headers={'Retry-After':'300'}),True])
        self.assertEqual(caught.exception.safe_code,'GEMINI_HTTP_503')
        self.assertNotIsInstance(caught.exception,ProviderRateLimited)
        self.assertEqual(len(self.starts),1)
        wait.assert_not_called()

    def test_client_errors_are_not_retried(self):
        for code in (400,401,403,404):
            with self.subTest(code=code),self.assertRaises(LLMProviderError) as caught:
                self.invoke([rates.UpstreamError(code=code),True])
            self.assertEqual(caught.exception.safe_code,f'GEMINI_HTTP_{code}')
            self.assertEqual(len(self.starts),1)

    def test_retry_sleep_honors_cancellation(self):
        clock=rates.Clock()
        with self.assertRaises(RequestStopped) as caught:
            with request_budget(30) as budget:
                clock.after_sleep=budget.cancelled.set
                with patch('vn_labor_online.providers.time.monotonic',side_effect=clock.time),patch('vn_labor_online.providers.time.sleep',side_effect=clock.sleep):
                    _wait_service_retry(5)
        self.assertEqual(caught.exception.reason,'REQUEST_CANCELLED')
        self.assertLessEqual(clock.now,.25)


if __name__=='__main__': unittest.main()
