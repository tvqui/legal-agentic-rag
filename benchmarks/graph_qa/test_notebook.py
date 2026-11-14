"""Offline notebook contract and hostile ZIP tests. No installation/API/model calls."""
import contextlib
import hashlib
import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path, PurePosixPath
import make_notebook
from protocol import settings as validate_settings

class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.nb=make_notebook.notebook()
        self.tmp=tempfile.TemporaryDirectory(prefix='graphqa_notebook_')
        self.base=Path(self.tmp.name)
        self.bundle_cell=next(''.join(c['source']) for c in self.nb['cells'] if c['cell_type']=='code' and "if SOURCE == 'attached_zip'" in ''.join(c['source']))
    def tearDown(self):self.tmp.cleanup()
    def bundle(self,name,entries,alter=None):
        path=self.base/(name+'.zip')
        files={n:hashlib.sha256(data).hexdigest() for n,data in entries}
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('package_manifest.json',json.dumps({'schema_version':1,'files':files}))
            for name,data in entries:
                if alter=='symlink':
                    info=zipfile.ZipInfo(name);info.external_attr=(stat.S_IFLNK|0o777)<<16;archive.writestr(info,data)
                else:archive.writestr(name,data+b'tampered' if alter=='hash' else data)
        return path
    def extract(self,path):
        # Execute the exact notebook extraction branch with only its workspace relocated.
        scope=dict(Path=Path,PurePosixPath=PurePosixPath,zipfile=zipfile,hashlib=hashlib,stat=stat,json=json,
                   SOURCE='attached_zip',CODE_ZIP=str(path),CODE_ROOT=self.base/'code')
        source=self.bundle_cell.replace("Path('/kaggle/working')",'Path('+repr(str(self.base))+')')
        with contextlib.redirect_stdout(io.StringIO()):exec(compile(source,'<bundle_cell>','exec'),scope)
        return scope['ROOT']
    def test_generated_notebook_and_cell_syntax(self):
        self.assertEqual(make_notebook.validate(self.nb),10)
        saved=json.loads((Path(__file__).parent/'Kaggle_Graph_QA.ipynb').read_text(encoding='utf-8'))
        self.assertEqual(saved,self.nb)
    def test_settings_cell_matches_runner_schema(self):
        config=''.join(self.nb['cells'][1]['source']);scope={}
        exec(compile(config,'<config>','exec'),scope)
        cell=next(''.join(c['source']) for c in self.nb['cells'] if c['cell_type']=='code' and "settings={'device'" in ''.join(c['source']))
        start=cell.index("settings={'device'");end=cell.index('SETTINGS.parent')
        exec(compile(cell[start:end],'<settings>','exec'),scope)
        path=self.base/'settings.json';path.write_text(json.dumps(scope['settings']),encoding='utf-8')
        self.assertEqual(validate_settings(path),scope['settings'])
    def test_verified_bundle_reuse_and_no_clobber(self):
        archive=self.bundle('valid',[('benchmarks/graph_qa/run.py',b'# inert\n')])
        root=self.extract(archive);self.assertEqual(self.extract(archive),root)
        target=root/'benchmarks/graph_qa/run.py';target.write_bytes(b'local change')
        with self.assertRaises(RuntimeError):self.extract(archive)
        self.assertEqual(target.read_bytes(),b'local change')
    def test_untrusted_bundles_rejected_before_source_write(self):
        for name,path,alter in [('parent','../escape',None),('absolute','/escape',None),('backslash','bad\\x',None),
                                ('alias','bad/./x',None),('double','bad//x',None),('symlink','link','symlink'),
                                ('hash','benchmarks/graph_qa/run.py','hash')]:
            with self.subTest(name=name):
                archive=self.bundle(name,[(path,b'data')],alter)
                with self.assertRaises((ValueError,RuntimeError)):self.extract(archive)
                root=self.base/'code'/hashlib.sha256(archive.read_bytes()).hexdigest()[:12]
                self.assertFalse((root/'benchmarks/graph_qa/run.py').exists())
    def test_kaggle_expanded_source_verified_and_tamper_rejected(self):
        archive=self.bundle('expanded',[('benchmarks/graph_qa/run.py',b'# inert')])
        expanded=self.base/'expanded';expanded.mkdir()
        with zipfile.ZipFile(archive) as z:z.extractall(expanded)
        root=self.extract(expanded)
        self.assertEqual((root/'benchmarks/graph_qa/run.py').read_bytes(),b'# inert')
        (expanded/'benchmarks/graph_qa/run.py').write_bytes(b'tampered')
        with self.assertRaises(ValueError):self.extract(expanded)
    def test_expanded_unmanifested_file_rejected(self):
        archive=self.bundle('extra',[('benchmarks/graph_qa/run.py',b'# inert')])
        expanded=self.base/'extra';expanded.mkdir()
        with zipfile.ZipFile(archive) as z:z.extractall(expanded)
        (expanded/'unexpected.env').write_text('synthetic',encoding='utf-8')
        with self.assertRaises(ValueError):self.extract(expanded)
    def test_download_cell_can_export_partial_results(self):
        source=next(''.join(c['source']) for c in self.nb['cells'] if c['cell_type']=='code' and 'from IPython.display' in ''.join(c['source']))
        (self.base/'comparison.md').write_text('# fixture',encoding='utf-8')
        archive=self.base/'result.zip';archive.write_bytes(b'fixture');calls=[]
        scope=dict(OUT=self.base,RESULT_ZIP=archive,PYTHON='python',ENTRY=self.base/'run.py',ROOT=self.base,
                   run_step=lambda *args,**kw:calls.append((args,kw)))
        source=source.replace('from IPython.display import FileLink, display, Markdown','FileLink=str\nMarkdown=str\ndisplay=lambda value: None')
        with contextlib.redirect_stdout(io.StringIO()):exec(compile(source,'<download_cell>','exec'),scope)
        self.assertEqual(len(calls),2)
        self.assertTrue(all(call[1]['check'] is False for call in calls))

if __name__=='__main__':unittest.main()
