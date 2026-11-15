"""Reliability regressions with synthetic sources and bounded fake providers."""
import json,unittest,unicodedata
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.answer_review import review_answer,merge_repair_claims
from vn_labor_online.models import Claim,ProviderClaim,AdjudicationDraft,VerifiedEvidencePack,VerifiedEvidenceItem,EvidenceState,AnswerTask,ProviderClaims
from vn_labor_online.config import AdjudicationConfig
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.generation_context import generation_batches,encode_payload
from vn_labor_online.context_budget import fits_context
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.claim_validation import semantic_issues

class RewardAndSourceScopeTests(unittest.TestCase):
    def slots(self,q):return plan_evidence(analyze(intake(q,[],'2026-09-15'),'2026-09-15')).slot_requirements
    def test_normal_wage_is_not_bonus(self):
        for q in ['Căn cứ tính lương ban đêm trong ngày làm việc bình thường là gì?', 'Bồi thường dụng cụ bị hư hỏng căn cứ vào yếu tố nào?']:
            with self.subTest(q=q):self.assertNotIn('bonus_basis',self.slots(q))
    def test_real_bonus_and_explicit_unaccented_bonus_remain(self):
        for q in ['Tiền thưởng căn cứ vào yếu tố nào?',unicodedata.normalize('NFD','Quy chế thưởng căn cứ vào yếu tố nào?'),'Tien thuong dua tren yeu to nao?']:
            with self.subTest(q=q):self.assertIn('bonus_basis',self.slots(q))
    def test_property_damage_and_deduction_have_distinct_sources(self):
        p=self.slots('Người lao động sơ suất làm hỏng dụng cụ, phải bồi thường tối đa bao nhiêu và khấu trừ lương mỗi tháng bao nhiêu?')
        self.assertEqual(p['work_property_damage_rule'][0][0].article,'129')
        self.assertEqual(p['work_property_wage_deduction'][0][0].article,'102')
        self.assertNotIn('work_property_damage_rule',self.slots('Tôi phải bồi thường chi phí đào tạo cho công ty không?'))
    def test_conditional_ordinal_phrasing_cannot_reset_cap(self):
        source='Ký hợp đồng lao động mới thì chỉ được ký thêm 01 lần, sau đó phải ký hợp đồng lao động không xác định thời hạn.'
        for prefix in ['Trường hợp','Nếu','Sau khi']:
            bad=prefix+' hợp đồng xác định thời hạn thứ hai hết hạn, hai bên được ký kết thêm 01 lần nữa.'
            self.assertIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues(bad,[NS(text=source,full_text=source)]))

