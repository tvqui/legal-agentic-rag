import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence


class PopulationRuleScopeTests(unittest.TestCase):
    def plan(self,question,day='2026-09-15'):
        return plan_evidence(analyze(intake(question,[]),day))

    def test_special_population_ban_does_not_require_general_overtime_permissions(self):
        for age in (12,13,14):
            with self.subTest(age=age):
                p=self.plan(f'Người lao động {age} tuổi có được làm 5 giờ một ngày hoặc làm thêm ban đêm không?')
                self.assertIn('minor_working_time',p.slot_requirements)
                self.assertNotIn('overtime_limits',p.slot_requirements)
                self.assertNotIn('overtime_extended_conditions',p.slot_requirements)
                self.assertNotIn('exceptions',p.mandatory_slots)
                self.assertEqual([(l.article,l.clause) for g in p.slot_requirements['minor_working_time'] for l in g],[('146','1')])

    def test_older_minor_overtime_keeps_general_caps_and_specific_population_rule(self):
        p=self.plan('Người lao động 17 tuổi có được làm thêm đến 280 giờ mỗi năm không?')
        self.assertIn('overtime_limits',p.slot_requirements)
        self.assertIn('minor_working_time',p.slot_requirements)
        self.assertEqual(p.slot_requirements['minor_working_time'][0][0].clause,'2')

    def test_old_code_hours_use_the_actual_historical_clause(self):
        for age in (13,16):
            p=self.plan(f'Người lao động {age} tuổi được làm tối đa bao nhiêu giờ mỗi tuần?','2020-09-15')
            self.assertEqual([(l.article,l.clause,l.documents) for g in p.slot_requirements['minor_working_time'] for l in g],[('163','2',['10/2012/QH13'])])

    def test_old_code_overtime_permission_has_its_own_clause(self):
        p=self.plan('Người lao động 17 tuổi có được làm thêm ban đêm không?','2020-09-15')
        self.assertEqual([g[0].clause for g in p.slot_requirements['minor_working_time']],['2','3'])

    def test_comparison_preserves_both_special_and_general_rules(self):
        p=self.plan('So sánh giới hạn làm thêm giờ của người lao động 14 tuổi với người trưởng thành.')
        self.assertIn('minor_working_time',p.slot_requirements)
        self.assertIn('overtime_limits',p.slot_requirements)


if __name__=='__main__':unittest.main()
