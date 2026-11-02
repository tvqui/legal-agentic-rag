import json,unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace as NS
from vn_labor_online.analysis import analyze,intake
from vn_labor_online.models import QueryRequest,AnswerResponse,Trace,Route,Stop
from vn_labor_online.scope import mixed_scope_exclusions
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_online.researcher import LegalResearcher
from vn_labor_online.config import ResearcherConfig

class MixedScopeContractTests(unittest.TestCase):
    def test_independent_land_question_cannot_discard_labour_claim(self):
        q='Công ty giữ bằng bản chính của tôi. Thủ tục chuyển quyền sử dụng đất cần gì?'
        a=analyze(intake(q,[]))
        self.assertTrue(a.in_scope)
        self.assertEqual(a.scope_exclusions,['Thủ tục chuyển quyền sử dụng đất cần gì?'])
        self.assertIn(a.scope_exclusions[0],q)
    def test_pure_land_request_remains_out_of_scope(self):
        self.assertFalse(analyze(intake('Tôi xin giấy chứng nhận quyền sử dụng đất cần gì?',[])).in_scope)
    def test_crime_as_disciplinary_fact_is_not_excluded(self):
        q='Người lao động trộm cắp tại nơi làm việc, công ty có được xử lý kỷ luật lao động bằng sa thải không?'
        self.assertTrue(analyze(intake(q,[])).in_scope)
        self.assertFalse(mixed_scope_exclusions(q))
    def test_separate_passport_question_is_reported(self):
        q='Công ty trả lương trễ có đúng không? Và tôi cần đổi hộ chiếu ở đâu?'
        self.assertEqual(len(mixed_scope_exclusions(q)),1)
    def test_holding_a_workers_passport_is_a_labour_question(self):
        q='Công ty giữ bản chính hộ chiếu để buộc người lao động tiếp tục làm việc có được không?'
        self.assertFalse(mixed_scope_exclusions(q))
    def test_researcher_cannot_add_excluded_tasks_back_into_coverage(self):
        q='Công ty trả lương trễ. Thủ tục ly hôn làm thế nào?'
        a=analyze(intake(q,[]))
        researcher=LegalResearcher(ResearcherConfig(mode='gemini',model='fake',api_key='FAKE_UNIT_ONLY',adaptive=False))
        researcher.provider=Mock();researcher.provider.structured.return_value={'scope':'MIXED','scope_quote':q,
            'answer_tasks':[{'task_id':'divorce','request_quote':'Thủ tục ly hôn làm thế nào?',
                             'description':'Thủ tục ly hôn','retrieval_query':'Thủ tục ly hôn'}]}
        updated,_=researcher.enrich(a,q,[])
        self.assertNotIn('divorce',[t.task_id for t in updated.answer_tasks])
        self.assertTrue(updated.scope_exclusions)
    @patch('vn_labor_online.pipeline.persist')
    def test_public_answer_discloses_unanswered_domain_instead_of_claiming_complete(self,_):
        pipe=OnlinePipeline.__new__(OnlinePipeline)
        pipe.cfg=NS(request_timeout_seconds=180,corpus_snapshot_as_of='2026-09-15',allow_partial=True,
            trace_dir='unused',retrieval=NS(request_cache_enabled=True))
        pipe.store=NS(report=NS(legal_status='PROVISIONAL'))
        trace=Trace(trace_id='t',query_id='q',build_id='b',route=Route.STANDARD,route_reason='fixture')
        pipe._ask=Mock(return_value=AnswerResponse(query_id='q',trace_id='t',trace=trace,build_id='b',status=Stop.SUFFICIENT,
            answer='Phần lao động đã được kiểm tra.',evidence_status='SUFFICIENT'))
        response=pipe.ask(QueryRequest(question='Công ty trả lương trễ. Thủ tục ly hôn làm thế nào?'))
        self.assertEqual(response.status,Stop.PARTIAL_ALLOWED)
        self.assertIn('Thủ tục ly hôn',response.answer)
        self.assertIn('mixed_scope_unanswered_parts',response.limitations)

if __name__=='__main__':unittest.main()
