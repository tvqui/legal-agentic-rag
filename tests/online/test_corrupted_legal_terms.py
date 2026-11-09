import tempfile,unittest
from pathlib import Path
from .test_online_core import fixture
from vn_labor_online.answer_quality import language_issues
from vn_labor_online.config import OnlineConfig
from vn_labor_online.artifact_store import ArtifactStore
from vn_labor_online.retrieval import as_evidence
from vn_labor_online.audit import deterministic_audit

class CorruptedLegalTermTests(unittest.TestCase):
    def test_corrupted_arbitration_institution_is_flagged(self):
        self.assertIn('SUSPECT_LEGAL_TERM',language_issues('Trước khi yêu cầu Hội đồng trong tài lao động giải quyết tranh chấp.'))
    def test_correct_institution_and_ordinary_document_context_are_preserved(self):
        for text in ['Trước khi yêu cầu Hội đồng trọng tài lao động giải quyết.',
                     'Hội đồng trong tài liệu hướng dẫn có nhiều thành viên.']:
            self.assertNotIn('SUSPECT_LEGAL_TERM',language_issues(text))
    def test_corrupted_source_is_not_silently_rewritten_or_used_as_verified(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);build=fixture(root)
            store=ArtifactStore(OnlineConfig(artifact_source=str(root),expected_build_id=build,cache_dir=str(root/'cache')))
            u=store.units_by_id['prov_1'];original='Trước khi yêu cầu Hội đồng trong tài lao động giải quyết.'
            u['source_text']=original;u['text']=original
            result=deterministic_audit(store,[as_evidence(u,1,'exact',1)],'2024-01-01',True)[0]
            self.assertFalse(result.verified)
            self.assertIn('SOURCE_TEXT_QUALITY:SUSPECT_LEGAL_TERM',result.audit_issues)
            self.assertEqual(u['source_text'],original)

if __name__=='__main__':unittest.main()
