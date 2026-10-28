import sys,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import protocol,external,qa,qa_worker,labor_retrieval,common,suite
from resume import restore

class ProtocolTests(unittest.TestCase):
    def test_hf_carddata_conversion_uses_dictionary_api(self):
        from huggingface_hub import DatasetCardData
        card=DatasetCardData(language=['vi'],license='cc-by-4.0')
        fake=NS(dataset_info=Mock(return_value=NS(sha='abc123',card_data=card)))
        with tempfile.TemporaryDirectory() as tmp,patch('huggingface_hub.HfApi',return_value=fake):
            meta=external.pin('owner/dataset','main',tmp)
            again=external.pin('owner/dataset','main',tmp)
        self.assertEqual(meta['license'],'cc-by-4.0');self.assertEqual(again,meta)
        self.assertEqual(fake.dataset_info.call_count,1)

    def test_fact_scoring_requires_same_unit_and_exact_support(self):
        a={'facts':[{'fact_id':'one','supports':[{'unit_id':'a','quote':'Đúng điều kiện'}]},
           {'fact_id':'two','supports':[{'unit_id':'b','quote':'không được'}]}]}
        m=protocol.context_metrics([{'unit_id':'a','text':'Đúng điều kiện.'},{'unit_id':'wrong','text':'không được'}],a)
        self.assertEqual(m['fact_coverage'],.5);self.assertEqual(m['evidence_precision'],.5)
        self.assertIsNone(protocol.context_metrics([{'unit_id':'a','text':'Đúng điều kiện.'}])['fact_coverage'])

    def test_annotation_build_and_quotes_cannot_silently_migrate(self):
        annotation={'id':'q','corpus_fingerprint':'build','facts':[{'fact_id':'f','description':'condition','supports':[{'unit_id':'a','quote':'must'}]}]}
        protocol.validate_annotation(annotation,{'a':{'text':'must happen'}},'build')
        with self.assertRaises(ValueError):protocol.validate_annotation(annotation,{'a':{'text':'may happen'}},'build')
        with self.assertRaises(ValueError):protocol.validate_annotation(annotation,{'a':{'text':'must happen'}},'other')

    def test_repetitions_are_not_independent_queries(self):
        rows=[{'id':'a','value':1},{'id':'a','value':0},{'id':'b','value':1}]
        values=protocol.query_macro(rows,lambda r:r['value'])
        self.assertEqual(values,{'a':.5,'b':1})
        self.assertEqual(protocol.bootstrap_ci(values.values(),samples=100)['n_queries'],2)
        self.assertIsNone(protocol.bootstrap_ci([.5])['ci95_low'])

    def test_paired_delta_rejects_unequal_denominators_by_intersection(self):
        rows=[{'id':'q1','variant':'full','status':'OK','score':1},
              {'id':'q2','variant':'full','status':'OK','score':0},
              {'id':'q1','variant':'minus','status':'OK','score':0}]
        p=protocol.paired_delta(rows,'full','minus',lambda r:r['score'])
        self.assertEqual(p['n_queries'],1);self.assertEqual(p['mean'],1);self.assertEqual(p['left_only_ids'],['q2'])
        self.assertIsNone(p['ci95_low'])

    def test_reranker_only_runs_in_declared_variants_without_qrels(self):
        from vn_labor_online.models import Evidence
        e=Evidence(unit_id='s',text='source',document_id='d',retrieval_method='test',authority_rank=100,
            valid_from='2021-01-01',temporal_verified=True)
        for method in labor_retrieval.METHODS:
            cfg=NS(reranker=NS(enabled=False))
            r=NS(bm25=Mock(return_value=[e]),dense=Mock(return_value=[e]),fusion=Mock(return_value=[e]),neural_rerank=Mock(return_value=[e]))
            g=NS(expand=Mock(return_value=([e],{})))
            row={'question':'q','query_date':'2026-01-01','required_groups':[['SECRET_GOLD']]}
            labor_retrieval.retrieve(method,row,r,g,cfg)
            self.assertEqual(r.neural_rerank.call_count,int(method.endswith('_rerank')))
            self.assertEqual(g.expand.call_count,int(method.startswith('hybrid_graph')))
            self.assertNotIn('SECRET_GOLD',str(r.neural_rerank.call_args))

    def config_and_response(self):
        from vn_labor_online.config import OnlineConfig
        from vn_labor_online.models import Stop,Claim
        cfg=OnlineConfig(artifact_source='fixture',adjudication={'mode':'ollama'})
        answer=NS(answer='answer',status=Stop.PARTIAL_ALLOWED,claims=[Claim(claim_id='c',text='claim',evidence_ids=['s'])],
          citations=[],warnings=[],parts=[],trace=NS(reference_audit='PASS',timings_ms={},trace_id='test',retrieval_rounds=0,events=[]))
        return cfg,answer

    def make_run(self,p):
        (p/'labor_gold.jsonl').write_text(json.dumps({'id':'q','question':'question','reference_answer':'reference',
          'expected_status':'ANSWERABLE','query_date':'2026-01-01','review_status':'DRAFT'})+'\n',encoding='utf-8')

    def settings(self,judge=True):return {'artifact':'fixture','repeats':1,'case_timeout_seconds':20,'qa_warmup':False,'judge':{'enabled':judge}}

    def test_judging_is_deferred_until_every_generation_completed(self):
        cfg,answer=self.config_and_response();calls=[]
        def factory(config):
            return NS(ask=lambda request:(calls.append('generation') or answer),close=Mock(),store=NS(units_by_id={}))
        def judge(*args):calls.append('judge');return {'status':'AI_JUDGED','correctness':1,'completeness':1,'evidence_support':1}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.make_run(p)
            with patch('vn_labor_online.config.load_config',return_value=cfg),patch('vn_labor_online.pipeline.OnlinePipeline',side_effect=factory),patch.object(qa,'score_judge',side_effect=judge):
                report=qa.evaluate(p,self.settings())
            self.assertTrue(report['complete']);self.assertEqual(calls,['generation']*5+['judge']*5)

    def test_capacity_stops_immediately_and_resume_keeps_successful_answers(self):
        from vn_labor_online.errors import ProviderRateLimited
        cfg,answer=self.config_and_response();count=0
        def ask(request):
            nonlocal count
            count+=1
            if count==2:raise ProviderRateLimited(quota_kind='RPD')
            return answer
        def factory(config):return NS(ask=ask,close=Mock(),store=NS(units_by_id={}))
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.make_run(p)
            with patch('vn_labor_online.config.load_config',return_value=cfg),patch('vn_labor_online.pipeline.OnlinePipeline',side_effect=factory):
                first=qa.evaluate(p,self.settings(False))
                self.assertEqual(count,2);self.assertEqual(first['stop_reason'],'UPSTREAM_CAPACITY_OR_CONFIGURATION')
                last=qa.evaluate(p,self.settings(False))
            self.assertTrue(last['complete']);self.assertEqual(count,6) # one successful answer preserved, only four pending rerun
            rows=common.jsonl(p/'ablation/responses.jsonl');self.assertEqual(len(rows),5)
            self.assertEqual(len(common.jsonl(p/'ablation/attempt_history.jsonl')),1)

    def test_judge_quota_pause_does_not_regenerate_answers_on_resume(self):
        cfg,answer=self.config_and_response();ask=Mock(return_value=answer)
        factory=lambda c:NS(ask=ask,close=Mock(),store=NS(units_by_id={}))
        success={'status':'AI_JUDGED','correctness':.5,'completeness':1,'evidence_support':.5}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.make_run(p)
            with patch('vn_labor_online.config.load_config',return_value=cfg),patch('vn_labor_online.pipeline.OnlinePipeline',side_effect=factory),patch.object(qa,'score_judge',return_value={'status':'ERROR','error_type':'ProviderRateLimited'}):
                first=qa.evaluate(p,self.settings());self.assertEqual(first['stop_reason'],'JUDGE_CAPACITY_OR_CONFIGURATION')
            with patch('vn_labor_online.config.load_config',return_value=cfg),patch('vn_labor_online.pipeline.OnlinePipeline',side_effect=factory),patch.object(qa,'score_judge',return_value=success):
                last=qa.evaluate(p,self.settings())
            self.assertTrue(last['complete']);self.assertEqual(ask.call_count,5)

    def test_errors_do_not_become_fast_successes_or_perfect_judge_scores(self):
        m=common.answer_summary([{'id':'a','status':'ERROR','elapsed_ms':1},{'id':'b','status':'OK','elapsed_ms':100,'judge':{'status':'ERROR'}}])
        self.assertEqual(m['mean_ms'],100);self.assertEqual(m['errors'],1)
        self.assertIsNone(m['ai_correctness']);self.assertEqual(m['ai_judge_errors'],1)

    def test_resume_archive_rejects_path_traversal(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);archive=p/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for n in ('run_info.json','settings_resolved.json','state.json','source_manifest.json','protocol.json'):z.writestr(n,'{}')
                z.writestr('../escape.txt','bad')
            with self.assertRaises(ValueError):restore(archive,p/'restored')
            self.assertFalse((p/'restored').exists())

    def test_frozen_models_use_artifact_embedding_revision(self):
        cfg,_=self.config_and_response();store=NS(dense_report={'model':'repo/model','model_revision':'exact_sha'})
        with patch('huggingface_hub.snapshot_download',return_value='model_path') as download:
            pins=labor_retrieval.pin_models(cfg,store,['dense'],'cache')
        self.assertEqual(pins['embedding']['revision'],'exact_sha');self.assertEqual(download.call_args.kwargs['revision'],'exact_sha')

    def test_human_review_unfilled_is_not_perfect_accuracy_and_hash_is_checked(self):
        from human_review import export_template,score
        import csv
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'ablation').mkdir()
            records=[{'id':'q','variant':'full','repeat':1,'status':'OK','question':'q','answer':'saved answer'}]
            (p/'ablation/responses.jsonl').write_text(json.dumps(records[0])+'\n',encoding='utf-8')
            export_template(p,records)
            result=score(p,p/'human_review_template.csv')
            self.assertEqual(result['reviewed'],0);self.assertIsNone(result['variants']['full']['human_correct_rate'])
            rows=list(csv.DictReader((p/'human_review_template.csv').open(encoding='utf-8-sig')))
            rows[0].update(reviewer='Reviewer',reviewed_at='2026-10-28',correct='1',complete='0',supported='1',temporal_correct='')
            with (p/'completed.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
            result=score(p,p/'completed.csv');self.assertEqual(result['variants']['full']['human_correct_and_supported_rate'],1)
            records[0]['answer']='different';(p/'ablation/responses.jsonl').write_text(json.dumps(records[0])+'\n')
            with self.assertRaises(ValueError):score(p,p/'completed.csv')

    def test_summary_does_not_claim_many_repetitions_are_many_queries(self):
        rows=[{'id':'q','question':'question','method':'bm25','status':'OK','elapsed_ms':1,'metrics':labor_retrieval.metrics(['a'],[['a']],1)} for _ in range(3)]
        manifest={'methods':['bm25'],'queries':1,'repeats':3,'k':1,'cutoffs':[1],'label_status':'DRAFT'}
        with tempfile.TemporaryDirectory() as tmp:
            result=labor_retrieval.summarize(Path(tmp),manifest,rows)
        self.assertEqual(result['variants']['bm25']['unique_queries'],1)
        self.assertEqual(result['variants']['bm25']['successful_attempts'],3)
        self.assertIsNone(result['variants']['bm25']['fact_coverage'])

    def test_report_keeps_common_judged_denominators(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'ablation').mkdir()
            one={'id':'q','repeat':1,'status':'OK','question':'q','answer':'a','elapsed_ms':1,'judge':{'status':'AI_JUDGED','correctness':1,'completeness':1,'evidence_support':1}}
            two={**one,'id':'other'}
            records=[{**one,'variant':'full'},{**two,'variant':'full'},{**one,'variant':'without_graph'}]
            (p/'ablation/responses.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records),encoding='utf-8')
            common.save(p/'state.json',{'stages':{'ablation':{'status':'ERROR'}}})
            suite.report(p)
            shared=common.read(p/'ablation/common_judged_comparison.json')
            self.assertEqual(shared['n_common_queries'],1)
            self.assertEqual(shared['variants']['full']['n'],1)
            self.assertIn('N/A',(p/'comparison_tables.md').read_text(encoding='utf-8'))

    def test_standard_notebook_is_compilable_and_primary_stages_are_separable(self):
        from make_notebook import notebook
        nb=notebook();texts=[]
        for cell in nb['cells']:
            if cell['cell_type']=='code':
                text=''.join(cell['source']);compile(text,'notebook','exec');texts.append(text)
        self.assertIn('preflight_external.py','\n'.join(texts))
        self.assertIn("if {'ablation','vlsp'} & set(STAGES):",'\n'.join(texts))
        self.assertIn('RESUME_EVALUATION_ZIP','\n'.join(texts))

    def test_archive_keeps_resolved_model_revision_metadata_without_weights(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);output=root/'run';output.mkdir();cache=root/'cache'
            common.save(output/'settings_resolved.json',{'cache':str(cache)})
            common.save(cache/'evaluation_pins/model.json',{'repo':'fixture/model','revision':'fixed_sha'})
            archive=suite.archive_run(output)
            with zipfile.ZipFile(archive) as z:
                pin=json.loads(z.read('model_revision_pins/model.json'))
                self.assertEqual(pin['revision'],'fixed_sha')
                self.assertTrue(all(not n.endswith(('.safetensors','.bin','.npy')) for n in z.namelist()))

    def test_negative_qa_migration_needs_no_fabricated_positive_evidence(self):
        row={'id':'outside','question':'outside domain','query_date':'2026-01-01','retrieval_eligible':False,
             'required_groups':[],'corpus_fingerprint':'old','expected_status':'OUT_OF_SCOPE','review_status':'APPROVED'}
        result,changed=suite.remap([row],NS(units=[],units_by_id={}),'new')
        self.assertEqual(result[0]['required_groups'],[]);self.assertEqual(result[0]['review_status'],'DRAFT')
        self.assertEqual(changed,['outside'])
        from gold import status_comparison
        self.assertTrue(status_comparison('OUT_OF_SCOPE','ABSTAIN'))
        self.assertIsNone(status_comparison('UNKNOWN_LABEL','ABSTAIN'))

if __name__=='__main__':unittest.main()
