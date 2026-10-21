import copy,json,unittest
from unittest.mock import Mock
from tests.online.test_semantic_answer_review import sample
from vn_labor_online.answer_quality import clean_draft
from vn_labor_online.answer_review import review_answer


class RepairClaimDuplicateTests(unittest.TestCase):
    def test_repaired_duplicates_are_cleaned_before_new_review_id_accounting(self):
        pack,draft,valid=sample()
        bad=copy.deepcopy(valid)
        bad['claims'][0].update(verdict='UNSUPPORTED',grounding=[])
        bad['coverage'][0].update(status='MISSING',claim_ids=[],missing='Cần sửa nhận định')
        bad.update(question_fully_addressed=False,missing_requirements=['Số ngày nghỉ'])
        checked=copy.deepcopy(valid)
        checked['claims'][0]['claim_id']='claim_001'
        checked['coverage'][0]['claim_ids']=['claim_001']
        text=draft.claims[0].text
        provider=Mock()
        provider.structured.side_effect=[bad,{'claims':[
            {'text':text,'evidence_ids':['source']},
            {'text':'Ngoài ra, '+text,'evidence_ids':['source']}]},checked]
        result,_=review_answer(provider,draft,pack)
        payload=json.loads(provider.structured.call_args.args[1])
        self.assertEqual(len(payload['claims']),1)
        self.assertEqual([c.claim_id for c in result.claims],['claim_001'])
        self.assertEqual(result.semantic_review['status'],'PASS')

    def test_deduplication_does_not_merge_different_thresholds_or_conditions(self):
        _,draft,_=sample()
        original=draft.claims[0]
        draft.claims=[original,
            original.model_copy(update={'claim_id':'days','text':original.text.replace('12 ngày','14 ngày')}),
            original.model_copy(update={'claim_id':'condition','text':original.text+' Trừ trường hợp pháp luật quy định khác.'})]
        result=clean_draft(draft,'nghỉ phép')
        self.assertEqual(len(result.claims),3)
