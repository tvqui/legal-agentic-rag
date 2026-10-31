import json,unittest
from unittest.mock import Mock
from copy import deepcopy
from jsonschema import Draft202012Validator
from vn_labor_online.answer_review import review_answer
from tests.online.test_semantic_answer_review import sample

class KeyedReviewerContractTests(unittest.TestCase):
    def provider(self,mutate=None):
        pack,draft,legacy=sample();wire={}
        def structured(system,user,schema):
            value=deepcopy(legacy)
            value['claims']={c['claim_id']:{k:v for k,v in c.items() if k!='claim_id'} for c in value['claims']}
            value['coverage']={c['task_id']:{k:v for k,v in c.items() if k!='task_id'} for c in value['coverage']}
            for claim in value['claims'].values():
                claim['grounding']={g['evidence_id']:'span_000' for g in claim['grounding']}
            wire.update(schema=schema,response=deepcopy(value),payload=json.loads(user))
            if mutate:mutate(value)
            return value
        provider=Mock();provider.context_tokens=None;provider.max_output_tokens=1000;provider.structured.side_effect=structured
        return pack,draft,provider,wire
    def test_exact_keyed_response_passes_and_does_not_add_inference(self):
        p,d,provider,wire=self.provider();result,warnings=review_answer(provider,d,p,0)
        self.assertEqual(result.semantic_review['status'],'PASS');self.assertFalse(warnings)
        self.assertEqual(provider.structured.call_count,1)
        self.assertEqual(result.claims,d.claims)
        self.assertTrue(Draft202012Validator(wire['schema']).is_valid(wire['response']))
    def test_decoder_contract_forbids_omitted_or_foreign_claims_and_sources(self):
        p,d,provider,wire=self.provider();review_answer(provider,d,p,0)
        schema=Draft202012Validator(wire['schema']);raw=wire['response']
        self.assertFalse(schema.is_valid({**raw,'claims':{}}))
        foreign=deepcopy(raw);foreign['claims']['invented']=foreign['claims'].pop('claim')
        self.assertFalse(schema.is_valid(foreign))
        foreign=deepcopy(raw);foreign['claims']['claim']['grounding']={'foreign':'span_000'}
        self.assertFalse(schema.is_valid(foreign))
    def test_source_quote_is_still_checked_after_decoder_accounting(self):
        p,d,provider,_=self.provider(lambda v:v['claims']['claim']['grounding'].update(source='span_999'))
        result,warnings=review_answer(provider,d,p,0)
        self.assertFalse(result.claims);self.assertIn('ANSWER_QUALITY_BLOCKED',warnings)
        self.assertEqual(result.semantic_review['error_code'],'GROUNDING_QUOTE_MISMATCH')
    def test_supported_without_grounding_is_never_recovered_as_answer(self):
        p,d,provider,_=self.provider(lambda v:v['claims']['claim'].update(grounding=[]))
        result,warnings=review_answer(provider,d,p,0)
        self.assertFalse(result.claims);self.assertEqual(result.semantic_review['error_code'],'UNSUPPORTED_SEMANTIC_PASS')
        self.assertIn('ANSWER_QUALITY_BLOCKED',warnings)
    def test_wrong_key_cannot_be_replaced_with_the_desired_id(self):
        def wrong(v):v['claims']={'other':v['claims']['claim']}
        p,d,provider,_=self.provider(wrong);result,warnings=review_answer(provider,d,p,0)
        self.assertFalse(result.claims);self.assertEqual(result.semantic_review['error_code'],'CLAIM_ACCOUNTING_MISMATCH')
    def test_hidden_identifier_cannot_override_its_object_key(self):
        p,d,provider,_=self.provider(lambda v:v['claims']['claim'].update(claim_id='other'))
        result,_=review_answer(provider,d,p,0)
        self.assertFalse(result.claims);self.assertEqual(result.semantic_review['error_code'],'REVIEW_KEYED_VALUE_INVALID')
    def test_retry_remains_bounded_and_rechecks_same_draft(self):
        p,d,provider,wire=self.provider();correct=provider.structured.side_effect;calls=0
        def first_wrong(*args):
            nonlocal calls
            calls+=1;value=correct(*args)
            if calls==1:value['coverage']={}
            return value
        provider.structured.side_effect=first_wrong
        result,warnings=review_answer(provider,d,p,1)
        self.assertEqual(result.semantic_review['status'],'PASS');self.assertEqual(calls,2)
        self.assertEqual(wire['payload']['claims'],[c.model_dump() for c in d.claims])
    def test_technical_failure_never_returns_unchecked_original_claims(self):
        p,d,provider,_=self.provider();provider.structured.side_effect=TimeoutError()
        result,warnings=review_answer(provider,d,p,1)
        self.assertFalse(result.claims);self.assertIn('ANSWER_QUALITY_BLOCKED',warnings)
