import unittest
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig
from vn_labor_online.models import Evidence

class DurationGuardScopeTests(unittest.TestCase):
    def source(self,article,text,clause='1'):
        return Evidence(unit_id='rule',kind='PROVISION',text=text,source_text=text,
            document_number='45/2019/QH14',article_number=article,clause_number=clause,
            retrieval_method='policy',score=1)
    def decision(self,item,q,issues,facts):
        return LegalApplicabilityAuditor(ApplicabilityConfig()).audit([item],q,issues,facts,'EXPLAIN')[1][0]
    def test_insufficient_employment_duration_is_not_reason_to_drop_severance_criterion(self):
        e=self.source('46','Người lao động đã làm việc thường xuyên từ đủ 12 tháng trở lên được trợ cấp thôi việc theo điều kiện luật định.')
        d=self.decision(e,'Làm việc 7 tháng thì đã đủ điều kiện thời gian nhận trợ cấp thôi việc không?',['TERMINATION'],{'worked_months':7})
        self.assertNotIn('FACT_CONTRADICTS_FULL_12_MONTH_RULE',d.reasons)
        self.assertNotEqual(d.audit_status,'FAIL')
    def test_service_months_do_not_establish_insurance_contribution_months(self):
        e=self.source('2','Người tham gia chưa đủ 12 tháng đóng bảo hiểm có điều kiện riêng.')
        d=self.decision(e,'Điều kiện hưởng bảo hiểm được quy định thế nào?',['SOCIAL_INSURANCE'],{'worked_months':15})
        self.assertNotIn('FACT_CONTRADICTS_UNDER_12_MONTH_RULE',d.reasons)
    def test_incompatible_annual_leave_branch_is_still_rejected(self):
        e=self.source('113','Người lao động làm việc chưa đủ 12 tháng được nghỉ hằng năm theo tỷ lệ.',clause='2')
        d=self.decision(e,'Làm việc đủ 12 tháng được nghỉ phép năm thế nào?',['LEAVE'],{'worked_months':12})
        self.assertEqual(d.audit_status,'FAIL')
        self.assertIn('FACT_CONTRADICTS_UNDER_12_MONTH_RULE',d.reasons)

if __name__=='__main__':unittest.main()
