"""Provider wiring and Gold-blind worker tests: all provider operations are mocked."""
import contextlib,io,json,os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).parent))
import worker
from protocol import DEFAULTS
class WorkerTests(unittest.TestCase):
    def fixture(self,probe=True):
        cfg=SimpleNamespace(graph=SimpleNamespace(enabled=False))
        pipe=Mock();pipe.cfg=cfg;pipe.store.path=lambda p:Path(p);pipe.store.report.model_dump.return_value={'compatible':True}
        state={'settings':dict(DEFAULTS),'artifact_root':'unused','artifact_hashes':{k:'fixture' for k in ('units','nodes','edges')},'all_artifact_files_sha256':{},'probe_review':probe}
        return pipe,state
    def test_review_probe_gets_environment_key_explicitly(self):
        pipe,state=self.fixture()
        provider=Mock();provider.structured.return_value={'ready':True}
        with patch('vn_labor_online.pipeline.OnlinePipeline',return_value=pipe),patch('vn_labor_online.providers.OllamaProvider',return_value=provider),patch('vn_labor_online.providers.GeminiProvider',return_value=provider) as gemini,patch.object(worker,'sha',return_value='fixture'),patch.object(worker,'pin_models',return_value={'revision':'fixture'}),patch.object(worker,'ollama_digest',return_value='fixture'),patch.object(worker,'environment',return_value={}),patch.dict(os.environ,{'GEMINI_API_KEY':'SYNTHETIC_NOT_A_KEY'}):
            _,meta=worker.init(state)
            self.assertEqual(gemini.call_args.kwargs['api_key'],'SYNTHETIC_NOT_A_KEY')
            self.assertNotIn('SYNTHETIC',json.dumps(meta))
    def test_generation_worker_does_not_repeat_gemini_probe(self):
        pipe,state=self.fixture(False)
        provider=Mock();provider.structured.return_value={'ready':True}
        with patch('vn_labor_online.pipeline.OnlinePipeline',return_value=pipe),patch('vn_labor_online.providers.OllamaProvider',return_value=provider),patch('vn_labor_online.providers.GeminiProvider',return_value=provider) as gemini,patch.object(worker,'sha',return_value='fixture'),patch.object(worker,'pin_models',return_value={}),patch.object(worker,'ollama_digest',return_value='fixture'),patch.object(worker,'environment',return_value={}):
            worker.init(state);gemini.assert_not_called()
    def test_gold_fields_rejected_before_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'state.json';state.write_text('{}');pipe=Mock()
            command={'id':'q','arm':'graph_on','question':'Fixture','query_date':'2026-09-15','reference_answer':'DO NOT LEAK'}
            output=io.StringIO()
            with patch.object(worker,'init',return_value=(pipe,{})),patch('sys.stdin',io.StringIO(json.dumps(command)+'\n')),contextlib.redirect_stdout(output):
                self.assertEqual(worker.main(state),0)
            messages=[json.loads(s) for s in output.getvalue().splitlines()]
            self.assertEqual(messages[-1]['status'],'ERROR');pipe.ask.assert_not_called()
            self.assertNotIn('DO NOT LEAK',output.getvalue())
if __name__=='__main__':unittest.main()
