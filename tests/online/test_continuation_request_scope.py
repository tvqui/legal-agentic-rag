import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.models import Evidence,EvidencePlan,LegalLocator
from vn_labor_online.evidence import extend_plan_for_evidence
from vn_labor_online.claim_validation import semantic_issues
from types import SimpleNamespace as NS

class ContinuationRequestScopeTests(unittest.TestCase):
    def plan(self,q):
        a=analyze(intake(q,[]),'2026-09-15');return a,plan_evidence(a)
    def test_colloquial_expiry_with_continued_work_keeps_the_rights_question(self):
        for q in ['Hợp đồng có thời hạn vừa hết 8 ngày, tôi vẫn đi làm mà chưa ký mới. Quyền lợi theo hợp đồng cũ không?',
                  'Hợp đồng xác định thời hạn của tôi đã hết, tôi vẫn làm. Tiền lương trong thời gian này theo hợp đồng cũ không?']:
            with self.subTest(q=q):
                a,p=self.plan(q);self.assertIn('CONTRACT.CONTINUATION',a.legal_subissues)
                self.assertEqual({loc.point for g in p.slot_requirements['contract_continuation'] for loc in g},{'a'})
                self.assertNotIn('renewal_exceptions',p.slot_requirements)
    def test_explicit_conversion_requires_the_prior_deadline_and_conversion_rule(self):
        a,p=self.plan('Hợp đồng lao động hết hạn, tôi vẫn làm việc chưa ký mới thì trở thành loại hợp đồng nào?')
        self.assertEqual({loc.point for g in p.slot_requirements['contract_continuation'] for loc in g},{'a','b'})
    def test_renewal_count_keeps_its_exceptions(self):
        a,p=self.plan('Sau hai hợp đồng lao động xác định thời hạn liên tiếp, người lao động tiếp tục làm việc thì phải ký loại hợp đồng nào? Nêu ngoại lệ.')
        self.assertIn('renewal_exceptions',p.slot_requirements)
        self.assertIn('c',{loc.point for g in p.slot_requirements['term_contract_renewal'] for loc in g})
    def test_housing_contract_does_not_become_an_employment_renewal(self):
        a,p=self.plan('Hợp đồng thuê nhà hết hạn, tôi vẫn sống ở đó thì phải ký mới không?')
        self.assertNotIn('CONTRACT.CONTINUATION',a.legal_subissues)
    def test_optional_source_cannot_invent_a_mandatory_delegation(self):
        plan=EvidencePlan(mandatory_slots=['rule'],slot_requirements={'rule':[[LegalLocator(documents=['TEST'],article='7')]]})
        main=Evidence(unit_id='r',document_number='TEST',article_number='7',kind='PROVISION',text='Quyền nhận thông tin.',retrieval_method='policy',verified=True)
        extra=Evidence(unit_id='x',document_number='OTHER',article_number='99',kind='PROVISION',text='Chính phủ quy định chi tiết.',retrieval_method='bm25',verified=True)
        result=extend_plan_for_evidence(plan,[main,extra],{},'2026-09-15')
        self.assertNotIn('implementing_regulation',result.mandatory_slots)
        self.assertNotIn('exceptions',result.mandatory_slots)
    def test_required_source_still_creates_its_delegation_dependency(self):
        plan=EvidencePlan(mandatory_slots=['rule'],slot_requirements={'rule':[[LegalLocator(documents=['TEST'],article='7')]]})
        main=Evidence(unit_id='r',document_number='TEST',article_number='7',kind='PROVISION',text='Chính phủ quy định chi tiết.',retrieval_method='policy',verified=True)
        self.assertIn('implementing_regulation',extend_plan_for_evidence(plan,[main],{},'2026-09-15').mandatory_slots)
    def test_special_application_population_does_not_define_all_fixed_term_contracts(self):
        source=NS(text='Điều 2. Đối tượng áp dụng. Người lao động có hợp đồng từ 9 tháng đến 24 tháng làm công việc sau:',full_text='Điều 2. Đối tượng áp dụng. Người lao động có hợp đồng từ 9 tháng đến 24 tháng làm công việc sau:')
        self.assertIn('CLAIM_SPECIAL_POPULATION_AS_GENERAL_DEFINITION',semantic_issues('Hợp đồng lao động xác định thời hạn có thời hạn từ 9 tháng đến 24 tháng.',[source]))
        self.assertNotIn('CLAIM_SPECIAL_POPULATION_AS_GENERAL_DEFINITION',semantic_issues('Đối tượng áp dụng trong phạm vi này có hợp đồng lao động xác định thời hạn từ 9 tháng đến 24 tháng.',[source]))

if __name__=='__main__':unittest.main()
