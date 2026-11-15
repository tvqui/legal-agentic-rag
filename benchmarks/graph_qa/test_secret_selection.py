"""Execute real notebook Secret cells against synthetic Kaggle clients only."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
from types import ModuleType
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]

class NotebookSecretSelectionTests(unittest.TestCase):
    def sources(self,kind):
        path=(ROOT/'benchmarks/graph_qa/Kaggle_Graph_QA.ipynb' if kind=='graph'
              else ROOT/'đo/Kaggle_Labor_Evaluation.ipynb')
        nb=json.loads(path.read_text(encoding='utf8'))
        config=''.join(nb['cells'][1]['source'])
        code=next(''.join(c['source']) for c in nb['cells']
                  if c['cell_type']=='code' and 'from kaggle_secrets import' in ''.join(c['source']))
        if kind=='graph':code=code.split("os.environ['VN_LABOR_GEMINI_RPM']")[0]
        return nb,config,code

    def execute(self,kind,name,lookup,enabled=True):
        _,config,code=self.sources(kind)
        scope={};exec(compile(config,'<config>','exec'),scope)
        scope.update(GEMINI_SECRET_NAME=name,os=os,run=Mock(),PYTHON='synthetic-python')
        if kind=='graph':scope.update(SEMANTIC_REVIEW=enabled,RUN_AI_JUDGE=False)
        else:scope['PHASE']='ablation' if enabled else 'retrieval'
        client=Mock();client.get_secret.side_effect=lookup
        module=ModuleType('kaggle_secrets');module.UserSecretsClient=Mock(return_value=client)
        capture=io.StringIO()
        with patch.dict('sys.modules',{'kaggle_secrets':module}),contextlib.redirect_stdout(capture):
            exec(compile(code,'<secrets>','exec'),scope)
        return client,scope,capture.getvalue()

    def test_named_secrets_feed_existing_provider_variable_without_rotation(self):
        for kind in ['graph','labor']:
            for label in ['GEMINI_API_KEY','GEMINI_API_KEY.2','GEMINI_API_KEY.3','GEMINI_API_KEY.41']:
                with self.subTest(kind=kind,label=label),patch.dict(os.environ,{},clear=True):
                    def lookup(name):
                        if name=='HF_TOKEN':return None
                        self.assertEqual(name,label)
                        return '  SYNTHETIC_PRIVATE_VALUE  '
                    client,scope,output=self.execute(kind,label,lookup)
                    self.assertEqual(os.environ['GEMINI_API_KEY'],'SYNTHETIC_PRIVATE_VALUE')
                    self.assertEqual([c.args[0] for c in client.get_secret.call_args_list],['HF_TOKEN',label])
                    self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',output)
                    self.assertIn(label,output)
                    self.assertNotIn(label,os.environ if label!='GEMINI_API_KEY' else {})
                    if kind=='labor':scope['run'].assert_called_once()

    def test_missing_or_empty_selection_clears_stale_key_and_does_not_fallback(self):
        for kind in ['graph','labor']:
            for value in [None,'','   ',RuntimeError('SYNTHETIC_PRIVATE_ERROR')]:
                with self.subTest(kind=kind,value=type(value).__name__),patch.dict(os.environ,{'GEMINI_API_KEY':'STALE_PRIVATE_VALUE'},clear=True):
                    names=[]
                    def lookup(name):
                        names.append(name)
                        if name=='HF_TOKEN':return None
                        if isinstance(value,Exception):raise value
                        return value
                    with self.assertRaises(RuntimeError) as caught:
                        self.execute(kind,'GEMINI_API_KEY.2',lookup)
                    self.assertNotIn('GEMINI_API_KEY',os.environ)
                    self.assertNotIn('SYNTHETIC_PRIVATE_ERROR',str(caught.exception))
                    self.assertEqual(names,['HF_TOKEN','GEMINI_API_KEY.2'])

    def test_retrieval_or_disabled_review_does_not_request_gemini(self):
        for kind in ['graph','labor']:
            with self.subTest(kind=kind),patch.dict(os.environ,{},clear=True):
                client,scope,_=self.execute(kind,'GEMINI_API_KEY.2',lambda name:None,False)
                self.assertEqual([c.args[0] for c in client.get_secret.call_args_list],['HF_TOKEN'])
                self.assertNotIn('GEMINI_API_KEY',os.environ)
                scope['run'].assert_not_called()

    def test_invalid_label_is_rejected_without_displaying_it(self):
        for kind in ['graph','labor']:
            _,config,_=self.sources(kind)
            for value in ['',None,'SYNTHETIC_PRIVATE_VALUE','GEMINI_API_KEY.0','GEMINI_API_KEY.2\n']:
                with self.subTest(kind=kind,value=type(value).__name__):
                    code=config.replace("GEMINI_SECRET_NAME = 'GEMINI_API_KEY'",'GEMINI_SECRET_NAME = '+repr(value))
                    with self.assertRaises(ValueError) as caught:exec(compile(code,'<config>','exec'),{})
                    self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',str(caught.exception))

    def test_notebooks_parse_and_default_selection_remains_compatible(self):
        for kind in ['graph','labor']:
            nb,config,_=self.sources(kind);scope={}
            exec(compile(config,'<config>','exec'),scope)
            self.assertEqual(scope['GEMINI_SECRET_NAME'],'GEMINI_API_KEY')
            for cell in nb['cells']:
                if cell['cell_type']=='code':ast.parse(''.join(cell['source']))

if __name__=='__main__':unittest.main()
