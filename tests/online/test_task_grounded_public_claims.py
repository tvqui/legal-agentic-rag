import unittest
from unittest.mock import Mock
from vn_labor_online.models import AdjudicationDraft,Claim,VerifiedEvidencePack,VerifiedEvidenceItem,EvidenceState,AnswerTask
from vn_labor_online.answer_review import Review,retain_task_grounded_claims,review_answer

class TaskGroundedPublicClaimTests(unittest.TestCase):
    def fixture(self):
        text='Bên nhận phải kiểm tra thông tin và lập biên bản bàn giao.'
        claims=[Claim(claim_id='conclusion',text='Bên nhận phải kiểm tra thông tin.',evidence_ids=['e']),
                Claim(claim_id='condition',text='Bên nhận phải lập biên bản bàn giao.',evidence_ids=['e']),
                Claim(claim_id='extra',text='Thông tin phải được bên nhận kiểm tra.',evidence_ids=['e'])]
        draft=AdjudicationDraft(answer_summary='',claims=claims,applicable_law_versions=[])
        raw={'claims':[{'claim_id':c.claim_id,'verdict':'SUPPORTED','grounding':[{'evidence_id':'e','quote':text}],'reason':'Khớp nguồn'} for c in claims],
            'coverage':[{'task_id':'question','status':'ANSWERED','claim_ids':['conclusion','condition'],'missing':''}],
            'question_fully_addressed':True,'missing_requirements':[]}
        return text,draft,raw
    def test_complete_answer_retains_all_assigned_independent_premises(self):
        _,draft,raw=self.fixture();result,removed=retain_task_grounded_claims(draft,Review.model_validate(raw))
        self.assertEqual([c.claim_id for c in result.claims],['conclusion','condition'])
        self.assertEqual(removed,['extra'])
        self.assertEqual(len(draft.claims),3)
    def test_shared_source_does_not_make_two_necessary_claims_duplicates(self):
        _,draft,raw=self.fixture();raw['coverage'][0]['claim_ids']=['conclusion','condition','extra']
        result,removed=retain_task_grounded_claims(draft,Review.model_validate(raw))
        self.assertEqual(len(result.claims),3);self.assertFalse(removed)
    def test_each_task_has_its_own_proof_retained(self):
        _,draft,raw=self.fixture();raw['coverage']=[{'task_id':'one','status':'ANSWERED','claim_ids':['conclusion'],'missing':''},
            {'task_id':'two','status':'ANSWERED','claim_ids':['condition'],'missing':''}]
        result,_=retain_task_grounded_claims(draft,Review.model_validate(raw))
        self.assertEqual({c.claim_id for c in result.claims},{'conclusion','condition'})
    def test_partial_answers_do_not_lose_explanatory_context(self):
        _,draft,raw=self.fixture();raw['question_fully_addressed']=False;raw['missing_requirements']=['Còn dữ kiện chưa rõ.']
        result,removed=retain_task_grounded_claims(draft,Review.model_validate(raw))
        self.assertEqual(result,draft);self.assertFalse(removed)
    def test_review_uses_exact_coverage_ids_without_another_model_call(self):
        text,draft,raw=self.fixture()
        task=AnswerTask(task_id='question',request_quote='Quy trình bàn giao?',description='Quy trình bàn giao',retrieval_query='Bàn giao')
        pack=VerifiedEvidencePack(query='Quy trình bàn giao?',evidence=[VerifiedEvidenceItem(evidence_id='e',text=text,full_text=text)],
            answer_tasks=[task],coverage_state=EvidenceState(slots={},gaps=[],coverage=1))
        provider=Mock();provider.structured.return_value=raw
        result,_=review_answer(provider,draft,pack,1)
        self.assertEqual(result.semantic_review['removed_unassigned_claim_ids'],['extra'])
        self.assertEqual(provider.structured.call_count,1)
        self.assertEqual(result.semantic_review['status'],'PASS')

if __name__=='__main__':unittest.main()
