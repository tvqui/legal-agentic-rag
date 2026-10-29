import json
import unittest
from unittest.mock import Mock
from vn_labor_online.analysis import analyze, intake, plan_evidence
from vn_labor_online.answer_review import Review, hard_issues, review_answer, validate_review
from vn_labor_online.compression import compress_evidence
from vn_labor_online.config import AdjudicationConfig, ApplicabilityConfig
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.evidence import build_verified_pack
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.models import (AdjudicationDraft, AnswerTask, Claim, Evidence,
    EvidenceState, VerifiedEvidenceItem, VerifiedEvidencePack)
from vn_labor_online.retrieval import as_evidence

def sample():
    text='Người lao động làm việc đủ 12 tháng được nghỉ 12 ngày làm việc trong điều kiện bình thường.'
    e=VerifiedEvidenceItem(evidence_id='source',instrument_number='45/2019/QH14',article='113',clause='1',point='a',text=text,full_text=text)
    state=EvidenceState(slots={},gaps=[],coverage=1)
    task=AnswerTask(task_id='entitlement',request_quote='nghỉ phép',description='Số ngày nghỉ',retrieval_query='nghỉ hằng năm')
    pack=VerifiedEvidencePack(query='Tôi hỏi nghỉ phép bao nhiêu ngày?',coverage_state=state,evidence=[e],answer_tasks=[task])
    claim=Claim(claim_id='claim',text='Nếu làm đủ 12 tháng trong điều kiện bình thường thì được nghỉ 12 ngày làm việc.',evidence_ids=['source'])
    draft=AdjudicationDraft(answer_summary='',claims=[claim],applicable_law_versions=[])
    verdict={'claims':[{'claim_id':'claim','verdict':'SUPPORTED','grounding':[{'evidence_id':'source','quote':text}], 'reason':'Entitlement and qualification match.'}],
        'coverage':[{'task_id':'entitlement','status':'ANSWERED','claim_ids':['claim'],'missing':''}],
        'question_fully_addressed':True,'missing_requirements':[]}
    return pack,draft,verdict

