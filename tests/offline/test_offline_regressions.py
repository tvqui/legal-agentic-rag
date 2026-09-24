import copy,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from vn_labor_offline.metadata import find_doc_number,infer_issuer,infer_title,find_effective_from,build_registry,issuer_from_number
from vn_labor_offline.segmentation import segment_document
from vn_labor_offline.legal_structure import parse_legal_document,parse_all
from vn_labor_offline.relations import build_relation_edges,choose_document
from vn_labor_offline.temporal import instrument_key,temporal_eligible
from vn_labor_offline.indexes import build_retrieval_units
from vn_labor_offline.cleaning import clean_text
from vn_labor_offline.config import load_yaml,resolve_paths,validate_config,CONFIG_KEYS
from vn_labor_offline.neo4j_loader import validate_export,neo4j_properties,replace_transaction
from vn_labor_offline.util import read_jsonl
from vn_labor_offline.quality import quality_issues
from vn_labor_offline.graph_builder import build_graph,graph_parent_id
from vn_labor_offline.scanner import resolve_source_catalog
from vn_labor_offline.provision_versions import materialize_provision_versions
from vn_labor_offline.gold import validate_gold_record

ROOT=Path(__file__).resolve().parents[2]
LAW='Điều 35. Chấm dứt hợp đồng\n1. Người lao động có quyền chấm dứt hợp đồng.\n2. Người lao động phải tuân thủ điều kiện sau:\na) Báo trước đúng thời hạn theo quy định.\nb) Thông báo cho người sử dụng lao động.'


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.out=Path(self.tmp.name)
        self.cfg=resolve_paths(load_yaml(ROOT/'config/pipeline.yaml'),ROOT/'config/pipeline.yaml')
        self.cfg['output_dir']=self.out; self.cfg['project_root']=self.out
        self.doc={'document_id':'d','file_id':'f','sha256':'abc','relative_path':'laws/a.pdf','document_type':'LAW','source_group':'LEGAL_DOCUMENT','instrument_number':'45/2019/QH14','document_number':'45/2019/QH14','title':'Bộ luật Lao động','version_role':'ORIGINAL','authority_rank':100,'language':'vi','provenance':{'file_id':'f'},'version_id':'d'}
        self.raw={'file_id':'f','sha256':'abc','relative_path':'laws/a.pdf','filename':'45-2019-QH14.pdf','document_type_hint':'LAW','source_group':'LEGAL_DOCUMENT','binding_default':True,'text':LAW,'text_chars':len(LAW),'extension':'.pdf'}
    def tearDown(self): self.tmp.cleanup()
    def test_filename_identity_beats_cited_law(self):
        self.assertEqual(find_doc_number('Căn cứ 51/2001/QH10','45-2019-QH14_Lao-dong.pdf'),'45/2019/QH14')
    def test_bare_body_citation_is_not_own_number(self):
        self.assertEqual(find_doc_number('Căn cứ 05/2015/NĐ-CP','unknown.pdf'),'')
    def test_header_number(self):
        self.assertEqual(find_doc_number('Số: 06/2020/TT-BLĐTBXH\nCăn cứ 45/2019/QH14','unknown.pdf'),'06/2020/TT-BLĐTBXH')
        self.assertEqual(find_doc_number('Luật số: 10/2012/QH13','unknown.doc'),'10/2012/QH13')
    def test_catalog_cannot_override_identity(self):
        from vn_labor_offline.metadata import checked_metadata
        with self.assertRaises(ValueError): checked_metadata({'document_id':'other'})
    def test_catalog_sha_binding(self):
        (self.out/'config').mkdir()
        (self.out/'config/source_catalog.yaml').write_text(json.dumps({'sources':{self.raw['filename']:{'sha256':'wrong'}}}),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'SHA mismatch'): build_registry([self.raw],self.cfg,self.out)

    def test_source_catalog_resolution_is_complete_and_unverified_without_explicit_provenance(self):
        resolved=resolve_source_catalog([self.raw],self.out,self.out)
        self.assertEqual(len(resolved),1)
        self.assertEqual(resolved[0]['catalog_status'],'UNVERIFIED')
        self.assertIn('source_provider',resolved[0]['missing_fields'])
        self.assertTrue((self.out/'00_manifest/source_review_queue.jsonl').exists())

    def test_source_catalog_resolution_fails_closed_on_sha_mismatch(self):
        (self.out/'config').mkdir()
        (self.out/'config/source_catalog.yaml').write_text(
            json.dumps({'sources':{self.raw['relative_path']:{'sha256':'wrong'}}}),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'SHA mismatch'):
            resolve_source_catalog([self.raw],self.out,self.out)
    def test_judgment_identity(self):
        raw={**self.raw,'filename':'02-2025-LĐPT.pdf','source_group':'JUDICIAL','document_type_hint':'JUDGMENT','text':'Căn cứ 05/2015/NĐ-CP'}
        d=build_registry([raw],self.cfg,self.out)[0]
        self.assertEqual(d['case_number'],'02/2025/LĐPT'); self.assertEqual(d['document_number'],'')
        self.assertIn('05/2015/NĐ-CP',d['cited_document_numbers'])
    def test_identity_does_not_change_with_extraction(self):
        a=build_registry([self.raw],self.cfg,self.out)[0]
        b=build_registry([{**self.raw,'text':'a changed citation 41/2024/QH15'}],self.cfg,self.out)[0]
        self.assertEqual(a['document_id'],b['document_id'])
    def test_issuer_not_preamble(self):
        self.assertEqual(infer_issuer('BỘ LAO ĐỘNG - THƯƠNG BINH VÀ XÃ HỘI\nTHÔNG TƯ\nCăn cứ Luật của QUỐC HỘI'),'Bộ Lao động - Thương binh và Xã hội')
    def test_longest_issuer(self):
        self.assertEqual(infer_issuer('ỦY BAN THƯỜNG VỤ QUỐC HỘI'),'Ủy ban Thường vụ Quốc hội')
        self.assertEqual(issuer_from_number('45/2019/QH14'),'Quốc hội')
        self.assertEqual(issuer_from_number('145/2020/NĐ-CP'),'Chính phủ')
    def test_title_not_attachment(self):
        title=infer_title('THÔNG TƯ\nQuy định điều kiện lao động\nCăn cứ Luật\n(Ban hành kèm theo Thông tư...)',self.raw)
        self.assertNotIn('kèm theo',title); self.assertIn('điều kiện lao động',title)
    def test_historical_not_expired_by_folder(self):
        d=build_registry([{**self.raw,'document_type_hint':'HISTORICAL'}],self.cfg,self.out)[0]
        self.assertEqual(d['version_role'],'HISTORICAL'); self.assertEqual(d['instrument_type'],'LAW'); self.assertEqual(d['status'],'UNKNOWN')
    def test_consolidation_does_not_steal_underlying_number_or_date(self):
        raw={**self.raw,'filename':'18_VBHN-VPQH.pdf','document_type_hint':'CONSOLIDATED','source_group':'CONSOLIDATED','text':'45/2019/QH14\nLuật này có hiệu lực từ ngày 01 tháng 01 năm 2026.'}
        d=build_registry([raw],self.cfg,self.out)[0]
        self.assertEqual(d['instrument_number'],''); self.assertEqual(d['effective_from'],'')
    def test_effective_date_only_own_clause(self):
        self.assertEqual(find_effective_from('Văn bản khác có hiệu lực từ ngày 01/01/2026.'),'')
        self.assertEqual(find_effective_from('Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2021.'),'2021-01-01')
    def test_conflicting_dates_unresolved(self):
        self.assertEqual(find_effective_from('Luật này có hiệu lực từ ngày 01/01/2021. Luật này có hiệu lực từ ngày 01/01/2026.'),'')
    def test_effective_date_tolerates_ocr_but_rejects_embedded_subject(self):
        text=('Phụ lục của Nghị định này có hiệu lực từ ngày 01 tháng 01 năm 2021. '
              '1. Nghị định này có hiệu Iực thi hành tù ngày 30 tháng 1l năm 2025.')
        self.assertEqual(find_effective_from(text),'2025-11-30')
    def test_annex_is_not_clause(self):
        text=LAW+'\nPHỤ LỤC\n1. Họ và tên của người đăng ký.\n2. Ngày sinh của người đăng ký.'
        ps=parse_legal_document(self.doc,text)
        self.assertEqual(len(ps),5); self.assertFalse(any('Họ và tên' in p['text'] for p in ps))
        self.assertIn('ANNEX',{s['segment_type'] for s in segment_document(self.doc,text)})
    def test_preamble_attachment_phrase_not_boundary(self):
        parts=segment_document(self.doc,'THÔNG TƯ\nBan hành kèm theo Thông tư\n'+LAW)
        self.assertEqual([s['segment_type'] for s in parts],['PREAMBLE','MAIN_BODY'])
    def test_annex_reference_in_prose_not_boundary(self):
        parts=segment_document(self.doc,LAW+'\nPhụ lục này được áp dụng theo quy định.')
        self.assertEqual(len(parts),1)
    def test_keep_preamble_config(self):
        self.assertNotIn('PREAMBLE',[s['segment_type'] for s in segment_document(self.doc,'LUẬT\n'+LAW,False)])
    def test_cleaning_preserves_vietnamese_heading(self):
        text='NHỮNG QUY ĐỊNH CHUNG\nĐiều 1. Phạm vi\nNội dung\na) Điểm đầu'
        self.assertEqual(clean_text(text),text)
    def test_repair_glued_chapter_heading(self):
        ps=parse_legal_document(self.doc,'NHỮNG QUY ĐỊNH CHUNG Điều 1. Phạm vi\n1. Nội dung của quy định.')
        self.assertEqual(ps[0]['number'],'1')
    def test_line_start_citation_not_article(self):
        ps=parse_legal_document(self.doc,LAW+'\nĐiều 35 của Luật số 45/2019/QH14 được áp dụng.')
        self.assertEqual(sum(p['level']=='ARTICLE' for p in ps),1)
    def test_quoted_amendment_not_new_article(self):
        text='Điều 1. Sửa đổi quy định\n1. Sửa đổi như sau:\n“Điều 2. Quy định mới\n1. Nội dung được sửa đổi.”;\nĐiều 2. Hiệu lực\nLuật này có hiệu lực từ ngày 01/01/2026.'
        ps=parse_legal_document(self.doc,text)
        self.assertEqual([p['number'] for p in ps if p['level']=='ARTICLE'],['1','2'])
        self.assertEqual(sum(p['level']=='CLAUSE' for p in ps),1)
    def test_ambiguity_is_reported_not_renumbered(self):
        raw={**self.raw,'text':'Điều 1. Quy định\n1. Nội dung đầu tiên.\n1. Nội dung khác cùng số.'}
        accepted=parse_all([self.doc],[raw],self.out,self.cfg)
        self.assertEqual([(p['level'],p['number']) for p in accepted],[('ARTICLE','1')])
        self.assertTrue(list(read_jsonl(self.out/'03_structure/quarantined_provisions.jsonl')))
        issue=list(read_jsonl(self.out/'reports/parsing_issues.jsonl'))[0]
        self.assertEqual(issue['type'],'AMBIGUOUS_CANONICAL_PATH_QUARANTINED')
        self.assertEqual(issue['severity'],'WARN')

    def test_provisions_keep_source_spans_and_validity_window(self):
        rows=parse_legal_document(
            {'document_id':'d','effective_from':'2020-01-01','effective_to':'2025-01-01'},
            'Chương I\nĐiều 1. Phạm vi\n1. Nội dung áp dụng.\na) Chi tiết.')
        article=next(row for row in rows if row['level']=='ARTICLE')
        point=next(row for row in rows if row['level']=='POINT')
        self.assertEqual((article['line_start'],article['line_end']),(2,2))
        self.assertLess(article['char_start'],article['char_end'])
        self.assertEqual((point['valid_from'],point['valid_to']),('2020-01-01','2025-01-01'))
        segment=segment_document({'document_id':'d'},'Chương I\nĐiều 1. Phạm vi\n1. Nội dung áp dụng.\na) Chi tiết.')[1]
        for row in rows:
            span=segment['text'][row['char_start']:row['char_end']]
            self.assertEqual([x.strip() for x in span.splitlines() if x.strip()],
                             [x.strip() for x in row['text'].splitlines() if x.strip()])
            self.assertEqual(row['span_scope'],'SEGMENT_TEXT')

    def test_chapter_section_graph_is_loadable_and_structurally_linked(self):
        text='Chương I\nMục 1\nĐiều 1. Phạm vi\n1. Nội dung áp dụng.\nMục 2\nĐiều 2. Quy định khác\n1. Nội dung khác.'
        provisions=parse_legal_document(self.doc,text)
        nodes,edges=build_graph([self.doc],provisions,[],[],[],[],[],{},self.out)
        validate_export(nodes,edges)
        labels={node['label'] for node in nodes}
        self.assertTrue({'Chapter','Section'}<=labels)
        hierarchy={(edge['source'],edge['target']) for edge in edges if edge['type']=='PART_OF'}
        self.assertTrue(all((p['provision_id'],graph_parent_id(p)) in hierarchy for p in provisions))
        article_ids={p['provision_id'] for p in provisions if p['level']=='ARTICLE'}
        self.assertFalse(any(e['type']=='NEXT' and e['source'] in article_ids and e['target'] in article_ids for e in edges))

    def test_temporal_alias_conflict_is_rejected(self):
        registry=[{**self.doc,'issuer':'Quốc hội','promulgated_date':'2019-11-20','source_url':'https://example.test',
                   'metadata_verified':True,'temporal_verified':True,'effective_from':'2020-01-01',
                   'effective_to':'','valid_from':'2021-01-01','valid_to':'','legal_status':'EFFECTIVE'}]
        issues=quality_issues(registry,[],[],[],[],self.out,self.cfg)
        self.assertIn('TEMPORAL_ALIAS_MISMATCH',{issue['type'] for issue in issues})
    def test_short_parent_is_quarantined_but_short_point_can_be_valid(self):
        raw={**self.raw,'text':'Điều 1. Quy định\n1. Nội dung đầy đủ.\na) Chết.\nĐiều 2.\n1. Nội dung bị mất cha.'}
        accepted=parse_all([self.doc],[raw],self.out,self.cfg)
        self.assertEqual([(p['level'],p['number']) for p in accepted],
                         [('ARTICLE','1'),('CLAUSE','1'),('POINT','a')])
        self.assertEqual(list(read_jsonl(self.out/'reports/parsing_issues.jsonl'))[0]['type'],
                         'SHORT_PROVISION_QUARANTINED')
    def test_different_instruments_not_merged_by_title(self):
        self.assertNotEqual(instrument_key({**self.doc,'instrument_number':'90/2019/NĐ-CP'}),instrument_key({**self.doc,'instrument_number':'38/2022/NĐ-CP'}))
    def test_unknown_instruments_not_merged(self):
        self.assertNotEqual(instrument_key({'document_id':'a'}),instrument_key({'document_id':'b'}))
    def test_temporal_future_excluded(self):
        record={'temporal_verified':True,'effective_from':'2025-01-01','legal_status':'EFFECTIVE'}
        self.assertFalse(temporal_eligible(record,'2023-01-01')); self.assertTrue(temporal_eligible(record,'2025-01-01'))
    def test_temporal_end_exclusive_and_historical(self):
        record={'temporal_verified':True,'effective_from':'2020-01-01','effective_to':'2025-01-01','legal_status':'EXPIRED'}
        self.assertTrue(temporal_eligible(record,'2023-01-01')); self.assertFalse(temporal_eligible(record,'2025-01-01'))
    def test_temporal_unknown_excluded(self):
        self.assertFalse(temporal_eligible({'effective_from':'2020-01-01'},'2023-01-01'))
    def test_expired_without_end_excluded(self):
        self.assertFalse(temporal_eligible({'temporal_verified':True,'effective_from':'2020-01-01','legal_status':'EXPIRED'},'2023-01-01'))
    def test_partially_expired_without_whole_document_end_is_eligible(self):
        record={'temporal_verified':True,'effective_from':'2020-01-01','legal_status':'PARTIALLY_EXPIRED'}
        self.assertTrue(temporal_eligible(record,'2023-01-01'))
    def test_no_global_case_article_fanout(self):
        ps=parse_legal_document(self.doc,LAW)
        result=build_relation_edges([self.doc],ps,[{'case_id':'c','facts':'Theo Điều 35.'}],self.out)
        self.assertEqual(result,[])
        self.assertEqual(next(c for c in read_jsonl(self.out/'04_knowledge/citations.jsonl') if c['source_id']=='c')['status'],'UNRESOLVED')
    def test_precise_cross_document_point(self):
        ps=parse_legal_document(self.doc,LAW)
        result=build_relation_edges([self.doc],ps,[{'case_id':'c','facts':'Theo điểm b khoản 2 Điều 35 Bộ luật Lao động số 45/2019/QH14.'}],self.out)
        edge=next(r for r in result if r['source_id']=='c')
        self.assertEqual(edge['target_id'],next(p['provision_id'] for p in ps if p['level']=='POINT' and p['number']=='b'))
    def test_operative_relations_resolve_to_target_provisions(self):
        target_provisions=parse_legal_document(self.doc,LAW)
        source={**self.doc,'document_id':'source','file_id':'source-file','instrument_number':'01/2026/NĐ-CP',
                'document_number':'01/2026/NĐ-CP','title':'Nghị định sửa đổi'}
        source_text=('Điều 1. Sửa đổi điểm b khoản 2 Điều 35 của Bộ luật Lao động số 45/2019/QH14.\n'
                     'Điều 2. Nghị định này quy định chi tiết khoản 2 Điều 35 của Bộ luật Lao động số 45/2019/QH14.')
        source_provisions=parse_legal_document(source,source_text)
        result=build_relation_edges([self.doc,source],target_provisions+source_provisions,[],self.out)
        target_clause=next(p['provision_id'] for p in target_provisions if p['level']=='CLAUSE' and p['number']=='2')
        target_point=next(p['provision_id'] for p in target_provisions if p['level']=='POINT' and p['number']=='b')
        source_ids={p['provision_id'] for p in source_provisions}
        self.assertTrue(any(e['type']=='AMENDS' and e['target_id']==target_point and e['source_id'] in source_ids for e in result))
        self.assertTrue(any(e['type']=='IMPLEMENTS' and e['target_id']==target_clause and e['source_id'] in source_ids for e in result))
    def test_curated_alias_clause_resolution(self):
        doc={**self.doc,'citation_aliases':['Bộ luật Lao động']}
        ps=parse_legal_document(doc,LAW)
        result=build_relation_edges([doc],ps,[{'case_id':'c','facts':'Theo khoản 2 Điều 35 Bộ luật Lao động.'}],self.out)
        self.assertEqual(next(r for r in result if r['source_id']=='c')['target_id'],next(p['provision_id'] for p in ps if p['level']=='CLAUSE' and p['number']=='2'))
    def test_threshold_applied(self):
        cfg={'knowledge':{'relation_confidence_threshold':.99}}
        ps=parse_legal_document(self.doc,LAW)
        result=build_relation_edges([self.doc],ps,[{'case_id':'c','facts':'Theo Điều 35 Luật số 45/2019/QH14.'}],self.out,cfg=cfg)
        self.assertEqual(result,[])
    def test_document_resolution_rejects_ties_and_translation(self):
        self.assertIsNone(choose_document([self.doc,dict(self.doc)]))
        self.assertEqual(choose_document([self.doc,{**self.doc,'source_group':'SUPPLEMENTARY'}]),self.doc)
    def test_retrieval_breadcrumb_and_provenance(self):
        units=build_retrieval_units(parse_legal_document(self.doc,LAW),[],[self.doc])
        point=next(u for u in units if u['level']=='POINT')
        self.assertIn('Điều 35',point['breadcrumb']); self.assertIn('Khoản 2',point['breadcrumb'])
        self.assertEqual(point['version_id'],'d'); self.assertEqual(point['provenance'],{'file_id':'f'})
        self.assertIn('phải tuân thủ',point['ancestor_context'])
    def test_chapter_breadcrumb_survives_preamble_segmentation(self):
        units=build_retrieval_units(parse_legal_document(self.doc,'Chương III\nHỢP ĐỒNG LAO ĐỘNG\n'+LAW),[],[self.doc])
        self.assertIn('Chương III',units[0]['breadcrumb'])
    def test_gold_gate_cannot_use_smoke_results(self):
        from vn_labor_offline.evaluation import reviewed_quality_gate
        self.assertFalse(reviewed_quality_gate(self.out,[],[])['passed'])
        (self.out/'reports').mkdir()
        (self.out/'reports/reviewed_quality_evaluation.json').write_text(json.dumps({'reviewed':True,'reviewer':'test','gold_source':'fixture','build_id':'stale','citation_sample_count':20,'citation_precision':1,'retrieval_sample_count':20,'retrieval_passed':True}),encoding='utf-8')
        self.assertFalse(reviewed_quality_gate(self.out,[],[])['passed'])
    def test_retrieval_duplicate_rejected(self):
        ps=parse_legal_document(self.doc,LAW)
        with self.assertRaises(ValueError): build_retrieval_units(ps+ps,[],[self.doc])

    def test_gold_requires_approved_reviewer(self):
        self.assertIn('missing:reviewer', validate_gold_record({
            'query_id':'q1','question':'q','query_type':'DIRECT_PROVISION',
            'review_status':'APPROVED','reviewer':None}))

    def test_provision_identity_is_stable_for_same_instrument_path(self):
        ps=parse_legal_document(self.doc,LAW)
        identities,_=materialize_provision_versions([self.doc],ps,self.out)
        self.assertEqual(len(identities),len({x['provision_identity_id'] for x in identities}))
        self.assertTrue(all(p.get('provision_identity_id') for p in ps))
    def test_nested_neo4j_property_roundtrip(self):
        self.assertEqual(json.loads(neo4j_properties({'x':[{'a':1}]})['x']),[{'a':1}])
    def test_graph_dangling_or_duplicate_rejected(self):
        nodes=[{'id':'a','label':'Article'},{'id':'b','label':'Clause'}]
        with self.assertRaises(ValueError): validate_export(nodes,[{'id':'e','source':'a','target':'missing','type':'PART_OF'}])
        with self.assertRaises(ValueError): validate_export(nodes+nodes,[{'id':'e','source':'a','target':'b','type':'PART_OF'}])
    def test_unknown_config_rejected(self):
        cfg=copy.deepcopy(self.cfg); cfg['extraction']['typo_timeout']=3
        with self.assertRaises(ValueError): validate_config(cfg)
    def test_declared_config_keys_are_consumed(self):
        sources='\n'.join(p.read_text(encoding='utf-8-sig') for p in (ROOT/'src/vn_labor_offline').glob('*.py') if p.name!='config.py')
        for section,keys in CONFIG_KEYS.items():
            for key in keys: self.assertIn(key,sources,key)

