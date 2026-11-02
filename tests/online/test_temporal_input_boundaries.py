"""Temporal input is a constraint, never permission to guess another date."""
import unittest
from datetime import datetime, timezone
from vn_labor_online.analysis import analyze, intake
from vn_labor_online.event_time import resolve_event_dates

class TemporalInputBoundaryTests(unittest.TestCase):
    def analyze(self, query, explicit=None):
        return analyze(intake(query, []), explicit)

    def test_written_day_month_year_preserves_exact_day(self):
        for day, month, year in [(15,12,2020),(1,1,2021),(29,2,2024),(7,8,2026)]:
            with self.subTest(day=day,month=month,year=year):
                a=self.analyze(f'Ngày {day} tháng {month} năm {year}, quy định tiền lương là gì?')
                expected=f'{year:04d}-{month:02d}-{day:02d}'
                self.assertEqual((a.query_date,a.query_date_end,a.query_date_precision),(expected,expected,'DAY'))

    def test_invalid_calendar_mentions_cannot_be_reinterpreted_as_a_year_or_today(self):
        for value in ['tháng 13 năm 2020','tháng 0/2020','tháng 19-2021',
                      'ngày 31 tháng 4 năm 2020','ngày 29 tháng 2 năm 2021',
                      'ngày 00 tháng 12 năm 2020','32/01/2022','2023-00-10']:
            with self.subTest(value=value):
                a=self.analyze(f'Quy định tiền lương tại {value} là gì?')
                self.assertEqual(a.temporal_resolution,'AMBIGUOUS')
                self.assertIsNone(a.query_date)
                self.assertTrue(a.missing_facts)

    def test_date_mentions_follow_text_order_instead_of_format_order(self):
        a=self.analyze('So sánh tiền lương ngày 15/12/2020 với ngày 2021-02-15.')
        self.assertEqual(a.event_dates[:2],['2020-12-15','2021-02-15'])

    def test_event_roles_also_ground_written_dates(self):
        text='Tôi ký hợp đồng ngày 02 tháng 3 năm 2018; công ty sa thải tôi ngày 14 tháng 6 năm 2025.'
        events, selected, ambiguous=resolve_event_dates(text)
        self.assertFalse(ambiguous)
        self.assertEqual(selected,'2025-06-14')
        self.assertEqual([e['role'] for e in events],['CONTRACT_SIGNED_AT','TERMINATION_AT'])
        for event in events:
            self.assertEqual(text[event['char_start']:event['char_end']],event['source_quote'])

    def test_date_before_event_verb_is_grounded_to_its_own_clause(self):
        text='Ngày 02/03/2018 tôi ký hợp đồng; ngày 14/06/2025 công ty sa thải tôi.'
        events, selected, ambiguous=resolve_event_dates(text)
        self.assertFalse(ambiguous)
        self.assertEqual(selected,'2025-06-14')
        self.assertEqual([e['role'] for e in events],['CONTRACT_SIGNED_AT','TERMINATION_AT'])

    def test_partial_month_and_year_do_not_become_full_date(self):
        for text,start,end,precision in [('tháng 2 năm 2024','2024-02-01','2024-02-29','MONTH'),
                                         ('năm 2020','2020-01-01','2020-12-31','YEAR')]:
            a=self.analyze('Quy định tiền lương trong '+text+'?')
            self.assertEqual((a.query_date,a.query_date_end,a.query_date_precision),(start,end,precision))

    def test_law_identifier_is_not_an_event_month(self):
        a=self.analyze('Điều 1 Nghị định 145/2020/NĐ-CP quy định gì?')
        self.assertIsNone(a.query_date)
        self.assertEqual(a.query_date_precision,'NONE')

    def test_current_request_day_still_uses_vietnam_clock(self):
        env=intake('Quy định tiền lương hôm nay là gì?',[])
        env.received_at=datetime(2026,10,31,18,tzinfo=timezone.utc)
        self.assertEqual(analyze(env).query_date,'2026-11-01')

if __name__=='__main__': unittest.main()
