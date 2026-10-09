from __future__ import annotations
import unittest
from unittest.mock import Mock
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.config import ApplicabilityConfig,AdjudicationConfig
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.claim_validation import semantic_issues
from tests.online.test_output_precision import rule,pack

def analysis(q,date='2025-01-01'):
    return analyze(intake(q,[]),date)

class V3CorrectionTests(unittest.TestCase):
    def test_original_diploma_synonyms(self):
        for q in ('Công ty yêu cầu ứng viên nộp bản gốc bằng đại học và giữ đến khi nghỉ việc. Điều này có hợp pháp không?',
          'NSDLĐ giữ bản gốc văn bằng của NLĐ có hợp pháp không?',
          'Công ty thu giữ bằng tốt nghiệp bản gốc của tôi.'):
            with self.subTest(q=q):
                a=analysis(q)
                self.assertIn('CONTRACT.PROHIBITED_ACTS',a.legal_subissues)
                self.assertNotIn('TERMINATION',a.legal_issues)
                self.assertEqual([g[0].clause for g in plan_evidence(a).slot_requirements['prohibited_contract_acts']],['1'])

    def test_incidental_exit_does_not_erase_real_independent_issue(self):
        a=analysis('Công ty giữ bản gốc văn bằng. Tôi muốn nghỉ việc và công ty yêu cầu báo trước 45 ngày; quy định thế nào?')
        self.assertIn('CONTRACT.PROHIBITED_ACTS',a.legal_subissues)
        self.assertIn('TERMINATION',a.legal_issues)
        self.assertIn('notice_requirement',plan_evidence(a).mandatory_slots)

    def test_copy_is_not_original(self):
        a=analysis('Ứng viên nộp bản sao bằng tốt nghiệp khi tuyển dụng.')
        self.assertNotIn('CONTRACT.PROHIBITED_ACTS',a.legal_subissues)

    def test_relationship_names_and_disclaimers(self):
        for q in ('Tôi ký hợp đồng cộng tác viên, mỗi tháng nhận lương và chịu quản lý của công ty. Có phải quan hệ lao động không?',
          'Hợp đồng ghi đây không phải hợp đồng lao động dù vẫn làm việc có trả công và chịu giám sát. Có đúng không?'):
            with self.subTest(q=q): self.assertIn('CONTRACT.RELATIONSHIP_QUALIFICATION',analysis(q).legal_subissues)

    def test_probation_numeric_duration(self):
        for q in ('Công ty cho tôi thử việc 60 ngày. Có đúng luật không?', 'Thử việc 30 ngày có hợp pháp không?'):
            with self.subTest(q=q): self.assertIn('CONTRACT.PROBATION_DURATION',analysis(q).legal_subissues)

    def test_repeat_probation_has_source_intro(self):
        a=analysis('Công ty cho NLĐ thử việc hai lần cho cùng một công việc nhưng gọi lần hai là giai đoạn đánh giá. Có hợp pháp không?')
        self.assertIn('CONTRACT.PROBATION_REPEAT',a.legal_subissues)
        p=plan_evidence(a); loc=p.slot_requirements['probation_once'][0][0]
        self.assertEqual((loc.article,loc.clause),('25',None)); self.assertTrue(loc.exact_level)

    def test_old_repeat_is_article_27(self):
        a=analysis('Thử việc lần thứ hai cùng công việc có hợp pháp không?','2020-12-15')
        loc=plan_evidence(a).slot_requirements['probation_once'][0][0]
        self.assertEqual(loc.article,'27'); self.assertEqual(loc.documents,['10/2012/QH13'])

    def test_probation_pay_sanction_requires_both_instruments(self):
        a=analysis('Thử việc trả lương dưới 85% bị xử phạt theo nghị định nào?')
        self.assertIn('CONTRACT.PROBATION_SANCTION',a.legal_subissues)
        p=plan_evidence(a)
        self.assertIn('probation_pay',p.slot_requirements)
        self.assertIn('probation_sanction',p.slot_requirements)
        self.assertIn('sanction_subject_multiplier',p.slot_requirements)
        self.assertIn('probation_remedy',p.slot_requirements)

    def test_no_2022_sanction_in_2020(self):
        p=plan_evidence(analysis('Thử việc trả dưới 85% bị xử phạt thế nào?','2020-12-15'))
        self.assertFalse(any('12/2022/NĐ-CP' in l.documents for groups in p.slot_requirements.values() for g in groups for l in g))
        self.assertIn('sanction_rule',p.mandatory_slots)

    def test_harassment_legal_classification_not_mandatory(self):
        a=analysis('Người lao động bị quấy rối tình dục tại nơi làm việc và nghỉ ngay. Công ty cho là trái pháp luật. Có đúng không?')
        self.assertTrue(a.facts['notice_exception'])
        self.assertNotIn('legal_classification',plan_evidence(a).mandatory_slots)
        self.assertNotIn('legal_consequences',plan_evidence(a).mandatory_slots)

    def test_mutual_agreement_not_unlawful_trigger(self):
        a=analysis('Hai bên thỏa thuận chấm dứt HĐLĐ vào ngày mai. Có tự động là trái pháp luật do không đủ 45 ngày không?')
        self.assertEqual(a.facts['query_intent'],'MUTUAL_TERMINATION')
        self.assertNotIn('legal_classification',plan_evidence(a).mandatory_slots)

    def test_material_effect_accepts_abbreviation(self):
        for s in ('ảnh hưởng trực tiếp đến việc thực hiện HĐLĐ','ảnh hưởng tới thực hiện hợp đồng lao động'):
            a=analysis('D ký HĐLĐ. Công ty cung cấp thông tin không trung thực khi giao kết và '+s+'. D nghỉ ngay, có đúng không?')
            with self.subTest(s=s):
                self.assertTrue(a.facts.get('misinformation_material_effect'))
                self.assertFalse(a.missing_facts)

    def test_material_effect_negation_is_not_established(self):
        a=analysis('Công ty cung cấp thông tin không trung thực khi giao kết nhưng không ảnh hưởng đến việc thực hiện HĐLĐ. Tôi nghỉ ngay có đúng không?')
        self.assertIsNot(a.facts.get('misinformation_material_effect'),True)
        self.assertTrue(a.missing_facts)

    def test_material_effect_question_is_not_a_fact(self):
        a=analysis('Công ty cung cấp thông tin không trung thực khi giao kết. Có ảnh hưởng trực tiếp đến việc thực hiện HĐLĐ không? Tôi muốn nghỉ ngay.')
        self.assertIsNot(a.facts.get('misinformation_material_effect'),True)

    def test_comparison_preserves_every_requested_mechanism(self):
        a=analysis('Làm sao phân biệt thực tập, tập nghề, thử việc và HĐLĐ?')
        self.assertIn('TRAINING.RELATIONSHIP_COMPARISON',a.legal_subissues)
        self.assertNotIn('contract_type',a.facts)
        locs=[l.article for gs in plan_evidence(a).slot_requirements.values() for g in gs for l in g]
        for article in ('13','24','26','61'): self.assertIn(article,locs)

    def test_intern_pay_explain_still_asks_relationship(self):
        a=analysis('Sinh viên thực tập ba tháng, trực tiếp làm sản phẩm cho công ty. Có bắt buộc trả lương không và theo cơ chế nào?')
        self.assertTrue(any('chương trình của trường' in q for q in a.missing_facts))

    def test_known_apprentice_does_not_repeat_classification_question(self):
        a=analysis('Công ty tuyển tôi vào tập nghề để làm việc cho mình. Tôi trực tiếp tham gia lao động, có được trả lương không?')
        self.assertFalse(a.missing_facts)

    def test_generic_relevance_is_not_support(self):
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig())
        item=rule('wrong','36','2',text='Người sử dụng lao động báo trước cho người lao động.')
        accepted,decisions,_=auditor.audit([item],'Công ty có được cho thử việc lần thứ hai cho cùng công việc không?',['CONTRACT'],{},'EXPLAIN')
        self.assertFalse(accepted)
        self.assertNotEqual(decisions[0].audit_status,'PASS')

    def test_exact_lookup_remains_supported(self):
        item=rule('lookup','1',text='Điều 1. Phạm vi điều chỉnh.').model_copy(update={'retrieval_method':'exact'})
        accepted,_,_=LegalApplicabilityAuditor(ApplicabilityConfig()).audit([item],'Điều 1 Bộ luật Lao động quy định gì?',['CONTRACT'],{},'LOOKUP')
        self.assertEqual(len(accepted),1)

    def test_independent_uncovered_issue_keeps_legacy_gate(self):
        p=plan_evidence(analysis('Thời gian thử việc tối đa là bao lâu, và tranh chấp đó có phải hòa giải trước khi ra tòa án không?'))
        self.assertIn('mandatory_reference',p.mandatory_slots)

    def test_false_probation_repetition_claim_is_rejected(self):
        item=rule('intro','25',text='Chỉ được thử việc một lần đối với một công việc.')
        for text in ('Không có quy định cấm thử việc nhiều lần cho cùng một công việc.',
          'Thử việc hai lần cùng một công việc là hợp pháp.'):
            with self.subTest(text=text): self.assertIn('CLAIM_PROBATION_REPEAT_NOT_SUPPORTED',semantic_issues(text,[item]))

    def test_valid_once_claim_not_rejected(self):
        self.assertNotIn('CLAIM_PROBATION_REPEAT_NOT_SUPPORTED',semantic_issues('Chỉ được thử việc một lần đối với một công việc.',[rule('intro','25',text='Chỉ được thử việc một lần đối với một công việc.')]))

    def test_repeat_answer_skips_model_and_preserves_condition(self):
        items=[rule('intro','25',text='Thời gian thử việc chỉ được thử việc một lần đối với một công việc.')]
        engine=LegalAdjudicator(AdjudicationConfig()); engine.provider=Mock()
        draft,_=engine.generate(pack('Công ty cho thử việc hai lần cho cùng một công việc, gọi lần hai là đánh giá. Có hợp pháp không?',items),False)
        engine.provider.structured.assert_not_called()
        self.assertIn('một lần',draft.answer_summary)
        self.assertIn('thực chất',draft.answer_summary)

    def test_probation_pay_numeric_conclusion(self):
        item=rule('pay','26',text='Tiền lương thử việc ít nhất bằng 85% mức lương của công việc đó.')
        draft,_=LegalAdjudicator(AdjudicationConfig()).generate(pack('Tôi thử việc được trả 80% mức lương công việc đó. Có đúng không?',[item]),False)
        self.assertIn('80%',draft.answer_summary)
        self.assertIn('thấp hơn',draft.answer_summary)

    def test_original_diploma_answer_does_not_need_deposit(self):
        item=rule('original','17','1',text='Giữ bản chính giấy tờ tùy thân, văn bằng, chứng chỉ của người lao động.')
        engine=LegalAdjudicator(AdjudicationConfig()); engine.provider=Mock()
        draft,_=engine.generate(pack('Công ty giữ bản gốc văn bằng đến khi nghỉ việc. Có hợp pháp không?',[item]),False)
        engine.provider.structured.assert_not_called()
        self.assertIn('bị cấm',draft.answer_summary)

    def test_missing_repeat_intro_never_yields_curated_conclusion(self):
        engine=LegalAdjudicator(AdjudicationConfig())
        draft,_=engine.generate(pack('Thử việc hai lần cùng một công việc có hợp pháp không?',[rule('other','25','2',text='Không quá 60 ngày.')]),False)
        self.assertNotIn('thực chất vẫn là thử việc',draft.answer_summary)

    def test_hybrid_explanation_uses_semantic_audit_for_unknown_rule(self):
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid'))
        auditor.provider=Mock()
        auditor.provider.structured.return_value={'decisions':{'w':{'relevant':True,'supports_claim':True,'conditions_status':'NOT_APPLICABLE','exception_status':'NOT_APPLICABLE'}}}
        accepted,decisions,_=auditor.audit([rule('w','90',text='Tiền lương là khoản người sử dụng lao động trả cho người lao động.')],'Giải thích tiền lương.',['WAGE'],{},'EXPLAIN')
        self.assertEqual([i.unit_id for i in accepted],['w'])
        auditor.provider.structured.assert_called_once()
        self.assertIn('MODEL_APPLICABILITY_PASS',decisions[0].reasons)

    def test_unknown_generic_support_stays_unresolved_on_provider_error(self):
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig(mode='hybrid'))
        auditor.provider=Mock();auditor.provider.structured.side_effect=RuntimeError('offline test')
        accepted,decisions,warnings=auditor.audit([rule('w','90',text='Tiền lương.')],'Giải thích tiền lương.',['WAGE'],{},'EXPLAIN')
        self.assertFalse(accepted);self.assertEqual(decisions[0].audit_status,'UNRESOLVED')

    def test_personal_diploma_is_not_required_job_qualification(self):
        a=analysis('Tôi tốt nghiệp cao đẳng và công ty cho thử việc 60 ngày. Có hợp pháp không?')
        self.assertNotIn('probation_work_group',a.facts)

    def test_explicit_required_job_qualification_is_recorded(self):
        a=analysis('Công việc yêu cầu trình độ cao đẳng trở lên, công ty cho tôi thử việc 90 ngày. Có hợp pháp không?')
        self.assertEqual(a.facts['probation_work_group'],'COLLEGE')
        self.assertTrue(any(c.field=='probation_work_group' and c.verified for c in a.fact_candidates))

    def test_known_job_duration_has_supported_comparison(self):
        texts=['Không quá 180 ngày đối với công việc quản lý doanh nghiệp.', 'Không quá 60 ngày đối với công việc cần trình độ cao đẳng trở lên.', 'Không quá 30 ngày đối với công việc cần trình độ trung cấp.', 'Không quá 06 ngày làm việc đối với công việc khác.']
        items=[rule(str(i),'25',str(i),text=t) for i,t in enumerate(texts,1)]
        q='Công việc yêu cầu trình độ cao đẳng trở lên, công ty cho tôi thử việc 90 ngày. Có hợp pháp không?'
        a=analysis(q)
        draft,_=LegalAdjudicator(AdjudicationConfig()).generate(pack(q,items,a.facts),False)
        self.assertIn('90 ngày vượt mức tối đa 60 ngày',draft.answer_summary)

    def test_calendar_and_working_days_not_silently_compared(self):
        texts=['Không quá 180 ngày đối với công việc quản lý doanh nghiệp.', 'Không quá 60 ngày đối với công việc cần trình độ cao đẳng trở lên.', 'Không quá 30 ngày đối với công việc cần trình độ trung cấp.', 'Không quá 06 ngày làm việc đối với công việc khác.']
        q='Tôi làm công việc khác, được thử việc 10 ngày. Có hợp pháp không?'
        items=[rule(str(i),'25',str(i),text=t) for i,t in enumerate(texts,1)]
        draft,_=LegalAdjudicator(AdjudicationConfig()).generate(pack(q,items,analysis(q).facts),False)
        self.assertNotIn('10 ngày vượt mức tối đa 6',draft.answer_summary)

    def test_historical_comparison_does_not_require_current_pay_clause(self):
        p=plan_evidence(analysis('Phân biệt thực tập, tập nghề, thử việc và HĐLĐ.','2020-12-15'))
        self.assertEqual(p.slot_requirements['comparison_training'][-1][0].clause,'4')

    def test_negated_job_qualification_not_treated_as_fact(self):
        for q in ('Công việc không yêu cầu trình độ cao đẳng, công ty thử việc 60 ngày có hợp pháp không?',
          'Tôi không làm công việc quản lý doanh nghiệp, được thử việc 90 ngày. Có hợp pháp không?',
          'Tôi không phải công nhân kỹ thuật, được thử việc 30 ngày có hợp pháp không?'):
            with self.subTest(q=q): self.assertNotIn('probation_work_group',analysis(q).facts)

    def test_unrelated_negation_cannot_hide_false_repeat_claim(self):
        text='Không được phép giữ bản chính văn bằng. Thử việc hai lần cho cùng một công việc là hợp pháp.'
        self.assertIn('CLAIM_PROBATION_REPEAT_NOT_SUPPORTED',semantic_issues(text,[rule('once','25',text='Chỉ được thử việc một lần đối với một công việc.')]))

    def test_pay_and_written_month_duration_are_both_planned(self):
        a=analysis('Công ty trả 80% mức lương chính thức trong hai tháng thử việc. Có hợp pháp không?')
        self.assertIn('CONTRACT.PROBATION_PAY',a.legal_subissues)
        self.assertIn('CONTRACT.PROBATION_DURATION',a.legal_subissues)
        p=plan_evidence(a)
        self.assertIn('probation_pay',p.slot_requirements)
        self.assertIn('probation_duration',p.slot_requirements)

    def test_minimum_regional_wage_not_assumed_to_be_job_wage(self):
        q='Tôi thử việc được trả 80% mức lương tối thiểu vùng. Có đúng không?'
        d,_=LegalAdjudicator(AdjudicationConfig()).generate(pack(q,[rule('pay','26',text='Tiền lương thử việc ít nhất bằng 85% mức lương của công việc đó.')]),False)
        self.assertNotIn('tỷ lệ 80%',d.answer_summary)
