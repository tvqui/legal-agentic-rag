import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import common,external,suite,qa,labor_retrieval

class SuiteTests(unittest.TestCase):
    def test_artifact_ambiguity_is_not_automatically_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'vn_labor_results.zip').write_bytes(b'fake')
            self.assertEqual(common.detect_artifact(p),p/'vn_labor_results.zip')
            (p/'dataset/reports').mkdir(parents=True)
            (p/'dataset/reports/final_outputs_validation.json').write_text('{}')
            with self.assertRaises(ValueError):common.detect_artifact(p)

    def test_redaction_preserves_model_token_limits(self):
        self.assertEqual(common.redact({'api_key':'secret','context_tokens':8192,'nested':{'access_token':'x'}}),
            {'api_key':'[REDACTED]','context_tokens':8192,'nested':{'access_token':'[REDACTED]'}})

    def test_ablation_changes_only_one_component_plus_shared_shortcuts(self):
        from vn_labor_online.config import OnlineConfig
        base=OnlineConfig(artifact_source='fake');base.reranker.enabled=True
        for name in qa.VARIANTS:
            cfg=qa.variant_config(base,name)
            self.assertEqual(cfg.graph.enabled,name!='without_graph')
            self.assertEqual(cfg.reranker.enabled,name!='without_reranker')
            self.assertEqual(cfg.adjudication.semantic_review,name!='without_review')
            self.assertFalse(cfg.retrieval.profile_fast_path)
        self.assertTrue(base.retrieval.profile_fast_path)

    def test_disabled_auditor_does_not_forge_verified_decisions(self):
        items=[NS(unit_id='source')]
        accepted,decisions,warnings=qa.DisabledAuditor().audit(items)
        self.assertEqual(accepted,items)
        self.assertEqual(decisions[0].audit_status,'UNRESOLVED')
        self.assertFalse(decisions[0].supports_claim)

    def test_independent_ir_metrics_and_rrf(self):
        m=external.ir_metrics(['x','a','a','b'],['a','b'],4)
        self.assertEqual(m['recall_at_k'],1);self.assertEqual(m['precision_at_k'],.5)
        self.assertEqual(m['mrr_at_k'],.5)
        self.assertEqual(external.rrf([['b','a'],['a','c']])[0],'a')

    def test_unknown_external_schema_fails(self):
        self.assertEqual(external.field({'text':'ok'},'content','text'),'ok')
        with self.assertRaises(ValueError):external.field({'answer':'wrong'},'text')

    def test_no_judge_is_not_scored_as_zero_or_human_accuracy(self):
        records=[{'status':'OK','elapsed_ms':20,'claims':[],'judge':{'status':'NOT_CONFIGURED'},'reference_audit':'PASS'}]
        value=common.answer_summary(records)
        self.assertIsNone(value['ai_correctness']);self.assertEqual(value['ai_judged'],0)
        self.assertEqual(value['content_answers'],0)

    def test_changed_build_rebinds_but_revokes_approval(self):
        unit={'unit_id':'new','instrument_number':'45/2019/QH14','article_number':'17','clause_number':'1',
            'point_number':'','level':'CLAUSE','text':'Source content','kind':'PROVISION','valid_from':'2021-01-01','temporal_verified':True}
        locator={k:unit[k] for k in ['instrument_number','article_number','clause_number','point_number','level']}
        row={'id':'q','question':'question','query_date':'2026-10-23','required_groups':[['old']],
            'required_group_locators':[[locator]],'corpus_fingerprint':'old_fp','review_status':'APPROVED','reviewer':'person'}
        store=NS(units=[unit],units_by_id={'new':unit})
        rows,changes=suite.remap([row],store,'new_fp')
        self.assertEqual(rows[0]['required_groups'],[['new']]);self.assertEqual(rows[0]['review_status'],'DRAFT')
        self.assertIsNone(rows[0]['reviewer']);self.assertEqual(changes,['q'])
        self.assertEqual(row['review_status'],'APPROVED')

    def test_new_build_without_mapping_refused(self):
        with self.assertRaises(ValueError):suite.remap([{'id':'q','corpus_fingerprint':'old'}],NS(),'new')

    def test_reports_show_not_evaluated_instead_of_fabricating_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);common.save(p/'state.json',{'stages':{'zalo':{'status':'ERROR'}}})
            suite.report(p);text=(p/'comparison_tables.md').read_text(encoding='utf-8')
            self.assertIn('NOT_EVALUATED',text);self.assertIn('N/A',text)
            self.assertEqual(common.read(p/'comparison_tables.json')['rows'],[])

    def test_notebook_python_cells_compile(self):
        from make_notebook import notebook
        nb=notebook()
        for cell in nb['cells']:
            if cell['cell_type']=='code':compile(''.join(cell['source']),'notebook','exec')

    def test_zalo_adapter_keeps_full_corpus_and_test_qrels(self):
        data={'corpus':[{'corpus_id':'a','text':'text a'},{'corpus_id':'b','text':'unrelated distractor'}],
          'queries':[{'query_id':'q','text':'question'}],
          'qrels':[{'corpus_id':'a','query_id':'q','score':1}]}
        settings={'cache':'unused','zalo':{'repo':'fixture','revision':'abc','qrels_split':'test','limit':1}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(external,'pin',return_value={'revision':'abc'}),\
             patch.object(external,'dataset',side_effect=lambda meta,name,split=None:data[name]):
            external.prepare_zalo(tmp,settings)
            self.assertEqual(len(common.jsonl(Path(tmp)/'zalo/corpus.jsonl')),2)
            self.assertEqual(common.jsonl(Path(tmp)/'zalo/questions.jsonl')[0]['relevant_ids'],['a'])

    def test_vlsp_adapter_preserves_reference_and_discloses_selection(self):
        data=[{'question':'Hợp đồng lao động được xử lý thế nào?','answer':'fixture reference'},
          {'question':'Thuế giá trị gia tăng?','answer':'excluded'}]
        settings={'cache':'unused','vlsp':{'repo':'fixture','revision':'abc','subset':'syllogism_questions',
          'split':'train','selection':'labor_keywords','query_date':'2025-07-15','date_assumption':'fixture','limit':2}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(external,'pin',return_value={'revision':'abc'}),\
             patch.object(external,'dataset',return_value=data):
            external.prepare_vlsp(tmp,settings)
            rows=common.jsonl(Path(tmp)/'vlsp/questions.jsonl')
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['reference_answer'],'fixture reference')
            self.assertEqual(common.read(Path(tmp)/'vlsp/source.json')['excluded_ids'],['vlsp_1'])

    def test_failed_stage_retry_preserves_old_attempt_instead_of_reusing_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);folder=output/'retrieval';folder.mkdir();(folder/'summary.json').write_text('{}')
            suite.retain_previous_attempt(output,'retrieval')
            self.assertFalse(folder.exists())
            self.assertEqual(len(list((output/'attempt_history').glob('*/summary.json'))),1)

    def test_qa_worker_writes_all_five_variants_without_external_calls(self):
        from vn_labor_online.config import OnlineConfig
        from vn_labor_online.models import Stop,Claim
        cfg=OnlineConfig(artifact_source='fixture',adjudication={'mode':'ollama'})
        response=NS(answer='fixture answer',status=Stop.PARTIAL_ALLOWED,
          claims=[Claim(claim_id='c',text='fixture claim',evidence_ids=['s'])],citations=[],warnings=[],parts=[],
          trace=NS(reference_audit='PASS',timings_ms={},trace_id='fixture',retrieval_rounds=1,
            events=[{'event':'retrieval_execution','reranker_requested':True}]))
        factories=[]
        def factory(config):
            pipe=NS(ask=Mock(return_value=response),close=Mock(),store=NS(units_by_id={}))
            factories.append(pipe);return pipe
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'labor_gold.jsonl').write_text(json.dumps({'id':'q','question':'fixture question',
                'reference_answer':'fixture reference','query_date':'2026-10-23','review_status':'DRAFT',
                'expected_status':'NEED_MORE_FACTS','missing_facts':['contract type']})+'\n')
            with patch('vn_labor_online.config.load_config',return_value=cfg),\
                 patch('vn_labor_online.pipeline.OnlinePipeline',side_effect=factory),\
                 patch.object(qa,'score_judge',return_value={'status':'NOT_CONFIGURED'}):
                result=qa.evaluate(p,{'artifact':'fixture','repeats':3,'qa_repeats':1,'case_timeout_seconds':30,'judge':{}})
            self.assertTrue(result['complete']);self.assertEqual(len(result['variants']),5)
            self.assertEqual(len(common.jsonl(p/'ablation/responses.jsonl')),5)
            self.assertTrue(all(v['ai_correctness'] is None for v in result['variants'].values()))
            self.assertTrue(all(v['draft_disposition_labelled']==1 for v in result['variants'].values()))
            common.save(p/'state.json',{'stages':{'ablation':{'status':'COMPLETE'}}})
            suite.report(p)
            self.assertIn('fixture answer',(p/'ablation/answers.md').read_text(encoding='utf-8'))
            self.assertIn('expected_status',(p/'ablation/answers.csv').read_text(encoding='utf-8-sig'))
            self.assertTrue(all(pipe.close.called for pipe in factories))

if __name__=='__main__':unittest.main()
