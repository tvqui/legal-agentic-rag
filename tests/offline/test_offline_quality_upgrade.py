from pathlib import Path
import contextlib,hashlib,io,json,tempfile,unittest
from unittest.mock import Mock,patch
from vn_labor_offline.ai_requests import AIRequests,source_chunks,error_details
from vn_labor_offline.ai_enrichment import cached_structured
from vn_labor_offline.page_content import pdf_note_candidates,align_notes,validated_notes,mask_segment_notes,native_form_layer
from vn_labor_offline.legal_structure import parse_legal_document
from vn_labor_offline.cases import enrich_case_ontology
from vn_labor_offline.checklists import ai_checklist

SCHEMA={'type':'object','properties':{'items':{'type':'array','items':{'type':'string'}}},'required':['items']}


class Provider:
    model='fixture'; timeout=1
    def __init__(self): self.calls=[]; self.fail_large=False
    def structured(self,system,user,schema):
        value=json.loads(user); self.calls.append(value)
        if self.fail_large and len(value['source'].encode())>1800: raise TimeoutError('token=SECRET_NEVER_LOG')
        return {'items':[]}


class OfflineQualityUpgradeTests(unittest.TestCase):
    def requests(self,directory,provider,**settings):
        root=Path(directory); cfg={'project_root':root,'knowledge':{'ai_cache_dir':'cache',**settings}}
        return AIRequests(provider,cfg,root,'checklists')

    def test_utf8_chunks_cover_every_character_with_bounded_bytes(self):
        text=('Người lao động được hưởng quyền lợi.\n'*120)+'KẾT LUẬN CUỐI'
        coverage=set()
        for offset,chunk in source_chunks(text,1500):
            self.assertEqual(text[offset:offset+len(chunk)],chunk)
            self.assertLessEqual(len(chunk.encode()),1500);coverage.update(range(offset,offset+len(chunk)))
        self.assertEqual(len(coverage),len(text))

    def test_final_chunk_does_not_generate_tiny_tail_requests(self):
        chunks=list(source_chunks('abc. remainder. FINAL',3500))
        self.assertEqual(chunks,[(0,'abc. remainder. FINAL')])

    def test_timeout_splits_and_resume_does_not_retry_failed_parent(self):
        provider=Provider();provider.fail_large=True
        with tempfile.TemporaryDirectory() as t,contextlib.redirect_stdout(io.StringIO()):
            requests=self.requests(t,provider,ai_chunk_bytes=3000)
            rows,errors,planned=requests.generate('system',{'source':'x'*2900},SCHEMA,'p')
            self.assertFalse(errors);self.assertEqual(planned,len(rows));self.assertGreater(len(rows),1)
            coverage=set()
            for row in rows:coverage.update(range(row['source_offset'],row['source_offset']+len(row['source'])))
            self.assertEqual(len(coverage),2900)
            previous=len(provider.calls)
            resumed=self.requests(t,provider,ai_chunk_bytes=3000)
            again,errors,_=resumed.generate('system',{'source':'x'*2900},SCHEMA,'p')
            self.assertEqual(len(provider.calls),previous);self.assertEqual(resumed.network_calls,0)
            self.assertEqual(len(again),len(rows));self.assertFalse(errors)
            logs=(Path(t)/'reports/offline_ai_requests.jsonl').read_text(encoding='utf-8')
            self.assertIn('AI_REQUEST_TIMEOUT',logs);self.assertNotIn('SECRET_NEVER_LOG',logs)

    def test_unrecoverable_failure_is_not_reported_complete(self):
        provider=Provider();provider.structured=Mock(side_effect=TimeoutError())
        with tempfile.TemporaryDirectory() as t,contextlib.redirect_stdout(io.StringIO()):
            request=self.requests(t,provider,ai_max_consecutive_failures=1)
            rows,errors,planned=request.generate('s',{'source':'body'},SCHEMA,'p')
            self.assertFalse(rows);self.assertEqual(planned,1)
            self.assertEqual(errors[0]['reason'],'AI_REQUEST_TIMEOUT');self.assertEqual(request.stop_reason,'AI_CIRCUIT_OPEN')

    def test_cached_success_remains_available_after_circuit_opens(self):
        provider=Provider()
        with tempfile.TemporaryDirectory() as t,contextlib.redirect_stdout(io.StringIO()):
            request=self.requests(t,provider,ai_max_consecutive_failures=1)
            request.generate('s',{'source':'cached'},SCHEMA,'p')
            provider.structured=Mock(side_effect=TimeoutError())
            request.generate('s',{'source':'bad'},SCHEMA,'b')
            rows,errors,_=request.generate('s',{'source':'cached'},SCHEMA,'p')
            self.assertTrue(rows);self.assertFalse(errors);self.assertEqual(provider.structured.call_count,1)
            self.assertEqual(request.stop_reason,'AI_CIRCUIT_OPEN')

    def test_stage_budget_prevents_new_network_calls(self):
        provider=Provider()
        with tempfile.TemporaryDirectory() as t,contextlib.redirect_stdout(io.StringIO()):
            request=self.requests(t,provider,ai_checklist_budget_seconds=.01)
            rows,errors,_=request.generate('s',{'source':'body'},SCHEMA,'p')
            self.assertFalse(rows);self.assertFalse(provider.calls)
            self.assertEqual(errors[0]['reason'],'AI_STAGE_BUDGET_EXHAUSTED')

    def test_schema_invalid_output_not_cached(self):
        provider=Provider();provider.structured=Mock(return_value={'wrong':True})
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):cached_structured(provider,'s',{},SCHEMA,Path(t),'p')
            self.assertFalse(list(Path(t).glob('*.json')))

    def test_exception_chain_preserves_reason_without_credentials(self):
        from vn_labor_online.errors import LLMProviderError
        try:
            try:raise TimeoutError('Bearer SECRET')
            except TimeoutError as exc:raise LLMProviderError('API_KEY=SECRET') from exc
        except LLMProviderError as exc:result=error_details(exc)
        self.assertEqual(result['reason'],'AI_REQUEST_TIMEOUT');self.assertNotIn('SECRET',json.dumps(result))

    def fake_page(self,footnote_y=760,font_size=10):
        def line(text,y,size):return {'bbox':[40,y,550,y+15],'dir':(1,0),'spans':[{'text':text,'size':size}]}
        page=Mock();page.rect.height=842
        page.get_text.return_value={'blocks':[{'lines':[
            line('Điều 62. Quy định',200,14),line('d) Chi phí đào tạo;',225,14),
            line('33 Khoản này được sửa đổi, bổ sung.',footnote_y,font_size)]}]}
        return page

    def test_footnote_requires_margin_and_smaller_font(self):
        self.assertEqual(len(pdf_note_candidates(self.fake_page())),1)
        self.assertFalse(pdf_note_candidates(self.fake_page(400)))
        self.assertFalse(pdf_note_candidates(self.fake_page(font_size=14)))

    def test_note_alignment_preserves_exact_text_and_offsets(self):
        text='Điều 62. Quy định\n2. Nội dung:\nd) Chi phí đào tạo;\n33 Khoản này được sửa đổi, bổ sung.\ne) Trách nhiệm.'
        candidates=pdf_note_candidates(self.fake_page())
        notes=align_notes(candidates,text,1,'source-sha',0)
        doc={'text':text,'sha256':'source-sha','non_body_annotations':notes,
            'page_provenance':[{'page':1,'text_start':0,'text_end':len(text)}]}
        valid=validated_notes(doc);self.assertEqual(len(valid),1)
        masked=mask_segment_notes(text,valid)
        self.assertEqual(len(masked),len(text));self.assertEqual(masked.count('\n'),text.count('\n'))
        parsed=parse_legal_document({'document_id':'d','effective_from':'2021-01-01'},text,valid)
        self.assertFalse(any('33 Khoản' in p['text'] for p in parsed))
        point=next(p for p in parsed if p.get('point_number')=='d')
        self.assertEqual(text[point['char_start']:point['char_end']],point['text'])
        self.assertIn('33 Khoản',doc['text'])

    def test_tampered_note_or_source_sha_does_not_mask_body(self):
        text='33 Khoản này được sửa đổi, bổ sung.'
        notes=align_notes(pdf_note_candidates(self.fake_page()),text,1,'sha',0)
        doc={'text':text,'sha256':'different','non_body_annotations':notes,
            'page_provenance':[{'page':1,'text_start':0,'text_end':len(text)}]}
        self.assertFalse(validated_notes(doc))
        doc['sha256']='sha';notes[0]['text_sha256']='tampered'
        self.assertFalse(validated_notes(doc))

    def test_digital_form_not_scanned_or_signature_layer_can_keep_native(self):
        text='Mẫu số 11\n'+('Tên ngân hàng và thông tin tài khoản: .................\n'*12)
        page=self.fake_page()
        self.assertTrue(native_form_layer(page,text,0))
        self.assertFalse(native_form_layer(page,text,.9))
        self.assertFalse(native_form_layer(page,'Ký bởi cơ quan ........',0))
        self.assertFalse(native_form_layer(page,text.replace('Mẫu số 11','Nội dung luật'),0))

    def test_interrupted_checklist_keeps_remaining_heuristic_baseline(self):
        from vn_labor_offline.checklists import build_checklists,AIItems
        provisions=[{'provision_id':p,'document_id':'d','text':'Người lao động được nghỉ hằng năm theo quy định.'} for p in ['a','b']]
        def baseline(p,*args):
            return [{'provision_id':p['provision_id'],'source_text':p['text'],'type':'PERMISSION',
                'generator':'heuristic','provenance_status':'VERIFIED','question':'Có quyền nghỉ không?'}]
        provider=Provider()
        with tempfile.TemporaryDirectory() as t,contextlib.redirect_stdout(io.StringIO()):
            cfg={'project_root':Path(t),'knowledge':{'ai_cache_dir':'cache','ai_max_provisions':2}}
            with patch('vn_labor_offline.checklists.provider_from_config',return_value=provider), \
                 patch('vn_labor_offline.checklists.heuristic_checklist',side_effect=baseline), \
                 patch('vn_labor_offline.checklists.ai_checklist',side_effect=[AIItems([],[],1,1),KeyboardInterrupt()]):
                with self.assertRaises(KeyboardInterrupt):
                    build_checklists(provisions,cfg,Path(t),mode='hybrid_ai')
            saved=[json.loads(line) for line in (Path(t)/'04_knowledge/diagnostic_checklists.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual({row['provision_id'] for row in saved},{'a','b'})

    def test_partial_case_results_preserve_all_case_records(self):
        provider=Mock(model='fixture');provider.structured.side_effect=TimeoutError()
        cases=[{'case_id':'a','facts':'small body','features':[]},{'case_id':'b','facts':'another body','features':[]}]
        with tempfile.TemporaryDirectory() as t,contextlib.redirect_stdout(io.StringIO()):
            cfg={'project_root':Path(t),'knowledge':{'ai_cache_dir':'cache','ai_max_consecutive_failures':1}}
            with patch('vn_labor_offline.cases.provider_from_config',return_value=provider):
                enrich_case_ontology(cases,cfg,Path(t))
            saved=[json.loads(l) for l in (Path(t)/'03_structure/cases.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(saved),2)
            report=json.loads((Path(t)/'reports/case_ai_quality.json').read_text(encoding='utf-8'))
            self.assertFalse(report['complete']);self.assertEqual(report['ai_attempted'],1)

if __name__=='__main__':unittest.main()
