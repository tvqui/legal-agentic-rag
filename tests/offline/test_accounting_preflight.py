import contextlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from vn_labor_offline.ai_preflight import probe


class AccountingPreflightTests(unittest.TestCase):
    def run_probe(self,valid):
        provider=Mock();provider.model='fixture';provider.timeout=1
        def inference(system,user,schema):
            data=json.loads(user)
            if 'requested_quote' in data:return {'quote':data['requested_quote']}
            return {'features':[],'source_coverage':{
                row['id']:{'status':'NO_ITEM','item_indexes':[],'reason':'Chỉ có tiêu đề.'}
                for row in data['source_excerpts']} if valid else {}}
        provider.structured.side_effect=inference
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);(root/'03_structure').mkdir()
            (root/'03_structure/cases.jsonl').write_text(json.dumps({'facts':'Một đoạn nguồn thực nghiệm đủ dài để kiểm tra hợp đồng đầu ra.'}),encoding='utf-8')
            cfg={'project_root':root,'output_dir':root,'knowledge':{
                'ai_source_accounting':True,'ai_cache_dir':'cache'}}
            with patch('vn_labor_offline.ai_preflight.provider_from_config',return_value=provider):return probe(cfg)

    def test_preflight_exercises_real_accounting_schema_before_long_job(self):
        result=self.run_probe(True)
        self.assertTrue(result['passed']);self.assertEqual(len(result['probes']),3)
        self.assertEqual(result['probes'][-1]['probe'],'source_accounting_v2')

    def test_broken_accounting_stops_preflight_even_when_old_quote_probes_pass(self):
        result=self.run_probe(False)
        self.assertFalse(result['passed']);self.assertTrue(all(r['passed'] for r in result['probes'][:2]))
