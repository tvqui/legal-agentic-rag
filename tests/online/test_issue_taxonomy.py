from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig,OnlineConfig,RetrievalConfig
from vn_labor_online.evidence import state_for,select_for_plan
from vn_labor_online.models import Evidence,QueryRequest,SlotStatus
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_online.researcher import LegalResearcher
from vn_labor_online.config import ResearcherConfig
from vn_labor_online.retrieval import Retriever
from vn_labor_online.taxonomy import classify_subissues,SUBISSUES,TAXONOMY_VERSION
from tests.online.test_online_core import fixture


def analyze_question(query,facts=None,date='2026-09-01'):
    return analyze(intake(query,[]),date,facts)


def evidence(article,clause='',point='',doc='18/VBHN-VPQH',text='Quy định về người lao động.'):
    uid=f'prov_{doc}_{article}_{clause}_{point}'
    return Evidence(unit_id=uid,retrieval_method='policy',verified=True,kind='PROVISION',
        provision_version_id=uid,article_number=article,clause_number=clause,point_number=point,
        document_number=doc,source_text=text,text=text,official_source=True,
        source_catalog_status='VERIFIED',provision_temporal_verified=True)


class IssueTaxonomyTests(unittest.TestCase):
    def test_registry_has_no_entitlement_outcomes_as_independent_topics(self):
        self.assertEqual(len(SUBISSUES),21)
        self.assertNotIn('LEAVE.ANNUAL_LEAVE_12',SUBISSUES)
        self.assertNotIn('LEAVE.ANNUAL_LEAVE_14',SUBISSUES)

    def test_employee_and_severance_coexist_without_assuming_illegality(self):
        a=analyze_question('Người lao động đơn phương chấm dứt hợp đồng có được trợ cấp thôi việc không?')
        self.assertIn('TERMINATION.EMPLOYEE_UNILATERAL',a.legal_subissues)
        self.assertIn('TERMINATION.SEVERANCE',a.legal_subissues)
        self.assertNotIn('TERMINATION.ILLEGAL_TERMINATION',a.legal_subissues)
        self.assertNotIn('unlawful',a.facts)

    def test_explicit_comparison_keeps_both_actors(self):
        a=analyze_question('So sánh người lao động đơn phương và người sử dụng lao động đơn phương chấm dứt hợp đồng.')
        self.assertIn('TERMINATION.EMPLOYEE_UNILATERAL',a.legal_subissues)
        self.assertIn('TERMINATION.EMPLOYER_UNILATERAL',a.legal_subissues)

    def test_mutual_agreement_is_not_notice_or_unlawful_termination(self):
        a=analyze_question('Hai bên thỏa thuận chấm dứt hợp đồng. Có được nghỉ sớm không?')
        slots=plan_evidence(a).mandatory_slots
        self.assertIn('agreement_rule',slots)
        self.assertNotIn('notice_requirement',slots)
        self.assertNotIn('legal_consequences',slots)

    def test_expiry_and_restructuring_require_their_own_rules(self):
        expiry=plan_evidence(analyze_question('Hợp đồng hết hạn thì chấm dứt như thế nào?'))
        self.assertIn('expiry_rule',expiry.mandatory_slots)
        self.assertNotIn('notice_requirement',expiry.mandatory_slots)
        structural=plan_evidence(analyze_question('Công ty cho tôi nghỉ vì thay đổi cơ cấu. Trợ cấp mất việc được tính thế nào?'))
        for slot in ('restructuring_ground_rule','employment_plan_rule','job_loss_allowance_rule'):
            self.assertIn(slot,structural.mandatory_slots)
        self.assertNotIn('notice_requirement',structural.mandatory_slots)

    def test_comparing_benefits_gets_comparison_route_and_both_slots(self):
        a=analyze_question('Trợ cấp thôi việc và trợ cấp mất việc khác nhau như thế nào?')
        self.assertEqual(a.requested_outcome,'COMPARE')
        self.assertEqual(a.route.value,'COMPLEX')
        self.assertIn('severance_rule',plan_evidence(a).mandatory_slots)
        self.assertIn('job_loss_allowance_rule',plan_evidence(a).mandatory_slots)

    def test_benefit_assessment_asks_eligibility_facts_not_notice_period(self):
        a=analyze_question('Tôi có được hưởng trợ cấp thôi việc không?')
        self.assertTrue(any('bảo hiểm thất nghiệp' in question for question in a.missing_facts))
        self.assertFalse(any('báo trước' in question for question in a.missing_facts))

    def test_dismissal_is_both_termination_and_discipline(self):
        a=analyze_question('Công ty sa thải tôi có đúng không?')
        self.assertIn('DISCIPLINE',a.legal_issues)
        self.assertIn('TERMINATION.DISMISSAL',a.legal_subissues)
        plan=plan_evidence(a)
        self.assertIn('dismissal_ground_rule',plan.mandatory_slots)
        self.assertIn('dismissal_procedure_rule',plan.mandatory_slots)
        self.assertNotIn('notice_requirement',plan.mandatory_slots)
        self.assertFalse(any('báo trước' in question for question in a.missing_facts))

    def test_holiday_is_not_annual_leave_calculation(self):
        a=analyze_question('Nghỉ Tết được bao nhiêu ngày và có hưởng lương không?')
        self.assertIn('LEAVE.PUBLIC_HOLIDAY',a.legal_subissues)
        self.assertNotIn('LEAVE.ANNUAL_LEAVE',a.legal_subissues)
        self.assertNotIn(a.facts.get('query_intent'),{'ANNUAL_LEAVE_CALC','ANNUAL_LEAVE_OVERVIEW'})
        self.assertFalse(a.missing_facts)
        self.assertIn('public_holiday_rule',plan_evidence(a).mandatory_slots)

    def test_personal_leave_does_not_enter_resignation_fact_gate(self):
        a=analyze_question('Tôi có được nghỉ việc riêng khi kết hôn không?')
        self.assertNotIn('TERMINATION',a.legal_issues)
        self.assertIn('LEAVE.PERSONAL_LEAVE',a.legal_subissues)
        self.assertFalse(a.missing_facts)
        self.assertNotIn('notice_requirement',plan_evidence(a).mandatory_slots)

    def test_numeral_in_question_does_not_establish_category(self):
        a=analyze_question('Tôi được nghỉ phép năm 14 ngày có đúng không?')
        self.assertNotIn('work_category',a.facts)
        self.assertTrue(any('Công việc' in question for question in a.missing_facts))

    def test_annual_overview_requires_all_three_categories(self):
        a=analyze_question('Người lao động làm việc đủ 12 tháng được nghỉ phép năm bao nhiêu ngày?')
        plan=plan_evidence(a)
        one=evidence('113','1','a',text='12 ngày làm việc.')
        state=state_for([one],plan,a.query_date)
        self.assertEqual(state.slots['leave_base_rule'].status,SlotStatus.MISSING)
        rows=[one,evidence('113','1','b'),evidence('113','1','c')]
        self.assertEqual(state_for(rows,plan,a.query_date).slots['leave_base_rule'].status,SlotStatus.FOUND_VERIFIED)

    def test_selection_preserves_low_score_group_needed_for_full_coverage(self):
        a=analyze_question('Người lao động làm việc đủ 12 tháng được nghỉ phép năm bao nhiêu ngày?')
        plan=plan_evidence(a)
        # High-scoring irrelevant items must not crowd out the third category.
        noise=[evidence(str(i)).model_copy(update={'score':100}) for i in range(10,20)]
        needed=[evidence('113','1',point).model_copy(update={'score':.01}) for point in ('a','b','c')]
        selected,state=select_for_plan(noise+needed,plan,a.query_date,False,4)
        self.assertTrue({item.unit_id for item in needed}.issubset({item.unit_id for item in selected}))
        self.assertEqual(state.slots['leave_base_rule'].status,SlotStatus.FOUND_VERIFIED)
        _,too_small=select_for_plan(needed,plan,a.query_date,False,2)
        self.assertEqual(too_small.slots['leave_base_rule'].status,SlotStatus.MISSING)

    def test_exact_budget_is_not_consumed_by_redundant_generic_evidence(self):
        a=analyze_question('Người lao động làm việc đủ 12 tháng được nghỉ phép năm bao nhiêu ngày?')
        plan=plan_evidence(a)
        noise=evidence('10').model_copy(update={'score':100})
        needed=[evidence('113','1',point) for point in ('a','b','c')]
        selected,state=select_for_plan([noise]+needed,plan,a.query_date,False,3)
        self.assertEqual({item.unit_id for item in selected},{item.unit_id for item in needed})
        self.assertEqual(state.slots['leave_base_rule'].status,SlotStatus.FOUND_VERIFIED)
        self.assertEqual(state.slots['official_source'].status,SlotStatus.FOUND_VERIFIED)

    def test_benefit_intro_does_not_replace_eligibility_and_calculation_clauses(self):
        a=analyze_question('Trợ cấp thôi việc được tính như thế nào?'); plan=plan_evidence(a)
        self.assertEqual(state_for([evidence('46')],plan,a.query_date).slots['severance_rule'].status,SlotStatus.MISSING)
        rows=[evidence('46',str(i)) for i in (1,2,3)]
        self.assertEqual(state_for(rows,plan,a.query_date).slots['severance_rule'].status,SlotStatus.FOUND_VERIFIED)

    def test_wrong_statute_same_article_cannot_fill_holiday_slot(self):
        a=analyze_question('Nghỉ lễ Quốc khánh được bao nhiêu ngày?'); plan=plan_evidence(a)
        wrong=evidence('112',doc='41/2024/QH15')
        self.assertEqual(state_for([wrong],plan,a.query_date).slots['public_holiday_rule'].status,SlotStatus.MISSING)
        correct=[evidence('112','1',point) for point in ('a','b','c','d','đ','e')]
        self.assertEqual(state_for(correct,plan,a.query_date).slots['public_holiday_rule'].status,SlotStatus.FOUND_VERIFIED)

    def test_wrong_actor_cannot_fill_employer_rule(self):
        a=analyze_question('Người sử dụng lao động đơn phương chấm dứt hợp đồng cần điều kiện nào?'); plan=plan_evidence(a)
        self.assertIn('employer_unilateral_rule',plan.mandatory_slots)
        self.assertEqual(state_for([evidence('35')],plan,a.query_date).slots['employer_unilateral_rule'].status,SlotStatus.MISSING)

    def test_historical_plan_uses_old_statute_and_different_locators(self):
        a=analyze_question('Người lao động muốn nghỉ phép năm khi làm việc đủ 12 tháng.',date='2020-12-15')
        plan=plan_evidence(a)
        locators=[locator for groups in plan.slot_requirements.values() for group in groups for locator in group]
        self.assertTrue(locators)
        self.assertTrue(all(locator.documents==['10/2012/QH13'] for locator in locators))
        self.assertEqual({locator.article for locator in locators},{'111'})
        self.assertEqual(state_for([evidence('113','1','a')],plan,a.query_date).slots['leave_base_rule'].status,SlotStatus.MISSING)

    def test_historical_liability_does_not_use_2019_or_employer_obligations(self):
        a=analyze_question('Người lao động đơn phương nghỉ việc trái pháp luật chịu hậu quả gì?',date='2020-12-15')
        locators=plan_evidence(a).slot_requirements['legal_consequences']
        self.assertEqual({loc.article for group in locators for loc in group},{'43'})
        self.assertTrue(all(loc.documents==['10/2012/QH13'] for group in locators for loc in group))

    def test_multisubject_plan_does_not_discard_leave_when_termination_present(self):
        a=analyze_question('Tôi đơn phương nghỉ việc, trợ cấp thôi việc và thanh toán phép năm chưa nghỉ thế nào?')
        slots=plan_evidence(a).mandatory_slots
        self.assertIn('employee_unilateral_rule',slots)
        self.assertIn('severance_rule',slots)
        self.assertIn('unused_leave_payment_rule',slots)
        self.assertNotIn('leave_base_rule',slots)
        self.assertFalse(any('Công việc thuộc' in question for question in a.missing_facts))

    def test_short_notice_requires_all_employee_consequence_clauses(self):
        a=analyze_question('Tôi muốn nghỉ việc, hợp đồng không xác định thời hạn. Tôi chỉ báo trước 20 ngày, không thuộc trường hợp được nghỉ không cần báo trước và không làm công việc đặc thù. Hậu quả là gì?')
        plan=plan_evidence(a)
        rows=[evidence('40','1'),evidence('40','2')]
        self.assertEqual(state_for(rows,plan,a.query_date).slots['legal_consequences'].status,SlotStatus.MISSING)
        rows.append(evidence('40','3'))
        self.assertEqual(state_for(rows,plan,a.query_date).slots['legal_consequences'].status,SlotStatus.FOUND_VERIFIED)

    def test_cross_reference_slots_are_retained_for_late_wage(self):
        a=analyze_question('Người lao động bị trả lương chậm muốn nghỉ ngay, quy định nào và ngoại lệ dẫn chiếu nào áp dụng?')
        plan=plan_evidence(a)
        self.assertIn('wage_delay_reference',plan.slot_requirements)
        loc=plan.slot_requirements['wage_delay_reference'][0][0]
        self.assertEqual((loc.article,loc.clause),('97','4'))

    def test_policy_anchors_keep_alternate_versions_and_avoid_wrong_law(self):
        a=analyze_question('Nghỉ lễ Quốc khánh được bao nhiêu ngày?'); plan=plan_evidence(a)
        rows=[evidence('112','1','đ').model_dump(),evidence('112','1','đ',doc='45/2019/QH14').model_dump(),evidence('112','1','đ',doc='41/2024/QH15').model_dump()]
        for row in rows: row['authority_rank']=100
        cfg=OnlineConfig(artifact_source='unused',retrieval=RetrievalConfig(dense_enabled=False))
        retriever=Retriever(SimpleNamespace(units=rows),cfg)
        got=retriever.policy_anchor(a.legal_issues,a.facts,plan)
        self.assertEqual({item.document_number for item in got},{'18/VBHN-VPQH','45/2019/QH14'})

    def test_applicability_excludes_annual_rule_for_holiday_and_wrong_actor(self):
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig())
        holiday=evidence('112',text='Nghỉ lễ Quốc khánh.'); annual=evidence('113','1','a',text='Nghỉ hằng năm 12 ngày.')
        _,decisions,_=auditor.audit([holiday,annual],'Nghỉ lễ Quốc khánh được bao nhiêu ngày?',['LEAVE'],{},'EXPLAIN')
        decision=next(item for item in decisions if item.evidence_id==annual.unit_id)
        self.assertEqual(decision.audit_status,'FAIL')
        self.assertIn('SUBISSUE_LEAVE_TYPE_MISMATCH',decision.reasons)
        _,decisions,_=auditor.audit([evidence('35')],'Người sử dụng lao động đơn phương chấm dứt cần điều kiện nào?',['TERMINATION'],{'actor':'EMPLOYER'},'EXPLAIN')
        self.assertEqual(decisions[0].audit_status,'FAIL')

    def test_categories_are_conditions_not_auto_approved_entitlements(self):
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig())
        _,decisions,_=auditor.audit([evidence('113','1','b')],'Tôi làm công việc bình thường được bao nhiêu ngày nghỉ phép năm?',
            ['LEAVE'],{'work_category':'NORMAL','query_intent':'ANNUAL_LEAVE_CALC'},'EXPLAIN')
        self.assertEqual(decisions[0].audit_status,'FAIL')
        self.assertIn('SUBISSUE_LEAVE_CATEGORY_MISMATCH',decisions[0].reasons)

    def test_trace_has_taxonomy_and_slot_constraints_without_new_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); build=fixture(root)
            cfg=OnlineConfig(artifact_source=str(root),expected_build_id=build,trace_dir=str(root/'traces'),
                retrieval=RetrievalConfig(dense_enabled=False),cache_dir=str(root/'cache'))
            pipeline=OnlinePipeline(cfg)
            result=pipeline.ask(QueryRequest(question='Điều 1 của Nghị định 145/2020/ND-CP quy định gì?'))
            event=next(event for event in result.trace.events if event['event']=='analysis')
            self.assertEqual(event['taxonomy_version'],TAXONOMY_VERSION)
            self.assertIn('subissues',event)
            self.assertIn('slot_requirements',next(event for event in result.trace.events if event['event']=='evidence_plan'))


if __name__=='__main__': unittest.main()
