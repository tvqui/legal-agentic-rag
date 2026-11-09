import unittest
from vn_labor_online.analysis import analyze,intake,plan_evidence

class EmployerNoticeEvidenceTests(unittest.TestCase):
    def test_notice_is_its_own_mandatory_source_group(self):
        for term,point in [('không xác định thời hạn','a'),('có thời hạn 27 tháng','b'),('có thời hạn 8 tháng','c')]:
            with self.subTest(term=term):
                q=f'Người lao động ký hợp đồng {term}, không làm công việc đặc thù, không thuộc trường hợp được bảo vệ tại Điều 37. Công ty muốn chấm dứt vì thường xuyên không hoàn thành công việc theo tiêu chí hợp lệ, phải báo trước bao lâu?'
                a=analyze(intake(q,[]),'2026-09-15');plan=plan_evidence(a)
                self.assertIn('employer_notice_requirement',plan.mandatory_slots)
                self.assertTrue(any(loc.article=='36' and loc.clause=='2' and loc.point==point for group in plan.slot_requirements['employer_notice_requirement'] for loc in group))
    def test_no_notice_branch_is_not_overridden_by_general_contract_duration(self):
        q='Người lao động có hợp đồng 27 tháng, không thuộc Điều 37, tự ý bỏ việc không lý do chính đáng 5 ngày làm việc liên tục. Theo điểm e khoản 1 Điều 36 công ty đơn phương chấm dứt có phải báo trước không?'
        a=analyze(intake(q,[]),'2026-09-15');plan=plan_evidence(a)
        self.assertIn('employer_notice_exemption',plan.mandatory_slots)
        self.assertNotIn('employer_notice_requirement',plan.mandatory_slots)
    def test_illness_ground_is_not_forced_into_generic_thirty_day_branch(self):
        q='Hợp đồng có thời hạn 27 tháng, không làm công việc đặc thù. Người lao động ốm đau đã điều trị kéo dài. Công ty chấm dứt thì phải báo trước bao lâu?'
        a=analyze(intake(q,[]),'2026-09-15');plan=plan_evidence(a)
        locs=[loc for group in plan.slot_requirements.get('employer_notice_requirement',[]) for loc in group]
        self.assertFalse(any(loc.point=='b' for loc in locs))
        self.assertTrue(any(loc.point=='c' for loc in locs))

    def test_negated_illness_ground_does_not_switch_the_notice_branch(self):
        q='Hợp đồng có thời hạn 27 tháng, không làm công việc đặc thù. Công ty chấm dứt do thường xuyên không hoàn thành công việc, không thuộc trường hợp ốm đau phải điều trị. Phải báo trước bao lâu?'
        a=analyze(intake(q,[]),'2026-09-15');plan=plan_evidence(a)
        locs=[loc for group in plan.slot_requirements.get('employer_notice_requirement',[]) for loc in group]
        self.assertTrue(any(loc.point=='b' for loc in locs))
        self.assertFalse(any(loc.point=='c' for loc in locs))

if __name__=='__main__':unittest.main()
