"""Regressions found by independently challenging the ONLINE upgrade."""
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from vn_labor_online.models import AnswerTask, Claim, AdjudicationDraft, QueryRequest
from vn_labor_online.answer_quality import clean_draft
from vn_labor_online.answer_review import _probation_amount_requirement, repair_required_computations
from vn_labor_online.numeric_answers import parse_salary_base, probation_minimum_amount, requests_probation_amount
from vn_labor_online.conversation import resolve_context
from vn_labor_online.config import OnlineConfig
from vn_labor_online.runtime import request_budget, retrieval_cache_summary, RequestStopped
from vn_labor_online.retrieval import request_cached_retrieval
from vn_labor_online.deployment import source_fingerprint,config_fingerprint
from vn_labor_online.analysis import analyze,intake
from .test_upgrade_regressions import _probation_pack


class NumericTaskScopeTests(unittest.TestCase):
    def setUp(self):
        self.question='Mức lương công việc là 8 triệu đồng/tháng. Lương thử việc thấp nhất bao nhiêu? Tôi được nghỉ phép năm bao nhiêu ngày?'
        self.pack=_probation_pack(self.question)

    def test_unrelated_task_does_not_require_probation_amount(self):
        task=AnswerTask(task_id='leave',request_quote='Tôi được nghỉ phép năm bao nhiêu ngày?',
            description='Số ngày nghỉ phép năm',retrieval_query='nghỉ hằng năm')
        self.assertIsNone(_probation_amount_requirement(task,self.pack))
        draft=AdjudicationDraft(answer_summary='Nội dung độc lập',claims=[],applicable_law_versions=[])
        self.assertEqual(repair_required_computations(draft,self.pack,[task]),draft)
        # Deterministic decomposition often repeats the whole original query
        # in request_quote for every task; that is not a scope signal.
        task.request_quote=self.question
        self.assertIsNone(_probation_amount_requirement(task,self.pack))

    def test_mixed_rate_and_money_request_keeps_monetary_requirement(self):
        q='Mức lương công việc là 12 triệu đồng/tháng. Lương thử việc ít nhất bao nhiêu phần trăm và tương ứng bao nhiêu tiền?'
        task=AnswerTask(task_id='pay',request_quote=q,description='Tiền thử việc',retrieval_query='lương thử việc')
        self.assertTrue(requests_probation_amount(q))
        self.assertEqual(_probation_amount_requirement(task,_probation_pack(q))[0],'10.200.000 đồng/tháng')

    def test_multiple_conflicting_salary_bases_are_not_resolved_by_first_match(self):
        q='Lương công việc là 8 triệu đồng/tháng. Lương công việc là 10 triệu đồng/tháng. Lương thử việc thấp nhất bao nhiêu?'
        self.assertIsNone(parse_salary_base(q))
        self.assertIsNone(probation_minimum_amount(q,salary_base_amount=8000000,salary_base_unit='tháng'))
        self.assertTrue(any('mức lương công việc khác nhau' in question for question in analyze(intake(q,[])).missing_facts))

    def test_explicit_money_question_without_base_asks_but_general_rate_question_does_not(self):
        result=analyze(intake('Tiền lương thử việc thấp nhất là bao nhiêu tiền?',[]))
        self.assertTrue(any('căn cứ tính' in question for question in result.missing_facts))
        result=analyze(intake('Tiền lương thử việc thấp nhất bằng bao nhiêu phần trăm?',[]))
        self.assertFalse(any('căn cứ tính' in question for question in result.missing_facts))

    def test_zero_salary_is_not_a_valid_computation_base(self):
        self.assertIsNone(parse_salary_base('Lương công việc là 0 đồng/tháng.'))

    def test_unrelated_source_with_same_article_number_and_percent_is_not_a_wage_rule(self):
        q='Lương công việc là 8 triệu đồng/tháng. Lương thử việc thấp nhất bao nhiêu?'
        p=_probation_pack(q,'Tiền đóng góp ít nhất bằng 85% kinh phí công việc.')
        task=AnswerTask(task_id='pay',request_quote=q,description=q,retrieval_query=q)
        self.assertIsNone(_probation_amount_requirement(task,p))


class ConservativeDedupTests(unittest.TestCase):
    def retained(self,texts):
        draft=AdjudicationDraft(answer_summary='\n'.join(texts),claims=[Claim(
            claim_id=str(i),text=text,evidence_ids=['shared']) for i,text in enumerate(texts)],applicable_law_versions=[])
        return clean_draft(draft,'Thời hạn báo trước là bao lâu?').claims

    def test_different_conditions_with_shared_source_are_preserved(self):
        base='Người lao động làm hợp đồng không xác định thời hạn phải báo trước 45 ngày '
        for tails in [('nếu công ty đã thanh toán lương.','nếu công ty chưa thanh toán lương.'),
                      ('trừ trường hợp A.','trừ trường hợp B.')]:
            with self.subTest(tails=tails):
                self.assertEqual(len(self.retained([base+t for t in tails])),2)

    def test_minimum_and_maximum_are_not_equivalent(self):
        base='Người lao động làm hợp đồng không xác định thời hạn phải báo trước '
        self.assertEqual(len(self.retained([base+'ít nhất 45 ngày.',base+'tối đa 45 ngày.'])),2)


