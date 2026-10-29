from __future__ import annotations

import unittest

from vn_labor_online.analysis import analyze, intake, plan_evidence
from vn_labor_online.answer_quality import clean_draft, render_claims
from vn_labor_online.answer_review import Review, repair_required_computations, review_answer, validate_review
from vn_labor_online.config import AdjudicationConfig
from vn_labor_online.conversation import resolve_context
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.generation import LegalAdjudicator, probation_pay_application
from vn_labor_online.models import (
    AdjudicationDraft,
    AnswerTask,
    Claim,
    EvidenceState,
    QueryRequest,
    VerifiedEvidenceItem,
    VerifiedEvidencePack,
)
from vn_labor_online.profile_generation import render_profile


def _conversation(question: str, prior: str) -> QueryRequest:
    return QueryRequest(
        question=question,
        conversation_turns=[{'turn_id': 'turn-1', 'role': 'user', 'content': prior}],
    )


def _probation_pack(question: str, text: str = 'Tiền lương thử việc ít nhất bằng 85% mức lương của công việc.') -> VerifiedEvidencePack:
    item = VerifiedEvidenceItem(
        evidence_id='probation-pay',
        instrument_number='18/VBHN-VPQH',
        article='26',
        clause='',
        text=text,
        full_text=text,
    )
    return VerifiedEvidencePack(
        query=question,
        query_date='2026-09-01',
        requested_outcome='EXPLAIN',
        coverage_state=EvidenceState(slots={}, gaps=[], coverage=1),
        evidence=[item],
    )


