import unittest
from vn_labor_online.analysis import analyze,intake
from vn_labor_online.conversation import resolve_context
from vn_labor_online.models import QueryRequest


class UncertainNumericFactsTests(unittest.TestCase):
    def test_researcher_cannot_confirm_a_count_by_omitting_uncertainty_from_its_quote(self):
        from vn_labor_online.researcher import _verified_candidate,_entailed
        from vn_labor_online.models import FactCandidate
        examples=[('notice_days',23,'Tôi không nhớ đã báo trước 23 ngày hay chưa.','báo trước 23 ngày'),
                  ('worked_months',6,'Tôi chưa chắc đã làm việc đủ 6 tháng.','đã làm việc đủ 6 tháng')]
        for field,value,query,quote in examples:
            with self.subTest(field=field):
                start=query.index(quote)
                candidate=FactCandidate(field=field,value=value,source_quote=quote,
                    char_start=start,char_end=start+len(quote),origin='RESEARCHER')
                self.assertTrue(_entailed(field,value,quote))
                self.assertIsNone(_verified_candidate(candidate,query))

    def test_researcher_can_still_confirm_a_truly_asserted_count(self):
        from vn_labor_online.researcher import _verified_candidate
        from vn_labor_online.models import FactCandidate
        query='Tôi đã báo trước 23 ngày.';quote='báo trước 23 ngày';start=query.index(quote)
        candidate=FactCandidate(field='notice_days',value=23,source_quote=quote,
            char_start=start,char_end=start+len(quote),origin='RESEARCHER')
        self.assertIsNotNone(_verified_candidate(candidate,query))

    def test_uncertain_notice_count_is_not_a_confirmed_fact(self):
        for sentence in ('Tôi không nhớ đã báo trước 17 ngày hay chưa.',
                         'Tôi không chắc đã báo trước 38 ngày.',
                         'Tôi báo trước 13 ngày, hoặc 31 ngày nếu tôi nhớ đúng.'):
            a=analyze(intake(sentence+' Tôi ký hợp đồng không xác định thời hạn, không làm nghề đặc thù và không được miễn báo trước. Tôi nghỉ có đúng luật không?',[]),'2026-09-15')
            self.assertNotIn('notice_days',a.facts)
            self.assertTrue(any('bao nhiêu ngày' in question for question in a.missing_facts))
            self.assertFalse(any(c.field=='notice_days' for c in a.fact_candidates))

    def test_denial_of_a_particular_duration_does_not_prove_zero(self):
        a=analyze(intake('Tôi đã báo trước 19 ngày, chứ không báo trước 45 ngày. Tôi nghỉ vậy đúng không?',[]))
        self.assertEqual(a.facts.get('notice_days'),19)
        a=analyze(intake('Tôi không báo trước 45 ngày. Tôi nghỉ vậy đúng không?',[]))
        self.assertNotIn('notice_days',a.facts)

    def test_explicit_no_notice_remains_zero(self):
        a=analyze(intake('Tôi chưa hề báo trước. Tôi nghỉ việc ngay được không?',[]))
        self.assertEqual(a.facts.get('notice_days'),0)

    def test_negated_immediate_departure_is_not_zero_notice(self):
        for negative in ('Tôi không nghỉ ngay.','Tôi chưa có ý định nghỉ ngay.'):
            a=analyze(intake(negative+' Tôi đã báo trước 19 ngày.',[]))
            self.assertEqual(a.facts.get('notice_days'),19)

    def test_conflicting_notice_durations_do_not_pick_the_first(self):
        a=analyze(intake('Tôi báo trước 17 ngày và báo trước 31 ngày. Tôi có nghỉ được không?',[]))
        self.assertNotIn('notice_days',a.facts)

    def test_unknown_worked_months_requires_an_actual_duration(self):
        a=analyze(intake('Tôi chưa rõ mình đã làm việc đủ 12 tháng hay chưa. Tôi làm công việc bình thường. Tôi được bao nhiêu ngày nghỉ phép năm?',[]),'2026-09-15')
        self.assertNotIn('worked_months',a.facts)
        self.assertTrue(any('bao nhiêu tháng' in q for q in a.missing_facts))

    def test_contract_term_and_worked_months_remain_distinct(self):
        a=analyze(intake('Tôi ký hợp đồng lao động 18 tháng và làm việc đủ 7 tháng.',[]))
        self.assertEqual(a.facts.get('contract_duration_months'),18)
        self.assertEqual(a.facts.get('worked_months'),7)

    def test_current_uncertainty_cannot_revive_a_previous_notice_count(self):
        request=QueryRequest(question='Tôi không nhớ đã báo trước 17 ngày hay chưa. Tôi nghỉ vậy đúng không?',
            conversation_turns=[{'turn_id':'old','content':'Tôi ký hợp đồng không xác định thời hạn, đã báo trước 17 ngày rồi nghỉ việc.'}])
        context=resolve_context(request)
        self.assertEqual(context.clarification_reason,'UNCONFIRMED_USER_FACT')
        self.assertNotIn('notice_days',context.facts)

    def test_explicit_uncertainty_overrides_an_older_supplied_fact(self):
        a=analyze(intake('Tôi không nhớ đã báo trước 17 ngày hay chưa.',[]),supplied_facts={'notice_days':17})
        self.assertNotIn('notice_days',a.facts)
        self.assertIn('notice_days',a.uncertain_fact_fields)


if __name__=='__main__':unittest.main()
