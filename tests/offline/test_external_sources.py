from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from vn_labor_offline.external_sources import (
    SOURCES, citation_spans, labour_scope, official_case_url, main, stage,
)
from vn_labor_offline.issues import load_issue_config, score_issues
from vn_labor_offline.ontology_vocabulary import lexical_aliases, read_vocabulary

ROOT = Path(__file__).resolve().parents[2]
SHA = '2cba5c1babf3708803ea452ae2e5f1ea692d0144c2831a5f2cec5830c4603221'


def case(**overrides):
    result = {'doc_name': 'TAND_LD_A', 'category': 'Labor', 'code': 'LĐ-PT',
        'is_precedent': False, 'official_document_id': '01/2020/LĐ-PT',
        'issued_date': '2020-09-01', 'court': 'Tòa án mẫu', 'markdown': 'Căn cứ Điều 35.',
        'web_url': 'https://anle.toaan.gov.vn/webcenter/portal/anle/a',
        'pdf_url': 'https://anle.toaan.gov.vn/webcenter/ShowProperty?a=1',
        'citations_source': 'llm', 'citations_law': [{'article': '35', 'span': [[7, 14]]}]}
    result.update(overrides)
    return result


def legal(eid='vbpl:uuid-a', **overrides):
    result = {'id': eid, 'title': 'Quy định tiền lương và lao động', 'so_ky_hieu': '1/2020/TT',
        'ngay_ban_hanh': '01/08/2020', 'ngay_co_hieu_luc': '01/09/2020',
        'co_quan_ban_hanh': 'Cơ quan mẫu'}
    result.update(overrides)
    return result


