"""Mechanism regressions discovered during live Gold review, with unseen fixtures."""
import unittest
from unittest.mock import Mock,patch
from datetime import date,datetime,timezone

from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.evidence import select_for_plan
from vn_labor_online.models import ApplicabilityDecision, Evidence, EvidencePlan, LegalLocator
from vn_labor_online.answer_review import Review,review_answer,validate_review
from vn_labor_online.answer_quality import render_claims
from vn_labor_online.models import (AdjudicationDraft,AnswerTask,Claim,EvidenceState,
                                    VerifiedEvidenceItem,VerifiedEvidencePack)
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.durations import probation_duration
from vn_labor_online.query_clock import relative_date_ranges,today_vietnam,unpublished_change_prediction
from vn_labor_online.conversation import resolve_context
from vn_labor_online.models import QueryRequest
from vn_labor_online.generation import _annual_leave_answer
from vn_labor_online.audit import _claim_supported


def evidence(uid, article, clause, score):
    return Evidence(unit_id=uid,document_number='fixture-law',article_number=article,
                    clause_number=clause,provision_version_id='version-'+uid,
                    retrieval_method='bm25',kind='PROVISION',verified=True,
                    text='Quy định làm căn cứ kiểm thử '+uid,score=score)


class LiveGoldMechanismRegressions(unittest.TestCase):
    def test_hypothetical_future_amendment_is_not_a_known_prospective_rule(self):
        day=date(2026,10,30)
        self.assertTrue(unpublished_change_prediction('Chính phủ sẽ nâng giới hạn vào năm 2032 bao nhiêu, nếu có thay đổi luật?','2032-01-01',day))
        self.assertFalse(unpublished_change_prediction('Theo nghị định đã ban hành, mức lương sẽ nâng vào năm 2032 thế nào?','2032-01-01',day))
        self.assertFalse(unpublished_change_prediction('Nghỉ hằng năm theo luật áp dụng vào năm 2032 có bao nhiêu ngày?','2032-01-01',day))
    def test_base_annual_leave_does_not_invent_zero_seniority_or_cite_an_absent_rule(self):
        for category,point,days,label in [('NORMAL','a',12,'điều kiện bình thường'),
                                        ('SPECIAL_HEAVY','c',16,'nghề, công việc đặc biệt nặng nhọc, độc hại, nguy hiểm')]:
            with self.subTest(category=category):
                text=f'Người lao động làm việc đủ 12 tháng cho một người sử dụng lao động thì được nghỉ hằng năm, hưởng nguyên lương theo hợp đồng lao động: {days} ngày làm việc đối với người làm công việc trong {label}.'
                item=VerifiedEvidenceItem(evidence_id='fixture',text=text,instrument_number='45/2019/QH14',
                    article='113',clause='1',point=point)
                pack=VerifiedEvidencePack(query='Tôi làm đủ 12 tháng được nghỉ bao nhiêu ngày?',
                    query_date='2026-02-01',facts={'query_intent':'ANNUAL_LEAVE_CALC','worked_months':12,'work_category':category},
                    evidence=[item],coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
                draft=_annual_leave_answer(pack,True,[])
                self.assertIsNotNone(draft)
                self.assertNotIn('0 năm',draft.answer_summary)
                self.assertNotIn('05 năm',draft.answer_summary)
                self.assertTrue(_claim_supported(draft.claims[0].text,evidence('fixture','113','1',1).model_copy(update={'text':text})))

    def test_dependency_only_requirements_do_not_replace_the_governing_rule(self):
        rule=evidence('primary','197','1',.98)
        exception=evidence('exception','197','2',.25)
        plan=EvidencePlan(mandatory_slots=['governing_rule','exceptions'],
                          slot_requirements={'exceptions':[[LegalLocator(documents=['fixture-law'],article='197',clause='2')]]})
        selected,state=select_for_plan([rule,exception],plan,'2026-01-01',False,6)
        self.assertIn('primary',{item.unit_id for item in selected})
        self.assertIn('exception',{item.unit_id for item in selected})
        self.assertFalse(state.gaps)

    def test_complete_substantive_profile_still_avoids_unrelated_padding(self):
        rule=evidence('primary','197','1',.8)
        noise=evidence('irrelevant','198','1',.99)
        plan=EvidencePlan(mandatory_slots=['specific_rule'],slot_requirements={
            'specific_rule':[[LegalLocator(documents=['fixture-law'],article='197',clause='1')]]})
        selected,_=select_for_plan([noise,rule],plan,'2026-01-01',False,6)
        self.assertEqual([item.unit_id for item in selected],['primary'])

    def model_audit(self,outcome):
        item=evidence('primary','197','1',.9)
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid'))
        auditor._deterministic=Mock(return_value=([],[ApplicabilityDecision(
            evidence_id=item.unit_id,relevant=True,supports_claim=False,
            audit_status='UNRESOLVED',reasons=['SEMANTIC_SUPPORT_REQUIRES_AUDIT'])],[]))
        auditor.provider=Mock()
        auditor.provider.context_tokens=None
        auditor.provider.max_output_tokens=500
        auditor.provider.structured.return_value={'decisions':{'primary':{
            'relevant':True,'supports_claim':True,'conditions_status':'SATISFIED',
            'exception_status':'TRIGGERED'}}}
        return auditor.audit([item],'Đánh giá tình huống kiểm thử',[],{},outcome)

    def test_triggered_disqualifying_exception_cannot_support_case_conclusion(self):
        accepted,decisions,_=self.model_audit('ASSESS_LEGALITY')
        self.assertFalse(accepted)
        self.assertEqual(decisions[0].audit_status,'FAIL')

    def test_explanation_can_retain_exception_context_without_adjudicating_facts(self):
        accepted,decisions,_=self.model_audit('EXPLAIN')
        self.assertEqual(len(accepted),1)
        self.assertEqual(decisions[0].exception_status,'TRIGGERED')

    def test_per_item_contract_rejects_pass_with_a_disqualifying_exception(self):
        decision=ApplicabilityDecision(evidence_id='primary',relevant=True,supports_claim=True,
                                      conditions_status='SATISFIED',exception_status='TRIGGERED',audit_status='PASS')
        with self.assertRaises(StructuredOutputError):
            LegalApplicabilityAuditor._validate_decision(decision,'primary','ASSESS_LEGALITY')

    def review_with_irrelevant_claim(self,missing=False):
        source='Điều khoản kiểm thử quy định quyền X khi điều kiện Y được đáp ứng.'
        task=AnswerTask(task_id='right',request_quote='Quyền X?',description='Quyền X',retrieval_query='Quyền X')
        pack=VerifiedEvidencePack(query='Quyền X khi có điều kiện Y?',requested_outcome='EXPLAIN',
            coverage_state=EvidenceState(slots={},gaps=[],coverage=1),answer_tasks=[task],
            evidence=[VerifiedEvidenceItem(evidence_id='fixture',text=source,full_text=source)])
        draft=AdjudicationDraft(answer_summary='',applicable_law_versions=[],claims=[
            Claim(claim_id='necessary',text='Nếu có điều kiện Y thì có quyền X.',evidence_ids=['fixture']),
            Claim(claim_id='extraneous',text='Tiêu đề phần về quyền X.',evidence_ids=['fixture'])])
        verdict={'claims':[
            {'claim_id':'necessary','verdict':'SUPPORTED','grounding':[{'evidence_id':'fixture','quote':source}],'reason':'Đúng quyền và điều kiện.'},
            {'claim_id':'extraneous','verdict':'IRRELEVANT','grounding':[],'reason':'Tiêu đề không bổ sung nội dung trả lời.'}],
            'coverage':[{'task_id':'right','status':'ANSWERED','claim_ids':['necessary'],'missing':''}],
            'question_fully_addressed':not missing,'missing_requirements':['Còn thiếu một yêu cầu độc lập.'] if missing else []}
        provider=Mock();provider.structured.return_value=verdict
        # Only irrelevant claims can be removed without requesting a new draft.
        result,warnings=review_answer(provider,draft,pack,repair_attempts=0)
        return provider,result,warnings

    def test_all_tasks_supported_after_irrelevant_claim_removed_need_no_repair(self):
        provider,result,warnings=self.review_with_irrelevant_claim()
        self.assertEqual([c.claim_id for c in result.claims],['necessary'])
        self.assertEqual(result.semantic_review['status'],'PASS')
        self.assertEqual(result.semantic_review['rejected_claim_ids'],['extraneous'])
        self.assertEqual(provider.structured.call_count,1)
        self.assertNotIn('answer_coverage',result.limitations)
        self.assertNotIn('ANSWER_SEMANTIC_REVIEW_INCOMPLETE',warnings)

    def test_missing_requirements_still_block_completion_after_pruning(self):
        _,result,_=self.review_with_irrelevant_claim(missing=True)
        self.assertEqual(result.semantic_review['status'],'PARTIAL')

    def test_complete_content_with_pending_metadata_has_an_accurate_limit_notice(self):
        _,draft,_=self.review_with_irrelevant_claim()
        draft=draft.model_copy(update={'limitations':['official_source','applicable_version']})
        rendered=render_claims(draft,True)
        self.assertIn('nguồn hoặc hiệu lực',rendered.answer_summary)
        self.assertNotIn('bằng chứng bắt buộc chưa đầy đủ',rendered.answer_summary)

    def test_missing_substantive_rules_are_not_disguised_as_metadata_only(self):
        _,draft,_=self.review_with_irrelevant_claim()
        draft=draft.model_copy(update={'limitations':['official_source','exceptions']})
        rendered=render_claims(draft,True)
        self.assertIn('bằng chứng bắt buộc chưa đầy đủ',rendered.answer_summary)

    def test_unseen_contract_issues_have_dated_source_guides_not_canned_answers(self):
        cases=[
            ('Doanh nghiệp giao kết hợp đồng lao động bằng lời nói trong 35 ngày, có được không?', 'CONTRACT.FORM','14'),
            ('Hợp đồng lao động xác định thời hạn ký 50 tháng có hợp lệ về thời hạn không?', 'CONTRACT.DURATION','20'),
            ('Hợp đồng lao động đã hết hạn, tôi vẫn làm việc và chưa ký mới, hợp đồng trở thành loại nào?', 'CONTRACT.CONTINUATION','20'),
            ('Người lao động được giao kết hợp đồng lao động đồng thời với nhiều công ty không?', 'CONTRACT.MULTIPLE_EMPLOYERS','19'),
            ('Dùng phụ lục của hợp đồng lao động để sửa nội dung có được không?', 'CONTRACT.APPENDIX','22'),
            ('Doanh nghiệp ký cam kết bảo mật bí mật công nghệ với nhân viên có được không?', 'CONTRACT.CONFIDENTIALITY','21'),
        ]
        for question,key,article in cases:
            with self.subTest(key=key):
                analysis=analyze(intake(question,[],'2026-02-01',{}),'2026-02-01',{})
                self.assertIn(key,analysis.legal_subissues)
                plan=plan_evidence(analysis)
                locators=[loc for groups in plan.slot_requirements.values() for group in groups for loc in group]
                self.assertTrue(any(loc.article==article and '45/2019/QH14' in loc.documents for loc in locators))

    def test_oral_contract_needs_its_term_only_for_a_personal_assessment(self):
        unknown='Công ty và tôi chỉ thỏa thuận miệng để làm việc theo hợp đồng lao động, như vậy có đúng không?'
        known='Tôi giao kết hợp đồng lao động bằng lời nói có thời hạn ba tuần, như vậy có đúng không?'
        generic='Hình thức hợp đồng lao động bằng lời nói được quy định như thế nào?'
        results=[analyze(intake(q,[],'2026-02-01',{}),'2026-02-01',{}) for q in (unknown,known,generic)]
        self.assertTrue(any('bao lâu' in q for q in results[0].missing_facts))
        self.assertFalse(any('bao lâu' in q for q in results[1].missing_facts))
        self.assertFalse(any('bao lâu' in q for q in results[2].missing_facts))

    def test_contract_background_does_not_create_a_duration_or_form_task(self):
        cases=[
            ('Tôi ký hợp đồng lao động xác định thời hạn 18 tháng, giờ muốn nghỉ việc và báo trước bao lâu?', 'CONTRACT.DURATION'),
            ('Hợp đồng mua bán thiết bị của công ty bằng lời nói có được không?', 'CONTRACT.FORM'),
            ('Tôi ký hợp đồng làm việc của viên chức bằng lời nói có hợp lệ không?', 'CONTRACT.FORM'),
        ]
        for question,unwanted in cases:
            with self.subTest(question=question):
                analysis=analyze(intake(question,[],'2026-02-01',{}),'2026-02-01',{})
                self.assertNotIn(unwanted,analysis.legal_subissues)

    def test_form_profile_does_not_apply_the_2019_code_to_a_2020_query(self):
        question='Hợp đồng lao động giao kết bằng lời nói có được không?'
        analysis=analyze(intake(question,[],'2020-10-01',{}),'2020-10-01',{})
        locators=[loc for groups in plan_evidence(analysis).slot_requirements.values() for group in groups for loc in group]
        self.assertTrue(any(loc.article=='16' and loc.documents==['10/2012/QH13'] for loc in locators))
        self.assertFalse(any('45/2019/QH14' in loc.documents for loc in locators))

    def test_job_requirement_paraphrases_are_not_confused_with_personal_diplomas(self):
        cases=[
            ('Vị trí chuyên môn yêu cầu trình độ cao đẳng, thử việc 75 ngày có được không?','COLLEGE'),
            ('Vị trí nghề nghiệp này đòi hỏi trình độ trung cấp, thử việc 32 ngày có đúng không?','INTERMEDIATE'),
            ('Tôi làm công việc phổ thông và thử việc 9 ngày làm việc, có đúng không?','OTHER'),
            ('Tôi thuộc diện người quản lý doanh nghiệp, thử việc 190 ngày có đúng không?','MANAGER'),
            ('Tôi có bằng cao đẳng, công ty cho thử việc 75 ngày, có đúng không?',None),
        ]
        for question,group in cases:
            with self.subTest(group=group):
                analysis=analyze(intake(question,[],'2026-02-01',{}),'2026-02-01',{})
                self.assertEqual(analysis.facts.get('probation_work_group'),group)

    def test_written_and_spoken_trial_durations_preserve_units_and_reject_ranges(self):
        for question,expected in [
            ('Tôi bị thử việc mười bảy ngày.',(17,'ngay')),
            ('Công ty yêu cầu thử việc hai trăm mười ngày.',(210,'ngay')),
            ('Tôi thử việc bảy ngày làm việc.',(7,'ngay lam viec')),
            ('Tôi thử việc 3 tháng.',(3,'thang')),
            ('Tôi thử việc từ 10 đến 20 ngày.',None),
            ('Trong thử việc, lương tính theo 20 ngày công.',None),
        ]:
            with self.subTest(question=question):self.assertEqual(probation_duration(question),expected)

    def test_negated_job_category_is_not_mistaken_for_a_requested_comparison(self):
        question='Công việc yêu cầu trình độ trung cấp và không phải quản lý doanh nghiệp, thử việc 33 ngày có đúng không?'
        analysis=analyze(intake(question,[],'2026-02-01',{}),'2026-02-01',{})
        locators=[loc for groups in plan_evidence(analysis).slot_requirements.values() for group in groups for loc in group]
        self.assertEqual({(loc.article,loc.clause) for loc in locators},{('25','3')})

    def test_cancellation_during_trial_does_not_ask_for_ordinary_resignation_facts(self):
        question='Tôi đang trong thời gian thử việc và muốn nghỉ ngay, có phải báo trước hoặc bồi thường về việc nghỉ không?'
        analysis=analyze(intake(question,[],'2026-02-01',{}),'2026-02-01',{})
        self.assertIn('CONTRACT.PROBATION_CANCELLATION',analysis.legal_subissues)
        self.assertFalse(any(key.startswith('TERMINATION.') for key in analysis.legal_subissues))
        self.assertFalse(analysis.missing_facts)
        locators=[loc for groups in plan_evidence(analysis).slot_requirements.values() for group in groups for loc in group]
        self.assertEqual({(loc.article,loc.clause) for loc in locators},{('27','2')})

    def test_post_trial_exit_and_training_repayment_are_not_waived_by_trial_rule(self):
        questions=[
            'Tôi đã kết thúc thử việc, ký hợp đồng không xác định thời hạn và muốn nghỉ ngay, có phải báo trước không?',
            'Tôi đang trong thời gian thử việc và nghỉ ngay, tôi có phải hoàn trả chi phí đào tạo theo hợp đồng đào tạo không?',
        ]
        for question in questions:
            with self.subTest(question=question):
                analysis=analyze(intake(question,[],'2026-02-01',{}),'2026-02-01',{})
                self.assertNotIn('CONTRACT.PROBATION_CANCELLATION',analysis.legal_subissues)

    def test_no_trial_rule_distinguishes_employment_term_from_trial_agreement_term(self):
        employment='Hợp đồng lao động có thời hạn 18 ngày, doanh nghiệp có thể áp dụng thử việc không?'
        trial='Hợp đồng thử việc 18 ngày cho công việc yêu cầu trình độ cao đẳng có đúng không?'
        a=analyze(intake(employment,[],'2026-02-01',{}),'2026-02-01',{})
        b=analyze(intake(trial,[],'2026-02-01',{}),'2026-02-01',{})
        self.assertIn('CONTRACT.PROBATION_EXCLUSION',a.legal_subissues)
        self.assertNotIn('CONTRACT.PROBATION_EXCLUSION',b.legal_subissues)

    def test_supported_claim_cannot_publish_an_additional_unchecked_citation(self):
        first='Quy tắc thứ nhất xác định điều kiện Y cho quyền X.'
        second='Quy tắc thứ hai xác định cách thức Z để thực hiện quyền X.'
        task=AnswerTask(task_id='rule',request_quote='Quyền X?',description='Điều kiện và cách thức',retrieval_query='Quyền X')
        pack=VerifiedEvidencePack(query='Điều kiện và cách thực hiện quyền X?',
            evidence=[VerifiedEvidenceItem(evidence_id='first',text=first,full_text=first),
                      VerifiedEvidenceItem(evidence_id='second',text=second,full_text=second)],
            answer_tasks=[task],coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
        draft=AdjudicationDraft(answer_summary='',applicable_law_versions=[],claims=[
            Claim(claim_id='claim',text='Quyền X cần điều kiện Y và được thực hiện theo cách thức Z.',evidence_ids=['first','second'])])
        raw={'claims':[{'claim_id':'claim','verdict':'SUPPORTED','grounding':[
            {'evidence_id':'first','quote':first}],'reason':'Hai tiền đề cùng cần thiết.'}],
            'coverage':[{'task_id':'rule','status':'ANSWERED','claim_ids':['claim'],'missing':''}],
            'question_fully_addressed':True,'missing_requirements':[]}
        with self.assertRaises(StructuredOutputError):
            validate_review(Review.model_validate(raw),draft,pack,[task])
        raw['claims'][0]['grounding'].append({'evidence_id':'second','quote':second})
        self.assertEqual(validate_review(Review.model_validate(raw),draft,pack,[task]),{'claim'})

    def test_current_day_uses_vietnam_timezone_at_utc_midnight_boundary(self):
        self.assertEqual(today_vietnam(datetime(2026,10,29,18,tzinfo=timezone.utc)),date(2026,10,30))
        self.assertEqual(today_vietnam(datetime(2026,10,29,16,tzinfo=timezone.utc)),date(2026,10,29))

    def test_relative_dates_preserve_calendar_ranges_and_leap_days(self):
        self.assertEqual(relative_date_ranges('Tháng trước tôi làm thêm.',date(2024,3,5)),
                         [('2024-02-01','2024-02-29','MONTH')])
        self.assertEqual(relative_date_ranges('Tuần trước tôi nghỉ.',date(2024,3,5)),
                         [('2024-02-26','2024-03-03','RANGE')])
        with patch('vn_labor_online.query_clock.today_vietnam',return_value=date(2026,10,30)):
            q='Hôm qua công ty cho tôi nghỉ việc, có đúng không?'
            analysis=analyze(intake(q,[]))
            self.assertEqual(analysis.query_date,'2026-10-29')
            q='Tôi ký hợp đồng từ năm 2020, bây giờ muốn nghỉ việc phải báo trước bao lâu?'
            analysis=analyze(intake(q,[]))
            self.assertEqual(analysis.query_date,'2026-10-30')

    def test_invalid_or_unresolved_dates_ask_instead_of_becoming_today(self):
        for question in ('Ngày 31/02/2026 công ty cho tôi nghỉ việc.',
                         'Ngày 32/01/2026 công ty cho tôi nghỉ việc.',
                         'Cách đây vài tháng tôi bị chấm dứt hợp đồng, có đúng không?'):
            with self.subTest(question=question):
                analysis=analyze(intake(question,[]))
                self.assertEqual(analysis.temporal_resolution,'AMBIGUOUS')
                self.assertTrue(any('thời gian' in q for q in analysis.missing_facts))

    def test_dotted_historical_date_does_not_use_the_current_law(self):
        question='Ngày 15.12.2020, người lao động ký hợp đồng lao động bằng lời nói có được không?'
        analysis=analyze(intake(question,[]))
        self.assertEqual(analysis.query_date,'2020-12-15')
        self.assertEqual(analysis.temporal_intent,'HISTORICAL')

    def test_explicit_current_followup_replaces_the_prior_historical_date(self):
        request=QueryRequest(question='Còn hiện nay thời hạn báo trước thì sao?',conversation_turns=[{
            'turn_id':'old','role':'user','content':'Ngày 15/12/2020 tôi làm theo hợp đồng không xác định thời hạn, muốn nghỉ việc thì phải báo trước bao lâu?'}])
        with patch('vn_labor_online.query_clock.today_vietnam',return_value=date(2026,10,30)):
            resolved=resolve_context(request)
        self.assertEqual(resolved.query_date,'2026-10-30')

    def test_contract_start_year_is_not_the_date_of_a_new_resignation(self):
        analysis=analyze(intake('Tôi ký hợp đồng không xác định thời hạn năm 2020 và muốn đơn phương nghỉ vì việc gia đình. Báo trước bao lâu?',[]))
        self.assertEqual(analysis.facts['contract_start_year'],2020)
        self.assertIsNone(analysis.query_date)
        formation=analyze(intake('Tôi giao kết hợp đồng bằng lời nói năm 2020, việc giao kết khi ấy có đúng luật không?',[]))
        self.assertEqual(formation.query_date,'2020-01-01')

    def test_older_requested_dates_are_not_silently_replaced_by_today(self):
        analysis=analyze(intake('Ngày 14/12/1999 quy định nghỉ hằng năm như thế nào?',[]))
        self.assertEqual(analysis.query_date,'1999-12-14')

    def test_vietnamese_causal_do_does_not_make_a_wage_question_english(self):
        for question in ('Do nhà máy mất điện, doanh nghiệp chậm lương 18 ngày. Có phải đền bù không?',
                         'Công ty ép dùng lương mua hàng do chính công ty bán, có đúng không?'):
            with self.subTest(question=question):
                analysis=analyze(intake(question,[]),'2026-02-01',{})
                self.assertTrue(analysis.in_scope)
        for question in ('How do I bake bread?', 'Do you know the weather tomorrow?'):
            self.assertFalse(analyze(intake(question,[])).in_scope)

    def test_dismissal_for_theft_is_labour_but_imprisonment_is_not(self):
        labour=analyze(intake('Công ty có được sa thải tôi vì hành vi trộm cắp tại nơi làm việc không?',[]),'2026-02-01',{})
        self.assertTrue(labour.in_scope)
        criminal=analyze(intake('Tôi bị sa thải rồi, hành vi trộm cắp bị phạt tù bao nhiêu năm?',[]),'2026-02-01',{})
        self.assertFalse(criminal.in_scope)

    def test_complete_overtime_question_is_not_an_ambiguous_contextless_followup(self):
        request=QueryRequest(question='Tôi làm thêm vào ngày nghỉ hằng tuần, lương tối thiểu bằng bao nhiêu phần trăm?')
        self.assertIsNone(resolve_context(request).clarification)
        self.assertIsNotNone(resolve_context(QueryRequest(question='Vậy điều đó thì sao?')).clarification)

    def test_wage_and_working_time_profiles_support_unseen_wording(self):
        cases=[
            ('Hai người cùng công việc có giá trị như nhau bị trả lương khác chỉ vì giới tính, có đúng không?','WAGE.EQUAL_PAY','90'),
            ('Trả lương theo công việc thấp hơn mức tối thiểu áp dụng có được không?','WAGE.MINIMUM_FLOOR','90'),
            ('Người hưởng lương tháng được trả mỗi tháng một lần không?','WAGE.PAYMENT_CYCLE','97'),
            ('Do mất điện doanh nghiệp chậm trả lương 18 ngày, có phải đền bù không?','WAGE.PAYMENT_DELAY','97'),
            ('Trả lương qua tài khoản ngân hàng thì ai chịu phí tài khoản?','WAGE.PAYMENT_METHODS','96'),
            ('Công ty bắt buộc nhân viên dùng tiền lương mua hàng của công ty có được không?','WAGE.PAYMENT_DISPOSAL','94'),
            ('Ngừng việc do lỗi của công ty thì tiền lương trả ra sao?','WAGE.DOWNTIME','99'),
            ('Nhà nước khuyến khích tuần làm việc 35 giờ hay một mức khác?','WORKING_TIME.WEEKLY_POLICY','105'),
            ('Thời gian buổi tối có thuộc giờ làm việc ban đêm không?','WORKING_TIME.NIGHT_DEFINITION','106'),
            ('Làm việc ban đêm 9 giờ thì được nghỉ giữa giờ bao lâu?','WORKING_TIME.REST_BREAK','109'),
            ('Khi chuyển ca làm việc khác, cần nghỉ trước ít nhất bao lâu?','WORKING_TIME.SHIFT_INTERVAL','110'),
            ('Làm thêm giờ thông thường có cần người lao động đồng ý không?','WORKING_TIME.OVERTIME_CONSENT','107'),
            ('Để cứu người trong thiên tai có được yêu cầu làm thêm giờ đặc biệt không?','WORKING_TIME.EMERGENCY_OVERTIME','108'),
        ]
        for question,key,article in cases:
            with self.subTest(key=key):
                analysis=analyze(intake(question,[]),'2026-02-01',{})
                self.assertIn(key,analysis.legal_subissues)
                plan=plan_evidence(analysis)
                self.assertTrue(any(loc.article==article for groups in plan.slot_requirements.values() for group in groups for loc in group))

    def test_disaster_recovery_is_not_automatically_a_life_protection_emergency(self):
        question='Doanh nghiệp khôi phục sản xuất sau thiên tai, có thể làm thêm tối đa 280 giờ trong năm không?'
        analysis=analyze(intake(question,[]),'2026-02-01',{})
        self.assertNotIn('WORKING_TIME.EMERGENCY_OVERTIME',analysis.legal_subissues)
        self.assertIn('WORKING_TIME.OVERTIME_LIMITS',analysis.legal_subissues)

    def test_weekly_rest_profiles_distinguish_rule_schedule_and_holiday_overlap(self):
        cases=[('Mỗi tuần tôi phải được nghỉ bao nhiêu giờ liên tục?','1'),
               ('Chọn ngày nghỉ hằng tuần vào thứ Tư có được không?','2'),
               ('Ngày nghỉ hằng tuần trùng ngày lễ thì nghỉ bù thế nào?','3')]
        for question,clause in cases:
            with self.subTest(question=question):
                plan=plan_evidence(analyze(intake(question,[]),'2026-02-01',{}))
                self.assertTrue(any(locator.article=='111' and locator.clause==clause
                    for group in plan.slot_requirements['weekly_rest'] for locator in group))
        old=plan_evidence(analyze(intake(cases[-1][0],[]),'2020-11-03',{}))
        self.assertTrue(any(loc.article=='115' and loc.clause=='3'
            for group in old.slot_requirements['holiday_weekly_overlap'] for loc in group))

    def test_leave_settlement_does_not_ask_facts_for_unrequested_exit_legality(self):
        question='Chấm dứt hợp đồng rồi mà còn ngày phép năm chưa sử dụng, công ty có phải thanh toán không?'
        analysis=analyze(intake(question,[]),'2026-02-01',{})
        self.assertIn('LEAVE.UNUSED_LEAVE_PAYMENT',analysis.legal_subissues)
        self.assertFalse(any(key.startswith('TERMINATION.') for key in analysis.legal_subissues))
        self.assertFalse(analysis.missing_facts)
        mixed=analyze(intake('Tôi chỉ báo trước 17 ngày rồi đơn phương nghỉ việc, có trái pháp luật không và ngày phép năm chưa sử dụng có được thanh toán không?',[]),'2026-02-01',{})
        self.assertTrue(any(key.startswith('TERMINATION.') for key in mixed.legal_subissues))
        self.assertTrue(mixed.missing_facts)

    def test_seniority_increment_is_not_a_request_to_compute_all_annual_leave(self):
        analysis=analyze(intake('Tôi đã làm cùng doanh nghiệp đủ 15 năm, số ngày nghỉ hằng năm có tăng thêm không?',[]),'2026-02-01',{})
        self.assertIn('LEAVE.SENIORITY_BONUS',analysis.legal_subissues)
        self.assertNotIn('LEAVE.ANNUAL_LEAVE',analysis.legal_subissues)
        self.assertFalse(analysis.missing_facts)

    def test_personal_leave_profiles_keep_only_requested_events_and_retain_overviews(self):
        for question,expected in [('Tôi kết hôn được nghỉ việc riêng mấy ngày?',{'a'}),
                                  ('Con trai tôi kết hôn thì được nghỉ mấy ngày?',{'b'}),
                                  ('Cha tôi qua đời được nghỉ mấy ngày?',{'c'}),
                                  ('Liệt kê các trường hợp nghỉ việc riêng hưởng lương.',{'a','b','c'})]:
            with self.subTest(question=question):
                plan=plan_evidence(analyze(intake(question,[]),'2026-02-01',{}))
                points={loc.point for group in plan.slot_requirements['personal_leave_rule'] for loc in group}
                self.assertEqual(points,expected)

    def test_statutory_unpaid_family_leave_does_not_require_a_separate_agreement(self):
        question='Bà ngoại tôi mất, tôi được nghỉ không hưởng lương theo luật như thế nào?'
        plan=plan_evidence(analyze(intake(question,[]),'2026-02-01',{}))
        clauses={loc.clause for group in plan.slot_requirements['unpaid_leave_rule'] for loc in group}
        self.assertEqual(clauses,{'2'})
        general=plan_evidence(analyze(intake('Các trường hợp nghỉ không hưởng lương và thỏa thuận thêm ngày nghỉ?',[]),'2026-02-01',{}))
        self.assertEqual({loc.clause for group in general.slot_requirements['unpaid_leave_rule'] for loc in group},{'2','3'})

    def test_stated_employee_exit_ground_replaces_unrelated_notice_questions(self):
        questions=[('Công ty không trả lương đúng hạn, không thuộc ngoại lệ bất khả kháng. Tôi có quyền nghỉ không báo trước không?','LATE_WAGE','b'),
                   ('Người lao động bị công ty ngược đãi, có được đơn phương chấm dứt không cần báo trước không?','MISTREATMENT','c'),
                   ('Công ty không bố trí đúng công việc, không thuộc điều 29. Tôi được đơn phương nghỉ không báo trước không?','WRONG_WORK','a')]
        for question,basis,point in questions:
            with self.subTest(basis=basis):
                analysis=analyze(intake(question,[]),'2026-02-01',{})
                self.assertEqual(analysis.facts.get('termination_basis'),basis)
                self.assertFalse(analysis.missing_facts)
                plan=plan_evidence(analysis)
                self.assertTrue(any(loc.article=='35' and loc.clause=='2' and loc.point==point
                    for group in plan.slot_requirements['employee_unilateral_rule'] for loc in group))
        negative=analyze(intake('Tôi không bị công ty đánh đập, muốn nghỉ vì việc gia đình.',[]),'2026-02-01',{})
        self.assertNotEqual(negative.facts.get('termination_basis'),'MISTREATMENT')

    def test_a_question_about_a_notice_exemption_does_not_assert_it_is_established(self):
        analysis=analyze(intake('Tôi có được nghỉ không cần báo trước không?',[]),'2026-02-01',{})
        self.assertIsNone(analysis.facts.get('notice_exception'))

    def test_employer_action_in_a_question_is_not_the_employees_resignation(self):
        for question,clause in [('Người lao động đang mang thai, doanh nghiệp có thể đơn phương chấm dứt hợp đồng vì mang thai không?','3'),
                               ('Người lao động nghỉ hằng năm đã được công ty chấp thuận, công ty có được đơn phương chấm dứt trong thời gian đó không?','2')]:
            with self.subTest(question=question):
                analysis=analyze(intake(question,[]),'2026-02-01',{})
                self.assertEqual(analysis.facts.get('actor'),'EMPLOYER')
                self.assertNotIn('TERMINATION.EMPLOYEE_UNILATERAL',analysis.legal_subissues)
                self.assertFalse(analysis.missing_facts)
                plan=plan_evidence(analysis)
                self.assertTrue(any(loc.article=='37' and loc.clause==clause
                    for group in plan.slot_requirements['employer_protection_rule'] for loc in group))

    def test_stipulated_wrongful_termination_does_not_relitigate_the_premise(self):
        for question,actor,article in [('Người lao động đã đơn phương nghỉ việc trái luật. Hậu quả bồi thường là gì?','EMPLOYEE','40'),
            ('Công ty đơn phương chấm dứt hợp đồng trái pháp luật. Công ty có nghĩa vụ bồi thường gì?','EMPLOYER','41')]:
            with self.subTest(actor=actor):
                analysis=analyze(intake(question,[]),'2026-02-01',{})
                self.assertEqual(analysis.facts.get('query_intent'),'STIPULATED_'+actor+'_LIABILITY')
                self.assertFalse(analysis.missing_facts)
                plan=plan_evidence(analysis)
                self.assertTrue(any(loc.article==article for groups in plan.slot_requirements.values() for group in groups for loc in group))
                self.assertNotIn('notice_requirement',plan.mandatory_slots)
        question='Tôi nghỉ ngay như vậy có trái pháp luật không và hậu quả bồi thường là gì?'
        self.assertNotEqual(analyze(intake(question,[]),'2026-02-01',{}).facts.get('query_intent'),'STIPULATED_EMPLOYEE_LIABILITY')

    def test_settlement_deadline_uses_the_historical_or_current_payment_rule(self):
        for day,article,clause in [('2020-09-21','47','2'),('2026-02-01','48','1')]:
            question='Sau khi chấm dứt hợp đồng, thời hạn thanh toán quyền lợi là bao nhiêu ngày?'
            analysis=analyze(intake(question,[]),day,{})
            self.assertFalse(analysis.missing_facts)
            plan=plan_evidence(analysis)
            self.assertTrue(any(loc.article==article and loc.clause==clause for group in plan.slot_requirements['termination_settlement'] for loc in group))

    def test_personal_duration_requests_keep_clarification_even_when_explanations_are_allowed(self):
        for question,needle in [('Tôi định xin nghỉ việc, phải báo trước bao lâu?','Loại hợp đồng'),
                                ('Tôi sắp được thử việc, tối đa mấy ngày?','Công việc thuộc nhóm')]:
            with self.subTest(question=question):
                analysis=analyze(intake(question,[]),'2026-02-01',{})
                self.assertTrue(any(needle in prompt for prompt in analysis.missing_facts))

    def test_specific_wage_and_overtime_verdicts_require_the_missing_comparison_basis(self):
        for question,needle in [('Tôi tăng ca thứ Bảy, công ty phải trả 200% không?','Ngày đó'),
            ('Lương thử việc của tôi là 7,2 triệu đồng mỗi tháng, có đúng luật không?','chính công việc'),
            ('Tôi nhận 4,7 triệu đồng mỗi tháng, có thấp hơn lương tối thiểu không?','trước khấu trừ'),
            ('Tôi bị yêu cầu làm thêm, chưa biết tổng số giờ, có vi phạm giới hạn làm thêm không?','Số giờ')]:
            with self.subTest(question=question):
                analysis=analyze(intake(question,[]),'2026-02-01',{})
                self.assertTrue(any(needle in prompt for prompt in analysis.missing_facts),analysis.missing_facts)
        known=analyze(intake('Tôi tăng ca thứ Bảy là ngày nghỉ hằng tuần của mình, lương ít nhất bao nhiêu phần trăm?',[]),'2026-02-01',{})
        self.assertFalse(any('Ngày đó' in prompt for prompt in known.missing_facts))

    def test_transfer_duration_alone_is_not_a_complete_legality_assessment(self):
        analysis=analyze(intake('Công ty điều chuyển tôi sang công việc khác 37 ngày, có hợp pháp không?',[]),'2026-02-01',{})
        self.assertTrue(any('Lý do tạm chuyển' in prompt for prompt in analysis.missing_facts))
        self.assertTrue(any('cộng dồn' in prompt for prompt in analysis.missing_facts))
        notice=analyze(intake('Công ty điều chuyển tôi vì nhu cầu sản xuất và báo trước 3 ngày làm việc, có hợp pháp không?',[]),'2026-02-01',{})
        self.assertNotIn('TERMINATION',notice.legal_issues)


if __name__=='__main__':unittest.main()
