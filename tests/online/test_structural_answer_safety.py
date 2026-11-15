"""Structural adversarial tests; synthetic evidence, no LLM/network."""
import itertools
import unittest
from types import SimpleNamespace as NS
from vn_labor_online.claim_validation import semantic_issues,fold
from vn_labor_online.formula_validation import hourly_formula_status
from vn_labor_online.answer_review import missing_automatic_conclusion
from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.models import Claim

class OrdinalCapTests(unittest.TestCase):
    def sources(self):
        text='Ký hợp đồng lao động mới thì chỉ được ký thêm 01 lần, sau đó phải ký hợp đồng lao động không xác định thời hạn.'
        return [NS(text=text,full_text=text)]
    def test_word_order_and_permission_variants(self):
        for number,ordinal,verb,modifier in itertools.product(['hai','2'],['thứ','lần thứ'],['ký','ký kết','giao kết'],['','tối đa ']):
            text=f'Sau khi hợp đồng lao động xác định thời hạn {ordinal} {number} hết hạn, hai bên được {verb} thêm {modifier}01 lần.'
            with self.subTest(text=text):self.assertIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues(text,self.sources()))
    def test_negated_permission_is_not_inverted(self):
        text='Sau khi hợp đồng lao động xác định thời hạn lần thứ hai hết hạn, không được ký kết thêm 01 lần.'
        self.assertNotIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues(text,self.sources()))
        self.assertNotIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues(text.replace('không được','không còn được'),self.sources()))
    def test_first_contract_and_background_fact_remain_usable(self):
        for text in ['Sau hợp đồng lần thứ nhất, được ký kết thêm một lần.','Hợp đồng lần thứ hai đã hết hạn.']:
            self.assertNotIn('CLAIM_RENEWAL_COUNT_BASE_SHIFT',semantic_issues(text,self.sources()))

class FormulaDimensionTests(unittest.TestCase):
    source=fold('Công thức tiền = (Lương giờ thực trả + Lương giờ thực trả × 30%) × Số giờ làm việc vào ban đêm.')
    def status(self,rhs):return hourly_formula_status(fold('Công thức tiền lương = '+rhs+'.'),self.source)
    def test_wrong_parentheses_do_not_hide_unit_mismatch(self):
        for rhs in ['lương giờ + (lương giờ × 30% × số giờ)', '(lương giờ + lương giờ × 30% × số giờ)', 'lương giờ × số giờ + lương giờ × 30%']:
            with self.subTest(rhs=rhs):self.assertEqual(self.status(rhs),'UNIT_MISMATCH')
    def test_valid_grouped_distributed_and_scalar_first_forms(self):
        for rhs in ['(lương giờ + lương giờ × 30%) × số giờ', 'lương giờ × số giờ + lương giờ × 30% × số giờ', '(1 + 30%) × lương giờ × số giờ']:
            with self.subTest(rhs=rhs):self.assertEqual(self.status(rhs),'VALID')
    def test_rate_and_hours_from_actual_model_vocabulary(self):
        base='Tiền lương giờ thực trả của công việc đang làm vào ngày làm việc bình thường'
        good=f'({base} + {base} x Mức ít nhất 30%) x Số giờ làm việc vào ban đêm'
        bad=f'{base} + ({base} x Mức ít nhất 30% x Số giờ làm việc vào ban đêm)'
        self.assertEqual(self.status(good),'VALID');self.assertEqual(self.status(bad),'UNIT_MISMATCH')
    def test_unknown_calls_names_and_excessive_nesting_are_not_executed(self):
        for rhs in ["__import__('os').system('x') + số giờ",'lương giờ × hệ số bí mật × số giờ','('*100+'lương giờ × số giờ'+')'*100]:
            self.assertEqual(self.status(rhs),'UNKNOWN')
    def test_alternative_rates_do_not_require_guessing_a_branch(self):
        self.assertEqual(self.status('lương giờ × mức ít nhất 120% hoặc 180% hoặc 250% × số giờ'),'VALID')
    def test_non_hourly_and_literal_sources_are_not_reinterpreted(self):
        self.assertEqual(hourly_formula_status(fold('Công thức tiền lương = (lương giờ + lương giờ × 30%) × số giờ.'),'nguon khong co don vi'),'NOT_APPLICABLE')
        self.assertEqual(hourly_formula_status(self.source,self.source),'NOT_APPLICABLE')
    def test_unit_validity_does_not_certify_a_statutory_rate(self):
        self.assertEqual(self.status('(lương giờ + lương giờ × 17%) × số giờ'),'VALID')
    def test_wrong_formula_reaches_the_shared_semantic_guard(self):
        text='Công thức tiền lương = lương giờ + (lương giờ × 30% × số giờ).'
        self.assertIn('CLAIM_FORMULA_UNIT_MISMATCH',semantic_issues(text,[NS(text=self.source,full_text=self.source)]))

