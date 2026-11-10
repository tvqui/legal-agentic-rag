import unittest
from vn_labor_online.generation import _nonredundant_quote_items,adjudicate
from vn_labor_online.models import VerifiedEvidenceItem,VerifiedEvidencePack,EvidenceState


class FallbackQuoteRedundancyTests(unittest.TestCase):
    def item(self,uid,text,**kwargs):
        return VerifiedEvidenceItem(evidence_id=uid,instrument_number='17/TEST',kind='PROVISION',
            article='91',text=text,**kwargs)

    def test_parent_header_is_already_quoted_in_child(self):
        parent=self.item('parent','Bên nhận phải kiểm tra hồ sơ:')
        child=self.item('child','Bên nhận phải kiểm tra hồ sơ: a) Hồ sơ điện tử cần chữ ký.',clause='1',point='a')
        p=VerifiedEvidencePack(query='Hồ sơ được kiểm tra thế nào?',facts={},
            coverage_state=EvidenceState(slots={},gaps=[],coverage=1),evidence=[parent,child])
        draft=adjudicate(p,False)
        self.assertEqual(len(draft.claims),1)
        self.assertEqual(draft.claims[0].evidence_ids,['child'])
        self.assertIn(child.text,draft.claims[0].text)
        self.assertEqual(len(p.evidence),2)

    def test_parent_exception_not_repeated_in_child_is_retained(self):
        parent=self.item('parent','Bên nhận phải kiểm tra hồ sơ, trừ hồ sơ đã được xác nhận.')
        child=self.item('child','Bên nhận phải kiểm tra hồ sơ điện tử.',clause='1')
        self.assertEqual(len(_nonredundant_quote_items([parent,child])),2)

    def test_separate_editions_are_never_merged(self):
        old=self.item('old','Nội dung quy định.',valid_from='2018-01-01',valid_to='2021-01-01')
        current=self.item('current','Nội dung quy định.',valid_from='2021-01-01')
        self.assertEqual(len(_nonredundant_quote_items([old,current])),2)

    def test_siblings_and_other_articles_keep_their_locators(self):
        a=self.item('a','Bên nhận phải kiểm tra hồ sơ.',clause='1',point='a')
        b=self.item('b',a.text,clause='1',point='b')
        other=a.model_copy(update={'evidence_id':'other','article':'92'})
        self.assertEqual(len(_nonredundant_quote_items([a,b,other])),3)

    def test_equivalent_whitespace_does_not_repeat_the_same_locator(self):
        a=self.item('a','Bên nhận phải kiểm tra hồ sơ.',clause='1')
        b=self.item('b','Bên nhận  phải kiểm tra\nhồ sơ.',clause='1')
        self.assertEqual([e.evidence_id for e in _nonredundant_quote_items([a,b])],['a'])

    def test_numerical_or_polarity_difference_is_not_a_duplicate(self):
        a=self.item('a','phải kiểm tra trong 15 ngày.',clause='1')
        b=self.item('b','không phải kiểm tra trong 15 ngày.',clause='1')
        c=self.item('c','phải kiểm tra trong 30 ngày.',clause='1')
        self.assertEqual(len(_nonredundant_quote_items([a,b,c])),3)


if __name__=='__main__':unittest.main()
