from unittest import TestCase

from vn_labor_online.analysis import analyze, intake, plan_evidence
from vn_labor_online.conversation import resolve_context
from vn_labor_online.models import QueryRequest
from vn_labor_online.researcher import _entailed


FIRST = ('Tôi ký hợp đồng không xác định thời hạn. Tôi chỉ báo trước 20 ngày rồi nghỉ. '
         'Tôi nghỉ như vậy có trái pháp luật không?')
REPLY = ('Tôi không làm ngành, nghề hoặc công việc đặc thù. Tôi nghỉ vì lý do cá nhân, '
         'không thuộc trường hợp được nghỉ không cần báo trước. Ngày dự kiến nghỉ chính thức là 30/09/2026, '
         'tôi chỉ báo trước 20 ngày và công ty chưa đồng ý cho nghỉ sớm. Với những dữ kiện này, '
         'tôi nghỉ như vậy có đúng không và có thể phải chịu hậu quả gì?')


def resolve(text, history=()):
    request = QueryRequest(question=text, conversation_turns=[
        {'turn_id': str(i), 'content': value} for i, value in enumerate(history)])
    context = resolve_context(request)
    analysis = analyze(intake(context.query, [], context.query_date, context.facts),
                       context.query_date, context.facts)
    return context, analysis


