import json,threading,time,unittest
from unittest.mock import Mock,patch
from vn_labor_online.demo_progress import ProgressLog,Step,call,execution_snapshot,skip
from vn_labor_online.runtime import request_budget,RequestStopped
from vn_labor_online.models import AnswerResponse,Trace,Route,Stop
from vn_labor_online.config import OnlineConfig

class ProgressJournalTests(unittest.TestCase):
    def test_observation_preserves_result_identity_and_original_exception(self):
        answer={'legal':'unchanged'}
        exc=RuntimeError('private URL?api_key=do-not-show')
        with request_budget(10):
            self.assertIs(call('analysis',lambda:answer,summary=lambda _: {'so_task':1}),answer)
            with self.assertRaises(RuntimeError) as seen:
                call('dense',lambda:(_ for _ in ()).throw(exc))
            self.assertIs(seen.exception,exc)
            steps=execution_snapshot()['steps']
        self.assertEqual([s['status'] for s in steps],['DONE','ERROR'])
        self.assertNotIn('do-not-show',json.dumps(steps))
        self.assertEqual(steps[-1]['output']['loai_loi'],'RuntimeError')

    def test_failed_summary_does_not_change_successful_legal_operation(self):
        with request_budget(10):
            result=call('analysis',lambda:7,summary=lambda _:1/0)
            self.assertEqual(result,7)
            self.assertEqual(execution_snapshot()['steps'][0]['status'],'DONE')

    def test_skip_is_explicit_no_fake_model_invocation(self):
        with request_budget(10):
            skip('dense','Profile đã đủ')
            steps=execution_snapshot()['steps']
        self.assertEqual(steps[0]['status'],'SKIPPED')
        self.assertFalse(any(s['step']=='model_call' for s in steps))

    def test_journal_is_bounded_and_snapshots_are_independent(self):
        log=ProgressLog(limit=2)
        for i in range(3):log.finish(log.begin('bm25'),{'so_nguon':i,'api_key':'secret'})
        snapshot=log.snapshot()
        self.assertEqual(snapshot['dropped'],1);self.assertEqual(len(snapshot['steps']),2)
        self.assertNotIn('api_key',snapshot['steps'][0]['output'])
        snapshot['steps'][0]['output']['so_nguon']=999
        self.assertNotEqual(log.snapshot()['steps'][0]['output']['so_nguon'],999)

    def test_snapshot_running_duration_and_console_safe_metadata(self):
        with patch.dict('os.environ',{'VN_LABOR_DEMO_CONSOLE':'1'}),patch('builtins.print') as printed,request_budget(10):
            stage=Step('bm25');before=execution_snapshot()['steps'][0]['elapsed_ms']
            time.sleep(.002)
            self.assertGreaterEqual(execution_snapshot()['steps'][0]['elapsed_ms'],before)
            stage.finish({'so_nguon':2})
            self.assertEqual(printed.call_count,2)
            self.assertTrue(printed.call_args.args[0].startswith('ONLINE_STEP '))

    def test_provider_records_real_structured_boundary_without_extra_calls(self):
        from vn_labor_online.providers import OllamaProvider
        provider=OllamaProvider();provider._post=Mock(return_value={'message':{'content':'{"ok":true}'}})
        with request_budget(10):
            result=provider.structured('private system','private user',{'type':'object'})
            steps=execution_snapshot()['steps']
        self.assertEqual(result,{'ok':True});provider._post.assert_called_once()
        self.assertEqual(steps[0]['step'],'model_call')
        self.assertIn('Ollama',steps[0]['technology'])
        self.assertNotIn('private',json.dumps(steps))

    def test_contextvars_do_not_mix_concurrent_requests(self):
        barrier=threading.Barrier(2);values={}
        def worker(key):
            with request_budget(10):
                Step('analysis').finish({'request_test':key});barrier.wait(3)
                values[key]=execution_snapshot()['steps']
        threads=[threading.Thread(target=worker,args=(key,)) for key in ('a','b')]
        for t in threads:t.start()
        for t in threads:t.join(5)
        self.assertEqual(values['a'][0]['output']['request_test'],'a')
        self.assertEqual(values['b'][0]['output']['request_test'],'b')

