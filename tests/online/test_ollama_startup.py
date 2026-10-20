import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock,patch


def launcher():
    spec=importlib.util.spec_from_file_location('tested_online_launcher',Path(__file__).resolve().parents[2]/'kaggle/online_remote.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class OllamaStartupTests(unittest.TestCase):
    def test_exact_cached_model_never_contacts_registry(self):
        module=launcher()
        with patch.object(module.subprocess,'run',return_value=Mock(returncode=0)) as run:
            self.assertEqual(module.ensure_ollama_model('qwen3:8b',{'OLLAMA_MODELS':'selected-cache'}),'CACHED')
        self.assertEqual(run.call_count,1)
        self.assertEqual(run.call_args.args[0],['ollama','show','qwen3:8b'])
        self.assertEqual(run.call_args.kwargs['env']['OLLAMA_MODELS'],'selected-cache')

    def test_skip_pull_cannot_hide_a_missing_model(self):
        module=launcher()
        with patch.object(module.subprocess,'run',return_value=Mock(returncode=1)) as run:
            with self.assertRaisesRegex(RuntimeError,'not available locally'):
                module.ensure_ollama_model('qwen3:8b',{},skip_pull=True)
        self.assertEqual(run.call_count,1)

    def test_transient_download_failure_retries_and_verifies_exact_model(self):
        module=launcher()
        with patch.object(module.subprocess,'run',side_effect=[Mock(returncode=1),Mock(returncode=1),Mock(returncode=0),Mock(returncode=0)]) as run,patch.object(module.time,'sleep'):
            self.assertEqual(module.ensure_ollama_model('qwen3:8b',{}),'PULLED')
        self.assertEqual([c.args[0][1] for c in run.call_args_list],['show','pull','pull','show'])

    def test_persistent_failure_and_timeout_are_bounded(self):
        module=launcher()
        with patch.object(module.subprocess,'run',return_value=Mock(returncode=1)) as run,patch.object(module.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'Backend has not started'):
                module.ensure_ollama_model('qwen3:8b',{},attempts=3)
        self.assertEqual(run.call_count,4)
        with patch.object(module.subprocess,'run',side_effect=[Mock(returncode=1),subprocess.TimeoutExpired(['ollama'],2)]) as run:
            with self.assertRaisesRegex(RuntimeError,'download timeout'):
                module.ensure_ollama_model('qwen3:8b',{},total_seconds=2)
        self.assertEqual(run.call_count,2)

    def test_zero_exit_without_a_model_cannot_start_backend(self):
        module=launcher()
        with patch.object(module.subprocess,'run',side_effect=[Mock(returncode=1),Mock(returncode=0),Mock(returncode=1)]):
            with self.assertRaisesRegex(RuntimeError,'exact model is unavailable'):
                module.ensure_ollama_model('qwen3:8b',{})
