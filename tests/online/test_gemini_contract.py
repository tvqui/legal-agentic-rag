import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from vn_labor_online.providers import GeminiProvider,gemini_transport_schema
from vn_labor_online.errors import StructuredOutputError,ProviderRateLimited
from vn_labor_online.analysis import analyze,intake,plan_evidence


class GeminiContractTests(unittest.TestCase):
    def test_wire_schema_keeps_named_properties_and_original_contract(self):
        schema={'type':'object','properties':{'maxItems':{'type':'integer'},
          'rows':{'type':'array','maxItems':2,'minItems':1,'items':{'$ref':'#/$defs/row'}}},
          '$defs':{'row':{'type':'object','properties':{'items':{'type':'array','maxItems':3,'items':{'type':'string','minLength':2}}},'required':['items']}},
          'required':['rows'],'additionalProperties':False}
        original=copy.deepcopy(schema); wire=gemini_transport_schema(schema)
        self.assertEqual(schema,original)
        self.assertIn('maxItems',wire['properties'])
        self.assertNotIn('maxItems',wire['properties']['rows'])
        self.assertEqual(wire['properties']['rows']['minItems'],1)
        self.assertNotIn('maxItems',wire['$defs']['row']['properties']['items'])
        self.assertEqual(wire['required'],['rows'])
        self.assertFalse(wire['additionalProperties'])

    def provider_response(self,value,schema):
        try: from google import genai
        except ImportError: self.skipTest('Optional google-genai SDK is not installed')
        sdk=Mock(); sdk.__enter__=Mock(return_value=sdk); sdk.__exit__=Mock(return_value=False)
        sdk.models.generate_content.return_value=SimpleNamespace(text=json.dumps(value),candidates=[])
        with patch('google.genai.Client',return_value=sdk),patch('vn_labor_online.providers.get_gemini_limiter') as gate:
            gate.return_value.acquire.return_value=0
            result=GeminiProvider('test-model','test-key').structured('system','user',schema)
        return result,sdk.models.generate_content.call_args.kwargs['config'].response_json_schema

    def test_original_max_items_is_enforced_after_wire_lowering(self):
        schema={'type':'object','properties':{'rows':{'type':'array','maxItems':1,'items':{'type':'string'}}},'required':['rows']}
        with self.assertRaisesRegex(StructuredOutputError,'GEMINI_SCHEMA_VALIDATION_FAILED'):
            self.provider_response({'rows':['first','second']},schema)
        result,wire=self.provider_response({'rows':['first']},schema)
        self.assertEqual(result,{'rows':['first']})
        self.assertNotIn('maxItems',wire['properties']['rows'])

    def test_local_validation_keeps_types_enums_required_and_nested_bounds(self):
        schema={'type':'object','properties':{'kind':{'enum':['RULE']},'rows':{'type':'array','maxItems':1,
          'items':{'type':'object','properties':{'count':{'type':'integer','minimum':0}},'required':['count'],'additionalProperties':False}}},
          'required':['kind','rows'],'additionalProperties':False}
        for value in ({'kind':'GUESS','rows':[]},{'rows':[]},{'kind':'RULE','rows':[{'count':-1}]},
          {'kind':'RULE','rows':[{'count':'2'}]},{'kind':'RULE','rows':[{'count':2,'extra':True}]}):
            with self.subTest(value=value),self.assertRaises(StructuredOutputError): self.provider_response(value,schema)

    def test_hypothetical_service_name_still_uses_relationship_qualification(self):
        from vn_labor_online.taxonomy import profile_covers_issues
        for query in ('Một hợp đồng mang tên hợp đồng dịch vụ, có việc làm, tiền lương và sự quản lý của doanh nghiệp thì bản chất pháp lý là gì?',
          'Một hợp đồng cộng tác viên có trả công và chịu sự quản lý của doanh nghiệp thì căn cứ quy định nào?'):
            with self.subTest(query=query):
                analysis=analyze(intake(query,[]))
                self.assertIn('CONTRACT.RELATIONSHIP_QUALIFICATION',analysis.legal_subissues)
                self.assertIn('relationship_qualification',plan_evidence(analysis).slot_requirements)
        query='Hợp đồng mang tên dịch vụ nhưng có các yếu tố việc làm, tiền lương và quản lý của doanh nghiệp thì bản chất quan hệ là gì?'
        analysis=analyze(intake(query,[]))
        self.assertTrue(profile_covers_issues(analysis))
        self.assertNotIn('mandatory_reference',plan_evidence(analysis).mandatory_slots)
        separate=analyze(intake(query+' Tiền lương tối thiểu phải trả là bao nhiêu?',[]))
        self.assertFalse(profile_covers_issues(separate))


