import unittest
from vn_labor_online.analysis import analyze,intake
from vn_labor_online.models import FactCandidate
from vn_labor_online.researcher import _entailed,_verified_candidate

class FactAssertionBoundaryTests(unittest.TestCase):
    def facts(self,text):return analyze(intake(text,[])).facts
    def proposed(self,query,field,value,quote):
        start=query.index(quote)
        return _verified_candidate(FactCandidate(field=field,value=value,source_quote=quote,
            char_start=start,char_end=start+len(quote)),query)

    def test_negated_harassment_is_not_a_confirmed_exemption(self):
        for text in ['Tôi không bị quấy rối tình dục tại nơi làm việc. Tôi muốn nghỉ vì lý do cá nhân.',
                     'Tôi chưa rõ có bị quấy rối tình dục tại nơi làm việc không. Tôi muốn nghỉ việc.',
                     'Tôi không biết liệu có bị quấy rối tình dục tại nơi làm việc hay không.']:
            with self.subTest(text=text):
                facts=self.facts(text)
                self.assertNotEqual(facts.get('termination_basis'),'SEXUAL_HARASSMENT')
                self.assertIsNot(facts.get('notice_exception'),True)

    def test_asserted_harassment_still_routes_to_the_requested_rule(self):
        facts=self.facts('Tôi bị quấy rối tình dục tại nơi làm việc và muốn nghỉ ngay.')
        self.assertEqual(facts.get('termination_basis'),'SEXUAL_HARASSMENT')

    def test_uncertain_job_qualification_is_not_a_confirmed_category(self):
        for prefix in ['Tôi chưa biết liệu ','Tôi không rõ ','Tôi không chắc ','Tôi chưa xác định được ']:
            q=prefix+'công việc yêu cầu trình độ cao đẳng hay không. Thử việc tối đa bao lâu?'
            with self.subTest(prefix=prefix):self.assertNotIn('probation_work_group',self.facts(q))

    def test_conflicting_job_groups_are_not_flattened(self):
        q='Vị trí A là công việc yêu cầu trình độ cao đẳng; vị trí B là công việc yêu cầu trình độ trung cấp. Thử việc bao lâu?'
        self.assertNotIn('probation_work_group',self.facts(q))

    def test_training_costs_are_an_asserted_expense_not_a_legal_repayment_question(self):
        for q in ['Tôi có phải hoàn trả chi phí đào tạo không?',
                  'Tôi không biết có chi phí đào tạo không.',
                  'Tôi không phải hoàn trả chi phí đào tạo theo lời bạn tôi.']:
            with self.subTest(q=q):self.assertNotIn('training_costs',self.facts(q))
        self.assertIs(self.facts('Công ty có chi phí đào tạo cho tôi.')['training_costs'],True)
        self.assertIs(self.facts('Tôi xác nhận không có chi phí đào tạo.')['training_costs'],False)

    def test_researcher_cannot_strip_outer_negation_for_an_occupation(self):
        q='Tôi không làm nghề đặc thù và muốn tự nghỉ việc.'
        self.assertIsNone(self.proposed(q,'special_occupation',True,'nghề đặc thù'))

    def test_researcher_cannot_turn_an_unknown_or_negated_pregnancy_into_a_fact(self):
        for q in ['Tôi không mang thai.','Tôi chưa rõ có mang thai không.','Tôi không chắc mình đang mang thai.']:
            with self.subTest(q=q):self.assertIsNone(self.proposed(q,'protected_status','MATERNITY','mang thai'))

    def test_researcher_training_costs_require_polarity_and_boolean_type(self):
        self.assertFalse(_entailed('training_costs',False,'Công ty có chi phí đào tạo'))
        self.assertFalse(_entailed('training_costs','False','Không có chi phí đào tạo'))
        q='Tôi không biết có chi phí đào tạo không.'
        self.assertIsNone(self.proposed(q,'training_costs',True,'có chi phí đào tạo'))

    def test_incidental_company_name_does_not_prove_the_acting_party(self):
        self.assertFalse(_entailed('actor','EMPLOYER','Công ty A'))
        self.assertFalse(_entailed('actor','EMPLOYEE','Tôi bị công ty sa thải'))
        self.assertTrue(_entailed('actor','EMPLOYER','Công ty sa thải tôi'))

if __name__=='__main__':unittest.main()
