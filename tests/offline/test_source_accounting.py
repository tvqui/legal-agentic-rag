import contextlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from vn_labor_offline.ai_requests import AIRequests
from vn_labor_offline.checklists import AI_CHECKLIST_SCHEMA
from vn_labor_offline.ai_enrichment import validate_structured


class SourceAccountingTests(unittest.TestCase):
    def request(self,root,provider,**settings):
        return AIRequests(provider,{'project_root':Path(root),'knowledge':{
            'ai_cache_dir':'cache','ai_source_accounting':True,**settings}},Path(root),'checklists')

    def model(self,modify=None):
        provider=Mock();provider.model='fixture';provider.timeout=1
        def generate(system,user,schema):
            value=json.loads(user);rows=value['source_excerpts']
            items=[{'type':'CONDITION','question':'Điều kiện '+r['id']+'?',
                    'source_text':r['id'],'fact_slots':[]} for r in rows]
            coverage={r['id']:{'status':'EXTRACTED','item_indexes':[i],'reason':'Có điều kiện trong nguồn.'}
                      for i,r in enumerate(rows)}
            result={'items':items,'source_coverage':coverage}
            if modify:modify(result,value)
            return result
        provider.structured.side_effect=generate
        return provider

    def run_generate(self,request,source='Quy định cụ thể. '*50):
        return request.generate('Extract rules.',{'source':source},AI_CHECKLIST_SCHEMA,'generic')

    def test_full_array_does_not_force_recursive_splitting(self):
        provider=self.model()
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            req=self.request(tmp,provider)
            rows,errors,planned=self.run_generate(req,'x'*800)
        self.assertEqual(provider.structured.call_count,1)
        self.assertEqual(len(rows[0]['data']['items']),4)
        self.assertEqual(planned,1);self.assertFalse(errors)

    def test_all_nonblank_source_characters_are_accounted_for_without_dropping_tail(self):
        source=('Nội dung và điều kiện.\n'*55)+'PHẦN CUỐI'
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            rows,errors,_=self.run_generate(self.request(tmp,self.model()),source)
        seen=set()
        for row in rows:
            offset=row['source_offset'];text=row['source']
            self.assertEqual(source[offset:offset+len(text)],text)
            seen.update(range(offset,offset+len(text)))
            for item in row['data']['items']:self.assertIn(item['source_text'],text)
        self.assertFalse(errors)
        self.assertTrue(all(i in seen for i,c in enumerate(source) if not c.isspace()))

    def test_explicit_more_continues_and_deduplicates_already_extracted_items(self):
        def modify(raw,value):
            uid=value['source_excerpts'][0]['id']
            if value['page']==0:raw['source_coverage'][uid]['status']='MORE'
            else:raw['items'][0]['question']='Điều kiện bổ sung?'
        model=self.model(modify)
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            rows,errors,_=self.run_generate(self.request(tmp,model),'Nguồn ngắn.')
            previous=model.structured.call_count
            resumed,again,_=self.run_generate(self.request(tmp,model),'Nguồn ngắn.')
        self.assertFalse(errors);self.assertFalse(again)
        self.assertEqual(len(rows[0]['data']['items']),2)
        self.assertEqual(model.structured.call_count,previous)
        self.assertEqual(rows,resumed)

    def test_repeated_more_without_progress_stops_and_stays_incomplete(self):
        def modify(raw,value):
            for row in raw['source_coverage'].values():row['status']='MORE'
        model=self.model(modify)
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            rows,errors,_=self.run_generate(self.request(tmp,model),'Nguồn ngắn.')
        self.assertEqual(model.structured.call_count,2)
        self.assertEqual(errors[0]['reason'],'AI_CONTINUATION_NO_PROGRESS')
        self.assertEqual(len(rows[0]['data']['items']),1)

    def test_unfinished_window_is_not_reported_complete_at_page_limit(self):
        def modify(raw,value):
            raw['items'][0]['question']=f"Mục mới {value['page']}?"
            for row in raw['source_coverage'].values():row['status']='MORE'
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            rows,errors,_=self.run_generate(self.request(tmp,self.model(modify),ai_continuation_pages=2),'Nguồn ngắn.')
        self.assertEqual(len(rows[0]['data']['items']),2)
        self.assertEqual(errors[0]['reason'],'AI_CONTINUATION_PAGE_LIMIT')

    def test_foreign_quote_id_cannot_become_grounded_text(self):
        def modify(raw,value):raw['items'][0]['source_text']='FOREIGN'
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            rows,errors,_=self.run_generate(self.request(tmp,self.model(modify)),'Nguồn ngắn.')
        self.assertFalse(rows);self.assertTrue(errors)

    def test_no_item_cannot_hide_an_extracted_item(self):
        def modify(raw,value):
            for row in raw['source_coverage'].values():row.update(status='NO_ITEM',item_indexes=[])
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            rows,errors,_=self.run_generate(self.request(tmp,self.model(modify)),'Nguồn ngắn.')
        self.assertFalse(rows);self.assertEqual(errors[0]['reason'],'AI_ACCOUNTING_UNASSIGNED_ITEM')

    def test_missing_coverage_entry_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            rows,errors,_=self.run_generate(self.request(tmp,self.model(lambda raw,value:raw.update(source_coverage={}))))
        self.assertFalse(rows);self.assertTrue(errors)

    def test_empty_extraction_is_not_accepted_as_complete(self):
        def modify(raw,value):
            raw['items']=[]
            for row in raw['source_coverage'].values():row['item_indexes']=[]
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            rows,errors,_=self.run_generate(self.request(tmp,self.model(modify)),'Nguồn ngắn.')
        self.assertFalse(rows);self.assertEqual(errors[0]['reason'],'AI_ACCOUNTING_EMPTY_EXTRACTION')

    def test_transport_failure_retains_previous_grounded_page_but_not_completion(self):
        model=self.model()
        original=model.structured.side_effect
        def request(*args):
            raw=original(*args);value=json.loads(args[1])
            if value['page']:raise TimeoutError('SECRET_MUST_NOT_BE_LOGGED')
            for row in raw['source_coverage'].values():row['status']='MORE'
            return raw
        model.structured.side_effect=request
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            rows,errors,_=self.run_generate(self.request(tmp,model),'Nguồn ngắn.')
            log=(Path(tmp)/'reports/offline_ai_requests.jsonl').read_text(encoding='utf-8')
        self.assertEqual(len(rows[0]['data']['items']),1)
        self.assertEqual(errors[0]['reason'],'AI_REQUEST_TIMEOUT')
        self.assertNotIn('SECRET_MUST_NOT_BE_LOGGED',log)

    def test_insufficient_remaining_request_budget_has_consistent_stop_reason(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            req=self.request(tmp,self.model(),ai_checklist_budget_seconds=.5)
            _,errors,_=self.run_generate(req,'Nguồn ngắn.')
        self.assertEqual(errors[0]['reason'],req.stop_reason)
        self.assertEqual(req.stop_reason,'AI_STAGE_BUDGET_EXHAUSTED')

    def test_boolean_cannot_be_used_as_integer_index(self):
        with self.assertRaises(ValueError):validate_structured(True,{'type':'integer','minimum':0})

    def test_valid_no_relevant_item_is_accounted_without_inventing_a_rule(self):
        def modify(raw,value):
            raw['items']=[]
            for row in raw['source_coverage'].values():row.update(status='NO_ITEM',item_indexes=[],reason='Chỉ có tiêu đề.')
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            rows,errors,planned=self.run_generate(self.request(tmp,self.model(modify)),'Tiêu đề')
        self.assertFalse(errors);self.assertEqual(planned,len(rows));self.assertFalse(rows[0]['data']['items'])

    def test_inconsistent_cached_ledger_can_be_retried_after_fix(self):
        model=self.model(lambda raw,value:raw['source_coverage'][value['source_excerpts'][0]['id']].update(item_indexes=[]))
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            _,errors,_=self.run_generate(self.request(tmp,model),'Nguồn ngắn.')
            self.assertTrue(errors)
            model.structured.side_effect=self.model().structured.side_effect
            rows,errors,_=self.run_generate(self.request(tmp,model),'Nguồn ngắn.')
        self.assertFalse(errors);self.assertTrue(rows);self.assertEqual(model.structured.call_count,2)

    def test_invalid_window_settings_fail_before_calling_model(self):
        model=self.model()
        with tempfile.TemporaryDirectory() as tmp:
            for values in [{'ai_anchor_chars':0},{'ai_accounting_window':True},{'ai_continuation_pages':99}]:
                with self.assertRaises(ValueError):self.run_generate(self.request(tmp,model,**values))
        model.structured.assert_not_called()

    def test_task_context_overflow_does_not_falsely_open_provider_outage_circuit(self):
        from vn_labor_online.errors import StructuredOutputError
        model=self.model();model.structured.side_effect=StructuredOutputError('PROMPT_CONTEXT_BUDGET_EXCEEDED')
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            req=self.request(tmp,model,ai_max_consecutive_failures=1)
            rows,errors,_=self.run_generate(req,'Nguồn ngắn.')
        self.assertFalse(rows);self.assertEqual(errors[0]['reason'],'AI_CONTEXT_BUDGET_EXCEEDED')
        self.assertIsNone(req.stop_reason)
