"""Execute notebook helpers and failure paths without installing models/services."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('online_notebook_generator', ROOT/'kaggle/online_notebook.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class KaggleOnlineNotebookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.notebook = generator.make_notebook()
        self.code = {cell['metadata']['name']: ''.join(cell['source'])
                     for cell in self.notebook['cells'] if cell['cell_type']=='code'}
        self.scope = {'Path': Path, 'WORKING': self.root/'working'}
        self.scope['WORKING'].mkdir()
        exec(self.code['helpers'], self.scope)

    def artifact(self, name='new'):
        root = self.root/name/'artifacts'
        files = ('05_graph/nodes.jsonl', '05_graph/edges.jsonl', '06_indexes/retrieval_units.jsonl',
                 'reports/dense_validation.json', 'reports/neo4j_validation.json')
        for name in files:
            target = root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('{}', encoding='utf-8')
        (root/'reports/final_outputs_validation.json').write_text(json.dumps({
            'stages': {key:True for key in ('registry','structure','graph','indexes')}}), encoding='utf-8')
        return root.resolve()

    def release(self):
        return ({'compatible':True,'build_id':'build','retrieval_unit_fingerprint':'units','dense_fingerprint':'dense'},
                {'expected_build_id':'build','expected_retrieval_unit_fingerprint':'units','expected_dense_fingerprint':'dense'})

    def test_notebook_roundtrip_syntax_and_clean_outputs(self):
        target = self.root/'notebook.ipynb'
        report = generator.write_notebook(target)
        notebook = json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(len({cell['id'] for cell in notebook['cells']}), len(notebook['cells']))
        for cell in notebook['cells']:
            if cell['cell_type']=='code':
                compile(''.join(cell['source']), cell['metadata']['name'], 'exec')
                self.assertEqual(cell['outputs'], [])
                self.assertIsNone(cell['execution_count'])
        self.assertEqual(notebook['cells'][-1]['metadata']['name'], 'backend')
        self.assertEqual(report['sha256'], hashlib.sha256(target.read_bytes()).hexdigest())
        self.assertTrue(Path(str(target)+'.sha256').is_file())

    def test_select_complete_unpacked_artifact(self):
        expected = self.artifact()
        self.assertEqual(self.scope['select_artifact'](self.root), expected)

    def test_does_not_prefer_old_zip_over_new_directory(self):
        self.artifact()
        (self.root/'vn_labor_results.zip').write_bytes(b'fixture')
        with self.assertRaisesRegex(RuntimeError, '2'):
            self.scope['select_artifact'](self.root)

    def test_partial_directory_is_not_a_final_artifact(self):
        root = self.artifact()
        (root/'05_graph/nodes.jsonl').unlink()
        with self.assertRaisesRegex(RuntimeError, '0'):
            self.scope['select_artifact'](self.root)

    def test_explicit_input_resolves_ambiguity_without_escaping_input(self):
        expected = self.artifact()
        self.artifact('other')
        self.assertEqual(self.scope['select_artifact'](self.root, str(expected)), expected)
        with self.assertRaises(RuntimeError):
            self.scope['select_artifact'](self.root, str(self.root.parent))
        with self.assertRaises(RuntimeError):
            self.scope['select_artifact'](self.root, str(self.root/'missing'))

    def test_all_release_fingerprints_and_real_compatibility_are_required(self):
        pin, effective = self.release()
        self.scope['assert_release'](pin, effective)
        for field in ('build_id','retrieval_unit_fingerprint','dense_fingerprint','compatible'):
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.scope['assert_release']({**pin,field:'wrong'}, effective)
        with self.assertRaises(RuntimeError):
            self.scope['assert_release'](pin, {'expected_build_id':'build'})

    def test_tail_is_bounded_and_redacts_secret(self):
        target = self.root/'log'
        target.write_text('x'*30000+'private-key-value', encoding='utf-8')
        with patch.dict(os.environ, {'GEMINI_API_KEY':'private-key-value'}):
            result = self.scope['log_tail'](target, limit=100)
        self.assertNotIn('private-key-value', result)
        self.assertIn('[REDACTED]', result)
        self.assertLess(len(result), 110)
        self.assertIsInstance(self.scope['log_tail'](self.root/'missing'), str)

    def test_actual_tunnel_url_is_saved_without_secret(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.dict(os.environ, {'VN_LABOR_API_KEY':'fixture-key'}):
            self.scope['backend_line']('REMOTE_BACKEND_URL=https://example.ngrok-free.dev')
        self.assertIn('VITE_BACKEND_TARGET=https://example.ngrok-free.dev', output.getvalue())
        self.assertNotIn('fixture-key', output.getvalue())
        self.assertEqual((self.scope['WORKING']/'remote_backend_url.txt').read_text().strip(),
                         'https://example.ngrok-free.dev')
        with self.assertRaises(RuntimeError):
            self.scope['backend_line']('REMOTE_BACKEND_URL=http://insecure')

    def test_failed_gemini_probe_invalidates_previous_success(self):
        self.scope.update(PYTHON=Path('/python'), CONFIG=Path('/config'), GEMINI_MODEL='model',
                          ROOT=self.root, NOTEBOOK_VALIDATED=True,
                          run_step=Mock(side_effect=RuntimeError('provider unavailable')))
        with self.assertRaisesRegex(RuntimeError, 'provider unavailable'):
            exec(self.code['gemini_check'], self.scope)
        self.assertFalse(self.scope['NOTEBOOK_VALIDATED'])
        with self.assertRaises(RuntimeError):
            exec(self.code['backend'], self.scope)
        self.assertEqual(self.scope['run_step'].call_count, 1)

    def test_successful_probe_allows_serve_and_passes_model_and_config(self):
        run = Mock()
        self.scope.update(PYTHON=Path('/python'), CONFIG=Path('/config'), GEMINI_MODEL='model',
                          ROOT=self.root, OLLAMA_MODEL='qwen3:8b', ARTIFACT_PATH=self.root/'artifacts',
                          READY_TIMEOUT_SECONDS=180, run_step=run, assert_ports_free=Mock())
        with contextlib.redirect_stdout(io.StringIO()):
            exec(self.code['gemini_check'], self.scope)
            exec(self.code['backend'], self.scope)
        self.assertTrue(self.scope['NOTEBOOK_VALIDATED'])
        args, kwargs = run.call_args
        self.assertIn('--config', args[0])
        self.assertIn(Path('/config'), args[0])
        self.assertIn('qwen3:8b', args[0])
        self.assertIsNone(kwargs['timeout'])
        self.assertEqual(kwargs['on_line'], self.scope['backend_line'])

    def test_old_service_prevents_second_backend_launch(self):
        run = Mock()
        self.scope.update(NOTEBOOK_VALIDATED=True, run_step=run,
                          assert_ports_free=Mock(side_effect=RuntimeError('old service')))
        with self.assertRaisesRegex(RuntimeError, 'old service'):
            exec(self.code['backend'], self.scope)
        run.assert_not_called()

    def test_fresh_secrets_replace_old_role_key_without_printing_credentials(self):
        self.artifact()
        values = {'GEMINI_API_KEY':'new-gemini-key', 'VN_LABOR_API_KEY':'a'*40,
                  'NGROK_AUTHTOKEN':'new-ngrok-token'}
        client = SimpleNamespace(get_secret=lambda name:values.get(name,''))
        fake_kaggle = SimpleNamespace(UserSecretsClient=lambda:client)
        self.scope.update(sys=SimpleNamespace(platform='linux',version_info=(3,13)),
            INPUT_ROOT=self.root, ARTIFACT='', GEMINI_MODEL='chosen-model', GEMINI_RPM=13,
            OLLAMA_MODEL='qwen3:8b', assert_ports_free=Mock(), NOTEBOOK_VALIDATED=True)
        response = Mock(status=200)
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=None)
        output = io.StringIO()
        with patch.dict('sys.modules',{'kaggle_secrets':fake_kaggle}), \
             patch.dict(os.environ, {'VN_LABOR_RESEARCHER_API_KEY':'stale','HF_TOKEN':'old-hf'}), \
             patch('shutil.which', return_value='/usr/bin/nvidia-smi'), \
             patch('subprocess.run', return_value=SimpleNamespace(stdout='Tesla T4\nTesla T4\n')), \
             patch('urllib.request.urlopen', return_value=response), contextlib.redirect_stdout(output):
            exec(self.code['preflight'], self.scope)
            self.assertEqual(os.environ['VN_LABOR_RESEARCHER_API_KEY'],values['GEMINI_API_KEY'])
            self.assertEqual(os.environ['VN_LABOR_GEMINI_RPM'],'13')
            self.assertNotIn('HF_TOKEN',os.environ)
            self.assertEqual(os.environ['VN_LABOR_ADJUDICATION_REVIEW_PROVIDER'],'gemini')
        self.assertFalse(self.scope['NOTEBOOK_VALIDATED'])
        for secret in values.values(): self.assertNotIn(secret,output.getvalue())

    def test_no_gpu_fails_before_install_or_secret_access(self):
        self.scope.update(sys=SimpleNamespace(platform='linux',version_info=(3,13)),
                          INPUT_ROOT=self.root, NOTEBOOK_VALIDATED=True)
        with patch('shutil.which', return_value=None), self.assertRaisesRegex(RuntimeError, 'GPU'):
            exec(self.code['preflight'], self.scope)
        self.assertFalse(self.scope['NOTEBOOK_VALIDATED'])

    def test_dependency_install_uses_isolated_python_and_existing_torch_constraints(self):
        repo = self.root/'repo'
        (repo/'.git').mkdir(parents=True)
        (repo/'src/vn_labor_online').mkdir(parents=True)
        (repo/'src/vn_labor_online/api.py').write_text('diagnostic-probe-v2',encoding='utf-8')
        (repo/'kaggle').mkdir()
        (repo/'kaggle/check_gemini.py').write_text('# fixture',encoding='utf-8')
        calls = []
        def git_output(args, **kwargs):
            return {'remote':'https://github.com/tvqui/legal-agentic-rag.git\n',
                    'status':'','rev-parse':'new-main-sha\n'}[args[1]]
        self.scope.update(ROOT=repo, REPO_URL='https://github.com/tvqui/legal-agentic-rag.git',
            BRANCH='main', PYTHON=self.root/'env/bin/python',
            run_step=lambda args,*a,**kw:calls.append(list(map(str,args))))
        with patch('subprocess.check_output',side_effect=git_output), \
             patch('importlib.metadata.version',return_value='2.8.0'), \
             patch('shutil.which',return_value='/usr/bin/ollama'), contextlib.redirect_stdout(io.StringIO()):
            exec(self.code['setup'], self.scope)
        pip = next(call for call in calls if 'pip' in call)
        self.assertEqual(pip[pip.index('--python')+1],str(self.scope['PYTHON']))
        self.assertIn('-c',pip)
        self.assertIn('torch==2.8.0',(self.scope['WORKING']/'torch_constraints.txt').read_text())
        self.assertEqual(sum(call[:2]==['apt-get','update'] for call in calls),1)
        self.assertTrue(any('--system-site-packages' in call for call in calls))

    def test_pin_incompatible_report_cannot_become_success(self):
        pin, expected = self.release()
        pin['compatible']=False
        def pin_output(args,*a,on_line=None,**kwargs):
            on_line(json.dumps(pin))
        self.scope.update(ROOT=self.root,PYTHON=Path('/python'),CONFIG=Path('/config'),
                          ARTIFACT_PATH=self.root/'artifacts',run_step=pin_output,
                          NOTEBOOK_VALIDATED=True)
        with patch('subprocess.check_output',return_value=json.dumps({'base':expected,'selected':expected})), \
             self.assertRaisesRegex(RuntimeError, 'tương thích'):
            exec(self.code['pin_config'],self.scope)
        self.assertFalse(self.scope['NOTEBOOK_VALIDATED'])

    def test_subprocess_log_redacts_output_and_reports_exit_failure(self):
        output=io.StringIO()
        with patch.dict(os.environ,{'GEMINI_API_KEY':'secret-fixture-value'}), \
             contextlib.redirect_stdout(output):
            self.scope['run_step']([self.scope['sys'].executable,'-c',
                'import os;print(os.environ["GEMINI_API_KEY"])'],'fixture',timeout=10)
            with self.assertRaisesRegex(RuntimeError,'exit=7'):
                self.scope['run_step']([self.scope['sys'].executable,'-c','raise SystemExit(7)'],
                                       'failure',timeout=10)
        self.assertNotIn('secret-fixture-value',output.getvalue())
        self.assertIn('[REDACTED]',(self.scope['WORKING']/'notebook_logs/fixture.log').read_text())


if __name__=='__main__':
    unittest.main()
