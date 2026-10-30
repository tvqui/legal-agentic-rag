"""Generated notebooks must retain their SHA on Windows and Linux checkouts."""
import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path


class NotebookIntegrityTests(unittest.TestCase):
    def test_generator_uses_canonical_newlines_and_valid_digests(self):
        generator=Path(__file__).with_name('make_notebook.py')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);script=root/'make_notebook.py';script.write_bytes(generator.read_bytes())
            subprocess.run([sys.executable,str(script)],cwd=root,check=True,capture_output=True)
            for name in ['Kaggle_Evaluation.ipynb','Kaggle_Evaluation_Standard.ipynb']:
                file=root/name;raw=file.read_bytes()
                self.assertNotIn(b'\r\n',raw)
                self.assertEqual(hashlib.sha256(raw).hexdigest(),Path(str(file)+'.sha256').read_text().split()[0])
                self.assertTrue(all(not c.get('outputs') for c in json.loads(raw)['cells']))

    def test_git_attributes_keep_notebook_bytes_stable(self):
        project=Path(__file__).resolve().parents[2]
        attributes=(project/'.gitattributes').read_text(encoding='utf-8')
        for name in ['kaggle/ONLINE_Backend.ipynb','benchmarks/evaluation_suite/Kaggle_Evaluation.ipynb',
                     'benchmarks/evaluation_suite/Kaggle_Evaluation_Standard.ipynb']:
            self.assertIn(name+' text eol=lf',attributes)


if __name__=='__main__':unittest.main()