class ExternalSourcesTests(unittest.TestCase):
    def stage_rows(self, source, rows, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'stage'
        report = stage(source, rows, path, max_scan=kwargs.pop('max_scan', 0), **kwargs)
        database = sqlite3.connect(path / 'external_sources.sqlite')
        self.addCleanup(database.close)
        return path, report, database

    def test_nonprecedent_stays_judgment_and_spans_do_not_approve_citation(self):
        raw = case()
        _, report, db = self.stage_rows('cases', {'documents': [raw, case(doc_name='civil', category='Civil', code='DS-PT')]})
        kind, encoded = db.execute('SELECT kind,payload_json FROM metadata').fetchone()
        self.assertEqual(kind, 'JUDGMENT_CANDIDATE')
        self.assertFalse(json.loads(encoded)['authority_verified'])
        relation = json.loads(db.execute('SELECT payload_json FROM relationships').fetchone()[0])
        self.assertFalse(relation['semantic_verified'])
        self.assertEqual(relation['spans'][0]['quote'], raw['markdown'][7:14])
        self.assertEqual(report['counts']['outside_labour_scope'], 1)
        self.assertFalse(report['approved_for_online'])

    def test_precedent_flag_is_strict_and_does_not_recognize_precedent_automatically(self):
        _, report, db = self.stage_rows('cases', {'documents': [case(is_precedent='false'), case(doc_name='true', is_precedent=True)]})
        self.assertEqual(report['issues']['IS_PRECEDENT_MUST_BE_BOOLEAN'], 1)
        kind, raw = db.execute('SELECT kind,payload_json FROM metadata').fetchone()
        self.assertEqual(kind, 'PRECEDENT_CANDIDATE')
        self.assertIn('PRECEDENT_RECOGNITION_NOT_PROVEN', json.loads(raw)['review_issues'])

    def test_legal_string_joins_html_and_unresolved_relation_direction(self):
        raw_html = '<html><head><style>SECRET</style></head><body>Điều 1<script>BAD</script><p>nội dung</p></body></html>'
        _, report, db = self.stage_rows('legal', {
            'metadata': [legal()],
            'content': [{'id': 'vbpl:uuid-a', 'content_html': raw_html}],
            'relationships': [{'doc_id': 'vbpl:uuid-a', 'other_doc_id': 'missing-uuid', 'relationship': 'Bị sửa đổi'}],
        })
        text, sha, encoded = db.execute('SELECT text,raw_sha256,payload_json FROM content').fetchone()
        self.assertEqual(text, 'Điều 1\nnội dung')
        self.assertEqual(json.loads(encoded)['raw'], raw_html)
        self.assertEqual(sha, hashlib.sha256(raw_html.encode()).hexdigest())
        target, relation, encoded = db.execute('SELECT other_doc_id,relation,payload_json FROM relationships').fetchone()
        self.assertIsNone(target)
        self.assertEqual(relation, 'Bị sửa đổi')
        self.assertFalse(json.loads(encoded)['effective_change_applied'])
        payload = json.loads(db.execute('SELECT payload_json FROM metadata').fetchone()[0])
        self.assertEqual(payload['date_claims']['effective_from'], '2020-09-01')
        self.assertNotIn('official_url', payload)

    def test_partial_scan_does_not_claim_content_missing(self):
        _, report, _ = self.stage_rows('legal', {'metadata': [legal()],
            'content': [{'id': 'unrelated', 'content_html': 'x'}, {'id': 'vbpl:uuid-a', 'content_html': 'OK'}],
            'relationships': []}, max_scan=1)
        self.assertEqual(report['issues']['CONTENT_NOT_OBSERVED_IN_SCAN'], 1)
        self.assertFalse(report['scans']['content']['source_exhausted'])
        self.assertNotIn('CONTENT_MISSING', report['issues'])

    def test_exhausting_sample_does_not_claim_entire_dataset_was_scanned(self):
        _, report, _ = self.stage_rows('legal', {'metadata': [legal()], 'content': [], 'relationships': []},
            provenance={'kind': 'LIVE_VIEWER_SAMPLE_REVISION_NOT_VERIFIED'})
        self.assertFalse(report['dataset_scan_complete'])
        self.assertEqual(report['coverage_scope'], 'SUPPLIED_INPUT_ONLY')
        self.assertIn('CONTENT_NOT_OBSERVED_IN_INPUT', report['issues'])
        self.assertNotIn('CONTENT_MISSING', report['issues'])

    def test_selection_limit_and_duplicate_identity_are_visible(self):
        _, report, _ = self.stage_rows('cases', {'documents': [case(), case(doc_name='next'), case(doc_name='third')]}, max_records=2)
        self.assertEqual(report['duplicate_identity_groups'], 1)
        self.assertEqual(report['duplicate_content_groups'], 1)
        self.assertEqual(report['counts']['selection_limit_rows'], 1)
        self.assertFalse(report['selection_complete_within_scan'])

    def test_duplicate_metadata_and_content_cannot_overwrite(self):
        _, report, db = self.stage_rows('legal', {'metadata': [legal(), legal(title='changed lao động')],
            'content': [{'id': 'vbpl:uuid-a', 'content_html': 'FIRST'}, {'id': 'vbpl:uuid-a', 'content_html': 'SECOND'}],
            'relationships': []})
        self.assertEqual(db.execute('SELECT text FROM content').fetchone()[0], 'FIRST')
        self.assertEqual(report['issues']['DUPLICATE_METADATA_ID'], 1)
        self.assertEqual(report['issues']['DUPLICATE_CONTENT_ID'], 1)

    def test_empty_html_and_invalid_dates_are_reported(self):
        _, report, _ = self.stage_rows('legal', {'metadata': [legal(), legal('bad', ngay_co_hieu_luc='31/02/2020')],
            'content': [{'id': 'vbpl:uuid-a', 'content_html': '<html><head><style>text</style></head><body></body></html>'}],
            'relationships': []})
        self.assertEqual(report['issues']['INVALID_DATE'], 1)
        self.assertEqual(report['issues']['EMPTY_CONTENT'], 1)

    def test_external_ids_integer_joins_but_uuid_stays_string(self):
        _, _, db = self.stage_rows('legal', {'metadata': [legal(12)],
            'content': [{'id': '12', 'content_html': 'content'}], 'relationships': []})
        self.assertEqual(db.execute('SELECT external_id FROM metadata').fetchone()[0], '12')
        self.assertEqual(db.execute('SELECT COUNT(*) FROM content').fetchone()[0], 1)

    def test_filter_ignores_incidental_body_and_authority_mentions(self):
        self.assertFalse(labour_scope({'title': 'Điều chỉnh dự toán', 'co_quan_ban_hanh': 'Bộ Lao động',
                                     'content_html': 'Người lao động'}, 'legal'))
        self.assertTrue(labour_scope({'title': 'Bảo hiểm thất nghiệp'}, 'legal'))
        self.assertTrue(labour_scope(case(category=None), 'cases'))
        self.assertFalse(official_case_url('https://anle.toaan.gov.vn.evil.test/x'))
        self.assertFalse(official_case_url('http://anle.toaan.gov.vn/x'))

    def test_invalid_unicode_span_is_not_grounded(self):
        for invalid in ([[0, 999]], [[True, 4]], [[2, 1]], 'wrong'):
            spans, status = citation_spans({'span': invalid}, 'Điều 1')
            self.assertFalse(spans)
            self.assertIn(status, {'INVALID_SPANS', 'MISSING_SPANS'})

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / 'canonical.txt').write_text('keep', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                stage('cases', {'documents': []}, path)
            self.assertEqual((path / 'canonical.txt').read_text(), 'keep')

    def test_dataset_revision_is_immutable(self):
        for spec in SOURCES.values():
            self.assertRegex(spec['revision'], r'^[0-9a-f]{40}$')
            self.assertNotIn('embeddings', spec['files'])
            self.assertNotIn('reduces', spec['files'])

    def test_network_failure_rolls_back_and_keeps_failed_manifest(self):
        def interrupted():
            yield case()
            raise ConnectionError('upstream lost')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'failed'
            with self.assertRaises(ConnectionError):
                stage('cases', {'documents': interrupted()}, path, max_scan=0)
            report = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'FAILED')
            self.assertFalse(report['approved_for_online'])
            with closing(sqlite3.connect(path / 'external_sources.sqlite')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM metadata').fetchone()[0], 0)

    def test_fetch_initialization_failure_is_inside_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'failed'
            fake_datasets = SimpleNamespace(load_dataset=Mock(side_effect=ConnectionError('offline')))
            with patch.dict(sys.modules, {'datasets': fake_datasets}):
                with self.assertRaises(ConnectionError):
                    main(['fetch', '--source', 'cases', '--output', str(path)])
            self.assertEqual(json.loads((path / 'manifest.json').read_text(encoding='utf-8'))['status'], 'FAILED')


class OntologyVocabularyTests(unittest.TestCase):
    def test_real_vocabulary_excludes_sample_rules_and_audits_versions(self):
        aliases, audit = lexical_aliases(ROOT / 'config/labor_ontology_v3.owl', SHA)
        self.assertEqual(audit['counts_by_type']['Class'], 105)
        self.assertEqual(audit['counts_by_type']['LegalIssue'], 46)
        self.assertFalse(audit['undefined_references'])
        self.assertIn('VERSION_IRI_MISMATCH', audit['warning_codes'])
        self.assertEqual(audit['legal_rules_imported'], 0)
        self.assertIn('trả lương trễ', aliases['Wage'])
        self.assertNotIn('đang điều trị', [v for values in aliases.values() for v in values])
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            lexical_aliases(ROOT / 'config/labor_ontology_v3.owl', '0' * 64)

    def test_lexical_crosswalk_is_used_by_existing_offline_classifier(self):
        issues = load_issue_config(ROOT)
        self.assertTrue(any(i['issue_key'] == 'Wage'
            for i in score_issues('Công ty trả lương trễ nhiều lần.', issues)))
        self.assertFalse(score_issues('Người bệnh đang điều trị.', issues))

    def test_dtd_is_refused_without_fetch_or_entity_expansion(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'bad.owl'
            path.write_text('<!DOCTYPE x [<!ENTITY e SYSTEM "file:///secret">]><x>&e;</x>')
            with self.assertRaisesRegex(ValueError, 'DTD'):
                read_vocabulary(path)


if __name__ == '__main__':
    unittest.main()
