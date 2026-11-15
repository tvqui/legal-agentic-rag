"""Synthetic tests: no API, Kaggle service, package install or model download."""
import argparse,ast,contextlib,io,json,os,tempfile,unittest
from pathlib import Path
from types import ModuleType,SimpleNamespace
from unittest.mock import Mock,patch
import eval_core as e
import test_evaluation as fixtures

NB=Path(__file__).with_name('Kaggle_Ablation_Evaluation.ipynb')

def cells():return json.loads(NB.read_text(encoding='utf8'))['cells']

def notebook_scope():
    scope={};exec(compile(''.join(cells()[1]['source']),'<config>','exec'),scope)
    scope.update(os=os,subprocess=Mock(),PYTHON='synthetic-python')
    display=ModuleType('IPython.display');display.display=Mock();display.FileLink=str
    source=next(''.join(c['source']) for c in cells() if c['cell_type']=='code' and 'def model_environment' in ''.join(c['source']))
    with patch.dict('sys.modules',{'IPython.display':display}):exec(compile(source,'<helpers>','exec'),scope)
    return scope

class AblationNotebookTests(unittest.TestCase):
    def test_cells_parse_and_configurations_are_separate(self):
        content=cells();source=[''.join(c['source']) for c in content if c['cell_type']=='code']
        for s in source:ast.parse(s)
        expected={'full','without_graph','without_reranker','without_auditor','without_review'}
        self.assertEqual({s.split("'")[1] for s in source if s.startswith('run_configuration(')},expected)
        self.assertEqual({s.split("'")[1] for s in source if s.startswith('judge_configuration(')},expected)
        scope=notebook_scope();self.assertEqual(scope['RUN_CONFIGURATIONS'],['full']);self.assertEqual(scope['JUDGE_CONFIGURATIONS'],[])
        self.assertEqual(scope['BACKEND_GEMINI_MODEL'],'gemini-3.1-flash-lite')
        self.assertEqual(scope['JUDGE_GEMINI_MODEL'],'gemini-3.5-flash-lite')
    def test_checkpoint_restore_rejects_paths_outside_output(self):
        import stat
        from unittest.mock import MagicMock
        source=next(''.join(c['source']) for c in cells() if c['cell_type']=='code' and 'if CHECKPOINT_ARCHIVE' in ''.join(c['source']))
        prefix=source.split('OUT.mkdir(parents=True,exist_ok=True)')[0]
        for filename in ['../escape','/absolute','nested'+chr(92)+'escape','C:escape','symlink']:
            with self.subTest(filename=filename),tempfile.TemporaryDirectory() as tmp:
                # Feed original member names: Windows ZipInfo normalizes its
                # separator, whereas the actual Kaggle runtime is Linux.
                out=Path(tmp)/'out';reader=Mock()
                info=SimpleNamespace(filename=filename,file_size=10,external_attr=(stat.S_IFLNK<<16) if filename=='symlink' else 0)
                reader.infolist.return_value=[info]
                archive=MagicMock();archive.__enter__.return_value=reader
                with patch('zipfile.ZipFile',return_value=archive):
                    with self.assertRaises(RuntimeError):exec(compile(prefix,'<restore>','exec'),{'CHECKPOINT_ARCHIVE':'synthetic.zip','OUT':out})
                reader.extractall.assert_not_called();self.assertFalse(out.exists())

    def test_stage_credentials_and_backend_roles_are_scoped_and_restored(self):
        scope=notebook_scope();scope['JUDGE_GEMINI_SECRET_NAME']='GEMINI_API_KEY.2'
        client=Mock();client.get_secret.side_effect=lambda label:'SYNTHETIC_A' if label=='GEMINI_API_KEY' else 'SYNTHETIC_B'
        kaggle=ModuleType('kaggle_secrets');kaggle.UserSecretsClient=Mock(return_value=client)
        with patch.dict('sys.modules',{'kaggle_secrets':kaggle}),patch.dict(os.environ,{'GEMINI_API_KEY':'PREVIOUS','VN_LABOR_RESEARCHER_API_KEY':'STALE_ROLE_KEY'},clear=True):
            for stage,key in [('generation','SYNTHETIC_A'),('judge','SYNTHETIC_B')]:
                with scope['model_environment'](stage):
                    self.assertEqual(os.environ['GEMINI_API_KEY'],key)
                    from vn_labor_online.config import load_config
                    cfg=load_config(Path(__file__).resolve().parents[1]/'config/online_kaggle.yaml')
                    self.assertEqual(cfg.researcher.model,'gemini-3.1-flash-lite')
                    self.assertEqual(cfg.researcher.api_key,key)
                    self.assertEqual(cfg.adjudication.review_model,'gemini-3.1-flash-lite')
                    self.assertEqual(cfg.adjudication.model,'qwen3:8b')
                    self.assertEqual((cfg.applicability.mode,cfg.applicability.provider,cfg.applicability.model),('hybrid','ollama','qwen3:8b'))
                self.assertEqual(dict(os.environ),{'GEMINI_API_KEY':'PREVIOUS','VN_LABOR_RESEARCHER_API_KEY':'STALE_ROLE_KEY'})
    def test_run_all_keeps_ollama_for_later_independent_cells(self):
        scope=notebook_scope();self.assertFalse(scope['CLEANUP_OLLAMA'])
        source=''.join(cells()[-1]['source']);owned=Mock();owned.poll.return_value=None;log=Mock()
        scope.update(OWN_OLLAMA=owned,OLLAMA_LOG=log)
        with contextlib.redirect_stdout(io.StringIO()):exec(compile(source,'<cleanup>','exec'),scope)
        owned.terminate.assert_not_called();log.close.assert_not_called()
        scope['CLEANUP_OLLAMA']=True
        with contextlib.redirect_stdout(io.StringIO()):exec(compile(source,'<cleanup>','exec'),scope)
        owned.terminate.assert_called_once();log.close.assert_called_once()

    def test_unselected_cells_make_no_calls(self):
        scope=notebook_scope()
        with contextlib.redirect_stdout(io.StringIO()):
            scope['run_configuration']('without_graph');scope['judge_configuration']('full')
        scope['subprocess'].run.assert_not_called()
    def test_backend_and_judge_commands_do_not_cross_stages(self):
        scope=notebook_scope()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'out';run=out/'runs/full';run.mkdir(parents=True)
            (run/'run_manifest.json').write_text('{}')
            (run/'responses.jsonl').write_text('')
            scope.update(OUT=out,BUNDLE=out/'bundle120',SETTINGS=out/'settings.json',ROOT=root,
                         model_environment=lambda _:contextlib.nullcontext(),export_checkpoint=Mock())
            scope['subprocess'].run.return_value=SimpleNamespace(returncode=0)
            scope['run_configuration']('full')
            args=scope['subprocess'].run.call_args.args[0]
            self.assertIn('--max-new-questions',args);self.assertIn('--resume',args);self.assertNotIn('--judge',args)
            self.assertNotIn('--limit',args)
            scope['JUDGE_CONFIGURATIONS']=['full'];scope['judge_configuration']('full')
            args=scope['subprocess'].run.call_args.args[0]
            self.assertIn('judge',args);self.assertNotIn('run',args);self.assertIn('--max-new-judgments',args)
            self.assertEqual(scope['export_checkpoint'].call_count,2)

