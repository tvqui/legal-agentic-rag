"""General regressions from a Graph QA review; no answer hardcoding or live models."""
import unittest
from vn_labor_online.analysis import analyze,intake
from vn_labor_online.audit import citations
from vn_labor_online.models import Evidence
class InputCoverageTests(unittest.TestCase):
    def analyze(self,q):return analyze(intake(q,[],'2026-09-15'),'2026-09-15')
    def test_instrument_and_container_remain_distinct(self):
        c=citations([Evidence(unit_id='u',retrieval_method='fixture',text='source',document_number='18/VBHN-VPQH',original_instrument_number='45/2019/QH14')])[0]
        self.assertEqual(c.instrument_number,'45/2019/QH14');self.assertEqual(c.document_number,'18/VBHN-VPQH')
    def test_qualification_job_modifiers_are_extracted(self):
        a=self.analyze('Vị trí tuyển dụng của tôi yêu cầu trình độ cao đẳng, không phải quản lý doanh nghiệp. Thử việc 100 ngày có được không?')
        self.assertEqual(a.facts.get('probation_work_group'),'COLLEGE')
        self.assertFalse(any('Công việc thuộc nhóm' in q for q in a.missing_facts))
    def test_pay_question_does_not_inherit_other_tasks_duration(self):
        a=self.analyze('Cho tôi biết lương thử việc tối thiểu bằng bao nhiêu phần trăm; khi tôi kết hôn được nghỉ mấy ngày?')
        self.assertIn('CONTRACT.PROBATION_PAY',a.legal_subissues)
        self.assertNotIn('CONTRACT.PROBATION_DURATION',a.legal_subissues)
        self.assertFalse(any('Công việc thuộc nhóm' in q for q in a.missing_facts))
    def test_counted_months_and_explicit_no_seniority_bonus(self):
        a=self.analyze('Tôi làm việc trong điều kiện bình thường, chưa có thâm niên tăng phép. Năm đầu chỉ có đúng tám tháng làm việc được tính phép. Tôi được bao nhiêu ngày nghỉ hằng năm?')
        self.assertEqual(a.facts.get('worked_months'),8)
        self.assertFalse(any('bao nhiêu tháng' in q or 'thâm niên' in q for q in a.missing_facts))
    def test_uncertain_months_do_not_become_exact_operands(self):
        a=self.analyze('Năm nay tôi có khoảng tám tháng làm việc được tính phép. Tôi được mấy ngày phép năm?')
        self.assertIsNone(a.facts.get('worked_months'))
    def test_other_degree_and_contract_term_not_work_facts(self):
        a=self.analyze('Tôi có bằng cao đẳng, ký hợp đồng tám tháng. Tôi chưa biết công việc yêu cầu trình độ gì.')
        self.assertIsNone(a.facts.get('probation_work_group'));self.assertIsNone(a.facts.get('worked_months'))
    def test_excluded_overtime_not_a_requested_task(self):
        a=self.analyze('Theo chế độ thời gian làm việc theo ngày trong điều kiện bình thường, giới hạn mỗi ngày và tuần là gì? Không tính làm thêm. Ban đêm tính từ mấy giờ?')
        self.assertIn('WORKING_TIME.NORMAL_HOURS',a.legal_subissues)
        self.assertNotIn('WORKING_TIME.OVERTIME_LIMITS',a.legal_subissues)
    def test_incidental_citation_not_literal_lookup(self):
        a=self.analyze('Ngoài trường hợp tại Điều 108, công ty cần tôi đồng ý những nội dung nào để làm thêm giờ? Nối Bộ luật Lao động với Nghị định 145.')
        self.assertNotEqual(a.requested_outcome,'LOOKUP')
        self.assertFalse(any('văn bản pháp luật nào' in q for q in a.missing_facts))
    def test_conditional_rule_explanation_not_personal_adjudication(self):
        a=self.analyze('Khi hết tạm hoãn mà hợp đồng còn hiệu lực, người lao động phải trở lại trong bao lâu? Nếu không có mặt theo Điều 31 thì công ty có quyền chấm dứt và có phải báo trước không?')
        self.assertEqual(a.requested_outcome,'EXPLAIN');self.assertFalse(a.missing_facts)
        from vn_labor_online.analysis import plan_evidence
        self.assertIn('return_after_suspension_rule',plan_evidence(a).slot_requirements)

    def test_expiry_priority_is_not_replaced_by_unilateral_protection(self):
        from vn_labor_online.analysis import plan_evidence
        a=self.analyze('Hợp đồng xác định thời hạn của tôi đến ngày hết hạn lúc đang mang thai. Tôi được ưu tiên gì khi ký hợp đồng mới?')
        p=plan_evidence(a)
        self.assertIn('TERMINATION.EXPIRY',a.legal_subissues)
        self.assertIn('maternity_expiry_protection',p.slot_requirements)
    def test_special_fixed_term_requires_delegated_notice_source(self):
        from vn_labor_online.analysis import plan_evidence
        a=self.analyze('Tôi làm công việc đặc thù, là thành viên tổ lái tàu bay, hợp đồng 18 tháng. Tôi nghỉ vì lý do cá nhân, không thuộc diện được nghỉ không báo trước. Tôi phải báo trước bao lâu?')
        self.assertFalse(a.facts.get('notice_exception'));self.assertIsNone(a.facts.get('notice_days'))
        p=plan_evidence(a)
        self.assertIn('special_notice_rule',p.slot_requirements)
        loc=p.slot_requirements['special_notice_rule'][0][0]
        self.assertEqual((loc.article,loc.clause,loc.point),('7','2','a'))
    def test_nonexpired_contract_does_not_assert_expiry(self):
        from vn_labor_online.termination_context import contract_expiry_context
        self.assertFalse(contract_expiry_context('Hợp đồng của tôi chưa đến ngày hết hạn, công ty đã cho nghỉ.'))


    def test_numeric_quantity_in_another_task_not_probation_duration(self):
        a=self.analyze('Tôi hỏi mức lương thử việc tối thiểu; khi tôi kết hôn nghỉ 3 ngày có hưởng lương không?')
        self.assertNotIn('CONTRACT.PROBATION_DURATION',a.legal_subissues)

if __name__=='__main__':unittest.main()
