"""Synthetic end-to-end transport/checkpoint tests; never call an actual model."""
import json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).parent))
import protocol as p
import run as runner

class FakeWorker:
    asks=[]
    failure=None
    def __init__(self,*args,**kwargs):self.meta={'kind':'ready','pins':{'model':'fixture'},'environment':{'fixture':True}}
    def close(self):pass
    def ask(self,job,timeout):
        self.asks.append(job)
        if self.failure:
            failure=self.failure;FakeWorker.failure=None;raise failure
        return {'kind':'answer','status':'OK','elapsed_ms':5,'response':{
            'status':'SUFFICIENT','answer':'SYNTHETIC TEST ONLY',
            'citations':[],'trace':{'events':[{'event':'selection','evidence_ids':['u']}],
                'retrieval_candidates':[{'unit_id':'u'}],'retrieval_rounds':int(job['arm']=='graph_on')}}}

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.settings_path=self.root/'settings.json';p.write(self.settings_path,{})
        self.settings=p.settings(self.settings_path);FakeWorker.asks=[];FakeWorker.failure=None
        p.append(self.root/'inference.jsonl',dict(id='q',question='Synthetic test',query_date='2026-09-15'))
        p.append(self.root/'gold.jsonl',dict(id='q',question='Synthetic test',query_date='2026-09-15',
            reference_answer='SYNTHETIC DRAFT',support=[],group='cross_reference',required_groups=[['u']],expected_tasks=[{'task_id':'t1'}],graph_support={'direct_reference_count':1}))
        p.append(self.root/'corpus.jsonl',dict(unit_id='u',source_text='Synthetic',valid_from='2021-01-01'))
        manifest={'label_status':'DRAFT','outputs_sha256':{n:p.sha(self.root/n) for n in ('inference.jsonl','gold.jsonl','corpus.jsonl')}}
        p.write(self.root/'manifest.json',manifest)
        self.state={'artifact_hashes':{},'all_artifact_files_sha256':{}}
        self.patch1=patch.object(runner,'setup',return_value=(manifest,self.state,{}));self.patch1.start()
        self.patch2=patch.object(runner,'Worker',FakeWorker);self.patch2.start()
        p.write(self.root/'preflight.json',{'settings':self.settings,'code_sha256':p.code_hashes(),'runtime':FakeWorker().meta})
        self.args=SimpleNamespace(run=str(self.root),settings=str(self.settings_path),profile='standard',dry_run=False,retry_errors=False)
    def tearDown(self):self.patch1.stop();self.patch2.stop();self.tmp.cleanup()
    def test_paired_execution_resume_reports_no_repeat(self):
        runner.execute(self.args);self.assertEqual(len(FakeWorker.asks),2)
        runner.execute(self.args);self.assertEqual(len(FakeWorker.asks),2)
        report=p.load(self.root/'comparison.json');self.assertEqual(report['execution_status'],'COMPLETE')
        self.assertEqual(report['successful_pairs'],1)
        self.assertTrue((self.root/'paired_questions.md').exists())
        self.assertTrue((self.root/'human_review.csv').exists())
        records=p.rows(self.root/'responses.jsonl')
        self.assertTrue(all(set(k for k in FakeWorker.asks[0])=={'id','arm','repeat','question','query_date'} for _ in [1]))
        self.assertTrue(all('response' in r for r in records))
    def test_hard_timeout_stops_and_keeps_cost_after_explicit_retry(self):
        FakeWorker.failure=TimeoutError('fixture')
        with self.assertRaises(RuntimeError):runner.execute(self.args)
        self.assertEqual(len(FakeWorker.asks),1)
        self.assertEqual(p.rows(self.root/'responses.jsonl')[0]['status'],'TIMEOUT')
        self.args.retry_errors=True;runner.execute(self.args)
        summary=p.load(self.root/'attempt_history_summary.json')
        self.assertEqual(summary['total_generation_attempts'],3);self.assertEqual(summary['total_execution_errors'],1)
        self.assertEqual(summary['retry_attempts'],1)
    def test_report_refuses_modified_gold(self):
        runner.execute(self.args);(self.root/'gold.jsonl').write_text('{}\n')
        with self.assertRaises(ValueError):runner.make_report(self.root)
    def test_stale_preflight_rejected(self):
        pf=p.load(self.root/'preflight.json');pf['code_sha256']={};p.write(self.root/'preflight.json',pf)
        with self.assertRaises(ValueError):runner.execute(self.args)
        self.assertEqual(FakeWorker.asks,[])

    def test_judge_failure_stops_without_losing_answers_or_exposing_error(self):
        runner.execute(self.args)
        provider=Mock();provider.structured.side_effect=RuntimeError('SYNTHETIC_PRIVATE_ERROR')
        with patch('vn_labor_online.providers.GeminiProvider',return_value=provider):
            with self.assertRaises(RuntimeError):runner.judge(self.args)
        self.assertEqual(provider.structured.call_count,1)
        records=p.rows(self.root/'responses.jsonl');self.assertEqual(len(records),2)
        self.assertTrue(all(r['response']['answer']=='SYNTHETIC TEST ONLY' for r in records))
        self.assertNotIn('SYNTHETIC_PRIVATE_ERROR',json.dumps(records))
    def test_judge_separate_then_resume_does_not_rejudge(self):
        runner.execute(self.args)
        provider=Mock();provider.structured.return_value=dict(correctness=1.,completeness=1.,evidence_support=1.,notes='SYNTHETIC ONLY',tasks=[dict(task_id='t1',addressed=True,evidence_supported=True)])
        with patch('vn_labor_online.providers.GeminiProvider',return_value=provider),patch.object(runner.time,'sleep'):
            runner.judge(self.args);runner.judge(self.args)
        self.assertEqual(provider.structured.call_count,2)
        runner.execute(self.args)
        self.assertTrue(all(r['judge']['status']=='AI_JUDGED' for r in p.rows(self.root/'responses.jsonl')))

if __name__=='__main__':unittest.main()
