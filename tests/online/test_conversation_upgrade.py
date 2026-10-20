from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
import threading

from pydantic import ValidationError
from vn_labor_online.analysis import analyze, intake, plan_evidence
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig, OnlineConfig, ResearcherConfig, load_config
from vn_labor_online.conversation import resolve_context
from vn_labor_online.models import QueryRequest, Evidence, Route, Stop, Trace, AnswerResponse
from vn_labor_online.models import AnswerTask, Claim
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_online.providers import OllamaProvider, GeminiProvider
from vn_labor_online.researcher import LegalResearcher
from vn_labor_online.runtime import RequestBudget, RequestRegistry, RequestStopped, checkpoint, request_budget


def question(text, history=()):
    return QueryRequest(question=text, conversation_turns=[{'turn_id':str(i),'content':t} for i,t in enumerate(history)])


class ContextTests(TestCase):
    def test_short_typed_history_does_not_break_independent_lookup(self):
        text='Điều 1 Nghị định 145/2020/NĐ-CP quy định gì? Hãy trình bày đầy đủ phạm vi điều chỉnh và dẫn nguồn chính thức.'
        result=resolve_context(question(text,['f','?',' \n']))
        self.assertEqual(result.query,text)
        self.assertFalse(result.used_turns)
        self.assertIsNone(result.clarification)

    def test_short_legacy_history_does_not_break_independent_lookup(self):
        request=QueryRequest(question='Điều 1 Nghị định 145/2020/NĐ-CP quy định gì?',conversation_context=['f','',' \n','a\u0301'])
        self.assertEqual(resolve_context(request).query,request.question)

    def test_short_history_does_not_erase_valid_followup_context(self):
        result=resolve_context(question('Còn thời gian thử việc tối đa?', ['Tôi đang thử việc.','f',' \n']))
        self.assertIn('thử việc',result.query)
        self.assertEqual(result.used_turns,['0'])
        self.assertEqual(result.facts['contract_type'],'PROBATION')

    def test_only_noise_history_cannot_invent_a_followup_topic(self):
        result=resolve_context(question('Còn bao lâu?', ['f','?']))
        self.assertTrue(result.clarification)
        self.assertFalse(result.facts)
        self.assertFalse(result.used_turns)

    def test_internal_analyzer_does_not_build_invalid_tasks_for_short_text(self):
        for text in ('f','',' \n','a\u0301'):
            with self.subTest(text=text):
                self.assertEqual(analyze(intake(text,[])).answer_tasks,[])

    def test_current_question_is_validated_after_normalization(self):
        for text in (' f ',' \n','a\u0301'):
            with self.subTest(text=text),self.assertRaises(ValidationError):
                QueryRequest(question=text)
        exact='  Người lao động được nghỉ phép bao lâu?  '
        self.assertEqual(QueryRequest(question=exact).question,exact)

    def test_followup_resolves_without_assistant_facts(self):
        req=question('thử bao lâu thì được lên chính thức', ['Tôi đang thử việc ở công ty sản xuất thực phẩm.'])
        resolved=resolve_context(req)
        analysis=analyze(intake(resolved.query,[],resolved.query_date,resolved.facts),resolved.query_date,resolved.facts)
        self.assertEqual(analysis.legal_subissues,['CONTRACT.PROBATION_DURATION','CONTRACT.PROBATION_END'])
        self.assertIn('probation_end',plan_evidence(analysis).slot_requirements)
        self.assertTrue(resolved.used_turns)
        for fact in resolved.provenance:
            text=req.conversation_turns[int(fact['turn_id'])].content
            self.assertEqual(text[fact['char_start']:fact['char_end']],fact['source_quote'])

    def test_unknown_followup_asks_before_any_model(self):
        pipe=OnlinePipeline.__new__(OnlinePipeline)
        with TemporaryDirectory() as folder:
            pipe.cfg=OnlineConfig(artifact_source=folder,trace_dir=folder)
            pipe.store=SimpleNamespace(report=SimpleNamespace(build_id='build'))
            pipe._ask=Mock(side_effect=AssertionError('must not retrieve'))
            result=pipe.ask(question('Còn bao lâu thì được?'))
            self.assertEqual(result.status,Stop.NEED_MORE_FACTS)
            self.assertEqual(result.trace.events[0]['model_calls'],0)

    def test_new_topic_does_not_reuse_probation(self):
        result=resolve_context(question('Tôi làm việc đủ 12 tháng thì được nghỉ phép bao nhiêu ngày?', ['Tôi đang thử việc.']))
        self.assertFalse(result.used_turns)
        self.assertNotIn('PROBATION',result.facts.values())

    def test_probation_wage_is_related_and_preserves_topic_for_next_turn(self):
        result=resolve_context(question('Còn lương bao nhiêu?', ['Tôi đang thử việc.']))
        self.assertIn('thử việc',result.query)
        a=analyze(intake(result.query,[],facts=result.facts),supplied_facts=result.facts)
        self.assertIn('CONTRACT.PROBATION_PAY',a.legal_subissues)
        later=resolve_context(question('Còn thời gian tối đa?', ['Tôi đang thử việc.','Còn lương bao nhiêu?']))
        self.assertIn('thử việc',later.query)

    def test_job_fact_reply_resumes_tasks_without_old_numbers(self):
        result=resolve_context(question('Tôi làm công việc yêu cầu trình độ cao đẳng.',
          ['Tôi đang thử việc. Thời gian thử việc tối đa là bao lâu và kết thúc thì có lên chính thức không?']))
        a=analyze(intake(result.query,[],facts=result.facts),supplied_facts=result.facts)
        self.assertIn('CONTRACT.PROBATION_DURATION',a.legal_subissues)
        self.assertIn('CONTRACT.PROBATION_END',a.legal_subissues)
        self.assertEqual(a.facts['probation_work_group'],'COLLEGE')

    def test_actor_switch_does_not_inherit_employee_notice(self):
        result=resolve_context(question('Còn công ty đơn phương chấm dứt hợp đồng thì sao?',
          ['Tôi muốn nghỉ việc và báo trước 20 ngày.']))
        self.assertFalse(result.used_turns)

    def test_cross_subject_followup_clarifies_rather_than_losing_contract_context(self):
        result=resolve_context(question('Còn tôi muốn nghỉ ngay thì sao?', ['Tôi đang thử việc.']))
        self.assertIsNotNone(result.clarification)

    def test_explicit_new_case_and_hypothetical_do_not_inherit(self):
        for text in ('Giả sử công ty khác cho tôi nghỉ thì sao?', 'Tình huống mới: tôi bị sa thải.'):
            self.assertFalse(resolve_context(question(text,['Tôi muốn nghỉ việc và báo trước 20 ngày.'])).used_turns)
        self.assertFalse(resolve_context(question('Còn bao lâu?', ['Giả sử tôi đang thử việc.'])).used_turns)

    def test_new_explicit_date_overrides_prior_date(self):
        result=resolve_context(question('Còn thời gian thử việc vào ngày 15/12/2020?', ['Tôi đang thử việc ngày 15/12/2026.']))
        self.assertEqual(result.query_date,'2020-12-15')

    def test_historical_probation_end_has_dated_locators(self):
        a=analyze(intake('Kết thúc thử việc thì có lên chính thức không?',[]),'2020-12-15')
        locators=plan_evidence(a).slot_requirements['probation_end']
        self.assertEqual({loc.article for group in locators for loc in group},{'29'})
        self.assertTrue(all('10/2012/QH13' in loc.documents for group in locators for loc in group))

    def test_assistant_turn_cannot_become_user_fact(self):
        with self.assertRaises(ValidationError):
            QueryRequest(question='Còn bao lâu?',conversation_turns=[{'turn_id':'x','role':'assistant','content':'Bạn đã làm 10 năm.'}])

    def test_provenance_offsets_refer_to_original_turn_not_collapsed_whitespace(self):
        text='Tôi đang thử việc.\n\nTôi muốn nghỉ việc và báo   trước 20 ngày.'
        result=resolve_context(question('Còn thời gian thử việc?', [text]))
        for fact in result.provenance:
            self.assertEqual(text[fact['char_start']:fact['char_end']],fact['source_quote'])

    def test_correction_overrides_old_user_fact(self):
        result=resolve_context(question('Tôi chỉ báo trước 30 ngày.', ['Tôi ký hợp đồng không xác định thời hạn và muốn nghỉ việc, báo trước 20 ngày.']))
        self.assertEqual(result.facts.get('notice_days'),30)
        self.assertNotIn('notice_days',{p['field'] for p in result.provenance})


