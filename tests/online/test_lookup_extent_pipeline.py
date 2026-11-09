import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from .test_online_core import fixture
from vn_labor_online.config import OnlineConfig,RetrievalConfig,GraphConfig
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_online.models import QueryRequest,AdjudicationDraft,Claim

class LookupExtentPipelineTests(unittest.TestCase):
    def run_lookup(self,children,max_units=2):
        with tempfile.TemporaryDirectory() as directory,patch.dict('os.environ',{},clear=True):
            root=Path(directory);build=fixture(root)
            cfg=OnlineConfig(artifact_source=str(root),expected_build_id=build,
                cache_dir=str(root/'cache'),trace_dir=str(root/'traces'),max_verified_units=max_units,
                retrieval=RetrievalConfig(dense_enabled=False,bm25_enabled=False),graph=GraphConfig(enabled=False))
            pipeline=OnlinePipeline(cfg);base=pipeline.store.units_by_id['prov_1']
            for i in range(children):
                uid='child_'+str(i);child={**base,'unit_id':uid,'provision_version_id':uid,
                    'provision_identity_id':uid,'level':'CLAUSE','clause_number':str(i+1),
                    'text':f'{i+1}. Người lao động được biết thông tin công việc.',
                    'source_text':f'{i+1}. Người lao động được biết thông tin công việc.',
                    'provenance_span':{'char_start':40+60*i,'char_end':99+60*i}}
                pipeline.store.units.append(child);pipeline.store.units_by_id[uid]=child
                node={'id':uid,'label':'Clause','properties':{'article_number':'1','clause_number':str(i+1),'point_number':''}}
                pipeline.store.nodes.append(node);pipeline.store.nodes_by_id[uid]=node
                pipeline.store.edges.append({'id':'edge_'+uid,'source':uid,'target':'prov_1','type':'PART_OF','properties':{}})
            seen=[]
            def generate(pack,*args):
                seen.append(pack)
                return AdjudicationDraft(answer_summary='Nội dung đã tìm thấy.',claims=[Claim(claim_id='c',
                    text=item.text,evidence_ids=[item.evidence_id]) for item in pack.evidence],
                    applicable_law_versions=[]),[]
            pipeline.adjudicator.generate=Mock(side_effect=generate)
            result=pipeline.ask(QueryRequest(question='Điều 1 Nghị định 145/2020/ND-CP quy định gì? Hãy trình bày đầy đủ.',query_date='2024-01-01'))
            return seen,result
    def test_exact_budget_equality_is_complete_not_truncated(self):
        packs,result=self.run_lookup(1)
        self.assertTrue(packs)
        self.assertTrue(packs[0].lookup_scope_complete)
        self.assertNotIn('LOOKUP_SOURCE_SCOPE_INCOMPLETE',result.warnings)
    def test_unseen_children_are_disclosed_even_with_supported_claims(self):
        packs,result=self.run_lookup(3)
        self.assertTrue(packs)
        self.assertFalse(packs[0].lookup_scope_complete)
        self.assertIn('LOOKUP_SOURCE_SCOPE_INCOMPLETE',result.warnings)
        self.assertIn('lookup_source_scope',result.limitations)

if __name__=='__main__':unittest.main()
