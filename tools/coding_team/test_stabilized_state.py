"""Offline state/retry safety regressions; no live models or service calls."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('coding_team_state', Path(__file__).with_name('team.py'))
team = importlib.util.module_from_spec(spec)
spec.loader.exec_module(team)


class StabilizedStateTests(unittest.TestCase):
    def setUp(self):
        env_loader=patch.object(team.coding_writer,'load_tool_env');env_loader.start();self.addCleanup(env_loader.stop)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / 'run'
        team.prepare_probe(self.run)
        self.client = Mock()

    def manifest(self):
        return json.loads((self.run / 'manifest.json').read_text(encoding='utf8'))

    def test_missing_create_id_never_creates_a_second_job(self):
        for invalid in (None, '', 'space in id'):
            with self.subTest(invalid=invalid):
                path = Path(self.temp.name) / ('probe_' + str(len(str(invalid))))
                team.prepare_probe(path)
                client = Mock()
                client.interactions.create.return_value = SimpleNamespace(id=invalid, status='in_progress')
                with self.assertRaises(team.ProviderFailure):
                    team.execute(path, 'antigravity', client, wait_seconds=0)
                self.assertEqual(team.execute(path, 'antigravity', client, wait_seconds=0, allow_partial=True), 'ERROR')
                self.assertEqual(client.interactions.create.call_count, 1)
                with self.assertRaises(ValueError):
                    team.execute(path, 'antigravity', client, wait_seconds=0)
                self.assertEqual(client.interactions.create.call_count, 1)
                m = json.loads((path/'manifest.json').read_text(encoding='utf8'))
                self.assertTrue(m['roles']['antigravity']['unknown_remote_outcome'])

    def test_existing_running_record_without_id_cannot_post(self):
        m = self.manifest()
        m['roles']['antigravity'] = {'status':'RUNNING', 'submitted_at':100}
        team.save(self.run/'manifest.json', m)
        with self.assertRaises(team.ProviderFailure):
            team.execute(self.run, 'antigravity', self.client, wait_seconds=0)
        self.client.interactions.create.assert_not_called()
        self.assertEqual(self.manifest()['roles']['antigravity']['status'], 'ERROR')

    def test_deadline_is_persisted_and_default_resume_cannot_extend_it(self):
        self.client.interactions.create.return_value = SimpleNamespace(id='job-1', status='in_progress')
        self.assertEqual(team.execute(self.run, 'antigravity', self.client, wait_seconds=0,
                                     wall_clock=lambda:100, remote_max_seconds=90), 'RUNNING')
        m = self.manifest()['roles']['antigravity']
        self.assertEqual((m['remote_max_seconds'], m['remote_deadline_at']), (90,190))
        self.client.interactions.get.return_value = SimpleNamespace(status='in_progress')
        self.client.interactions.cancel.return_value = SimpleNamespace(status='cancelled')
        self.assertEqual(team.execute(self.run, 'antigravity', self.client, wait_seconds=0,
                                     wall_clock=lambda:191), 'CANCELLED')
        self.assertEqual(self.manifest()['roles']['antigravity']['remote_deadline_at'],190)
        self.assertEqual(self.client.interactions.create.call_count,1)
        self.client.interactions.cancel.assert_called_once_with(id='job-1',timeout=30)

    def test_legacy_deadline_uses_original_submission_and_can_only_shorten(self):
        m = self.manifest()
        m['roles']['antigravity'] = {'status':'RUNNING','interaction_id':'legacy','submitted_at':100}
        team.save(self.run/'manifest.json', m)
        self.client.interactions.get.return_value = SimpleNamespace(status='in_progress')
        self.assertEqual(team.execute(self.run,'antigravity',self.client,wait_seconds=0,
                                     wall_clock=lambda:120,remote_max_seconds=90), 'RUNNING')
        self.assertEqual(self.manifest()['roles']['antigravity']['remote_deadline_at'],190)
        self.assertEqual(team.execute(self.run,'antigravity',self.client,wait_seconds=0,
                                     wall_clock=lambda:130,remote_max_seconds=300), 'RUNNING')
        self.assertEqual(self.manifest()['roles']['antigravity']['remote_deadline_at'],190)
        self.assertEqual(team.execute(self.run,'antigravity',self.client,wait_seconds=0,
                                     wall_clock=lambda:140,remote_max_seconds=60), 'RUNNING')
        self.assertEqual(self.manifest()['roles']['antigravity']['remote_deadline_at'],160)
        self.client.interactions.create.assert_not_called()

    def pending(self, state='CANCEL_REQUESTED', deadline=190):
        m=self.manifest()
        m['roles']['antigravity']={'status':state,'interaction_id':'job-1','submitted_at':100,
                                  'remote_max_seconds':90,'remote_deadline_at':deadline}
        team.save(self.run/'manifest.json',m)

    def test_cancel_requested_state_is_not_lost_or_resent_on_poll(self):
        self.pending()
        self.client.interactions.get.return_value=SimpleNamespace(status='in_progress')
        self.assertEqual(team.execute(self.run,'antigravity',self.client,wait_seconds=0,
                                     wall_clock=lambda:200),'CANCEL_REQUESTED')
        self.client.interactions.cancel.assert_not_called()
        self.client.interactions.create.assert_not_called()
        self.assertEqual(self.manifest()['roles']['antigravity']['status'],'CANCEL_REQUESTED')

    def test_cancel_requested_survives_poll_transport_failure(self):
        self.pending()
        self.client.interactions.get.side_effect=RuntimeError('DO_NOT_LOG')
        with self.assertRaises(team.ProviderFailure):
            team.execute(self.run,'antigravity',self.client,wait_seconds=0,retries=0,wall_clock=lambda:130)
        self.assertEqual(self.manifest()['roles']['antigravity']['status'],'CANCEL_REQUESTED')
        self.assertNotIn('DO_NOT_LOG',(self.run/'manifest.json').read_text())

    def test_unknown_remote_status_keeps_same_id_pending_and_redacts_status(self):
        self.pending('RUNNING')
        self.client.interactions.get.return_value=SimpleNamespace(status='PRIVATE_UPPERCASE_TOKEN')
        self.assertEqual(team.execute(self.run,'antigravity',self.client,wait_seconds=0,
                                     wall_clock=lambda:130),'RUNNING')
        m=self.manifest()['roles']['antigravity']
        self.assertEqual(m['interaction_id'],'job-1')
        self.assertEqual(m['remote_status'],'UNKNOWN')
        self.assertNotIn('PRIVATE_UPPERCASE_TOKEN',json.dumps(m))
        self.client.interactions.create.assert_not_called()

    def test_diagnostic_status_has_true_allowlist(self):
        for state in ('PRIVATE_UPPERCASE_TOKEN', None):
            exc=type('ProviderError',(Exception,),{'code':503,'status':state})()
            self.assertIsNone(team.safe_diagnostic(exc)['api_status'])
        exc=type('ProviderError',(Exception,),{'code':503,'status':'UNAVAILABLE'})()
        self.assertEqual(team.safe_diagnostic(exc)['api_status'],'UNAVAILABLE')

    def test_diagnostic_unhashable_or_arbitrary_status_is_never_logged(self):
        for state in (['PRIVATE_TOKEN'], {'PRIVATE_TOKEN':'value'}, 'CUSTOM_SECRET_STATUS'):
            with self.subTest(status_type=type(state).__name__):
                exc=type('ProviderError',(Exception,),{'code':503,'status':state})()
                report=team.safe_diagnostic(exc)
                self.assertIsNone(report['api_status'])
                self.assertNotIn('PRIVATE_TOKEN',json.dumps(report))
                self.assertNotIn('CUSTOM_SECRET_STATUS',json.dumps(report))

    def test_completed_remote_without_valid_output_is_terminal_incomplete(self):
        self.client.interactions.create.return_value=SimpleNamespace(
            id='finished-job',status='completed',output_text='',text='',outputs=[])
        with self.assertRaises(team.ProviderFailure):
            team.execute(self.run,'antigravity',self.client,wait_seconds=0)
        record=self.manifest()['roles']['antigravity']
        self.assertEqual(record['status'],'INCOMPLETE')
        self.assertEqual(record['remote_status'],'completed')
        self.assertEqual(record['interaction_id'],'finished-job')
        self.assertEqual(team.execute(self.run,'antigravity',self.client,wait_seconds=0),'INCOMPLETE')
        self.client.interactions.create.assert_called_once()
        self.client.interactions.get.assert_not_called()

    def test_current_configured_key_is_rejected_even_without_known_prefix(self):
        with patch.dict(os.environ,{'CODING_TEAM_GOOGLE_API_KEY':'unusual-fixture-key-123'}):
            with self.assertRaises(ValueError):
                team.reject_secrets('Provider echoed unusual-fixture-key-123 into a comment')
            team.reject_secrets('No credential here')

    def test_explicit_probe_executor_change_is_rejected_but_omission_resumes(self):
        path=Path(self.temp.name)/'static'
        team.prepare_probe(path,executor='local-static')
        self.assertEqual(team.main(['probe','--run-dir',str(path),'--role','antigravity']),0)
        with self.assertRaises(ValueError):
            team.main(['probe','--run-dir',str(path),'--role','antigravity','--executor','remote'])
        self.assertFalse((path/'.controller.lock').exists())

    def test_cli_lock_blocks_a_second_process_and_is_released_normally(self):
        helper="""import importlib.util,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('locked_team',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
try:
 with m.run_lock(Path(sys.argv[2])): pass
except ValueError: sys.exit(7)
sys.exit(0)
"""
        with team.run_lock(self.run):
            result=subprocess.run([sys.executable,'-X','utf8','-c',helper,str(Path(team.__file__).resolve()),str(self.run)],
                                  capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,7,result.stderr)
            self.assertTrue((self.run/'.controller.lock').exists())
        self.assertFalse((self.run/'.controller.lock').exists())
        with team.run_lock(self.run): pass

    def cli_client(self):
        self.client.__enter__=Mock(return_value=self.client)
        self.client.__exit__=Mock(return_value=False)
        return self.client

    def test_cli_poll_failure_returns_pending_with_or_without_partial(self):
        for state in ('RUNNING','CANCEL_REQUESTED'):
            for partial in (False,True):
                with self.subTest(state=state,allow_partial=partial):
                    self.pending(state)
                    self.client.interactions.get.side_effect=RuntimeError('PRIVATE_FAILURE_TEXT')
                    args=['run','--run-dir',str(self.run),'--role','antigravity','--wait-seconds','0','--retries','0']
                    if partial: args.append('--allow-partial')
                    output=io.StringIO()
                    with patch.dict(os.environ,{'CODING_TEAM_GOOGLE_API_KEY':'fake-state-test-key'}), patch('google.genai.Client',return_value=self.cli_client()), patch('sys.stdout',output):
                        self.assertEqual(team.main(args),2)
                    self.assertIn('Poll SAME job',output.getvalue())
                    self.assertNotIn('PRIVATE_FAILURE_TEXT',output.getvalue())
                    self.assertEqual(self.manifest()['roles']['antigravity']['status'],state)
                    self.client.interactions.create.assert_not_called()
                    self.assertFalse((self.run/'.controller.lock').exists())

    def test_cli_deadline_cancel_failure_is_still_pending_not_terminal(self):
        self.pending('RUNNING')
        self.client.interactions.get.return_value=SimpleNamespace(status='in_progress')
        self.client.interactions.cancel.side_effect=RuntimeError('PRIVATE_CANCEL_FAILURE')
        with patch.dict(os.environ,{'CODING_TEAM_GOOGLE_API_KEY':'fake-state-test-key'}), patch('google.genai.Client',return_value=self.cli_client()), patch('sys.stdout',io.StringIO()):
            self.assertEqual(team.main(['run','--run-dir',str(self.run),'--role','antigravity','--wait-seconds','0','--retries','0']),2)
        self.assertEqual(self.manifest()['roles']['antigravity']['status'],'RUNNING')
        self.client.interactions.create.assert_not_called()
        self.client.interactions.cancel.assert_called_once_with(id='job-1',timeout=30)

    def test_cli_terminal_bad_output_returns_failure_not_pending(self):
        self.client.interactions.create.return_value=SimpleNamespace(id='complete-empty',status='completed',output_text='',text='',outputs=[])
        with patch.dict(os.environ,{'CODING_TEAM_GOOGLE_API_KEY':'fake-state-test-key'}), patch('google.genai.Client',return_value=self.cli_client()), patch('sys.stdout',io.StringIO()):
            self.assertEqual(team.main(['run','--run-dir',str(self.run),'--role','antigravity','--wait-seconds','0','--retries','0','--allow-partial']),1)
        self.assertEqual(self.manifest()['roles']['antigravity']['status'],'INCOMPLETE')
        self.client.interactions.create.assert_called_once()

    def test_cli_explicit_cancel_timeout_retains_pending_id_and_exit_two(self):
        self.pending('RUNNING')
        self.client.interactions.cancel.side_effect=RuntimeError('PRIVATE_CANCEL_FAILURE')
        output=io.StringIO()
        with patch.dict(os.environ,{'CODING_TEAM_GOOGLE_API_KEY':'fake-state-test-key'}), patch('google.genai.Client',return_value=self.cli_client()), patch('sys.stdout',output):
            self.assertEqual(team.main(['cancel','--run-dir',str(self.run)]),2)
        record=self.manifest()['roles']['antigravity']
        self.assertEqual((record['status'],record['interaction_id']),('CANCEL_REQUESTED','job-1'))
        self.assertIn('Poll SAME job ID',output.getvalue())
        self.assertNotIn('PRIVATE_CANCEL_FAILURE',output.getvalue())
        self.assertNotIn('PRIVATE_CANCEL_FAILURE',json.dumps(record))
        self.client.interactions.create.assert_not_called()

    def test_stale_lock_is_not_removed_automatically(self):
        lock=self.run/'.controller.lock'
        lock.write_text('{"pid":999999999}',encoding='utf8')
        with self.assertRaises(ValueError):
            with team.run_lock(self.run): pass
        self.assertTrue(lock.exists())


if __name__=='__main__': unittest.main()
