"""Local synthetic recovery tests; never calls Kaggle, git, pip or models."""
import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock, patch
import zipfile

NB = Path(__file__).resolve().parents[1]/'đo/Kaggle_Naive_QA_Recovery.ipynb'

def sources():
    return [''.join(c['source']) for c in json.loads(NB.read_text(encoding='utf-8'))['cells'] if c['cell_type']=='code']

def recovery_functions():
    source=next(s for s in sources() if 'def restore_checkpoint' in s)
    nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)]
    scope=dict(Path=Path,PurePosixPath=PurePosixPath,hashlib=hashlib,zipfile=zipfile,stat=stat,json=json)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<restore>','exec'),scope)
    return scope

def restore_function():return recovery_functions()['restore_checkpoint']

class RecoveryNotebookTests(unittest.TestCase):
    def test_all_cells_parse_and_no_generation_command(self):
        for source in sources(): ast.parse(source)
        execution=next(s for s in sources() if '# JUDGE_SAVED_ONLY' in s)
        self.assertIn("'judge','--run'",execution)
        self.assertNotIn("'run','--bundle'",execution)
        self.assertIn('e.source_tree()==m[',next(s for s in sources() if 'CODE_AND_BUNDLE_VERIFIED' in s))

    def make_archive(self,path,extra=None):
        required=['settings.json','bundle120/manifest.json','bundle120/corpus.jsonl',
            'bundle120/questions.jsonl','naive_qa/run_manifest.json','naive_qa/responses.jsonl','naive_qa/progress.json']
        with zipfile.ZipFile(path,'w') as z:
            for name in required:z.writestr('standard/'+name,'{}')
            if extra:z.writestr(extra,'synthetic')

    def test_restore_and_rerun_preserve_new_judgments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'checkpoint.zip';out=root/'output/standard'
            self.make_archive(archive);restore=restore_function()
            with contextlib.redirect_stdout(io.StringIO()):
                digest=restore(archive,out)
                (out/'naive_qa/responses.jsonl').write_text('NEW_JUDGMENT')
                self.assertEqual(restore(archive,out),digest)
            self.assertEqual((out/'naive_qa/responses.jsonl').read_text(),'NEW_JUDGMENT')

    def test_unsafe_archive_members_are_rejected_before_extraction(self):
        for name in ['../escape','standard/../../escape','/standard/escape',
                     'standard/C:escape','standard/.env',
                     'other/file','standard/cache/file']:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);archive=root/'bad.zip';out=root/'output/standard'
                self.make_archive(archive,name)
                with self.assertRaises(ValueError):restore_function()(archive,out)
                self.assertFalse(out.exists())

    def test_backslash_rejected_before_extraction(self):
        # Windows ZipInfo rewrites separators when creating a real fixture.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'synthetic.zip';archive.write_bytes(b'synthetic')
            info=SimpleNamespace(filename='standard/'+chr(92)+'escape',file_size=1,external_attr=0)
            reader=Mock();reader.infolist.return_value=[info]
            opened=MagicMock();opened.__enter__.return_value=reader
            with patch('zipfile.ZipFile',return_value=opened):
                with self.assertRaisesRegex(ValueError,'không an toàn'):
                    restore_function()(archive,root/'out/standard')
            reader.extractall.assert_not_called()

    def test_auto_detects_kaggle_extracted_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'checkpoint.zip'
            source=root/'input/datasets/user/naive_qa_checkpoint/standard'
            self.make_archive(archive)
            restore_function()(archive,source)
            # Remove the ZIP candidate: Kaggle Input only has extracted files.
            finder=recovery_functions()['find_checkpoint']
            self.assertEqual(finder(root/'input'),source)
            out=root/'working/standard'
            with contextlib.redirect_stdout(io.StringIO()):
                digest=restore_function()(source,out)
                (out/'naive_qa/responses.jsonl').write_text('JUDGED')
                self.assertEqual(restore_function()(source,out),digest)
            self.assertEqual((out/'naive_qa/responses.jsonl').read_text(),'JUDGED')
            self.assertEqual((source/'naive_qa/responses.jsonl').read_text(),'{}')

    def test_directory_change_cannot_overwrite_judged_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'checkpoint.zip';source=root/'input/standard';out=root/'working/standard'
            self.make_archive(archive);restore_function()(archive,source)
            restore_function()(source,out)
            (source/'settings.json').write_text('CHANGED')
            with self.assertRaises(RuntimeError):restore_function()(source,out)

    def test_directory_with_secret_or_missing_files_rejected(self):
        for missing in [False,True]:
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);archive=root/'checkpoint.zip';source=root/'input/standard';out=root/'working/standard'
                self.make_archive(archive);restore_function()(archive,source)
                if missing:(source/'settings.json').unlink()
                else:(source/'.env').write_text('SYNTHETIC')
                with self.assertRaises(ValueError):restore_function()(source,out)
                self.assertFalse(out.exists())

    def test_multiple_checkpoints_require_explicit_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'checkpoint.zip'
            self.make_archive(archive)
            for name in ['first','second']:restore_function()(archive,root/name/'standard')
            finder=recovery_functions()['find_checkpoint']
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):finder(root)
            self.assertEqual(finder(root,str(root/'first/standard')),root/'first/standard')

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'bad.zip';out=root/'output/standard'
            self.make_archive(archive)
            with zipfile.ZipFile(archive,'a') as z:
                info=zipfile.ZipInfo('standard/link');info.external_attr=stat.S_IFLNK<<16
                z.writestr(info,'../escape')
            with self.assertRaises(ValueError):restore_function()(archive,out)

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'checkpoint.zip';out=root/'output/standard'
            self.make_archive(archive);out.mkdir(parents=True)
            with self.assertRaises(RuntimeError):restore_function()(archive,out)

    def judge_case(self,code=0,mutate=False):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'standard';run=out/'naive_qa';run.mkdir(parents=True)
            records=[dict(id='A',status='OK',result={'answer':'synthetic'},metrics={}),
                     dict(id='B',status='ERROR',error={'error_code':'OLLAMA_TIMEOUT'},metrics={})]
            def write(rows):
                (run/'responses.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            write(records)
            def invoke(args,**kw):
                self.assertIn('judge',args)
                after=json.loads(json.dumps(records))
                after[0]['judge']={'status':'AI_JUDGED'};after[0]['metrics']['ai_correctness']=.5
                if mutate:after[0]['result']['answer']='CHANGED'
                write(after)
                (run/'judge_progress.json').write_text(json.dumps({'complete_for_saved_answers':code==0}))
                return SimpleNamespace(returncode=code,args=args)
            display=ModuleType('IPython.display');display.display=Mock();display.Markdown=str;display.FileLink=str
            subprocess=SimpleNamespace(run=Mock(side_effect=invoke),CalledProcessError=__import__('subprocess').CalledProcessError)
            scope=dict(Path=Path,json=json,shutil=__import__('shutil'),subprocess=subprocess,
                CHECKPOINT_SHA256='synthetic',RECORDS=records,COMMIT='a'*40,JUDGE_MODEL='frozen-model',
                PYTHON='synthetic-python',RUN=run,ROOT=out,OUT=out,MAX_NEW_JUDGMENTS=None)
            source=next(s for s in sources() if '# JUDGE_SAVED_ONLY' in s)
            error=None
            with patch.dict('sys.modules',{'IPython.display':display}),contextlib.redirect_stdout(io.StringIO()):
                try:exec(compile(source,'<judge>','exec'),scope)
                except Exception as exc:error=exc
            archive=out.with_name('standard_judge_recovery.zip');self.assertTrue(archive.exists())
            with zipfile.ZipFile(archive) as z:
                state=json.loads(z.read('standard/recovery_status.json'))
                saved=[json.loads(s) for s in z.read('standard/naive_qa/responses.jsonl').decode().splitlines()]
                self.assertEqual(saved[1],records[1])
            self.assertEqual(subprocess.run.call_count,1)
            return state,error

    def test_judge_preserves_generation_and_errors(self):
        state,error=self.judge_case()
        self.assertIsNone(error);self.assertTrue(state['generation_unchanged'])
        self.assertFalse(state['generation_rerun']);self.assertEqual(state['generation_errors_retained'],1)

    def test_quota_pause_still_exports(self):
        state,error=self.judge_case(code=2)
        self.assertIsNone(error);self.assertEqual(state['judge_exit'],2)
        self.assertTrue(state['generation_unchanged'])

    def test_fatal_judge_still_exports(self):
        state,error=self.judge_case(code=1)
        self.assertIsNotNone(error);self.assertEqual(state['exception_type'],'CalledProcessError')

    def test_generation_mutation_is_flagged(self):
        state,error=self.judge_case(mutate=True)
        self.assertFalse(state['generation_unchanged'])
        self.assertEqual(state['verification_error_type'],'RuntimeError')

if __name__=='__main__':unittest.main()