class ExplicitConclusionTests(unittest.TestCase):
    query='Khi thỏa thuận hết hạn, quyền ưu tiên có làm thỏa thuận tự động kéo dài không?'
    def claim(self,text):return Claim(claim_id='c',text=text,evidence_ids=['s'])
    def test_background_quote_does_not_answer_automatic_outcome(self):
        self.assertTrue(missing_automatic_conclusion(self.query,[self.claim('Người tham gia được ưu tiên ký thỏa thuận mới.')]))
    def test_explicit_qualified_answer_is_present_not_automatically_true(self):
        self.assertFalse(missing_automatic_conclusion(self.query,[self.claim('Không tự động kéo dài chỉ vì quyền ưu tiên; cần xét điều kiện nguồn.')]))
    def test_deferred_or_nonquestion_automaticity_is_not_a_new_task(self):
        self.assertFalse(missing_automatic_conclusion('Chưa xét việc thỏa thuận tự động kéo dài hay không?',[]))
        self.assertFalse(missing_automatic_conclusion('Thỏa thuận có điều khoản tự động gia hạn. Tôi hỏi về tiền lương.',[]))
    def test_discipline_main_rule_is_retained_alongside_referenced_content(self):
        q='Đang chờ cơ quan xác minh, công ty có được kỷ luật ngay không? Nhóm hành vi được dẫn chiếu gồm những gì?'
        p=plan_evidence(analyze(intake(q,[],'2026-09-15'),'2026-09-15'))
        self.assertEqual((p.slot_requirements['pending_discipline_waiting_rule'][0][0].article,p.slot_requirements['pending_discipline_waiting_rule'][0][0].point),('122','c'))
        self.assertIn('pending_discipline_cross_reference',p.slot_requirements)

class BoundedReviewRepairTests(unittest.TestCase):
    def run_case(self,query,source,bad,good,repeat_bad=False):
        from unittest.mock import Mock
        from vn_labor_online.answer_review import review_answer
        from vn_labor_online.models import VerifiedEvidencePack,VerifiedEvidenceItem,EvidenceState,AnswerTask,AdjudicationDraft
        task=AnswerTask(task_id='t',request_quote=query,description=query,retrieval_query=query)
        pack=VerifiedEvidencePack(query=query,requested_outcome='EXPLAIN',evidence=[VerifiedEvidenceItem(evidence_id='s',text=source,full_text=source)],answer_tasks=[task],coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
        draft=AdjudicationDraft(answer_summary='',claims=[Claim(claim_id='initial',text=bad,evidence_ids=['s'])],applicable_law_versions=[])
        def verdict(cid):
            return {'claims':[{'claim_id':cid,'verdict':'SUPPORTED','grounding':[{'evidence_id':'s','quote':source}],'reason':'SYNTHETIC verdict'}],
                'coverage':[{'task_id':'t','status':'ANSWERED','claim_ids':[cid],'missing':''}],'question_fully_addressed':True,'missing_requirements':[]}
        def repaired_review(system,user,schema):
            import json
            ids=[c['claim_id'] for c in json.loads(user)['claims']]
            result=verdict('claim_001')
            # The repair retains independently supported background; account
            # for it as well, without assigning it the missing application.
            if 'initial' in ids:result['claims']+=verdict('initial')['claims']
            return result
        provider=Mock()
        replies=iter([verdict('initial'),{'claims':[{'text':bad if repeat_bad else good,'evidence_ids':['s']}]},repaired_review])
        def respond(*args):
            reply=next(replies)
            return reply(*args) if callable(reply) else reply
        provider.structured.side_effect=respond
        result,_=review_answer(provider,draft,pack,1)
        self.assertEqual(provider.structured.call_count,3)
        return result
    def test_ordinal_cap_false_pass_is_repaired_once(self):
        source='Ký hợp đồng lao động mới thì chỉ được ký thêm 01 lần, sau đó phải ký hợp đồng lao động không xác định thời hạn.'
        result=self.run_case('Sau hợp đồng thứ hai thì sao?',source,
            'Sau hợp đồng lần thứ hai, được ký kết thêm tối đa một lần.',
            'Sau hai hợp đồng phải ký hợp đồng không xác định thời hạn nếu tiếp tục làm việc.')
        self.assertEqual(result.semantic_review['status'],'PASS')
        self.assertFalse(result.semantic_review['iterations'][0]['question_fully_addressed'])
    def test_parenthesized_dimension_error_is_repaired_once(self):
        source='Nguồn quy định công thức tiền = (lương giờ + lương giờ × 30%) × số giờ.'
        result=self.run_case('Nêu công thức tiền lương.',source,
            'Công thức tiền lương = lương giờ + (lương giờ × 30% × số giờ).',
            'Công thức tiền lương = (lương giờ + lương giờ × 30%) × số giờ.')
        self.assertEqual(result.semantic_review['status'],'PASS')
    def test_repair_cannot_republish_the_same_wrong_formula(self):
        source='Nguồn quy định công thức tiền = (lương giờ + lương giờ × 30%) × số giờ.'
        result=self.run_case('Nêu công thức tiền lương.',source,
            'Công thức tiền lương = lương giờ + (lương giờ × 30% × số giờ).','unused',True)
        self.assertFalse(result.claims);self.assertEqual(result.semantic_review['status'],'FAIL')
    def test_background_only_false_completion_is_repaired_once(self):
        source='Hết hạn thỏa thuận thì được ưu tiên ký thỏa thuận mới theo điều kiện nguồn.'
        result=self.run_case('Ưu tiên có làm thỏa thuận tự động kéo dài không?',source,
            'Hết hạn thỏa thuận thì được ưu tiên ký thỏa thuận mới.',
            'Quyền ưu tiên không tự động kéo dài thỏa thuận; phải xét điều kiện trong nguồn.')
        self.assertEqual(result.semantic_review['status'],'PASS')
        self.assertFalse(result.semantic_review['iterations'][0]['question_fully_addressed'])

if __name__=='__main__':unittest.main()
