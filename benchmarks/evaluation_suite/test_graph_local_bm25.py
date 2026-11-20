"""CPU diagnostic contracts: no models/downloads or real legal conclusions."""
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

spec=importlib.util.spec_from_file_location('graph_local_bm25',Path(__file__).with_name('graph_local_bm25.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
from vn_labor_online.models import Evidence


def item(uid):
    return Evidence(unit_id=uid,text=uid,score=1,retrieval_method='test')

class ComponentTests(unittest.TestCase):
    def test_union_preserves_base_and_caps_novel_not_duplicate_candidates(self):
        base=[item('a'),item('b')]
        out=p.candidate_union(base,[item('b'),item('c'),item('c'),item('d')],1)
        self.assertEqual([x.unit_id for x in out],['a','b','c'])
        self.assertEqual([x.unit_id for x in base],['a','b'])
        self.assertEqual(p.candidate_union(base,[item('c')],0),base)
        for bad in (-1,True,1.5):
            with self.assertRaises(ValueError):p.candidate_union(base,[],bad)

    def test_request_allowlist_excludes_qrels_and_answers(self):
        q={'id':'q','question':'question','query_date':'2026-09-15','required_groups':[['secret']],
           'answer':'secret','category':'exposed'}
        self.assertEqual(p.inference_request(q),{k:q[k] for k in ('id','question','query_date')})

    def test_arms_change_only_expansion_or_selection_and_keep_new_path(self):
        base=[item('a'),item('b')]
        new=item('c').model_copy(update={'graph_path':['edge'],'graph_relations':['REFERENCES']})
        graph=SimpleNamespace(references_by_source={'a':{'c'}})
        calls=[]
        def expand(seeds,gaps,query):
            calls.append((seeds,gaps,query));return [new],{'nodes_visited':3}
        graph.expand=expand
        q={'id':'q','question':'Nêu ngoại lệ','query_date':'2026-09-15'}
        with patch.object(p,'eligible',side_effect=lambda items,request:items):
            rows={arm:p.predict_arm(arm,q,base,graph,3) for arm in p.ARMS}
        self.assertEqual(rows['no_graph']['ids'],['a','b'])
        self.assertEqual(rows['graph_expansion']['ids'],['a','b','c'])
        self.assertEqual(rows['reference_selection_only']['ids'],['a','b'])
        self.assertEqual(rows['graph_and_selection']['ids'],['a','c','b'])
        self.assertEqual(rows['graph_and_selection']['graph_paths']['c']['edges'],['edge'])
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][1],[])

    def test_arm_order_counterbalances(self):
        self.assertEqual(p.arm_order(1,0),list(p.ARMS))
        self.assertEqual(p.arm_order(2,0),list(p.ARMS)[::-1])
        self.assertEqual(p.arm_order(1,1),list(p.ARMS)[::-1])

    def test_subgroup_query_means_and_graph_contrasts_not_repeat_pseudoreplication(self):
        names=('group_recall_at_k','mrr_at_k','group_ndcg_at_k','all_groups_found','pool_group_recall')
        rows=[]
        for arm in p.ARMS:
            for qid in ('a','b'):
                for repeat in (1,2):
                    value=1.0 if arm=='graph_and_selection' and qid=='a' else .5
                    rows.append({'arm':arm,'id':qid,'repeat':repeat,'ids':['x'],
                                 **{name:value for name in names}})
        members={'a':{'features':['explicit_reference']},'b':{'features':['ordinary']},
                 'outside_sample':{'features':['not_sampled']}}
        result=p.subgroup_analysis(rows,['a','b'],members,names,2)
        pair=next(r for r in result['paired'] if r['group']=='all_sample'
                  and r['contrast']=='GRAPH_EXPANSION_WITH_SELECTOR_ON'
                  and r['metric']=='group_recall_at_k')
        self.assertEqual(pair['n_queries'],2)
        self.assertEqual(pair['mean'],.25)
        self.assertEqual((pair['wins'],pair['ties'],pair['losses']),(1,1,0))
        tiny=next(r for r in result['paired'] if r['group']=='explicit_reference')
        self.assertIsNone(tiny['low'])
        empty=next(r for r in result['subgroup_tables'] if r['group']=='not_sampled')
        self.assertEqual(empty['n_queries'],0)
        self.assertIsNone(empty['group_recall_at_k'])
        self.assertTrue(all(v['stable'] for v in result['repeat_stability'].values()))
        rows[0]['ids']=['changed']
        changed=p.subgroup_analysis(rows,['a','b'],members,names,2)
        self.assertEqual(changed['repeat_stability']['no_graph']['rank_unstable_ids'],['a'])
        with self.assertRaisesRegex(ValueError,'schedule'):
            p.subgroup_analysis(rows[:-1],['a','b'],members,names,2)

    def test_provenance_records_measured_sources_and_package_versions(self):
        result=p.provenance()
        self.assertIn('src/vn_labor_online/graph.py',result['source_hashes'])
        self.assertIn('src/vn_labor_online/reference_selection.py',result['source_hashes'])
        self.assertEqual(set(result['packages']),{'bm25s','numpy','torch'})
        self.assertTrue(all(len(v)==64 for v in result['source_hashes'].values()))

    def test_wrong_artifact_and_selection_text_are_rejected_before_prediction(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            q={'id':'q','question':'Question','query_date':'2026-09-15'}
            gold=(json.dumps({**q,'required_groups':[['a']]})+'\n').encode()
            corpus=b'{"unit_id":"a"}\n'
            manifest={'questions_sha256':p.sha(gold),'corpus_jsonl_sha256':p.sha(corpus),
                      'artifact_file_hashes':{'05_graph/edges.jsonl':'expected'}}
            archive=root/'run.zip'
            with ZipFile(archive,'w') as z:
                z.writestr('bundle120/manifest.json',json.dumps(manifest))
                z.writestr('bundle120/inference_questions.jsonl',json.dumps(q)+'\n')
                z.writestr('bundle120/questions.jsonl',gold)
                z.writestr('bundle120/corpus.jsonl',corpus)
            selection=root/'selection.json'
            binding={'archive_sha256':p.sha(archive.read_bytes()),
                     'inference_sha256':p.sha((json.dumps(q)+'\n').encode()),
                     'corpus_sha256':manifest['corpus_jsonl_sha256'],'gold_sha256':manifest['questions_sha256']}
            selection.write_text(json.dumps({**binding,'sample_ids':['q'],'membership':[q]}),encoding='utf8')
            with patch.object(p,'runtime',return_value=(None,None,None,None,{'05_graph/edges.jsonl':'wrong'})) as rt:
                with self.assertRaisesRegex(ValueError,'Artifact fingerprint'):
                    p.evaluate(archive,root/'artifact',selection,root/'out',root/'cache')
                rt.assert_called_once()
            selection.write_text(json.dumps({'sample_ids':['q'],'membership':[{**q,'question':'tampered'}]}),encoding='utf8')
            with patch.object(p,'runtime') as rt:
                with self.assertRaisesRegex(ValueError,'Selection differs'):
                    p.evaluate(archive,root/'artifact',selection,root/'out',root/'cache')
                rt.assert_not_called()

if __name__=='__main__':unittest.main()
