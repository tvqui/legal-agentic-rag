"""Regression checks for long Kaggle builds; no GPU/network needed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
import zipfile
from vn_labor_offline.integrity import require_complete_extraction
from vn_labor_offline.ai_enrichment import cached_structured
from vn_labor_offline.cases import source_chunks,enrich_case_ontology
from vn_labor_offline.indexes import build_retrieval_units
from vn_labor_offline.legal_structure import parse_legal_document
from vn_labor_offline.util import write_jsonl

ROOT=Path(__file__).resolve().parents[2]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    value=importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
runner=module('final_runner_integrity','kaggle/offline_final_remote.py')
bootstrap=module('bootstrap_integrity','kaggle/bootstrap.py')

class OfflineIntegrityTests(unittest.TestCase):
    def test_unreadable_page_stops_before_indexes(self):
        with tempfile.TemporaryDirectory() as t:
            rows=[{'file_id':'f','text':'body','page_provenance':[{'page':1,'ocr_status':'FAILED'}]}]
            with self.assertRaises(RuntimeError): require_complete_extraction(rows,Path(t))
            self.assertFalse(json.loads((Path(t)/'reports/extraction_integrity.json').read_text())['passed'])

    def test_cleaning_loss_stops_build(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(RuntimeError):
                require_complete_extraction([{'file_id':'f','text':'body','page_provenance':[
                    {'page':1,'page_quality_status':'ERROR'}]}],Path(t))

    def test_count_mismatch_and_duplicate_document_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            for rows in ([{'file_id':'f','text':'body','page_count':2,'page_provenance':[{}]}],
                         [{'file_id':'f','text':'body'}]*2,[]):
                with self.assertRaises(RuntimeError): require_complete_extraction(rows,Path(t))

    def test_technical_audit_cannot_reuse_stale_pass(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); (p/'final_outputs_validation.json').write_text('{"checks":[{"passed":true}]}')
            with patch.object(runner,'REPORTS',p),patch.object(runner,'_run',return_value=1):
                with self.assertRaisesRegex(RuntimeError,'did not create'): runner._technical_audit()

    def test_incomplete_audit_stage_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            def audit(*a,**kw):
                (p/'final_outputs_validation.json').write_text(json.dumps({'checks':[{'stage':'graph','passed':True}]}))
                return 1
            with patch.object(runner,'REPORTS',p),patch.object(runner,'_run',side_effect=audit):
                with self.assertRaises(RuntimeError): runner._technical_audit()

    def test_valid_local_audit_accepts_only_missing_live_aura(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            def audit(*a,**kw):
                checks=[{'stage':s,'passed':True,'check':'files'} for s in ['registry','structure','graph','indexes']]
                checks.append({'stage':'indexes','passed':False,'check':'Neo4j live verification'})
                (p/'final_outputs_validation.json').write_text(json.dumps({'checks':checks})); return 1
            with patch.object(runner,'REPORTS',p),patch.object(runner,'_run',side_effect=audit):
                self.assertTrue(runner._technical_audit()['passed'])

    def test_broken_ai_cache_retried_and_prompt_change_invalidates(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); provider=Mock(model='model'); provider.structured.return_value={'value':'ok'}
            schema={'type':'object','properties':{'value':{'type':'string'}},'required':['value']}
            cached_structured(provider,'first',{},schema,p,'id')
            next(p.glob('*.json')).write_text('{broken')
            self.assertEqual(cached_structured(provider,'first',{},schema,p,'id'),{'value':'ok'})
            cached_structured(provider,'second',{},schema,p,'id')
            self.assertEqual(provider.structured.call_count,3)

    def test_invalid_schema_never_cached(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); provider=Mock(model='model'); provider.structured.return_value={'wrong':True}
            with self.assertRaises(ValueError):
                cached_structured(provider,'s',{}, {'type':'object','required':['items']},p,'id')
            self.assertFalse(list(p.glob('*.json')))

    def test_long_case_chunks_cover_final_decision_and_every_character(self):
        source='Nội dung vụ án. '*9000+'FINAL COURT OUTCOME'
        chunks=list(source_chunks(source,3000)); covered=set()
        for start,chunk in chunks:
            self.assertLessEqual(len(chunk.encode('utf-8')),3000)
            self.assertEqual(source[start:start+len(chunk)],chunk)
            covered.update(range(start,start+len(chunk)))
        self.assertEqual(len(covered),len(source)); self.assertIn('FINAL COURT OUTCOME',chunks[-1][1])

    def test_quote_not_in_sent_chunk_cannot_become_feature(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); case={'case_id':'c','facts':'a'*18000,'decision':'COURT DECISION','features':[]}
            provider=Mock(model='model'); provider.structured.return_value={'features':[
                {'type':'OUTCOME','value':'outcome','source_quote':'COURT DECISION'}]}
            cfg={'project_root':p,'knowledge':{'ai_cache_dir':'cache'}}
            with patch('vn_labor_offline.cases.provider_from_config',return_value=provider):
                result=enrich_case_ontology([case],cfg,p)
            self.assertTrue(result[0]['features'])
            self.assertTrue(all(row['source_chunk_offset']>0 for row in result[0]['features']))

    def test_case_failure_circuit_stops_repeated_calls(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); cfg={'project_root':p,'knowledge':{'ai_cache_dir':'cache','ai_max_consecutive_failures':2}}
            provider=Mock(model='m'); provider.structured.side_effect=TimeoutError()
            with patch('vn_labor_offline.cases.provider_from_config',return_value=provider):
                result=enrich_case_ontology([{'case_id':str(i),'facts':'case body','features':[]} for i in range(5)],cfg,p)
            self.assertEqual(len(result),5); self.assertEqual(provider.structured.call_count,2)
            self.assertTrue(json.loads((p/'reports/case_ai_quality.json').read_text())['circuit_open'])

    def test_short_legal_locators_remain_retrievable(self):
        doc={'document_id':'d','document_number':'n','document_type':'LAW','title':'Law'}
        text='Điều 124. Hình thức xử lý kỷ luật lao động\n1. Khiển trách.\n2. Kéo dài thời hạn nâng lương không quá 06 tháng.\n3. Cách chức.\n4. Sa thải.'
        provisions=parse_legal_document(doc,text)
        units=build_retrieval_units(provisions,[],[doc])
        self.assertEqual({p['provision_id'] for p in provisions},{u['unit_id'] for u in units})
        self.assertEqual(len([u for u in units if u.get('clause_number')]),4)

    def test_full_ancestor_context_survives(self):
        doc={'document_id':'d','document_number':'n','title':'Law'}
        parent={'provision_id':'a','document_id':'d','parent_id':'d','text':'scope '*1000+'EXCEPTION_AT_END','level':'ARTICLE','number':'1'}
        child={'provision_id':'b','document_id':'d','parent_id':'a','text':'a) rule;','level':'POINT','number':'a'}
        units=build_retrieval_units([parent,child],[],[doc])
        self.assertIn('EXCEPTION_AT_END',units[1]['ancestor_context'])

    def test_restore_duplicate_zip_rejected_before_extract(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); archive=p/'input.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('artifacts/a','first'); z.writestr('artifacts/a','second')
            with self.assertRaises(ValueError): bootstrap.restore_artifacts(archive,p)
            self.assertFalse((p/'artifacts').exists())

    def test_checkpoint_survives_ollama_setup_failure(self):
        import contextlib,sys,types
        events=[]
        @contextlib.contextmanager
        def fail(*a,**kw):
            events.append('ollama'); raise RuntimeError('MODEL_DOWNLOAD_FAILED'); yield
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); reports=p/'reports'
            with patch.object(runner,'ROOT',p),patch.object(runner,'REPORTS',reports),\
                 patch.object(runner,'STATE',reports/'state.json'),patch.object(runner,'RUN',reports/'run.json'),\
                 patch.object(runner,'_run',return_value=0),patch.object(runner,'_technical_audit',return_value={'passed':True}),\
                 patch.object(runner,'_configure_ai'),patch.object(runner,'_export',side_effect=lambda n:events.append(n)),\
                 patch.dict(sys.modules,{'ollama_offline':types.SimpleNamespace(session=fail)}),\
                 patch.dict('os.environ',{'VN_LABOR_OFFLINE_AI_PROVIDER':'ollama'}),\
                 patch.object(runner.sys,'argv',['runner','--ai-max-provisions','1']):
                with self.assertRaisesRegex(RuntimeError,'MODEL_DOWNLOAD_FAILED'): runner.main()
            self.assertEqual(events,['vn_labor_results_technical_checkpoint.zip','ollama','vn_labor_results_recovery.zip'])
            self.assertEqual(json.loads((reports/'run.json').read_text())['pipeline_exit_code'],1)


    def test_hybrid_ai_excludes_oversized_prompts_without_truncating_source(self):
        from vn_labor_offline.checklists import select_hybrid_ai_ids
        prepared=[({'provision_id':'large','text':'x'*10000},[{}],()),
                  ({'provision_id':'small','text':'x'*200},[{}],())]
        self.assertEqual(select_hybrid_ai_ids(prepared,2,1000),{'small'})

    def test_bad_extraction_settings_cannot_reuse_cached_document(self):
        from vn_labor_offline.extract import _cache_matches_current_sources,EXTRACTION_SCHEMA
        row={'file_id':'f','sha256':'s','_extraction_settings_fingerprint':'new'}
        cached={'file_id':'f','sha256':'s','text':'body','extraction_schema':EXTRACTION_SCHEMA,
                'extraction_settings_fingerprint':'old','page_provenance':[]}
        self.assertFalse(_cache_matches_current_sources(cached,row,{},{}))

    def test_page_quality_error_is_not_a_cache_hit(self):
        from vn_labor_offline.extract import _cache_matches_current_sources,EXTRACTION_SCHEMA
        row={'file_id':'f','sha256':'s'}
        cached={'file_id':'f','sha256':'s','text':'body','extraction_schema':EXTRACTION_SCHEMA,
                'page_provenance':[{'page':1,'page_quality_status':'ERROR'}]}
        self.assertFalse(_cache_matches_current_sources(cached,row,{},{}))


    def test_corrupt_full_download_restarts_and_bad_metadata_recovers(self):
        import hashlib
        downloader=module('dense_download_integrity','scripts/prepare_dense_model.py')
        body=b'GOOD'
        info={'sha':downloader.REVISION,'siblings':[{'rfilename':'config.json','size':4,
            'lfs':{'sha256':hashlib.sha256(body).hexdigest()}}]}
        response=Mock(status_code=200,headers={})
        response.json.return_value=info; response.iter_content.return_value=[body]
        download=Mock(status_code=200,headers={}); download.iter_content.return_value=[body]
        manager=Mock(); manager.__enter__=Mock(return_value=download);manager.__exit__=Mock(return_value=False)
        session=Mock();session.get.side_effect=[response,manager]
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); model=p/'model';model.mkdir()
            (model/'source.json').write_text('{broken')
            (model/'config.json.download').write_bytes(b'BAD!')
            with patch.object(downloader,'ROOT',p),patch.object(downloader,'MODEL',model),\
                 patch.object(downloader,'FILES',['config.json']),patch.object(downloader.requests,'Session',return_value=session):
                downloader.main()
            self.assertEqual((model/'config.json').read_bytes(),body)
            self.assertEqual(session.get.call_args_list[1].kwargs['headers'],{})


    def test_ollama_setup_timeout_terminates_owned_process(self):
        runtime=module('ollama_runtime_integrity','kaggle/ollama_offline.py')
        process=Mock(pid=123);process.poll.return_value=None
        with tempfile.TemporaryDirectory() as t:
            with patch.object(runtime.subprocess,'Popen',return_value=process),\
                 patch.object(runtime.time,'monotonic',side_effect=[0,100]),\
                 patch.object(runtime.time,'sleep'),patch.object(runtime.os,'killpg',create=True) as kill:
                with self.assertRaises(TimeoutError):
                    runtime.bounded_command(['ollama','pull','model'],{},Path(t)/'pull.log',50)
            kill.assert_called_once();process.wait.assert_called_once()

    def test_existing_ollama_is_not_reused_with_unknown_gpu(self):
        runtime=module('ollama_existing_integrity','kaggle/ollama_offline.py')
        response=Mock();response.__enter__=Mock();response.__exit__=Mock(return_value=False)
        with tempfile.TemporaryDirectory() as t:
            with patch.object(runtime.shutil,'which',return_value='/usr/bin/ollama'),\
                 patch.object(runtime.urllib.request,'urlopen',return_value=response),\
                 patch.object(runtime.subprocess,'Popen') as spawn:
                with self.assertRaisesRegex(RuntimeError,'already runs'):
                    with runtime.session(Path(t),'model'): pass
            spawn.assert_not_called()


    def test_interrupted_jsonl_write_preserves_complete_previous_stage(self):
        def broken():
            yield {'new':1}
            raise RuntimeError('interrupted')
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'stage.jsonl';write_jsonl(p,[{'old':1}])
            with self.assertRaises(RuntimeError): write_jsonl(p,broken())
            self.assertEqual(p.read_text().strip(),'{'+'"old": 1'+'}')
            self.assertEqual(len(list(Path(t).iterdir())),1)

    def test_recovery_export_survives_corrupt_report_and_excludes_temporary(self):
        remote=module('remote_recovery_integrity','kaggle/remote.py')
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'project';out=p/'artifacts';(out/'reports').mkdir(parents=True)
            (out/'reports/summary.json').write_text('{broken')
            (out/'reports/kaggle_run.json').write_text('{"pipeline_exit_code":1}')
            (out/'vectors.npy.tmp').write_text('partial')
            with patch.object(remote,'ROOT',p),patch.object(remote,'OUT',out):
                remote.export('vn_labor_results_recovery.zip')
            with zipfile.ZipFile(p.parent/'vn_labor_results_recovery.zip') as z:
                self.assertNotIn('artifacts/vectors.npy.tmp',z.namelist())
                self.assertIn('CHƯA ĐẠT',z.read('artifacts/reports/tong_hop_sau_chay.md').decode('utf-8'))

if __name__=='__main__': unittest.main()
