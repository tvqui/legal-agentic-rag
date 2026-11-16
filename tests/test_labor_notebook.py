"""Notebook orchestration tests; no models, network or API calls."""
import ast
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import zipfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'đo'))
from retry_failed import retry_failed, restart_owned_ollama

NB = Path(__file__).resolve().parents[1] / 'đo/Kaggle_Labor_Evaluation.ipynb'

class LaborNotebookTests(unittest.TestCase):
    def execute_case(self, generation=0, judge=0, progress=None, report=0, phase='naive_qa'):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'standard'
            run = out / phase
            run.mkdir(parents=True)
            (run/'run_manifest.json').write_text('{}')
            original = json.dumps({'status':'ERROR','id':'synthetic','method':'synthetic','repeat':1,'elapsed_ms':1})+'\n'
            (run/'responses.jsonl').write_text(original)
            if progress is not None:
                (run/'progress.json').write_text(json.dumps(progress))
            calls = []
            def invoke(args, **kwargs):
                calls.append(args)
                code = report if 'report' in args else judge if 'judge' in args else generation
                return SimpleNamespace(returncode=code, args=args)
            scope = dict(PHASE=phase,PROFILE='standard',OUT=out,BUNDLE=out/'bundle',
                         SETTINGS=out/'settings.json',PYTHON='synthetic',ROOT=out,
                         RESUME=False,RETRY_ERRORS=False,Path=Path,json=json,
                         AUTO_RETRY_ROUNDS=0,RETRY_BACKOFF_SECONDS=0,retry_failed=retry_failed,
                         restart_owned_ollama=restart_owned_ollama,
                         subprocess=SimpleNamespace(run=Mock(side_effect=invoke),
                             CalledProcessError=__import__('subprocess').CalledProcessError))
            nb = json.loads(NB.read_text(encoding='utf-8'))
            error = None
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    exec(compile(''.join(nb['cells'][8]['source']), '<measurement>', 'exec'), scope)
                except Exception as exc:
                    error = exc
            archive = out.with_name('standard_results.zip')
            self.assertTrue(archive.exists())
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(z.read(phase+'/responses.jsonl'), (run/'responses.jsonl').read_bytes())
                state = json.loads(z.read(phase+'_notebook_execution.json'))
            return calls, state, error

    def test_every_code_cell_parses(self):
        for cell in json.loads(NB.read_text(encoding='utf-8'))['cells']:
            if cell['cell_type'] == 'code':
                ast.parse(''.join(cell['source']))

    def test_finished_with_errors_still_judges_and_exports(self):
        calls,state,error=self.execute_case(2,progress=dict(expected=360,saved=360,paused=None,complete=False))
        self.assertIsNone(error)
        self.assertTrue(any('judge' in c for c in calls))
        self.assertEqual(state['generation_exit'],2)
        self.assertFalse(state['generation_progress']['complete'])

    def test_interrupted_or_missing_progress_does_not_judge(self):
        for progress in [None,dict(expected=360,saved=200,paused=None),
                         dict(expected=360,saved=360,paused='PROVIDER_CAPACITY'),
                         dict(expected=0,saved=0,paused=None)]:
            with self.subTest(progress=progress):
                calls,state,error=self.execute_case(2,progress=progress)
                self.assertFalse(any('judge' in c for c in calls))
                self.assertFalse(state['generation_schedule_finished'])
                self.assertIsNone(error)

    def test_judge_quota_pause_keeps_checkpoint(self):
        calls,state,error=self.execute_case(judge=2)
        self.assertEqual(state['judge_exit'],2)
        self.assertIsNone(error)
        self.assertTrue(any('report' in c for c in calls))

    def test_fatal_generation_still_exports_before_raising(self):
        calls,state,error=self.execute_case(generation=1)
        self.assertIsNotNone(error)
        self.assertEqual(state['exception_type'],'CalledProcessError')
        self.assertFalse(any('judge' in c for c in calls))

    def test_fatal_judge_still_exports_before_raising(self):
        calls,state,error=self.execute_case(judge=1)
        self.assertIsNotNone(error)
        self.assertEqual(state['judge_exit'],1)

    def test_report_error_does_not_destroy_records(self):
        calls,state,error=self.execute_case(report=1)
        self.assertIsNone(error)
        self.assertEqual(state['report_exit'],1)

    def test_retrieval_never_calls_judge(self):
        calls,state,error=self.execute_case(phase='retrieval')
        self.assertFalse(any('judge' in c for c in calls))
        self.assertIsNone(error)

if __name__ == '__main__':
    unittest.main()