class ProgressApiTests(unittest.TestCase):
    def result(self):
        return AnswerResponse(query_id='q',status=Stop.NEED_MORE_FACTS,answer='Clarify',evidence_status='NOT_RETRIEVED',
            build_id='b',trace_id='t',trace=Trace(trace_id='t',query_id='q',build_id='b',route=Route.STANDARD,route_reason='fixture'))
    def pipeline(self,ask):
        pipe=Mock();pipe.cfg=OnlineConfig(artifact_source='fixture');pipe.ask.side_effect=ask
        return pipe
    def test_live_polling_and_final_response_share_steps_owner_only(self):
        from fastapi.testclient import TestClient
        from vn_labor_online.api import create_app
        entered=threading.Event();release=threading.Event()
        def ask(_):
            running=Step('dense');entered.set()
            if not release.wait(5):raise AssertionError('test blocked')
            running.finish({'so_nguon':3});return self.result()
        pipe=self.pipeline(ask)
        with patch('vn_labor_online.api.OnlinePipeline',return_value=pipe),patch('vn_labor_online.api.load_config'),patch.dict('os.environ',{'VN_LABOR_API_KEY':''}):
            with TestClient(create_app()) as client:
                headers={'X-Client-Session':'a'*64};responses=[]
                thread=threading.Thread(target=lambda:responses.append(client.post('/v1/answer',json={'question':'private user question','message_id':'m'},headers=headers)))
                thread.start()
                try:
                    self.assertTrue(entered.wait(3))
                    snapshot=client.get('/v1/requests/m',headers=headers).json()
                    self.assertEqual(snapshot['steps'][-1]['status'],'RUNNING')
                    self.assertNotIn('private user question',json.dumps(snapshot))
                    self.assertEqual(client.get('/v1/requests/m',headers={'X-Client-Session':'b'*64}).status_code,404)
                finally:release.set();thread.join(5)
                self.assertEqual(responses[0].status_code,200)
                final=responses[0].json()['trace']['execution_steps']
                self.assertEqual(next(e for e in final if e['step']=='dense')['output']['so_nguon'],3)
                self.assertEqual(final[-1]['step'],'response')
                self.assertEqual(client.get('/v1/requests/m',headers=headers).json()['state'],'DONE')

    def test_failure_keeps_step_and_diagnostics_without_raw_provider_message(self):
        from fastapi.testclient import TestClient
        from vn_labor_online.api import create_app
        def ask(_):
            return call('dense',lambda:(_ for _ in ()).throw(RuntimeError('secret=never-return-this')))
        with patch('vn_labor_online.api.OnlinePipeline',return_value=self.pipeline(ask)),patch('vn_labor_online.api.load_config'),patch.dict('os.environ',{'VN_LABOR_API_KEY':''}):
            with TestClient(create_app(),raise_server_exceptions=False) as client:
                headers={'X-Client-Session':'a'*64}
                result=client.post('/v1/answer',json={'question':'Question','message_id':'m'},headers=headers)
                self.assertEqual(result.status_code,500)
                payload=result.json();steps=payload['details']['execution_steps']
                self.assertTrue(any(e['step']=='dense' and e['status']=='ERROR' for e in steps))
                self.assertFalse(any(e['status']=='RUNNING' for e in steps))
                self.assertNotIn('never-return-this',json.dumps(payload))
                self.assertEqual(client.get('/v1/requests/m',headers=headers).json()['state'],'FAILED')

    def test_cancellation_closes_running_steps(self):
        from fastapi.testclient import TestClient
        from vn_labor_online.api import create_app
        def ask(_):
            Step('profile')
            raise RequestStopped('REQUEST_CANCELLED','retrieval')
        with patch('vn_labor_online.api.OnlinePipeline',return_value=self.pipeline(ask)),patch('vn_labor_online.api.load_config'),patch.dict('os.environ',{'VN_LABOR_API_KEY':''}):
            with TestClient(create_app()) as client:
                result=client.post('/v1/answer',json={'question':'Question','message_id':'m'},headers={'X-Client-Session':'a'*64})
                self.assertEqual(result.status_code,409)
                self.assertEqual(next(e for e in result.json()['details']['execution_steps'] if e['step']=='profile')['status'],'CANCELLED')

if __name__=='__main__':unittest.main()
