"""General mechanisms, novel wording and synthetic statutes; no model API calls."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.conversation import resolve_context
from vn_labor_online.models import QueryRequest,Evidence,EvidencePlan
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig,OnlineConfig
from vn_labor_online.evidence import extend_plan_for_evidence,state_for
from vn_labor_online.exception_references import exception_locators
from vn_labor_online.retrieval import Retriever

def request(text,history=()):
 return QueryRequest(question=text,conversation_turns=[{'turn_id':str(i),'content':s} for i,s in enumerate(history)])

class ContextGeneralizationTests(unittest.TestCase):
 def test_bare_deictic_verdict_does_not_invent_the_antecedent(self):
  for text in ['Vậy có được như thế không?', 'Việc đó có đúng không?', 'Thế thì có hợp pháp không?']:
   c=resolve_context(request(text,['Tôi đang thử việc.', 'Tôi có bao nhiêu ngày nghỉ phép năm?']))
   with self.subTest(text=text):self.assertEqual(c.clarification_reason,'AMBIGUOUS_FOLLOWUP')
 def test_meaningful_followup_question_still_uses_context(self):
  c=resolve_context(request('Còn thời gian tối đa là bao lâu?', ['Tôi đang thử việc cho công việc yêu cầu trình độ trung cấp.']))
  self.assertIsNone(c.clarification)
  self.assertTrue(c.used_turns)
 def test_job_reply_without_repeating_probation_keeps_original_trial_quantity(self):
  c=resolve_context(request('Công việc của tôi yêu cầu trình độ trung cấp, không phải người quản lý doanh nghiệp.',
     ['Tôi muốn hỏi việc thử việc 50 ngày có hợp pháp không.']))
  self.assertTrue(c.used_turns)
  self.assertEqual(c.facts.get('probation_work_group'),'INTERMEDIATE')
  self.assertEqual(c.facts.get('probation_duration_value'),50)
  self.assertEqual(c.facts.get('probation_duration_unit'),'ngay')
  self.assertNotIn('50',c.query)
 def test_followup_trial_application_uses_source_limit_and_confirmed_prior_quantity(self):
  from tests.online.test_output_precision import rule,pack
  from vn_labor_online.profile_generation import render_profile
  c=resolve_context(request('Công việc của tôi yêu cầu trình độ trung cấp.',
     ['Tôi muốn hỏi việc thử việc 50 ngày có hợp pháp không.']))
  e=rule('limit','25','3',text='3. Không quá 30 ngày đối với công việc có chức danh nghề nghiệp cần trình độ chuyên môn, kỹ thuật trung cấp, công nhân kỹ thuật, nhân viên nghiệp vụ;')
  draft=render_profile(pack(c.query,[e],c.facts),False,[])
  self.assertIsNotNone(draft)
  self.assertTrue(any('50 ngày vượt mức tối đa 30 ngày' in claim.text for claim in draft.claims))
 def test_conditional_same_job_keeps_confirmed_group(self):
  for text in ['Nếu công ty yêu cầu thử việc lần nữa cho chính công việc ấy thì sao?',
               'Nếu tôi tiếp tục thử việc theo cùng hợp đồng thì được không?']:
   with self.subTest(text=text):
    c=resolve_context(request(text,['Tôi đang thử việc cho công việc yêu cầu trình độ cao đẳng.']))
    self.assertEqual(c.facts.get('probation_work_group'),'COLLEGE')
    self.assertTrue(c.used_turns)
 def test_unrelated_hypothetical_does_not_inherit_personal_facts(self):
  for text in ['Nếu công ty khác thuê tôi thì sao?', 'Giả sử tôi làm cùng công việc nhưng ở công ty khác.']:
   with self.subTest(text=text):
    c=resolve_context(request(text,['Tôi đang thử việc cho công việc yêu cầu trình độ trung cấp.']))
    self.assertFalse(c.used_turns)
    self.assertNotIn('probation_work_group',c.facts)
 def test_changed_job_group_without_correction_requires_confirmation(self):
  c=resolve_context(request('Tôi làm công việc yêu cầu trình độ trung cấp. Thời gian thử việc tối đa là bao lâu?',
    ['Tôi đang thử việc cho công việc yêu cầu trình độ cao đẳng.']))
  self.assertEqual(c.clarification_reason,'MATERIAL_FACT_CONFLICT')
  self.assertNotIn('probation_work_group',c.facts)
 def test_disability_fact_reply_preserves_and_checks_prior_case(self):
  c=resolve_context(request('Tôi không phải người khuyết tật. Vậy tôi được nghỉ phép bao nhiêu ngày?',
    ['Tôi là người khuyết tật, làm công việc bình thường và đã làm đủ 12 tháng. Tôi được nghỉ phép bao nhiêu ngày?']))
  self.assertEqual(c.clarification_reason,'MATERIAL_FACT_CONFLICT')
  self.assertNotIn('disabled',c.facts)
  self.assertEqual(c.facts.get('worked_months'),12)
 def test_disability_correction_is_not_a_permanent_conflict(self):
  c=resolve_context(request('Đính chính: tôi không phải người khuyết tật. Tôi được nghỉ phép bao nhiêu ngày?',
    ['Tôi là người khuyết tật, làm công việc bình thường và đã làm đủ 12 tháng. Tôi được nghỉ phép bao nhiêu ngày?']))
  self.assertIsNone(c.clarification)
  self.assertIs(c.facts.get('disabled'),False)
  self.assertEqual(c.facts.get('worked_months'),12)
 def test_job_group_correction_keeps_original_span_provenance(self):
  text='Đính chính: công việc yêu cầu trình độ trung cấp. Thử việc tối đa bao lâu?'
  c=resolve_context(request(text,['Tôi đang thử việc cho công việc yêu cầu trình độ cao đẳng.']))
  self.assertIsNone(c.clarification)
  self.assertEqual(c.facts.get('probation_work_group'),'INTERMEDIATE')
  for p in c.provenance:
   if p['turn_id']=='current_request':self.assertEqual(text[p['char_start']:p['char_end']],p['source_quote'])

class EvidencePlanGeneralizationTests(unittest.TestCase):
 def test_number_of_topics_does_not_invent_a_statutory_reference(self):
  for text in ['Công ty giữ bằng và phạt tiền khi nhân viên đi muộn có được không?',
               'Một lần vi phạm nội quy, công ty vừa khiển trách vừa kéo dài thời hạn nâng lương. Có được không?',
               'So sánh nội quy lao động với thỏa ước lao động tập thể.']:
   with self.subTest(text=text):
    a=analyze(intake(text,[]),'2026-09-15');p=plan_evidence(a)
    self.assertNotIn('mandatory_reference',p.mandatory_slots)
 def test_generic_applicability_is_not_a_keyword_presence_requirement(self):
  a=analyze(intake('Công ty được cộng hai hình thức kỷ luật cho một hành vi không?',[]),'2026-09-15')
  p=plan_evidence(a)
  self.assertNotIn('conditions',p.mandatory_slots)
  self.assertNotIn('exceptions',p.mandatory_slots)
 def test_unknown_material_prerequisite_remains_unresolved(self):
  auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid'))
  e=Evidence(unit_id='unknown',text='Quy tắc có điều kiện.',retrieval_method='bm25')
  auditor._deterministic=Mock(return_value=([],[],[]));auditor.provider=Mock()
  auditor.provider.structured.return_value={'decisions':{'unknown':{'relevant':True,'supports_claim':True,
   'conditions_status':'UNKNOWN','exception_status':'NOT_APPLICABLE'}}}
  accepted,decisions,_=auditor.audit([e],'Tôi có đủ điều kiện không?',['GENERAL'],{},'ASSESS_LEGALITY')
  self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
 def test_explicit_source_reference_is_still_mandatory(self):
  e=Evidence(unit_id='source',document_number='TEST',article_number='51',clause_number='2',
   text='Cấm thực hiện, trừ trường hợp quy định tại khoản 4 Điều 179 của Bộ luật này.',
   kind='PROVISION',retrieval_method='bm25',verified=True)
  p=extend_plan_for_evidence(EvidencePlan(mandatory_slots=['governing_rule']),[e],{},None)
  loc=p.slot_requirements['exceptions'][0][0]
  self.assertEqual((loc.documents,loc.article,loc.clause),(['TEST'],'179','4'))
  self.assertIn('exceptions',state_for([e],p,None).gaps)
 def test_external_and_untrusted_references_are_not_implicitly_bound(self):
  for text in ['Trừ trường hợp quy định tại khoản 4 Điều 179 của luật khác.',
               'Xem khoản 4 Điều 179 của Bộ luật này.']:
   e=Evidence(unit_id='source',document_number='TEST',article_number='51',text=text,kind='PROVISION',retrieval_method='bm25')
   self.assertFalse(exception_locators(e))
 def test_exception_retrieval_uses_target_article_and_point_same_edition(self):
  e=Evidence(unit_id='seed',document_id='edition',document_number='TEST',article_number='51',clause_number='2',
   text='Cấm thực hiện, trừ trường hợp quy định tại điểm b khoản 4 Điều 179 của Bộ luật này.',
   kind='PROVISION',retrieval_method='bm25',verified=True)
  units=[{'unit_id':uid,'document_id':edition,'document_number':'TEST','article_number':article,
    'clause_number':'4','point_number':point,'kind':'PROVISION','text':'Nội dung nguồn.'}
    for uid,edition,article,point in [('target','edition','179','b'),('wrong-point','edition','179','a'),
      ('wrong-edition','old','179','b'),('wrong-article','edition','51','b')]]
  extra,_=Retriever(SimpleNamespace(units=units),OnlineConfig(artifact_source='unused')).exception_context([e],8)
  self.assertEqual([x.unit_id for x in extra],['target'])
  self.assertFalse(extra[0].verified)

class SourceReadabilityTests(unittest.TestCase):
 def test_corrupt_ancestor_is_rejected_before_model_inference(self):
  from vn_labor_online.audit import deterministic_audit
  from vn_labor_online.retrieval import as_evidence
  unit={'unit_id':'unit','document_number':'TEST','document_id':'doc','article_number':'111',
   'kind':'PROVISION','text':'Nội dung khoản nguyên vẹn.','source_text':'Nội dung khoản nguyên vẹn.',
   'ancestor_context':'Điều 1l1. Tiêu đề.', 'source_url':'https://vbpl.vn/test',
   'provenance':{'file_id':'file'},'provenance_span':{'char_start':0,'char_end':25}}
  store=SimpleNamespace(units_by_id={'unit':unit},catalog_by_file_id={'file':{'catalog_status':'VERIFIED','source_url':'https://vbpl.vn/test'}},
    nodes_by_id={'doc':{},'unit':{'properties':{'article_number':'111'}}})
  checked=deterministic_audit(store,[as_evidence(unit,1,'bm25',0)],None)[0]
  self.assertFalse(checked.verified)
  self.assertIn('SOURCE_TEXT_QUALITY:SUSPECT_LEGAL_LOCATOR',checked.audit_issues)
  unit['ancestor_context']='Điều 111. Tiêu đề.'
  self.assertTrue(deterministic_audit(store,[as_evidence(unit,1,'bm25',0)],None)[0].verified)
 def test_equal_child_text_does_not_erase_a_different_inherited_scope(self):
  from tests.online.test_output_precision import rule
  from vn_labor_online.evidence import select_for_plan
  first=rule('a','88','1',text='Nội dung khoản giống nhau.').model_copy(update={'ancestor_context':'Nhóm áp dụng thứ nhất.'})
  second=rule('b','88','1',text='Nội dung khoản giống nhau.').model_copy(update={'ancestor_context':'Nhóm áp dụng thứ hai.'})
  selected,_=select_for_plan([first,second],EvidencePlan(mandatory_slots=['governing_rule']),None,False,10)
  self.assertEqual({item.unit_id for item in selected},{'a','b'})

class ResearcherFactGroundingTests(unittest.TestCase):
 def test_numeric_fact_requires_matching_role_and_unit(self):
  from vn_labor_online.researcher import _entailed
  for field,value,quote in [('age',20,'Tôi báo trước 20 ngày'),('worked_months',20,'Tôi báo trước 20 ngày'),
      ('notice_days',12,'Tôi đã làm việc 12 tháng'),('service_years',12,'Tôi làm việc 12 tháng'),
      ('travel_days',3,'Tôi 30 tuổi và có 3 hợp đồng')]:
   with self.subTest(field=field):self.assertFalse(_entailed(field,value,quote))
 def test_actual_numeric_facts_and_nonexact_durations(self):
  from vn_labor_online.researcher import _entailed
  for field,value,quote in [('age',20,'Tôi 20 tuổi'),('notice_days',20,'Tôi báo trước 20 ngày'),
       ('worked_months',12,'Tôi làm việc đủ 12 tháng'),('service_years',5,'Tôi làm đủ 5 năm')]:
   with self.subTest(field=field):self.assertTrue(_entailed(field,value,quote))
  self.assertFalse(_entailed('worked_months',12,'Tôi làm việc khoảng 12 tháng'))
 def test_numeric_strings_and_bools_are_not_verified_numbers(self):
  from vn_labor_online.researcher import _entailed
  self.assertFalse(_entailed('notice_days','20','Tôi báo trước 20 ngày'))
  self.assertFalse(_entailed('worked_months',True,'Tôi làm việc 1 tháng'))
  self.assertFalse(_entailed('notice_days',False,'Tôi nghỉ ngay'))
 def test_age_bound_is_not_an_exact_age_or_confirmed_adult(self):
  for words in ['dưới 18 tuổi','chưa đủ 18 tuổi','khoảng 18 tuổi','từ đủ 18 tuổi']:
   a=analyze(intake('Người lao động '+words+' có được làm thêm không?',[]))
   with self.subTest(words=words):self.assertNotIn('age',a.facts)
  a=analyze(intake('Tôi dưới 18 tuổi, muốn làm việc thì cần điều kiện gì?',[]))
  self.assertNotEqual(a.facts.get('minor'),False)
 def test_question_and_multiple_ages_do_not_become_one_confirmed_age(self):
  for text in ['Người lao động có đủ 18 tuổi không?', 'Anh A 16 tuổi, anh B 20 tuổi. Điều kiện làm việc thế nào?']:
   with self.subTest(text=text):self.assertNotIn('age',analyze(intake(text,[])).facts)

class ClaimScopeTests(unittest.TestCase):
 def test_monetary_penalty_requires_source_for_a_penalty_not_just_a_violated_duty(self):
  from vn_labor_online.claim_validation import semantic_issues
  e=Evidence(unit_id='rule',text='Không áp dụng nhiều hình thức kỷ luật đối với một hành vi.',retrieval_method='bm25')
  bad='Người sử dụng lao động sẽ bị phạt tiền từ 20.000.000 đồng đến 40.000.000 đồng.'
  self.assertIn('CLAIM_MONETARY_PENALTY_WITHOUT_SANCTION_SOURCE',semantic_issues(bad,[e]))
 def test_sourced_penalty_and_negative_limit_are_not_equivalent_to_invention(self):
  from vn_labor_online.claim_validation import semantic_issues
  e=Evidence(unit_id='sanction',text='Phạt tiền từ 10.000.000 đồng đến 20.000.000 đồng đối với hành vi đó.',retrieval_method='bm25')
  self.assertNotIn('CLAIM_MONETARY_PENALTY_WITHOUT_SANCTION_SOURCE',semantic_issues('Mức phạt tiền từ 10.000.000 đồng đến 20.000.000 đồng.',[e]))
  plain=Evidence(unit_id='rule',text='Quy định nghĩa vụ.',retrieval_method='bm25')
  self.assertNotIn('CLAIM_MONETARY_PENALTY_WITHOUT_SANCTION_SOURCE',semantic_issues('Chưa có căn cứ xác định mức phạt tiền 20.000.000 đồng.',[plain]))
 def test_unsupported_locator_does_not_poison_independent_supported_claims(self):
  from tests.online.test_output_precision import rule,pack
  from vn_labor_online.generation import LegalAdjudicator
  from vn_labor_online.config import AdjudicationConfig
  e=rule('source','88',text='Người sử dụng lao động phải thông báo cho người lao động bằng văn bản.')
  engine=LegalAdjudicator(AdjudicationConfig(mode='ollama'));engine.provider=Mock()
  engine.provider.structured.return_value={'claims':[
    {'text':'Điều 88 yêu cầu thông báo bằng văn bản.','evidence_ids':['source']},
    {'text':'Điều 89 quy định người lao động không được bảo vệ.','evidence_ids':['source']}]}
  draft,warnings=engine._generate(pack('Cần thực hiện nghĩa vụ gì?',[e]),False,[])
  self.assertEqual(len(draft.claims),1)
  self.assertNotIn('Điều 89',draft.answer_summary)
  self.assertIn('ADJUDICATION_UNSUPPORTED_LOCATOR_DROPPED',warnings)
 def test_real_cross_reference_in_cited_source_is_not_dropped(self):
  from tests.online.test_output_precision import rule,pack
  from vn_labor_online.audit import claim_reference_issues
  p=pack('Giải thích quy định.',[rule('source','88',text='Thực hiện nghĩa vụ theo Điều 99.')])
  self.assertFalse(claim_reference_issues('Nguồn dẫn chiếu Điều 99.',p.evidence))
 def test_unconfirmed_status_is_not_a_confirmed_disqualifying_fact(self):
  from vn_labor_online.claim_validation import semantic_issues
  e=Evidence(unit_id='rule',text='Người lao động khuyết tật có quyền theo nhóm áp dụng.',retrieval_method='bm25')
  bad='Người lao động chưa được xác nhận khuyết tật không thuộc trường hợp được hưởng quyền này.'
  self.assertIn('CLAIM_UNCERTAINTY_AS_NEGATIVE_FACT',semantic_issues(bad,[e]))
  good='Chưa được xác nhận tình trạng nên chưa thể kết luận người lao động không có quyền hưởng theo nhóm này.'
  self.assertNotIn('CLAIM_UNCERTAINTY_AS_NEGATIVE_FACT',semantic_issues(good,[e]))
 def test_qualified_source_does_not_support_a_blanket_prohibition(self):
  from vn_labor_online.claim_validation import semantic_issues
  e=Evidence(unit_id='rule',text='Không được ép buộc người lao động chi tiêu lương vào mua hàng hóa.',retrieval_method='bm25')
  for text in ['Yêu cầu mua hàng không được phép trong bất kỳ trường hợp nào.',
               'Việc mua hàng luôn luôn trái pháp luật.']:
   with self.subTest(text=text):
    self.assertIn('CLAIM_UNSUPPORTED_UNIVERSAL_SCOPE',semantic_issues(text,[e]))
 def test_supported_coercion_scope_and_disclosed_limit_are_kept(self):
  from vn_labor_online.claim_validation import semantic_issues
  e=Evidence(unit_id='rule',text='Không được ép buộc người lao động chi tiêu lương vào mua hàng hóa.',retrieval_method='bm25')
  for text in ['Công ty không được ép buộc người lao động mua hàng bằng tiền lương.',
               'Chưa thể khẳng định mọi yêu cầu mua hàng đều trái pháp luật trong mọi trường hợp.']:
   self.assertNotIn('CLAIM_UNSUPPORTED_UNIVERSAL_SCOPE',semantic_issues(text,[e]))
 def test_explicit_universal_source_can_support_same_scope(self):
  from vn_labor_online.claim_validation import semantic_issues
  e=Evidence(unit_id='rule',text='Nghiêm cấm hành vi đó trong mọi trường hợp.',retrieval_method='bm25')
  self.assertNotIn('CLAIM_UNSUPPORTED_UNIVERSAL_SCOPE',semantic_issues('Hành vi đó bị cấm trong mọi trường hợp.',[e]))

class RoutingParaphraseTests(unittest.TestCase):
 def test_group_rule_question_does_not_require_personal_pregnancy_details(self):
  q='Lao động nữ trong thời gian hành kinh được nghỉ mỗi ngày tối thiểu bao nhiêu phút theo Bộ luật Lao động? Thời gian này có được trả lương không?'
  a=analyze(intake(q,[]),'2026-09-15')
  self.assertFalse(any('mang thai' in text or 'Tình trạng' in text for text in a.missing_facts))
 def test_personal_employer_assessment_keeps_protection_fact_gate(self):
  q='Công ty đơn phương chấm dứt hợp đồng với tôi là lao động nữ. Có hợp pháp không?'
  a=analyze(intake(q,[]),'2026-09-15')
  self.assertTrue(any('mang thai' in text for text in a.missing_facts))
 def test_holiday_overlap_is_context_not_an_unasked_holiday_list(self):
  from vn_labor_online.taxonomy import profile_covers_issues
  for q in ['Ngày nghỉ hằng tuần trùng ngày lễ, Tết thì nghỉ bù thế nào?',
        'Nếu nghỉ hàng tuần trùng ngày lễ thì người lao động có được nghỉ bù không?']:
   a=analyze(intake(q,[]),'2026-09-15')
   with self.subTest(q=q):
    self.assertTrue(profile_covers_issues(a))
    self.assertEqual(len(a.answer_tasks),1)
    self.assertNotIn('public_holiday_rule',plan_evidence(a).slot_requirements)
 def test_separately_requested_holiday_list_is_preserved(self):
  a=analyze(intake('Liệt kê các ngày lễ được nghỉ và giải thích nghỉ bù khi nghỉ hằng tuần trùng ngày lễ.',[]),'2026-09-15')
  self.assertIn('LEAVE.PUBLIC_HOLIDAY',a.legal_subissues)
  self.assertIn('public_holiday_rule',plan_evidence(a).slot_requirements)
 def test_explicit_uncertainty_about_entitlement_requires_a_fact_not_a_negative_assumption(self):
  q='Tôi chưa được xác nhận là người khuyết tật. Công việc của tôi trong điều kiện bình thường, làm đủ 12 tháng. Có thể khẳng định ngay số ngày phép của tôi chỉ là 12 ngày không?'
  a=analyze(intake(q,[]),'2026-09-15')
  self.assertEqual(a.requested_outcome,'ASSESS_LEGALITY')
  self.assertIsNone(a.facts.get('disabled'))
  self.assertTrue(any('khuyết tật' in text for text in a.missing_facts))
 def test_personal_numeric_result_waits_for_decisive_facts(self):
  from vn_labor_online.analysis import personal_result_needs_facts
  a=analyze(intake('Tôi muốn nghỉ việc. Tôi phải báo trước bao lâu?',[]),'2026-09-15')
  self.assertTrue(a.missing_facts)
  self.assertTrue(personal_result_needs_facts(a.query_text))
  a=analyze(intake('Công ty thử việc tôi 50 ngày. Vậy có vượt thời gian được phép không?',[]),'2026-09-15')
  self.assertEqual(a.requested_outcome,'ASSESS_LEGALITY')
  self.assertTrue(a.missing_facts)
 def test_general_overview_can_still_explain_while_clarifying(self):
  from vn_labor_online.analysis import personal_result_needs_facts
  self.assertFalse(personal_result_needs_facts('Tôi muốn biết quy định chung, theo từng loại hợp đồng phải báo trước bao lâu?'))
 def test_private_transactions_do_not_enter_labour_retrieval(self):
  for text in ['Tôi bán nhà riêng thì cần nộp thuế gì?', 'Hợp đồng thuê nhà của tôi có hiệu lực không?',
               'Chia di sản thừa kế cần giấy tờ gì?', 'Đăng ký kết hôn ở cơ quan nào?']:
   with self.subTest(text=text):self.assertFalse(analyze(intake(text,[])).in_scope)
 def test_housing_or_tax_in_employment_context_is_not_rejected(self):
  for text in ['Công ty thuê nhà cho người lao động, khoản này tính thuế thu nhập cá nhân từ tiền lương thế nào?',
               'Người lao động có được nghỉ khi đăng ký kết hôn không?']:
   with self.subTest(text=text):self.assertTrue(analyze(intake(text,[])).in_scope)
 def test_night_work_aliases_do_not_add_negated_overtime_task(self):
  for phrase in ['ca đêm','ban đêm','giờ đêm','làm đêm']:
   a=analyze(intake('Tôi chỉ làm '+phrase+' trong giờ làm việc bình thường, không làm thêm giờ. Tôi được trả thêm tối thiểu bao nhiêu phần trăm?',[]),'2026-09-15')
   with self.subTest(phrase=phrase):
    self.assertIn('WAGE.NIGHT_PAY',a.legal_subissues)
    self.assertNotIn('WAGE.OVERTIME_PAY',a.legal_subissues)
    self.assertFalse(any('overtime' in task.topic_ids for task in a.answer_tasks))
 def test_actual_overtime_request_still_has_own_task(self):
  a=analyze(intake('Tôi làm ca đêm và làm thêm giờ. Tiền lương được tính thế nào?',[]),'2026-09-15')
  self.assertIn('WAGE.NIGHT_PAY',a.legal_subissues)
  self.assertIn('WAGE.OVERTIME_PAY',a.legal_subissues)
 def test_wage_disposal_phrases_route_without_creating_legal_facts(self):
  for phrase in ['bắt tôi dùng một phần lương','ép tôi sử dụng 20% tiền lương','buộc người lao động chi tiêu lương']:
   q='Doanh nghiệp '+phrase+' để mua hàng của họ. Có hợp pháp không?'
   a=analyze(intake(q,[]),'2026-09-15')
   with self.subTest(phrase=phrase):self.assertIn('WAGE.PAYMENT_DISPOSAL',a.legal_subissues)
 def test_extracted_job_group_always_has_exact_source_span(self):
  for phrase in ['yêu cầu trung cấp','cần cao đẳng','đòi hỏi trình độ trung cấp']:
   q='Tôi thử việc cho công việc '+phrase+'. Thử việc tối đa bao lâu?'
   a=analyze(intake(q,[]),'2026-09-15')
   with self.subTest(phrase=phrase):
    self.assertIn('probation_work_group',a.facts)
    fact=next(c for c in a.fact_candidates if c.field=='probation_work_group')
    self.assertEqual(fact.value,a.facts['probation_work_group'])
    self.assertEqual(q[fact.char_start:fact.char_end],fact.source_quote)

class GraphRecoveryTests(unittest.TestCase):
 def test_pipeline_recovers_through_unknown_seed_without_citing_it(self):
  import tempfile
  from pathlib import Path
  from tests.online.test_online_core import fixture
  from vn_labor_online.pipeline import OnlinePipeline
  from vn_labor_online.config import RetrievalConfig,GraphConfig
  from vn_labor_online.models import ApplicabilityDecision
  from vn_labor_online.retrieval import as_evidence
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);build=fixture(root)
   cfg=OnlineConfig(artifact_source=tmp,expected_build_id=build,trace_dir=str(root/'traces'),
      retrieval=RetrievalConfig(dense_enabled=False,issue_anchor_enabled=False,case_law_enabled=False,community_enabled=False),
      graph=GraphConfig(max_nodes=4,max_edges=5,max_hops=2,max_rounds=2))
   pipe=OnlinePipeline(cfg)
   try:
    seed=as_evidence(pipe.store.units_by_id['prov_1'],1,'bm25',1)
    pipe.retriever.bm25=Mock(return_value=[seed])
    def audit(items,*args,**kw):
     accepted=[];decisions=[]
     for item in items:
      unresolved=item.unit_id=='prov_1'
      decisions.append(ApplicabilityDecision(evidence_id=item.unit_id,relevant=True,supports_claim=True,
        conditions_status='UNKNOWN' if unresolved else 'NOT_APPLICABLE',exception_status='NOT_APPLICABLE',
        audit_status='UNRESOLVED' if unresolved else 'PASS'))
      if not unresolved:accepted.append(item)
     return accepted,decisions,[]
    pipe.applicability.audit=Mock(side_effect=audit)
    result=pipe.ask(QueryRequest(question='Quy định về tiền lương?',query_date='2026-09-15'))
    event=next(e for e in result.trace.events if e.get('event')=='graph_search_seeds')
    self.assertEqual(event['unresolved_search_only_ids'],['prov_1'])
    self.assertGreater(result.trace.retrieval_rounds,0)
    self.assertNotIn('prov_1',{c.evidence_id for c in result.citations})
    self.assertGreaterEqual(pipe.applicability.audit.call_count,2)
   finally:pipe.close()
 def test_unknown_applicability_can_seed_search_without_becoming_evidence(self):
  from vn_labor_online.graph import search_seeds
  from vn_labor_online.models import ApplicabilityDecision
  from vn_labor_online.evidence import build_verified_pack
  item=Evidence(unit_id='seed',text='Nguồn có dẫn chiếu.',retrieval_method='bm25',verified=True)
  decision=ApplicabilityDecision(evidence_id='seed',relevant=True,supports_claim=True,audit_status='UNRESOLVED',
    conditions_status='UNKNOWN',exception_status='UNKNOWN')
  self.assertEqual([x.unit_id for x in search_seeds([],[item],[decision],10)],['seed'])
  pack=build_verified_pack('Câu hỏi',None,{},state_for([],EvidencePlan(mandatory_slots=['governing_rule']),None),[item],[decision])
  self.assertFalse(pack.evidence)
 def test_hard_fail_irrelevance_and_unverified_source_never_seed(self):
  from vn_labor_online.graph import search_seeds
  from vn_labor_online.models import ApplicabilityDecision
  for verified,status,relevant,support in [(False,'UNRESOLVED',True,True),(True,'FAIL',True,True),
       (True,'UNRESOLVED',False,True),(True,'UNRESOLVED',True,False)]:
   item=Evidence(unit_id='seed',text='Nguồn.',retrieval_method='bm25',verified=verified)
   d=ApplicabilityDecision(evidence_id='seed',relevant=relevant,supports_claim=support,audit_status=status)
   self.assertFalse(search_seeds([],[item],[d],10))
 def test_graph_time_limit_covers_queue_preparation(self):
  from vn_labor_online.graph import GraphExplorer
  from vn_labor_online.config import GraphConfig
  edges=[{'id':str(i),'source':'seed','target':'node'+str(i),'type':'REFERENCES'} for i in range(100)]
  graph=GraphExplorer(SimpleNamespace(edges=edges,units_by_id={},nodes_by_id={}),GraphConfig())
  graph._score=Mock(return_value=(1,{}))
  with patch('vn_labor_online.graph.time.monotonic',side_effect=[0,.002,.003]):
   result=graph.expand_round(['seed'],['mandatory_reference'],'hỏi',{'seed'},{},10,10,wall_clock_ms=1)
  graph._score.assert_not_called()
  self.assertEqual(result[2]['stop_reason'],'TIME_BUDGET')

class RequestDateTests(unittest.TestCase):
 def test_full_contract_date_supplies_transition_fact_not_termination_date(self):
  q='Tôi ký hợp đồng ngày 10/05/2018 và dự định nghỉ việc ngày 02/08/2026. Cần áp dụng luật nào?'
  a=analyze(intake(q,[]))
  self.assertEqual(a.query_date,'2026-08-02')
  self.assertEqual(a.facts.get('contract_start_year'),2018)
  fact=next(c for c in a.fact_candidates if c.field=='contract_start_year')
  self.assertEqual(q[fact.char_start:fact.char_end],fact.source_quote)
  e=Evidence(unit_id='rule',text='Quy định chấm dứt hợp đồng.',kind='PROVISION',retrieval_method='bm25',verified=True)
  p=extend_plan_for_evidence(EvidencePlan(mandatory_slots=['governing_rule']),[e],a.facts,a.query_date)
  self.assertIn('transitional_rule',p.mandatory_slots)
 def test_unpublished_forecast_question_need_not_contain_if_or_will(self):
  from datetime import date
  from vn_labor_online.query_clock import unpublished_change_prediction
  self.assertTrue(unpublished_change_prediction('Tháng sau Chính phủ có chắc chắn tăng số ngày phép năm lên 20 ngày không?',
      '2026-11-01',date(2026,10,31)))
 def test_future_date_does_not_block_enacted_rule_or_personal_wage_question(self):
  from datetime import date
  from vn_labor_online.query_clock import unpublished_change_prediction
  for text in ['Theo nghị định đã ban hành, tháng sau mức hưởng của tôi là bao nhiêu?',
       'Tháng sau công ty có chắc chắn tăng lương theo hợp đồng cho tôi không?']:
   self.assertFalse(unpublished_change_prediction(text,'2026-11-01',date(2026,10,31)))
 def test_relative_date_uses_request_timestamp_not_later_wall_clock(self):
  from datetime import datetime,timezone
  env=intake('Hôm qua tôi thử việc. Thời gian thử việc là bao lâu?',[])
  env.received_at=datetime(2026,9,14,16,59,59,tzinfo=timezone.utc)
  self.assertEqual(analyze(env).query_date,'2026-09-13')
 def test_historical_event_date_is_independent_of_request_day(self):
  from datetime import datetime,timezone
  env=intake('Ngày 15/12/2020 tôi muốn nghỉ việc thì phải báo trước bao lâu?',[])
  env.received_at=datetime(2026,10,31,18,tzinfo=timezone.utc)
  self.assertEqual(analyze(env).query_date,'2020-12-15')
 def test_invalid_date_cannot_default_to_today(self):
  a=analyze(intake('Ngày 31/02/2026 tôi nghỉ việc có được không?',[]))
  self.assertIsNone(a.query_date)
  self.assertEqual(a.temporal_resolution,'AMBIGUOUS')

class ComponentBudgetTests(unittest.TestCase):
 def test_repeated_calls_share_allowance_and_reserve_generation(self):
  from vn_labor_online.runtime import request_budget,operation_budget,request_timeout,OperationBudgetExceeded
  clock=[100.0]
  with patch('vn_labor_online.runtime.time.monotonic',side_effect=lambda:clock[0]):
   with request_budget(180) as budget:
    # dataclass default_factory is bound at definition, so set the test clock explicitly.
    budget.started=100
    with operation_budget('auditor',50,45,60):
     self.assertEqual(request_timeout(300),45)
     clock[0]+=30
    with operation_budget('auditor',50,45,60):
     self.assertEqual(request_timeout(300),20)
     clock[0]+=19
    with operation_budget('auditor',50,45,60):
     self.assertEqual(request_timeout(300),1)
     clock[0]+=.5
    budget.operation_spent['auditor']=50
    with self.assertRaises(OperationBudgetExceeded):
     with operation_budget('auditor',50,45,60):self.fail('must not call model')
    self.assertGreater(budget.remaining(),60)
 def test_operation_timeout_restores_parent_and_never_cancels_request(self):
  from vn_labor_online.runtime import request_budget,operation_budget,request_timeout,checkpoint,OperationBudgetExceeded
  clock=[100.0]
  with patch('vn_labor_online.runtime.time.monotonic',side_effect=lambda:clock[0]):
   with request_budget(180) as budget:
    budget.started=100
    with self.assertRaises(OperationBudgetExceeded):
     with operation_budget('auditor',50,20,60):
      clock[0]+=21;checkpoint()
    self.assertFalse(budget.cancelled.is_set())
    self.assertGreater(request_timeout(180),150)
 def test_cancel_is_not_swallowed_by_per_item_auditor(self):
  from vn_labor_online.runtime import RequestStopped
  auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='ollama'))
  auditor.provider=Mock();auditor.provider.structured.side_effect=RequestStopped('REQUEST_CANCELLED')
  e=Evidence(unit_id='one',text='Nguồn.',retrieval_method='bm25')
  with self.assertRaises(RequestStopped):auditor.audit([e],'Hỏi?',['GENERAL'],{})
 def test_auditor_retains_completed_decisions_when_component_budget_expires(self):
  from vn_labor_online.runtime import OperationBudgetExceeded
  auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid',max_items=1,max_batches=3))
  auditor.provider=Mock();auditor._deterministic=Mock(return_value=([],[],[]))
  auditor._structured=Mock(side_effect=[{'decisions':{'one':{'relevant':True,'supports_claim':True,
    'conditions_status':'NOT_APPLICABLE','exception_status':'NOT_APPLICABLE'}}},OperationBudgetExceeded()])
  items=[Evidence(unit_id=uid,text='Nguồn.',retrieval_method='bm25') for uid in ['one','two','three']]
  accepted,decisions,warnings=auditor.audit(items,'Giải thích',['GENERAL'],{})
  self.assertEqual([e.unit_id for e in accepted],['one'])
  self.assertEqual(auditor._structured.call_count,2)
  self.assertTrue(all(d.audit_status=='UNRESOLVED' for d in decisions[1:]))
  self.assertIn('APPLICABILITY_COMPONENT_BUDGET_EXHAUSTED',warnings)

if __name__=='__main__':unittest.main()
