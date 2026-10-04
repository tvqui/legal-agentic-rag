from __future__ import annotations

import unittest
from pydantic import ValidationError

from vn_labor_online.analysis import analyze,intake
from vn_labor_online.audit import reference_audit
from vn_labor_online.config import GraphConfig
from vn_labor_online.evidence import extend_plan_for_evidence
from vn_labor_online.graph import GraphExplorer
from vn_labor_online.models import Claim,Evidence,EvidencePlan
from vn_labor_online.temporal import legal_regime_for,requires_transition_rule


class CompletionPhaseTests(unittest.TestCase):
    def test_single_historical_issue_does_not_force_complex_route(self):
        analysis=analyze(intake('Tôi nghỉ việc ngày 20/12/2020 có đúng quy định không?',[]),supplied_facts={
          'actor':'EMPLOYEE','contract_type':'INDEFINITE','notice_days':45,
          'notice_exception':False,'special_occupation':False})
        self.assertEqual(analysis.route.value,'STANDARD')
        self.assertEqual(analysis.temporal_intent,'HISTORICAL')

    def test_unknown_special_occupation_is_a_required_fact(self):
        query=('Tôi ký hợp đồng lao động không xác định thời hạn. Ngày 10/9/2026 tôi gửi thông báo nghỉ '
          'và nghỉ chính thức ngày 30/9/2026. Tôi không thuộc trường hợp được nghỉ không cần báo trước. '
          'Việc báo trước 20 ngày có đúng quy định không?')
        analysis=analyze(intake(query,[]))
        self.assertTrue(any('đặc thù' in question for question in analysis.missing_facts))

    def test_out_of_scope_is_detected_without_retrieval_hint(self):
        analysis=analyze(intake('Tội giết người bị xử lý hình sự như thế nào?',[]))
        self.assertFalse(analysis.in_scope)

    def test_temporal_regime_boundaries_are_half_open(self):
        self.assertEqual(legal_regime_for('2020-12-31'),'BLLD_2012')
        self.assertEqual(legal_regime_for('2021-01-01'),'BLLD_2019')
        self.assertTrue(requires_transition_rule(2020,'2021-01-01'))
        self.assertFalse(requires_transition_rule(2021,'2021-01-01'))

    def test_graph_hard_caps_are_schema_enforced(self):
        with self.assertRaises(ValidationError): GraphConfig(max_hops=3)
        with self.assertRaises(ValidationError): GraphConfig(max_nodes=16)

    def test_graph_cycle_guard_and_relation_allowlist(self):
        units=[{'unit_id':'a','text':'quy định nghỉ việc','kind':'PROVISION'},
          {'unit_id':'b','text':'sửa đổi quy định nghỉ việc','kind':'PROVISION'},
          {'unit_id':'c','text':'nút kế tiếp không phải quan hệ pháp lý','kind':'PROVISION'}]
        class Store:
            units_by_id={row['unit_id']:row for row in units}
            nodes_by_id={row['unit_id']:{'properties':{}} for row in units}
            edges=[{'id':'e1','source':'a','target':'b','type':'AMENDS'},
              {'id':'e2','source':'b','target':'a','type':'AMENDS'},
              {'id':'e3','source':'a','target':'c','type':'NEXT'}]
        seed=Evidence(unit_id='a',retrieval_method='seed',text='quy định nghỉ việc')
        added,stats=GraphExplorer(Store(),GraphConfig(max_nodes=3,max_hops=2,max_rounds=2)).expand(
          [seed],['amendment_history'],'nghỉ việc')
        self.assertEqual([item.unit_id for item in added],['b'])
        self.assertLessEqual(stats['nodes_visited'],3)

    def test_delegation_extends_evidence_plan(self):
        item=Evidence(unit_id='p',retrieval_method='exact',text='Chính phủ quy định chi tiết nội dung này.',
          source_text='Chính phủ quy định chi tiết nội dung này.',verified=True)
        plan=extend_plan_for_evidence(EvidencePlan(mandatory_slots=['governing_rule']),[item],{},None)
        self.assertIn('implementing_regulation',plan.mandatory_slots)

    def test_claim_audit_checks_references_against_claim_evidence(self):
        item=Evidence(unit_id='p40',retrieval_method='policy',document_id='d',document_number='45/2019/QH14',
          article_number='40',clause_number='2',text='Bồi thường tiền lương.',source_text='Bồi thường tiền lương.',
          source_url='https://example.test/law',verified=True)
        claim=Claim(claim_id='bad',text='Điều 7 Nghị định 145/2020/NĐ-CP quy định 120 ngày.',evidence_ids=['p40'])
        ok,issues=reference_audit('[p40]',[item],[],[claim])
        self.assertFalse(ok)
        self.assertTrue(any(issue.startswith('CLAIM_UNSUPPORTED_ARTICLE:7') for issue in issues))


if __name__=='__main__': unittest.main()
