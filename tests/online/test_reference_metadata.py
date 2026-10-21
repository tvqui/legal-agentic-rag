import unittest
from vn_labor_online.audit import reference_audit,citations
from vn_labor_online.models import Claim,Evidence


class ReferenceMetadataTests(unittest.TestCase):
    def evidence(self):
        return Evidence(unit_id='source',retrieval_method='policy',verified=True,
            document_number='12/2022/NĐ-CP',document_type='Nghị định',
            document_title='Quy định xử phạt vi phạm hành chính trong lĩnh vực lao động',
            article_number='10',clause_number='2',point_number='c',
            text='c) Trả lương cho người lao động trong thời gian thử việc thấp hơn 85% mức lương của công việc đó;',
            source_url='https://example.test/official-document')

    def audit(self,text):
        item=self.evidence()
        claim=Claim(claim_id='identity',text=text,evidence_ids=['source'])
        return reference_audit(text+' [source]',[item],citations([item]),[claim])

    def test_identity_uses_actual_metadata_not_only_clause_body(self):
        ok,issues=self.audit('Văn bản xử phạt cần kiểm tra là Nghị định 12/2022/NĐ-CP; căn cứ về hành vi đang hỏi nằm tại Điều 10 khoản 2.')
        self.assertTrue(ok,issues)

    def test_metadata_does_not_allow_another_instrument_or_locator(self):
        for text,code in (
            ('Nghị định 99/2099/NĐ-CP xử phạt tại Điều 10 khoản 2.','CLAIM_UNSUPPORTED_INSTRUMENT'),
            ('Nghị định 12/2022/NĐ-CP xử phạt tại Điều 999 khoản 2.','CLAIM_UNSUPPORTED_ARTICLE'),
            ('Thông tư 12/2022/NĐ-CP xử phạt tại Điều 10 khoản 2.','CLAIM_DOCUMENT_TYPE_MISMATCH')):
            with self.subTest(text=text):
                ok,issues=self.audit(text)
                self.assertFalse(ok)
                self.assertTrue(any(x.startswith(code) for x in issues),issues)

    def test_unrelated_entitlement_cannot_be_created_from_metadata(self):
        ok,issues=self.audit('Mọi công dân được hưởng lương hưu gấp năm lần thu nhập dù chưa từng đóng góp.')
        self.assertFalse(ok)
        self.assertTrue(any(x.startswith('CLAIM_CONTENT_UNSUPPORTED') for x in issues))