class ClarificationFollowupTests(TestCase):
    def test_reported_two_turn_reply_completes_fact_gate_and_keeps_consequences(self):
        context, analysis = resolve(REPLY, [FIRST])
        self.assertEqual(context.used_turns, ['0'])
        self.assertEqual(analysis.facts['contract_type'], 'INDEFINITE')
        self.assertIs(analysis.facts['special_occupation'], False)
        self.assertIs(analysis.facts['notice_exception'], False)
        self.assertIs(analysis.facts['mutual_termination_agreement'], False)
        self.assertEqual(analysis.facts['notice_days'], 20)
        self.assertEqual(analysis.query_date, '2026-09-30')
        self.assertEqual(analysis.missing_facts, [])
        self.assertIn('legal_consequences', plan_evidence(analysis).mandatory_slots)
        origin = next(p for p in context.provenance if p['field'] == 'contract_type')
        self.assertEqual(FIRST[origin['char_start']:origin['char_end']], origin['source_quote'])

    def test_category_wording_variants_keep_full_negative_source_span(self):
        for text in (
            'Tôi không làm ngành, nghề hoặc công việc đặc thù.',
            'Tôi không thuộc ngành, nghề, công việc đặc thù.',
            'Tôi không làm ngành nghề đặc thù.',
            'Tôi không thuộc công việc đặc thù.',
            'Công việc của tôi không phải công việc đặc thù.',
            'Tôi không thuộc nhóm ngành, nghề và công việc đặc thù.',
        ):
            with self.subTest(text=text):
                analysis = analyze(intake(text, []))
                self.assertIs(analysis.facts['special_occupation'], False)
                candidate = next(c for c in analysis.fact_candidates if c.field == 'special_occupation')
                self.assertIn('không', candidate.source_quote)
                self.assertEqual(text[candidate.char_start:candidate.char_end], candidate.source_quote)

    def test_positive_statement_is_not_confused_with_negative_category(self):
        for text in ('Tôi làm ngành, nghề hoặc công việc đặc thù.',
                     'Tôi thuộc ngành nghề đặc thù.', 'Tôi làm công việc đặc thù.'):
            with self.subTest(text=text):
                self.assertIs(analyze(intake(text, [])).facts.get('special_occupation'), True)

    def test_uncertainty_question_and_hypothesis_are_not_confirmed_facts(self):
        for text in ('Tôi không biết có thuộc ngành, nghề hoặc công việc đặc thù không.',
                     'Tôi chưa rõ công việc có thuộc ngành nghề đặc thù không.',
                     'Công việc có thuộc ngành, nghề hoặc công việc đặc thù không?',
                     'Tôi thuộc ngành nghề đặc thù, phải không?',
                     'Nếu tôi làm ngành nghề đặc thù thì sao?'):
            with self.subTest(text=text):
                self.assertNotIn('special_occupation', analyze(intake(text, [])).facts)

    def test_researcher_cannot_reverse_a_negative_statement(self):
        quote = 'Tôi không làm ngành, nghề hoặc công việc đặc thù.'
        self.assertTrue(_entailed('special_occupation', False, quote))
        self.assertFalse(_entailed('special_occupation', True, quote))
        self.assertFalse(_entailed('special_occupation', False, 'Tôi chưa rõ công việc có thuộc ngành nghề đặc thù không.'))

    def test_a_later_reply_keeps_previously_confirmed_negative_category(self):
        previous = FIRST + ' Tôi không làm ngành, nghề hoặc công việc đặc thù.'
        context, analysis = resolve('Tôi chỉ báo trước 20 ngày. Tôi không thuộc trường hợp được nghỉ không cần báo trước.', [previous])
        self.assertIs(analysis.facts['special_occupation'], False)
        origin = next(p for p in context.provenance if p['field'] == 'special_occupation')
        self.assertIn('không', origin['source_quote'])
        self.assertEqual(previous[origin['char_start']:origin['char_end']], origin['source_quote'])

    def test_current_negative_correction_overrides_previous_positive_category(self):
        previous = FIRST + ' Tôi làm ngành nghề đặc thù.'
        context, analysis = resolve('Đính chính: ' + REPLY, [previous])
        self.assertIs(analysis.facts['special_occupation'], False)
        records=[p for p in context.provenance if p['field']=='special_occupation']
        self.assertTrue(any(p['status']=='SUPERSEDED' for p in records))
        self.assertTrue(any(p['turn_id']=='current_request' and p['status']=='USER_REPORTED'
            and 'không' in p['source_quote'].lower() for p in records))

    def test_no_history_does_not_invent_contract_type(self):
        context, analysis = resolve(REPLY)
        self.assertFalse(context.used_turns)
        self.assertNotIn('contract_type', analysis.facts)
        self.assertIs(analysis.facts['special_occupation'], False)
        self.assertIn('Loại hợp đồng là gì?', analysis.missing_facts)

    def test_explicit_new_case_does_not_inherit_contract_type(self):
        context, analysis = resolve('Tình huống mới: ' + REPLY, [FIRST])
        self.assertFalse(context.used_turns)
        self.assertNotIn('contract_type', analysis.facts)

    def test_unrelated_topic_does_not_inherit_resignation_facts(self):
        context, analysis = resolve('Tôi không làm công việc đặc thù. Tôi làm đủ 12 tháng thì được nghỉ phép bao nhiêu ngày?', [FIRST])
        self.assertFalse(context.used_turns)
        self.assertNotIn('contract_type', analysis.facts)
        self.assertNotIn('notice_days', analysis.facts)

    def test_explicit_new_independent_question_does_not_reuse_contract_type(self):
        text = ('Tôi ký hợp đồng lao động ở công ty khác. Tôi chỉ báo trước 20 ngày rồi nghỉ. '
                'Tôi không làm công việc đặc thù và không thuộc trường hợp được nghỉ không cần báo trước. Có đúng không?')
        context, analysis = resolve(text, [FIRST])
        self.assertFalse(context.used_turns)
        self.assertNotIn('contract_type', analysis.facts)

    def test_short_negative_fact_reply_resumes_prior_assessment(self):
        previous = FIRST + ' Tôi không thuộc trường hợp được nghỉ không cần báo trước.'
        context, analysis = resolve('Tôi không làm ngành, nghề hoặc công việc đặc thù.', [previous])
        self.assertEqual(context.used_turns, ['0'])
        self.assertEqual(analysis.requested_outcome, 'ASSESS_LEGALITY')
        self.assertEqual(analysis.missing_facts, [])
