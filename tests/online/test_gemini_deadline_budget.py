import unittest
from unittest.mock import Mock,patch
from vn_labor_online.providers import GeminiProvider
from vn_labor_online.runtime import request_budget,RequestBudget,OperationBudgetExceeded
from vn_labor_online.gemini_diagnostics import classify_error


class GeminiDeadlineBudgetTests(unittest.TestCase):
    def test_insufficient_configured_timeout_never_calls_the_sdk_or_takes_a_slot(self):
        provider=GeminiProvider('test-model','test-key',timeout=7)
        provider.rate_limiter=Mock()
        with patch('google.genai.Client') as client, self.assertRaises(OperationBudgetExceeded):
            provider.structured('system','input',{'type':'object'})
        client.assert_not_called()
        provider.rate_limiter.acquire.assert_not_called()

    def test_insufficient_root_budget_is_not_expanded_to_the_provider_minimum(self):
        provider=GeminiProvider('test-model','test-key',timeout=45)
        provider.rate_limiter=Mock()
        with request_budget(8),patch('google.genai.Client') as client,self.assertRaises(OperationBudgetExceeded):
            provider.structured('system','input',{'type':'object'})
        client.assert_not_called()

    def test_pacing_wait_is_charged_before_checking_the_inference_deadline_again(self):
        clock=Mock(return_value=0)
        provider=GeminiProvider('test-model','test-key',timeout=45)
        provider.rate_limiter=Mock()
        def pace(*args):clock.return_value=9;return 9
        provider.rate_limiter.acquire.side_effect=pace
        with patch('vn_labor_online.runtime.time.monotonic',clock),request_budget(18,existing=RequestBudget(18,started=0)),patch('google.genai.Client') as client,self.assertRaises(OperationBudgetExceeded):
            provider.structured('system','input',{'type':'object'})
        client.assert_not_called()
        provider.rate_limiter.acquire.assert_called_once()

    def test_observed_upstream_deadline_error_has_only_fixed_safe_diagnostics(self):
        error=RuntimeError('Manually set deadline 7s is too short. Minimum allowed deadline is 10s. private-value')
        # SDK variants can expose either a message or a structured payload.
        error.message=str(error)
        error.status='INVALID_ARGUMENT'
        result=classify_error(error)
        self.assertEqual(result['error_reason'],'DEADLINE_TOO_SHORT')
        self.assertNotIn('private-value',str(result))


if __name__=='__main__':unittest.main()
