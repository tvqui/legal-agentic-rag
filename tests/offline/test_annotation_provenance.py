import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from vn_labor_offline.page_content import align_notes
from vn_labor_offline.segmentation import segment_document
from vn_labor_offline.legal_structure import parse_legal_document
from vn_labor_offline.provenance import enrich_provenance
from vn_labor_offline.quality import provision_provenance_issues
from vn_labor_offline.integrity import require_complete_provenance
from vn_labor_offline.util import write_jsonl


class AnnotationProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.out=Path(self.temp.name)
        note='7 Khoản này được sửa đổi, bổ sung theo Luật số 01/2026.'
        self.text='Điều 1. Quy định\n1. Người lao động có quyền\n'+note+'\n\ntiếp tục thực hiện nghĩa vụ.'
        split=self.text.index('tiếp tục')
        self.registry=[{'document_id':'d','file_id':'f','document_type':'LAW'}]
        pages=[{'page':1,'text_start':0,'text_end':split},{'page':2,'text_start':split,'text_end':len(self.text)}]
        candidate={'schema':'pdf-footnote-v1','text':note,'bbox':[40,760,550,785],
            'page_height':842,'font_size':10,'body_font_size':14}
        notes=align_notes([candidate],self.text[:split],1,'source-sha',0)
        self.docs=[{'file_id':'f','sha256':'source-sha','text':self.text,
            'non_body_annotations':notes,'page_provenance':pages}]
        write_jsonl(self.out/'03_structure/segments.jsonl',segment_document(self.registry[0],self.text))
        self.provisions=parse_legal_document(self.registry[0],self.text,notes)
        enrich_provenance(self.provisions,self.docs,self.registry,self.out)

    def tearDown(self): self.temp.cleanup()

    def audit(self): return provision_provenance_issues(self.registry,self.docs,self.provisions,self.out)

    def test_mid_clause_footnote_keeps_exact_bounding_and_exclusion_spans(self):
        self.assertFalse(self.audit())
        clause=next(p for p in self.provisions if p['level']=='CLAUSE')
        self.assertNotIn('7 Khoản',clause['text'])
        raw=self.text[clause['document_char_start']:clause['document_char_end']]
        self.assertIn('7 Khoản',raw)
        exclusion=clause['excluded_annotation_spans'][0]
        self.assertEqual(self.text[exclusion['document_char_start']:exclusion['document_char_end']],self.docs[0]['non_body_annotations'][0]['text'])
        self.assertEqual((clause['page_start'],clause['page_end']),(1,2))
        self.assertTrue(require_complete_provenance(self.registry,self.docs,self.provisions,self.out)['passed'])

    def test_wrong_annotation_sha_does_not_bypass_source_validation(self):
        self.docs[0]['non_body_annotations'][0]['text_sha256']='tampered'
        self.assertTrue(any(e['type']=='INVALID_PROVISION_PROVENANCE' for e in self.audit()))

    def test_forged_or_missing_declared_exclusion_is_rejected(self):
        clause=next(p for p in self.provisions if p['level']=='CLAUSE')
        saved=copy.deepcopy(clause['excluded_annotation_spans'])
        for value in [[],[{**saved[0],'segment_char_start':saved[0]['segment_char_start']+1}]]:
            clause['excluded_annotation_spans']=value
            self.assertTrue(any(e['type']=='INVALID_PROVISION_PROVENANCE' for e in self.audit()))

    def test_removing_body_words_is_rejected_and_report_is_nonpass(self):
        clause=next(p for p in self.provisions if p['level']=='CLAUSE')
        clause['text']=clause['text'].replace('tiếp tục ','')
        with self.assertRaisesRegex(RuntimeError,'provenance invalid'):
            require_complete_provenance(self.registry,self.docs,self.provisions,self.out)
        report=json.loads((self.out/'reports/provision_provenance_integrity.json').read_text(encoding='utf-8'))
        self.assertFalse(report['passed']);self.assertTrue(report['errors'])

    def test_pipeline_rejects_corruption_before_case_ai_and_dense(self):
        from vn_labor_offline.pipeline import construct_from_extracted
        clause=next(p for p in self.provisions if p['level']=='CLAUSE');clause['text']=clause['text'].replace('tiếp tục ','')
        cfg={'output_dir':self.out,'project_root':self.out,'knowledge':{'case_ontology_mode':'ai'}}
        with patch('vn_labor_offline.pipeline.write_page_quality_artifacts'), \
             patch('vn_labor_offline.page_content.write_notes'), \
             patch('vn_labor_offline.integrity.require_complete_extraction'), \
             patch('vn_labor_offline.pipeline.resolve_source_catalog'), \
             patch('vn_labor_offline.pipeline.build_registry',return_value=self.registry), \
             patch('vn_labor_offline.pipeline.parse_all',return_value=self.provisions), \
             patch('vn_labor_offline.pipeline.enrich_case_ontology') as ai, \
             patch('vn_labor_offline.pipeline.dense_worker') as dense:
            with self.assertRaisesRegex(RuntimeError,'provenance invalid'):
                construct_from_extracted(cfg,self.docs)
            ai.assert_not_called();dense.assert_not_called()

if __name__=='__main__':unittest.main()
