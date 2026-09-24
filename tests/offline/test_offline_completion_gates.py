"""Regression fixtures for evidence alignment and reviewed temporal boundaries."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from vn_labor_offline.evidence import locate_evidence
from vn_labor_offline.gold import validate_gold_record, evaluate_gold
from vn_labor_offline.gold_evaluator import evaluate_approved_gold
from vn_labor_offline.hierarchy_headings import build_hierarchy_headings
from vn_labor_offline.provision_versions import materialize_provision_versions
from vn_labor_offline.scanner import resolve_source_catalog, source_catalog_gate
from vn_labor_offline.segmentation import segment_document
from vn_labor_offline.temporal import select_provision_versions


class CompletionGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'config').mkdir()
        self.out=self.root/'artifacts'

    def tearDown(self):
        self.temp.cleanup()

    def test_source_catalog_does_not_verify_landing_metadata_without_provenance_review(self):
        manifest=[{'file_id':'file','relative_path':'legal_corpus/laws/01.pdf',
                   'filename':'01.pdf','sha256':'abc','source_group':'LEGAL_DOCUMENT','binding_default':True}]
        catalog={'sources':{'legal_corpus/laws/01.pdf':{'sha256':'abc','source_provider':'VBPL',
            'source_url':'https://example.test/01','metadata_verified':True,
            'official_source':True,'reviewer':'lawyer','reviewed_at':'2026-09-15'}}}
        (self.root/'config/source_catalog.yaml').write_text(json.dumps(catalog),encoding='utf-8')
        record=resolve_source_catalog(manifest,self.root,self.out)[0]
        self.assertEqual(record['catalog_status'],'UNVERIFIED')
        self.assertIn('collected_at',record['missing_fields'])
        registry=[{'file_id':'file','sha256':'abc','source_group':'LEGAL_DOCUMENT'}]
        self.assertFalse(source_catalog_gate([record],registry)['passed'])

    def test_sentence_evidence_uses_original_offsets_after_whitespace_changes(self):
        segment='Điều 1. Tiền lương\nNgười lao động phải  làm việc đúng giờ.'
        document='Lời mở đầu\n'+segment
        provision={'segment_id':'seg','char_start':segment.index('Người'),
                   'char_end':len(segment),'document_char_start':document.index('Người'),
                   'document_char_end':len(document),'page_status':'NOT_APPLICABLE',
                   'source_unit_type':'DOCUMENT'}
        text,span,status=locate_evidence(provision,'phải làm việc đúng giờ',segment,document)
        self.assertEqual(status,'RESOLVED')
        self.assertEqual(text,'phải  làm việc đúng giờ')
        self.assertEqual(segment[span['segment_char_start']:span['segment_char_end']],text)
        self.assertEqual(document[span['document_char_start']:span['document_char_end']],text)

    def test_chapter_heading_has_own_source_span_before_article(self):
        document='Chương I\nHỢP ĐỒNG LAO ĐỘNG\nĐiều 1. Phạm vi\n1. Nội dung áp dụng.'
        segments=segment_document({'document_id':'doc'},document)
        rows=build_hierarchy_headings([{'document_id':'doc','file_id':'file'}],
            [{'file_id':'file','text':document,'page_provenance':[]}],segments,self.out)
        chapter=next(row for row in rows if row['label']=='Chapter')
        self.assertEqual(chapter['title'],'HỢP ĐỒNG LAO ĐỘNG')
        self.assertEqual(chapter['provenance_status'],'RESOLVED')
        self.assertEqual(document[chapter['document_char_start']:chapter['document_char_end']],
                         segments[0]['text'][chapter['segment_char_start']:chapter['segment_char_end']])

    def test_overlapping_reviewed_provision_versions_are_rejected(self):
        docs=[{'document_id':'d1','instrument_id':'inst','sha256':'sha1','effective_from':'2020-01-01'},
              {'document_id':'d2','instrument_id':'inst','sha256':'sha2','effective_from':'2024-01-01'}]
        provisions=[{'provision_id':'p1','document_id':'d1','article_number':'1','clause_number':'',
                     'point_number':'','valid_from':'2020-01-01','valid_to':''},
                    {'provision_id':'p2','document_id':'d2','article_number':'1','clause_number':'',
                     'point_number':'','valid_from':'2024-01-01','valid_to':''}]
        reviews={'versions':{'p1':{'review_status':'APPROVED','reviewer':'lawyer',
            'reviewed_at':'2026-09-15','source_sha256':'sha1','evidence':'official source',
            'valid_from':'2020-01-01','valid_to':'2025-01-01'},
            'p2':{'review_status':'APPROVED','reviewer':'lawyer',
            'reviewed_at':'2026-09-15','source_sha256':'sha2','evidence':'amendment',
            'valid_from':'2024-01-01','valid_to':''}}}
        (self.root/'config/provision_version_reviews.yaml').write_text(json.dumps(reviews),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Overlapping reviewed provision versions'):
            materialize_provision_versions(docs,provisions,self.out,self.root)

    def test_point_in_time_selector_excludes_unreviewed_and_ended_versions(self):
        versions=[{'provision_version_id':'old','provision_identity_id':'id',
                   'valid_from':'2020-01-01','valid_to':'2025-01-01',
                   'provision_temporal_verified':True},
                  {'provision_version_id':'new','provision_identity_id':'id',
                   'valid_from':'2025-01-01','valid_to':None,
                   'provision_temporal_verified':True},
                  {'provision_version_id':'unreviewed','provision_identity_id':'other',
                   'valid_from':'2020-01-01','valid_to':None,
                   'provision_temporal_verified':False}]
        self.assertEqual([v['provision_version_id'] for v in
                          select_provision_versions(versions,'2024-12-31')],['old'])
        self.assertEqual([v['provision_version_id'] for v in
                          select_provision_versions(versions,'2025-01-01')],['new'])

    def test_draft_gold_is_valid_but_approval_requires_reviewer_and_qrels(self):
        draft={'query_id':'q','question':'Mức lương?','query_type':'DIRECT_PROVISION',
               'review_status':'DRAFT','reviewer':None}
        self.assertEqual(validate_gold_record(draft),[])
        approved={**draft,'review_status':'APPROVED'}
        self.assertIn('missing:reviewer',validate_gold_record(approved))
        self.assertIn('missing:gold_unit_ids',validate_gold_record(approved))
        self.assertFalse(evaluate_gold(self.out)['passed'])

    def test_gold_evaluator_rejects_temporal_qrels_without_reviewed_validity(self):
        (self.out/'06_indexes').mkdir(parents=True)
        (self.out/'06_indexes/retrieval_units.jsonl').write_text(json.dumps({
            'unit_id':'unit-1','valid_from':'2020-01-01','valid_to':'',
            'provision_temporal_verified':False})+'\n',encoding='utf-8')
        approved=[{'query_id':'q1','question':'Rule on date?','query_type':'TEMPORAL',
                   'query_date':'2024-01-01','gold_unit_ids':['unit-1'],'build_id':'build'}]
        thresholds={'k':10,'minimum_union_recall_at_k':0.5,
                    'minimum_approved_queries':1,'minimum_retrieval_queries':1,
                    'required_query_types':['TEMPORAL']}
        with patch('vn_labor_offline.gold_evaluator.evaluation_fingerprint',return_value='build'), \
             patch('vn_labor_offline.gold_evaluator.approved_thresholds',return_value=(thresholds,'')), \
             patch('vn_labor_offline.gold_evaluator.query_indexes') as query:
            result=evaluate_approved_gold(self.out,approved)
        self.assertEqual(result['status'],'INVALID_TEMPORAL_QRELS')
        query.assert_not_called()

    def test_gold_evaluator_measures_reviewed_union_recall(self):
        (self.out/'06_indexes').mkdir(parents=True)
        (self.out/'06_indexes/retrieval_units.jsonl').write_text(
            json.dumps({'unit_id':'unit-1'})+'\n'+json.dumps({'unit_id':'unit-2'})+'\n',
            encoding='utf-8')
        approved=[{'query_id':'q1','question':'Where?','query_type':'DIRECT_PROVISION',
                   'gold_unit_ids':['unit-1','unit-2'],'build_id':'build'}]
        thresholds={'k':10,'minimum_union_recall_at_k':0.75,
                    'minimum_approved_queries':1,'minimum_retrieval_queries':1,
                    'required_query_types':['DIRECT_PROVISION']}
        retrieved=[{'dense':['unit-1'],'bm25':[],'union':['unit-1']}]
        with patch('vn_labor_offline.gold_evaluator.evaluation_fingerprint',return_value='build'), \
             patch('vn_labor_offline.gold_evaluator.approved_thresholds',return_value=(thresholds,'')), \
             patch('vn_labor_offline.gold_evaluator.query_indexes',return_value=retrieved):
            result=evaluate_approved_gold(self.out,approved)
        self.assertEqual(result['status'],'EVALUATED')
        self.assertFalse(result['passed'])
        self.assertEqual(result['mean_union_recall_at_k'],0.5)


if __name__=='__main__':
    unittest.main()
