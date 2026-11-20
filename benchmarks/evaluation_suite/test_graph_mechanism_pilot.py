"""Meaningful unit checks for mechanism audit isolation and frozen schedules."""
import hashlib,importlib.util,json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
spec=importlib.util.spec_from_file_location('mechanism',Path(__file__).with_name('graph_mechanism_pilot.py'))
pilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(pilot)

def fixture(root,broken=None):
    questions=[{'id':'a','question':'Nêu các ngoại lệ được dẫn tại khoản này?','query_date':'2026-09-15','required_groups':[['x'],['y']]},
               {'id':'b','question':'Tiền lương là gì?','query_date':'2026-09-15','required_groups':[['x']]}]
    raw=lambda rows: ''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows).encode()
    gold=raw(questions);corpus=raw([{'unit_id':'x','source_text':'heading','article_number':'1'},
                                 {'unit_id':'y','source_text':'rule','article_number':'2'}])
    edge=raw([{'id':'edge','source':'x','target':'y','type':'REFERENCES'}])
    methods=['hybrid','hybrid_graph','hybrid_rerank','hybrid_graph_rerank']
    run={'methods':methods,'selected_ids':['a','b'],'repeats':2,'k':1}
    rows=[{'method':m,'id':q['id'],'repeat':r,'status':'OK','elapsed_ms':1 if 'graph' not in m else 2,
           'result':{'retrieved_ids':['x'] if m=='hybrid' else ['x','y'] if m!='hybrid_graph_rerank' else ['y','x']}}
          for m in methods for q in questions for r in (1,2)]
    if broken=='missing':rows.pop()
    if broken=='duplicate':rows.append(rows[0])
    if broken=='error':rows[0]['status']='ERROR'
    if broken=='unknown':rows[0]['result']['retrieved_ids']=['invalid']
    manifest={'questions_sha256':pilot.sha(gold),'corpus_jsonl_sha256':pilot.sha(corpus),'label_status':'DRAFT',
              'artifact_file_hashes':{'05_graph/edges.jsonl':pilot.sha(edge)}}
    if broken=='hash':manifest['questions_sha256']='wrong'
    artifact=root/'artifact';(artifact/'05_graph').mkdir(parents=True)
    (artifact/'05_graph/edges.jsonl').write_bytes(edge if broken!='edges' else b'wrong')
    path=root/'archive.zip'
    with ZipFile(path,'w') as z:
        for name,obj in [('bundle120/manifest.json',manifest),('retrieval/run_manifest.json',run)]:z.writestr(name,json.dumps(obj))
        z.writestr('bundle120/questions.jsonl',gold);z.writestr('bundle120/corpus.jsonl',corpus)
        z.writestr('bundle120/inference_questions.jsonl',raw([{k:q[k] for k in ('id','question','query_date')} for q in questions]))
        z.writestr('retrieval/responses.jsonl',raw(rows))
    return path,artifact

class MechanismTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name);self.addCleanup(self.temp.cleanup)
    def test_time_document_identifiers_are_not_event_dates(self):
        self.assertNotIn('time_specific_or_transition_proxy',pilot.features('Điều 1 Nghị định 145/2020/NĐ-CP quy định gì?'))
        self.assertIn('time_specific_or_transition_proxy',pilot.features('Ngày 15/12/2020 tôi nghỉ việc thì sao?'))
    def test_negative_fact_is_not_exception_request(self):
        self.assertIn('exception_excluded_proxy',pilot.features('Nếu tôi không thuộc ngoại lệ thì sao?'))
        self.assertIn('exception_requested_proxy',pilot.features('Tôi không thuộc ngoại lệ. Hãy nêu các ngoại lệ?'))
        self.assertNotIn('crossref_requested_proxy',pilot.features('Theo quy định tại Điều 35 thì sao?'))
    def test_sampling_reproducible_not_input_order_or_outcome(self):
        rows=[{'id':str(i),'features':['ordinary_or_unclassified' if i<6 else 'multi_document_proxy']} for i in range(10)]
        a=pilot.sample_membership(rows);b=pilot.sample_membership(list(reversed(rows)))
        self.assertEqual(a,b);self.assertEqual(len(a),5)
        with self.assertRaises(ValueError):pilot.sample_membership(rows,per_feature=0)
    def test_real_2x2_and_metadata_not_qa_claims(self):
        path,artifact=fixture(self.root);out=self.root/'out';r=pilot.evaluate(path,artifact,out)
        self.assertEqual(r['query_count'],2);self.assertFalse(r['held_out'])
        self.assertEqual(r['unmeasured']['citation_accuracy'],'NOT_EVALUATED')
        catalog={x['feature']:x for x in r['coverage_catalog']}
        self.assertEqual(catalog['multi_document_proxy']['status'],'NOT_SAMPLED')
        self.assertEqual(catalog['time_specific_or_transition_proxy']['population_count'],0)
        self.assertEqual(catalog['literal_lookup_proxy']['metric_status'],'NOT_EVALUATED_NO_QUESTIONS')
        self.assertTrue((out/'coverage_catalog.csv').is_file())
        self.assertEqual(r['capabilities']['IMPLEMENTS_edge_count'],0)
        self.assertTrue(r['capabilities']['temporal_filter_shared'])
        cases=json.loads((out/'cases.json').read_text(encoding='utf8'))
        self.assertTrue(all('expansion_same_selector_deltas' in q and 'same_selector_after_missing_groups' in q for q in cases))
        full=[x for x in r['pairs'] if x['group']=='all_queries' and x['contrast']=='GRAPH_ONLY_STORED' and x['metric']=='mrr_at_k'][0]
        self.assertEqual(full['n_queries'],2);self.assertEqual(full['losses'],1)
        e=json.loads((out/'evidence.json').read_text(encoding='utf8'))
        row=next(x for x in e if x['query_id']=='a' and x['unit_id']=='y')
        self.assertEqual(row['structural_path'][0]['type'],'REFERENCES')
        self.assertIn('NOT_ACTUAL',row['path_status'])
        with self.assertRaises(FileExistsError):pilot.evaluate(path,artifact,out)
    def test_failed_missing_corrupt_schedules_are_not_dropped(self):
        for kind in ['missing','duplicate','error','unknown','hash','edges']:
            with self.subTest(kind=kind):
                root=self.root/kind;root.mkdir();path,artifact=fixture(root,kind)
                with self.assertRaises(ValueError):pilot.evaluate(path,artifact,root/'out')
    def test_outcome_preserves_mixed_improvement_and_harm(self):
        self.assertEqual(pilot.outcome({'recall':.5,'rank':-.1}),'MIXED')
        self.assertEqual(pilot.outcome({'recall':0,'rank':-.1}),'HARMED')
        self.assertEqual(pilot.outcome({'recall':0}),'UNCHANGED')

    def test_bounded_bidirectional_connectivity_is_not_infinite(self):
        e={'id':'e','source':'a','target':'b','type':'PART_OF'}
        adj={'a':[(e,'b','OUT')],'b':[(e,'a','IN')]}
        self.assertEqual(pilot.structural_paths(['b'],['a'],adj,1)['a'][0]['direction'],'IN')
        self.assertNotIn('a',pilot.structural_paths(['b'],['a'],adj,0))

if __name__=='__main__':unittest.main()
