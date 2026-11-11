import unittest
from vn_labor_online.claim_validation import (
    invalid_clause_locator,
    semantic_issues,
    _conditional_consequence_lost,
    fold
)
from vn_labor_online.models import (
    Claim,
    VerifiedEvidenceItem,
    Evidence,
    EvidencePlan,
    LegalLocator,
    AnswerTask,
    QueryAnalysis,
    Route
)
from vn_labor_online.analysis import analyze, intake, plan_evidence, missing_fact_questions
from vn_labor_online.answer_review import hard_issues, repair_required_computations
from vn_labor_online.period_answers import rule_periods
from vn_labor_online.tasks import assess_parts


class Full173P0RegressionsTest(unittest.TestCase):
    def test_gold_mr020_diem_number_locator_confusion(self):
        text = 'Theo quy định tại điểm 2 Điều 25 Bộ luật Lao động, thời gian thử việc không quá 60 ngày.'
        source = VerifiedEvidenceItem(
            evidence_id='prov_test',
            instrument_number='18/VBHN-VPQH',
            article='25',
            clause='2',
            point='',
            text='Không quá 60 ngày đối với công việc có chức danh nghề nghiệp cần trình độ chuyên môn, kỹ thuật từ cao đẳng trở lên.'
        )
        self.assertTrue(invalid_clause_locator(text))
        claim = Claim(claim_id='c1', text=text, evidence_ids=['prov_test'])
        issues = hard_issues(claim, [source])
        self.assertIn('CLAIM_CLAUSE_POINT_CONFUSION', issues)
        self.assertIn('CLAIM_LOCATOR_METADATA_MISMATCH', issues)

        correction = 'Không có điểm 2 Điều 25; đúng phải là khoản 2 Điều 25.'
        self.assertFalse(invalid_clause_locator(correction))
        corrected_claim = Claim(claim_id='c_corrected', text=correction, evidence_ids=['prov_test'])
        self.assertNotIn('CLAIM_LOCATOR_METADATA_MISMATCH', hard_issues(corrected_claim, [source]))
        wrong_clause = Claim(
            claim_id='c_wrong_clause',
            text='Theo khoản 3 Điều 25 Bộ luật Lao động, thời gian thử việc không quá 60 ngày.',
            evidence_ids=['prov_test']
        )
        self.assertIn('CLAIM_LOCATOR_METADATA_MISMATCH', hard_issues(wrong_clause, [source]))
        for text in (
            'Theo Điều 25, khoản 2 Bộ luật Lao động, thời gian thử việc không quá 60 ngày.',
            'Theo khoản 2, Điều 25 Bộ luật Lao động, thời gian thử việc không quá 60 ngày.',
        ):
            claim = Claim(claim_id='c_correct_order', text=text, evidence_ids=['prov_test'])
            self.assertNotIn('CLAIM_LOCATOR_METADATA_MISMATCH', hard_issues(claim, [source]))
        wrong_after_article = Claim(
            claim_id='c_wrong_after_article',
            text='Theo Điều 25, khoản 3 Bộ luật Lao động, thời gian thử việc không quá 60 ngày.',
            evidence_ids=['prov_test']
        )
        self.assertIn('CLAIM_LOCATOR_METADATA_MISMATCH', hard_issues(wrong_after_article, [source]))

    def test_scope03_dropped_qualifier_ma_thanh_vien(self):
        source_text = 'b) Phải có sự tham gia của tổ chức đại diện người lao động tại cơ sở mà người lao động đang bị xử lý kỷ luật là thành viên;'
        source = VerifiedEvidenceItem(
            evidence_id='prov_122_1b',
            instrument_number='18/VBHN-VPQH',
            article='122',
            clause='1',
            point='b',
            text=source_text
        )
        query = 'Thủ tục xử lý kỷ luật lao động cần những ai tham gia?'
        dropped_claim = 'Khi xử lý kỷ luật lao động, người sử dụng lao động phải có sự tham gia của tổ chức đại diện người lao động tại cơ sở.'
        claim_bad = Claim(claim_id='c_bad', text=dropped_claim, evidence_ids=['prov_122_1b'])
        issues_bad = hard_issues(claim_bad, [source], context_query=query)
        self.assertIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST', issues_bad)

        good_claim = 'Khi xử lý kỷ luật lao động, người sử dụng lao động phải có sự tham gia của tổ chức đại diện người lao động tại cơ sở mà người lao động đang bị xử lý kỷ luật là thành viên.'
        claim_good = Claim(claim_id='c_good', text=good_claim, evidence_ids=['prov_122_1b'])
        issues_good = hard_issues(claim_good, [source], context_query=query)
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST', issues_good)

    def test_synthetic_probe_negative_condition_confirmed_by_context(self):
        source = VerifiedEvidenceItem(
            evidence_id='prov_synth',
            text='Trường hợp hồ sơ không bị thất lạc thì bên nhận phải trả đủ chứng từ cho bên giao.'
        )
        query = 'Hồ sơ không bị thất lạc. Bên nhận có phải trả đủ chứng từ không?'
        claim_text = 'Bên nhận phải trả đủ chứng từ cho bên giao.'
        claim = Claim(claim_id='c_synth', text=claim_text, evidence_ids=['prov_synth'])
        issues = hard_issues(claim, [source], context_query=query)
        self.assertNotIn('CLAIM_CONDITIONAL_ANTECEDENT_LOST', issues)

    def test_fresh06_limited_facet_overbroad_legality(self):
        source = VerifiedEvidenceItem(
            evidence_id='prov_105',
            instrument_number='18/VBHN-VPQH',
            article='105',
            clause='2',
            text='Người sử dụng lao động có quyền quy định thời giờ làm việc theo giờ hoặc ngày hoặc tuần; trường hợp theo tuần thì thời giờ làm việc bình thường không quá 10 giờ trong 01 ngày và không quá 48 giờ trong 01 tuần.'
        )
        query = 'Tôi làm 10 giờ mỗi ngày theo cách bố trí thời giờ làm việc theo tuần; tổng cộng 48 giờ trong tuần và không có thời gian làm thêm. Chỉ vì quá 8 giờ trong một ngày thì có thể khẳng định công ty vi phạm không?'
        overbroad = 'Việc công ty bố trí thời giờ làm việc 10 giờ mỗi ngày và tổng cộng 48 giờ trong một tuần không vi phạm quy định pháp luật.'
        claim_bad = Claim(claim_id='c_bad', text=overbroad, evidence_ids=['prov_105'])
        issues_bad = hard_issues(claim_bad, [source], context_query=query)
        self.assertIn('CLAIM_LIMITED_FACET_AS_OVERALL_LEGALITY', issues_bad)

        bounded = 'Chỉ vì quá 8 giờ trong một ngày thì chưa thể khẳng định công ty vi phạm quy định pháp luật.'
        claim_good = Claim(claim_id='c_good', text=bounded, evidence_ids=['prov_105'])
        issues_good = hard_issues(claim_good, [source], context_query=query)
        self.assertNotIn('CLAIM_LIMITED_FACET_AS_OVERALL_LEGALITY', issues_good)

    def test_new02_single_act_discipline_citation_mismatch(self):
        claim_text = 'Việc công ty áp dụng đồng thời hai hình thức kỷ luật là khiển trách và kéo dài thời hạn nâng lương đối với cùng một hành vi vi phạm nội quy lao động là không đúng quy định pháp luật, vì mỗi hành vi vi phạm chỉ được áp dụng một hình thức kỷ luật tương ứng.'
        source_122_3 = VerifiedEvidenceItem(
            evidence_id='prov_122_3',
            instrument_number='45/2019/QH14',
            article='122',
            clause='3',
            text='Khi một người lao động đồng thời có nhiều hành vi vi phạm kỷ luật lao động thì chỉ áp dụng hình thức kỷ luật cao nhất tương ứng với hành vi vi phạm nặng nhất.'
        )
        claim_bad = Claim(claim_id='c_bad', text=claim_text, evidence_ids=['prov_122_3'])
        issues_bad = hard_issues(claim_bad, [source_122_3])
        self.assertIn('CLAIM_DISCIPLINE_SINGLE_ACT_CITATION_MISMATCH', issues_bad)

        source_122_2 = VerifiedEvidenceItem(
            evidence_id='prov_122_2',
            instrument_number='45/2019/QH14',
            article='122',
            clause='2',
            text='Không được áp dụng nhiều hình thức xử lý kỷ luật lao động đối với một hành vi vi phạm kỷ luật lao động.'
        )
        claim_good = Claim(claim_id='c_good', text=claim_text, evidence_ids=['prov_122_2'])
        issues_good = hard_issues(claim_good, [source_122_2])
        self.assertNotIn('CLAIM_DISCIPLINE_SINGLE_ACT_CITATION_MISMATCH', issues_good)

    def test_gold_td013_minimum_wage_authority_planning(self):
        query = 'Theo Bộ luật Lao động, cơ quan nào quyết định và công bố mức lương tối thiểu, dựa trên khuyến nghị của cơ quan nào?'
        analysis = analyze(intake(query, []), '2026-01-01')
        plan = plan_evidence(analysis)
        self.assertIn('minimum_wage_authority', plan.slot_requirements)
        locators = plan.slot_requirements['minimum_wage_authority'][0]
        self.assertTrue(any(loc.article == '91' and loc.clause == '4' for loc in locators))

    def test_tv003_repair_computation_does_not_duplicate_existing_amount(self):
        from vn_labor_online.models import AdjudicationDraft, VerifiedEvidencePack, EvidenceState
        expected = '6.800.000 đồng/tháng'
        source = VerifiedEvidenceItem(
            evidence_id='prov_26',
            instrument_number='18/VBHN-VPQH',
            article='26',
            text='Tiền lương của người lao động trong thời gian thử việc do hai bên thỏa thuận nhưng ít nhất phải bằng 85% mức lương của công việc đó.'
        )
        task = AnswerTask(
            task_id='t1',
            request_quote='Mức lương 8 triệu thì lương thử việc thấp nhất là bao nhiêu?',
            description='Lương thử việc',
            retrieval_query='thử việc lương',
            legal_subissues=['CONTRACT.PROBATION_PAY']
        )
        pack = VerifiedEvidencePack(
            query='Mức lương là 8 triệu đồng/tháng. Lương thử việc thấp nhất là bao nhiêu?',
            query_date='2026-01-01',
            facts={'salary_base_amount': 8000000, 'salary_unit': 'tháng'},
            coverage_state=EvidenceState(coverage=1.0, gaps=[], slots={}),
            evidence=[source],
            answer_tasks=[task]
        )
        initial_claim = Claim(
            claim_id='c1',
            text=f'Tiền lương thử việc ít nhất phải bằng 85% mức lương của công việc đó, tương ứng mức thấp nhất là {expected}.',
            evidence_ids=['prov_26']
        )
        draft = AdjudicationDraft(
            answer_summary='',
            claims=[initial_claim],
            applicable_law_versions=[],
            assumptions=[],
            limitations=[]
        )
        repaired = repair_required_computations(draft, pack, [task])
        self.assertEqual(len(repaired.claims), 1)
        self.assertEqual(repaired.claims[0].text.count(expected), 1)

    def test_tv012_assess_parts_no_empty_missing_partial(self):
        task = AnswerTask(
            task_id='t_prob',
            request_quote='Hợp đồng dưới 1 tháng có phải thử việc không?',
            description='Không áp dụng thử việc đối với HĐ dưới 1 tháng',
            retrieval_query='không thử việc dưới 1 tháng',
            legal_subissues=['CONTRACT.PROBATION_EXCLUSION']
        )
        analysis = QueryAnalysis(
            answer_tasks=[task],
            query_date='2026-01-01',
            legal_subissues=['CONTRACT.PROBATION_EXCLUSION'],
            legal_issues=['CONTRACT'],
            facts={},
            explicit_references=[],
            event_dates=[],
            requested_outcome='EXPLAIN',
            temporal_intent='EXPLICIT_DATE',
            missing_facts=[],
            route=Route.STANDARD,
            route_reason='fixture',
            query_text=task.request_quote
        )
        item = Evidence(
            unit_id='prov_24_3',
            document_number='18/VBHN-VPQH',
            article_number='24',
            clause_number='3',
            retrieval_method='fixture',
            provision_version_id='version_24_3',
            source_text='Không áp dụng thử việc đối với người lao động giao kết hợp đồng lao động có thời hạn dưới 01 tháng.',
            text='Không áp dụng thử việc đối với người lao động giao kết hợp đồng lao động có thời hạn dưới 01 tháng.',
            kind='PROVISION',
            official_source=True,
            source_catalog_status='VERIFIED',
            provision_temporal_verified=True,
            verified=True,
            authority_rank=1
        )
        claim = Claim(
            claim_id='c_prob',
            text='Không áp dụng thử việc đối với người lao động giao kết hợp đồng dưới 01 tháng.',
            evidence_ids=['prov_24_3']
        )
        semantic_review = {
            'status': 'PASS',
            'iterations': [{
                'coverage': [{
                    'task_id': 't_prob',
                    'status': 'ANSWERED',
                    'claim_ids': ['c_prob'],
                    'missing': ''
                }]
            }]
        }
        parts = assess_parts(analysis, [item], [claim], semantic_review, allow_fallback=False)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].answer_status, 'ANSWERED')
        self.assertEqual(parts[0].missing_requirements, [])

    def test_gold_td004_seniority_clarification_question(self):
        query = 'Tôi đang làm tại một doanh nghiệp, năm nay tôi được nghỉ bao nhiêu ngày phép năm?'
        missing = missing_fact_questions(['LEAVE'], 'ASSESS_LEGALITY', {'query_intent': 'ANNUAL_LEAVE_CALC'}, query, '2026-01-01')
        self.assertTrue(any('thâm niên' in q.lower() or 'thời gian' in q.lower() for q in missing), missing)


if __name__ == '__main__':
    unittest.main()
