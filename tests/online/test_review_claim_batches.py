"""Verify every claim ID in bounded groups, without relaxing grounding or coverage."""
import json
import unittest
from types import SimpleNamespace
from vn_labor_online.answer_review import audit_in_batches,validate_review,accounting_schema,Review
from vn_labor_online.errors import StructuredOutputError
from tests.online.test_semantic_answer_review import sample


class BatchProvider:
    max_output_tokens=6144
    def __init__(self,omit=False,fake_quote=False):
        self.calls=[]; self.omit=omit; self.fake_quote=fake_quote
    def structured(self,system,user,schema):
        payload=json.loads(user); self.calls.append(payload)
        if 'checked_claims' in payload:
            return {'coverage':[{'task_id':t['task_id'],'status':'ANSWERED',
                'claim_ids':[c['claim_id'] for c in payload['checked_claims']],'missing':''} for t in payload['tasks']],
                'question_fully_addressed':True,'missing_requirements':[]}
        claims=payload['claims']
        if self.omit: claims=claims[:-1]
        return {'claims':[{'claim_id':c['claim_id'],'verdict':'SUPPORTED',
            'grounding':[{'evidence_id':'source','quote':('Fabricated quotation must be rejected.' if self.fake_quote else ' '.join(payload['evidence'][0]['source_spans'].values()))}],
            'reason':'Source and qualifications match.'} for c in claims]}


class ReviewClaimBatchTests(unittest.TestCase):
    def fixture(self,count):
        p,d,v=sample()
        d=d.model_copy(update={'claims':[d.claims[0].model_copy(update={'claim_id':f'claim_{i}'}) for i in range(count)]})
        payload={'question':p.query,'tasks':[t.model_dump() for t in p.answer_tasks],
            'claims':[c.model_dump() for c in d.claims]}
        return p,d,payload

    def test_large_answer_retains_every_claim_and_checks_coverage_separately(self):
        p,d,payload=self.fixture(10); provider=BatchProvider()
        review=audit_in_batches(provider,payload,d,p,p.answer_tasks)
        self.assertEqual(validate_review(review,d,p,p.answer_tasks),{c.claim_id for c in d.claims})
        self.assertEqual([len(c['claims']) for c in provider.calls[:-1]],[4,4,2])
        self.assertEqual(len(provider.calls[-1]['checked_claims']),10)
        self.assertNotIn('evidence',provider.calls[-1])
        self.assertTrue(all(' '.join(c['evidence'][0]['source_spans'].values())==p.evidence[0].full_text for c in provider.calls[:-1]))

    def test_missing_id_is_not_silently_accepted_or_sent_to_coverage(self):
        p,d,payload=self.fixture(10); provider=BatchProvider(omit=True)
        with self.assertRaisesRegex(StructuredOutputError,'accounting mismatch'):
            audit_in_batches(provider,payload,d,p,p.answer_tasks)
        self.assertEqual(len(provider.calls),1)

    def test_batches_do_not_relax_exact_source_grounding(self):
        p,d,payload=self.fixture(10); provider=BatchProvider(fake_quote=True)
        with self.assertRaisesRegex(StructuredOutputError,'exact cited-source quotation'):
            audit_in_batches(provider,payload,d,p,p.answer_tasks)
        self.assertEqual(len(provider.calls),1)

    def test_configured_claim_capacity_cannot_expand_into_unbounded_calls(self):
        p,d,payload=self.fixture(33); provider=BatchProvider()
        with self.assertRaisesRegex(StructuredOutputError,'REVIEW_CLAIM_BATCH_LIMIT'):
            audit_in_batches(provider,payload,d,p,p.answer_tasks)
        self.assertFalse(provider.calls)

    def test_accounting_retry_for_medium_answer_uses_small_batches(self):
        p,d,payload=self.fixture(6); provider=BatchProvider()
        payload['previous_validation_error']='CLAIM_ACCOUNTING_MISMATCH'
        review=audit_in_batches(provider,payload,d,p,p.answer_tasks)
        self.assertEqual([len(c['claims']) for c in provider.calls[:-1]],[4,2])
        self.assertEqual(len(validate_review(review,d,p,p.answer_tasks)),6)

    def test_decoder_contract_rejects_missing_and_foreign_ids(self):
        from jsonschema import Draft202012Validator
        p,d,_=self.fixture(2)
        schema=accounting_schema(Review,[c.claim_id for c in d.claims],[t.task_id for t in p.answer_tasks])
        valid={'claims':[{'claim_id':c.claim_id,'verdict':'UNSUPPORTED','grounding':[],
            'reason':'Chưa có đủ căn cứ.'} for c in d.claims],
            'coverage':[{'task_id':t.task_id,'status':'MISSING','claim_ids':[],
                'missing':'Chưa đủ bằng chứng.'} for t in p.answer_tasks],
            'question_fully_addressed':False,'missing_requirements':['source']}
        validator=Draft202012Validator(schema)
        self.assertTrue(validator.is_valid(valid))
        self.assertFalse(validator.is_valid({**valid,'claims':valid['claims'][:-1]}))
        foreign=json.loads(json.dumps(valid)); foreign['claims'][0]['claim_id']='invented_id'
        self.assertFalse(validator.is_valid(foreign))
        foreign=json.loads(json.dumps(valid)); foreign['coverage'][0]['task_id']='invented_task'
        self.assertFalse(validator.is_valid(foreign))

    def test_schema_is_per_request_and_does_not_mutate_model_contract(self):
        original=Review.model_json_schema()
        accounting_schema(Review,['private_claim'],['one_task'])
        self.assertEqual(Review.model_json_schema(),original)
        fresh=accounting_schema(Review,['other_claim'],['other_task'])
        self.assertNotIn('private_claim',json.dumps(fresh))

    def test_duplicate_ids_remain_invalid_even_with_correct_array_size(self):
        p,d,_=self.fixture(2)
        verdict={'claim_id':d.claims[0].claim_id,'verdict':'UNSUPPORTED','grounding':[],
            'reason':'Không xác minh được.'}
        review=Review(claims=[verdict,verdict],coverage=[],question_fully_addressed=False,missing_requirements=[])
        with self.assertRaisesRegex(StructuredOutputError,'each claim exactly once'):
            validate_review(review,d,p,[])


if __name__=='__main__': unittest.main()
