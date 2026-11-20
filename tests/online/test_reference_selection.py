import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from vn_labor_online.config import GraphConfig
from vn_labor_online.graph import GraphExplorer
from vn_labor_online.models import Evidence
from vn_labor_online.reference_selection import post_select_references, reference_intent


def evidence(uid, **kwargs):
    return Evidence(unit_id=uid, text='unchanged '+uid, retrieval_method='synthetic', **kwargs)


class ReferenceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.pool=[evidence(uid,score=1/(rank+1),rank=rank+1) for rank,uid in enumerate('abcdef')]

    def test_moves_only_direct_references_into_head_and_retains_full_pool(self):
        out=post_select_references(self.pool,{'a':['f','e'],'e':['d']},'Nêu ngoại lệ được viện dẫn',4)
        self.assertEqual([x.unit_id for x in out],['a','e','f','b','c','d'])
        self.assertEqual([x.rank for x in out],list(range(1,7)))

    def test_protects_primary_and_uses_semantic_not_edge_order(self):
        out=post_select_references(self.pool,{'a':['f','e']},'Các điều được dẫn có nội dung gì?',2)
        self.assertEqual([x.unit_id for x in out[:2]],['a','e'])

    def test_no_generic_legal_word_trigger(self):
        for query in ('Nêu căn cứ áp dụng theo quy định','Mức lương cơ bản là gì?','Chép nguyên văn một điều'):
            self.assertEqual([x.unit_id for x in post_select_references(self.pool,{'a':['f']},query,3)],list('abcdef'))

    def test_vietnamese_english_and_unicode_variants(self):
        for query in ('NGOẠI LỆ','được viện dẫn','ĐƯỢC DẪN','dan chieu','referred to','cross-references','exceptions'):
            with self.subTest(query=query): self.assertTrue(reference_intent(query))

    def test_explicit_refusal_is_not_confused_with_negative_legal_fact(self):
        for query in ('Không bàn về ngoại lệ','Đừng đề cập ngoại lệ','do not discuss exceptions',"don't discuss exceptions"):
            self.assertFalse(reference_intent(query))
        self.assertTrue(reference_intent('Tôi không cần báo trước, tôi hỏi ngoại lệ nào áp dụng?'))

    def test_secondary_seed_and_reference_chains_are_not_followed(self):
        refs={'b':['f'],'a':['e'],'e':['d']}
        out=post_select_references(self.pool,refs,'Các ngoại lệ nào?',4,max_promotions=3)
        self.assertEqual([x.unit_id for x in out],list('aebcdf'))

    def test_never_adds_missing_unfiltered_candidate(self):
        out=post_select_references(self.pool,{'a':['outside-pool']},'Ngoại lệ?',4)
        self.assertEqual([x.unit_id for x in out],list('abcdef'))

    def test_zero_budget_and_zero_k_keep_full_order(self):
        for k,cap in ((0,None),(1,None),(4,0)):
            out=post_select_references(self.pool,{'a':['f']},'ngoại lệ',k,cap)
            self.assertEqual([x.unit_id for x in out],list('abcdef'))

    def test_budget_cannot_exceed_head_even_with_huge_explicit_cap(self):
        out=post_select_references(self.pool,{'a':list('fedcb')},'ngoại lệ',2,99)
        self.assertEqual([x.unit_id for x in out],list('abcdef'))

    def test_rejects_bad_limits_even_for_empty_input(self):
        for bad in (-1,True,2.1,float('nan')):
            with self.assertRaises(ValueError): post_select_references([],{},'',bad)
            with self.assertRaises(ValueError): post_select_references([],{},'',3,bad)

    def test_first_metadata_wins_duplicate_ids_and_inputs_are_immutable(self):
        first=evidence('x',rank=9,graph_path=['proof'],verified=False,score=.3)
        duplicate=evidence('x',rank=2).model_copy(update={'text':'untrusted second duplicate'})
        original=first.model_dump()
        out=post_select_references([first,duplicate,*self.pool],{'x':['f']},'ngoại lệ',4)
        self.assertEqual(out[0].model_dump(exclude={'rank'}),first.model_dump(exclude={'rank'}))
        self.assertEqual(first.model_dump(),original)
        self.assertFalse(out[0].verified)
        self.assertEqual(len({x.unit_id for x in out}),len(out))

    def test_graph_index_uses_only_outgoing_references(self):
        edges=[{'source':'a','target':'e','type':'REFERENCES'},
               {'source':'b','target':'a','type':'REFERENCES'},
               {'source':'a','target':'f','type':'SIMILAR_TO'},
               {'source':'a','target':'d','type':'PART_OF'}]
        graph=GraphExplorer(SimpleNamespace(edges=edges),GraphConfig())
        self.assertEqual(graph.references_by_source['a'],{'e'})
        out=post_select_references(self.pool,graph.references_by_source,'ngoại lệ',4)
        self.assertEqual([x.unit_id for x in out],list('aebcdf'))

    def test_bounded_graph_traversal_preserves_ranked_seed_order(self):
        graph=GraphExplorer(SimpleNamespace(edges=[]),GraphConfig(max_nodes=30,max_hops=1))
        graph.expand_round=Mock(return_value=([],[],{'edges_visited':0,'critical_edges_followed':[],'stop_reason':None}))
        seeds=[evidence('seed-'+str(n)) for n in reversed(range(20))]
        graph.expand(seeds,[],'unseen question')
        self.assertEqual(graph.expand_round.call_args.args[0],[item.unit_id for item in seeds])
