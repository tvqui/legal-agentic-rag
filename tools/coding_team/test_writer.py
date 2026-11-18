"""Offline Groq/fallback contract tests. No live credentials or API requests."""
import importlib.util,json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('provider_team',Path(__file__).with_name('team.py'))
team=importlib.util.module_from_spec(spec);spec.loader.exec_module(team)
w=team.coding_writer

class WriterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.run=Path(self.tmp.name)/'run'
        self.env=patch.dict(os.environ,{},clear=True);self.env.start();self.addCleanup(self.env.stop)
        loader=patch.object(w,'load_tool_env');loader.start();self.addCleanup(loader.stop)
        self.loader=loader
    def invoke(self,route=None,**kwargs):
        self.record={}
        return w.generate(route or w.route_for(w.GROQ_MODEL),'task','system',self.record,lambda:None,
            team.call_with_retry,team.reject_secrets,team.http_code,retries=kwargs.pop('retries',1),sleep=Mock(),**kwargs)
    def response(self,text='OK'):
        return NS(text=text,candidates=[])
    def test_default_new_writer_and_route_are_pinned(self):
        team.prepare_probe(self.run,executor='local-static');m,_=team.verify(self.run)
        self.assertEqual(m['models']['gemma'],w.GROQ_MODEL)
        self.assertEqual(m['models']['reviewer'],'gemini-3.5-flash-lite')
        self.assertEqual(m['writer_route']['fallback'],w.FALLBACK_MODEL)
        m['writer_route']['fallback']='gemma-4-31b-it';team.save(self.run/'manifest.json',m)
        with self.assertRaises(ValueError):team.verify(self.run)
    def test_old_writer_environment_does_not_automatically_reactivate_gemma(self):
        os.environ['CODING_TEAM_WRITER_MODEL']='gemma-4-31b-it'
        with self.assertRaises(ValueError):team.prepare_probe(self.run)
        self.assertFalse(self.run.exists())
    def test_new_writer_cannot_drop_route_to_change_provider_on_resume(self):
        team.prepare_probe(self.run);m,_=team.verify(self.run)
        m.pop('writer_route');m.pop('writer_route_sha256');team.save(self.run/'manifest.json',m)
        with self.assertRaises(ValueError):team.verify(self.run)
    def test_groq_request_uses_fixed_endpoint_timeout_and_json(self):
        os.environ['GROQ_API_KEY']='fake-test-groq-key'
        payload={'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}], 'usage':{'total_tokens':5}}
        with patch('httpx.Client') as factory:
            client=factory.return_value.__enter__.return_value
            client.post.return_value=NS(status_code=200,content=b'{}',json=lambda:payload)
            r=w.groq_generate('JSON task','system JSON','json',17,True)
        args=client.post.call_args
        self.assertEqual(args.args[0],w.GROQ_ENDPOINT)
        self.assertEqual(args.kwargs['json']['model'],w.GROQ_MODEL)
        self.assertEqual(args.kwargs['json']['response_format'],{'type':'json_object'})
        self.assertFalse(factory.call_args.kwargs['follow_redirects'])
        self.assertEqual(factory.call_args.kwargs['timeout'].read,17)
        self.assertEqual(r.text,'{"ok":true}')
    def test_groq_error_body_never_persisted(self):
        os.environ['GROQ_API_KEY']='fake-key'
        with patch('httpx.Client') as factory:
            factory.return_value.__enter__.return_value.post.return_value=NS(status_code=400,json=lambda:{'error':{'code':'json_validate_failed','message':'PRIVATE_BODY'}})
            with self.assertRaises(w.WriterFailure) as caught:w.groq_generate('task','system','json',15,True)
        self.assertEqual(caught.exception.reason,'GROQ_JSON_VALIDATION_FAILED')
        self.assertNotIn('PRIVATE_BODY',str(caught.exception))
    def test_bounded_retry_then_google_fallback(self):
        with patch.object(w,'groq_generate',side_effect=w.WriterFailure('GROQ_HTTP_ERROR',503)) as primary,patch.object(w,'google_generate',return_value=self.response()) as fallback:
            self.invoke()
        self.assertEqual(primary.call_count,2);fallback.assert_called_once()
        self.assertTrue(self.record['fallback_used']);self.assertEqual(self.record['actual_model'],w.FALLBACK_MODEL)
        self.assertEqual([x['provider'] for x in self.record['writer_attempts']],['groq','google'])
    def test_429_never_retries_or_switches_provider(self):
        with patch.object(w,'groq_generate',side_effect=w.WriterFailure('GROQ_HTTP_ERROR',429)) as primary,patch.object(w,'google_generate') as fallback:
            with self.assertRaises(w.WriterFailure):self.invoke(retries=2)
        primary.assert_called_once();fallback.assert_not_called()
    def test_ambiguous_transport_does_not_retry_or_fallback(self):
        with patch.object(w,'groq_generate',side_effect=RuntimeError('PRIVATE_TRANSPORT')) as primary,patch.object(w,'google_generate') as fallback:
            with self.assertRaises(RuntimeError):self.invoke()
        primary.assert_called_once();fallback.assert_not_called()
        self.assertNotIn('PRIVATE_TRANSPORT',json.dumps(self.record))
    def test_missing_groq_key_can_use_authorized_fallback(self):
        with patch.object(w,'google_generate',return_value=self.response()) as fallback:self.invoke()
        fallback.assert_called_once();self.assertEqual(self.record['fallback_reason'],'MISSING_GROQ_CREDENTIAL')
    def test_no_fallback_when_disabled(self):
        with patch.object(w,'google_generate') as fallback:
            with self.assertRaises(w.WriterFailure):self.invoke(w.route_for(w.GROQ_MODEL,fallback=False))
        fallback.assert_not_called()
    def test_json_validation_rejects_nonobject_duplicates_nan_fences(self):
        for text in ['[]','{"x":1,"x":2}','{"x":NaN}','```json\n{}\n```','not JSON','{"x":1e999}']:
            with self.subTest(text=text),self.assertRaises(w.WriterFailure):w.validate_output(text,'json',lambda t:None)
        self.assertTrue(w.validate_output('{"unicode":"đúng"}','json',lambda t:None)['valid'])
    def test_bad_json_falls_back_but_secret_echo_does_not(self):
        route=w.route_for(w.GROQ_MODEL,'json')
        with patch.object(w,'groq_generate',return_value=self.response('bad')),patch.object(w,'google_generate',return_value=self.response('{"ok":true}')):
            self.invoke(route)
        self.assertEqual(self.record['actual_model'],w.FALLBACK_MODEL)
        os.environ['GROQ_API_KEY']='fake-secret-to-reject'
        with patch.object(w,'groq_generate',return_value=self.response('fake-secret-to-reject')),patch.object(w,'google_generate') as fallback:
            with self.assertRaises(ValueError):self.invoke()
        fallback.assert_not_called()
    def test_truncated_or_tool_response_is_not_accepted(self):
        os.environ['GROQ_API_KEY']='fake-key'
        for finish,tools in [('length',None),('stop',[{'id':'untrusted'}])]:
            payload={'choices':[{'finish_reason':finish,'message':{'content':'code','tool_calls':tools}}]}
            with patch('httpx.Client') as factory:
                factory.return_value.__enter__.return_value.post.return_value=NS(status_code=200,content=b'{}',json=lambda:payload)
                with self.assertRaises(w.WriterFailure):w.groq_generate('task','sys','text',20,False)
    def test_json_probe_has_no_conflicting_ok_instruction(self):
        q=w.request_context(w.route_for(w.GROQ_MODEL,'json'),team.PROBE_SNAPSHOT,True)
        self.assertIn('{"ok":true}',q);self.assertNotIn('Reply only OK',q)
    def test_writer_alias_and_only_groq_requires_no_google_client(self):
        os.environ['GROQ_API_KEY']='fake-key'
        with patch.object(w,'groq_generate',return_value=self.response()),patch('google.genai.Client') as google:
            code=team.main(['probe','--run-dir',str(self.run),'--role','writer','--executor','local-static','--no-writer-fallback'])
        self.assertEqual(code,0);google.assert_not_called()
        m,_=team.verify(self.run);self.assertEqual(m['roles']['gemma']['actual_model'],w.GROQ_MODEL)
    def test_reviewer_sees_actual_model_not_legacy_role_label(self):
        team.prepare_probe(self.run,executor='local-static')
        manifest,_=team.verify(self.run)
        content='x = 1\n';snapshot='TASK\nreview\nEND TASK\n\nFILE sample.py\n'+content+'\nEND FILE\n'
        manifest.pop('purpose');manifest['files']={'sample.py':team.digest(content)};manifest['snapshot_sha256']=team.digest(snapshot)
        (self.run/'snapshot.txt').write_text(snapshot,encoding='utf8');team.save(self.run/'manifest.json',manifest)
        with patch.object(w,'groq_generate',return_value=self.response()):team.execute(self.run,'writer',None)
        team.execute(self.run,'antigravity',None)
        google=Mock();google.models.generate_content.return_value=self.response()
        team.execute(self.run,'reviewer',google)
        self.assertIn('actual_model=qwen/qwen3.8-27b',google.models.generate_content.call_args.kwargs['contents'])
    def test_explicit_writer_format_change_on_resume_is_refused(self):
        team.prepare_probe(self.run,writer_format='text')
        with self.assertRaises(ValueError):team.main(['probe','--run-dir',str(self.run),'--role','writer','--writer-format','json'])
    def test_helper_env_is_allowlisted_and_process_environment_wins(self):
        self.loader.stop()
        p=Path(self.tmp.name)/'.env';p.write_text('GROQ_API_KEY="new-test-key"\nOTHER_SECRET=ignored\n',encoding='utf8')
        os.environ['GROQ_API_KEY']='process-test-key'
        w.load_tool_env(p)
        self.assertEqual(os.environ['GROQ_API_KEY'],'process-test-key');self.assertNotIn('OTHER_SECRET',os.environ)
        del os.environ['GROQ_API_KEY'];w.load_tool_env(p);self.assertEqual(os.environ['GROQ_API_KEY'],'new-test-key')
    def test_duplicate_or_invalid_helper_env_is_rejected_without_value(self):
        self.loader.stop()
        p=Path(self.tmp.name)/'.env'
        for text in ['GROQ_API_KEY=a\nGROQ_API_KEY=b','GROQ_API_KEY="unterminated']:
            p.write_text(text,encoding='utf8')
            with self.assertRaises(ValueError):w.load_tool_env(p)
    def test_google_fallback_uses_exact_model_low_thinking_and_json(self):
        client=Mock();client.models.generate_content.return_value=self.response('{"ok":true}')
        w.google_generate('task','sys','json',12,False,client)
        args=client.models.generate_content.call_args.kwargs
        self.assertEqual(args['model'],'gemini-3.5-flash')
        self.assertEqual(args['config'].response_mime_type,'application/json')
        self.assertEqual(args['config'].http_options.retry_options.attempts,1)

if __name__=='__main__':unittest.main()
