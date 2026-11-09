import unittest
from types import SimpleNamespace as NS
from vn_labor_online.claim_validation import semantic_issues

class RelativeContractCountTests(unittest.TestCase):
    def sources(self,count='01'):
        text=f'Trường hợp ký hợp đồng lao động mới thì cũng chỉ được ký thêm {count} lần, sau đó phải ký hợp đồng lao động không xác định thời hạn.'
        return [NS(text=text,full_text=text)]
    def test_additional_limit_is_not_reset_after_two_prior_contracts(self):
        claim='Hợp đồng lao động xác định thời hạn chỉ được ký thêm 01 lần sau khi hai hợp đồng trước đó hết hạn.'
        self.assertIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues(claim,self.sources()))
    def test_source_derived_additional_count_is_not_hardcoded(self):
        self.assertIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues('Sau ba hợp đồng, được ký thêm một lần.',self.sources('02')))
        self.assertNotIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues('Sau hai hợp đồng, được ký thêm một lần.',self.sources('02')))
    def test_one_original_plus_one_additional_is_preserved(self):
        self.assertNotIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues('Sau một hợp đồng, được ký thêm một lần.',self.sources()))
    def test_a_prohibition_of_further_renewal_is_not_inverted(self):
        self.assertNotIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues('Sau hai hợp đồng, không được ký thêm một lần.',self.sources()))
    def test_an_attached_explicit_exception_is_not_erased(self):
        sources=self.sources()+[NS(text='Đối với nhóm này, hai bên có thể giao kết nhiều lần hợp đồng lao động xác định thời hạn.',full_text='Đối với nhóm này, hai bên có thể giao kết nhiều lần hợp đồng lao động xác định thời hạn.')]
        self.assertNotIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues('Theo ngoại lệ này, sau hai hợp đồng được ký thêm một lần.',sources))

if __name__=='__main__':unittest.main()
