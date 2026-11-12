"""Model role boundaries; fake SDK only, no Google quota or model downloads."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import yaml

from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import AdjudicationConfig, ApplicabilityConfig, load_config
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.gemini_quota import GeminiRatePolicy
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.providers import GeminiProvider


class ModelRoleTests(unittest.TestCase):
    def load(self, role, original, env):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.yaml'
            path.write_text(yaml.safe_dump({'online':{'artifact_source':'fixture',role:original}}),encoding='utf-8')
            with patch.dict(os.environ,env,clear=True):
                return getattr(load_config(path),role)

    def test_explicit_role_env_wins_over_global_model(self):
        for role in ('researcher','applicability','adjudication'):
            with self.subTest(role=role):
                cfg=self.load(role,{'mode':'gemini','model':'yaml-model'},
                    {'GEMINI_MODEL':'global-model','VN_LABOR_'+role.upper()+'_MODEL':'role-model',
                     'GEMINI_API_KEY':'fixture-key'})
                self.assertEqual(cfg.model,'role-model')
                self.assertEqual(cfg.api_key,'fixture-key')

    def test_explicit_cloud_yaml_wins_and_legacy_provider_switch_uses_global(self):
        for role in ('researcher','applicability','adjudication'):
            cfg=self.load(role,{'mode':'gemini','model':'yaml-model'},{'GEMINI_MODEL':'global'})
            self.assertEqual(cfg.model,'yaml-model')
            cfg=self.load(role,{'mode':'ollama','model':'qwen3:8b'},
                          {'GEMINI_MODEL':'global','VN_LABOR_'+role.upper()+'_MODE':'gemini'})
            self.assertEqual(cfg.model,'global')

    def test_cloud_agents_keep_independent_review_and_fail_closed(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':'fixture-only'},clear=True):
            auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid',provider='gemini',model='audit'))
            judge=LegalAdjudicator(AdjudicationConfig(mode='gemini',model='draft',
                review_provider='gemini',review_model='review'))
        self.assertIsInstance(auditor.provider,GeminiProvider)
        self.assertEqual(judge.provider.model,'draft')
        self.assertEqual(judge.review_provider.model,'review')
        self.assertIsNot(judge.review_provider,judge.provider)
        self.assertTrue(judge.cfg.fail_closed)
        self.assertTrue(judge.cfg.semantic_review)

    def test_per_model_rpm_is_normalized_and_validated(self):
        env={'VN_LABOR_GEMINI_MODEL_RPM':json.dumps({'gemini-3.8-flash':4})}
        with patch.dict(os.environ,env,clear=True):
            self.assertEqual(GeminiRatePolicy.from_env('models/gemini-3.8-flash').rpm,4)
            self.assertEqual(GeminiRatePolicy.from_env('other').rpm,13)
        for invalid in ('[]','{"x":true}','{"x":0}','{"x":1.5}','{"x":2,"models/x":3}'):
            with self.subTest(invalid=invalid),patch.dict(os.environ,{'VN_LABOR_GEMINI_MODEL_RPM':invalid},clear=True):
                with self.assertRaises(ValueError): GeminiRatePolicy.from_env('x')

    def test_cloud_auditor_retains_deterministic_gate_before_model(self):
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='gemini',model='fixture'))
        with patch.object(auditor,'_hybrid',return_value=([],[],[])) as bounded, \
                patch.object(auditor,'_provider_per_item',side_effect=AssertionError('Must keep hard-rule gate')):
            self.assertEqual(auditor.audit([],'query',[],{}),([],[],[]))
        bounded.assert_called_once()

    def test_new_model_requests_omit_sampling_without_weakening_schema(self):
        try:
            from google import genai
        except ImportError:
            self.skipTest('Optional google-genai not installed')
        schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']}
        for model in ('gemini-3.1-flash-lite','gemini-3.5-flash-lite','models/gemini-3.8-flash'):
            with self.subTest(model=model),patch.dict(os.environ,{},clear=True):
                sdk=Mock()
                sdk.__enter__=Mock(return_value=sdk)
                sdk.__exit__=Mock(return_value=False)
                sdk.models.generate_content.return_value=SimpleNamespace(text='{"ok":true}',candidates=[])
                provider=GeminiProvider(model,'fixture-key')
                provider.rate_limiter=Mock()
                provider.rate_limiter.acquire.return_value=0
                with patch.object(genai,'Client',return_value=sdk):
                    self.assertEqual(provider.structured('system','user',schema),{'ok':True})
                    options=sdk.models.generate_content.call_args.kwargs['config']
                    self.assertEqual(options.temperature,0 if model.startswith('gemini-3.1') else None)
                    self.assertEqual(options.response_mime_type,'application/json')
                    self.assertIsNotNone(options.response_json_schema)
                    sdk.models.generate_content.return_value=SimpleNamespace(text='{"ok":"wrong-type"}',candidates=[])
                    with self.assertRaises(StructuredOutputError): provider.structured('system','user',schema)

    def test_profile_preserves_artifact_and_never_copies_credentials(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('role_profile',root/'scripts/configure_online_models.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)/'base.yaml'; output=Path(directory)/'experiment.yaml'
            source={'artifact_source':'artifact-fixture','expected_build_id':'unchanged',
                    'embedding_model':'BAAI/bge-m3','researcher':{'api_key':'must-not-copy'}}
            base.write_text(yaml.safe_dump({'online':source}),encoding='utf-8')
            models=dict(researcher='gemini-3.5-flash-lite',auditor='gemini-3.5-flash-lite',
                        adjudicator='gemini-3.5-flash-lite',reviewer='gemini-3.8-flash')
            module.create_config(base,output,**models)
            result=yaml.safe_load(output.read_text(encoding='utf-8'))['online']
            for key in ('artifact_source','expected_build_id','embedding_model'):
                self.assertEqual(result[key],source[key])
            self.assertNotIn('must-not-copy',output.read_text(encoding='utf-8'))
            self.assertTrue(result['adjudication']['semantic_review'])
            with self.assertRaises(FileExistsError): module.create_config(base,output,**models)
            with self.assertRaises(ValueError): module.create_config(base,base,**models)
            models['auditor']='gemma-4-31b-it'
            with self.assertRaises(ValueError): module.create_config(base,Path(directory)/'gemma.yaml',**models)
