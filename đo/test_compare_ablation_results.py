import json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import eval_core as e
import compare_ablation_results as c

class CompareAblationTests(unittest.TestCase):
    def archive(self,path,method,control='same'):
        controls={'fixture':control};key=e.fingerprint(controls)
        manifest={'comparison_key':key,'comparison_controls':controls,'methods':[method],'task':'qa',
            'bundle':{'label_status':'DRAFT','evaluation_scope':'DEVELOPMENT_NOT_HELD_OUT'},
            'scheduled_queries':1,'selected_ids':['q'],'repeats':1}
        record={'id':'q','method':method,'repeat':1,'status':'OK','elapsed_ms':1,'metrics':{},'result':{'answer':'synthetic','citations':[]}}
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('runs/'+method+'/run_manifest.json',json.dumps(manifest))
            z.writestr('runs/'+method+'/responses.jsonl',json.dumps(record)+'\n')
    def test_combines_two_independent_archives_without_api(self):
        with tempfile.TemporaryDirectory() as tmp,patch('eval_core.plot_table'):
            root=Path(tmp);a=root/'full.zip';b=root/'without_graph.zip'
            self.archive(a,'full');self.archive(b,'without_graph')
            table=c.compare([a,b],root/'report')
            self.assertEqual({r['method'] for r in table},{'full','without_graph'})
            self.assertEqual(e.read(root/'report/input_provenance.json')['comparison_groups'],1)
            self.assertEqual(e.sha(a),e.read(root/'report/input_provenance.json')['inputs'][0]['zip_sha256'])
    def test_different_models_or_controls_remain_separate(self):
        with tempfile.TemporaryDirectory() as tmp,patch('eval_core.plot_table'):
            root=Path(tmp);a=root/'full.zip';b=root/'without_graph.zip'
            self.archive(a,'full','model-A');self.archive(b,'without_graph','model-B')
            c.compare([a,b],root/'report')
            self.assertEqual(e.read(root/'report/input_provenance.json')['comparison_groups'],2)
            self.assertEqual(e.read(root/'report/comparison/paired_deltas.json'),[])
    def test_two_checkpoints_of_the_same_configuration_are_not_pooled(self):
        with tempfile.TemporaryDirectory() as tmp,patch('eval_core.plot_table'):
            root=Path(tmp);a=root/'full.zip';b=root/'full-other.zip'
            self.archive(a,'full');self.archive(b,'full')
            with self.assertRaisesRegex(ValueError,'Duplicate configuration'):c.compare([a,b],root/'report')
    def test_unsafe_archive_cannot_write_outside_extraction_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'unsafe.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape.txt','synthetic')
            with self.assertRaises(ValueError):c.extract_checked(archive,root/'extract')
            self.assertFalse((root/'escape.txt').exists());self.assertFalse((root/'extract').exists())

if __name__=='__main__':unittest.main()