class SemanticAnswerReviewTests(unittest.TestCase):
    def test_verified_quotation_and_complete_claim_accounting(self):
        p,d,v=sample()
        self.assertEqual(validate_review(Review.model_validate(v),d,p,p.answer_tasks),{'claim'})

    def test_fabricated_quote_fails_even_if_model_says_supported(self):
        p,d,v=sample(); v['claims'][0]['grounding'][0]['quote']='Được nghỉ 99 ngày làm việc.'
        with self.assertRaises(StructuredOutputError): validate_review(Review.model_validate(v),d,p,p.answer_tasks)

    def test_cross_source_quote_cannot_support_a_different_citation(self):
        p,d,v=sample(); v['claims'][0]['grounding'][0]['evidence_id']='other'
        with self.assertRaises(StructuredOutputError): validate_review(Review.model_validate(v),d,p,p.answer_tasks)

    def test_omitted_claim_in_review_is_not_silently_passed(self):
        p,d,v=sample(); v['claims']=[]
        with self.assertRaises(StructuredOutputError): validate_review(Review.model_validate(v),d,p,p.answer_tasks)

    def test_duplicate_claim_verdict_is_rejected(self):
        p,d,v=sample(); v['claims']*=2
        with self.assertRaises(StructuredOutputError): validate_review(Review.model_validate(v),d,p,p.answer_tasks)

    def test_all_tasks_required_even_if_one_claim_is_supported(self):
        p,d,v=sample(); p.answer_tasks.append(AnswerTask(task_id='remedy',request_quote='nghỉ phép',description='Khắc phục',retrieval_query='khắc phục'))
        with self.assertRaises(StructuredOutputError): validate_review(Review.model_validate(v),d,p,p.answer_tasks)

    def test_completeness_cannot_rely_on_rejected_claim(self):
        p,d,v=sample(); v['claims'][0]['verdict']='UNSUPPORTED'
        with self.assertRaises(StructuredOutputError): validate_review(Review.model_validate(v),d,p,p.answer_tasks)

    def test_valid_review_json_cannot_support_late_wage_claim_omitting_exception(self):
        p,d,_=sample()
        question='Người lao động bị chậm trả lương có được nghỉ không cần báo trước không?'
        source=('Người lao động có quyền đơn phương chấm dứt hợp đồng lao động không cần báo trước '
            'nếu không được trả đủ lương hoặc trả lương không đúng thời hạn, trừ trường hợp quy định '
            'tại khoản 4 Điều 97 của Bộ luật này.')
        evidence=p.evidence[0].model_copy(update={
            'instrument_number':'18/VBHN-VPQH','article':'35','clause':'2','point':'b',
            'text':source,'full_text':source,
        })
        task=AnswerTask(task_id='entitlement',request_quote=question,
            description='Điều kiện nghỉ không báo trước',retrieval_query=question)
        p=p.model_copy(update={'query':question,'evidence':[evidence],'answer_tasks':[task]})
        claim=Claim(claim_id='claim',
            text='Người lao động được nghỉ không cần báo trước trong mọi trường hợp bị chậm trả lương.',
            evidence_ids=['source'])
        d=d.model_copy(update={'claims':[claim]})
        review={
            'claims':[{'claim_id':'claim','verdict':'SUPPORTED',
                'grounding':[{'evidence_id':'source','quote':source}],
                'reason':'Câu trả lời đã được căn cứ hỗ trợ.'}],
            'coverage':[{'task_id':'entitlement','status':'ANSWERED','claim_ids':['claim'],'missing':''}],
            'question_fully_addressed':True,'missing_requirements':[],
        }

        parsed=Review.model_validate(review)
        self.assertEqual(parsed.claims[0].verdict,'SUPPORTED')
        with self.assertRaises(StructuredOutputError):
            validate_review(parsed,d,p,p.answer_tasks)

    def test_false_completion_with_declared_missing_part_is_rejected(self):
        p,d,v=sample(); v['missing_requirements']=['Còn thiếu hậu quả']
        with self.assertRaises(StructuredOutputError): validate_review(Review.model_validate(v),d,p,p.answer_tasks)

    def test_independent_review_runs_after_a_deterministic_draft_in_model_mode(self):
        p,d,v=sample(); engine=LegalAdjudicator(AdjudicationConfig(mode='ollama'))
        engine.provider=Mock(); engine.provider.structured.return_value=v
        engine._generate_with_layout=Mock(return_value=(d,[]))
        result,warnings=engine.generate(p,False)
        self.assertEqual(result.semantic_review['status'],'PASS')
        self.assertEqual(engine.provider.structured.call_count,1)
        self.assertIn('[source]',result.answer_summary)

    def test_unavailable_auditor_does_not_return_unverified_fallback(self):
        p,d,v=sample(); provider=Mock(); provider.structured.side_effect=TimeoutError()
        result,warnings=review_answer(provider,d,p)
        self.assertFalse(result.claims); self.assertIn('ANSWER_QUALITY_BLOCKED',warnings)

    def test_repair_has_to_pass_a_new_review(self):
        p,d,v=sample(); bad=json.loads(json.dumps(v)); bad['claims'][0].update(verdict='UNSUPPORTED',grounding=[])
        bad['coverage'][0].update(status='MISSING',claim_ids=[],missing='Số ngày chưa có căn cứ')
        bad.update(question_fully_addressed=False,missing_requirements=['Số ngày'])
        repaired=json.loads(json.dumps(v)); repaired['claims'][0]['claim_id']='claim_001'; repaired['coverage'][0]['claim_ids']=['claim_001']
        provider=Mock(); provider.structured.side_effect=[bad,{'claims':[{'text':d.claims[0].text,'evidence_ids':['source']}]},repaired]
        result,warnings=review_answer(provider,d,p)
        self.assertEqual(provider.structured.call_count,3)
        self.assertEqual(result.semantic_review['status'],'PASS')

    def test_supported_partial_parts_are_not_called_complete(self):
        p,d,v=sample(); v.update(question_fully_addressed=False,missing_requirements=['Chưa có nguồn cho hậu quả'])
        provider=Mock(); provider.structured.return_value=v
        result,warnings=review_answer(provider,d,p,repair_attempts=0)
        self.assertTrue(result.claims); self.assertEqual(result.semantic_review['status'],'PARTIAL')
        self.assertIn('answer_coverage',result.limitations)

    def test_inherited_prohibition_is_not_a_permission(self):
        p,d,v=sample(); e=p.evidence[0].model_copy(update={'text':'Điều động người lao động vì tham gia đình công.',
            'full_text':'Các hành vi bị nghiêm cấm: Điều động người lao động vì tham gia đình công.'})
        claim=Claim(claim_id='bad',text='Công ty có thể điều động người lao động vì tham gia đình công.',evidence_ids=['source'])
        self.assertIn('INHERITED_PROHIBITION_LOST',hard_issues(claim,[e]))

    def test_stop_condition_is_not_a_lawful_strike_condition(self):
        p,d,v=sample(); e=p.evidence[0].model_copy(update={'full_text':'Các trường hợp hoãn, ngừng đình công: thiên tai, dịch bệnh.'})
        claim=Claim(claim_id='bad',text='Đình công được coi là hợp pháp nếu xuất hiện thiên tai.',evidence_ids=['source'])
        self.assertIn('STOP_CONDITION_INVERTED_TO_PERMISSION',hard_issues(claim,[e]))

    def test_full_context_preserves_negation_and_tail_exception(self):
        body='Nội dung dài về điều kiện công việc. '*80+'Trừ trường hợp pháp luật có quy định khác.'
        e=Evidence(unit_id='source',retrieval_method='bm25',text=body,source_text=body,
            ancestor_context='Các hành vi bị nghiêm cấm:')
        result=compress_evidence(e,'công việc',max_chars=80)
        self.assertIn('bị nghiêm cấm',result); self.assertTrue(result.endswith('quy định khác.'))
        self.assertGreater(len(result),80)

    def test_retrieval_keeps_parent_context_without_rewriting_raw_text(self):
        raw={'unit_id':'u','text':'Nội dung','ancestor_context':'Các hành vi bị nghiêm cấm'}
        item=as_evidence(raw,1,'bm25',1)
        self.assertEqual(item.ancestor_context,raw['ancestor_context'])
        self.assertEqual(item.text,raw['text'])

    def test_norm_explanation_does_not_require_case_facts(self):
        a=analyze(intake('Khi nào đơn phương chấm dứt hợp đồng lao động được coi là trái pháp luật?',[]))
        self.assertEqual(a.requested_outcome,'EXPLAIN'); self.assertFalse(a.missing_facts)

    def test_spelled_seniority_is_a_fact_not_a_dropped_qualifier(self):
        a=analyze(intake('NLĐ chưa thành niên làm cùng công ty sáu năm. Số ngày nghỉ tối thiểu là bao nhiêu?',[]))
        self.assertEqual(a.facts['service_years'],6); self.assertTrue(a.facts['minor'])
        self.assertIn('seniority_rule',plan_evidence(a).slot_requirements)

    def test_minimum_wage_requires_operative_rule_not_policy_factors(self):
        a=analyze(intake('Lương cơ bản thấp hơn lương tối thiểu nhưng phụ cấp cao thì có đủ không?',[]),explicit_date='2026-06-10')
        p=plan_evidence(a)
        self.assertEqual(p.slot_requirements['minimum_wage_operative_rule'][0][0].documents,['293/2025/NĐ-CP'])

    def test_minimum_wage_hints_change_with_date(self):
        for date,doc in [('2020-08-11','90/2019/NĐ-CP'),('2023-03-12','38/2022/NĐ-CP'),('2025-01-07','74/2024/NĐ-CP')]:
            a=analyze(intake('Lương theo công việc thấp hơn lương tối thiểu; áp dụng thế nào?',[]),explicit_date=date)
            self.assertEqual(plan_evidence(a).slot_requirements['minimum_wage_operative_rule'][0][0].documents,[doc])

    def test_training_contents_require_each_item_not_only_repayment(self):
        a=analyze(intake('Hợp đồng đào tạo nghề phải có những nội dung gì?',[]))
        groups=plan_evidence(a).slot_requirements['training_contract_contents']
        self.assertEqual([g[0].point for g in groups],['a','b','c','d','đ','e'])

    def test_discipline_forms_require_substance_not_article_title(self):
        a=analyze(intake('Các hình thức kỷ luật lao động là gì?',[]))
        self.assertEqual([g[0].clause for g in plan_evidence(a).slot_requirements['discipline_forms']],['1','2','3','4'])

    def test_health_insurance_cannot_be_replaced_by_employment_definition(self):
        a=analyze(intake('NLĐ thuộc diện nào phải tham gia BHYT thông qua quan hệ lao động?',[]),explicit_date='2026-02-11')
        self.assertIn('health_insurance_current_amendment',plan_evidence(a).slot_requirements)

    def test_all_eligible_candidates_are_assessed_in_bounded_batches(self):
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid',max_items=2,max_batches=3))
        items=[Evidence(unit_id=f'e{i}',retrieval_method='bm25',text='Quy định về lao động',verified=True) for i in range(5)]
        base=[{'evidence_id':x.unit_id,'relevant':True,'supports_claim':False,'audit_status':'UNRESOLVED'} for x in items]
        from vn_labor_online.models import ApplicabilityDecision
        auditor._deterministic=Mock(return_value=([],[ApplicabilityDecision(**x) for x in base],[]))
        def judge(system,payload,schema):
            ids=[x['evidence']['id'] for x in json.loads(payload)['candidates']]
            return {'decisions':{uid:{'relevant':True,'supports_claim':True,'conditions_status':'UNKNOWN','exception_status':'UNKNOWN'} for uid in ids}}
        auditor.provider=Mock(); auditor.provider.structured.side_effect=judge
        accepted,decisions,warnings=auditor.audit(items,'Giải thích quy định lao động',['GENERAL'],{},'EXPLAIN')
        self.assertEqual(len(accepted),5); self.assertEqual(auditor.provider.structured.call_count,3)
        self.assertFalse(any('BATCH_LIMIT' in x for x in warnings))

    def test_unknown_condition_still_blocks_unconditional_case_application(self):
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid'))
        item=Evidence(unit_id='x',retrieval_method='bm25',text='Trường hợp được nghỉ',verified=True)
        from vn_labor_online.models import ApplicabilityDecision
        auditor._deterministic=Mock(return_value=([],[ApplicabilityDecision(evidence_id='x',relevant=True,supports_claim=False,audit_status='UNRESOLVED')],[]))
        auditor.provider=Mock(); auditor.provider.structured.return_value={'decisions':{'x':{'relevant':True,'supports_claim':True,'conditions_status':'UNKNOWN','exception_status':'UNKNOWN'}}}
        accepted,decisions,warnings=auditor.audit([item],'Tôi có được nghỉ không?',['GENERAL'],{},'ASSESS_LEGALITY')
        self.assertFalse(accepted); self.assertEqual(decisions[0].audit_status,'UNRESOLVED')