class ProviderCapacityTests(unittest.TestCase):
    def test_required_gemini_review_cannot_follow_a_rate_limited_researcher_with_costly_fallback(self):
        from tests.online.test_online_core import fixture
        from vn_labor_online.config import OnlineConfig,RetrievalConfig,AdjudicationConfig
        from vn_labor_online.pipeline import OnlinePipeline
        from vn_labor_online.models import QueryRequest
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); build=fixture(root)
            cfg=OnlineConfig(artifact_source=str(root),expected_build_id=build,cache_dir=str(root/'cache'),
              trace_dir=str(root/'traces'),retrieval=RetrievalConfig(dense_enabled=False),
              adjudication=AdjudicationConfig(mode='ollama',review_provider='gemini',review_model='test'))
            pipe=OnlinePipeline(cfg)
            try:
                pipe.researcher.enrich=lambda analysis,*args:(analysis,['RESEARCHER_PROVIDER_ERROR:GEMINI_HTTP_429'])
                pipe.applicability.audit=Mock(side_effect=AssertionError('No expensive audit on quota failure'))
                pipe.adjudicator.generate=Mock(side_effect=AssertionError('No expensive generation on quota failure'))
                with self.assertRaises(ProviderRateLimited):
                    pipe.ask(QueryRequest(question='Tôi hỏi quy định về tiền lương lao động.'))
                pipe.adjudicator.generate.assert_not_called()
                pipe.applicability.audit.assert_not_called()
            finally: pipe.close()

    def test_api_reports_provider_capacity_separately_from_missing_legal_evidence(self):
        from fastapi.testclient import TestClient
        from vn_labor_online.api import create_app
        from vn_labor_online.config import OnlineConfig
        pipe=Mock(); pipe.cfg=OnlineConfig(artifact_source='test'); pipe.ask.side_effect=ProviderRateLimited('GEMINI_HTTP_429')
        with patch('vn_labor_online.api.OnlinePipeline',return_value=pipe),patch('vn_labor_online.api.load_config'),patch.dict('os.environ',{'VN_LABOR_API_KEY':''}):
            with TestClient(create_app()) as client:
                result=client.post('/v1/answer',json={'question':'Câu hỏi kiểm tra hạn mức dịch vụ AI'})
        self.assertEqual(result.status_code,503)
        self.assertEqual(result.json()['category'],'PROVIDER_RATE_LIMIT')
        self.assertTrue(result.json()['error_id'].startswith('ERR_'))
        self.assertEqual(result.headers['retry-after'],'60')


class AlternativeQualityTests(unittest.TestCase):
    def test_generic_slots_do_not_reintroduce_unreviewed_ocr_duplicate(self):
        from vn_labor_online.models import Evidence,EvidencePlan,LegalLocator
        from vn_labor_online.evidence import select_for_plan
        base=dict(retrieval_method='policy',verified=True,kind='PROVISION',article_number='114',
          binding=True,authority_rank=100,source_url='https://vbpl.vn/source',valid_from='2021-01-01',
          temporal_verified=True,provision_temporal_verified=False,official_source=False,source_catalog_status='DRAFT')
        clean=Evidence(unit_id='clean',document_number='18/VBHN-VPQH',score=.1,
          text='Cứ đủ 05 năm làm việc cho một người sử dụng lao động được tăng 01 ngày nghỉ hằng năm.',**base)
        bad=Evidence(unit_id='bad',document_number='45/2019/QH14',score=.99,
          text='Đỉều 1l4. Cứ đủ 05 năm làm việc cho một nguời sử dụng lao động được tăng 01 ngày nghỉ hằng năm.',**base)
        plan=EvidencePlan(mandatory_slots=['governing_rule','official_source','seniority_rule'],
          slot_requirements={'seniority_rule':[[LegalLocator(documents=['18/VBHN-VPQH','45/2019/QH14'],article='114')]]})
        selected,state=select_for_plan([bad,clean],plan,'2026-01-01',True,12)
        self.assertEqual([item.unit_id for item in selected],['clean'])
        self.assertIn('official_source',state.gaps)

    def test_ocr_locator_detection_does_not_rewrite_or_reject_valid_suffixes(self):
        from vn_labor_online.answer_quality import language_issues
        for text in ('Đỉều 1l4. Nội dung nguồn','Điều 2I3. Nội dung','Khoản ll4 quy định'):
            self.assertIn('SUSPECT_LEGAL_LOCATOR',language_issues(text))
        for text in ('Điều 114 quy định','Điều 114a quy định','Chương II. Nội dung'):
            self.assertNotIn('SUSPECT_LEGAL_LOCATOR',language_issues(text))
