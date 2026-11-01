import json,unittest
from unittest.mock import Mock
from vn_labor_online.analysis import analyze,intake
from vn_labor_online.researcher import LegalResearcher
from vn_labor_online.config import ResearcherConfig,ApplicabilityConfig
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.models import Evidence

class ScopeRecoveryTests(unittest.TestCase):
 def test_personal_property_synonyms_do_not_become_employment(self):
  for query in ['Tôi chuyển nhượng căn hộ chung cư thì đóng thuế gì?',
                'Bán bất động sản riêng cần kê khai loại thuế nào?',
                'Cho thuê căn hộ thì làm hợp đồng dân sự như thế nào?',
                'Công ty của bạn tôi mua nhà riêng; lệ phí trước bạ bao nhiêu?']:
   with self.subTest(query=query):self.assertFalse(analyze(intake(query,[])).in_scope)
 def test_employee_housing_and_payroll_tax_are_not_rejected(self):
  for query in ['Công ty trả phụ cấp thuê căn hộ cho người lao động thì tính vào tiền lương không?',
                'Tiền lương làm đêm của người lao động có được miễn thuế không?',
                'Doanh nghiệp bán nhà ở cho công nhân và khấu trừ lương có được không?']:
   with self.subTest(query=query):self.assertTrue(analyze(intake(query,[])).in_scope)
 def researcher(self,result):
  r=LegalResearcher(ResearcherConfig(mode='gemini',model='fake',api_key='FAKE_UNIT_ONLY',adaptive=False))
  r.provider=Mock();r.provider.structured.return_value=result
  return r
 def test_semantic_scope_gate_handles_unknown_non_labour_question(self):
  q='Tôi làm hộ chiếu lần đầu cần giấy tờ nào?'
  a=analyze(intake(q,[]));self.assertTrue(a.in_scope)
  updated,warnings=self.researcher({'scope':'OUT_OF_SCOPE','scope_quote':'làm hộ chiếu lần đầu'}).enrich(a,q,[])
  self.assertFalse(updated.in_scope);self.assertFalse(updated.retrieval_queries)
  self.assertIn('RESEARCHER_SCOPE_OUT_OF_SCOPE',warnings)
 def test_scope_quote_must_come_from_current_query(self):
  q='Tôi làm hộ chiếu lần đầu cần giấy tờ nào?'
  a=analyze(intake(q,[]))
  updated,_=self.researcher({'scope':'OUT_OF_SCOPE','scope_quote':'câu hỏi không tồn tại'}).enrich(a,q,[])
  self.assertTrue(updated.in_scope)
 def test_scope_classifier_cannot_discard_recognized_labour_issue(self):
  q='Người lao động làm việc ban đêm được trả thêm tiền lương không?'
  a=analyze(intake(q,[]));self.assertTrue(a.legal_subissues)
  updated,_=self.researcher({'scope':'OUT_OF_SCOPE','scope_quote':q}).enrich(a,q,[])
  self.assertTrue(updated.in_scope)
 def test_mixed_scope_retains_employment_task(self):
  q='Tôi chưa nhận tiền làm thêm giờ và cần đổi hộ chiếu; nên làm gì?'
  a=analyze(intake(q,[]))
  updated,_=self.researcher({'scope':'MIXED','scope_quote':q}).enrich(a,q,[])
  self.assertTrue(updated.in_scope)
  self.assertTrue(updated.answer_tasks)
 def test_missing_scope_fields_are_backwards_compatible(self):
  q='Nghĩa vụ lập biên bản được quy định ra sao?'
  a=analyze(intake(q,[]))
  updated,_=self.researcher({'retrieval_queries':['nghĩa vụ lập biên bản lao động']}).enrich(a,q,[])
  self.assertTrue(updated.in_scope)
 def test_tax_keyword_alone_is_not_a_confirmed_employment_relationship(self):
  q='Thuế thu nhập cá nhân khi được tặng chứng khoán phải nộp bao nhiêu?'
  a=analyze(intake(q,[]));self.assertIn('income_tax',a.routing_topics)
  updated,_=self.researcher({'scope':'OUT_OF_SCOPE','scope_quote':'được tặng chứng khoán'}).enrich(a,q,[])
  self.assertFalse(updated.in_scope)

class AuxiliaryContextRecoveryTests(unittest.TestCase):
 def test_oversized_ai_annotation_does_not_discard_full_legal_text(self):
  auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid',max_items=1))
  auditor._deterministic=Mock(return_value=([],[],[]))
  auditor.store=Mock();auditor.store.diagnostic_items.return_value=[{'annotation':'X'*20000}]
  # A strict byte budget excludes the AI annotation but fits the whole source.
  provider=Mock();provider.context_tokens=12000;provider.max_output_tokens=1024
  provider.count_prompt_tokens=None
  provider.structured.return_value={'decisions':{'source':{'relevant':True,'supports_claim':True,
   'conditions_status':'NOT_APPLICABLE','exception_status':'NOT_APPLICABLE'}}}
  auditor.provider=provider
  text='Bên giao việc phải lập biên bản trước khi bàn giao tài sản.'
  ancestor='Điều 701. Nghĩa vụ bàn giao tài sản; áp dụng cho bên giao việc.'
  item=Evidence(unit_id='source',text=text,source_text=text,ancestor_context=ancestor,retrieval_method='bm25')
  accepted,_,warnings=auditor.audit([item],'Giải thích nghĩa vụ bàn giao.',['GENERAL'],{})
  self.assertEqual([e.unit_id for e in accepted],['source'])
  payload=json.loads(provider.structured.call_args.args[1])
  evidence=payload['candidates'][0]['evidence']
  self.assertEqual(evidence['text'],text);self.assertEqual(evidence['ancestor_context'],ancestor)
  self.assertNotIn('diagnostic_checklist',evidence)
  self.assertIn('APPLICABILITY_AUXILIARY_CHECKLIST_OMITTED',warnings)
 def test_long_statutory_text_is_never_truncated_to_fit(self):
  auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid',max_items=1))
  auditor._deterministic=Mock(return_value=([],[],[]))
  provider=Mock();provider.context_tokens=10000;provider.max_output_tokens=1024;provider.count_prompt_tokens=None
  auditor.provider=provider
  source=Evidence(unit_id='source',text='Nội dung quy phạm. '*4000,retrieval_method='bm25')
  accepted,decisions,warnings=auditor.audit([source],'Giải thích nghĩa vụ.',['GENERAL'],{})
  self.assertFalse(accepted);provider.structured.assert_not_called()
  self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
  self.assertIn('APPLICABILITY_OUTPUT_INVALID:PROMPT_CONTEXT_BUDGET_EXCEEDED',warnings)

if __name__=='__main__':unittest.main()
