from __future__ import annotations
import unittest
from types import SimpleNamespace

from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.taxonomy import taxonomy_exclusion,annual_leave_points,sanction_instrument_lookup
from vn_labor_online.generation import _annual_leave_answer
from vn_labor_online.answer_review import review_error_code
from vn_labor_online.errors import StructuredOutputError
from vn_labor_online.models import VerifiedEvidencePack
from tests.online.test_hard_question_regressions import _state,_verified


class Risk100Regressions(unittest.TestCase):
    def analyze(self,query): return analyze(intake(query,[]),'2026-09-01')

    def test_overlap_requires_both_base_categories_not_only_largest(self):
        query='Người khuyết tật làm nghề đặc biệt nặng nhọc đủ 12 tháng, có 10 năm thâm niên. Có được cộng 14 ngày với 16 ngày phép không?'
        analysis=self.analyze(query)
        groups=plan_evidence(analysis).slot_requirements['leave_base_rule']
        self.assertEqual({locator.point for group in groups for locator in group},{'b','c'})
        for point in ('b','c'):
            evidence=SimpleNamespace(document_number='18/VBHN-VPQH',article_number='113',clause_number='1',point_number=point)
            self.assertIsNone(taxonomy_exclusion(evidence,analysis.legal_subissues,analysis.facts))

    def test_nonoverlap_does_not_collect_unrelated_base_categories(self):
        facts={'query_intent':'ANNUAL_LEAVE_CALC','work_category':'SPECIAL_HEAVY'}
        self.assertEqual(annual_leave_points(facts),('c',))
        evidence=SimpleNamespace(document_number='18/VBHN-VPQH',article_number='113',clause_number='1',point_number='b')
        self.assertEqual(taxonomy_exclusion(evidence,['LEAVE.ANNUAL_LEAVE'],facts),'SUBISSUE_LEAVE_CATEGORY_MISMATCH')

    def test_disability_leave_question_does_not_request_all_disability_rights(self):
        queries=[
            'Người lao động khuyết tật đã làm đủ 12 tháng. Hỏi số ngày nghỉ hằng năm là bao nhiêu?',
            'Người khuyết tật làm nghề đặc biệt nặng nhọc đủ 12 tháng. Có được cộng 14 ngày phép vì khuyết tật với 16 ngày vì công việc hay không?',
        ]
        for query in queries:
            with self.subTest(query=query):
                tasks=self.analyze(query).answer_tasks
                self.assertTrue(tasks)
                self.assertNotIn('topic_disabled_workers',{t.task_id for t in tasks})
                self.assertTrue(all(t.legal_subissues for t in tasks))

    def test_separate_disability_rights_request_is_not_dropped(self):
        analysis=self.analyze('Người khuyết tật có bao nhiêu ngày nghỉ phép? Ngoài phép năm, người khuyết tật có những quyền lao động đặc thù nào?')
        self.assertIn('topic_disabled_workers',{t.task_id for t in analysis.answer_tasks})

    def test_overlap_draft_cites_both_variants_and_refuses_missing_comparator(self):
        facts={'query_intent':'ANNUAL_LEAVE_CALC','work_category':'SPECIAL_HEAVY','disabled':True,'worked_months':12}
        special=_verified('special','113','1','c','16 ngày làm việc với nghề đặc biệt nặng nhọc.')
        protected=_verified('protected','113','1','b','14 ngày làm việc đối với người khuyết tật.')
        pack=VerifiedEvidencePack(query='Người khuyết tật làm nghề đặc biệt nặng nhọc có cộng hai mức phép năm không?',
            facts=facts,coverage_state=_state(['special','protected']),evidence=[special,protected])
        draft=_annual_leave_answer(pack,True,[])
        self.assertEqual(set(draft.claims[0].evidence_ids),{'special','protected'})
        self.assertIn('16 ngày',draft.claims[0].text)
        self.assertNotIn('12, 14 và 16',draft.claims[0].text)
        self.assertIsNone(_annual_leave_answer(pack.model_copy(update={'evidence':[special]}),True,[]))

    def test_written_months_are_extracted_with_real_fact_provenance(self):
        for word,number in [('bốn',4),('tám',8),('mười một',11),('mười hai',12)]:
            query=f'Người lao động làm việc {word} tháng trong năm thì có bao nhiêu ngày nghỉ phép?'
            with self.subTest(word=word):
                analysis=self.analyze(query)
                self.assertEqual(analysis.facts.get('worked_months'),number)
                candidates=[c for c in analysis.fact_candidates if c.field=='worked_months']
                self.assertEqual(len(candidates),1)
                self.assertEqual(query[candidates[0].char_start:candidates[0].char_end],candidates[0].source_quote)

    def test_month_calendar_mentions_are_not_worked_duration(self):
        analysis=self.analyze('Tôi bắt đầu làm việc từ tháng tám năm 2025. Tôi có bao nhiêu ngày phép?')
        self.assertNotIn('worked_months',analysis.facts)

    def test_approximate_or_incomplete_duration_is_not_an_exact_month_count(self):
        for duration in ('chưa đủ mười hai','dưới 12','khoảng tám','hơn tám'):
            with self.subTest(duration=duration):
                analysis=self.analyze(f'Tôi làm việc {duration} tháng. Phép năm tính thế nào?')
                self.assertNotIn('worked_months',analysis.facts)

    def test_semantic_contract_failures_have_safe_actionable_codes(self):
        self.assertEqual(review_error_code(StructuredOutputError('coverage depends on an unproved claim')),
                         'COVERAGE_USES_UNSUPPORTED_CLAIM')
        self.assertEqual(review_error_code(StructuredOutputError('unanswered task requires explanation')),
                         'UNANSWERED_TASK_MISSING_EXPLANATION')
        self.assertEqual(review_error_code(StructuredOutputError('unknown cited source')),'UNKNOWN_CITED_SOURCE')

    def test_instrument_lookup_does_not_require_unrequested_fine_calculation(self):
        query='Thử việc trả dưới 85% lương thì cần kiểm tra văn bản xử phạt nào?'
        analysis=self.analyze(query)
        plan=plan_evidence(analysis)
        self.assertIn('probation_sanction',plan.slot_requirements)
        self.assertNotIn('sanction_subject_multiplier',plan.slot_requirements)
        self.assertNotIn('probation_remedy',plan.slot_requirements)
        self.assertNotIn('topic_remedies',{t.task_id for t in analysis.answer_tasks})

    def test_amount_or_remedy_request_keeps_complete_sanction_requirements(self):
        for suffix in ('và mức phạt bao nhiêu?', 'và phải khắc phục thế nào?', 'và thời hiệu xử phạt là gì?'):
            query='Trả lương thử việc dưới 85%, theo văn bản nào '+suffix
            with self.subTest(suffix=suffix):
                self.assertFalse(sanction_instrument_lookup(query))
                plan=plan_evidence(self.analyze(query))
                self.assertIn('sanction_subject_multiplier',plan.slot_requirements)

    def test_instrument_lookup_renders_cited_identity_without_unverified_amount(self):
        from vn_labor_online.profile_generation import render_profile
        pay=_verified('pay','26',text='Tiền lương thử việc ít nhất phải bằng 85% mức lương của công việc đó.')
        sanction=_verified('sanction','10','2','c','Trả lương trong thời gian thử việc thấp hơn 85% mức lương của công việc đó;')
        sanction=sanction.model_copy(update={'instrument_number':'12/2022/NĐ-CP'})
        pack=VerifiedEvidencePack(query='Người thử việc bị trả dưới 85% lương thì ngoài Bộ luật Lao động còn phải kiểm tra văn bản xử phạt nào?',
            query_date='2026-09-01',coverage_state=_state(['pay','sanction']),evidence=[pay,sanction])
        draft=render_profile(pack,True,[])
        self.assertIsNotNone(draft)
        self.assertIn('Nghị định 12/2022/NĐ-CP',draft.claims[0].text)
        self.assertEqual(draft.claims[0].evidence_ids,['sanction'])
        self.assertNotIn('hai lần',draft.answer_summary)

    def test_pregnancy_expiry_is_not_replaced_with_unstated_continued_employment(self):
        query='HĐLĐ hết hạn khi người lao động đang mang thai. Hợp đồng có tự động kéo dài không?'
        analysis=self.analyze(query)
        self.assertIn('TERMINATION.EXPIRY',analysis.legal_subissues)
        slots=plan_evidence(analysis).slot_requirements
        self.assertIn('expiry_rule',slots)
        self.assertIn('maternity_expiry_protection',slots)
        self.assertNotIn('term_contract_renewal',slots)
        self.assertEqual(slots['expiry_rule'][0][0].article,'34')
        self.assertEqual(slots['maternity_expiry_protection'][0][0].article,'137')

    def test_renewal_after_continued_work_still_gets_complete_rule_chain(self):
        slots=plan_evidence(self.analyze('HĐLĐ hết hạn nhưng tôi vẫn tiếp tục làm việc. Sau 30 ngày hợp đồng thuộc loại nào?')).slot_requirements
        self.assertIn('term_contract_renewal',slots)
        self.assertIn('renewal_exceptions',slots)

    def test_conversion_claim_must_keep_continued_work_condition(self):
        from vn_labor_online.claim_validation import semantic_issues
        source=_verified('renewal','20','2',text='Khi hợp đồng hết hạn mà người lao động vẫn tiếp tục làm việc thì trong thời hạn 30 ngày hai bên phải ký kết hợp đồng lao động mới.')
        bad='Hết 30 ngày mà hai bên không ký hợp đồng mới thì hợp đồng trở thành không xác định thời hạn.'
        good='Nếu người lao động vẫn tiếp tục làm việc sau khi hợp đồng hết hạn, hết 30 ngày không ký mới thì hợp đồng trở thành không xác định thời hạn.'
        self.assertIn('CLAIM_CONTRACT_CONTINUATION_CONDITION_LOST',semantic_issues(bad,[source]))
        self.assertNotIn('CLAIM_CONTRACT_CONTINUATION_CONDITION_LOST',semantic_issues(good,[source]))

    def test_recruitment_criterion_is_not_a_request_for_overtime_pay(self):
        analysis=self.analyze('Doanh nghiệp chỉ tuyển nữ vì cho rằng nữ có thể làm thêm giờ tốt hơn. Có hợp pháp không?')
        self.assertIn('EQUALITY',analysis.legal_issues)
        self.assertNotIn('WAGE',analysis.legal_issues)
        self.assertNotIn('Thời điểm phát sinh tiền lương là khi nào?',analysis.missing_facts)

    def test_remuneration_request_still_requires_wage_evidence(self):
        analysis=self.analyze('Người lao động làm thêm giờ thì tiền lương được tính như thế nào?')
        self.assertIn('WAGE',analysis.legal_issues)
        self.assertIn('WAGE.OVERTIME_PAY',analysis.legal_subissues)

    def test_combination_principle_does_not_demand_personal_month_count(self):
        from vn_labor_online.taxonomy import profile_covers_issues
        query='Người khuyết tật được 14 ngày phép và làm nghề đặc biệt nặng nhọc được 16 ngày; có được cộng thành 30 ngày không?'
        analysis=self.analyze(query)
        self.assertEqual(analysis.requested_outcome,'EXPLAIN')
        self.assertFalse(analysis.missing_facts)
        self.assertNotIn('worked_months',analysis.facts)
        self.assertTrue(profile_covers_issues(analysis))
        b=_verified('protected','113','1','b','14 ngày làm việc đối với người khuyết tật.')
        c=_verified('special','113','1','c','16 ngày làm việc đối với nghề đặc biệt nặng nhọc.')
        pack=VerifiedEvidencePack(query=query,facts=analysis.facts,evidence=[b,c],coverage_state=_state(['protected','special']))
        draft=_annual_leave_answer(pack,True,[])
        self.assertIn('Không cộng',draft.answer_summary)
        self.assertIn('khi làm đủ 12 tháng',draft.answer_summary)
        self.assertNotIn('0 năm',draft.answer_summary)

    def test_personal_total_calculation_still_requires_missing_worked_months(self):
        analysis=self.analyze('Tôi là người khuyết tật làm công việc đặc biệt nặng nhọc. Tổng số ngày phép năm tôi được hưởng là bao nhiêu?')
        self.assertTrue(any('bao nhiêu tháng' in question for question in analysis.missing_facts))

    def test_conversion_condition_can_be_in_the_explicit_question_context(self):
        from vn_labor_online.claim_validation import semantic_issues
        source=_verified('renewal','20','2',text='Khi hợp đồng hết hạn mà người lao động vẫn tiếp tục làm việc thì trong thời hạn 30 ngày hai bên phải ký kết hợp đồng lao động mới.')
        claim='Hết 30 ngày không ký hợp đồng mới thì hợp đồng trở thành không xác định thời hạn.'
        context='HĐLĐ hết hạn nhưng NLĐ vẫn tiếp tục làm việc. Sau 30 ngày hợp đồng thế nào?'
        self.assertNotIn('CLAIM_CONTRACT_CONTINUATION_CONDITION_LOST',semantic_issues(claim,[source],context_query=context))
        negative='HĐLĐ hết hạn và NLĐ không tiếp tục làm việc. Sau 30 ngày hợp đồng thế nào?'
        self.assertIn('CLAIM_CONTRACT_CONTINUATION_CONDITION_LOST',semantic_issues(claim,[source],context_query=negative))
        past='Tôi đi làm từ năm 2022. Hợp đồng nay hết hạn. Sau 30 ngày hợp đồng thế nào?'
        self.assertIn('CLAIM_CONTRACT_CONTINUATION_CONDITION_LOST',semantic_issues(claim,[source],context_query=past))


if __name__=='__main__': unittest.main()
