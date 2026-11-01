import unittest
from vn_labor_online.analysis import analyze,intake,_notice_exception_fact
from vn_labor_online.models import FactCandidate
from vn_labor_online.researcher import _verified_candidate

class NoticePolarityTests(unittest.TestCase):
 def test_negative_operator_cannot_be_lost_inside_exemption(self):
  for phrase in ['Tôi không được miễn báo trước.', 'Tôi chưa được miễn thời hạn báo trước.',
    'Tôi chẳng thuộc diện được nghỉ không cần báo trước.',
    'Tôi không thuộc trường hợp được miễn báo trước.',
    'Tôi không có bất kỳ tình tiết nào thuộc trường hợp được nghỉ không cần báo trước.',
    'Tôi không thuộc trường hợp không cần báo trước.', 'Tôi không thuộc trường hợp miễn báo trước.']:
   with self.subTest(phrase=phrase):
    a=analyze(intake(phrase,[]));self.assertIs(a.facts.get('notice_exception'),False)
    candidates=[c for c in a.fact_candidates if c.field=='notice_exception']
    self.assertTrue(candidates)
    self.assertTrue(candidates[0].source_quote.lower().startswith(('không','chưa','chẳng')))
    self.assertEqual(a.query_text[candidates[0].char_start:candidates[0].char_end],candidates[0].source_quote)
 def test_internal_no_notice_does_not_invert_positive_exemption(self):
  for phrase in ['Tôi được nghỉ không cần báo trước.', 'Tôi được quyền nghỉ không cần báo trước.',
    'Tôi thuộc trường hợp được miễn báo trước.', 'Tôi không cần báo trước.', 'Tôi thuộc diện miễn báo trước.']:
   with self.subTest(phrase=phrase):self.assertIs(analyze(intake(phrase,[])).facts.get('notice_exception'),True)
 def test_questions_and_uncertainty_are_not_confirmed_exemptions(self):
  for phrase in ['Tôi có được miễn báo trước không?', 'Tôi chưa rõ có thuộc trường hợp được miễn báo trước không.',
    'Liệu tôi được nghỉ không cần báo trước?', 'Trường hợp nào được nghỉ không cần báo trước?',
    'Tôi không biết mình được miễn báo trước hay không.']:
   with self.subTest(phrase=phrase):self.assertNotIn('notice_exception',analyze(intake(phrase,[])).facts)
 def test_unmarked_contradiction_cannot_choose_an_exemption(self):
  q='Tôi được miễn báo trước. Tôi không thuộc trường hợp được miễn báo trước.'
  self.assertNotIn('notice_exception',analyze(intake(q,[])).facts)
 def test_researcher_cannot_quote_away_an_outer_negation(self):
  q='Tôi không được miễn báo trước.';quote='được miễn báo trước'
  candidate=FactCandidate(field='notice_exception',value=True,source_quote=quote,
    char_start=q.index(quote),char_end=q.index(quote)+len(quote))
  self.assertIsNone(_verified_candidate(candidate,q))
 def test_researcher_can_preserve_full_negative_statement(self):
  q='Tôi không được miễn báo trước.';quote='không được miễn báo trước'
  candidate=FactCandidate(field='notice_exception',value=False,source_quote=quote,
    char_start=q.index(quote),char_end=q.index(quote)+len(quote))
  self.assertTrue(_verified_candidate(candidate,q).verified)
 def test_negative_notice_case_has_no_false_exemption_or_missing_fact(self):
  q=('Tôi ký hợp đồng không xác định thời hạn. Tôi không làm công việc đặc thù, nghỉ vì lý do cá nhân, '
    'không được miễn báo trước. Tôi chỉ báo trước 17 ngày, công ty chưa đồng ý cho nghỉ sớm. Tôi nghỉ vậy có đúng không?')
  a=analyze(intake(q,[]),'2026-09-15')
  self.assertIs(a.facts['notice_exception'],False)
  self.assertEqual(a.facts['notice_days'],17)
  self.assertFalse(a.missing_facts)

class ContractCertaintyTests(unittest.TestCase):
 def test_uncertain_type_words_cannot_establish_a_contract_type(self):
  for q in ['Tôi chưa biết hợp đồng của mình có phải loại không xác định thời hạn hay không.',
    'Tôi không rõ hợp đồng không xác định thời hạn hay xác định thời hạn.',
    'Liệu đây là hợp đồng xác định thời hạn không?']:
   with self.subTest(q=q):self.assertNotIn('contract_type',analyze(intake(q,[])).facts)
 def test_negating_a_type_does_not_prove_the_opposite_type(self):
  q='Hợp đồng của tôi không phải loại không xác định thời hạn.'
  self.assertNotIn('contract_type',analyze(intake(q,[])).facts)
 def test_affirmative_types_and_explicit_terms_are_retained(self):
  for q,expected in [('Tôi ký hợp đồng không xác định thời hạn.','INDEFINITE'),
    ('Hợp đồng của tôi là hợp đồng xác định thời hạn.','FIXED_TERM'),
    ('Hợp đồng lao động có thời hạn 23 tháng.','FIXED_TERM')]:
   with self.subTest(q=q):self.assertEqual(analyze(intake(q,[])).facts.get('contract_type'),expected)
 def test_conflicting_current_types_are_not_flattened(self):
  q='Tôi có hợp đồng không xác định thời hạn và hợp đồng xác định thời hạn ở hai nơi.'
  self.assertNotIn('contract_type',analyze(intake(q,[])).facts)
 def test_researcher_cannot_turn_uncertain_type_excerpt_into_fact(self):
  q='Tôi chưa biết hợp đồng của tôi có phải không xác định thời hạn hay không.'
  quote='không xác định thời hạn'
  candidate=FactCandidate(field='contract_type',value='INDEFINITE',source_quote=quote,
    char_start=q.index(quote),char_end=q.index(quote)+len(quote))
  self.assertIsNone(_verified_candidate(candidate,q))
 def test_notice_assessment_still_asks_for_unknown_contract(self):
  q=('Tôi muốn nghỉ và chỉ báo trước 16 ngày. Tôi chưa rõ hợp đồng có phải loại không xác định thời hạn không. '
    'Tôi không làm công việc đặc thù, không được miễn báo trước, công ty không đồng ý cho nghỉ sớm. Nghỉ vậy có đúng không?')
  a=analyze(intake(q,[]),'2026-09-15')
  self.assertNotIn('contract_type',a.facts)
  self.assertTrue(any('Loại hợp đồng' in x for x in a.missing_facts))

if __name__=='__main__':unittest.main()
