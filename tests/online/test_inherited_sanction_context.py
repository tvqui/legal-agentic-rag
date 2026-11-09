import unittest
from vn_labor_online.models import Evidence,EvidenceState
from vn_labor_online.evidence import build_verified_pack
from vn_labor_online.claim_validation import semantic_issues

class InheritedSanctionContextTests(unittest.TestCase):
    def test_raw_evidence_and_verified_pack_share_the_parent_fine_context(self):
        item=Evidence(unit_id='fine',retrieval_method='policy',kind='PROVISION',verified=True,
            text='b) Dùng tiền phạt thay cho kỷ luật.',source_text='b) Dùng tiền phạt thay cho kỷ luật.',
            ancestor_context='Phạt tiền từ 12.000.000 đồng đến 18.000.000 đồng đối với người sử dụng lao động có hành vi sau:',
            document_number='12/2022/NĐ-CP',article_number='19',clause_number='3',point_number='b')
        pack=build_verified_pack('Chế tài hành vi này là gì?','2026-09-15',{},EvidenceState(slots={},gaps=[],coverage=1),[item])
        claim='Người sử dụng lao động bị phạt tiền từ 12.000.000 đồng đến 18.000.000 đồng về hành vi dùng tiền phạt thay cho kỷ luật.'
        raw=semantic_issues(claim,[item]);verified=semantic_issues(claim,pack.evidence)
        self.assertNotIn('CLAIM_MONETARY_PENALTY_WITHOUT_SANCTION_SOURCE',raw)
        self.assertEqual(raw,verified)
    def test_missing_parent_amount_still_requires_a_sanction_source(self):
        item=Evidence(unit_id='rule',retrieval_method='policy',text='Không được phạt tiền nhân viên.',ancestor_context='Hành vi bị cấm')
        self.assertIn('CLAIM_MONETARY_PENALTY_WITHOUT_SANCTION_SOURCE',semantic_issues('Người sử dụng lao động bị phạt tiền 18.000.000 đồng.',[item]))

if __name__=='__main__':unittest.main()
