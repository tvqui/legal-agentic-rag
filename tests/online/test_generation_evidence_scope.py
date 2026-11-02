import unittest
from unittest.mock import Mock
from vn_labor_online.evidence_budget import generation_evidence
from vn_labor_online.models import EvidenceState,VerifiedEvidencePack,VerifiedEvidenceItem,EvidencePlan,LegalLocator,ExplicitReference
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.config import AdjudicationConfig

class GenerationEvidenceScopeTests(unittest.TestCase):
    def pack(self,query='Công ty có phải trả đủ tiền lương cho thời gian bị tạm đình chỉ công việc không?'):
        rule=VerifiedEvidenceItem(evidence_id='r',instrument_number='TEST-RULE',article='71',clause='4',
            text='Nếu không bị xử lý kỷ luật thì người lao động được trả đủ tiền lương.',norm_role='RULE')
        fine=VerifiedEvidenceItem(evidence_id='f',instrument_number='TEST-FINE',article='9',clause='2',
            text='Phạt tiền đối với hành vi không trả đủ lương.',norm_role='SANCTION')
        return VerifiedEvidencePack(query=query,coverage_state=EvidenceState(slots={},gaps=[],coverage=1),evidence=[rule,fine])
    def test_unrequested_optional_fines_do_not_enter_generation(self):
        pack=self.pack();self.assertEqual([e.evidence_id for e in generation_evidence(pack)],['r'])
        self.assertEqual(len(pack.evidence),2)
    def test_fines_are_preserved_when_requested(self):
        for q in ['Công ty bị phạt bao nhiêu?','Nêu chế tài và hậu quả của hành vi.']:
            with self.subTest(q=q):self.assertEqual(len(generation_evidence(self.pack(q))),2)
    def test_required_sanction_dependency_is_not_removed(self):
        pack=self.pack();pack.evidence_plan=EvidencePlan(mandatory_slots=['remedy'],
            slot_requirements={'remedy':[[LegalLocator(documents=['TEST-FINE'],article='9',clause='2')]]})
        self.assertEqual(len(generation_evidence(pack)),2)
    def test_explicit_literal_source_survives(self):
        pack=self.pack('Giải thích Điều 9 văn bản TEST-FINE.')
        pack.lookup_reference=ExplicitReference(instrument_number='TEST-FINE',article='9')
        self.assertEqual(len(generation_evidence(pack)),2)
    def test_each_explicit_reference_survives_in_a_multi_instrument_request(self):
        pack=self.pack('Giải thích Điều 9 khoản khác và Điều 9 Nghị định 12/2022/NĐ-CP.')
        pack.evidence[1].instrument_number='12/2022/NĐ-CP'
        self.assertEqual(len(generation_evidence(pack)),2)
    def test_only_sanctions_cannot_be_misrepresented_as_a_governing_rule(self):
        pack=self.pack();pack.evidence=pack.evidence[1:]
        self.assertEqual(generation_evidence(pack)[0].norm_role,'SANCTION')
    def test_generation_view_does_not_mutate_review_sources(self):
        engine=LegalAdjudicator(AdjudicationConfig())
        engine._generate=Mock(wraps=engine._generate)
        pack=self.pack();engine._generate_with_layout(pack,False)
        supplied=engine._generate.call_args.args[0]
        self.assertEqual([e.evidence_id for e in supplied.evidence],['r'])
        self.assertEqual([e.evidence_id for e in pack.evidence],['r','f'])
if __name__=='__main__':unittest.main()
