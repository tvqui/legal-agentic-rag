import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from vn_labor_online.models import QueryRequest,AnswerResponse,Trace,Route,Stop,Claim,Citation
from vn_labor_online.period_answers import rule_periods,RulePeriod,combine_period_answers
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_online.runtime import RequestStopped

QUERY='Từ 20/12/2020 đến 10/01/2021, thời gian thử việc tối đa của công việc yêu cầu cao đẳng là bao lâu? Nếu quy định thay đổi trong khoảng này hãy phân biệt.'

class PeriodAnswerTests(unittest.TestCase):
    def store(self):
        return NS(units=[{'valid_from':'2013-05-01','valid_to':'2021-01-01'},
                         {'valid_from':'2021-01-01','valid_to':None}],
                  cfg=NS(corpus_snapshot_as_of='2026-09-15'),units_by_id={},report=NS(legal_status='PROVISIONAL'))
    def response(self,when,uid='source',status=Stop.PARTIAL_ALLOWED):
        trace=Trace(trace_id='t_'+when,query_id='q',build_id='build',route=Route.STANDARD,route_reason='test',reference_audit='PASS')
        return AnswerResponse(query_id='q',trace_id=trace.trace_id,trace=trace,build_id='build',status=status,
            query_date=when,answer=f'Quy định tại ngày {when} [{uid}]' if status==Stop.PARTIAL_ALLOWED else 'Thiếu căn cứ.',
            claims=[Claim(claim_id='same_id',text='Nội dung đã qua hậu kiểm.',evidence_ids=[uid])] if status==Stop.PARTIAL_ALLOWED else [],
            citations=[Citation(evidence_id=uid)] if status==Stop.PARTIAL_ALLOWED else [],evidence_status='PARTIAL')
    def test_slices_use_exclusive_valid_to_without_gaps(self):
        periods=rule_periods(QueryRequest(question=QUERY),self.store())
        self.assertEqual([(p.start,p.end) for p in periods],[('2020-12-20','2020-12-31'),('2021-01-01','2021-01-10')])
        self.assertIn('Tại ngày 2020-12-20',periods[0].question)
        self.assertNotIn('10/01/2021',periods[0].question)
        self.assertNotIn('hãy phân biệt',periods[0].question.lower())
        self.assertNotIn('hãy phân biệt',periods[1].question.lower())
    def test_written_calendar_range_is_supported(self):
        q=QUERY.replace('20/12/2020','ngày 20 tháng 12 năm 2020').replace('10/01/2021','ngày 10 tháng 1 năm 2021')
        self.assertEqual(len(rule_periods(QueryRequest(question=q),self.store())),2)
    def test_many_changes_are_bounded_instead_of_dropping_middle_periods(self):
        store=self.store();store.units += [{'valid_from':f'2021-01-{d:02d}'} for d in range(2,8)]
        self.assertFalse(rule_periods(QueryRequest(question=QUERY),store))
    def test_invalid_or_reversed_dates_do_not_form_a_period_plan(self):
        for q in [QUERY.replace('20/12/2020','31/04/2020'),QUERY.replace('20/12/2020','20/12/2022')]:
            self.assertFalse(rule_periods(QueryRequest(question=q),self.store()))
    def test_concrete_cases_and_api_dates_are_not_silently_split(self):
        self.assertFalse(rule_periods(QueryRequest(question=QUERY,query_date='2026-09-15'),self.store()))
        self.assertFalse(rule_periods(QueryRequest(question='Tôi làm việc '+QUERY),self.store()))
        self.assertFalse(rule_periods(QueryRequest(question=QUERY,facts={'contract_type':'INDEFINITE'}),self.store()))
    def test_impersonal_concrete_assessments_are_not_recast_as_rule_explanations(self):
        for q in ['Từ 20/12/2020 đến 10/01/2021, công ty sa thải người lao động có đúng luật không?',
                  'Từ 20/12/2020 đến 10/01/2021, công ty cho thử 75 ngày ở công việc yêu cầu cao đẳng, có hợp pháp không?']:
            with self.subTest(q=q):self.assertFalse(rule_periods(QueryRequest(question=q),self.store()))
    def test_snapshot_boundary_is_also_checked(self):
        req=QueryRequest(question='Từ 14/09/2026 đến 17/09/2026, mức lương được quy định thế nào?')
        periods=rule_periods(req,self.store())
        self.assertEqual([(p.start,p.end) for p in periods],[('2026-09-14','2026-09-15'),('2026-09-16','2026-09-17')])
    def test_period_claim_ids_are_namespaced_and_sources_stay_visible(self):
        req=QueryRequest(question=QUERY);periods=rule_periods(req,self.store())
        r=combine_period_answers(req,periods,[self.response('2020-12-20','old'),self.response('2021-01-01','new')])
        self.assertEqual([c.claim_id for c in r.claims],['period_1_same_id','period_2_same_id'])
        self.assertEqual({c.evidence_id for c in r.citations},{'old','new'})
        self.assertIsNone(r.query_date)
        self.assertEqual(r.status,Stop.PARTIAL_ALLOWED)
        self.assertIn('cross_period_synthesis_not_verified',r.limitations)
    def test_failed_period_is_not_erased_or_called_answered(self):
        req=QueryRequest(question=QUERY);periods=rule_periods(req,self.store())
        r=combine_period_answers(req,periods,[self.response('2020-12-20','old'),self.response('2021-01-01',status=Stop.INSUFFICIENT_EVIDENCE)])
        self.assertEqual(len(r.claims),1);self.assertEqual(r.parts[-1].answer_status,'MISSING')
        self.assertIn('Thiếu căn cứ.',r.answer)
        self.assertEqual(r.status,Stop.PARTIAL_ALLOWED)
    def test_artifact_mismatch_cannot_be_merged(self):
        req=QueryRequest(question=QUERY);periods=rule_periods(req,self.store())
        second=self.response('2021-01-01');second.build_id='other'
        with self.assertRaises(ValueError):combine_period_answers(req,periods,[self.response('2020-12-20'),second])
    def test_unchecked_claims_cannot_be_exposed_by_aggregation(self):
        req=QueryRequest(question=QUERY);periods=rule_periods(req,self.store())
        bad=self.response('2020-12-20','unchecked');bad.trace.reference_audit='FAIL'
        r=combine_period_answers(req,periods,[bad,self.response('2021-01-01','checked')])
        self.assertEqual({c.evidence_id for c in r.citations},{'checked'})
        self.assertNotIn('[unchecked]',r.answer)
        self.assertEqual(len(r.claims),1)
    def test_obvious_outside_domain_is_not_sent_through_period_subrequests(self):
        req=QueryRequest(question='Từ 20/12/2020 đến 10/01/2021, thủ tục quyền sử dụng đất quy định thế nào?')
        self.assertFalse(rule_periods(req,self.store()))
    def test_conflicting_period_keeps_source_links_and_conflict_status(self):
        req=QueryRequest(question=QUERY);periods=rule_periods(req,self.store())
        first=self.response('2020-12-20',status=Stop.CONFLICTING_EVIDENCE)
        first.citations=[Citation(evidence_id='conflict_source')]
        first.answer='Nguồn xung đột. [conflict_source]'
        second=self.response('2021-01-01',status=Stop.INSUFFICIENT_EVIDENCE)
        r=combine_period_answers(req,periods,[first,second])
        self.assertEqual(r.status,Stop.CONFLICTING_EVIDENCE)
        self.assertEqual(r.citations[0].evidence_id,'conflict_source')
    def pipeline(self):
        pipe=OnlinePipeline.__new__(OnlinePipeline);pipe.store=self.store()
        pipe.cfg=NS(request_timeout_seconds=180,corpus_snapshot_as_of='2026-09-15',allow_partial=True,
            trace_dir='unused',retrieval=NS(request_cache_enabled=True))
        pipe._ask=Mock(side_effect=lambda req,**kw:self.response(req.query_date,req.query_date))
        return pipe
    @patch('vn_labor_online.pipeline.persist')
    def test_pipeline_reuses_existing_checked_path_for_each_period(self,_):
        pipe=self.pipeline();result=pipe.ask(QueryRequest(question=QUERY))
        self.assertEqual(pipe._ask.call_count,2)
        self.assertEqual([(call.args[0].query_date,call.kwargs['period_end']) for call in pipe._ask.call_args_list],
                         [('2020-12-20','2020-12-31'),('2021-01-01','2021-01-10')])
        self.assertEqual(len(result.claims),2)
    @patch('vn_labor_online.pipeline.persist')
    def test_cancellation_is_not_swallowed_to_finish_other_periods(self,_):
        pipe=self.pipeline();pipe._ask.side_effect=RequestStopped('REQUEST_CANCELLED')
        with self.assertRaises(RequestStopped):pipe.ask(QueryRequest(question=QUERY))
        self.assertEqual(pipe._ask.call_count,1)

if __name__=='__main__':unittest.main()