class TerminationFactGateTests(unittest.TestCase):
    def test_employee_compensation_question_requires_decisive_facts(self):
        questions = (
            'Tôi tự ý nghỉ việc, công ty yêu cầu bồi thường. Tôi có phải bồi thường không?',
            'Tôi nghỉ việc theo ý mình, công ty đòi bồi thường. Tôi có phải bồi thường không?',
            'Tôi chủ động xin nghỉ, công ty không đồng ý và đòi tiền bồi thường. Chỉ với thông tin đó thì tôi có phải trả không?',
            'Tôi nghỉ việc ngay và công ty yêu cầu bồi thường. Tôi có phải trả tiền không?',
        )
        for question in questions:
            with self.subTest(question=question):
                result = analyze(intake(question, []), '2026-09-01')

                self.assertEqual(result.requested_outcome, 'ASSESS_LEGALITY')
                self.assertEqual(result.facts.get('actor'), 'EMPLOYEE')
                self.assertIn('TERMINATION.EMPLOYEE_LIABILITY', result.legal_subissues)
                self.assertTrue(any('Loại hợp đồng' in item for item in result.missing_facts))
                self.assertTrue(any('báo trước' in item for item in result.missing_facts))
                self.assertTrue(any('không cần báo trước' in item for item in result.missing_facts))

    def test_followup_with_notice_and_training_keeps_both_obligations(self):
        question = (
            'Bổ sung cho cùng vụ việc: hợp đồng của tôi không xác định thời hạn, tôi chỉ báo trước 12 ngày '
            'và không thuộc trường hợp được miễn báo trước. Công ty còn yêu cầu hoàn trả chi phí đào tạo '
            'nhưng tôi chưa biết thỏa thuận đào tạo ghi gì. Nghĩa vụ nào có thể kết luận và cần làm rõ gì?'
        )
        result = analyze(intake(question, []), '2026-09-01')

        self.assertIn('TERMINATION.EMPLOYEE_UNILATERAL', result.legal_subissues)
        self.assertIn('TERMINATION.ILLEGAL_TERMINATION', result.legal_subissues)
        self.assertIn('TERMINATION.EMPLOYEE_LIABILITY', result.legal_subissues)
        self.assertIn('TRAINING.COST_REPAYMENT', result.legal_subissues)
        self.assertGreaterEqual(len(result.answer_tasks), 2)

    def test_employer_termination_does_not_assign_employee_liability(self):
        question = 'Công ty muốn đơn phương chấm dứt hợp đồng của người lao động. Cần kiểm tra điều kiện và thủ tục nào?'
        result = analyze(intake(question, []), '2026-09-01')

        self.assertEqual(result.facts.get('actor'), 'EMPLOYER')
        self.assertIn('TERMINATION.EMPLOYER_UNILATERAL', result.legal_subissues)
        self.assertNotIn('TERMINATION.EMPLOYEE_LIABILITY', result.legal_subissues)
        self.assertNotIn('TERMINATION.EMPLOYER_LIABILITY', result.legal_subissues)

    def test_late_wage_paraphrase_plans_only_the_applicable_exception_chain(self):
        question = (
            'Người lao động nghỉ không báo trước vì bị chậm trả lương thì điều kiện nào '
            'và ngoại lệ nào phải kiểm tra trước khi kết luận?'
        )
        result = analyze(intake(question, []), '2026-09-01')

        self.assertEqual(result.facts.get('termination_basis'), 'LATE_WAGE')
        self.assertEqual(result.facts.get('actor'), 'EMPLOYEE')
        self.assertIsNone(result.facts.get('notice_exception'))
        plan = plan_evidence(result)
        locators = [
            locator
            for group in plan.slot_requirements['employee_unilateral_rule']
            for locator in group
        ]
        self.assertEqual(
            {(item.article, item.clause, item.point) for item in locators},
            {('35', '2', 'b')},
        )
        wage_locators = [
            locator
            for group in plan.slot_requirements['wage_delay_reference']
            for locator in group
        ]
        self.assertEqual(
            {(item.article, item.clause) for item in wage_locators},
            {('97', '4')},
        )
        self.assertNotIn('notice_requirement', plan.slot_requirements)

    def test_negated_late_wage_does_not_become_a_termination_fact(self):
        result = analyze(
            intake('Tôi không bị chậm trả lương nhưng đang cân nhắc nghỉ việc.', []),
            '2026-09-01',
        )

        self.assertNotEqual(result.facts.get('termination_basis'), 'LATE_WAGE')

    def test_employer_led_termination_paraphrase_keeps_employer_as_actor(self):
        questions = (
            'Công ty chủ động chấm dứt hợp đồng của tôi rồi yêu cầu tôi bồi thường. Có thể kết luận trách nhiệm của tôi chỉ từ việc công ty yêu cầu không?',
            'Công ty cho tôi nghỉ rồi đòi bồi thường. Chỉ dựa vào yêu cầu đó có thể kết luận trách nhiệm của tôi không?',
            'Công ty cho tôi nghỉ sau khi báo trước 30 ngày rồi yêu cầu bồi thường. Chỉ từ yêu cầu đó có thể kết luận trách nhiệm của tôi không?',
        )
        for question in questions:
            with self.subTest(question=question):
                result = analyze(intake(question, []), '2026-09-01')

                self.assertEqual(result.facts.get('actor'), 'EMPLOYER')
                self.assertTrue(any(fact.field == 'actor' and fact.value == 'EMPLOYER' for fact in result.fact_candidates))
                self.assertIn('TERMINATION.EMPLOYER_UNILATERAL', result.legal_subissues)
                self.assertIn('TERMINATION.EMPLOYEE_LIABILITY', result.legal_subissues)
                self.assertNotIn('TERMINATION.EMPLOYER_LIABILITY', result.legal_subissues)
                self.assertTrue(any(
                    'TERMINATION.EMPLOYEE_LIABILITY' in task.legal_subissues
                    for task in result.answer_tasks
                ))
                self.assertTrue(any(
                    'dựa trên hành vi hoặc nghĩa vụ cụ thể' in item
                    for item in result.missing_facts
                ))

    def test_explicit_employer_compensation_question_keeps_employer_liability(self):
        question = 'Công ty đơn phương chấm dứt hợp đồng trái pháp luật thì công ty phải bồi thường những gì?'
        result = analyze(intake(question, []), '2026-09-01')

        self.assertEqual(result.facts.get('actor'), 'EMPLOYER')
        self.assertIn('TERMINATION.EMPLOYER_LIABILITY', result.legal_subissues)
        self.assertNotIn('TERMINATION.EMPLOYEE_LIABILITY', result.legal_subissues)

    def test_employer_intention_to_terminate_routes_to_employer_rules(self):
        question = 'Công ty muốn đơn phương chấm dứt hợp đồng của người lao động vì thường xuyên không hoàn thành công việc. Cần kiểm tra điều kiện và thủ tục nào?'
        result = analyze(intake(question, []), '2026-09-01')

        self.assertEqual(result.facts.get('actor'), 'EMPLOYER')
        self.assertTrue(any(fact.field == 'actor' and fact.value == 'EMPLOYER' for fact in result.fact_candidates))
        self.assertIn('TERMINATION.EMPLOYER_UNILATERAL', result.legal_subissues)
        self.assertNotIn('TERMINATION.EMPLOYEE_UNILATERAL', result.legal_subissues)
        self.assertNotIn('TERMINATION.EMPLOYEE_LIABILITY', result.legal_subissues)
        self.assertTrue(plan_evidence(result).slot_requirements)

    def test_explicit_twelve_month_contract_supplies_term_and_does_not_ask_type_again(self):
        question = 'Tình huống mới ở công ty B: tôi đã ký hợp đồng 12 tháng và muốn nghỉ ngay, không báo trước. Tôi có phải bồi thường không?'
        analysis = analyze(intake(question, []), '2026-09-01')

        self.assertEqual(analysis.facts.get('contract_type'), 'FIXED_TERM')
        self.assertEqual(analysis.facts.get('contract_duration_months'), 12)
        self.assertFalse(any('Loại hợp đồng' in missing for missing in analysis.missing_facts))
        plan = plan_evidence(analysis)
        locators = [
            locator
            for group in plan.slot_requirements['employee_unilateral_rule']
            for locator in group
        ]
        self.assertEqual({locator.point for locator in locators}, {'b'})

    def test_generic_no_notice_question_plans_exception_children_not_normal_notice_periods(self):
        questions = (
            'Khi nào người lao động có thể đơn phương chấm dứt hợp đồng mà không cần báo trước? Hãy nêu điều kiện từng trường hợp.',
            'Tôi có hợp đồng không xác định thời hạn. Khi nào tôi có thể nghỉ mà không cần phải báo trước?',
        )
        for question in questions:
            with self.subTest(question=question):
                plan = plan_evidence(analyze(intake(question, []), '2026-09-01'))

                self.assertNotIn('notice_requirement', plan.slot_requirements)
                locators = [
                    locator
                    for slot in ('employee_unilateral_rule', 'general_notice_exceptions')
                    for group in plan.slot_requirements[slot]
                    for locator in group
                ]
                self.assertTrue(locators)
                self.assertTrue(all(locator.article == '35' and locator.clause == '2' for locator in locators))
                self.assertTrue(all(locator.point is None and not locator.exact_level for locator in locators))

    def test_known_notice_and_exception_facts_are_not_requested_again(self):
        question = (
            'Tôi làm hợp đồng không xác định thời hạn, nghỉ ngay và không thuộc trường hợp '
            'được nghỉ không cần báo trước. Có phải bồi thường không?'
        )
        result = analyze(intake(question, []), '2026-09-01')

        self.assertEqual(result.facts.get('notice_days'), 0)
        self.assertIs(result.facts.get('notice_exception'), False)
        self.assertFalse(any('báo trước bao nhiêu ngày' in item for item in result.missing_facts))
        self.assertTrue(any('ngành' in item for item in result.missing_facts))
        plan = plan_evidence(result)
        self.assertIn('notice_requirement', plan.slot_requirements)
        self.assertIn('legal_consequences', plan.mandatory_slots)

    def test_stipulated_hypothetical_is_not_treated_as_an_unverified_finding(self):
        question = 'Nếu người lao động đã đơn phương chấm dứt trái pháp luật thì hậu quả bồi thường là gì?'
        result = analyze(intake(question, []), '2026-09-01')

        self.assertEqual(result.facts.get('query_intent'), 'STIPULATED_EMPLOYEE_LIABILITY')
        self.assertFalse(result.missing_facts)