class EvaluationBatchTests(unittest.TestCase):
    def bundle(self,root):
        q,_=fixtures.fixture_bundle(root/'bundle')
        questions=[q,{**q,'id':'q2'}];e.write_rows(root/'bundle/questions.jsonl',questions)
        m=e.read(root/'bundle/manifest.json');m['questions_sha256']=e.sha(root/'bundle/questions.jsonl');e.dump(root/'bundle/manifest.json',m)
    def test_gpu_spec_policy_keeps_uuid_history_but_checks_real_spec(self):
        base={'platform':'Linux','machine':'x86_64','processor':'','cpu_count':4,'hardware_id':None,
              'gpu':'Tesla T4, GPU-original, 15360 MiB, 570.1'}
        other={**base,'gpu':'Tesla T4, GPU-new, 15360 MiB, 570.1'}
        self.assertEqual(e.comparison_hardware(base,'GPU_SPEC'),e.comparison_hardware(other,'GPU_SPEC'))
        self.assertNotEqual(e.comparison_hardware(base),e.comparison_hardware(other))
        changed={**other,'gpu':'Tesla T4, GPU-new, 15360 MiB, 580.1'}
        self.assertNotEqual(e.comparison_hardware(base,'GPU_SPEC'),e.comparison_hardware(changed,'GPU_SPEC'))
        with self.assertRaises(ValueError):e.comparison_hardware({**base,'gpu':None},'GPU_SPEC')
        self.assertIn('GPU-original',base['gpu'])

    def test_batching_preserves_selection_and_resumes_without_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.bundle(p)
            e.dump(p/'settings.json',{'cache':str(p/'cache'),'device':'cpu','candidate_k':30,'embedding_identity':'FROM_BUNDLE'})
            args=e.base_parser('test').parse_args(['run','--bundle',str(p/'bundle'),'--config',str(p/'settings.json'),
                '--out',str(p/'run'),'--methods','bm25','--allow-draft','--max-new-questions','1'])
            adapter=Mock();adapter.prepare.return_value={};adapter.run.return_value={'retrieved_ids':['u1'],'llm_calls':0}
            env={'platform':'fixture','machine':'','processor':'','cpu_count':1,'gpu':None,'hardware_id':None,'packages':{}}
            with patch('adapters.resolved_settings',return_value={}),patch('adapters.create',return_value=adapter),patch('eval_core.environment',return_value=env),patch('eval_core.plot_table'):
                self.assertEqual(e.execute(args),2)
                m=e.read(p/'run/run_manifest.json');self.assertEqual(len(m['selected_ids']),2)
                self.assertEqual(e.read(p/'run/progress.json')['paused'],'BATCH_LIMIT')
                args.resume=True;args.max_new_questions=2
                self.assertEqual(e.execute(args),0);self.assertEqual(adapter.run.call_count,2)
                self.assertEqual(e.execute(args),0);self.assertEqual(adapter.run.call_count,2)
                self.assertEqual(e.read(p/'run/run_manifest.json')['comparison_key'],m['comparison_key'])
    def test_judge_batch_skips_completed_scores_on_next_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.bundle(p);run=p/'run';run.mkdir()
            e.dump(run/'run_manifest.json',{'task':'qa','source_tree':e.source_tree(),
                'settings':{'bundle_corpus':str(p/'bundle/corpus.jsonl'),'judge':{'provider':'gemini','model':'gemini-3.5-flash-lite'}}})
            records=[{'id':qid,'status':'OK','metrics':{},'result':{'answer':'Synthetic','claims':[],'citations':[]}} for qid in ['q1','q2']]
            # fixture question id is q1.
            questions=e.rows(p/'bundle/questions.jsonl');records[0]['id']=questions[0]['id']
            e.write_rows(run/'responses.jsonl',records)
            provider=Mock();provider.structured.return_value={**{k:1. for k in ['correctness','completeness','evidence_support','relevance','temporal_application']},'reason':'Synthetic','task_scores':[]}
            with patch('adapters.reader',return_value=provider),patch('eval_core.report_runs'):
                first=e.judge_run(run,1);self.assertEqual(first['pending_saved_answers'],1)
                second=e.judge_run(run,1);self.assertTrue(second['complete_for_saved_answers'])
                e.judge_run(run,1);self.assertEqual(provider.structured.call_count,2)

if __name__=='__main__':unittest.main()
