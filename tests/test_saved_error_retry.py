"""Bounded retry policy tests; all child processes and model calls are fake."""
import json,sys,tempfile,unittest,contextlib,io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'đo'))
import retry_failed as r

class SavedErrorRetryTests(unittest.TestCase):
    def result(self,code=2):return SimpleNamespace(returncode=code)
    def record(self,id,code=None):
        return {'id':id,'method':'full','repeat':1,'question':'Synthetic question',
                'status':'ERROR' if code else 'OK','error':{'error_code':code} if code else None,
                'elapsed_ms':10,'metrics':{},'result':{'claims':[]}}
    def save(self,root,records,paused=None):
        (root/'responses.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in records),encoding='utf-8')
        r.dump(root/'progress.json',{'expected':len(records),'saved':len(records),'paused':paused})

    def test_only_transient_errors_are_retried_and_first_pass_is_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);records=[self.record('good'),self.record('retry','GEMINI_HTTP_503'),self.record('manual','SYNTHETIC_PERMANENT')]
            self.save(root,records);first=(root/'responses.jsonl').read_bytes()
            def invoke(args):
                self.assertIn('--resume',args);self.assertIn('--retry-errors',args)
                codes=args[args.index('--retry-error-codes')+1:]
                self.assertNotIn('GEMINI_HTTP_429',codes)
                with (root/'attempt_history.jsonl').open('a') as f:f.write(json.dumps(records[1])+'\n')
                records[1]=self.record('retry');self.save(root,records)
                return self.result()
            callback=Mock(side_effect=invoke)
            with contextlib.redirect_stdout(io.StringIO()):r.retry_failed(root,['python','run'],callback,self.result(),max_rounds=2,backoff_seconds=0)
            self.assertEqual(callback.call_count,1)
            self.assertEqual((root/'first_pass_generation.jsonl').read_bytes(),first)
            self.assertEqual([x['id'] for x in r.read(root/'failed_questions.json')],['manual'])
            self.assertEqual(r.read(root/'retry_costs.json')['total_generation_ms'],40)

    def test_retry_round_cap_persists_across_repeated_notebook_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.save(root,[self.record('r','GEMINI_HTTP_503')])
            invoke=Mock(return_value=self.result())
            with contextlib.redirect_stdout(io.StringIO()):
                for _ in range(2):r.retry_failed(root,['python','run'],invoke,self.result(),max_rounds=2,backoff_seconds=0)
            self.assertEqual(invoke.call_count,2)
            self.assertEqual(r.read(root/'generation_retry_state.json')['stop_reason'],'RETRY_LIMIT')

    def test_paused_and_quota_runs_never_retry(self):
        for paused,code in [('BATCH_LIMIT','GEMINI_HTTP_503'),('UPSTREAM_CAPACITY_OR_CONFIGURATION','GEMINI_HTTP_429'),(None,'GEMINI_HTTP_400')]:
            with self.subTest(paused=paused,code=code),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.save(root,[self.record('r',code)],paused)
                invoke=Mock();r.retry_failed(root,['python','run'],invoke,self.result(),backoff_seconds=0)
                invoke.assert_not_called();self.assertEqual(len(r.read(root/'failed_questions.json')),1)

    def test_valid_refusals_and_na_are_not_errors_to_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);records=[self.record('clarify'),self.record('abstain')]
            records[0]['result']['answer_status']='NEED_MORE_FACTS';records[1]['status']='N/A'
            self.save(root,records);invoke=Mock()
            r.retry_failed(root,['python','run'],invoke,self.result(),backoff_seconds=0)
            invoke.assert_not_called();self.assertEqual(r.read(root/'failed_questions.json'),[])

    def test_ollama_timeout_requires_owned_restart_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.save(root,[self.record('r','OLLAMA_TIMEOUT')]);invoke=Mock()
            r.retry_failed(root,['python','run'],invoke,self.result(),backoff_seconds=0)
            invoke.assert_not_called()
            self.assertEqual(r.read(root/'generation_retry_state.json')['stop_reason'],'OWNED_OLLAMA_RESTART_REQUIRED')

    def test_failed_restart_does_not_submit_another_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.save(root,[self.record('r','OLLAMA_TIMEOUT')]);invoke=Mock()
            with contextlib.redirect_stdout(io.StringIO()):
                r.retry_failed(root,['python','run'],invoke,self.result(),backoff_seconds=0,before_retry=Mock(side_effect=RuntimeError('synthetic')))
            invoke.assert_not_called()

    def test_judge_retry_archives_failed_score_and_keeps_completed_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);records=[self.record('scored'),self.record('retry')]
            records[0]['judge']={'status':'AI_JUDGED','correctness':.7}
            records[1]['judge']={'status':'ERROR','error':{'error_code':'GEMINI_HTTP_503'}}
            self.save(root,records);r.dump(root/'judge_progress.json',{'paused':None,'pending_saved_answers':1})
            def invoke(args):
                self.assertNotIn('--retry-errors',args)
                records[1]['judge']={'status':'AI_JUDGED','correctness':.5}
                self.save(root,records);r.dump(root/'judge_progress.json',{'paused':None,'pending_saved_answers':0})
                return self.result(0)
            with contextlib.redirect_stdout(io.StringIO()):r.retry_failed(root,['python','judge'],invoke,self.result(),stage='judge',backoff_seconds=0)
            self.assertEqual(r.rows(root/'responses.jsonl')[0]['judge']['correctness'],.7)
            self.assertEqual(len(r.rows(root/'judge_attempt_history.jsonl')),1)
            self.assertEqual(r.read(root/'failed_judgments.json'),[])

    def test_no_server_owned_means_no_process_is_killed(self):
        with patch.object(r.subprocess,'Popen') as create:
            with self.assertRaises(RuntimeError):r.restart_owned_ollama({},[{'error':{'error_code':'OLLAMA_TIMEOUT'}}])
            create.assert_not_called()

    def test_fatal_child_exit_stops_without_an_infinite_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.save(root,[self.record('r','GEMINI_HTTP_503')]);invoke=Mock(return_value=self.result(1))
            with contextlib.redirect_stdout(io.StringIO()):r.retry_failed(root,['python','run'],invoke,self.result(),backoff_seconds=0)
            self.assertEqual(invoke.call_count,1)
            self.assertEqual(r.read(root/'generation_retry_state.json')['stop_reason'],'FATAL_EXIT')

    def test_lock_prevents_overlapping_controllers_and_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.save(root,[self.record('r','GEMINI_HTTP_503')])
            lock=root/'.retry_controller.lock';lock.write_text('ANOTHER_OWNER')
            with self.assertRaises(RuntimeError):r.retry_failed(root,['python','run'],Mock(),self.result(),backoff_seconds=0)
            self.assertEqual(lock.read_text(),'ANOTHER_OWNER')

    def test_owned_server_is_restarted_and_warmed_before_retry(self):
        process=Mock();process.poll.return_value=None
        new=Mock();new.poll.return_value=None
        log=Mock();log.closed=False;scope={'OWN_OLLAMA':process,'OLLAMA_LOG':log}
        tags=MagicMock();tags.__enter__.return_value=io.StringIO('{}')
        response=MagicMock();response.__enter__.return_value=io.StringIO(json.dumps({'done':True,'message':{'content':'{"ready":true}'}}))
        with patch.object(r.subprocess,'Popen',return_value=new) as create,patch.object(r.urllib.request,'urlopen',side_effect=[tags,response]) as request:
            r.restart_owned_ollama(scope,[{'error':{'error_code':'OLLAMA_TIMEOUT'}}])
        process.terminate.assert_called_once();self.assertIs(scope['OWN_OLLAMA'],new)
        self.assertEqual(create.call_args.kwargs['env']['CUDA_VISIBLE_DEVICES'],'1')
        self.assertEqual(request.call_count,2)

    def test_policy_change_cannot_reset_retry_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.save(root,[self.record('r','GEMINI_HTTP_503')])
            r.retry_failed(root,['python','run'],Mock(),self.result(),max_rounds=0,backoff_seconds=0)
            with self.assertRaises(ValueError):r.retry_failed(root,['python','run'],Mock(),self.result(),max_rounds=2,backoff_seconds=0)