class ExtractionTests(unittest.TestCase):
    setUp=OfflineTests.setUp
    tearDown=OfflineTests.tearDown
    def test_mixed_pdf_ocr_routes_by_page(self):
        import pymupdf as fitz
        from vn_labor_offline.extract import extract_pdf_pages
        path=self.out/'mixed.pdf'
        pdf=fitz.open(); p=pdf.new_page(); p.insert_text((30,30),'Native machine text with enough readable characters for this routing test.')
        p=pdf.new_page(); p.draw_rect(fitz.Rect(20,20,100,100),fill=(0,0,0)); pdf.save(path); pdf.close()
        cfg=copy.deepcopy(self.cfg); cfg['extraction']['min_text_chars_before_ocr']=20
        with patch('vn_labor_offline.extract.extract_pdf_docling',return_value='OCR page two text') as ocr:
            pages,provenance=extract_pdf_pages(path,self.raw,cfg,self.out)
        self.assertEqual(len(pages),2); self.assertFalse(provenance[0]['ocr']); self.assertTrue(provenance[1]['ocr'])
        self.assertEqual(ocr.call_args.args[-1],2)
    def test_timeout_enforced_and_reported(self):
        from vn_labor_offline.extract import extract_all
        self.cfg['extraction']['document_timeout_seconds']=.25
        with patch('vn_labor_offline.extract.subprocess.run',side_effect=subprocess.TimeoutExpired('worker',.1)) as run:
            result=extract_all([self.raw],self.cfg,self.out)
        self.assertEqual(run.call_args.kwargs['timeout'],.25)
        self.assertIn('TimeoutExpired',result[0]['extraction_error'])

    def test_dense_failure_still_leaves_graph_and_report(self):
        from vn_labor_offline.pipeline import construct_from_extracted
        self.cfg['project_root']=ROOT
        with patch('vn_labor_offline.pipeline.dense_worker',side_effect=RuntimeError('simulated OOM')), patch('vn_labor_offline.pipeline.build_bm25_index'):
            report=construct_from_extracted(self.cfg,[self.raw])
        self.assertTrue(list(read_jsonl(self.out/'05_graph/nodes.jsonl')))
        self.assertIn('DENSE_BUILD_FAILED',report['issues_by_type'])
        self.assertFalse(report['ready_for_offline_v1'])

    def test_neo4j_legacy_conflict_blocks_before_delete(self):
        from unittest.mock import Mock
        tx=Mock(); tx.run.return_value.single.side_effect=[{'count':0},{'count':1}]
        with self.assertRaises(RuntimeError): replace_transaction(tx,[{'id':'a'}],[],'dataset','build',500)
        self.assertEqual(tx.run.call_count,2)

    def test_neo4j_extra_nodes_fail_exact_verification(self):
        from unittest.mock import Mock
        tx=Mock(); result=Mock(); result.single.return_value={'count':0}
        def run(query,**kwargs):
            if 'RETURN n.id AS id' in query: return [{'id':'a','type':'Article'},{'id':'stale','type':'Article'}]
            if 'RETURN r.id AS id' in query: return []
            return result
        tx.run.side_effect=run
        with self.assertRaisesRegex(RuntimeError,'exact graph'):
            replace_transaction(tx,[{'id':'a','label':'Article','properties':{}}],[],'dataset','build',500)

if __name__=='__main__': unittest.main()