class RepairLedgerTests(unittest.TestCase):
    source='Bên giao phải lập biên bản. Bên nhận phải xác nhận việc bàn giao.'
    def fixture(self):
        a=Claim(claim_id='original',text='Bên giao phải lập biên bản.',evidence_ids=['s'])
        b=ProviderClaim(text='Bên nhận phải xác nhận việc bàn giao.',evidence_ids=['s'])
        draft=AdjudicationDraft(answer_summary='',claims=[a],applicable_law_versions=[])
        tasks=[AnswerTask(task_id=t,request_quote=t+'?',description=t,retrieval_query=t+'?') for t in ['one','two']]
        pack=VerifiedEvidencePack(query='Nghĩa vụ của từng bên?',requested_outcome='EXPLAIN',answer_tasks=tasks,evidence=[VerifiedEvidenceItem(evidence_id='s',text=self.source,full_text=self.source)],coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
        return draft,pack,b
    def verdict(self,ids,complete):
        return {'claims':[{'claim_id':cid,'verdict':'SUPPORTED','grounding':[{'evidence_id':'s','quote':self.source}],'reason':'Synthetic proof'} for cid in ids],
            'coverage':[{'task_id':'one','status':'ANSWERED','claim_ids':['original'],'missing':''},
                {'task_id':'two','status':'ANSWERED' if complete else 'MISSING','claim_ids':['claim_001'] if complete else [],'missing':'' if complete else 'Chưa trả lời nghĩa vụ bên nhận.'}],
            'question_fully_addressed':complete,'missing_requirements':[] if complete else ['Thiếu nghĩa vụ bên nhận.']}
    def test_repair_retains_supported_part_and_reaudits_whole_union(self):
        d,p,b=self.fixture();provider=Mock();provider.structured.side_effect=[self.verdict(['original'],False),{'claims':[b.model_dump()]},self.verdict(['original','claim_001'],True)]
        result,_=review_answer(provider,d,p,1)
        self.assertEqual([c.text for c in result.claims],[d.claims[0].text,b.text])
        self.assertEqual(result.semantic_review['status'],'PASS');self.assertEqual(provider.structured.call_count,3)
        last=json.loads(provider.structured.call_args_list[-1].args[1])
        self.assertEqual(len(last['claims']),2)
    def test_new_audit_failure_only_returns_prior_snapshot(self):
        d,p,b=self.fixture();provider=Mock();provider.structured.side_effect=[self.verdict(['original'],False),{'claims':[b.model_dump()]},TimeoutError()]
        result,_=review_answer(provider,d,p,1)
        self.assertEqual(result.claims,d.claims);self.assertEqual(result.semantic_review['status'],'PARTIAL')
    def test_exact_duplicate_is_removed_but_changed_meaning_gets_new_id(self):
        d,_,b=self.fixture();d.claims[0].claim_id='claim_001'
        same=ProviderClaim(text=d.claims[0].text,evidence_ids=['s'])
        result=merge_repair_claims(d,d.claims,[same,b])
        self.assertEqual([c.claim_id for c in result],['claim_001','claim_002'])
        self.assertEqual(result[0].text,d.claims[0].text)

class SourceContextTests(unittest.TestCase):
    def payload(self):return {'query':'Explain each duty.','required_evidence_groups':{'duty':[]},'evidence':[{'evidence_id':str(i),'text':'If risk is present then stop and report. '*22,'unknown':None} for i in range(3)]}
    def provider(self):return NS(context_tokens=2200,max_output_tokens=128)
    def test_whole_sources_survive_and_every_request_fits(self):
        payload=self.payload();batches=generation_batches(self.provider(),'system',payload)
        self.assertGreater(len(batches),1)
        self.assertEqual([(e['evidence_id'],e['text']) for b in batches for e in b['evidence']],[(e['evidence_id'],e['text']) for e in payload['evidence']])
        self.assertTrue(all(fits_context(self.provider(),'system',encode_payload(b)) for b in batches))
        self.assertTrue(all(b['required_evidence_groups']==payload['required_evidence_groups'] for b in batches))
        self.assertIn('unknown',payload['evidence'][0])
    def test_one_oversized_source_is_not_truncated(self):
        payload=self.payload();payload['evidence'][0]['text']='complete source '*1000
        with self.assertRaises(StructuredOutputError):generation_batches(self.provider(),'system',payload)
    def test_batch_limit_is_not_bypassed(self):
        with self.assertRaises(StructuredOutputError):generation_batches(self.provider(),'system',self.payload(),max_batches=1)
    def test_generation_batches_restrict_citations_and_keep_output_bound(self):
        engine=LegalAdjudicator(AdjudicationConfig(mode='deterministic',semantic_review=False));engine.provider=self.provider();seen=[]
        def draft(system,user,schema):
            body=json.loads(user);ids=[e['evidence_id'] for e in body['evidence']];seen.extend(ids)
            self.assertEqual(schema['$defs']['ProviderClaim']['properties']['evidence_ids']['items']['enum'],ids)
            return {'claims':[{'text':'A complete supported duty.','evidence_ids':[ids[0]]}]},[]
        engine._generation_structured=Mock(side_effect=draft)
        result,warnings=engine._bounded_generation_structured('system',self.payload(),ProviderClaims.model_json_schema())
        self.assertEqual(seen,['0','1','2']);self.assertEqual(len(result['claims']),3)
        self.assertIn('ADJUDICATION_CONTEXT_BATCHED',warnings)
    def test_source_batches_share_one_primary_time_budget(self):
        from vn_labor_online.runtime import request_timeout,OperationBudgetExceeded
        engine=LegalAdjudicator(AdjudicationConfig(mode='deterministic',semantic_review=False,primary_budget_seconds=1))
        engine.provider=self.provider();clock=[100.0];allowances=[]
        def structured(system,user,schema):
            allowances.append(request_timeout(100))
            clock[0]+=.6
            uid=json.loads(user)['evidence'][0]['evidence_id']
            return {'claims':[{'text':'A distinct duty.','evidence_ids':[uid]}]},[]
        engine._generation_structured=Mock(side_effect=structured)
        with patch('vn_labor_online.runtime.time.monotonic',side_effect=lambda:clock[0]):
            with self.assertRaises(OperationBudgetExceeded):
                engine._bounded_generation_structured('system',self.payload(),ProviderClaims.model_json_schema())
        self.assertEqual(len(allowances),2)
        self.assertAlmostEqual(allowances[0],1)
        self.assertAlmostEqual(allowances[1],.4)

    def test_batch_cannot_cite_a_source_from_another_batch(self):
        engine=LegalAdjudicator(AdjudicationConfig(mode='deterministic',semantic_review=False));engine.provider=self.provider()
        engine._generation_structured=Mock(return_value=({'claims':[{'text':'Unknown proof.','evidence_ids':['foreign']}]},[]))
        with self.assertRaises(StructuredOutputError):engine._bounded_generation_structured('system',self.payload(),ProviderClaims.model_json_schema())

if __name__=='__main__':unittest.main()
