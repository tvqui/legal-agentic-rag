from __future__ import annotations
import json
import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace

from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.audit import reference_audit,citations
from vn_labor_online.claim_validation import semantic_issues,proposition_issues
from vn_labor_online.config import AdjudicationConfig,ApplicabilityConfig,ResearcherConfig
from vn_labor_online.evidence import build_verified_pack,state_for
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.issue_mapping import graph_issue_keys
from vn_labor_online.models import Evidence,EvidencePlan,Claim,LegalLocator,RuleProposition
from vn_labor_online.providers import OllamaProvider
from vn_labor_online.researcher import LegalResearcher
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.answer_quality import clean_draft
from tests.online.test_output_precision import rule,pack

class ReviewContentTests(unittest.TestCase):
    def test_travel_only_does_not_require_annual_entitlements(self):
        q='Một người lao động nghỉ phép năm đi đường bộ. Tổng thời gian đi và về là 5 ngày. Khoản nào quy định thời gian đi đường?'
        a=analyze(intake(q,[]),'2025-01-01');p=plan_evidence(a)
        self.assertIn('LEAVE.TRAVEL_DAYS',a.legal_subissues)
        self.assertNotIn('LEAVE.ANNUAL_LEAVE',a.legal_subissues)
        self.assertNotIn('leave_base_rule',p.mandatory_slots)

    def test_definition_of_illegality_is_not_definition_of_parties(self):
        q='Hãy xác định điều luật định nghĩa đơn phương chấm dứt HĐLĐ trái pháp luật và nghĩa vụ của người lao động. Không gộp hai điều luật khác nhau.'
        a=analyze(intake(q,[]),'2025-01-01')
        self.assertNotIn('CONTRACT.PARTY_DEFINITIONS',a.legal_subissues)

    def test_stipulated_training_liability_does_not_reassess_notice(self):
        q='Khi NLĐ đơn phương chấm dứt HĐLĐ trái pháp luật và có hợp đồng đào tạo, những điều luật nào điều chỉnh nghĩa vụ hoàn trả?'
        a=analyze(intake(q,[]),'2025-01-01');p=plan_evidence(a)
        self.assertFalse(a.missing_facts)
        self.assertEqual(a.facts['query_intent'],'STIPULATED_EMPLOYEE_LIABILITY')
        self.assertNotIn('notice_requirement',p.mandatory_slots)
        self.assertIn('training_liability',p.slot_requirements)
        self.assertNotIn('unlawful',a.facts)

    def test_intern_pay_asks_relationship_not_date(self):
        a=analyze(intake('Tôi sắp đi thực tập tại một công ty. Tôi có được trả lương không?',[]),'2025-01-01')
        self.assertTrue(any('chương trình của trường' in q for q in a.missing_facts))
        self.assertFalse(any('Thời điểm' in q for q in a.missing_facts))

    def test_overtime_waiver_explanation_does_not_ask_event_date(self):
        a=analyze(intake('NLĐ ký giấy tự nguyện làm thêm không nhận tiền thì NSDLĐ có được miễn trả tiền làm thêm không?',[]),'2025-01-01')
        self.assertFalse(a.missing_facts)
        self.assertIn('overtime_pay',plan_evidence(a).slot_requirements)

    def test_night_holiday_pay_does_not_retrieve_list_of_holidays(self):
        a=analyze(intake('Một ca vừa là làm thêm giờ, vừa ban đêm, vừa rơi vào ngày lễ thì phải kết hợp các quy định nào?',[]),'2025-01-01')
        p=plan_evidence(a)
        self.assertNotIn('public_holiday_rule',p.slot_requirements)
        self.assertIn('night_overtime_pay',p.slot_requirements)
        self.assertIn('night_overtime_formula',p.slot_requirements)

    def test_probation_current_and_historical_have_different_complete_groups(self):
        q='Thời gian thử việc tối đa của từng nhóm công việc là bao nhiêu?'
        new=plan_evidence(analyze(intake(q,[]),'2025-01-01'))
        old=plan_evidence(analyze(intake(q,[]),'2020-12-15'))
        self.assertEqual(len(new.slot_requirements['probation_duration']),4)
        self.assertEqual(len(old.slot_requirements['probation_duration']),3)
        self.assertTrue(all(g[0].documents==['10/2012/QH13'] for g in old.slot_requirements['probation_duration']))

    def test_complete_probation_answer_has_180_days_and_skips_llm(self):
        texts=['Không quá 180 ngày đối với công việc của người quản lý doanh nghiệp.',
          'Không quá 60 ngày đối với công việc cần trình độ từ cao đẳng trở lên.',
          'Không quá 30 ngày đối với công việc cần trình độ trung cấp.',
          'Không quá 06 ngày làm việc đối với công việc khác.']
        items=[rule(f'p{i}','25',str(i),text=text) for i,text in enumerate(texts,1)]
        engine=LegalAdjudicator(AdjudicationConfig());engine.provider=Mock()
        draft,warnings=engine.generate(pack('Thời gian thử việc tối đa của từng nhóm công việc là bao nhiêu?',items),False)
        engine.provider.structured.assert_not_called()
        self.assertEqual({c.proposition.value for c in draft.claims},{180,60,30,6})
        self.assertNotIn('60 ngày làm việc',draft.answer_summary)
        self.assertTrue(reference_audit(draft.answer_summary,items,citations(items),draft.claims)[0])

    def test_missing_probation_branch_cannot_be_promoted_by_other_clauses(self):
        q='Thời gian thử việc tối đa của từng nhóm công việc là bao nhiêu?'
        p=plan_evidence(analyze(intake(q,[]),'2025-01-01'))
        items=[rule(str(i),'25',str(i),text='Không quá 60 ngày.') for i in (2,3,4)]
        self.assertIn('probation_duration',state_for(items,p,'2025-01-01').gaps)

    def test_numeric_proposition_cannot_be_forged(self):
        item=rule('a','25','2',text='Không quá 60 ngày đối với công việc cần trình độ cao đẳng.')
        claim=Claim(claim_id='c',text='Không quá 90 ngày.',evidence_ids=['a'],proposition=RuleProposition(
          predicate='PROBATION_LIMIT',value=90,unit='ngày',locator=LegalLocator(documents=['45/2019/QH14'],article='25',clause='2')))
        self.assertIn('CLAIM_PROPOSITION_NOT_SUPPORTED',proposition_issues(claim,[item]))

    def test_sanction_omission_is_not_prohibition(self):
        item=rule('sanction','14','2','a',text='Phạt tiền đối với hành vi không đào tạo cho người lao động trước khi chuyển nghề.',doc='12/2022/NĐ-CP')
        bad='Người sử dụng lao động không được đào tạo cho người lao động trước khi chuyển nghề.'
        self.assertIn('CLAIM_OMISSION_DUTY_INVERTED',semantic_issues(bad,[item]))
        c=Claim(claim_id='c',text=bad,evidence_ids=['sanction'])
        self.assertFalse(reference_audit(bad+' [sanction]',[item],citations([item]),[c])[0])
        self.assertFalse(semantic_issues('Hành vi không đào tạo cho người lao động trước khi chuyển nghề bị phạt tiền.',[item]))

    def test_adjudicator_rejects_inverted_model_output_and_uses_source_fallback(self):
        item=rule('sanction','14','2','a',text='Phạt tiền đối với hành vi không đào tạo cho người lao động trước khi chuyển nghề.',doc='12/2022/NĐ-CP')
        engine=LegalAdjudicator(AdjudicationConfig());engine.provider=Mock()
        engine.provider.structured.return_value={'claims':[{'text':'Người sử dụng lao động không được đào tạo cho người lao động trước khi chuyển nghề.','evidence_ids':['sanction']}]}
        draft,warnings=engine.generate(pack('Quy định xử phạt hành vi không đào tạo là gì?',[item]),False)
        self.assertNotIn('không được đào tạo',draft.answer_summary)
        self.assertTrue(any(w.startswith('ADJUDICATION_PROVIDER_FALLBACK') for w in warnings))

    def test_wrong_document_type_is_rejected_and_pack_has_metadata(self):
        item=rule('x','40','3',text='Hoàn trả chi phí đào tạo.',doc='18/VBHN-VPQH')
        self.assertIn('CLAIM_DOCUMENT_TYPE_MISMATCH',semantic_issues('Nghị định số 18/VBHN-VPQH quy định hoàn trả chi phí đào tạo.',[item]))
        evidence=pack('Chi phí đào tạo',[item]).evidence[0]
        self.assertEqual(evidence.document_type,'Văn bản hợp nhất')
        self.assertEqual(citations([item])[0].document_type,'Văn bản hợp nhất')

    def test_old_reason_requirement_and_training_exception_are_blocked(self):
        item=rule('x','35',text='Người lao động có quyền đơn phương chấm dứt hợp đồng nhưng phải báo trước.')
        self.assertTrue(semantic_issues('Người lao động được nghỉ nếu có lý do chính đáng.',[item]))
        self.assertTrue(semantic_issues('Đào tạo là trường hợp được nghỉ không cần báo trước.',[item]))

    def test_calendar_days_cannot_be_relabelled_as_working_days(self):
        item=rule('x','25','2',text='Không quá 60 ngày đối với công việc cần trình độ cao đẳng.')
        self.assertIn('CLAIM_PROBATION_DAY_UNIT_MISMATCH',semantic_issues('Không quá 60 ngày làm việc.',[item]))

    def test_all_offline_issue_keys_are_reachable(self):
        import yaml
        from pathlib import Path
        from vn_labor_online.issue_mapping import GRAPH_ISSUES
        offline=set(yaml.safe_load(Path('config/issues.yaml').read_text(encoding='utf-8'))['issues'])
        self.assertTrue(offline<=graph_issue_keys(list(GRAPH_ISSUES)))

    def test_profile_auditor_does_not_pass_unrelated_neighbour(self):
        items=[rule('right','98','1','a',text='Tiền lương làm thêm ít nhất 150%.'),rule('wrong','112','1','a',text='Tết Dương lịch: 01 ngày.')]
        accepted,decisions,_=LegalApplicabilityAuditor(ApplicabilityConfig()).audit(items,
          'NLĐ tự nguyện làm thêm không nhận tiền thì NSDLĐ có được miễn trả tiền làm thêm không?', ['WAGE'],{},'ASSESS_LEGALITY')
        self.assertIn('right',{x.unit_id for x in accepted})
        self.assertNotIn('wrong',{x.unit_id for x in accepted})

    def test_duplicates_are_collapsed_without_losing_citation_ids(self):
        from vn_labor_online.models import AdjudicationDraft
        draft=AdjudicationDraft(answer_summary='Lặp.',claims=[Claim(claim_id='a',text='Tiền lương do hai bên thỏa thuận.',evidence_ids=['one']),Claim(claim_id='b',text='Tiền lương do hai bên thỏa thuận.',evidence_ids=['two'])],applicable_law_versions=[])
        cleaned=clean_draft(draft,'Tiền lương?')
        self.assertEqual(len(cleaned.claims),1)
        self.assertEqual(cleaned.claims[0].evidence_ids,['one','two'])

    def test_http_reuses_client_and_does_not_retry_schema_error(self):
        p=OllamaProvider();p.client=Mock()
        response=Mock(status_code=200);response.json.return_value={'message':{'content':'not json'}}
        p.client.post.return_value=response
        with self.assertRaises(Exception): p.structured('s','u',{})
        self.assertEqual(p.client.post.call_count,1)
        p.close();response.close.assert_not_called()

    def test_transient_http_retry_is_bounded(self):
        p=OllamaProvider();p.client=Mock()
        first=Mock(status_code=503);second=Mock(status_code=200)
        second.json.return_value={'message':{'content':'{"ok":true}'}}
        p.client.post.side_effect=[first,second]
        with patch('vn_labor_online.providers.time.sleep'):
            self.assertEqual(p.structured('s','u',{}),{'ok':True})
        self.assertEqual(p.client.post.call_count,2)


    def test_exact_parent_slot_cannot_be_satisfied_by_a_child_point(self):
        from vn_labor_online.taxonomy import locator_matches
        child=rule('child','107','3','a',text='Một ngành được phép làm thêm.')
        parent=rule('parent','107','3',text='Không quá 300 giờ trong 01 năm.')
        locator=LegalLocator(documents=['45/2019/QH14'],article='107',clause='3',exact_level=True)
        self.assertFalse(locator_matches(child,locator))
        self.assertTrue(locator_matches(parent,locator))

    def test_fee_requirement_needs_the_fee_text_not_just_location(self):
        from vn_labor_online.taxonomy import locator_matches
        locator=LegalLocator(documents=['18/VBHN-VPQH'],article='61',clause='2',exact_level=True,text_contains=['không được thu học phí'])
        self.assertFalse(locator_matches(rule('a','61','2',doc='18/VBHN-VPQH',text='Thời hạn tập nghề không quá 03 tháng.'),locator))
        self.assertTrue(locator_matches(rule('b','61','2',doc='18/VBHN-VPQH',text='Người sử dụng lao động không được thu học phí.'),locator))

    def test_negated_reason_requirement_is_not_rejected(self):
        item=rule('x','35',text='Người lao động có quyền đơn phương chấm dứt nhưng phải báo trước.')
        self.assertFalse(semantic_issues('Người lao động không cần có lý do chính đáng để đơn phương chấm dứt.',[item]))

    def test_numeric_proposition_requires_exact_day_unit(self):
        item=rule('x','25','4',text='Không quá 06 ngày làm việc đối với công việc khác.')
        claim=Claim(claim_id='c',text='Không quá 06 ngày.',evidence_ids=['x'],proposition=RuleProposition(predicate='PROBATION_LIMIT',value=6,unit='ngày',locator=LegalLocator(documents=['45/2019/QH14'],article='25',clause='4')))
        self.assertIn('CLAIM_PROPOSITION_NOT_SUPPORTED',proposition_issues(claim,[item]))

    def test_historical_probation_renderer_uses_only_old_three_branches(self):
        items=[rule('p'+str(i),'27',str(i),doc='10/2012/QH13',text=t) for i,t in enumerate(['Không quá 60 ngày đối với công việc có trình độ cao đẳng.','Không quá 30 ngày đối với công việc cần trình độ trung cấp.','Không quá 06 ngày làm việc đối với công việc khác.'],1)]
        original=pack('Thời gian thử việc tối đa của từng nhóm công việc là bao nhiêu?',items)
        historical=original.model_copy(update={'query_date':'2020-12-15'})
        engine=LegalAdjudicator(AdjudicationConfig());engine.provider=Mock()
        draft,_=engine.generate(historical,False)
        engine.provider.structured.assert_not_called()
        self.assertEqual({c.proposition.value for c in draft.claims},{60,30,6})
        self.assertNotIn('180',draft.answer_summary)


    def test_night_holiday_chain_does_not_require_other_day_types(self):
        question='Một ca vừa là làm thêm giờ, vừa ban đêm, vừa rơi vào ngày lễ thì phải kết hợp các quy định nào?'
        plan=plan_evidence(analyze(intake(question,[]),'2025-01-01'))
        groups=plan.slot_requirements['overtime_pay']
        self.assertEqual({loc.point for group in groups for loc in group},{None,'c'})
        general=plan_evidence(analyze(intake('Tiền lương làm thêm vào ngày thường, ngày nghỉ hằng tuần và ngày lễ là bao nhiêu?',[]),'2025-01-01'))
        self.assertEqual({loc.point for group in general.slot_requirements['overtime_pay'] for loc in group},{None,'a','b','c'})


    def test_researcher_skips_known_contextual_parents_but_keeps_independent_issue(self):
        researcher=LegalResearcher(ResearcherConfig(mode='ollama'))
        queries=[
            'Hãy phân biệt điều luật định nghĩa đơn phương chấm dứt HĐLĐ trái pháp luật và nghĩa vụ của người lao động.',
            'Khi NLĐ đơn phương chấm dứt HĐLĐ trái pháp luật và có hợp đồng đào tạo, những điều luật nào điều chỉnh nghĩa vụ hoàn trả?',
            'Tôi nghỉ việc trước thời hạn cam kết sau đào tạo. Tôi có phải trả tiền cho công ty không?',
            'Giới hạn làm thêm giờ theo ngày, tháng và năm hiện nay thế nào?',
            'Một ca vừa làm thêm giờ, vừa ban đêm, vừa rơi vào ngày lễ thì phải kết hợp các quy định nào?',
        ]
        for query in queries:
            with self.subTest(query=query):
                analysis=analyze(intake(query,[]),'2025-01-01')
                self.assertEqual(researcher.execution_path(analysis),'SKIPPED_KNOWN_PROFILE')
        independent=analyze(intake('Giới hạn làm thêm giờ và thủ tục khởi kiện tranh chấp lao động thế nào?',[]),'2025-01-01')
        self.assertEqual(researcher.execution_path(independent),'MODEL_REQUESTED')


    def test_question_or_negation_is_not_a_stipulated_unlawful_fact(self):
        for query in (
          'Khi NLĐ đơn phương chấm dứt HĐLĐ thì có bị coi là trái pháp luật không?',
          'Khi NLĐ đơn phương chấm dứt HĐLĐ không trái pháp luật thì có phải hoàn trả chi phí đào tạo không?',
        ):
            with self.subTest(query=query):
                analysis=analyze(intake(query,[]),'2025-01-01')
                self.assertNotEqual(analysis.facts.get('query_intent'),'STIPULATED_EMPLOYEE_LIABILITY')

    def test_training_query_keeps_an_explicit_notice_question(self):
        query='Tôi ký hợp đồng lao động không xác định thời hạn, có hợp đồng đào tạo. Thời hạn báo trước khi tôi đơn phương nghỉ việc là bao nhiêu và nghĩa vụ hoàn trả chi phí đào tạo thế nào?'
        analysis=analyze(intake(query,[]),'2025-01-01')
        self.assertIn('TRAINING.COST_REPAYMENT',analysis.legal_subissues)
        self.assertIn('TERMINATION.EMPLOYEE_UNILATERAL',analysis.legal_subissues)
        plan=plan_evidence(analysis)
        self.assertIn('training_contract',plan.slot_requirements)
        self.assertIn('notice_requirement',plan.slot_requirements)

    def test_mixed_notice_training_question_is_not_answered_with_notice_only(self):
        items=[rule('notice','35','1','a',text='Báo trước ít nhất 45 ngày đối với hợp đồng không xác định thời hạn.'),
          rule('definition','39',text='Đơn phương không đúng Điều 35 là trái pháp luật.'),
          rule('training','62','1',text='Hai bên phải ký kết hợp đồng đào tạo nghề.')]
        evidence=pack('Thời hạn báo trước và nghĩa vụ hoàn trả chi phí đào tạo thế nào?',items).model_copy(update={
          'requested_outcome':'ASSESS_LEGALITY','facts':{'actor':'EMPLOYEE','contract_type':'INDEFINITE','notice_days':20,'special_occupation':False,'notice_exception':False}})
        engine=LegalAdjudicator(AdjudicationConfig());engine.provider=Mock()
        engine.provider.structured.return_value={'claims':[{'text':'Hai bên phải ký kết hợp đồng đào tạo nghề.','evidence_ids':['training']}]}
        engine._generate(evidence,True)
        engine.provider.structured.assert_called_once()

if __name__=='__main__': unittest.main()
