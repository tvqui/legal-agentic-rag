"""No provider calls; prove separation and honest handling of missing actual sources."""
import json,unittest
from unittest.mock import Mock
from judging import grade,faithful_payload
class JudgingTests(unittest.TestCase):
    def fixture(self):
        record={'id':'q','arm':'graph_on','question':'Fixture task','query_date':'2026-09-15','response':{'status':'PARTIAL_ALLOWED','answer':'A claim',
            'claims':[{'claim_id':'c1','text':'A claim','evidence_ids':['u']}],'citations':[{'evidence_id':'u'}],
            'trace':{'events':[{'event':'selection','evidence_ids':['u']}]}}}
        gold={'reference_answer':'GOLD_CANARY','support':[{'quote':'GOLD_ONLY_SOURCE'}],'expected_tasks':[{'task_id':'t1','description':'Fixture task'}]}
        corpus={'u':{'unit_id':'u','source_text':'ACTUAL_SOURCE','ancestor_context':'ACTUAL_PARENT'}}
        factual={'correctness':.5,'completeness':1.,'notes':'reference result','tasks':[{'task_id':'t1','addressed':True}]}
        support={'evidence_support':0.,'notes':'unsupported by actual source','tasks':[{'task_id':'t1','evidence_supported':False}]}
        return record,gold,corpus,factual,support
    def test_two_stages_and_no_gold_in_faithfulness(self):
        r,g,c,f,s=self.fixture();provider=Mock();provider.structured.side_effect=[f,s]
        result=grade(provider,r,g,c)
        reference=json.loads(provider.structured.call_args_list[0].args[1]);actual=json.loads(provider.structured.call_args_list[1].args[1])
        self.assertIn('GOLD_CANARY',json.dumps(reference));self.assertNotIn('GOLD_CANARY',json.dumps(actual));self.assertNotIn('GOLD_ONLY_SOURCE',json.dumps(actual))
        self.assertIn('ACTUAL_SOURCE',json.dumps(actual));self.assertIn('ACTUAL_PARENT',json.dumps(actual))
        self.assertNotIn('arm',actual);self.assertEqual(result['evidence_support'],0.)
        self.assertEqual(result['judge_stages'],2)
    def test_unknown_selection_is_na_not_invented_or_zero(self):
        r,g,c,f,_=self.fixture();r['response'].pop('trace');provider=Mock();provider.structured.return_value=f
        result=grade(provider,r,g,c)
        self.assertIsNone(result['evidence_support']);self.assertEqual(result['evidence_support_status'],'MISSING_SELECTED_CONTEXT')
        self.assertIsNone(result['tasks'][0]['evidence_supported']);self.assertEqual(provider.structured.call_count,1)
    def test_source_outside_selected_cannot_rescue_citation(self):
        r,g,c,f,_=self.fixture();r['response']['trace']['events'][0]['evidence_ids']=[]
        provider=Mock();provider.structured.return_value=f;result=grade(provider,r,g,c)
        self.assertEqual(result['evidence_support'],0.);self.assertEqual(provider.structured.call_count,1)
        self.assertEqual(result['actual_cited_source_count'],0)
    def test_refusal_has_no_claim_faithfulness_score(self):
        r,g,c,f,_=self.fixture();r['response'].update(status='INSUFFICIENT_EVIDENCE',claims=[],citations=[])
        provider=Mock();provider.structured.return_value=f;result=grade(provider,r,g,c)
        self.assertIsNone(result['evidence_support']);self.assertEqual(result['evidence_support_status'],'NO_CITED_CLAIMS')
    def test_missing_task_is_rejected(self):
        r,g,c,f,_=self.fixture();f['tasks']=[];provider=Mock();provider.structured.return_value=f
        with self.assertRaises(ValueError):grade(provider,r,g,c)

    def test_missing_actual_source_is_na_not_an_unsupported_claim(self):
        r,g,c,f,_=self.fixture();c['u'].pop('source_text');provider=Mock();provider.structured.return_value=f
        result=grade(provider,r,g,c)
        self.assertIsNone(result['evidence_support']);self.assertEqual(result['evidence_support_status'],'MISSING_SOURCE_TEXT')
        self.assertEqual(provider.structured.call_count,1)
    def test_unknown_task_support_keeps_na_in_scoring(self):
        from scoring import score_record
        r,g,c,f,_=self.fixture();r['response'].pop('trace');provider=Mock();provider.structured.return_value=f
        result=grade(provider,r,g,c);r.update(status='OK',judge={'status':'AI_JUDGED',**result})
        g.update(required_groups=[['u']],query_date=r['query_date'])
        scores=score_record(r,g,c)
        self.assertIsNone(scores['ai_evidence_support']);self.assertIsNone(scores['ai_task_supported_fraction'])

    def test_local_warning_does_not_fabricate_or_clamp_ai_scores(self):
        r,g,c,f,s=self.fixture()
        c['u']['source_text']='Công thức tiền = (lương giờ + lương giờ × 30%) × số giờ.'
        r['response']['claims'][0]['text']='Công thức tiền lương = lương giờ + (lương giờ × 30% × số giờ).'
        f['correctness']=f['completeness']=1.;s['evidence_support']=1.
        provider=Mock();provider.structured.side_effect=[f,s]
        result=grade(provider,r,g,c)
        self.assertEqual(result['correctness'],1.)
        self.assertIn('CLAIM_FORMULA_UNIT_MISMATCH',result['local_answer_checks']['issues'][0]['codes'])
        from scoring import score_record
        r.update(status='OK',judge={'status':'AI_JUDGED',**result});g.update(required_groups=[['u']],query_date=r['query_date'])
        scored=score_record(r,g,c)
        self.assertTrue(scored['ai_full_score_with_local_warning'])

if __name__=='__main__':unittest.main()
