import json,unittest
from unittest.mock import Mock,patch
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.answer_quality import clean_source_excerpt,source_layout_issues
from vn_labor_online.compression import compress_evidence
from vn_labor_online.answer_review import compose_answer,review_answer
from vn_labor_online.config import AdjudicationConfig
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.termination_context import contract_continuation_facets
from tests.online.test_answer_composition import sample
from vn_labor_online.models import Evidence

class V9PipelinePreservationTests(unittest.TestCase):
    def test_contract_ordinals_resolve_mechanism_without_answers(self):
        for ordinal in ['hai','ba','2','3']:
            q='Sau hợp đồng xác định thời hạn thứ '+ordinal+', chuyển sang hợp đồng không xác định thời hạn thế nào?'
            a=analyze(intake(q,[],'2026-09-15'),'2026-09-15');p=plan_evidence(a)
            self.assertIn('RENEWAL_COUNT',contract_continuation_facets(q))
            self.assertIn('term_contract_renewal',p.slot_requirements)
            loc=p.slot_requirements['term_contract_renewal'][0][0]
            self.assertEqual((loc.article,loc.clause,loc.point),('20','2','c'))
            self.assertIn('renewal_exceptions',p.slot_requirements)
        self.assertFalse(contract_continuation_facets('Công thức tính lương theo sản phẩm thứ hai là gì?'))
    def test_formula_symbols_and_lines_survive_source_compression(self):
        raw='Tiền\nlương\n=\nMức\nlương\n*\nSố\ngiờ'
        item=Evidence(unit_id='s',text='display',source_text=raw,retrieval_method='fixture')
        clean=clean_source_excerpt(raw,'Công thức là gì?')
        self.assertIn('\n=\n',clean);self.assertIn('\n*\n',clean)
        self.assertEqual(compress_evidence(item,'Công thức là gì?'),raw)
        self.assertIn('SOURCE_FORMULA_LAYOUT_REQUIRES_REVIEW',source_layout_issues(raw))
        self.assertEqual(source_layout_issues('Tiền = mức lương × số giờ.'),[])
        self.assertEqual(item.source_text,raw)
    def test_bad_composed_claim_does_not_discard_independent_good_candidate(self):
        p,d=sample();good=d.claims[0].text
        provider=Mock();provider.structured.return_value={'claims':[
            {'text':good,'evidence_ids':['source']},
            {'text':'Theo Điều 999 văn bản TEST, được hưởng 99 ngày.','evidence_ids':['source']}]}
        result=compose_answer(provider,d,p)
        self.assertEqual([c.text for c in result.claims],[good])
        self.assertEqual(result.semantic_review,{'composition_rejected_claim_ids':['claim_002']})
    def test_pruned_candidate_still_requires_independent_review(self):
        p,d=sample();engine=LegalAdjudicator(AdjudicationConfig(mode='ollama'))
        engine._review_provider=Mock();engine._review_provider.structured.return_value={'claims':[
            {'text':d.claims[0].text,'evidence_ids':['source']},
            {'text':'Theo Điều 999, được hưởng 99 ngày.','evidence_ids':['source']}]}
        blocked=d.model_copy(update={'claims':[],'semantic_review':{'status':'FAIL'}})
        with patch.object(engine,'_generate_with_layout',return_value=(d,[])),patch(
                'vn_labor_online.answer_review.review_answer',return_value=(blocked,['ANSWER_QUALITY_BLOCKED'])) as check:
            result,warnings=engine.generate(p,True)
        check.assert_called_once();self.assertFalse(result.claims)
        self.assertIn('ANSWER_COMPOSITION_PARTIAL_CANDIDATE_FOR_REVIEW',warnings)
    def test_foreign_source_still_rejects_entire_composition(self):
        p,d=sample();provider=Mock();provider.structured.return_value={'claims':[
            {'text':d.claims[0].text,'evidence_ids':['source']},
            {'text':'Unsupported external evidence.','evidence_ids':['foreign']}]}
        with self.assertRaises(StructuredOutputError):compose_answer(provider,d,p)

if __name__=='__main__':unittest.main()
