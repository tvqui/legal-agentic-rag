import importlib.util,json,tempfile,unittest
from unittest.mock import Mock
from pathlib import Path
from types import SimpleNamespace as NS

spec=importlib.util.spec_from_file_location('comparison',Path(__file__).with_name('run.py'))
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class MetricsTests(unittest.TestCase):
    def test_alternative_versions_do_not_count_as_two_required_rules(self):
        m=mod.metrics(['a','a_version','b'],[['a','a_version'],['b']],3)
        self.assertEqual(m['group_recall_at_k'],1)
        self.assertEqual(m['novel_group_precision_at_k'],2/3)
        self.assertLess(m['group_ndcg_at_k'],1)
        self.assertTrue(m['all_groups_found'])

    def test_missing_results_count_against_recall(self):
        m=mod.metrics([], [['a'],['b']],10)
        self.assertEqual(m['group_recall_at_k'],0)
        self.assertEqual(m['mrr_at_k'],0)

    def test_ideal_ranking_and_topk_cutoff(self):
        self.assertEqual(mod.metrics(['a','b'],[['a'],['b']],2)['group_ndcg_at_k'],1)
        self.assertEqual(mod.metrics(['noise','a'],[['a']],1)['group_recall_at_k'],0)

    def test_gold_mismatch_and_overlap_refused(self):
        row={'id':'x','question':'question','query_date':'2026-10-23','corpus_fingerprint':'build','required_groups':[['a']]}
        store=NS(units_by_id={'a':{}})
        mod.validate_gold([row],store,'build')
        with self.assertRaises(ValueError):mod.validate_gold([row],store,'other')
        row['required_groups']=[['a'],['a']]
        with self.assertRaises(ValueError):mod.validate_gold([row],store,'build')

    def test_errors_are_reported_instead_of_scored_as_success(self):
        manifest={'methods':['bm25','dense'],'queries':1,'repeats':1,'label_status':'DRAFT'}
        rows=[{'id':'q','question':'text','method':'dense','repeat':1,'status':'ERROR','error':'missing model','elapsed_ms':1}]
        with tempfile.TemporaryDirectory() as tmp:
            report=mod.summarize(Path(tmp),manifest,rows)
            self.assertFalse(report['complete'])
            self.assertEqual(report['variants']['dense']['errors'],1)
            self.assertIsNone(report['variants']['dense']['group_recall_at_k'])
            self.assertIsNone(report['variants']['bm25']['mean_ms'])

    def test_methods_use_only_declared_channels_and_same_filters(self):
        from vn_labor_online.models import Evidence
        def item(uid,start='2021-01-01',end=None):
            return Evidence(unit_id=uid,text='Source text',document_id='doc',retrieval_method='test',
                source_url='https://example.test/law',authority_rank=100,
                valid_from=start,valid_to=end,temporal_verified=True)
        lexical=item('lexical');vector=item('vector');expired=item('expired',end='2022-01-01')
        added=item('graph'); graph=NS(expand=Mock(return_value=([added,expired],{'rounds':1})))
        row={'question':'question','query_date':'2026-10-23'}
        for method in mod.METHODS:
            with self.subTest(method=method):
                r=NS(bm25=Mock(return_value=[lexical,expired]),dense=Mock(return_value=[vector,expired]),
                    fusion=Mock(side_effect=lambda channels:list({e.unit_id:e for c in channels for e in c}.values())))
                graph.expand.reset_mock()
                result,stats=mod.retrieve(method,row,r,graph,None)
                self.assertNotIn('expired',[e.unit_id for e in result])
                self.assertEqual(r.bm25.call_count,int(method!='dense'))
                self.assertEqual(r.dense.call_count,int(method!='bm25'))
                self.assertEqual(graph.expand.call_count,int(method=='hybrid_graph'))
                self.assertEqual('graph' in [e.unit_id for e in result],method=='hybrid_graph')

if __name__=='__main__':unittest.main()
