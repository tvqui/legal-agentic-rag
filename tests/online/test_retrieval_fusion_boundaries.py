import math
import threading
import unittest
from unittest.mock import Mock

from vn_labor_online.config import OnlineConfig, RerankerConfig
from vn_labor_online.errors import IndexUnavailable
from vn_labor_online.models import Evidence
from vn_labor_online.retrieval import Retriever


def item(uid, text='source', **kwargs):
    return Evidence(unit_id=uid, text=text, retrieval_method='fixture', **kwargs)


def retriever():
    r = object.__new__(Retriever)
    r.cfg = OnlineConfig(artifact_source='fixture', reranker=RerankerConfig(enabled=True, top_n=2))
    r._reranker = Mock(); r._lock = threading.Lock()
    return r


class RetrievalFusionBoundaryTests(unittest.TestCase):
    def test_zero_weight_channel_cannot_change_candidates_or_metadata(self):
        r = retriever()
        a = item('a', 'trusted')
        result = r.fusion([[a], [item('a', 'zero channel'), item('b')]], weights=[1, 0])
        self.assertEqual([x.unit_id for x in result], ['a'])
        self.assertEqual(result[0].text, 'trusted')
        self.assertEqual(r.fusion([[a]], weights=[0]), [])

    def test_explicit_empty_and_invalid_weights_are_rejected(self):
        r = retriever()
        for w in ([], [-1], [float('nan')], [float('inf')], [True]):
            with self.subTest(weights=w), self.assertRaises(ValueError):
                r.fusion([[item('a')]], weights=w)

    def test_duplicate_inside_one_channel_cannot_create_extra_votes(self):
        r = retriever()
        result = r.fusion([[item('a'), item('a'), item('b')]])
        self.assertAlmostEqual(result[0].score, 1 / 61)
        self.assertAlmostEqual(result[1].score, 1 / 62)

    def test_channel_weights_are_applied_once(self):
        r = retriever()
        result = r.fusion([[item('a')], [item('b'), item('a')]], weights=[1, .5])
        self.assertEqual(result[0].unit_id, 'a')
        self.assertAlmostEqual(result[0].score, 1 / 61 + .5 / 62)

    def test_fusion_keeps_source_and_graph_provenance(self):
        r=retriever()
        result=r.fusion([[item('a','original')],[item('a','original',graph_path=['edge'],
            graph_relations=['REFERENCES'],graph_directions=['OUT'])]],weights=[1,.5])
        self.assertEqual(result[0].graph_path,['edge'])
        self.assertEqual(result[0].text,'original')

    def test_reranker_preserves_parent_context_and_new_ranks(self):
        r = retriever(); r._reranker.compute_score.return_value = [.1, .9]
        parent = 'Các hành vi sau đây bị nghiêm cấm:'
        values = [item('a', 'a) Giữ giấy tờ.', ancestor_context=parent, rank=1), item('b', rank=2), item('c', rank=3)]
        result = r.neural_rerank(values, 'query')
        self.assertIn(parent, r._reranker.compute_score.call_args.args[0][0][1])
        self.assertEqual([x.unit_id for x in result], ['b', 'a', 'c'])
        self.assertEqual([x.rank for x in result], [1, 2, 3])
        self.assertEqual(values[0].text, 'a) Giữ giấy tờ.')
        self.assertEqual(values[0].rank, 1)

    def test_reranker_refuses_invalid_normalized_scores(self):
        for scores in ([.5, float('nan')], [.5, float('inf')], [-1, .5], [1.1, .5]):
            r = retriever(); r._reranker.compute_score.return_value = scores
            with self.subTest(scores=scores), self.assertRaises(IndexUnavailable):
                r.neural_rerank([item('a'), item('b')], 'query')

    def test_zero_signal_tie_keeps_first_stage_order(self):
        r = retriever(); r._reranker.compute_score.return_value = [.5, .5]
        self.assertEqual([x.unit_id for x in r.neural_rerank([item('z'), item('a')], 'query')], ['z', 'a'])

    def test_full_prior_weight_preserves_first_stage_order(self):
        r = retriever(); r.cfg.reranker.first_stage_weight = 1
        r._reranker.compute_score.return_value = [.1, .9]
        self.assertEqual([x.unit_id for x in r.neural_rerank([item('z'), item('a')], 'query')], ['z', 'a'])


if __name__ == '__main__':
    unittest.main()
