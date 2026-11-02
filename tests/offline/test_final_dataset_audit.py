import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

class FinalDatasetAuditTests(unittest.TestCase):
    def test_snapshot_and_missing_gold_group_are_reported_without_approval(self):
        audit=module('audit_final_dataset')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifact=root/'artifact.zip';gold=root/'gold.zip'
            with zipfile.ZipFile(artifact,'w') as z:
                for name,rows in {
                    '02_registry/documents':[{'document_id':'d','relative_path':'law.pdf','sha256':'sha'}],
                    '03_structure/provisions':[], '06_indexes/retrieval_units':[],
                    '04_knowledge/legal_changes':[], '03_structure/quarantined_provisions':[],
                    'reviews/page_quality/page_review_evidence':[]}.items():
                    z.writestr('artifacts/'+name+'.jsonl','\n'.join(map(json.dumps,rows)))
                z.writestr('artifacts/reports/summary.json','{}')
                z.writestr('artifacts/reports/final_outputs_validation.json',json.dumps({'stages':{'graph':False}}))
            with zipfile.ZipFile(gold,'w') as z:
                z.writestr('labor_gold.jsonl',json.dumps({'id':'new','question':'Question',
                    'query_date':'2027-01-02','required_groups':[['missing-id']]}))
            original=artifact.read_bytes()
            result=audit.audit(artifact,root/'report',gold,snapshot_as_of='2027-01-01')
            self.assertEqual(result['gold_with_unresolved_groups'],1)
            self.assertEqual(result['gold_flags']['QUERY_AFTER_CORPUS_SNAPSHOT'],1)
            self.assertEqual(result['human_approvals_created'],0)
            self.assertFalse(result['technical_stages']['graph'])
            self.assertEqual(result['corpus_snapshot_as_of'],'2027-01-01')
            self.assertEqual(artifact.read_bytes(),original)
            with self.assertRaises(FileExistsError):audit.audit(artifact,root/'report',snapshot_as_of='2027-01-01')

    def test_official_probe_does_not_follow_non_official_or_credential_urls(self):
        sources=module('check_official_sources')
        for url in ['http://vbpl.vn/x','https://vbpl.vn.evil.example','https://127.0.0.1/x','https://secret@vbpl.vn/x']:
            self.assertFalse(sources.allowed(url))
        self.assertTrue(sources.allowed('https://congbao.chinhphu.vn/van-ban/x'))

    def test_question_date_conflict_is_flagged_without_guessing_historical_law_numbers(self):
        audit=module('audit_final_dataset')
        self.assertTrue(audit.question_date_conflict('Ngày 01/01/2028 áp dụng mức nào?','2026-10-23'))
        self.assertTrue(audit.question_date_conflict('Năm 2029 có thay đổi gì?','2026-10-23'))
        self.assertFalse(audit.question_date_conflict('Điều 1 Nghị định 145/2020/NĐ-CP?','2026-10-23'))
