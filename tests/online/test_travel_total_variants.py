import unittest
from vn_labor_online.analysis import analyze,intake

class TravelTotalVariantsTests(unittest.TestCase):
    def test_round_trip_variants_keep_total_and_provenance(self):
        for text in ['cả đi và về hết 7 ngày','đi lẫn về mất 5 ngày','tổng thời gian đi và về là 3 ngày']:
            with self.subTest(text=text):
                a=analyze(intake('Khi nghỉ phép năm, tôi đi đường bộ '+text+'. Thời gian đi đường được tính thêm thế nào?',[]),'2026-09-15')
                value=7 if '7' in text else 5 if '5' in text else 3
                self.assertEqual(a.facts.get('travel_days'),value)
                candidates=[f for f in a.fact_candidates if f.field=='travel_days']
                self.assertTrue(candidates)
                self.assertTrue(any(c.verified and str(value) in c.source_quote for c in candidates))
    def test_conflicting_totals_are_not_silently_reduced_to_the_first(self):
        a=analyze(intake('Khi nghỉ phép năm, cả đi và về hết 7 ngày, nhưng thời gian đi và về là 5 ngày theo vé. Tôi được tính thời gian đi đường thế nào?',[]),'2026-09-15')
        self.assertNotIn('travel_days',a.facts)
    def test_one_way_duration_is_not_treated_as_a_round_trip_total(self):
        a=analyze(intake('Tôi nghỉ phép năm, đi đường bộ 3 ngày, chưa biết chiều về mất bao lâu. Thời gian đi đường có được tính thêm không?',[]),'2026-09-15')
        self.assertNotIn('travel_days',a.facts)

if __name__=='__main__':unittest.main()
