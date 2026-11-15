"""General source planning and bounded graph regressions; no live LLMs."""
import unittest
from types import SimpleNamespace as NS
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.config import GraphConfig
from vn_labor_online.graph import GraphExplorer
from vn_labor_online.models import LegalLocator

class ImplementingRequirementsTests(unittest.TestCase):
    def plan(self,q,date='2026-09-15'):
        return plan_evidence(analyze(intake(q,[],date),date))
    def test_time_paid_overtime_formula_has_operative_clause(self):
        p=self.plan('Tôi hưởng lương theo thời gian, làm thêm ngày thường. Xin công thức tính theo nghị định 145, không cần tính tiền.')
        loc=p.slot_requirements['overtime_implementing_formula'][0][0]
        self.assertEqual((loc.documents,loc.article,loc.clause),(['145/2020/NĐ-CP'],'55','1'))
        self.assertTrue(loc.exact_level)
    def test_plain_overtime_rate_does_not_force_formula(self):
        p=self.plan('Làm thêm vào ngày thường tối thiểu được trả bao nhiêu phần trăm?')
        self.assertNotIn('overtime_implementing_formula',p.slot_requirements)
    def test_old_question_does_not_acquire_2020_decree(self):
        p=self.plan('Tôi hưởng lương theo thời gian, làm thêm ngày thường. Nêu công thức tính.', '2020-06-20')
        self.assertNotIn('overtime_implementing_formula',p.slot_requirements)
    def test_night_formula_retains_explicit_hourly_base_reference(self):
        p=self.plan('Tôi hưởng lương theo thời gian làm ban đêm trong giờ bình thường, không làm thêm. Nêu công thức theo nghị định 145.')
        self.assertIn('night_implementing_formula',p.slot_requirements)
        loc=p.slot_requirements['night_hourly_wage_reference'][0][0]
        self.assertEqual((loc.article,loc.clause,loc.point),('55','1','a'))
        self.assertNotIn('overtime_implementing_formula',p.slot_requirements)
    def test_consent_contents_requires_every_point(self):
        p=self.plan('Công ty muốn tôi đồng ý làm thêm giờ; sự đồng ý phải bao gồm những nội dung gì?')
        groups=p.slot_requirements['overtime_consent_contents']
        self.assertEqual([g[0].point for g in groups],['a','b','c'])
    def test_guided_rest_rule_and_direct_discipline_prohibition(self):
        p=self.plan('Nghỉ giữa giờ ban đêm tối thiểu bao lâu theo hướng dẫn chi tiết?')
        self.assertEqual(p.slot_requirements['rest_break_implementing_rule'][0][0].article,'64')
        p=self.plan('Công ty có được phạt tiền hoặc cắt lương để kỷ luật tôi không?')
        loc=p.slot_requirements['discipline_financial_prohibition'][0][0]
        self.assertEqual((loc.article,loc.clause),('127','2'))

class LeaveAndMixedScopeTests(unittest.TestCase):
    def test_family_leave_does_not_create_exit_notice_gap(self):
        q='Bà nội qua đời, công ty cho tôi nghỉ theo chế độ nào và phải báo trước không?'
        a=analyze(intake(q,[],'2026-09-15'),'2026-09-15')
        self.assertNotIn('TERMINATION',a.legal_issues)
        self.assertNotIn('termination_conditions',plan_evidence(a).mandatory_slots)
    def test_independent_termination_task_is_preserved(self):
        q='Bà nội qua đời, tôi xin nghỉ việc riêng. Sau đó tôi muốn chấm dứt hợp đồng lao động thì cần báo trước bao lâu?'
        a=analyze(intake(q,[],'2026-09-15'),'2026-09-15')
        self.assertIn('TERMINATION',a.legal_issues)
    def test_rest_guidance_and_normal_emergency_consent_both_planned(self):
        q='Một ca làm đủ sáu giờ có ba giờ ban đêm, nghỉ giữa giờ tối thiểu bao lâu? Dẫn cả Bộ luật và hướng dẫn.'
        a=analyze(intake(q,[],'2026-09-15'),'2026-09-15')
        self.assertIn('rest_break_implementing_rule',plan_evidence(a).slot_requirements)
        q='Làm thêm thông thường có cần đồng ý không? Nếu để khắc phục thiên tai, bảo vệ tính mạng thì có khác không?'
        a=analyze(intake(q,[],'2026-09-15'),'2026-09-15')
        self.assertIn('ordinary_overtime_consent',plan_evidence(a).slot_requirements)

