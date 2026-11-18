"""Ablation recovery notebook: synthetic data, no services or model calls."""
import ast,contextlib,hashlib,io,json,stat,tempfile,unittest,zipfile
from pathlib import Path,PurePosixPath
NB=Path(__file__).resolve().parents[1]/'đo/Kaggle_Ablation_Recovery.ipynb'
METHODS=('full','without_graph','without_reranker','without_auditor','without_review')
REQUIRED=['settings.json','bundle120/manifest.json','bundle120/corpus.jsonl','bundle120/questions.jsonl',
          'runs/full/run_manifest.json','runs/full/responses.jsonl','runs/full/progress.json']

def functions():
    cells=json.loads(NB.read_text(encoding='utf-8'))['cells']
    source=''.join(cells[2]['source']);nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)]
    scope=dict(Path=Path,PurePosixPath=PurePosixPath,json=json,hashlib=hashlib,zipfile=zipfile,
               stat=stat,METHODS=METHODS,CHECKPOINT_REQUIRED=REQUIRED)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<recovery>','exec'),scope)
    return scope

class AblationRecoveryTests(unittest.TestCase):
    def fixture(self,p,extra=None):
        with zipfile.ZipFile(p,'w') as z:
            for name in REQUIRED:
                value=json.dumps({'task':'qa','methods':['full']}) if name.endswith('run_manifest.json') else '{}'
                z.writestr(name,value)
            if extra:z.writestr(extra,'synthetic')

    def test_all_cells_parse_and_only_judge_is_run(self):
        cells=json.loads(NB.read_text(encoding='utf-8'))['cells']
        for cell in cells:
            if cell['cell_type']=='code':compile(''.join(cell['source']),'<cell>','exec')
        judge=''.join(cells[5]['source'])
        self.assertIn("'judge','--run'",judge);self.assertNotIn("'run','--bundle'",judge)
        self.assertIn("root_dir=OUT)",judge)

    def test_flat_zip_and_extracted_dataset_are_detected_and_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'full_ablation_results.zip';self.fixture(archive)
            funcs=functions();out=root/'input/datasets/user/checkpoint'
            funcs['restore_checkpoint'](archive,out)
            self.assertEqual(funcs['checkpoint_manifest'](out)['methods'],['full'])
            self.assertEqual(funcs['find_checkpoint'](root/'input'),out)
            self.assertEqual(funcs['checkpoint_manifest'](archive)['methods'],['full'])
            restored=root/'working/full';funcs['restore_checkpoint'](out,restored)
            self.assertEqual((restored/'runs/full/responses.jsonl').read_text(),'{}')
            (restored/'runs/full/responses.jsonl').write_text('NEW_JUDGMENT')
            with contextlib.redirect_stdout(io.StringIO()):funcs['restore_checkpoint'](out,restored)
            self.assertEqual((restored/'runs/full/responses.jsonl').read_text(),'NEW_JUDGMENT')

    def test_zip_traversal_and_secrets_are_rejected(self):
        for extra in ['../escape','/escape','nested/.env','nested/cache/file']:
            with self.subTest(extra=extra),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);archive=root/'bad.zip';self.fixture(archive,extra)
                with self.assertRaises(ValueError):functions()['restore_checkpoint'](archive,root/'out')
                self.assertFalse((root/'out').exists())

    def test_duplicate_inputs_need_explicit_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'full_ablation_results.zip';self.fixture(archive)
            funcs=functions();funcs['restore_checkpoint'](archive,root/'full')
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError):funcs['find_checkpoint'](root)
            self.assertEqual(funcs['find_checkpoint'](root,str(root/'full')),root/'full')

    def test_new_input_cannot_overwrite_saved_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'full_ablation_results.zip';self.fixture(archive)
            funcs=functions();out=root/'full';funcs['restore_checkpoint'](archive,out)
            with zipfile.ZipFile(archive,'a') as z:z.writestr('new.txt','different')
            with self.assertRaises(RuntimeError):funcs['restore_checkpoint'](archive,out)

if __name__=='__main__':unittest.main()
