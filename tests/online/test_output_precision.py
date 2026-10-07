from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig,AdjudicationConfig,ResearcherConfig
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.evidence import select_for_plan,state_for,build_verified_pack
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.models import Evidence,EvidencePlan,ApplicabilityDecision
from vn_labor_online.providers import _decode_content,OllamaProvider
from vn_labor_online.researcher import LegalResearcher

def rule(uid,article,clause='',point='',text='Quy định về người lao động.',doc='45/2019/QH14'):
    return Evidence(unit_id=uid,kind='PROVISION',retrieval_method='policy',verified=True,
      provision_identity_id=uid,provision_version_id=uid,document_number=doc,
      article_number=article,clause_number=clause,point_number=point,text=text,source_text=text,
      official_source=True,source_catalog_status='VERIFIED',provision_temporal_verified=True,
      temporal_verified=True,authority_rank=100,document_id='doc',valid_from='2021-01-01',source_url='https://vbpl.vn/test')

def pack(query,items,facts=None,outcome='EXPLAIN'):
    return build_verified_pack(query,'2025-01-01',facts or {},
      state_for(items,EvidencePlan(mandatory_slots=['governing_rule']),None),items,requested_outcome=outcome)

class OutputPrecisionTests(unittest.TestCase):
    def test_contract_type_profile_is_dated_and_preserves_all_required_types(self):
        question='Hiện nay hợp đồng lao động có những loại nào?'
        current=plan_evidence(analyze(intake(question,[]),'2025-01-01'))
        old=plan_evidence(analyze(intake(question,[]),'2020-01-01'))
        self.assertEqual([group[0].article for group in current.slot_requirements['contract_types']],['20','20'])
        self.assertEqual([group[0].point for group in old.slot_requirements['contract_types']],['a','b','c'])
        self.assertTrue(all(group[0].documents==['10/2012/QH13'] for group in old.slot_requirements['contract_types']))

    def test_contract_types_do_not_call_model_or_invent_third_probation_type(self):
        items=[rule('a','20','1','a','Hợp đồng lao động không xác định thời hạn.'),
          rule('b','20','1','b','Hợp đồng xác định thời hạn không quá 36 tháng.')]
        engine=LegalAdjudicator(AdjudicationConfig()); engine.provider=Mock()
        draft,warnings=engine.generate(pack('Hiện nay hợp đồng lao động có những loại nào?',items),False)
        engine.provider.structured.assert_not_called()
        self.assertFalse(warnings); self.assertEqual(len(draft.claims),2)
        self.assertIn('không phải một loại hợp đồng lao động thứ ba',draft.answer_summary)
        self.assertEqual({uid for claim in draft.claims for uid in claim.evidence_ids},{'a','b'})

    def test_intern_label_does_not_establish_employment(self):
        item=rule('intern','13','1',text='Việc làm có trả công, tiền lương và sự quản lý, điều hành, giám sát của một bên.')
        engine=LegalAdjudicator(AdjudicationConfig()); engine.provider=Mock()
        draft,_=engine.generate(pack('Thực tập sinh có phải là người lao động không?', [item]),False)
        engine.provider.structured.assert_not_called()
        self.assertIn('tự nó chưa đủ để kết luận',draft.answer_summary)
        self.assertIn('trả công, tiền lương',draft.answer_summary)

    def test_lean_provider_output_derives_metadata_and_renders_only_claims(self):
        item=rule('wage','90',text='Tiền lương do hai bên thỏa thuận.')
        engine=LegalAdjudicator(AdjudicationConfig()); engine.provider=Mock()
        engine.provider.structured.return_value={'claims':[{'text':'Tiền lương do hai bên thỏa thuận.','evidence_ids':['wage']}]}
        draft,warnings=engine.generate(pack('Tiền lương là gì?', [item]),True,['Một giả định đã cho.'])
        self.assertFalse(warnings); self.assertEqual(draft.assumptions,['Một giả định đã cho.'])
        self.assertEqual(draft.claims[0].claim_id,'claim_001')
        self.assertEqual(draft.applicable_law_versions[0].instrument_number,'45/2019/QH14')
        schema=engine.provider.structured.call_args.args[2]
        self.assertEqual(schema['$defs']['ProviderClaim']['properties']['evidence_ids']['items']['enum'],['wage'])
        self.assertNotIn('answer_summary',schema['properties'])

    def test_provider_claim_with_unknown_id_falls_back(self):
        item=rule('wage','90',text='Tiền lương do hai bên thỏa thuận.')
        engine=LegalAdjudicator(AdjudicationConfig()); engine.provider=Mock()
        engine.provider.structured.return_value={'claims':[{'text':'Sai.','evidence_ids':['invented']}]}
        draft,warnings=engine.generate(pack('Tiền lương là gì?',[item]),False)
        self.assertTrue(warnings); self.assertNotIn('invented',draft.answer_summary)

    def test_not_applicable_conditions_can_pass_but_failed_conditions_cannot(self):
        item=rule('wage','90',text='Tiền lương do hai bên thỏa thuận.')
        engine=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid')); engine.provider=Mock()
        for conditions,expected in [('NOT_APPLICABLE','PASS'),('NOT_SATISFIED','FAIL'),('UNKNOWN','UNRESOLVED')]:
            engine.provider.structured.return_value={'decisions':{'wage':{'relevant':True,'supports_claim':True,
              'conditions_status':conditions,'exception_status':'NOT_APPLICABLE'}}}
            accepted,decisions,_=engine.audit([item],'Tiền lương này có đúng luật không?',['WAGE'],{},'ASSESS_LEGALITY')
            self.assertEqual(decisions[0].audit_status,expected)
            self.assertEqual(bool(accepted),expected=='PASS')

    def test_wrong_ids_and_model_error_cannot_promote_lexical_match(self):
        item=rule('wage','90',text='Tiền lương do hai bên thỏa thuận.')
        engine=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid')); engine.provider=Mock()
        engine.provider.structured.return_value={'decisions':{'other':{}}}
        accepted,decisions,warnings=engine.audit([item],'Tiền lương này có đúng luật không?',['WAGE'],{},'ASSESS_LEGALITY')
        self.assertFalse(accepted); self.assertEqual(decisions[0].audit_status,'UNRESOLVED'); self.assertTrue(warnings)

    def test_verified_pack_excludes_failed_unresolved_and_missing_decisions(self):
        items=[rule('pass','90'),rule('fail','91'),rule('unknown','92'),rule('absent','93')]
        decisions=[ApplicabilityDecision(evidence_id='pass',relevant=True,supports_claim=True,
          conditions_status='NOT_APPLICABLE',exception_status='NOT_APPLICABLE',audit_status='PASS'),
          ApplicabilityDecision(evidence_id='fail',relevant=True,supports_claim=True,audit_status='FAIL'),
          ApplicabilityDecision(evidence_id='unknown',relevant=True,supports_claim=True,audit_status='UNRESOLVED')]
        result=build_verified_pack('lương',None,{},state_for(items,['governing_rule'],None),items,decisions)
        self.assertEqual([item.evidence_id for item in result.evidence],['pass'])

    def test_minimal_pack_keeps_required_groups_without_padding(self):
        query='Hiện nay hợp đồng lao động có những loại nào?'
        plan=plan_evidence(analyze(intake(query,[]),'2025-01-01'))
        items=[rule('a','20','1','a'),rule('b','20','1','b'),rule('unrelated','36','2','a')]
        selected,state=select_for_plan(items,plan,'2025-01-01',False,12)
        self.assertEqual({item.unit_id for item in selected},{'a','b'}); self.assertFalse(state.gaps)

    def test_dedup_retains_changed_text_and_distinct_temporal_versions(self):
        original=rule('a','20','1','a',text='Nội dung một.')
        copy=rule('b','20','1','a',text='Nội dung một.',doc='18/VBHN-VPQH')
        changed=rule('c','20','1','a',text='Nội dung khác.',doc='18/VBHN-VPQH')
        historical=original.model_copy(update={'unit_id':'d','provision_identity_id':'d','provision_version_id':'d','valid_from':'2022-01-01'})
        selected,_=select_for_plan([original,copy,changed,historical],EvidencePlan(mandatory_slots=['governing_rule']),None,False,12)
        self.assertEqual({item.unit_id for item in selected},{'a','c','d'})

    def test_cleaner_existing_source_is_preferred_without_rewriting_ocr(self):
        query='Thế nào là người lao động và người sử dụng lao động?'
        plan=plan_evidence(analyze(intake(query,[]),'2025-01-01'))
        employee=rule('employee','3','1')
        corrupt=rule('corrupt','3','2',text='Người sừ dụng lao động là tố chức; phải có lực hành vi dân sự đầy đủ.').model_copy(update={'score':100})
        clean=rule('clean','3','2',text='Người sử dụng lao động là tổ chức; phải có năng lực hành vi dân sự đầy đủ.',doc='18/VBHN-VPQH')
        selected,_=select_for_plan([employee,corrupt,clean],plan,'2025-01-01',False,12)
        self.assertEqual({item.unit_id for item in selected},{'employee','clean'})
        self.assertIn('sừ dụng',corrupt.source_text)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(StructuredOutputError): _decode_content('{"decisions":{"a":{},"a":{}}}')

    def test_ollama_payload_has_schema_think_false_and_token_budget(self):
        provider=OllamaProvider(max_output_tokens=512)
        response=Mock(); response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
        response.read.return_value=b'{"message":{"content":"{\\"claims\\":[]}"},"done_reason":"stop"}'
        with patch('urllib.request.urlopen',return_value=response) as request:
            provider.structured('system','user',{'type':'object'})
        payload=json.loads(request.call_args.args[0].data)
        self.assertFalse(payload['think']); self.assertEqual(payload['format'],{'type':'object'})
        self.assertEqual(payload['options']['num_predict'],512)

    def test_researcher_skips_explicit_lookup_but_not_ambiguous_issue(self):
        engine=LegalResearcher(ResearcherConfig()); engine.provider=Mock()
        engine.enrich(analyze(intake('Điều 1 của Nghị định 145/2020/NĐ-CP quy định gì?',[]),'2025-01-01'),'query',[])
        engine.provider.structured.assert_not_called()
        engine.provider.structured.return_value={}
        engine.enrich(analyze(intake('Quyền và nghĩa vụ trong tranh chấp lao động là gì?',[]),'2025-01-01'),'query',[])
        engine.provider.structured.assert_called_once()

    def test_unpaid_intern_status_question_skips_model_but_wage_issue_does_not(self):
        engine=LegalResearcher(ResearcherConfig()); engine.provider=Mock()
        status='Công ty gọi một NLĐ là thực tập sinh không lương. Chỉ dựa vào tên gọi có thể kết luận không phải HĐLĐ không?'
        wage='Tôi làm theo hợp đồng lao động mang tên thực tập sinh không lương. Mức lương tối thiểu phải trả là bao nhiêu?'
        self.assertEqual(engine.execution_path(analyze(intake(status,[]),'2025-01-01')),'SKIPPED_KNOWN_PROFILE')
        self.assertEqual(engine.execution_path(analyze(intake(wage,[]),'2025-01-01')),'MODEL_REQUESTED')

    def test_misinformation_does_not_conclude_material_effect_from_topic(self):
        facts={'actor':'EMPLOYEE','termination_basis':'EMPLOYER_MISINFORMATION'}
        items=[rule('g','35','2','g',text='Cung cấp thông tin không trung thực ảnh hưởng đến việc thực hiện hợp đồng.'),
          rule('info','16','1',text='Cung cấp trung thực thông tin khi giao kết hợp đồng.')]
        accepted,decisions,_=LegalApplicabilityAuditor(ApplicabilityConfig()).audit(items,'Thông tin tuyển dụng sai.',
          ['TERMINATION'],facts,'ASSESS_LEGALITY')
        self.assertFalse(accepted); self.assertTrue(all(d.audit_status=='UNRESOLVED' for d in decisions))
        draft,_=LegalAdjudicator(AdjudicationConfig()).generate(pack('Thông tin tuyển dụng sai.',items,facts),False)
        self.assertNotIn('có quyền nghỉ không cần báo trước theo dữ kiện',draft.answer_summary)

    def test_misinformation_link_query_keeps_both_articles(self):
        facts={'actor':'EMPLOYEE','termination_basis':'EMPLOYER_MISINFORMATION'}
        items=[rule('g','35','2','g',text='Thông tin không trung thực theo khoản 1 Điều 16 ảnh hưởng đến việc thực hiện hợp đồng.'),
          rule('info','16','1',text='Cung cấp trung thực thông tin khi giao kết hợp đồng.')]
        query='Công ty cung cấp sai địa điểm làm việc khi tuyển dụng khiến NLĐ sau đó muốn nghỉ ngay. Những điều luật nào phải được nối với nhau?'
        engine=LegalAdjudicator(AdjudicationConfig()); engine.provider=Mock()
        draft,_=engine.generate(pack(query,items,facts),False)
        engine.provider.structured.assert_not_called()
        self.assertEqual({uid for claim in draft.claims for uid in claim.evidence_ids},{'g','info'})
        self.assertIn('Điểm g khoản 2 Điều 35',draft.answer_summary)

    def test_missing_material_effect_is_asked_only_for_case_assessment(self):
        explain=analyze(intake('Công ty cung cấp sai địa điểm khi tuyển dụng khiến NLĐ muốn nghỉ ngay. Những điều luật nào cần nối?',[]),'2025-01-01')
        assess=analyze(intake('Công ty cung cấp sai địa điểm khi tuyển dụng. Tôi có quyền nghỉ ngay không?',[]),'2025-01-01')
        self.assertFalse(explain.missing_facts)
        self.assertNotIn('notice_exception',explain.facts)
        self.assertTrue(any('ảnh hưởng' in question for question in assess.missing_facts))

    def test_fact_gate_avoids_unnecessary_researcher_request(self):
        query='Tôi muốn nghỉ việc ngay. Tôi có được nghỉ không?'
        analysis=analyze(intake(query,[]),'2025-01-01')
        self.assertTrue(analysis.missing_facts)
        engine=LegalResearcher(ResearcherConfig()); engine.provider=Mock()
        engine.enrich(analysis,query,[])
        engine.provider.structured.assert_not_called()
        self.assertEqual(engine.execution_path(analysis),'SKIPPED_FACT_GATE')

    def test_deposit_profile_requires_only_correct_clause(self):
        query='Công ty yêu cầu tôi đặt cọc trước khi vào làm. Việc này có trái luật không?'
        plan=plan_evidence(analyze(intake(query,[]),'2025-01-01'))
        groups=plan.slot_requirements['prohibited_contract_acts']
        self.assertEqual([(group[0].article,group[0].clause) for group in groups],[('17','2')])

    def test_output_coverage_repairs_missing_required_cross_reference_without_model(self):
        from types import SimpleNamespace
        from vn_labor_online.config import OnlineConfig,RetrievalConfig,RerankerConfig
        from vn_labor_online.pipeline import OnlinePipeline
        from vn_labor_online.models import AdjudicationDraft,Claim,QueryRequest
        items=[rule('g','35','2','g',text='Người sử dụng lao động cung cấp thông tin không trung thực theo khoản 1 Điều 16 ảnh hưởng đến việc thực hiện hợp đồng, được chấm dứt hợp đồng không cần báo trước.'),
          rule('info','16','1',text='Người sử dụng lao động phải cung cấp trung thực thông tin khi giao kết hợp đồng.')]
        with tempfile.TemporaryDirectory() as tmp:
            engine=object.__new__(OnlinePipeline)
            engine.cfg=OnlineConfig(artifact_source='unused',corpus_snapshot_as_of='2025-01-01',trace_dir=tmp,
              retrieval=RetrievalConfig(dense_enabled=True),reranker=RerankerConfig(enabled=True))
            engine.store=SimpleNamespace(report=SimpleNamespace(build_id='test',provisional_reasons=[]))
            engine.researcher=LegalResearcher(ResearcherConfig())
            engine.retriever=Mock(); engine.retriever.policy_anchor.return_value=items
            engine.applicability=LegalApplicabilityAuditor(ApplicabilityConfig())
            engine.adjudicator=Mock(); engine.graph=Mock()
            engine.adjudicator.generate.return_value=(AdjudicationDraft(answer_summary='Thông tin khi giao kết.',
              claims=[Claim(claim_id='c',text='Khoản 1 Điều 16 yêu cầu cung cấp trung thực thông tin khi giao kết.',evidence_ids=['info'])],
              applicable_law_versions=[]),[])
            query='Công ty cung cấp sai địa điểm làm việc khi tuyển dụng khiến NLĐ muốn nghỉ ngay. Những điều luật nào phải được nối với nhau?'
            with patch('vn_labor_online.pipeline.deterministic_audit',side_effect=lambda _,values,*args:values):
                response=engine.ask(QueryRequest(question=query,query_date='2025-01-01'))
            self.assertIn('ANSWER_REQUIRED_EVIDENCE_REPAIRED',response.warnings)
            self.assertEqual({c.evidence_id for c in response.citations},{'g','info'})
            engine.retriever.dense.assert_not_called(); engine.retriever.neural_rerank.assert_not_called()

if __name__=='__main__': unittest.main()
