import json,sys,tempfile,unittest,zipfile,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import protocol as p
import run
import package
class ProtocolTests(unittest.TestCase):
    def test_only_graph_enabled_differs(self):
        pair=p.assert_pair(p.DEFAULTS,'fakeartifact');off=pair['graph_off'];on=pair['graph_on']
        self.assertFalse(off['graph']['enabled']);self.assertTrue(on['graph']['enabled'])
        self.assertEqual(off['retrieval']['exception_context_top_k'],8)
        self.assertTrue(off['retrieval']['profile_fast_path']);self.assertTrue(off['retrieval']['exact_lookup'])
        self.assertTrue(off['retrieval']['case_law_enabled']);self.assertTrue(off['retrieval']['community_enabled'])
        off['graph']['enabled']=True;self.assertEqual(off,on)
    def test_invalid_settings(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'s.json'
            for change in ({'api_key':'notallowed'},{'repetitions':True},{'judge_enabled':True},{'ollama_url':'https://external.invalid/api/chat'}):
                p.write(path,change)
                with self.assertRaises(ValueError):p.settings(path)
    def test_schedule_blind_balanced_reproducible(self):
        inference=[dict(id=str(i),question='q',query_date='2026-09-15') for i in range(24)]
        s={**p.DEFAULTS,'repetitions':2};jobs=p.schedule(inference,s,'standard')
        self.assertEqual(len(jobs),96);self.assertEqual(jobs,p.schedule(inference,s,'standard'))
        self.assertEqual(len(p.schedule(inference,s,'smoke')),16)
        for i in range(0,len(jobs),2):
            self.assertEqual(jobs[i]['id'],jobs[i+1]['id']);self.assertNotEqual(jobs[i]['arm'],jobs[i+1]['arm'])
            self.assertEqual(set(jobs[i]),{'id','arm','repeat','question','query_date'})
        self.assertNotEqual(jobs[0]['arm'],jobs[48]['arm'])
    def test_integrity_and_lock(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'inference.jsonl').write_text('abc')
            p.write(root/'manifest.json',{'outputs_sha256':{'inference.jsonl':p.sha(root/'inference.jsonl')}})
            p.verify_dataset(root)
            with p.Lock(root):
                with self.assertRaises(FileExistsError):
                    with p.Lock(root):pass
            self.assertFalse((root/'.controller.lock').exists())
            (root/'inference.jsonl').write_text('changed')
            with self.assertRaises(ValueError):p.verify_dataset(root)
    def test_quota_and_safe_error(self):
        self.assertTrue(run.quota_error({'trace':[{'error_code':'GEMINI_HTTP_429'}]}))
        self.assertFalse(run.quota_error({'answer':'429'}))
        self.assertNotIn('SECRET',json.dumps(p.safe_error(RuntimeError('SECRET'))))
    def test_worker_real_subprocess_timeout_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);code="import json,sys,time;print(json.dumps({'kind':'ready','pins':{}}),flush=True);sys.stdin.readline();time.sleep(10)"
            worker=run.Worker(root,root/'state',timeout=3,command=[sys.executable,'-u','-c',code])
            with self.assertRaises(TimeoutError):worker.ask(dict(id='x',question='q',query_date='2026-09-15',arm='graph_off'),.1)
            worker.close();self.assertIsNotNone(worker.p.poll())
    def test_worker_real_subprocess_response(self):
        with tempfile.TemporaryDirectory() as d:
            code="import json,sys;print(json.dumps({'kind':'ready','pins':{}}),flush=True);r=json.loads(sys.stdin.readline());print(json.dumps({'kind':'answer','status':'OK','response':{'answer':r['question']}}),flush=True)"
            worker=run.Worker(Path(d),Path(d)/'state',timeout=3,command=[sys.executable,'-u','-c',code])
            result=worker.ask(dict(id='x',question='q',query_date='2026-09-15',arm='graph_on'),3)
            self.assertEqual(result['response']['answer'],'q');worker.close()
    def test_worker_safe_init_failure(self):
        with tempfile.TemporaryDirectory() as d:
            code="import json;print(json.dumps({'kind':'fatal','error':{'code':'OLLAMA_TIMEOUT'}}),flush=True)"
            with self.assertRaises(RuntimeError):run.Worker(Path(d),Path(d)/'state',timeout=3,command=[sys.executable,'-u','-c',code])
            self.assertEqual(p.load(Path(d)/'preflight_error.json')['error']['code'],'OLLAMA_TIMEOUT')
    def test_package_secret_exclusion(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name,content in {'src/pkg/a.py':'x=1','config/x.yaml':'x:1','benchmarks/graph_qa/run.py':'pass','benchmarks/graph_qa/.env':'SECRET','pyproject.toml':'[project]'}.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
            output=root/'bundle.zip';package.build(output,root)
            with zipfile.ZipFile(output) as z:
                manifest=json.loads(z.read('package_manifest.json'))
                self.assertEqual(set(z.namelist()),set(manifest['files'])|{'package_manifest.json'})
                self.assertFalse(any('.env' in n for n in z.namelist()))
                for name,digest in manifest['files'].items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),digest)
    def test_export_partial(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);rp=root/'run';rp.mkdir();(rp/'responses.jsonl').write_text('partial')
            args=type('Args',(),{'run':str(rp),'output':str(root/'results.zip')});run.export(args)
            with zipfile.ZipFile(args.output) as z:self.assertIn('responses.jsonl',z.namelist())
            self.assertTrue((root/'results.zip.sha256').exists())

    def test_journal_recovers_completed_and_preserves_judge(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);base=dict(id='x',arm='graph_off',repeat=1,status='OK',elapsed_ms=1,response={'answer':'x'})
            p.append(root/'attempt_journal.jsonl',{**base,'status':'ERROR','error':{'code':'OLD'}})
            p.append(root/'attempt_journal.jsonl',base)
            self.assertEqual(run.recover_records(root),[base])
            enriched={**base,'judge':{'status':'AI_JUDGED','correctness':1}}
            run.save_records(root,[enriched]);self.assertEqual(run.recover_records(root),[enriched])
    def test_freeze_resume_preserves_runtime_and_rejects_changed_config(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'manifest.json').write_text('{}')
            p.append(root/'inference.jsonl',dict(id='q',question='q',query_date='2026-09-15'))
            state={'artifact_hashes':{},'all_artifact_files_sha256':{}}
            with patch.object(run,'setup',return_value=({'label_status':'DRAFT'},state,{})):
                first,jobs=run.freeze_run(root,p.DEFAULTS,'standard')
                first['runtime']={'pins':{'digest':'abc'},'environment':{}};p.write(root/'run_manifest.json',first)
                second,_=run.freeze_run(root,p.DEFAULTS,'standard');self.assertEqual(second['runtime'],first['runtime'])
                with self.assertRaises(ValueError):run.freeze_run(root,{**p.DEFAULTS,'seed':9},'standard')

if __name__=='__main__':unittest.main()
