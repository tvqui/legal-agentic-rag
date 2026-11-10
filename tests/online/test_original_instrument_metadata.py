import unittest
from vn_labor_online.retrieval import as_evidence
from vn_labor_online.models import EvidenceState,VerifiedEvidenceItem
from vn_labor_online.evidence import build_verified_pack
from vn_labor_online.claim_validation import semantic_issues
from vn_labor_online.models import ExplicitReference
from vn_labor_online.retrieval import Retriever
from vn_labor_online.config import OnlineConfig
from types import SimpleNamespace as NS


class OriginalInstrumentMetadataTests(unittest.TestCase):
    def test_original_identity_survives_retrieval_and_packing(self):
        unit={'unit_id':'e','text':'Nội dung quy định được trích từ bản hợp nhất.',
            'document_number':'99/VBHN-TEST','instrument_number':'17/2020/QH14',
            'document_title':'Văn bản hợp nhất Luật Quản lý hồ sơ'}
        evidence=as_evidence(unit,1,'policy',1).model_copy(update={'verified':True})
        pack=build_verified_pack('Quy định gì?',None,{},EvidenceState(slots={},gaps=[],coverage=1),[evidence])
        self.assertEqual(pack.evidence[0].instrument_number,'99/VBHN-TEST')
        self.assertEqual(pack.evidence[0].original_instrument_number,'17/2020/QH14')

    def item(self,**kwargs):
        return VerifiedEvidenceItem(evidence_id='e',instrument_number='99/VBHN-TEST',
            original_instrument_number='17/2020/QH14',document_title='Văn bản hợp nhất Luật Quản lý hồ sơ',
            text='Bên nhận phải lập danh mục hồ sơ.',**kwargs)

    def test_effective_year_cannot_replace_enactment_year_in_a_name(self):
        issues=semantic_issues('Theo Luật Quản lý hồ sơ năm 2022, bên nhận phải lập danh mục hồ sơ.',[self.item(valid_from='2022-01-01')])
        self.assertIn('CLAIM_INSTRUMENT_YEAR_MISMATCH',issues)

    def test_enactment_and_effective_years_can_be_stated_separately(self):
        issues=semantic_issues('Luật Quản lý hồ sơ năm 2020 có hiệu lực từ năm 2022.',[self.item(valid_from='2022-01-01')])
        self.assertNotIn('CLAIM_INSTRUMENT_YEAR_MISMATCH',issues)

    def test_consolidation_number_alone_does_not_prove_an_enactment_year(self):
        item=self.item().model_copy(update={'original_instrument_number':None})
        self.assertNotIn('CLAIM_INSTRUMENT_YEAR_MISMATCH',semantic_issues('Luật Quản lý hồ sơ năm 2022 quy định về hồ sơ.',[item]))

    def test_edition_year_is_not_confused_with_the_original_enactment_year(self):
        item=self.item(version_role='CONSOLIDATED',consolidation_as_of='2026-02-12')
        self.assertNotIn('CLAIM_INSTRUMENT_YEAR_MISMATCH',semantic_issues('Văn bản hợp nhất Luật Quản lý hồ sơ năm 2026 quy định về hồ sơ.',[item]))
        self.assertIn('CLAIM_INSTRUMENT_YEAR_MISMATCH',semantic_issues('Luật Quản lý hồ sơ năm 2026 quy định về hồ sơ.',[item]))

    def test_exact_lookup_accepts_an_explicit_edition_identifier(self):
        unit={'unit_id':'edition','text':'Nội dung đã hợp nhất.','level':'ARTICLE',
              'article_number':'9','document_number':'99/VBHN-TEST','instrument_number':'17/2020/QH14'}
        original={**unit,'unit_id':'original','document_number':'17/2020/QH14'}
        store=NS(units=[unit,original],units_by_id={'edition':unit,'original':original},nodes=[],edges=[])
        retriever=Retriever(store,OnlineConfig(artifact_source='unused'))
        edition=retriever.exact([ExplicitReference(instrument_number='99/VBHN-TEST',article='9')])
        self.assertEqual([e.unit_id for e in edition],['edition'])
        original_hits=retriever.exact([ExplicitReference(instrument_number='17/2020/QH14',article='9')])
        self.assertEqual({e.unit_id for e in original_hits},{'edition','original'})
        self.assertEqual(len(original_hits),2)

    def test_parenthetical_amendment_year_is_not_inferred_from_consolidation(self):
        item=self.item(version_role='CONSOLIDATED',consolidation_as_of='2026-02-12')
        for name in ('Luật Quản lý hồ sơ (sửa đổi, bổ sung năm 2026)',
                     'Luật Quản lý hồ sơ (sửa đổi, bổ sung) năm 2026',
                     'Luật Quản lý hồ sơ sửa đổi và bổ sung năm 2026'):
            with self.subTest(name=name):
                self.assertIn('CLAIM_INSTRUMENT_YEAR_MISMATCH',semantic_issues(name+' quy định về hồ sơ.',[item]))

    def test_explicit_source_amendment_is_not_mistaken_for_a_new_original_law(self):
        item=self.item().model_copy(update={'full_text':
            'Luật này được sửa đổi, bổ sung bởi Luật số 29/2024/QH15. Bên nhận phải lập danh mục hồ sơ.'})
        self.assertNotIn('CLAIM_INSTRUMENT_YEAR_MISMATCH',semantic_issues(
            'Luật Quản lý hồ sơ (sửa đổi, bổ sung năm 2024) yêu cầu bên nhận lập danh mục hồ sơ.',[item]))


if __name__=='__main__':unittest.main()
