"""New wording checks for actor, calendar role and user-reported job facts."""
import unittest
from vn_labor_online.analysis import analyze, intake,plan_evidence
from vn_labor_online.conversation import resolve_context
from vn_labor_online.models import QueryRequest


class RequestGroundingBoundaryTests(unittest.TestCase):
    def test_absent_employer_event_does_not_override_a_resignation(self):
        for absent in ('Công ty không chấm dứt hợp đồng.', 'Công ty chưa sa thải tôi.',
                       'Doanh nghiệp chưa từng cho tôi nghỉ việc.'):
            with self.subTest(absent=absent):
                a=analyze(intake(absent+' Tôi muốn xin nghỉ việc vì lý do cá nhân, phải báo trước bao lâu?',[]))
                self.assertEqual(a.facts.get('actor'),'EMPLOYEE')
                self.assertIn('TERMINATION.EMPLOYEE_UNILATERAL',a.legal_subissues)
                self.assertNotIn('TERMINATION.DISMISSAL',a.legal_subissues)

    def test_legal_prohibition_is_still_an_employer_action_topic(self):
        from vn_labor_online.termination_context import explicit_employer_action
        self.assertTrue(explicit_employer_action('Công ty không được chấm dứt hợp đồng trong những trường hợp nào?'))
        a=analyze(intake('Công ty không được sa thải lao động đang mang thai đúng không?',[]))
        self.assertIn('TERMINATION.DISMISSAL',a.legal_subissues)

    def test_employer_notice_keeps_the_acting_party(self):
        for subject in ('Công ty', 'Doanh nghiệp', 'Người sử dụng lao động'):
            for action in ('báo trước cho tôi 17 ngày rồi cho tôi nghỉ việc',
                           'thông báo trước 22 ngày rồi chấm dứt hợp đồng với tôi'):
                with self.subTest(subject=subject, action=action):
                    result = analyze(intake(f'Tôi ký hợp đồng không xác định thời hạn. {subject} {action}. Có đúng không?', []))
                    self.assertEqual(result.facts.get('actor'), 'EMPLOYER')
                    self.assertIn('TERMINATION.EMPLOYER_UNILATERAL', result.legal_subissues)

    def test_employer_notice_is_not_employee_notice_provenance(self):
        result = analyze(intake('Công ty báo trước cho tôi 17 ngày rồi cho tôi nghỉ việc. Tôi có được bồi thường không?', []))
        candidate = next(c for c in result.fact_candidates if c.field == 'actor')
        self.assertEqual(candidate.value, 'EMPLOYER')
        self.assertIn('Công ty', candidate.source_quote)

    def test_start_of_employment_does_not_date_a_current_resignation(self):
        for beginning in ('Tôi bắt đầu làm việc từ ngày 12/04/2018.',
                          'Tôi làm việc từ ngày 2018-04-12.'):
            result = analyze(intake(beginning + ' Bây giờ tôi muốn đơn phương nghỉ việc, phải báo trước bao lâu?', []))
            self.assertNotEqual(result.query_date, '2018-04-12')
            self.assertNotEqual(result.temporal_intent, 'HISTORICAL')

    def test_signed_date_and_present_language_keep_current_clock(self):
        result = analyze(intake('Tôi ký hợp đồng ngày 12/04/2018. Hiện nay tôi muốn nghỉ việc, cần báo trước bao lâu?', []))
        self.assertNotEqual(result.query_date, '2018-04-12')
        self.assertNotEqual(result.temporal_resolution, 'AMBIGUOUS')

    def test_unknown_past_termination_does_not_default_to_start_day(self):
        result = analyze(intake('Tôi bắt đầu làm việc ngày 12/04/2018. Sau đó tôi bị công ty cho nghỉ việc. Việc này đúng luật không?', []))
        self.assertIsNone(result.query_date)
        self.assertEqual(result.temporal_resolution, 'AMBIGUOUS')

    def test_explicit_termination_still_wins_over_start_day(self):
        result = analyze(intake('Tôi bắt đầu làm việc ngày 12/04/2018; công ty chấm dứt hợp đồng ngày 25/08/2020. Có đúng không?', []))
        self.assertEqual(result.query_date, '2020-08-25')

    def test_multiple_background_milestones_do_not_override_a_current_request(self):
        a=analyze(intake('Tôi ký hợp đồng ngày 12/04/2018; bắt đầu làm việc từ ngày 19/04/2018. Bây giờ tôi muốn nghỉ việc, phải báo trước bao lâu?',[]))
        self.assertNotEqual(a.temporal_resolution,'AMBIGUOUS')
        self.assertNotIn(a.query_date,{'2018-04-12','2018-04-19'})

    def test_multiple_historical_contract_events_still_require_clarification(self):
        a=analyze(intake('Tôi ký hợp đồng ngày 12/04/2018; ký hợp đồng khác ngày 19/04/2026. Việc giao kết có đúng hình thức không?',[]))
        self.assertEqual(a.temporal_resolution,'AMBIGUOUS')
        self.assertIsNone(a.query_date)

    def test_negated_hazard_is_not_an_affirmative_work_category(self):
        for negative in ('không làm nghề nặng nhọc', 'không thuộc nhóm công việc nặng nhọc',
                         'không làm công việc đặc biệt nặng nhọc'):
            result = analyze(intake(f'Tôi làm công việc bình thường, {negative}. Tôi được nghỉ phép năm bao nhiêu ngày?', []))
            self.assertEqual(result.facts.get('work_category'), 'NORMAL')
            candidates = [c for c in result.fact_candidates if c.field == 'work_category']
            self.assertTrue(candidates)
            self.assertIn('bình thường', candidates[0].source_quote)

    def test_negative_category_does_not_prove_normal_conditions(self):
        result = analyze(intake('Tôi không làm nghề nặng nhọc. Tôi có bao nhiêu ngày phép năm?', []))
        self.assertNotIn('work_category', result.facts)

    def test_unknown_or_conflicting_categories_are_not_confirmed(self):
        for text in ('Tôi chưa rõ công việc có phải công việc nặng nhọc hay không.',
                     'Tôi làm công việc bình thường và làm công việc đặc biệt nặng nhọc.'):
            self.assertNotIn('work_category', analyze(intake(text, [])).facts)

    def test_bare_contract_fact_reply_resumes_the_pending_question(self):
        previous = 'Tôi muốn nghỉ việc vì lý do cá nhân, không làm nghề đặc thù. Tôi phải báo trước bao lâu?'
        result = resolve_context(QueryRequest(question='Không xác định thời hạn.',
            conversation_turns=[dict(turn_id='first',content=previous)]))
        self.assertTrue(result.used_turns)
        self.assertEqual(result.facts.get('contract_type'), 'INDEFINITE')
        parsed = analyze(intake(result.query, [], result.query_date, result.facts),result.query_date,result.facts)
        self.assertIn('TERMINATION.EMPLOYEE_UNILATERAL', parsed.legal_subissues)

    def test_bare_contract_reply_without_context_does_not_invent_a_task(self):
        result = resolve_context(QueryRequest(question='Không xác định thời hạn.'))
        self.assertFalse(result.used_turns)
        self.assertNotIn('nghỉ việc',result.query)

    def test_electronic_and_copy_questions_do_not_require_oral_exception(self):
        for question in ('Hợp đồng lao động điện tử có giá trị như văn bản không?',
                         'Khi giao kết hợp đồng lao động bằng văn bản, mỗi bên giữ một bản không?'):
            a=analyze(intake(question,[]),'2026-09-15')
            locators=[loc for group in plan_evidence(a).slot_requirements['contract_form'] for loc in group]
            self.assertTrue(locators)
            self.assertTrue(all(loc.clause=='1' for loc in locators))

    def test_oral_eligibility_preserves_the_exception_scope(self):
        a=analyze(intake('Tôi ký hợp đồng lao động bằng lời nói trong 20 ngày, có đúng hình thức không?',[]),'2026-09-15')
        locators=[loc for group in plan_evidence(a).slot_requirements['contract_form'] for loc in group]
        self.assertTrue(any(loc.clause is None for loc in locators))

    def test_duration_inside_expired_contract_does_not_hide_continuation(self):
        for duration in ('17 tháng','2 năm','45 ngày'):
            a=analyze(intake(f'Hợp đồng {duration} đã hết hạn, tôi tiếp tục làm việc mà chưa ký mới. Quyền lợi theo hợp đồng cũ không?',[]))
            self.assertIn('CONTRACT.CONTINUATION',a.legal_subissues)

    def test_negated_category_does_not_create_a_separate_task(self):
        for excluded in ('không thuộc nhóm lao động cao tuổi','không phải giúp việc gia đình'):
            a=analyze(intake(f'Tôi {excluded}. Hợp đồng 17 tháng đã hết hạn, tôi tiếp tục làm việc 35 ngày. Hợp đồng trở thành loại nào?',[]))
            self.assertIn('CONTRACT.CONTINUATION',a.legal_subissues)
            self.assertEqual(len(a.answer_tasks),1)
            self.assertNotIn('RETIREMENT',a.legal_issues)
            self.assertNotIn('DOMESTIC_WORKER',a.legal_issues)

    def test_specialist_rights_still_exist_when_actually_requested(self):
        from vn_labor_online.topics import detect_topics
        self.assertIn('older_workers',{t.key for t in detect_topics('Người lao động cao tuổi có quyền gì?')})
        self.assertIn('disabled_workers',{t.key for t in detect_topics('Công ty không được phân biệt đối xử với người khuyết tật như thế nào?')})


if __name__ == '__main__':
    unittest.main()