class ConfirmationTests(unittest.TestCase):
    def request(self,current):
        return QueryRequest(question=current,conversation_turns=[
            {'turn_id':'a','role':'user','content':'Tôi làm hợp đồng không xác định thời hạn và muốn nghỉ việc.'},
            {'turn_id':'b','role':'user','content':'Còn hợp đồng của tôi là xác định thời hạn 12 tháng.'}])

    def test_explicit_confirmation_resolves_either_conflicting_value(self):
        for contract in ('không xác định thời hạn','xác định thời hạn 12 tháng'):
            with self.subTest(contract=contract):
                result=resolve_context(self.request(f'Tôi xác nhận hợp đồng của tôi là {contract}. Tôi muốn nghỉ việc thì cần báo trước bao lâu?'))
                self.assertIsNone(result.clarification)
                self.assertFalse(any(p.get('status')=='CONFLICT' for p in result.provenance))
                self.assertTrue(any(p['turn_id']=='current_request' for p in result.provenance))
                if contract=='không xác định thời hạn':
                    self.assertNotIn('contract_duration_months',result.facts)

    def test_unconfirmed_conflict_still_asks(self):
        self.assertTrue(resolve_context(self.request('Vậy tôi cần báo trước bao lâu?')).clarification)


class RequestCacheTests(unittest.TestCase):
    def retriever(self):
        class FakeRetriever:
            def __init__(self):
                self.cfg=OnlineConfig(artifact_source='fixture')
                self.cfg.retrieval.request_cache_enabled=True
                self.store=SimpleNamespace(units=[],nodes=[],edges=[])
                self.calls=0
            @request_cached_retrieval
            def bm25(self,query,k=None):
                self.calls+=1
                if query=='error':raise ValueError('synthetic')
                return [{'nested':{'value':self.calls}}]
        return FakeRetriever()

    def test_reuse_is_isolated_from_mutation_and_next_request(self):
        r=self.retriever()
        with request_budget(10) as budget:
            r.bm25('same')[0]['nested']['value']=999
            self.assertEqual(r.bm25('same')[0]['nested']['value'],1)
            self.assertEqual(retrieval_cache_summary()['hits'],1)
        self.assertFalse(budget.retrieval_cache)
        with request_budget(10):r.bm25('same')
        self.assertEqual(r.calls,2)

    def test_different_k_and_changed_store_do_not_hit(self):
        r=self.retriever()
        with request_budget(10):
            r.bm25('same',1);r.bm25('same',2)
            r.store.units.append({'id':'new'})
            r.bm25('same',2)
        self.assertEqual(r.calls,3)

    def test_error_cancel_and_disabled_cache_are_not_bypassed(self):
        r=self.retriever()
        with request_budget(10) as budget:
            for _ in range(2):
                with self.assertRaises(ValueError):r.bm25('error')
            r.bm25('same');budget.cancelled.set()
            with self.assertRaises(RequestStopped):r.bm25('same')
            budget.cancelled.clear()
        self.assertEqual(r.calls,3)
        r.cfg.retrieval.request_cache_enabled=False
        with request_budget(10):r.bm25('same');r.bm25('same')
        self.assertEqual(r.calls,5)

    def test_cache_is_bounded_and_absent_outside_requests(self):
        r=self.retriever()
        r.bm25('same');r.bm25('same')
        self.assertEqual(r.calls,2)
        with request_budget(10) as budget:
            for i in range(40):r.bm25(str(i))
            self.assertLessEqual(len(budget.retrieval_cache),16)


class DeploymentIdentityTests(unittest.TestCase):
    def test_effective_settings_change_identity_but_secret_values_do_not(self):
        cfg=OnlineConfig(artifact_source='fixture')
        before=config_fingerprint(cfg)
        cfg.researcher.api_key='synthetic-one'
        self.assertEqual(config_fingerprint(cfg),before)
        cfg.graph.max_hops+=1
        self.assertNotEqual(config_fingerprint(cfg),before)

    def test_code_change_changes_identity_but_non_code_file_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'module.py').write_text('VALUE=1',encoding='utf-8')
            before=source_fingerprint(root)
            (root/'private.env').write_text('not read by the fingerprint',encoding='utf-8')
            self.assertEqual(source_fingerprint(root),before)
            (root/'module.py').write_text('VALUE=2',encoding='utf-8')
            self.assertNotEqual(source_fingerprint(root),before)