class RuntimeTests(TestCase):
    def test_missing_prerequisite_keeps_only_independent_claims(self):
        from vn_labor_online.answer_review import Review,validate_review
        evidence=SimpleNamespace(evidence_id='e',full_text='The source contains a sufficiently long quotation with supporting context for the independently checked claim.',text='The source contains a sufficiently long quotation with supporting context for the independently checked claim.')
        claims=[Claim(claim_id=k,text='The independently checked claim.',evidence_ids=['e']) for k in ('independent','dependent')]
        tasks=[AnswerTask(task_id='basis',request_quote='q1',description='basis',retrieval_query='q1'),
          AnswerTask(task_id='apply',request_quote='q2',description='application',retrieval_query='q2',depends_on=['basis']),
          AnswerTask(task_id='general',request_quote='q3',description='general rule',retrieval_query='q3')]
        review=Review(claims=[{'claim_id':c.claim_id,'verdict':'SUPPORTED','grounding':[{'evidence_id':'e','quote':evidence.text}],'reason':'supported'} for c in claims],
          coverage=[{'task_id':'basis','status':'MISSING','claim_ids':[],'missing':'Unknown prerequisite'},
            {'task_id':'apply','status':'ANSWERED','claim_ids':['dependent'],'missing':''},
            {'task_id':'general','status':'ANSWERED','claim_ids':['independent'],'missing':''}],
          question_fully_addressed=False,missing_requirements=['Unknown prerequisite'])
        with patch('vn_labor_online.answer_review.hard_issues',return_value=[]):
            supported=validate_review(review,SimpleNamespace(claims=claims),SimpleNamespace(evidence=[evidence]),tasks)
        self.assertEqual(supported,{'independent'})
        self.assertEqual(review.coverage[1].status,'PARTIAL')
        self.assertFalse(review.question_fully_addressed)

    def test_deadline_and_nested_budget_share_parent(self):
        with self.assertRaises(RequestStopped),request_budget(10) as outer:
            with request_budget(100) as inner:
                self.assertIs(inner,outer)
                inner.started-=11
                with self.assertRaises(RequestStopped): checkpoint()
            # Context manager exit also refuses a late result.

    def test_cancelled_request_stops_before_network(self):
        budget=RequestBudget(10); budget.cancelled.set()
        with self.assertRaises(RequestStopped),request_budget(10,budget):
            raise AssertionError('cannot enter cancelled work')

    def test_provider_timeout_is_bounded_by_remaining_budget(self):
        provider=OllamaProvider(timeout=300)
        response=Mock(status_code=200); response.json.return_value={'ok':True}
        provider.__dict__['client']=Mock(); provider.client.post.return_value=response
        with request_budget(2): provider._post({}, {})
        self.assertLessEqual(provider.client.post.call_args.kwargs['timeout'],2)

    def test_registry_deduplicates_and_isolates_capabilities(self):
        registry=RequestRegistry(limit=2)
        status,entry=registry.begin(('session1','m1'),'a',10)
        self.assertEqual(status,'NEW')
        self.assertEqual(registry.begin(('session1','m1'),'a',10)[0],'RUNNING')
        self.assertEqual(registry.begin(('session1','m1'),'b',10)[0],'CONFLICT')
        self.assertIsNone(registry.get(('session2','m1')))
        registry.finish(('session1','m1'),{'answer':'x'})
        self.assertEqual(registry.begin(('session1','m1'),'a',10)[0],'DONE')

    def test_partial_applicability_batch_survives_later_failure(self):
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid',max_items=1,max_batches=2))
        items=[Evidence(unit_id=k,retrieval_method='bm25',text='quoted source') for k in ('first','second')]
        auditor._deterministic=Mock(return_value=([],[],[]))
        auditor.provider=Mock()
        auditor.provider.structured.side_effect=[{'decisions':{'first':{'relevant':True,'supports_claim':True,
          'conditions_status':'NOT_APPLICABLE','exception_status':'NOT_APPLICABLE'}}},RuntimeError('provider failed')]
        accepted,decisions,warnings=auditor.audit(items,'Tra cứu',[],{})
        self.assertEqual([item.unit_id for item in accepted],['first'])
        self.assertEqual(decisions[1].audit_status,'UNRESOLVED')

    def test_gemini_missing_key_falls_back_without_inventing_facts(self):
        researcher=LegalResearcher(ResearcherConfig(mode='gemini',model='evaluated-model'))
        a=analyze(intake('Quy định về lao động?',[]))
        updated,warnings=researcher.enrich(a,a.query_text,[])
        self.assertEqual(updated,a)
        self.assertTrue(warnings)

    def test_gemini_sdk_schema_and_scoped_timeout(self):
        try: from google.genai import types
        except ImportError: self.skipTest('Optional google-genai SDK is not installed')
        # Validate real SDK types rather than mocking unsupported options.
        config=types.GenerateContentConfig(response_json_schema={'type':'object'},response_mime_type='application/json')
        self.assertEqual(config.response_mime_type,'application/json')
        sdk=Mock(); sdk.__enter__=Mock(return_value=sdk); sdk.__exit__=Mock(return_value=False)
        sdk.models.generate_content.return_value=SimpleNamespace(text='{"legal_issues":[]}')
        with patch('google.genai.Client',return_value=sdk) as factory,request_budget(2):
            result=GeminiProvider('evaluated-model','test-key',30).structured('system','user',{'type':'object'})
        self.assertEqual(result,{'legal_issues':[]})
        self.assertLessEqual(factory.call_args.kwargs['http_options'].timeout,2000)


