"""Source quotations retain artifact characters, independently of generated claims."""
import json
from types import SimpleNamespace
import unittest
from vn_labor_online.audit import citations,deterministic_audit,reference_audit
from vn_labor_online.retrieval import as_evidence

class CitationSourceTextTests(unittest.TestCase):
    raw='  Điều 7. Nội dung nguồn\r\n\t1. Không quá 02 ngày; nếu đủ điều kiện.\n  a) Giữ  hai khoảng trắng, dấu “ngoặc” và chữ a\u0301.\n'
    def fixture(self,raw=True):
        unit={'unit_id':'prov_source','kind':'PROVISION','document_id':'doc_source',
            'document_number':'TEST','document_title':'Văn bản thử nghiệm','article_number':'7',
            'clause_number':None,'point_number':None,'text':'Một bản hiển thị đã rút gọn.',
            'source_url':'https://example.org/source','ancestor_context':'KHÔNG GHÉP TIÊU ĐỀ NÀY VÀO TRÍCH NGUYÊN VĂN',
            'provenance':{'file_id':'file_source'},'provenance_span':{'char_start':0,'char_end':len(self.raw)}}
        if raw:unit['source_text']=self.raw
        store=SimpleNamespace(units_by_id={'prov_source':unit},nodes_by_id={
            'doc_source':{},'prov_source':{'properties':{'article_number':'7'}}},
            catalog_by_file_id={'file_source':{'catalog_status':'VERIFIED','source_url':unit['source_url']}})
        item=as_evidence(unit,1,'exact',1)
        checked=deterministic_audit(store,[item],None)[0]
        self.assertTrue(checked.verified,checked.audit_issues)
        return store,checked
    def test_serialized_citation_keeps_every_source_character(self):
        _,item=self.fixture();ref=citations([item])[0]
        self.assertEqual(ref.source_text,self.raw)
        self.assertEqual(json.loads(ref.model_dump_json())['source_text'],self.raw)
        self.assertNotIn('KHÔNG GHÉP',ref.source_text)
        self.assertTrue(reference_audit('Đối chiếu [prov_source]',[item],[ref])[0])
    def test_missing_raw_text_never_falls_back_to_retrieval_display(self):
        _,item=self.fixture(raw=False)
        self.assertIsNone(citations([item])[0].source_text)
    def test_changed_source_cannot_pass_unit_integrity_check(self):
        store,item=self.fixture()
        forged=item.model_copy(update={'source_text':self.raw.replace('Không','Có')})
        checked=deterministic_audit(store,[forged],None)[0]
        self.assertFalse(checked.verified)
        self.assertIn('SOURCE_TEXT_NOT_FROM_UNIT',checked.audit_issues)
    def test_changed_public_excerpt_cannot_pass_final_reference_audit(self):
        _,item=self.fixture();ref=citations([item])[0]
        ref.source_text=self.raw.replace('Không','Có')
        ok,issues=reference_audit('Đối chiếu [prov_source]',[item],[ref])
        self.assertFalse(ok);self.assertIn('CITATION_SOURCE_TEXT_MISMATCH',issues)

if __name__=='__main__':unittest.main()