class MissingLocatorGraphTests(unittest.TestCase):
    def graph(self):
        units={
            'noise':dict(unit_id='noise',kind='PROVISION',document_number='B',article_number='7',clause_number='2',text='quy định tiền lương và thời giờ làm việc'),
            'target':dict(unit_id='target',kind='PROVISION',document_number='A',article_number='7',clause_number='2',text='Nguồn bổ sung được dẫn chiếu.'),
        }
        edges=[dict(id='e1',source='seed',target='noise',type='REFERENCES'),dict(id='e2',source='seed',target='target',type='REFERENCES')]
        return GraphExplorer(NS(edges=edges,units_by_id=units,nodes_by_id={}),GraphConfig())
    def expand(self,slots,gaps=['need']):
        return self.graph().expand_round(['seed'],gaps,'quy định tiền lương và thời giờ làm việc',{'seed'},{},1,3,requirement_slots=slots)[0]
    def test_missing_document_locator_beats_keyword_neighbour_under_budget(self):
        result=self.expand({'need':[[LegalLocator(documents=['A'],article='7',clause='2')]]})
        self.assertEqual([e.unit_id for e in result],['target'])
        self.assertFalse(result[0].verified)
        self.assertEqual(result[0].component_scores['missing_requirement_match'],1.)
    def test_satisfied_other_slot_does_not_promote_its_target(self):
        result=self.expand({'satisfied':[[LegalLocator(documents=['A'],article='7')]],'need':[]})
        self.assertEqual([e.unit_id for e in result],['noise'])
    def test_wrong_document_cannot_match_and_empty_gap_stays_empty(self):
        result=self.expand({'need':[[LegalLocator(documents=['C'],article='7')]]})
        self.assertEqual(result[0].component_scores['missing_requirement_match'],0.)
        self.assertFalse(self.expand({'need':[]},[]))


class EnumeratedReferenceTests(unittest.TestCase):
    def refs(self,text):
        from vn_labor_online.exception_references import exception_locators
        from vn_labor_online.models import Evidence
        return exception_locators(Evidence(unit_id='s',retrieval_method='fixture',kind='PROVISION',document_number='DEMO',article_number='11',source_text=text,text=text))
    def test_all_explicit_local_exceptions_survive_list_shorthand(self):
        refs=self.refs('Quy tắc chung, trừ trường hợp quy định tại khoản 1 Điều 73, khoản 2 Điều 81 và khoản 4 Điều 92 của Bộ luật này.')
        self.assertEqual({(x.article,x.clause) for x in refs},{('73','1'),('81','2'),('92','4')})
    def test_exception_list_after_an_excluded_population(self):
        refs=self.refs('Quy tắc chung, trừ hợp đồng của người quản lý và trường hợp quy định tại khoản 1 Điều 73, khoản 2 Điều 81 và khoản 4 Điều 92 của Bộ luật này.')
        self.assertEqual({(x.article,x.clause) for x in refs},{('73','1'),('81','2'),('92','4')})
    def test_foreign_and_plain_references_are_not_invented_exceptions(self):
        self.assertFalse(self.refs('Quy định tại khoản 1 Điều 73 và khoản 2 Điều 81 của Bộ luật này.'))
        self.assertFalse(self.refs('Trừ trường hợp tại khoản 1 Điều 73 và khoản 2 Điều 81 của luật khác.'))

if __name__=='__main__':unittest.main()
