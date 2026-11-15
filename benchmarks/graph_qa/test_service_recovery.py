"""Pair recovery is bounded, transparent and unavailable for legal refusals."""
import unittest
from unittest.mock import patch
import test_runner as fixtures
from test_runner import FakeWorker
import protocol as p
import run as runner
from service_recovery import service_failure

class ServiceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.base=fixtures.RunnerTests();self.base.setUp()
        self.root=self.base.root;self.args=self.base.args
        self.settings={**self.base.settings,'service_recovery_enabled':True}
        p.write(self.base.settings_path,self.settings)
        p.write(self.root/'preflight.json',{'settings':self.settings,'code_sha256':p.code_hashes(),'runtime':FakeWorker().meta})
    def tearDown(self):self.base.tearDown()
    def failure(self,result,code='GEMINI_HTTP_503'):
        result['response'].update(status='INSUFFICIENT_EVIDENCE',limitations=['review_service_unavailable'])
        result['response']['trace']['execution_steps']=[{'step':'semantic_review','status':'ERROR','output':{'ma_loi':code}}]
        return result
    def initial(self,persistent=False,code='GEMINI_HTTP_503'):
        original=FakeWorker.ask
        def ask(worker,job,timeout):
            result=original(worker,job,timeout)
            if job['arm']=='graph_on' and (len(FakeWorker.asks)<=2 or persistent):self.failure(result,code)
            return result
        self.patcher=patch.object(FakeWorker,'ask',ask);self.patcher.start();self.addCleanup(self.patcher.stop)
        runner.execute(self.args)
    def test_once_for_both_arms_and_keep_every_original_cost(self):
        self.initial();runner.recover_services(self.args);runner.recover_services(self.args)
        self.assertEqual(len(FakeWorker.asks),4)
        self.assertEqual(FakeWorker.asks[:2],FakeWorker.asks[2:])
        journal=p.rows(self.root/'attempt_journal.jsonl');self.assertEqual(len(journal),4)
        self.assertEqual(len(p.rows(self.root/'retry_history.jsonl')),2)
        summary=p.load(self.root/'attempt_history_summary.json')
        self.assertEqual(summary['total_service_failure_attempts'],1)
        self.assertEqual(summary['service_recovery_attempts'],2)
        self.assertEqual(summary['all_attempts_elapsed_ms'],20)
        self.assertTrue(all(r.get('service_recovery_pair')=='q:1' for r in p.rows(self.root/'responses.jsonl')))
    def test_persistent_service_error_never_gets_a_second_pair_retry(self):
        self.initial(persistent=True);runner.recover_services(self.args);runner.recover_services(self.args)
        self.assertEqual(len(FakeWorker.asks),4)
        self.assertEqual(p.load(self.root/'service_recovery.json')['q:1']['status'],'DONE')
    def test_legal_refusal_quota_and_unknown_error_are_not_service_recovery(self):
        for code in ['GEMINI_HTTP_429','OLLAMA_TIMEOUT','GEMINI_CLIENT_ERROR','GEMINI_SCHEMA_VALIDATION_FAILED']:
            record=self.failure({'status':'OK','response':{'trace':{}}},code)
            self.assertFalse(service_failure(record))
        self.assertFalse(service_failure({'status':'OK','response':{'status':'INSUFFICIENT_EVIDENCE','limitations':['answer_coverage']}}))
        self.initial(code='GEMINI_SCHEMA_VALIDATION_FAILED');runner.recover_services(self.args)
        self.assertEqual(len(FakeWorker.asks),2)
    def test_old_optional_503_cannot_make_a_final_schema_error_retryable(self):
        record=self.failure({'status':'OK','response':{'trace':{}}})
        record['response']['trace']['execution_steps'].append({
            'step':'semantic_review','status':'ERROR','output':{'ma_loi':'GEMINI_SCHEMA_VALIDATION_FAILED'}})
        self.assertFalse(service_failure(record))

    def test_no_opt_in_no_recovery(self):
        self.initial();self.settings['service_recovery_enabled']=False;p.write(self.base.settings_path,self.settings)
        with self.assertRaises(ValueError):runner.recover_services(self.args)
        self.assertEqual(len(FakeWorker.asks),2)
    def test_unknown_crash_outcome_is_not_blindly_submitted_again(self):
        self.initial()
        with patch.object(FakeWorker,'ask',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):runner.recover_services(self.args)
        with self.assertRaisesRegex(RuntimeError,'uncertain'):runner.recover_services(self.args)
        self.assertEqual(len(FakeWorker.asks),2)
        self.assertIn('SERVICE_RECOVERY_PAIR_INCOMPLETE',p.load(self.root/'comparison.json')['warnings'])

if __name__=='__main__':unittest.main()
