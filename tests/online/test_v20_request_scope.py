import json
import unittest
from unittest.mock import Mock,patch
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.answer_quality import language_issues
from vn_labor_online.answer_review import review_answer,Review,review_error_details
from vn_labor_online.errors import LLMProviderError
from vn_labor_online.evidence import extend_plan_for_evidence
from vn_labor_online.models import Evidence,EvidencePlan,LegalLocator
from vn_labor_online.taxonomy import profile_covers_issues


class RequestScopeTests(unittest.TestCase):
    def test_paid_leave_qualifier_does_not_create_an_independent_wage_question(self):
        for q in ('Tôi kết hôn thì được nghỉ việc riêng hưởng nguyên lương mấy ngày?',
                  'Tôi kết hôn thì được nghỉ có hưởng lương bao nhiêu ngày?',
                  'Ngày Quốc khánh được nghỉ có lương mấy ngày?'):
            with self.subTest(q=q):
                a=analyze(intake(q,[]),'2026-09-15')
                self.assertTrue(profile_covers_issues(a))

    def test_independent_wage_or_bonus_request_is_not_erased(self):
        for suffix in ('Tiền lương làm căn cứ chi trả tính thế nào?',
                       'Thưởng chuyên cần trong các ngày này tính thế nào?',
                       'Lương tháng thứ 13 công ty có bắt buộc trả không?'):
            with self.subTest(suffix=suffix):
                a=analyze(intake('Tôi kết hôn được nghỉ hưởng nguyên lương mấy ngày? '+suffix,[]),'2026-09-15')
                self.assertFalse(profile_covers_issues(a))

    def source(self,uid,article,text):
        return Evidence(unit_id=uid,kind='PROVISION',document_number='TEST',article_number=article,
            clause_number='1',text=text,verified=True,retrieval_method='policy')

    def test_off_profile_reference_cannot_add_an_unrequested_exception(self):
        p=EvidencePlan(mandatory_slots=['rule'],slot_requirements={'rule':[[LegalLocator(documents=['TEST'],article='90')]]})
        main=self.source('main','90','Quy định về hiệu lực thi hành.')
        side=self.source('side','91','Quy tắc khác, trừ trường hợp quy định tại khoản 2 Điều này.')
        result=extend_plan_for_evidence(p,[main,side],{},'2026-09-15')
        self.assertNotIn('exceptions',result.mandatory_slots)
        # Its exception is still required when that rule is actually requested.
        p.slot_requirements['rule']=[[LegalLocator(documents=['TEST'],article='91')]]
        self.assertIn('exceptions',extend_plan_for_evidence(p,[main,side],{},'2026-09-15').mandatory_slots)

    def test_unprofiled_independent_task_keeps_its_own_dependencies(self):
        p=EvidencePlan(mandatory_slots=['rule'],slot_requirements={'rule':[[LegalLocator(documents=['TEST'],article='90')]]},
            task_queries={'independent':'Quyền khác của các bên?'})
        side=self.source('side','91','Quy tắc khác, trừ trường hợp quy định tại khoản 2 Điều này.')
        self.assertIn('exceptions',extend_plan_for_evidence(p,[side],{},'2026-09-15').mandatory_slots)

    def test_temporal_selection_has_a_complete_plan_without_calling_researcher(self):
        from vn_labor_online.researcher import LegalResearcher
        from vn_labor_online.config import ResearcherConfig
        q='Hợp đồng ký ngày 12/04/2017, công ty chấm dứt ngày 03/08/2026. Phải đánh giá theo thời điểm nào?'
        a=analyze(intake(q,[]))
        researcher=LegalResearcher(ResearcherConfig(mode='ollama'));researcher.provider=Mock()
        self.assertEqual(researcher.execution_path(a),'SKIPPED_KNOWN_PROFILE')
        result,_=researcher.enrich(a,q,[])
        researcher.provider.structured.assert_not_called()
        self.assertEqual(result.query_date,'2026-08-03')
        self.assertIn('labour_contract_transition',plan_evidence(result).slot_requirements)

    def test_medical_costs_require_the_intro_and_all_statutory_branches(self):
        a=analyze(intake('Người lao động bị tai nạn lao động được thanh toán các chi phí y tế nào?',[]),'2026-09-15')
        groups=plan_evidence(a).slot_requirements['accident_medical_costs']
        self.assertEqual({loc.point for group in groups for loc in group},{None,'a','b','c'})
        self.assertTrue(all(loc.article=='38' and loc.clause=='2' for group in groups for loc in group))

    def test_suspect_joined_medical_word_is_flagged_without_guessing_a_repair(self):
        self.assertIn('SUSPECT_OCR_WORD',language_issues('2. Thanh toán chi phí = ytế nghề'))
        self.assertEqual(language_issues('Chi phí y tế = 1.000.000 đồng.'),[])

    def test_narrow_medical_payer_question_does_not_request_every_cost_category(self):
        a=analyze(intake('Ai thanh toán chi phí y tế khi người lao động bị tai nạn lao động?',[]),'2026-09-15')
        groups=plan_evidence(a).slot_requirements['accident_medical_costs']
        self.assertEqual({loc.point for group in groups for loc in group},{None})

    def test_safe_provider_diagnostics_do_not_publish_arbitrary_exception_fields(self):
        exc=LLMProviderError('private',safe_diagnostics={'error_reason':'SCHEMA_REJECTED',
            'api_status':'INVALID_ARGUMENT','error_fields':['response_json_schema','private-key-value'],
            'raw':'private-token'})
        details=review_error_details(exc)
        self.assertEqual(details['error_reason'],'SCHEMA_REJECTED')
        self.assertEqual(details['error_fields'],['response_json_schema'])
        self.assertNotIn('private',json.dumps(details))

    def test_application_repair_receives_the_outcome_and_is_reaudited(self):
        from tests.online.test_application_coverage_contract import ApplicationCoverageContractTests
        p,d,r,tasks=ApplicationCoverageContractTests().fixture(
            'Người nhận hồ sơ phải gửi xác nhận trong thời hạn 07 ngày làm việc.')
        second=r.model_copy(deep=True)
        second.claims[0].claim_id='claim_001'
        second.coverage[0].claim_ids=['claim_001']
        provider=Mock();provider.structured.return_value={'claims':[{'text':
            'Nếu đã qua 12 ngày làm việc mà chưa xác nhận thì đã vượt thời hạn 07 ngày làm việc.',
            'evidence_ids':['source']}]}
        with patch('vn_labor_online.answer_review.audit_in_batches',side_effect=[r,second]) as audit:
            result,_=review_answer(provider,d,p,1)
        self.assertEqual(result.semantic_review['status'],'PASS')
        self.assertEqual(audit.call_count,2)
        prompt,payload,_=provider.structured.call_args.args
        self.assertIn('PUBLIC claim text',prompt)
        self.assertEqual(json.loads(payload)['input']['requested_outcome'],'ASSESS_LEGALITY')


if __name__=='__main__':unittest.main()
