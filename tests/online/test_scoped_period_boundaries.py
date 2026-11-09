import unittest
from types import SimpleNamespace as NS
from vn_labor_online.models import QueryRequest
from vn_labor_online.period_answers import rule_periods
from vn_labor_online.retrieval import Retriever
from vn_labor_online.config import OnlineConfig
from vn_labor_online.claim_validation import semantic_issues

class ScopedPeriodBoundaryTests(unittest.TestCase):
    def test_unrelated_publication_does_not_split_known_rule_explanation(self):
        units=[{'unit_id':'old','kind':'PROVISION','document_number':'10/2012/QH13','article_number':'27','clause_number':'1','point_number':'','source_text':'Thời gian thử việc theo trình độ cao đẳng.','text':'Thời gian thử việc theo trình độ cao đẳng.','valid_from':'2013-05-01','valid_to':'2021-01-01'},
               {'unit_id':'new','kind':'PROVISION','document_number':'45/2019/QH14','article_number':'25','clause_number':'2','point_number':'','source_text':'Thời gian thử việc theo trình độ cao đẳng.','text':'Thời gian thử việc theo trình độ cao đẳng.','valid_from':'2021-01-01','valid_to':None},
               {'unit_id':'unrelated','kind':'PROVISION','document_number':'145/2020/NĐ-CP','article_number':'99','text':'Một nội dung khác.','promulgated_date':'2020-12-30','valid_from':'2021-02-01'}]
        store=NS(units=units,units_by_id={u['unit_id']:u for u in units},edges=[],nodes=[])
        retriever=Retriever(store,OnlineConfig(artifact_source='unused'))
        req=QueryRequest(question='Từ 20/12/2020 đến 10/01/2021, công việc yêu cầu cao đẳng có thời gian thử việc tối đa bao lâu?')
        periods=rule_periods(req,store,retriever=retriever)
        self.assertEqual([(p.start,p.end) for p in periods],[('2020-12-20','2020-12-31'),('2021-01-01','2021-01-10')])
    def test_one_version_does_not_prove_no_change_over_an_interval(self):
        source=NS(text='Thời gian thử việc không quá 60 ngày.',full_text='Thời gian thử việc không quá 60 ngày.')
        text='Không có quy định thay đổi về thời gian thử việc trong khoảng thời gian từ 2014 đến 2020.'
        self.assertIn('CLAIM_UNPROVED_CHANGE_ABSENCE',semantic_issues(text,[source]))
    def test_pointwise_comparison_is_not_an_exhaustive_change_history(self):
        source=NS(text='Thời gian thử việc không quá 60 ngày.',full_text='Thời gian thử việc không quá 60 ngày.')
        self.assertNotIn('CLAIM_UNPROVED_CHANGE_ABSENCE',semantic_issues('Ở hai mốc được đối chiếu, mức trần cùng là 60 ngày nên không thay đổi về con số giữa hai mốc.',[source]))

if __name__=='__main__':unittest.main()
