import unittest
from unittest.mock import Mock,patch
from vn_labor_online.runtime import RequestBudget,request_budget,request_timeout,OperationBudgetExceeded
from vn_labor_online.models import EvidenceState,VerifiedEvidencePack,VerifiedEvidenceItem
from vn_labor_online.config import AdjudicationConfig
from vn_labor_online.generation import LegalAdjudicator

class Clock:
    def __init__(self):self.now=0
    def __call__(self):return self.now

class AdjudicationTimeReserveTests(unittest.TestCase):
    def engine(self,**kwargs):
        engine=LegalAdjudicator(AdjudicationConfig(mode='ollama',**kwargs))
        engine.provider=Mock();return engine
    def test_primary_call_preserves_configured_review_time(self):
        clock=Clock();engine=self.engine();observed=[]
        engine.provider.structured.side_effect=lambda *args:observed.append(request_timeout(120)) or {'claims':[]}
        with patch('vn_labor_online.runtime.time.monotonic',clock),request_budget(180,existing=RequestBudget(180,started=0)):
            clock.now=100;engine._primary_structured('s','u',{})
            self.assertEqual(observed,[35])
    def test_no_primary_budget_cannot_consume_the_reserved_reviewer_window(self):
        clock=Clock();engine=self.engine()
        with patch('vn_labor_online.runtime.time.monotonic',clock),request_budget(180,existing=RequestBudget(180,started=0)):
            clock.now=140
            with self.assertRaises(OperationBudgetExceeded):engine._primary_structured('s','u',{})
            engine.provider.structured.assert_not_called()
            self.assertEqual(request_timeout(45),40)
    def test_repeated_primary_and_language_calls_share_one_budget(self):
        clock=Clock();engine=self.engine(primary_budget_seconds=30)
        allowances=[]
        def call(*args):
            allowances.append(request_timeout(120));clock.now+=20;return {}
        engine.provider.structured.side_effect=call
        with patch('vn_labor_online.runtime.time.monotonic',clock),request_budget(180,existing=RequestBudget(180,started=0)):
            engine._primary_structured('s','u',{})
            with self.assertRaises(OperationBudgetExceeded):engine._primary_structured('s','u',{})
        self.assertEqual(allowances,[30,10])
    def test_ablation_without_review_does_not_reserve_an_unused_reviewer_window(self):
        clock=Clock();engine=self.engine(semantic_review=False);allowances=[]
        engine.provider.structured.side_effect=lambda *args:allowances.append(request_timeout(120)) or {}
        with patch('vn_labor_online.runtime.time.monotonic',clock),request_budget(180,existing=RequestBudget(180,started=0)):
            clock.now=150;engine._primary_structured('s','u',{})
        self.assertEqual(allowances,[30])
    def test_budget_fallback_still_requires_independent_semantic_review(self):
        clock=Clock();engine=self.engine();clock.now=140
        source='Bên giao tài liệu phải thông báo danh mục tài liệu trước khi bàn giao.'
        pack=VerifiedEvidencePack(query='Giải thích quy định bàn giao tài liệu.',evidence=[VerifiedEvidenceItem(evidence_id='e',text=source,full_text=source)],coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
        review=Mock();review.context_tokens=16384;review.max_output_tokens=2048;review.count_prompt_tokens=None
        review.structured.return_value={'claims':[{'claim_id':'claim_001','verdict':'SUPPORTED','grounding':[{'evidence_id':'e','quote':source}],'reason':'Khớp nguồn'}],
            'coverage':[{'task_id':'question','status':'ANSWERED','claim_ids':['claim_001'],'missing':''}],
            'question_fully_addressed':True,'missing_requirements':[]}
        engine._review_provider=review
        with patch('vn_labor_online.runtime.time.monotonic',clock),request_budget(180,existing=RequestBudget(180,started=0)):
            draft,warnings=engine.generate(pack,False)
        engine.provider.structured.assert_not_called()
        self.assertEqual(review.structured.call_count,1)
        self.assertEqual(draft.semantic_review['status'],'PASS')
        self.assertTrue(any('OperationBudgetExceeded' in w for w in warnings))

if __name__=='__main__':unittest.main()