class ContextAndRepairTests(unittest.TestCase):
    def test_large_pack_uses_separate_claim_and_coverage_checks(self):
        p,d,v=sample(); p.evidence[0].full_text+=' Nội dung nguồn dài.'*400
        provider=Mock(); provider.context_tokens=1200; provider.max_output_tokens=100
        provider.structured.side_effect=[{'claims':v['claims']},{k:v[k] for k in ('coverage','question_fully_addressed','missing_requirements')}]
        result,warnings=review_answer(provider,d,p,repair_attempts=0)
        self.assertEqual(result.semantic_review['status'],'PASS')
        self.assertEqual(provider.structured.call_count,2)
        self.assertIn('Nội dung nguồn dài.',provider.structured.call_args_list[0].args[1])
        self.assertNotIn('full_text',provider.structured.call_args_list[1].args[1])

    def test_repair_failure_preserves_checked_partial_claims(self):
        p,d,v=sample(); v.update(question_fully_addressed=False,missing_requirements=['Chưa đủ hậu quả'])
        provider=Mock(); provider.structured.side_effect=[v,TimeoutError()]
        result,warnings=review_answer(provider,d,p,repair_attempts=1)
        self.assertEqual(result.claims,d.claims)
        self.assertEqual(result.semantic_review['status'],'PARTIAL')
        self.assertIn('ANSWER_SEMANTIC_REVIEW_INCOMPLETE',warnings)

    def test_ollama_context_overflow_is_rejected_before_request(self):
        from vn_labor_online.providers import OllamaProvider
        provider=OllamaProvider(context_tokens=400,max_output_tokens=100)
        provider._post=Mock()
        with self.assertRaises(StructuredOutputError): provider.structured('system','x'*400,{})
        provider._post.assert_not_called()

    def test_http_provider_does_not_use_undefined_ollama_budget(self):
        from vn_labor_online.providers import HttpJsonProvider
        provider=HttpJsonProvider('https://example.test/chat','test')
        provider._post=Mock(return_value={'choices':[{'message':{'content':'{"ok":true}'}}]})
        self.assertEqual(provider.structured('system','user',{}),{'ok':True})

    def test_spelled_seniority_has_exact_verified_source_span(self):
        q='NLĐ chưa thành niên làm cùng công ty sáu năm. Số ngày nghỉ tối thiểu là bao nhiêu?'
        a=analyze(intake(q,[]))
        candidates=[c for c in a.fact_candidates if c.field=='service_years']
        self.assertTrue(candidates)
        self.assertTrue(all(c.verified and q[c.char_start:c.char_end]==c.source_quote for c in candidates))

    def test_paid_managed_internship_does_not_require_the_same_facts_again(self):
        q='Tôi là thực tập sinh bốn tháng, làm việc toàn thời gian, nhận lương cố định và chịu KPI như nhân viên. Đây có phải quan hệ lao động không?'
        a=analyze(intake(q,[]))
        self.assertTrue(a.facts.get('employment_paid_work'))
        self.assertTrue(a.facts.get('employment_management'))
        self.assertFalse(any('quản lý' in x.lower() and 'trả công' in x.lower() for x in a.missing_facts))

if __name__=='__main__': unittest.main()
