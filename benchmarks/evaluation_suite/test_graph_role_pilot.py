"""Checks for query-only grouping and honest paired pilot accounting."""
import hashlib
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile
import unittest
from tempfile import TemporaryDirectory

spec=importlib.util.spec_from_file_location('graph_role_pilot',Path(__file__).with_name('graph_role_pilot.py'))
pilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(pilot)
METHODS=['hybrid','hybrid_graph','hybrid_rerank','hybrid_graph_rerank']


def archive(tmp_path, broken=None):
    questions=[{'id':'a','question':'Nêu các ngoại lệ được dẫn chiếu?','query_date':'2026-09-15',
                'required_groups':[['x'],['y']]},
               {'id':'b','question':'Tiền lương là gì?','query_date':'2026-09-15','required_groups':[['x']]}]
    raw=lambda rows: ''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows).encode()
    gold=raw(questions);corpus=raw([{'unit_id':'x'},{'unit_id':'y'}])
    manifest={'questions_sha256':hashlib.sha256(gold).hexdigest(),
              'corpus_jsonl_sha256':hashlib.sha256(corpus).hexdigest(),'label_status':'DRAFT',
              'artifact_file_hashes':{'05_graph/edges.jsonl':'edge_hash'}}
    run={'methods':METHODS,'selected_ids':['a','b'],'repeats':2,'k':1}
    rows=[{'method':m,'id':q['id'],'repeat':r,'status':'OK',
           'result':{'retrieved_ids':['x','y'] if m!='hybrid_graph_rerank' else ['y','x']}}
          for m in METHODS for q in questions for r in (1,2)]
    if broken=='missing':rows.pop()
    if broken=='failed':rows[0]['status']='ERROR'
    if broken=='duplicate':rows.append(rows[0])
    if broken=='unknown':rows[0]['result']['retrieved_ids']=['z']
    if broken=='fingerprint':manifest['questions_sha256']='bad'
    path=tmp_path/'run.zip'
    with ZipFile(path,'w') as z:
        z.writestr('bundle120/manifest.json',json.dumps(manifest));z.writestr('retrieval/run_manifest.json',json.dumps(run))
        z.writestr('bundle120/questions.jsonl',gold);z.writestr('bundle120/corpus.jsonl',corpus)
        z.writestr('bundle120/inference_questions.jsonl',raw([{k:q[k] for k in ('id','question','query_date')} for q in questions]))
        z.writestr('retrieval/responses.jsonl',raw(rows))
    return path


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.tmp=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_classifier_is_semantic_proxy_not_word_substring(self):
        self.assertEqual(pilot.classify('Văn bản và phạm vi áp dụng'), ['ordinary_or_unclassified'])
        self.assertNotIn('explicit_cross_reference',pilot.classify('Theo quy định tại Điều 35, thời hạn là gì?'))
        self.assertIn('explicit_cross_reference',pilot.classify('Nêu các nhóm được dẫn tại khoản này?'))
        self.assertIn('exception_mentioned_not_requested',pilot.classify('Tôi không thuộc trường hợp ngoại lệ nghỉ ngay.'))
        self.assertIn('exception_language',pilot.classify('Tôi không thuộc ngoại lệ. Hãy nêu các ngoại lệ?'))
        self.assertIn('exception_mentioned_not_requested',pilot.classify('Nếu không thuộc ngoại lệ thì sao?'))
        self.assertIn('literal_lookup_proxy',pilot.classify('Hãy trích nguyên văn điều luật.'))

    def test_bootstrap_query_unit_not_repeats(self):
        result=pilot.paired_ci([.5,-.5],samples=200,seed=4)
        self.assertEqual(result['n_queries'],2)
        self.assertEqual((result['wins'],result['ties'],result['losses']),(1,0,1))
        self.assertEqual(result['mean'],0)
        self.assertEqual(result,pilot.paired_ci([.5,-.5],samples=200,seed=4))
        self.assertIsNone(pilot.paired_ci([.5])['low'])

    def test_complete_pilot_query_macro(self):
        tmp_path=self.tmp
        result=pilot.evaluate(archive(tmp_path),tmp_path/'out')
        self.assertEqual((result['n_queries'],result['repeats']),(2,2))
        paired=[r for r in result['paired_vs_hybrid_rerank'] if r['group']=='all_queries' and r['metric']=='mrr_at_k']
        self.assertEqual(paired[0]['n_queries'],2)
        self.assertEqual((paired[0]['losses'],paired[0]['ties']),(1,1))
        self.assertFalse(result['independent_heldout'])
        membership=json.loads((tmp_path/'out/membership.json').read_text(encoding='utf-8'))
        self.assertEqual(membership['selection_basis'],'QUERY_TEXT_ONLY_NOT_OUTCOMES')
        self.assertNotIn('required_groups',membership['rows'][0])
        self.assertTrue((tmp_path/'out/tables.csv').is_file())

    def test_reject_incomplete_or_corrupt_inputs(self):
        for broken in ['missing','failed','duplicate','unknown','fingerprint']:
            with self.subTest(broken=broken):
                root=self.tmp/broken;root.mkdir()
                with self.assertRaises(ValueError):pilot.evaluate(archive(root,broken),root/'out')

    def test_reject_replay_changes_candidate_pool(self):
        tmp_path=self.tmp;path=archive(tmp_path)
        rows=[{'id':q,'repeat':r,'variant':'reference_closure','graph_path_used':True,'ids':['x']}
              for q in ('a','b') for r in (1,2)]
        replay=tmp_path/'predictions.jsonl';replay.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
        meta={'archive_sha256':pilot.digest(path.read_bytes()),
              'selector_sha256':pilot.digest((pilot.ROOT/'src/vn_labor_online/reference_selection.py').read_bytes()),
              'edge_sha256':'edge_hash'}
        (tmp_path/'summary.json').write_text(json.dumps(meta),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'candidate pool'):pilot.evaluate(path,tmp_path/'out',replay)

    def test_reject_wrong_replay_source(self):
        path=archive(self.tmp);replay=self.tmp/'predictions.jsonl'
        replay.write_text('',encoding='utf-8')
        (self.tmp/'summary.json').write_text(json.dumps({'archive_sha256':'wrong'}),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'provenance'):pilot.evaluate(path,self.tmp/'out',replay)

    def matching_artifact(self, archive_path):
        raw = (json.dumps({'source':'x','target':'y','type':'REFERENCES'})+'\n').encode()
        artifact = self.tmp/'artifact'
        (artifact/'05_graph').mkdir(parents=True)
        (artifact/'05_graph/edges.jsonl').write_bytes(raw)
        with ZipFile(archive_path) as z:
            members = {name:z.read(name) for name in z.namelist()}
        manifest = json.loads(members['bundle120/manifest.json'])
        manifest['artifact_file_hashes']['05_graph/edges.jsonl'] = pilot.digest(raw)
        members['bundle120/manifest.json'] = json.dumps(manifest).encode()
        with ZipFile(archive_path,'w') as z:
            for name, content in members.items(): z.writestr(name,content)
        return artifact, pilot.digest(raw)

    def test_selection_counterfactual_uses_matching_edges_without_adding_candidates(self):
        path = archive(self.tmp)
        artifact, _ = self.matching_artifact(path)
        result = pilot.evaluate(path,self.tmp/'out',artifact=artifact)
        counter = [r for r in result['tables'] if r['group']=='all_queries'
                   and r['method']=='selection_without_expansion']
        self.assertEqual(len(counter),1)
        self.assertEqual(counter[0]['group_recall_at_k'],.75)
        (artifact/'05_graph/edges.jsonl').write_text('corrupt',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'Graph fingerprint'):
            pilot.evaluate(path,self.tmp/'out_bad',artifact=artifact)

    def test_reject_same_pool_replay_permutation_with_valid_sidecar(self):
        path = archive(self.tmp)
        artifact, edge_hash = self.matching_artifact(path)
        replay = self.tmp/'predictions.jsonl'
        rows = [{'id':q,'repeat':r,'variant':'reference_closure',
                 'graph_path_used':True,'ids':['x','y']}
                for q in ('a','b') for r in (1,2)]
        replay.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf8')
        meta = {'archive_sha256':pilot.digest(path.read_bytes()),
                'selector_sha256':pilot.digest((pilot.ROOT/'src/vn_labor_online/reference_selection.py').read_bytes()),
                'edge_sha256':edge_hash}
        (self.tmp/'summary.json').write_text(json.dumps(meta),encoding='utf8')
        with self.assertRaisesRegex(ValueError,'ordering'):
            pilot.evaluate(path,self.tmp/'out',replay,artifact)

    def test_never_overwrite_existing_results(self):
        path=archive(self.tmp);out=self.tmp/'out';out.mkdir()
        with self.assertRaises(FileExistsError):pilot.evaluate(path,out)


if __name__=='__main__':
    unittest.main()