class SelectiveRunnerTests(unittest.TestCase):
    def fixture(self,root):
        import eval_core as e
        from test_evaluation import fixture_bundle
        q,_=fixture_bundle(root/'bundle')
        e.write_rows(root/'bundle/questions.jsonl',[q,{**q,'id':'q2'}])
        m=e.read(root/'bundle/manifest.json');m['questions_sha256']=e.sha(root/'bundle/questions.jsonl');e.dump(root/'bundle/manifest.json',m)
        e.dump(root/'settings.json',{'cache':str(root/'cache'),'embedding_identity':'FROM_BUNDLE'})
        return e

    def test_runner_retries_selected_error_only_and_keeps_other_error(self):
        from vn_labor_online.errors import LLMProviderError
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e=self.fixture(root)
            args=e.base_parser('synthetic').parse_args(['run','--bundle',str(root/'bundle'),'--config',str(root/'settings.json'),
                '--out',str(root/'run'),'--methods','bm25','--allow-draft'])
            adapter=Mock();adapter.prepare.return_value={}
            # The first two attempts fail, in deterministic question order.
            adapter.run.side_effect=[LLMProviderError(safe_code='OLLAMA_TIMEOUT'),ValueError('synthetic permanent error')]
            env={'platform':'fixture','machine':'','processor':'','cpu_count':1,'gpu':None,'hardware_id':None,'packages':{}}
            with patch('adapters.resolved_settings',return_value={}),patch('adapters.create',return_value=adapter),patch('eval_core.environment',return_value=env),patch('eval_core.plot_table'),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(e.execute(args),2)
                initial=e.rows(root/'run/responses.jsonl');bad=next(x for x in initial if x['error']['error_type']=='ValueError')
                args.resume=True;args.retry_errors=True;args.retry_error_codes=['OLLAMA_TIMEOUT']
                adapter.run.side_effect=None;adapter.run.return_value={'retrieved_ids':['u1'],'llm_calls':0}
                self.assertEqual(e.execute(args),2)
                final=e.rows(root/'run/responses.jsonl')
                self.assertEqual(next(x for x in final if x['id']==bad['id']),bad)
                self.assertEqual(sum(x['status']=='OK' for x in final),1)
                self.assertEqual(adapter.run.call_count,3)
                self.assertEqual(len(e.rows(root/'run/attempt_history.jsonl')),1)

    def test_judge_filter_keeps_unselected_error_and_completed_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e=self.fixture(root);run=root/'run';run.mkdir()
            e.dump(run/'run_manifest.json',{'task':'qa','source_tree':e.source_tree(),
                'settings':{'bundle_corpus':str(root/'bundle/corpus.jsonl'),'judge':{'provider':'gemini','model':'synthetic'}}})
            records=[{'id':'q1','method':'full','repeat':1,'status':'OK','metrics':{},'result':{'answer':'Synthetic','claims':[],'citations':[]},
                      'judge':{'status':'ERROR','error':{'error_code':code}}} for code in ['GEMINI_HTTP_503','GEMINI_HTTP_400']]
            records[1]['id']='q2';e.write_rows(run/'responses.jsonl',records)
            provider=Mock();provider.structured.return_value={**{k:1. for k in ['correctness','completeness','evidence_support','relevance','temporal_application']},'reason':'Synthetic','task_scores':[]}
            with patch('adapters.reader',return_value=provider),patch('eval_core.report_runs'):
                e.judge_run(run,retry_error_codes=['GEMINI_HTTP_503'])
            after=e.rows(run/'responses.jsonl')
            self.assertEqual(after[1],records[1]);self.assertEqual(after[0]['judge']['status'],'AI_JUDGED')
            self.assertEqual(provider.structured.call_count,1)

if __name__=='__main__':unittest.main()
