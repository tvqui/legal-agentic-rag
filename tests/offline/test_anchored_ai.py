from pathlib import Path
import contextlib, hashlib, importlib.util, io, json, tempfile, unittest
from unittest.mock import patch, Mock
from vn_labor_offline.ai_requests import AIRequests
from vn_labor_offline.ai_enrichment import cached_structured,validate_structured
from vn_labor_offline.anchored_ai import anchors,repair_grounding,request_fragment
from vn_labor_offline.cases import CASE_FEATURE_SCHEMA,enrich_case_ontology
from vn_labor_offline.evidence import locate_document_evidence


class Provider:
    model='fixture'; timeout=1
    def __init__(self): self.calls=[]
    def structured(self,system,user,schema):
        payload=json.loads(user);self.calls.append(payload)
        return {'features':[{'type':'OUTCOME','value':'Giữ đúng số tiền 1.000 đồng.',
            'source_quote':payload['source_excerpts'][0]['id']}]}


class AnchoredAITests(unittest.TestCase):
    def requests(self,temp,provider,**extra):
        root=Path(temp)
        return AIRequests(provider,{'project_root':root,'knowledge':{'ai_cache_dir':'cache',
            'ai_compact_output':True,'ai_grounding_repair':True,'ai_max_split_depth':3,**extra}},root,'case_ontology')

    def test_anchors_keep_numbers_and_exact_character_offsets(self):
        source='l không phải 1; 1.000 đồng, 45 ngày.\n' * 30
        seen=set()
        for item in anchors(source):
            self.assertEqual(source[item['start']:item['end']],item['text'])
            self.assertLessEqual(len(item['text']),200)
            seen.update(range(item['start'],item['end']))
        self.assertTrue(all(index in seen for index,char in enumerate(source) if not char.isspace()))

    def test_model_selects_id_and_original_text_is_restored_without_rewriting(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            provider=Provider();request=self.requests(temp,provider)
            source='Tòa án buộc thanh toán 1.000 đồng.\n'
            rows,errors,_=request.generate('system',{'source':source},CASE_FEATURE_SCHEMA,'case')
            self.assertFalse(errors);self.assertEqual(rows[0]['data']['features'][0]['source_quote'],source)
            self.assertIn('source_excerpts',provider.calls[0])

    def test_string_limits_are_enforced_before_caching(self):
        with self.assertRaisesRegex(ValueError,'AI_SCHEMA_STRING_LIMIT'):
            validate_structured('x'*201,{'type':'string','maxLength':200})

    def test_legacy_cache_is_reused_without_a_network_call(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            provider=Provider();request=self.requests(temp,provider)
            payload={'source':'Nguồn nguyên văn','source_offset':0}
            provider.structured=Mock(return_value={'features':[{'type':'OUTCOME','value':'Kết quả',
                'source_quote':payload['source']}]})
            cached_structured(provider,'system',payload,CASE_FEATURE_SCHEMA,request.cache,'case')
            provider.structured=Mock(side_effect=AssertionError('Must not call provider'))
            data,_=request_fragment(request,'system',payload,CASE_FEATURE_SCHEMA,'case')
            self.assertEqual(data['features'][0]['source_quote'],payload['source'])
            provider.structured.assert_not_called()

    def test_adaptive_split_covers_source_and_length_failures_do_not_open_provider_circuit(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            provider=Provider();calls=[]
            def generate(system,user,schema):
                payload=json.loads(user);calls.append(payload)
                if len(payload['source'])>600: raise RuntimeError('AI_OUTPUT_TOKEN_LIMIT')
                return {'features':[]}
            provider.structured=generate;request=self.requests(temp,provider,ai_max_consecutive_failures=1)
            source='x'*2900
            rows,errors,planned=request.generate('system',{'source':source},CASE_FEATURE_SCHEMA,'case')
            self.assertFalse(errors);self.assertEqual(planned,len(rows));self.assertIsNone(request.stop_reason)
            covered=set()
            for row in rows:covered.update(range(row['source_offset'],row['source_offset']+len(row['source'])))
            self.assertEqual(len(covered),len(source))
            previous=len(calls);again=self.requests(temp,provider)
            resumed,errors,_=again.generate('system',{'source':source},CASE_FEATURE_SCHEMA,'case')
            self.assertFalse(errors);self.assertEqual(previous,len(calls));self.assertEqual(len(rows),len(resumed))

    def test_saturated_leaf_is_not_reported_complete(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            provider=Provider()
            provider.structured=lambda system,user,schema:{'features':[
                {'type':'OUTCOME','value':str(index),'source_quote':'S1'} for index in range(4)]}
            rows,errors,_=self.requests(temp,provider).generate('system',{'source':'Đoạn ngắn.'},CASE_FEATURE_SCHEMA,'case')
            self.assertEqual(len(rows[0]['data']['features']),4)
            self.assertEqual(errors[0]['reason'],'AI_FRAGMENT_CAPACITY_REACHED')

    def test_unknown_source_id_is_rejected_and_not_cached(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            provider=Provider();provider.structured=lambda *args:{'features':[{
                'type':'OUTCOME','value':'Sai','source_quote':'S999'}]}
            request=self.requests(temp,provider)
            rows,errors,_=request.generate('system',{'source':'Nguồn ngắn.'},CASE_FEATURE_SCHEMA,'case')
            self.assertFalse(rows);self.assertEqual(errors[0]['reason'],'AI_INVALID_STRUCTURED_OUTPUT')
            self.assertFalse(list(request.cache.glob('*.json')))

    def test_grounding_repair_preserves_valid_items_and_is_resumable(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            provider=Provider();request=self.requests(temp,provider)
            source='Tòa án chấp nhận yêu cầu thanh toán 1.000 đồng.'
            good={'type':'CLAIM_OR_REMEDY','value':'Yêu cầu thanh toán','source_quote':'yêu cầu thanh toán'}
            bad={'type':'OUTCOME','value':'Nội dung cần kiểm','source_quote':'nội dung không có trong nguồn'}
            response={'source_offset':0,'source':source,'data':{'features':[good,bad]}}
            def valid(item,row):return locate_document_evidence(item['source_quote'],row['source'])[2]=='RESOLVED'
            rows,errors=repair_grounding(request,'system',{'source':source},CASE_FEATURE_SCHEMA,'case',[response],[],valid)
            self.assertFalse(errors);self.assertIn(good,rows[0]['data']['features']);self.assertEqual(len(provider.calls),1)
            again,errors=repair_grounding(request,'system',{'source':source},CASE_FEATURE_SCHEMA,'case',[response],[],valid)
            self.assertFalse(errors);self.assertEqual(len(provider.calls),1);self.assertEqual(rows,again)

    def test_empty_repair_keeps_incomplete_status(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            provider=Provider();provider.structured=lambda *args:{'features':[]}
            request=self.requests(temp,provider);source='Nguồn thực tế.'
            response={'source_offset':0,'source':source,'data':{'features':[
                {'type':'OUTCOME','value':'Sai','source_quote':'Không có'}]}}
            rows,errors=repair_grounding(request,'system',{'source':source},CASE_FEATURE_SCHEMA,'case',[response],[],lambda item,row:False)
            self.assertFalse(rows[0]['data']['features']);self.assertEqual(errors[0]['rejected_items'],1)
            self.assertEqual(errors[0]['reason'],'AI_GROUNDING_REPAIR_INCOMPLETE')

    def test_resume_drops_features_bound_to_a_different_source(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(temp);provider=Provider()
            cases=[{'case_id':'case','facts':'Nguồn mới.', 'features':[
                {'type':'OUTCOME','value':'Sai nguồn','source_quote':'Nguồn cũ.',
                 'generator':'structured-ai:fixture','evidence_span':{
                 'coordinate_space':'CASE_SOURCE_TEXT','source_sha256':'old','char_start':0,'char_end':9}}]}]
            cfg={'project_root':root,'knowledge':{'ai_cache_dir':'cache'}}
            with patch('vn_labor_offline.cases.provider_from_config',return_value=provider),\
                 patch.object(AIRequests,'generate',return_value=([],[{'reason':'AI_STAGE_BUDGET_EXHAUSTED'}],1)):
                result=enrich_case_ontology(cases,cfg,root)
            self.assertFalse(result[0]['features'])
            report=json.loads((root/'reports/case_ai_quality.json').read_text())
            self.assertEqual(report['complete_cases'],0);self.assertFalse(report['complete'])

    def test_resume_refuses_changed_corpus_before_technical_audit(self):
        repo=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('final_remote_fixture',repo/'kaggle/offline_final_remote.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'artifacts/01_extracted';out.mkdir(parents=True)
            (out/'documents.jsonl').write_text(json.dumps({'file_id':'old','sha256':'old','relative_path':'a.pdf'})+'\n')
            cfg={'data_dir':root/'data','output_dir':root/'artifacts'}
            with patch('vn_labor_offline.config.load_yaml',return_value=cfg),\
                 patch('vn_labor_offline.config.resolve_paths',return_value=cfg),\
                 patch('vn_labor_offline.scanner.scan',return_value=[{'file_id':'new','sha256':'new','relative_path':'a.pdf'}]),\
                 patch.object(module,'_technical_audit') as audit:
                with self.assertRaisesRegex(RuntimeError,'identity mismatch'):module._resume_integrity(root/'config.yaml')
                audit.assert_not_called()

    def test_changed_index_metadata_stops_enrichment_before_any_ai_call(self):
        from vn_labor_offline.pipeline import rerun_enrichment
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(temp);cfg={'project_root':root,'output_dir':root}
            with patch('vn_labor_offline.pipeline.load_stage',return_value=[]),\
                 patch('vn_labor_offline.pipeline.enrich_provenance',return_value=[]),\
                 patch('vn_labor_offline.integrity.require_complete_provenance'),\
                 patch('vn_labor_offline.pipeline.build_hierarchy_headings'),\
                 patch('vn_labor_offline.pipeline.materialize_provision_versions',return_value=([],[])),\
                 patch('vn_labor_offline.pipeline.build_retrieval_units',return_value=[{'unit_id':'changed'}]),\
                 patch('vn_labor_offline.pipeline.enrich_case_ontology') as case_ai,\
                 patch('vn_labor_offline.pipeline.build_checklists') as checklist_ai:
                with self.assertRaisesRegex(RuntimeError,'rebuild technical indexes before AI'):
                    rerun_enrichment(cfg,mode='hybrid_ai')
                case_ai.assert_not_called();checklist_ai.assert_not_called()

if __name__=='__main__':unittest.main()
