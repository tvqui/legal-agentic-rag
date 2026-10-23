"""Never turn missing worker/job facts into a concrete leave entitlement."""
import unittest
from tests.online.test_output_precision import rule,pack
from vn_labor_online.generation import _annual_leave_answer


class AnnualLeaveUnknownCategoryTests(unittest.TestCase):
    def items(self):
        return [rule('normal','113','1','a','12 ngày làm việc đối với người làm công việc trong điều kiện bình thường;'),
            rule('heavy','113','1','b','14 ngày làm việc đối với người lao động chưa thành niên, lao động là người khuyết tật, người làm nghề, công việc nặng nhọc, độc hại, nguy hiểm;'),
            rule('special','113','1','c','16 ngày làm việc đối với người làm nghề, công việc đặc biệt nặng nhọc, độc hại, nguy hiểm.'),
            rule('seniority','114',text='Cứ đủ 05 năm làm việc cho một người sử dụng lao động thì số ngày nghỉ hằng năm được tăng thêm tương ứng 01 ngày.')]

    def draft(self,**facts):
        facts={'query_intent':'ANNUAL_LEAVE_CALC','service_years':6,'worked_months':12,**facts}
        return _annual_leave_answer(pack('Tôi làm được 6 năm, được nghỉ phép bao nhiêu ngày?',self.items(),facts),True,[])

    def test_tenure_and_months_do_not_establish_job_group(self):
        self.assertIsNone(self.draft())

    def test_disability_alone_does_not_exclude_special_heavy_work(self):
        self.assertIsNone(self.draft(disabled=True))

    def test_minority_alone_does_not_establish_the_job_group(self):
        self.assertIsNone(self.draft(minor=True))

    def test_normal_work_does_not_imply_adult_without_disability(self):
        draft=self.draft(work_category='NORMAL')
        self.assertTrue(draft.claims[0].text.startswith('Nếu người lao động không thuộc nhóm'))
        self.assertIn('chưa thành niên hoặc người khuyết tật',draft.claims[0].text)
        self.assertEqual(set(draft.claims[0].evidence_ids),{'normal','seniority'})

    def test_verified_normal_adult_group_keeps_its_source_bound_calculation(self):
        draft=self.draft(work_category='NORMAL',minor=False,disabled=False)
        self.assertIn('13 ngày',draft.claims[0].text)
        self.assertFalse(draft.claims[0].text.startswith('Nếu người lao động không thuộc nhóm'))

    def test_known_disability_in_normal_work_keeps_14_day_base(self):
        draft=self.draft(work_category='NORMAL',disabled=True)
        self.assertIn('15 ngày',draft.claims[0].text)
        self.assertEqual(set(draft.claims[0].evidence_ids),{'heavy','seniority'})

    def test_special_heavy_group_is_not_reduced_by_disability(self):
        draft=self.draft(work_category='SPECIAL_HEAVY',disabled=True)
        self.assertIn('17 ngày',draft.claims[0].text)
        self.assertEqual(set(draft.claims[0].evidence_ids),{'heavy','special','seniority'})


if __name__=='__main__': unittest.main()
