"""Pagination exceptions must preserve body-loss and OCR-error protections."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf as fitz
from vn_labor_offline.extract import extract_one
from vn_labor_offline.integrity import require_complete_extraction
from vn_labor_offline.quality import quality_issues
from vn_labor_offline.page_quality import finalize_page_quality, page_number_only_evidence


class PaginationQualityTests(unittest.TestCase):
    def evidence(self, **overrides):
        args=dict(page_number=5,page_height=842.0,native_boxes=[[300.0,25.0,310.0,52.0]],
                  image_count=0,drawing_count=0)
        args.update(overrides)
        return page_number_only_evidence('5', '5', **args)

    def test_only_matching_page_number_in_empty_margin_is_nonblocking_and_audited(self):
        page={'page':5,'blank':False,'ocr_status':'COMPLETE','non_body_text_evidence':self.evidence()}
        finalize_page_quality(page,'','5')
        self.assertEqual(page['page_quality_status'],'REVIEW_REQUIRED')
        self.assertIn('PAGE_NUMBER_ONLY_REMOVED',page['quality_reason_codes'])
        self.assertNotIn('EMPTY_AFTER_CLEANING',page['quality_reason_codes'])
        with tempfile.TemporaryDirectory() as temp:
            self.assertTrue(require_complete_extraction([{'file_id':'f','text':'Actual body','page_provenance':[page]}],temp)['passed'])

    def test_body_number_image_vector_wrong_number_or_missing_geometry_are_not_exempt(self):
        for args in ({'native_boxes':[[300,300,310,320]]},{'image_count':1},{'drawing_count':1},
                     {'page_number':4},{'native_boxes':[]},{'page_height':float('nan')},
                     {'native_boxes':[[300,-1,310,20]]},{'native_boxes':[[300,800,310,850]]}):
            with self.subTest(args=args): self.assertIsNone(self.evidence(**args))
        self.assertIsNone(page_number_only_evidence('5','Another body',page_number=5,page_height=842,
                          native_boxes=[[300,25,310,52]],image_count=0,drawing_count=0))

    def test_real_text_loss_and_unproved_digits_still_block(self):
        for selected in ('5','Article 1. Real legal text','50000'):
            page={'page':5,'blank':False,'ocr_status':'COMPLETE'}
            finalize_page_quality(page,'',selected)
            self.assertEqual(page['page_quality_status'],'ERROR')
            self.assertIn('EMPTY_AFTER_CLEANING',page['quality_reason_codes'])

    def test_ocr_failure_not_hidden_by_pagination_proof(self):
        page={'page':5,'blank':False,'ocr_status':'FAILED','non_body_text_evidence':self.evidence()}
        finalize_page_quality(page,'','5')
        self.assertEqual(page['page_quality_status'],'ERROR')
        self.assertIn('OCR_FAILED',page['quality_reason_codes'])

    def test_stale_proof_for_other_page_or_content_is_not_accepted(self):
        for number,selected in ((4,'5'),(5,'6'),(5,'5 body')):
            page={'page':number,'blank':False,'ocr_status':'COMPLETE','non_body_text_evidence':self.evidence()}
            finalize_page_quality(page,'',selected)
            self.assertEqual(page['page_quality_status'],'ERROR')

    def test_pdf_end_to_end_footer_only_vs_numeric_body(self):
        for position,expected in (((300,30),'REVIEW_REQUIRED'),((300,350),'ERROR')):
            with self.subTest(position=position), tempfile.TemporaryDirectory() as temp:
                root=Path(temp); (root/'config').mkdir(); pdf=root/'example.pdf'
                with fitz.open() as document:
                    page=document.new_page();page.insert_text((30,200),'Actual document body.')
                    page=document.new_page();page.insert_text(position,'2');document.save(pdf)
                row={'file_id':'f','path':str(pdf),'relative_path':'example.pdf','extension':'.pdf',
                     'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}
                cfg={'project_root':str(root),'extraction':{'use_docling':'auto','ocr_use_gpu':False,
                     'page_quality_render_previews':False},'cleaning':{}}
                with patch('vn_labor_offline.extract.extract_pdf_docling',side_effect=['Actual document body.','2']):
                    result=extract_one(row,cfg,root/'out')
                self.assertIsNone(result['extraction_error'])
                self.assertEqual(result['text'].strip(),'Actual document body.')
                self.assertEqual(result['page_provenance'][1]['page_quality_status'],expected)
                self.assertEqual(result['page_provenance'][1]['cleaned_chars'],0)

    def test_downstream_quality_validates_proof_and_rejects_changed_hash(self):
        page={'page':5,'blank':False,'ocr_status':'COMPLETE','chars':1,
              'non_body_text_evidence':self.evidence()}
        finalize_page_quality(page,'','5')
        pages=[{'page':i,'chars':10,'cleaned_chars':10} for i in range(1,5)]+[page]
        extracted={'file_id':'f','extension':'.pdf','text_chars':1500,
                   'page_count':5,'page_provenance':pages}
        registry={'document_id':'d','file_id':'f','source_group':'LEGAL_DOCUMENT',
                  'instrument_number':'1/2020','title':'Test document','issuer':'Test issuer',
                  'promulgated_date':'2020-01-01','source_url':'https://example.com',
                  'metadata_verified':True,'temporal_verified':True}
        with tempfile.TemporaryDirectory() as temp:
            valid=quality_issues([registry],[extracted],[],[],[],Path(temp))
            self.assertNotIn('INCOMPLETE_PAGE_EXTRACTION',[r['type'] for r in valid])
            page['selected_text_sha256']='changed'
            invalid=quality_issues([registry],[extracted],[],[],[],Path(temp))
            self.assertIn('INCOMPLETE_PAGE_EXTRACTION',[r['type'] for r in invalid])