class ProbationAmountTests(unittest.TestCase):
    def test_exact_amount_is_calculated_with_the_source_rule_unit(self):
        cases = (
            ('Mức lương của vị trí là 8 triệu đồng/tháng. Lương thử việc tối thiểu bao nhiêu?',
             '6.800.000 đồng/tháng'),
            ('Mức lương công việc: 12.000.000 đồng/tháng. Mức thử việc thấp nhất là bao nhiêu?',
             '10.200.000 đồng/tháng'),
            ('Mức lương của công việc là 1.000.000 đồng/ngày. Mức thử việc tối thiểu là bao nhiêu?',
             '850.000 đồng/ngày'),
            ('Mức lương của vị trí là 8,000,000 đồng/tháng. Tiền lương thử việc thấp nhất là bao nhiêu?',
             '6.800.000 đồng/tháng'),
            ('Mức lương của công việc là 11,2 triệu đồng/tháng. Tiền lương thử việc tối thiểu là bao nhiêu đồng mỗi tháng?',
             '9.520.000 đồng/tháng'),
            ('Lương công việc là 15,75 triệu đồng mỗi tháng. Tiền lương thử việc tối thiểu là bao nhiêu đồng/tháng?',
             '13.387.500 đồng/tháng'),
            ('Lương của vị trí là 40.000 đồng/giờ. Tiền lương thử việc thấp nhất là bao nhiêu đồng một giờ?',
             '34.000 đồng/giờ'),
        )
        for question, expected in cases:
            with self.subTest(question=question):
                self.assertIn(expected, probation_pay_application(question))

    def test_current_probation_pay_is_not_mistaken_for_the_salary_base(self):
        question = 'Công ty đang trả lương thử việc 8 triệu đồng/tháng. Có thấp hơn luật không?'
        self.assertEqual(probation_pay_application(question), '')

    def test_deterministic_profile_puts_calculated_amount_in_a_cited_claim(self):
        question = 'Mức lương của vị trí là 8 triệu đồng/tháng. Lương thử việc tối thiểu bao nhiêu?'
        engine = LegalAdjudicator(AdjudicationConfig(mode='deterministic', semantic_review=False))

        draft, warnings = engine.generate(_probation_pack(question), partial=False)

        self.assertFalse(warnings)
        self.assertIn('6.800.000 đồng/tháng', draft.answer_summary)
        self.assertEqual(draft.claims[0].evidence_ids, ['probation-pay'])

    def test_valid_answered_verdict_cannot_supply_a_missing_public_amount_from_its_reason(self):
        question = 'Mức lương của vị trí là 8 triệu đồng/tháng. Lương thử việc thấp nhất là bao nhiêu?'
        pack = _probation_pack(question)
        task = AnswerTask(
            task_id='amount',
            request_quote=question,
            description='Mức lương thử việc tối thiểu bằng tiền',
            retrieval_query='tiền lương thử việc',
        )
        pack.answer_tasks = [task]
        claim = Claim(
            claim_id='claim-pay',
            text='Tiền lương thử việc do hai bên thỏa thuận nhưng ít nhất bằng 85% mức lương của công việc.',
            evidence_ids=['probation-pay'],
        )
        draft = AdjudicationDraft(
            answer_summary=claim.text,
            claims=[claim],
            applicable_law_versions=[],
        )
        review = Review.model_validate({
            'claims': [{
                'claim_id': 'claim-pay',
                'verdict': 'SUPPORTED',
                'grounding': [{
                    'evidence_id': 'probation-pay',
                    'quote': pack.evidence[0].text,
                }],
                'reason': 'Mức tính ra là 6.800.000 đồng/tháng theo tỷ lệ 85%.',
            }],
            'coverage': [{
                'task_id': 'amount',
                'status': 'ANSWERED',
                'claim_ids': ['claim-pay'],
                'missing': '',
            }],
            'question_fully_addressed': True,
            'missing_requirements': [],
        })

        with self.assertRaises(StructuredOutputError):
            validate_review(review, draft, pack, [task])
        repaired = repair_required_computations(draft, pack, [task])
        self.assertIn('6.800.000 đồng/tháng', repaired.answer_summary)
        self.assertIn('6.800.000 đồng/tháng', repaired.claims[0].text)
        self.assertEqual(validate_review(review, repaired, pack, [task]), {'claim-pay'})
        class FixedReviewer:
            def structured(self, *_):
                return review.model_dump()
        reviewed, warnings = review_answer(FixedReviewer(), draft, pack)
        public = clean_draft(render_claims(reviewed, partial=False), question)
        self.assertFalse(warnings)
        self.assertEqual(reviewed.semantic_review['status'], 'PASS')
        self.assertIn('6.800.000 đồng/tháng', public.answer_summary)
        self.assertIn('6.800.000 đồng/tháng', public.claims[0].text)

    def test_rule_or_percentage_question_does_not_get_an_unrequested_amount(self):
        question = 'Mức lương của vị trí là 8 triệu đồng/tháng. Tỷ lệ lương thử việc tối thiểu là bao nhiêu phần trăm?'
        pack = _probation_pack(question)
        task = AnswerTask(
            task_id='rate',
            request_quote=question,
            description='Tỷ lệ lương thử việc tối thiểu',
            retrieval_query='tiền lương thử việc',
        )
        claim = Claim(
            claim_id='claim-rate',
            text='Tiền lương thử việc ít nhất bằng 85% mức lương của công việc.',
            evidence_ids=['probation-pay'],
        )
        draft = AdjudicationDraft(answer_summary=claim.text, claims=[claim], applicable_law_versions=[])

        self.assertEqual(probation_pay_application(question), '')
        result = repair_required_computations(draft, pack, [task])
        self.assertNotIn('6.800.000 đồng/tháng', result.answer_summary)
        self.assertEqual(len(result.claims), 1)


