import io,json,logging,socket,threading,time,unittest
from unittest.mock import Mock,patch
from vn_labor_online.demo_progress import ProgressLog,Step,call,execution_snapshot,skip
from vn_labor_online.runtime import request_budget,RequestStopped
from vn_labor_online.models import AnswerResponse,Trace,Route,Stop
from vn_labor_online.config import OnlineConfig
from vn_labor_online.errors import LLMProviderError,IndexUnavailable

class ProgressJournalTests(unittest.TestCase):
    def test_public_error_keeps_only_allowlisted_provider_codes_and_diagnostics(self):
        from vn_labor_online.demo_progress import public_error
        error=LLMProviderError('private provider message',safe_code='GEMINI_HTTP_400',
          safe_diagnostics={'api_status':'INVALID_ARGUMENT','error_reason':'INVALID_ARGUMENT',
            'error_fields':['response_schema','private_field'],'message':'private diagnostic'})
        summary=public_error(error)
        self.assertEqual(summary['ma_loi'],'GEMINI_HTTP_400')
        self.assertEqual(summary['diagnostics']['api_status'],'INVALID_ARGUMENT')
        self.assertEqual(summary['diagnostics']['error_reason'],'INVALID_ARGUMENT')
        self.assertEqual(summary['diagnostics']['error_fields'],['response_schema'])
        self.assertNotIn('private provider message',json.dumps(summary))
        self.assertNotIn('private diagnostic',json.dumps(summary))
        self.assertNotIn('private_field',json.dumps(summary))

    def test_public_error_rejects_untrusted_uppercase_codes_and_diagnostics(self):
        from vn_labor_online.demo_progress import public_error
        error=LLMProviderError('private',safe_code='TOKEN_EXFILTRATION',
          safe_diagnostics={'api_status':'TOKEN_EXFILTRATION','error_reason':'TOKEN_EXFILTRATION'})
        error.reason='PRIVATE_UPPERCASE_REASON'
        summary=public_error(error)
        self.assertNotIn('ma_loi',summary)
        self.assertNotIn('diagnostics',summary)
        self.assertNotIn('reason',summary)

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
    def test_provider_safe_code_is_logged_with_controlled_diagnostics_and_request_id(self):
        from fastapi.testclient import TestClient
        from vn_labor_online.api import create_app
        error=LLMProviderError('private provider response',safe_code='GEMINI_HTTP_400',
          safe_diagnostics={'api_status':'INVALID_ARGUMENT','error_reason':'INVALID_ARGUMENT',
            'message':'private diagnostic'})
        pipe=self.pipeline(Mock(side_effect=error))
        with patch('vn_labor_online.api.OnlinePipeline',return_value=pipe),patch('vn_labor_online.api.load_config'),patch.dict('os.environ',{'VN_LABOR_API_KEY':''}):
            with TestClient(create_app()) as client:
                with self.assertLogs('vn_labor_online.api',level='ERROR') as captured:
                    response=client.post('/v1/answer',json={'question':'Question'})
        logs='\n'.join(captured.output)
        self.assertEqual(response.status_code,503)
        self.assertIn('GEMINI_HTTP_400',logs)
        self.assertIn('api_status=INVALID_ARGUMENT',logs)
        self.assertIn('request_id=REQ_',logs)
        self.assertNotIn('private provider response',logs)
        self.assertNotIn('private diagnostic',logs)

    def test_online_error_keeps_status_and_safe_correlation_fields(self):
        from fastapi.testclient import TestClient
        from vn_labor_online.api import create_app
        def fail(_):
            return call('dense',lambda:(_ for _ in ()).throw(IndexUnavailable('private index path')))
        pipe=self.pipeline(fail)
        with patch('vn_labor_online.api.OnlinePipeline',return_value=pipe),patch('vn_labor_online.api.load_config'),patch.dict('os.environ',{'VN_LABOR_API_KEY':''}):
            with TestClient(create_app()) as client:
                with self.assertLogs('vn_labor_online.api',level='ERROR') as captured:
                    response=client.post('/v1/answer',json={'question':'Question'})
        logs='\n'.join(captured.output)
        self.assertEqual(response.status_code,503)
        self.assertIn('error_id=ERR_',logs)
        self.assertIn('request_id=REQ_',logs)
        self.assertIn('step=dense',logs)
        self.assertIn('IndexUnavailable',logs)
        self.assertNotIn('private index path',logs)

    def test_startup_failure_logs_type_without_exception_message(self):
        from fastapi.testclient import TestClient
        from vn_labor_online.api import create_app
        with patch('vn_labor_online.api.load_config',side_effect=RuntimeError('startup-private-secret')):
            with self.assertLogs('vn_labor_online.api',level='ERROR') as captured:
                with TestClient(create_app()) as client:
                    response=client.get('/ready')
        logs='\n'.join(captured.output)
        self.assertEqual(response.status_code,503)
        self.assertIn('RuntimeError',logs)
        self.assertNotIn('startup-private-secret',logs)

    def test_uvicorn_asgi_log_sanitizes_unhandled_exception_chain(self):
        import httpx
        import uvicorn
        from vn_labor_online.api import create_app

        def fail(_):
            def chained_error():
                try:
                    raise RuntimeError('inner-chain-private-secret')
                except RuntimeError as inner:
                    raise ValueError('outer-private-secret') from inner
            return call('dense',chained_error)

        pipe=self.pipeline(fail)
        app_logger=logging.getLogger('vn_labor_online.api')
        uvicorn_logger=logging.getLogger('uvicorn.error')
        app_stream=io.StringIO();uvicorn_stream=io.StringIO()
        app_handler=logging.StreamHandler(app_stream);uvicorn_handler=logging.StreamHandler(uvicorn_stream)
        previous_levels=(app_logger.level,uvicorn_logger.level)
        app_logger.addHandler(app_handler);uvicorn_logger.addHandler(uvicorn_handler)
        app_logger.setLevel(logging.ERROR);uvicorn_logger.setLevel(logging.ERROR)
        listener=socket.socket()
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind(('127.0.0.1',0));listener.listen(128);listener.setblocking(False)
        port=listener.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(create_app(),log_config=None,access_log=False,
          host='127.0.0.1',port=port,timeout_graceful_shutdown=2))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
        try:
            with patch('vn_labor_online.api.OnlinePipeline',return_value=pipe),patch('vn_labor_online.api.load_config'),patch.dict('os.environ',{'VN_LABOR_API_KEY':''}):
                thread.start()
                deadline=time.monotonic()+5
                while not server.started and thread.is_alive() and time.monotonic()<deadline:
                    time.sleep(.01)
                self.assertTrue(server.started,'Uvicorn did not start')
                response=httpx.post(f'http://127.0.0.1:{port}/v1/answer',json={'question':'Question'},
                  timeout=5,trust_env=False)
                self.assertEqual(response.status_code,500)
        finally:
            server.should_exit=True
            if thread.is_alive():thread.join(5)
            listener.close()
            app_logger.removeHandler(app_handler);uvicorn_logger.removeHandler(uvicorn_handler)
            app_logger.setLevel(previous_levels[0]);uvicorn_logger.setLevel(previous_levels[1])
            app_handler.close();uvicorn_handler.close()
        logs=app_stream.getvalue()+'\n'+uvicorn_stream.getvalue()
        self.assertNotIn('outer-private-secret',logs)
        self.assertNotIn('inner-chain-private-secret',logs)
        self.assertIn('SanitizedASGIError',logs)
        self.assertIn('ValueError',logs)
        self.assertIn('step=dense',logs)
        self.assertIn('request_id=REQ_',logs)
        self.assertIn('error_id=ERR_',logs)
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
                with self.assertLogs('vn_labor_online.api',level='ERROR') as captured:
                    result=client.post('/v1/answer',json={'question':'Question','message_id':'m'},headers=headers)
                self.assertEqual(result.status_code,500)
                payload=result.json();steps=payload['details']['execution_steps']
                self.assertTrue(any(e['step']=='dense' and e['status']=='ERROR' for e in steps))
                self.assertFalse(any(e['status']=='RUNNING' for e in steps))
                self.assertNotIn('never-return-this',json.dumps(payload))
                self.assertNotIn('never-return-this','\n'.join(captured.output))
                self.assertIn('RuntimeError','\n'.join(captured.output))
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
