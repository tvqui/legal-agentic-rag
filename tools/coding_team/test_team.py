import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import os

# These tests are offline: use a tiny SDK type shim when google-genai is absent.
# The production team.py NEVER uses this shim.
import sys
import types as pytypes
try:
    from google.genai import types as _real_sdk_types
except ImportError:
    google=pytypes.ModuleType('google')
    genai=pytypes.ModuleType('google.genai')
    sdk_types=pytypes.ModuleType('google.genai.types')
    class _Config:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.__dict__.setdefault('temperature',None)
    sdk_types.GenerateContentConfig=_Config
    sdk_types.HttpOptions=_Config
    sdk_types.HttpRetryOptions=_Config
    sdk_types.ThinkingConfig=_Config
    genai.types=sdk_types
    genai.Client=Mock()
    google.genai=genai
    sys.modules.update({'google':google,'google.genai':genai,'google.genai.types':sdk_types})

spec=importlib.util.spec_from_file_location('coding_team',Path(__file__).with_name('team.py'))
team=importlib.util.module_from_spec(spec); spec.loader.exec_module(team)

class CodingTeamTests(unittest.TestCase):
    def setUp(self):
        env_loader=patch.object(team.coding_writer,'load_tool_env');env_loader.start();self.addCleanup(env_loader.stop)
        legacy=patch.dict(team.MODELS,gemma='gemma-4-31b-it');legacy.start();self.addCleanup(legacy.stop)
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'repo'; self.root.mkdir()
        self.run=Path(self.temp.name)/'run'
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        (self.root/'sample.py').write_text('def add(a,b): return a+b\n',encoding='utf-8')
        subprocess.run(['git','add','sample.py'],cwd=self.root,check=True)
        subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                        'commit','-qm','fixture','--no-gpg-sign'],cwd=self.root,check=True)
        self.client=Mock()
        self.client.models.generate_content.return_value=SimpleNamespace(text='Proposed diff; NOT applied.',candidates=[])

    def tearDown(self): self.temp.cleanup()

    def prepare(self): return team.prepare(self.root,self.run,'Review add function',['sample.py'])

    def test_prepare_local_only_and_no_source_mutation(self):
        manifest=self.prepare()
        self.assertIn('sample.py',manifest['files'])
        self.assertEqual(team.execute(self.run,'gemma',self.client),'COMPLETE')
        self.assertEqual((self.root/'sample.py').read_text(),'def add(a,b): return a+b\n')
        self.assertEqual(team.execute(self.run,'gemma',self.client),'COMPLETE')
        self.client.models.generate_content.assert_called_once()
        self.assertIn('proposal writer ONLY',self.client.models.generate_content.call_args.kwargs['config'].system_instruction)

    def test_blocks_secrets_untracked_and_traversal(self):
        (self.root/'.env').write_text('fixture only')
        for name in ('.env','../outside.py','missing.py'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                team.prepare(self.root,self.run,'task',[name])
        with self.assertRaises(ValueError):
            team.prepare(self.root,self.run,'AIza'+'a'*35,['sample.py'])
        self.assertFalse(self.run.exists())

    def test_changed_snapshot_refused(self):
        self.prepare(); (self.run/'snapshot.txt').write_text('modified',encoding='utf-8')
        with self.assertRaises(ValueError): team.execute(self.run,'gemma',self.client)
        self.client.models.generate_content.assert_not_called()

    def test_background_resume_polls_same_job_without_duplicate_post(self):
        self.prepare(); team.execute(self.run,'gemma',self.client)
        self.client.interactions.create.return_value=SimpleNamespace(id='job-1',status='in_progress')
        self.assertEqual(team.execute(self.run,'antigravity',self.client,wait_seconds=0),'RUNNING')
        kwargs=self.client.interactions.create.call_args.kwargs
        self.assertEqual(kwargs['agent'],'antigravity-preview-09-2026')
        self.assertTrue(kwargs['background']); self.assertEqual(kwargs['environment'],'remote')
        self.assertNotIn('generation_config',kwargs)
        self.assertIn('sandbox executor ONLY',kwargs['input'])
        self.assertEqual(kwargs['agent_config']['max_total_tokens'],16000)
        self.client.interactions.get.return_value=SimpleNamespace(status='completed',output_text='Sandbox review and proposed diff')
        self.assertEqual(team.execute(self.run,'antigravity',self.client),'COMPLETE')
        self.client.interactions.create.assert_called_once()
        self.client.interactions.get.assert_called_once_with(id='job-1',timeout=30)
        self.assertEqual(team.execute(self.run,'reviewer',self.client),'COMPLETE')
        payload=self.client.models.generate_content.call_args.kwargs
        self.assertIn('Proposed diff; NOT applied.',payload['contents'])
        self.assertIn('Sandbox review and proposed diff',payload['contents'])
        self.assertIsNone(payload['config'].temperature)
        self.assertEqual(payload['model'],team.MODELS['reviewer'])
        self.assertIn('independent reviewer ONLY',payload['config'].system_instruction)

    def test_error_saved_without_message_and_not_blindly_retried(self):
        self.prepare()
        self.client.models.generate_content.side_effect=RuntimeError('FAKE_PRIVATE_VALUE')
        with self.assertRaises(RuntimeError): team.execute(self.run,'gemma',self.client)
        manifest=(self.run/'manifest.json').read_text(encoding='utf-8')
        self.assertNotIn('FAKE_PRIVATE_VALUE',manifest)
        with self.assertRaises(ValueError): team.execute(self.run,'gemma',self.client)
        self.client.models.generate_content.assert_called_once()

    def test_sdk_status_code_and_safe_diagnostics_are_retained(self):
        self.prepare()
        class Rejected(Exception):
            status_code=400
            status='INVALID_ARGUMENT'
            message='API key not valid. FAKE_PRIVATE_VALUE'
        self.client.models.generate_content.side_effect=Rejected()
        with self.assertRaises(RuntimeError): team.execute(self.run,'gemma',self.client)
        text=(self.run/'manifest.json').read_text(encoding='utf-8')
        record=json.loads(text)['roles']['gemma']
        self.assertEqual(record['http_code'],400)
        self.assertEqual(record['diagnostics']['error_reason'],'API_KEY_REJECTED')
        self.assertNotIn('FAKE_PRIVATE_VALUE',text)

    def test_prior_output_tampering_and_truncation_are_not_accepted(self):
        self.prepare()
        self.client.models.generate_content.return_value=SimpleNamespace(
            text='unfinished',candidates=[SimpleNamespace(finish_reason='MAX_TOKENS')])
        with self.assertRaises(RuntimeError): team.execute(self.run,'gemma',self.client)
        self.assertFalse((self.run/'gemma.md').exists())

    def test_reviewer_cannot_run_without_other_two_results(self):
        self.prepare()
        with self.assertRaises((ValueError,FileNotFoundError)):
            team.execute(self.run,'reviewer',self.client)
        self.client.models.generate_content.assert_not_called()

    def test_size_and_empty_tasks(self):
        for task in ('','a'*3001):
            with self.assertRaises(ValueError): team.prepare(self.root,self.run,task,['sample.py'])
        (self.root/'sample.py').write_text('a'*8001)
        with self.assertRaises(ValueError): self.prepare()

    def test_large_modules_can_be_sent_as_explicit_line_excerpts(self):
        (self.root/'sample.py').write_text('line\n'*2000,encoding='utf-8')
        manifest=team.prepare(self.root,self.run,'Inspect excerpt',['sample.py@100:110'])
        self.assertIn('sample.py@100:110',manifest['files'])
        self.assertEqual((self.run/'snapshot.txt').read_text().count('line\n'),11)

    def test_invalid_line_ranges_and_changed_result_are_rejected(self):
        for name in ('sample.py@2:1','sample.py@1:99'):
            with self.assertRaises(ValueError): team.prepare(self.root,self.run,'task',[name])
        self.prepare(); team.execute(self.run,'gemma',self.client)
        (self.run/'gemma.md').write_text('tampered')
        with self.assertRaises(ValueError): team.execute(self.run,'antigravity',self.client)
        self.client.interactions.create.assert_not_called()

    def test_only_explicit_503_504_are_retried_and_attempts_are_recorded(self):
        self.prepare()
        class Busy(Exception): code=503
        self.client.models.generate_content.side_effect=[Busy(),SimpleNamespace(text='proposal',candidates=[])]
        sleep=Mock()
        self.assertEqual(team.execute(self.run,'gemma',self.client,sleep=sleep),'COMPLETE')
        sleep.assert_called_once()
        self.assertGreaterEqual(sleep.call_args.args[0],5)
        self.assertLessEqual(sleep.call_args.args[0],6)
        self.assertEqual(self.client.models.generate_content.call_count,2)
        record=json.loads((self.run/'manifest.json').read_text())['roles']['gemma']
        self.assertEqual(len(record['attempts']),2)
        self.assertEqual(record['attempts'][0]['http_code'],503)

    def test_429_not_retried_and_agent_post_never_retried(self):
        self.prepare()
        team.execute(self.run,'gemma',self.client)
        class Busy(Exception): code=503
        self.client.interactions.create.side_effect=Busy()
        with self.assertRaises(team.ProviderFailure): team.execute(self.run,'antigravity',self.client,retries=2,sleep=Mock())
        self.client.interactions.create.assert_called_once()
        class Limited(Exception): code=429
        self.client.models.generate_content.side_effect=Limited()
        second=Path(self.temp.name)/'probe'
        team.prepare_probe(second)
        before=self.client.models.generate_content.call_count
        with self.assertRaises(team.ProviderFailure): team.execute(second,'reviewer',self.client,retries=2,sleep=Mock())
        self.assertEqual(self.client.models.generate_content.call_count,before+1)

    def test_remote_cancelled_is_terminal_instead_of_running(self):
        self.prepare(); team.execute(self.run,'gemma',self.client)
        self.client.interactions.create.return_value=SimpleNamespace(id='job-cancelled',status='cancelled')
        self.assertEqual(team.execute(self.run,'antigravity',self.client),'CANCELLED')
        self.assertEqual(team.execute(self.run,'antigravity',self.client),'CANCELLED')
        self.client.interactions.create.assert_called_once()
        self.client.interactions.get.assert_not_called()

    def test_agent_total_wall_limit_survives_process_resume(self):
        self.prepare(); team.execute(self.run,'gemma',self.client)
        self.client.interactions.create.return_value=SimpleNamespace(id='job-old',status='in_progress')
        team.execute(self.run,'antigravity',self.client,wait_seconds=0,wall_clock=lambda:100)
        self.client.interactions.get.return_value=SimpleNamespace(status='in_progress')
        self.client.interactions.cancel.return_value=SimpleNamespace(status='cancelled')
        status=team.execute(self.run,'antigravity',self.client,wait_seconds=0,wall_clock=lambda:200,remote_max_seconds=30)
        self.assertEqual(status,'CANCELLED')
        self.client.interactions.cancel.assert_called_once_with(id='job-old',timeout=30)
        self.client.interactions.create.assert_called_once()

    def test_probe_reviewer_has_no_dependency_on_other_helpers(self):
        team.prepare_probe(self.run)
        self.assertEqual(team.execute(self.run,'reviewer',self.client),'COMPLETE')
        request=self.client.models.generate_content.call_args.kwargs
        self.assertIn('Reply only OK',request['contents'])
        self.assertIsNone(request['config'].system_instruction)
        self.assertEqual(request['config'].max_output_tokens,512)

    def test_partial_review_explicitly_records_missing_helper(self):
        self.prepare(); team.execute(self.run,'gemma',self.client)
        self.assertEqual(team.execute(self.run,'reviewer',self.client,allow_partial=True),'COMPLETE')
        request=self.client.models.generate_content.call_args.kwargs
        self.assertIn('MISSING HELPER: antigravity, status=NOT_RUN',request['contents'])
        record=json.loads((self.run/'manifest.json').read_text())['roles']['reviewer']
        self.assertEqual(record['dependencies']['antigravity'],'NOT_RUN')

    def test_interaction_outputs_text_works_without_output_text_property(self):
        response=SimpleNamespace(outputs=[SimpleNamespace(type='text',text='OK')])
        self.assertEqual(team.response_text(response),'OK')

    def test_probe_budget_covers_observed_harness_and_saves_terminal_usage(self):
        team.prepare_probe(self.run)
        response=SimpleNamespace(id='budget-probe',status='incomplete',
            usage={'total_input_tokens':4748,'total_output_tokens':1,'total_tokens':9000,'private':'not-logged'})
        self.client.interactions.create.return_value=response
        self.assertEqual(team.execute(self.run,'antigravity',self.client),'INCOMPLETE')
        self.assertEqual(self.client.interactions.create.call_args.kwargs['agent_config']['max_total_tokens'],8192)
        record=json.loads((self.run/'manifest.json').read_text())['roles']['antigravity']
        self.assertTrue(record['token_limit_exceeded_observed'])
        self.assertEqual(record['remote_usage']['total_input_tokens'],4748)
        self.assertNotIn('private',record['remote_usage'])

    def test_partial_resume_skips_cached_provider_failure_without_new_post(self):
        self.prepare()
        self.client.models.generate_content.side_effect=RuntimeError('private failure')
        with self.assertRaises(team.ProviderFailure): team.execute(self.run,'gemma',self.client)
        self.assertEqual(team.execute(self.run,'gemma',self.client,allow_partial=True),'ERROR')
        self.client.models.generate_content.assert_called_once()

    def test_cli_partial_failure_continues_reviewer_and_does_not_retry_on_resume(self):
        self.prepare()
        class Busy(Exception): code=503
        self.client.interactions.create.side_effect=Busy()
        self.client.__enter__=Mock(return_value=self.client)
        self.client.__exit__=Mock(return_value=False)
        args=['run','--run-dir',str(self.run),'--role','all','--allow-partial','--retries','0','--wait-seconds','0']
        with patch.dict(os.environ,{'CODING_TEAM_GOOGLE_API_KEY':'fake-test-only'}), \
             patch('google.genai.Client',return_value=self.client):
            self.assertEqual(team.main(args),1)
            self.assertEqual(team.main(args),1)
        self.client.interactions.create.assert_called_once()
        self.assertEqual(self.client.models.generate_content.call_count,2)

    def test_exponential_backoff_and_jitter_have_bounded_attempts(self):
        class Unavailable(Exception): code=503
        operation=Mock(side_effect=[Unavailable(),Unavailable(),'OK'])
        sleep=Mock(); record={}
        self.assertEqual(team.call_with_retry(operation,record,lambda:None,retries=2,sleep=sleep,jitter=lambda:.25),'OK')
        self.assertEqual([c.args[0] for c in sleep.call_args_list],[5.25,10.25])
        self.assertEqual(len(record['attempts']),3)

    def test_deadline_is_explicit_per_request_and_sdk_retry_not_nested(self):
        team.prepare_probe(self.run)
        team.execute(self.run,'reviewer',self.client,call_timeout_seconds=120)
        options=self.client.models.generate_content.call_args.kwargs['config'].http_options
        self.assertEqual(options.timeout,120000)
        self.assertEqual(options.retry_options.attempts,1)
        record=json.loads((self.run/'manifest.json').read_text())['roles']['reviewer']
        self.assertEqual(record['call_timeout_seconds'],120)

    def test_reviewer_selection_is_pinned_and_does_not_change_on_resume(self):
        team.prepare_probe(self.run,reviewer_model='gemini-3.6-flash')
        with patch.dict(os.environ,{'CODING_TEAM_REVIEW_MODEL':'gemini-3.5-flash-lite'}):
            self.assertEqual(team.execute(self.run,'reviewer',self.client),'COMPLETE')
        self.assertEqual(self.client.models.generate_content.call_args.kwargs['model'],'gemini-3.6-flash')
        manifest=json.loads((self.run/'manifest.json').read_text())
        manifest['models']['reviewer']='gemini-3.5-flash-lite'
        (self.run/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError): team.verify(self.run)

    def test_old_gemini38_runs_remain_readable_after_default_model_change(self):
        team.prepare_probe(self.run,reviewer_model='gemini-3.8-flash')
        manifest=json.loads((self.run/'manifest.json').read_text())
        manifest.pop('model_config_sha256')
        (self.run/'manifest.json').write_text(json.dumps(manifest))
        with patch.dict(team.MODELS,reviewer='gemini-3.6-flash'):
            team.execute(self.run,'reviewer',self.client)
        self.assertEqual(self.client.models.generate_content.call_args.kwargs['model'],'gemini-3.8-flash')

    def test_unknown_or_paid_unreviewed_model_is_rejected_before_api_call(self):
        with self.assertRaises(ValueError): team.prepare_probe(self.run,reviewer_model='unreviewed-provider-model')
        self.assertFalse(self.run.exists())

    def test_default_reviewer_uses_working_lite_and_model_specific_thinking(self):
        team.prepare_probe(self.run)
        team.execute(self.run,'reviewer',self.client)
        request=self.client.models.generate_content.call_args.kwargs
        self.assertEqual(request['model'],'gemini-3.5-flash-lite')
        level=request['config'].thinking_config.thinking_level
        self.assertEqual(getattr(level,'value',str(level)).lower(),'minimal')


class ResilienceTests(unittest.TestCase):
    def setUp(self):
        env_loader=patch.object(team.coding_writer,'load_tool_env');env_loader.start();self.addCleanup(env_loader.stop)
        legacy=patch.dict(team.MODELS,gemma='gemma-4-31b-it');legacy.start();self.addCleanup(legacy.stop)
        self.temp=tempfile.TemporaryDirectory()
        self.run=Path(self.temp.name)/'probe'
    def tearDown(self):
        self.temp.cleanup()

    def test_500_502_retry_and_success(self):
        for status in (500,502,503,504,408):
            with self.subTest(status=status):
                class Transient(Exception): pass
                error=Transient(); error.code=status
                operation=Mock(side_effect=[error,'OK'])
                sleeps=Mock()
                record={}
                result=team.call_with_retry(operation,record,lambda:None,retries=1,sleep=sleeps,jitter=lambda:0)
                self.assertEqual(result,'OK')
                self.assertEqual(operation.call_count,2)
                sleeps.assert_called_once_with(5)
                self.assertEqual(record['attempts'][0]['http_code'],status)

    def test_unknown_or_quota_error_not_retried(self):
        for error in (RuntimeError('secret'),type('Quota',(Exception,),{'code':429})()):
            operation=Mock(side_effect=error)
            with self.assertRaises(Exception):
                team.call_with_retry(operation,{},lambda:None,retries=2,sleep=Mock())
            self.assertEqual(operation.call_count,1)

    def test_diagnostic_is_standalone_and_never_leaks_private_value(self):
        error=RuntimeError('PRIVATE_TOKEN')
        self.assertNotIn('PRIVATE_TOKEN',json.dumps(team.safe_diagnostic(error)))
        self.assertEqual(team.safe_diagnostic(type('E',(Exception,),{'code':500})())['error_reason'],
                         'TRANSIENT_SERVER_OR_TIMEOUT')

    def test_local_static_runs_without_network_or_source_execution(self):
        team.prepare_probe(self.run,executor='local-static')
        client=Mock()
        self.assertEqual(team.execute(self.run,'antigravity',None),'COMPLETE')
        client.models.generate_content.assert_not_called()
        record=json.loads((self.run/'manifest.json').read_text())['roles']['antigravity']
        self.assertEqual(record['verification_level'],'STATIC_ONLY')
        self.assertFalse(record['execution_performed'])
        self.assertTrue((self.run/'local_static_report.json').exists())
        self.assertEqual(team.execute(self.run,'antigravity',None),'COMPLETE')

    def test_detect_syntax_errors_without_executing(self):
        snapshot='TASK\ncheck\nEND TASK\n\nFILE bad.py\nraise RuntimeError("DO NOT EXECUTE")\ndef f(:\nEND FILE\n'
        report=team.local_static_report(snapshot)
        self.assertEqual(report['checks'][0]['status'],'SYNTAX_ERROR')
        self.assertFalse(report['execution_performed'])

    def test_local_static_mode_cannot_be_changed_by_manifest_edit(self):
        team.prepare_probe(self.run,executor='local-static')
        manifest=json.loads((self.run/'manifest.json').read_text())
        manifest['execution']['antigravity']='remote'
        (self.run/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            team.verify(self.run)

    def test_writer_alternative_pinned_across_resume(self):
        team.prepare_probe(self.run,writer_model='gemma-4-26b-a4b-it')
        manifest,_=team.verify(self.run)
        self.assertEqual(manifest['models']['gemma'],'gemma-4-26b-a4b-it')
        record=json.loads((self.run/'manifest.json').read_text())
        record['models']['gemma']='gemma-4-31b-it'
        (self.run/'manifest.json').write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            team.verify(self.run)

    def test_cancel_unknown_status_must_not_claim_cancelled(self):
        team.prepare_probe(self.run)
        m=json.loads((self.run/'manifest.json').read_text())
        m['roles']['antigravity']={'status':'RUNNING','interaction_id':'dummy'}
        (self.run/'manifest.json').write_text(json.dumps(m))
        mock=Mock()
        mock.interactions.cancel.return_value=SimpleNamespace(status='in_progress')
        mock.__enter__=Mock(return_value=mock)
        mock.__exit__=Mock(return_value=False)
        with patch.dict(os.environ,{'CODING_TEAM_GOOGLE_API_KEY':'fake-test-only'}),patch('google.genai.Client',return_value=mock):
            self.assertEqual(team.main(['cancel','--run-dir',str(self.run)]),2)
        m=json.loads((self.run/'manifest.json').read_text())
        self.assertEqual(m['roles']['antigravity']['status'],'CANCEL_REQUESTED')

    def test_local_static_cli_runs_without_api_key_or_sdk(self):
        args=['probe','--run-dir',str(self.run),'--role','antigravity','--executor','local-static']
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(team.main(args),0)
        manifest=json.loads((self.run/'manifest.json').read_text())
        self.assertEqual(manifest['execution']['antigravity'],'local-static')


if __name__=='__main__': unittest.main()