class ScopeAndOutputTests(unittest.TestCase):
    def test_college_job_requirement_scopes_probation_duration_to_60_day_rule(self):
        question = (
            'Với công việc đòi hỏi trình độ cao đẳng, thời gian thử việc tối đa là bao lâu '
            'và mức lương thử việc tối thiểu bằng bao nhiêu phần trăm mức lương công việc?'
        )
        analysis = analyze(intake(question, []), '2026-09-01')

        self.assertEqual(analysis.facts.get('probation_work_group'), 'COLLEGE')
        duration_groups = plan_evidence(analysis).slot_requirements['probation_duration']
        self.assertEqual(
            {locator.clause for group in duration_groups for locator in group},
            {'2'},
        )

    def test_incidental_probation_duration_is_not_a_separate_task(self):
        result = analyze(intake(
            'Công ty trả 70% lương công việc trong thời gian thử việc. Có đúng quy định không?',
            [],
        ))

        self.assertIn('CONTRACT.PROBATION_PAY', result.legal_subissues)
        self.assertNotIn('CONTRACT.PROBATION_DURATION', result.legal_subissues)

    def test_probation_minimum_amount_is_not_a_second_statutory_wage_task(self):
        question = 'Lương công việc là 15,75 triệu đồng mỗi tháng. Tiền lương tối thiểu trong thời gian thử việc là bao nhiêu đồng/tháng?'
        result = analyze(intake(question, []), '2026-09-01')

        self.assertIn('CONTRACT.PROBATION_PAY', result.legal_subissues)
        self.assertEqual(len(result.answer_tasks), 1)

    def test_explicit_regional_minimum_wage_remains_a_separate_task(self):
        question = 'Lương thử việc tối thiểu là bao nhiêu và lương tối thiểu vùng I là bao nhiêu?'
        result = analyze(intake(question, []), '2026-09-01')

        self.assertGreaterEqual(len(result.answer_tasks), 2)

    def test_normal_working_hours_uses_only_the_requested_dated_rule(self):
        question = (
            'Theo thời giờ làm việc bình thường tính theo ngày, luật giới hạn tối đa mấy giờ '
            'một ngày và một tuần?'
        )
        analysis = analyze(intake(question, []), '2026-09-01')
        plan = plan_evidence(analysis)

        self.assertIn('WORKING_TIME.NORMAL_HOURS', analysis.legal_subissues)
        self.assertEqual(
            [(loc.article, loc.clause) for group in plan.slot_requirements['normal_working_hours'] for loc in group],
            [('105', '1')],
        )
        source = 'Thời giờ làm việc bình thường không quá 08 giờ trong 01 ngày và không quá 48 giờ trong 01 tuần.'
        pack = VerifiedEvidencePack(
            query=question,
            query_date='2026-09-01',
            coverage_state=EvidenceState(slots={}, gaps=[], coverage=1),
            evidence=[VerifiedEvidenceItem(
                evidence_id='normal-hours',
                instrument_number='18/VBHN-VPQH',
                article='105',
                clause='1',
                text=source,
                full_text=source,
            )],
            resolved_rule_requirements=plan.slot_requirements,
        )

        draft = render_profile(pack, partial=False, assumptions=[])

        self.assertIsNotNone(draft)
        self.assertEqual(len(draft.claims), 1)
        self.assertIn('08 giờ', draft.answer_summary)
        self.assertIn('48 giờ', draft.answer_summary)
        self.assertNotIn('làm thêm', draft.answer_summary.lower())

    def test_normal_hours_question_does_not_create_an_unrequested_break_task(self):
        question = 'Theo chế độ thời giờ làm việc bình thường tính theo ngày, luật giới hạn tối đa mấy giờ một ngày và một tuần?'
        result = analyze(intake(question, []), '2026-09-01')

        self.assertIn('WORKING_TIME.NORMAL_HOURS', result.legal_subissues)
        self.assertEqual(len(result.answer_tasks), 1)

    def test_explicit_break_question_keeps_a_separate_requested_topic(self):
        question = 'Theo thời giờ làm việc bình thường, tối đa mấy giờ một ngày và người lao động được nghỉ giữa giờ bao lâu?'
        result = analyze(intake(question, []), '2026-09-01')

        self.assertGreaterEqual(len(result.answer_tasks), 2)

    def test_near_duplicate_notice_claims_merge_without_erasing_legal_conditions(self):
        claims = [
            Claim(
                claim_id='claim-1',
                text='Người lao động làm theo hợp đồng không xác định thời hạn có quyền đơn phương chấm dứt nhưng phải báo trước ít nhất 45 ngày.',
                evidence_ids=['notice-rule'],
            ),
            Claim(
                claim_id='claim-2',
                text='Theo điểm a khoản 1 Điều 35, người lao động phải báo trước tối thiểu 45 ngày khi chấm dứt hợp đồng không xác định thời hạn.',
                evidence_ids=['notice-rule'],
            ),
            Claim(
                claim_id='claim-employer',
                text='Người sử dụng lao động phải báo trước ít nhất 45 ngày khi đơn phương chấm dứt hợp đồng không xác định thời hạn.',
                evidence_ids=['notice-rule'],
            ),
            Claim(
                claim_id='claim-fixed',
                text='Người lao động làm hợp đồng xác định thời hạn phải báo trước ít nhất 45 ngày.',
                evidence_ids=['notice-rule'],
            ),
        ]
        draft = AdjudicationDraft(
            answer_summary='\n'.join(claim.text for claim in claims),
            claims=claims,
            applicable_law_versions=[],
        )

        cleaned = clean_draft(draft, 'Cần báo trước bao lâu?')

        self.assertEqual(len(cleaned.claims), 3)
        self.assertTrue(any('không xác định thời hạn' in claim.text for claim in cleaned.claims))
        self.assertTrue(any('Người sử dụng lao động' in claim.text for claim in cleaned.claims))
        self.assertTrue(any('xác định thời hạn phải báo' in claim.text for claim in cleaned.claims))

    def test_four_paraphrases_of_the_same_notice_period_collapse_to_one_claim(self):
        claims = [
            Claim(claim_id=f'claim-{index}', text=text, evidence_ids=['notice-rule'])
            for index,text in enumerate((
                'Người lao động làm theo hợp đồng không xác định thời hạn có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước ít nhất 45 ngày.',
                'Theo Điều 35, khoản 1, điểm a của Bộ luật Lao động, người lao động phải báo trước ít nhất 45 ngày khi đơn phương chấm dứt hợp đồng không xác định thời hạn.',
                'Người lao động cần báo trước ít nhất 45 ngày trước khi đơn phương nghỉ việc theo hợp đồng không xác định thời hạn.',
                'Theo quy định tại Điều 35, khoản 1, điểm a của Văn bản hợp nhất Bộ luật Lao động, người lao động làm theo hợp đồng không xác định thời hạn phải báo trước ít nhất 45 ngày khi đơn phương chấm dứt hợp đồng lao động.',
            ),1)
        ]
        draft=AdjudicationDraft(
            answer_summary='\\n'.join(claim.text for claim in claims),
            claims=claims,
            applicable_law_versions=[],
        )

        cleaned=clean_draft(draft,'Tôi làm theo hợp đồng không xác định thời hạn, cần báo trước bao lâu?')

        self.assertEqual(len(cleaned.claims),1)
        self.assertIn('45 ngày',cleaned.claims[0].text)
        self.assertEqual(cleaned.claims[0].evidence_ids,['notice-rule'])


