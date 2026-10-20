"""Service-year facts must retain the meaning of the user's duration."""
import unittest

from vn_labor_online.analysis import analyze,intake


class ServiceDurationTests(unittest.TestCase):
    def analysis(self,text):
        return analyze(intake(text,[]),'2026-09-15')

    def test_ordinal_year_is_not_an_additional_completed_year(self):
        for ordinal,completed in [('5',4),('6',5),('10',9),('11',10),('sáu',5)]:
            query=f'Tôi làm công việc bình thường đủ 12 tháng, đang ở năm thứ {ordinal} làm cho cùng công ty. Có bao nhiêu ngày phép năm?'
            with self.subTest(ordinal=ordinal):
                result=self.analysis(query)
                self.assertEqual(result.facts.get('service_years'),completed)
                candidates=[c for c in result.fact_candidates if c.field=='service_years']
                self.assertEqual(len(candidates),1)
                self.assertEqual(candidates[0].value,completed)
                self.assertEqual(query[candidates[0].char_start:candidates[0].char_end],candidates[0].source_quote)
                if completed>=5:
                    self.assertIn('LEAVE.SENIORITY_BONUS',result.legal_subissues)
                else:
                    self.assertNotIn('LEAVE.SENIORITY_BONUS',result.legal_subissues)

    def test_employer_abbreviation_and_spelled_duration_preserve_tenure(self):
        for duration,years in [('11',11),('mười một',11),('sáu',6)]:
            query=f'Tôi đã làm cùng NSDLĐ {duration} năm, trong năm làm tám tháng. Phép năm tính thế nào?'
            with self.subTest(duration=duration):
                result=self.analysis(query)
                self.assertEqual(result.facts.get('service_years'),years)
                self.assertEqual(result.facts.get('worked_months'),8)

    def test_explicit_tenure_and_continuous_work_remain_exact(self):
        for wording in ('đã làm việc liên tục cho cùng công ty được 10 năm',
                        'đã làm cho cùng người sử dụng lao động đủ 10 năm',
                        'có thâm niên 10 năm'):
            with self.subTest(wording=wording):
                self.assertEqual(self.analysis(f'Tôi {wording}. Phép năm bao nhiêu ngày?').facts.get('service_years'),10)

    def test_approximate_negative_and_calendar_years_are_not_exact_service(self):
        for wording in ('làm việc khoảng 5 năm','làm việc trên năm năm',
                        'chưa làm đủ 5 năm','không làm được 5 năm',
                        'làm việc dưới 10 năm','làm việc từ năm 2022',
                        'có thâm niên hơn 10 năm'):
            with self.subTest(wording=wording):
                self.assertNotIn('service_years',self.analysis(f'Tôi {wording}. Phép năm tính thế nào?').facts)


if __name__=='__main__': unittest.main()