class RequestApiTests(TestCase):
    def test_cancel_reaches_running_request_and_deadline_is_structured(self):
        from fastapi.testclient import TestClient
        from vn_labor_online.api import create_app
        entered=threading.Event(); release=threading.Event()
        def running(_):
            entered.set()
            if not release.wait(5): raise AssertionError('test did not release model')
            checkpoint()
        pipeline=Mock(); pipeline.cfg=OnlineConfig(artifact_source='test'); pipeline.ask.side_effect=running
        with patch('vn_labor_online.api.OnlinePipeline',return_value=pipeline),patch('vn_labor_online.api.load_config'),patch.dict('os.environ',{'VN_LABOR_API_KEY':''}):
            with TestClient(create_app()) as client:
                headers={'X-Client-Session':'a'*64}
                body={'question':'Câu hỏi kiểm tra','message_id':'m'}
                responses=[]
                worker=threading.Thread(target=lambda:responses.append(client.post('/v1/answer',json=body,headers=headers)))
                worker.start()
                try:
                    self.assertTrue(entered.wait(3))
                    self.assertEqual(client.get('/v1/requests/m',headers=headers).json()['state'],'RUNNING')
                    self.assertEqual(client.post('/v1/answer',json=body,headers=headers).status_code,429)
                    self.assertEqual(client.post('/v1/requests/m/cancel',headers={'X-Client-Session':'b'*64}).status_code,404)
                    self.assertTrue(client.post('/v1/requests/m/cancel',headers=headers).json()['cancel_requested'])
                finally:
                    release.set(); worker.join(5)
                self.assertEqual(responses[0].status_code,409)
                self.assertEqual(responses[0].json()['category'],'CANCELLED')
                pipeline.ask.side_effect=RequestStopped('REQUEST_DEADLINE_EXCEEDED')
                response=client.post('/v1/answer',json={**body,'message_id':'timeout'},headers=headers)
                self.assertEqual(response.status_code,504)
                self.assertEqual(response.json()['category'],'TIMEOUT')

    def test_idempotency_progress_ownership_and_conflict(self):
        from fastapi.testclient import TestClient
        from vn_labor_online.api import create_app
        trace=Trace(trace_id='t',query_id='q',build_id='b',route=Route.STANDARD,route_reason='test')
        result=AnswerResponse(query_id='q',status=Stop.NEED_MORE_FACTS,answer='Bổ sung dữ kiện',
          evidence_status='NOT_RETRIEVED',build_id='b',trace_id='t',trace=trace)
        pipeline=Mock(); pipeline.cfg=OnlineConfig(artifact_source='test'); pipeline.ask.return_value=result
        with patch('vn_labor_online.api.OnlinePipeline',return_value=pipeline),patch('vn_labor_online.api.load_config'),patch.dict('os.environ',{'VN_LABOR_API_KEY':''}):
            with TestClient(create_app()) as client:
                body={'question':'Câu hỏi kiểm tra','conversation_id':'c','message_id':'m'}
                headers={'X-Client-Session':'a'*64}
                first=client.post('/v1/answer',json=body,headers=headers)
                self.assertEqual(first.status_code,200,first.text)
                self.assertEqual(client.post('/v1/answer',json=body,headers=headers).status_code,200)
                self.assertEqual(pipeline.ask.call_count,1)
                self.assertEqual(client.get('/v1/requests/m',headers=headers).json()['state'],'DONE')
                self.assertEqual(client.get('/v1/requests/m',headers={'X-Client-Session':'b'*64}).status_code,404)
                self.assertEqual(client.post('/v1/answer',json={**body,'question':'Câu hỏi khác'},headers=headers).status_code,409)
                self.assertTrue(first.headers.get('X-Request-ID'))