class ConversationConflictTests(unittest.TestCase):
    def test_same_case_material_contract_conflict_requires_confirmation(self):
        result = resolve_context(_conversation(
            'Còn hợp đồng của tôi là xác định thời hạn, tôi báo trước 30 ngày.',
            'Tôi ký hợp đồng không xác định thời hạn và muốn nghỉ việc, báo trước 20 ngày.',
        ))

        self.assertTrue(result.clarification)
        self.assertNotIn('contract_type', result.facts)
        self.assertNotIn('notice_days', result.facts)

    def test_same_case_contract_conflict_is_found_without_a_followup_prefix(self):
        result = resolve_context(_conversation(
            'Tôi muốn nghỉ việc. Hợp đồng của tôi là loại xác định thời hạn 12 tháng và tôi đã báo trước 30 ngày; công ty có thể yêu cầu gì?',
            'Hợp đồng của tôi là loại không xác định thời hạn.',
        ))

        self.assertTrue(result.clarification)
        self.assertNotIn('contract_type', result.facts)

    def test_explicit_correction_replaces_fact_and_records_provenance(self):
        result = resolve_context(_conversation(
            'Đính chính: hợp đồng của tôi là xác định thời hạn, tôi báo trước 30 ngày.',
            'Tôi ký hợp đồng không xác định thời hạn và muốn nghỉ việc, báo trước 20 ngày.',
        ))

        self.assertEqual(result.facts.get('contract_type'), 'FIXED_TERM')
        self.assertEqual(result.facts.get('notice_days'), 30)
        self.assertTrue(any(item.get('status') == 'SUPERSEDED' for item in result.provenance))
        self.assertTrue(any(item.get('turn_id') == 'current_request' for item in result.provenance))

    def test_explicit_correction_prefix_updates_a_fact_across_related_topics(self):
        result = resolve_context(_conversation(
            'Tôi xin đính chính cho cùng vụ việc: hợp đồng thực tế là loại xác định thời hạn 12 tháng. Nếu tôi đã báo trước 30 ngày thì còn phải kiểm tra điều kiện nào?',
            'Tôi đang làm theo hợp đồng lao động không xác định thời hạn.',
        ))

        self.assertEqual(result.facts.get('contract_type'), 'FIXED_TERM')
        self.assertTrue(any(item.get('status') == 'SUPERSEDED' for item in result.provenance))
        self.assertTrue(any(item.get('supersedes') == ['turn-1'] for item in result.provenance))
        self.assertIn('chấm dứt hợp đồng lao động', result.query)

    def test_additional_facts_resume_the_same_case_tasks(self):
        result = resolve_context(_conversation(
            'Bổ sung cho cùng vụ việc: hợp đồng của tôi không xác định thời hạn, tôi chỉ báo trước 12 ngày và không thuộc trường hợp được miễn báo trước. Chi phí đào tạo chưa rõ.',
            'Tôi muốn nghỉ việc và công ty yêu cầu bồi thường. Tôi có phải trả tiền không?',
        ))

        resumed=analyze(intake(result.query, [], result.query_date, result.facts), result.query_date, result.facts)
        self.assertIn('TERMINATION.EMPLOYEE_LIABILITY', resumed.legal_subissues)
        self.assertIn('TRAINING.COST_REPAYMENT', resumed.legal_subissues)
        self.assertGreaterEqual(len(resumed.answer_tasks), 2)
        self.assertEqual(result.facts.get('contract_type'), 'INDEFINITE')
        self.assertEqual(result.facts.get('notice_days'), 12)
        self.assertIs(result.facts.get('notice_exception'), False)
        self.assertTrue(result.used_turns)

    def test_time_effective_salary_change_is_not_a_same_case_conflict(self):
        result = resolve_context(_conversation(
            'Còn từ tháng 8/2026, mức lương công việc là 10 triệu đồng/tháng.',
            'Tôi đang thử việc; mức lương của công việc là 8 triệu đồng/tháng.',
        ))

        self.assertIsNone(result.clarification)
        self.assertEqual(result.facts.get('salary_base_amount'), 10_000_000)
        self.assertEqual(result.facts.get('salary_base_unit'), 'tháng')
        self.assertTrue(result.used_turns)
        self.assertTrue(any(item.get('status') == 'SUPERSEDED_BY_TIME' for item in result.provenance))


if __name__ == '__main__':
    unittest.main()
