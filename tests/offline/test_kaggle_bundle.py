import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


bootstrap = module('kaggle_bootstrap_test', 'kaggle/bootstrap.py')
remote = module('kaggle_remote_test', 'kaggle/remote.py')
packager = module('kaggle_packager_test', 'scripts/package_kaggle.py')


class KaggleTests(unittest.TestCase):
    def test_remote_audit_propagates_failed_validation_exit_code(self):
        with patch.object(remote, 'audit', return_value=1), patch.object(remote.sys, 'argv', ['remote.py', 'audit']):
            with self.assertRaises(SystemExit) as stopped:
                remote.main()
        self.assertEqual(stopped.exception.code, 1)

    def test_one_click_notebook_reads_and_strips_aura_secrets(self):
        cell = next(c for c in packager.make_notebook()['cells'] if c['cell_type'] == 'code' and 'UserSecretsClient' in ''.join(c['source']))
        secrets = {'NEO4J_URI': 'neo4j+s://example.invalid', 'NEO4J_USER': 'neo4j',
                   'NEO4J_PASSWORD': 'test-only', 'NEO4J_DATABASE': ' labor_project '}
        client = types.SimpleNamespace(get_secret=secrets.__getitem__)
        artifacts = [ROOT / name for name in (
          'artifacts/03_structure/provisions.jsonl', 'artifacts/03_structure/cases.jsonl',
          'artifacts/05_graph/nodes.jsonl', 'artifacts/06_indexes/retrieval_units.jsonl',
          'artifacts/reports/dense_validation.json')]
        namespace = {'LOAD_AURA': True, 'subprocess': bootstrap.subprocess, 'ROOT': ROOT}
        with patch.dict('sys.modules', {'kaggle_secrets': types.SimpleNamespace(UserSecretsClient=lambda: client)}), \
             patch.object(Path, 'is_file', return_value=True), \
             patch.object(bootstrap.subprocess, 'check_output', return_value='0, Tesla T4\n1, Tesla T4\n'):
            exec(''.join(cell['source']), namespace)
        self.assertEqual(namespace['NEO4J_ENV']['NEO4J_DATABASE'], 'labor_project')
        self.assertEqual(set(namespace['NEO4J_ENV']), set(secrets))

    def test_one_click_build_requests_aura_and_clears_secret_copies(self):
        cell = next(c for c in packager.make_notebook()['cells']
                    if c['cell_type'] == 'code' and 'offline_ai_build.log' in ''.join(c['source']))
        with tempfile.TemporaryDirectory() as temp:
            reports = Path(temp)
            (reports / 'final_outputs_validation.json').write_text(
                json.dumps({'ready_for_offline_v1': True}), encoding='utf-8')
            (reports / 'neo4j_validation.json').write_text(
                json.dumps({'passed': True, 'build_id': 'build-test'}), encoding='utf-8')
            received = []
            def logged(arguments, name, environment):
                received.append((list(arguments), name, dict(environment)))
                return 0
            namespace = {
                'OFFLINE_AI_MODEL': 'qwen3:8b', 'OFFLINE_AI_MODE': 'hybrid_ai',
                'LOAD_AURA': True, 'NEO4J_ENV': {
                    'NEO4J_URI': 'neo4j+s://example.invalid', 'NEO4J_USER': 'neo4j',
                    'NEO4J_PASSWORD': 'test-only', 'NEO4J_DATABASE': 'database'},
                'run_logged': logged, 'REPORTS': reports, 'OLLAMA_PROCESS': None,
                'OLLAMA_LOG_HANDLE': None, 'subprocess': bootstrap.subprocess, 'json': json,
            }
            exec(''.join(cell['source']), namespace)
        self.assertIn('--load-aura', received[0][0])
        self.assertEqual(received[0][1], 'offline_ai_build.log')
        self.assertEqual(namespace['AI_ENV'], {})
        self.assertTrue(all(not value for value in namespace['NEO4J_ENV'].values()))

    def test_install_skips_ensurepip_and_repairs_existing_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'kaggle').mkdir()
            (root / 'kaggle/constraints.txt').write_text('setuptools==81.0.0\n')
            with patch.object(bootstrap.subprocess, 'run') as run, patch.object(bootstrap.sys, 'version_info', (3, 12, 13)), patch('importlib.metadata.version', return_value='2.10.0'):
                first = bootstrap.install(root)
                second = bootstrap.install(root)
            self.assertEqual(first, second)
            calls = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(calls), 4)
            for cmd in calls[::2]:
                self.assertIn('--without-pip', cmd)
                self.assertIn('--system-site-packages', cmd)
                self.assertNotIn('--clear', cmd)
            for cmd in calls[1::2]:
                self.assertEqual(cmd[:4], [bootstrap.sys.executable, '-m', 'pip', '--python'])
                self.assertEqual(cmd[4], str(first))

    def test_notebook_code_compiles_and_has_no_secrets(self):
        notebook = packager.make_notebook()
        for i, cell in enumerate(notebook['cells']):
            if cell['cell_type'] == 'code':
                self.assertEqual(cell['outputs'], [])
                compile(''.join(cell['source']), f'cell{i}', 'exec')
        source_text = '\n'.join(''.join(cell['source']) for cell in notebook['cells'])
        serialized = json.dumps(notebook)
        self.assertIn('LOAD_AURA = True', source_text)
        self.assertIn('OFFLINE_AI_MODE = "hybrid_ai"', source_text)
        self.assertIn("arguments.append('--load-aura')", source_text)
        self.assertNotIn('RUN_PIPELINE = True', source_text)
        self.assertIn('UserSecretsClient', source_text)
        self.assertIn('AI_ENV.clear()', source_text)
        self.assertIn('INSTALL_TIMEOUT_SECONDS = 10 * 60', source_text)
        self.assertIn('installer_process.wait(timeout=INSTALL_TIMEOUT_SECONDS)', source_text)
        self.assertIn('PULL_STALL_SECONDS = 15 * 60', source_text)
        self.assertIn('PULL_TOTAL_SECONDS = 90 * 60', source_text)
        self.assertIn("print('Ollama pull:'", source_text)
        self.assertNotIn("subprocess.run(['ollama', 'pull'", source_text)
        self.assertNotIn('change_me', serialized)

    def test_restore_rejects_traversal_and_other_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for bad in ('../outside.txt', '/absolute.txt', 'artifacts/../../escape', 'src/code.py', 'C:/secret'):
                archive = root / 'input.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr(bad, 'bad')
                with self.assertRaises(ValueError):
                    bootstrap.restore_artifacts(archive, root)

    def test_restore_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'input.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('artifacts/reports/checkpoint.json', '{}')
            bootstrap.restore_artifacts(archive, root)
            self.assertTrue((root / 'artifacts/reports/checkpoint.json').exists())
            with self.assertRaises(ValueError):
                bootstrap.restore_artifacts(archive, root)

    def test_verify_rejects_incomplete_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'bundle_manifest.json').write_text(json.dumps({
                'schema': 1, 'files': [{'path': 'data/missing.pdf', 'bytes': 3, 'sha256': 'bad'}]}))
            with self.assertRaises(ValueError):
                bootstrap.verify_bundle(root)

    def test_restore_auto_unzipped_kaggle_input(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'input/artifacts/01_extracted/page_cache'
            source.mkdir(parents=True)
            (source / 'p.json').write_text('{}')
            root = base / 'project'
            root.mkdir()
            bootstrap.restore_artifacts(base / 'input/artifacts', root)
            self.assertEqual((root / 'artifacts/01_extracted/page_cache/p.json').read_text(), '{}')

    def test_config_is_remote_only(self):
        import yaml
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'config').mkdir()
            original = (ROOT / 'config/pipeline.yaml').read_bytes()
            (root / 'config/pipeline.yaml').write_bytes(original)
            with patch.object(remote, 'ROOT', root), patch.object(remote, 'OUT', root / 'artifacts'), patch.object(remote, 'CONFIG', root / 'config/kaggle.yaml'):
                remote.configure()
            cfg = yaml.safe_load((root / 'config/kaggle.yaml').read_text(encoding='utf-8'))
            self.assertTrue(cfg['extraction']['ocr_use_gpu'])
            self.assertEqual(cfg['retrieval']['embedding_device'], 'cuda:0')
            self.assertEqual((root / 'config/pipeline.yaml').read_bytes(), original)

    def test_export_keeps_checkpoints_excludes_models_and_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'project'
            out = root / 'artifacts'
            (out / 'reports').mkdir(parents=True)
            (out / 'reports/kaggle_run.json').write_text('{"pipeline_exit_code":1}')
            (out / 'reports/final_outputs_validation.json').write_text('{"ready_for_offline_v1":true}')
            (root / '.env').write_text('SECRET=do-not-export')
            (out / '01_extracted/page_cache').mkdir(parents=True)
            (out / '01_extracted/page_cache/p.json').write_text('{}')
            with patch.object(remote, 'ROOT', root), patch.object(remote, 'OUT', out):
                remote.export()
            with zipfile.ZipFile(root.parent / 'vn_labor_results.zip') as z:
                self.assertIn('artifacts/01_extracted/page_cache/p.json', z.namelist())
                self.assertTrue(all(n.startswith('artifacts/') for n in z.namelist()))
                self.assertIn('CHƯA ĐẠT', z.read('artifacts/reports/tong_hop_sau_chay.md').decode())


if __name__ == '__main__':
    unittest.main()

