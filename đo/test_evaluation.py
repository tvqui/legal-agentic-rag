"""Deterministic contract/metric/reproducibility tests; never call real LLMs."""
import argparse
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import eval_core as e
import adapters as a


def fixture_bundle(path):
    corpus = [{'unit_id': 'u1', 'text': 'Source A', 'display_text': 'Source A', 'article_number': '7',
               'clause_number': '1', 'point_number': '', 'document_number': 'EXAMPLE',
               'source_url': 'https://example.org/law', 'valid_from': '2021-01-01', 'valid_to': '2026-01-01',
               'provision_temporal_verified': False}]
    question = {'id': 'q1', 'question': 'Fixture question', 'query_date': '2025-01-01',
                'required_groups': [['u1']], 'expected_status': 'ANSWERABLE', 'review_status': 'DRAFT',
                'reference_answer': 'NEVER SEND THIS REFERENCE TO INFERENCE'}
    path.mkdir(parents=True)
    e.write_rows(path / 'corpus.jsonl', corpus)
    e.write_rows(path / 'questions.jsonl', [question])
    e.dump(path / 'manifest.json', {'protocol': e.VERSION, 'corpus_jsonl_sha256': e.sha(path / 'corpus.jsonl'),
        'questions_sha256': e.sha(path / 'questions.jsonl'), 'label_status': 'DRAFT',
        'evaluation_scope': 'DEVELOPMENT_NOT_HELD_OUT', 'embedding_identity': {'model': 'fixture', 'revision': '0'}})
    return question, {u['unit_id']: u for u in corpus}


class MetricTests(unittest.TestCase):
    def test_binary_ir_hand_calculation(self):
        scores = e.retrieval_metrics(['bad', 'a', 'b'], [['a'], ['b']], 3)
        self.assertEqual(scores['precision_at_k'], 2 / 3)
        self.assertEqual(scores['recall_at_k'], 1)
        self.assertEqual(scores['mrr_at_k'], .5)
        self.assertAlmostEqual(scores['ndcg_at_k'], (1 / math.log2(3) + .5) / (1 + 1 / math.log2(3)))

    def test_interchangeable_sources_do_not_duplicate_group_gain(self):
        s = e.retrieval_metrics(['a', 'a2'], [['a', 'a2'], ['b']], 2)
        self.assertEqual(s['group_recall_at_k'], .5)
        self.assertLess(s['group_ndcg_at_k'], 1)
        self.assertEqual(s['recall_at_k'], 2 / 3)

    def test_short_result_does_not_shrink_precision_denominator(self):
        self.assertEqual(e.retrieval_metrics(['a'], [['a']], 10)['precision_at_k'], .1)

    def test_duplicate_ranks_rejected(self):
        with self.assertRaises(ValueError): e.retrieval_metrics(['a', 'a'], [['a']], 2)

    def test_bootstrap_sampling_unit_is_query_not_repeat(self):
        values = [{'id': 'a', 'metrics': {'m': 1}}] * 10 + [{'id': 'b', 'metrics': {'m': 0}}]
        self.assertEqual(e.mean(e.macro(values, 'm').values()), .5)
        self.assertEqual(e.ci([1])['low'], None)

    def test_source_metadata_temporal_boundary_and_no_claim_of_human_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            q, corpus = fixture_bundle(Path(tmp) / 'bundle')
            result = {'answer_status': 'PARTIAL_ALLOWED', 'claims': [{'text': 'example'}], 'citations': [
                {'evidence_id': 'u1', 'article': '7', 'clause': '1', 'point': '', 'document_number': 'EXAMPLE',
                 'official_url': 'https://example.org/law'}]}
            scores = e.qa_metrics(result, q, corpus)
            self.assertEqual(scores['citation_locator_metadata_match'], 1)
            self.assertEqual(scores['citation_temporal_review_fraction'], 0)
            self.assertEqual(scores['disposition_match'], 1)
            q['query_date'] = '2026-01-01'
            self.assertEqual(e.qa_metrics(result, q, corpus)['citation_interval_match'], 0)
            result['citations'][0]['clause'] = '2'
            self.assertEqual(e.qa_metrics(result, q, corpus)['citation_locator_metadata_match'], 0)

    def test_no_citations_is_na_not_perfect_precision(self):
        q = {'query_date': '2025-01-01', 'expected_status': 'NEED_MORE_FACTS'}
        s = e.qa_metrics({'answer_status': 'NEED_MORE_FACTS'}, q, {})
        self.assertIsNone(s['citation_id_validity'])
        self.assertEqual(s['clarification_match'], 1)

    def test_sufficient_native_status_is_an_answer_not_a_false_failure(self):
        scores = e.qa_metrics({'answer_status': 'SUFFICIENT', 'claims': [{'text': 'x'}]},
                              {'query_date': '2025-01-01', 'expected_status': 'ANSWERABLE'}, {})
        self.assertEqual(scores['disposition_match'], 1)

    def test_malformed_url_is_bad_citation_not_crashing_evaluator(self):
        q = {'query_date': '2025-01-01'}
        corpus = {'a': {'source_url': 'https://[invalid', 'valid_from': None}}
        s = e.qa_metrics({'citations': [{'evidence_id': 'a', 'official_url': 'https://[invalid'}]}, q, corpus)
        self.assertEqual(s['citation_url_metadata_match'], 0)
        self.assertIsNone(s['citation_interval_match'])

    def test_true_errors_are_counted_not_scored_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); run = p / 'run'; run.mkdir()
            e.dump(run / 'run_manifest.json', {'comparison_key': 'x', 'methods': ['full'], 'task': 'qa',
                'bundle': {'label_status': 'DRAFT', 'evaluation_scope': 'DEVELOPMENT_NOT_HELD_OUT'},
                'scheduled_queries': 2, 'repeats': 1})
            e.write_rows(run / 'responses.jsonl', [
                {'id': 'q1', 'method': 'full', 'status': 'OK', 'elapsed_ms': 10,
                 'metrics': {'ai_correctness': .5}, 'judge': {'status': 'AI_JUDGED'}},
                {'id': 'q2', 'method': 'full', 'status': 'ERROR', 'elapsed_ms': 1000, 'metrics': {}}])
            with patch('eval_core.plot_table'):
                result = e.report_runs([run], p / 'report')[0]
            self.assertEqual(result['errors'], 1)
            self.assertEqual(result['mean_ms_success'], 10)
            self.assertEqual(result['metric_scored_queries']['ai_correctness'], 1)
            self.assertEqual(result['status'], 'INCOMPLETE_OR_NA')


class ContractTests(unittest.TestCase):
    def test_reranker_is_pinned_without_resolving_main_after_cache_loss(self):
        from vn_labor_online.config import OnlineConfig
        cfg = OnlineConfig(artifact_source='fixture')
        revision = 'a' * 40
        settings = {'cache': 'fixture', 'reranker_revision': revision}
        with patch('labor_retrieval.pin_models', return_value={}) as base, \
             patch('huggingface_hub.snapshot_download', return_value='fixture-model') as download:
            result = a.pin_runtime_models(cfg, Mock(), ['hybrid_rerank'], settings)
        self.assertEqual(base.call_args.args[2], ['hybrid'])
        self.assertEqual(download.call_args.kwargs['revision'], revision)
        self.assertEqual(result['reranker']['revision'], revision)
        with self.assertRaises(ValueError): a.pin_runtime_models(cfg, Mock(), ['hybrid_rerank'], {'cache': 'fixture'})

    def test_project_adapter_prepares_without_changing_variant_or_losing_settings(self):
        from vn_labor_online.config import OnlineConfig
        cfg = OnlineConfig(artifact_source='fixture')
        cfg.adjudication.mode = 'ollama'; cfg.adjudication.model = 'fixture'
        cfg.reranker.enabled = False
        settings = {'cache': 'fixture', 'reranker_revision': 'a' * 40}
        pipe = Mock()
        pipe.retriever.bm25.return_value = []
        with patch('adapters.config_for_bundle', return_value=cfg), \
             patch('vn_labor_online.pipeline.OnlinePipeline', return_value=pipe), \
             patch('adapters.verify_store'), patch('adapters.pin_runtime_models', return_value={}) as pin:
            adapter = a.ProjectAdapter('full', settings, {}, Path('.'))
            prepared = adapter.prepare()
        self.assertEqual(pin.call_args.args[2], ['hybrid'])
        self.assertEqual(pin.call_args.args[3]['reranker_revision'], 'a' * 40)
        self.assertFalse(prepared['effective_config']['reranker']['enabled'])
        self.assertTrue(cfg.retrieval.exact_lookup)  # Base remains unchanged.

    def test_provider_outage_is_not_scored_as_legal_abstention(self):
        result = {'claims': [], 'trace': {'events': [{'event': 'semantic_answer_audit',
            'status': 'ERROR', 'error_code': 'GEMINI_HTTP_503'}]}}
        self.assertEqual(e.infrastructure_failure(result), 'GEMINI_HTTP_503')
        result['claims'] = [{'text': 'Reviewed recovery answer'}]
        self.assertIsNone(e.infrastructure_failure(result))
        self.assertIsNone(e.infrastructure_failure({'claims': [], 'trace': {'events': []}}))

    def test_error_log_does_not_trust_arbitrary_reason(self):
        error = RuntimeError('private-key-in-message'); error.reason = 'PRIVATE_KEY_IN_REASON'
        self.assertNotIn('PRIVATE', json.dumps(e.safe_error(error)))
        self.assertNotIn('private-key', json.dumps(e.safe_error(error)))

    def test_inference_allowlist_no_label_leak(self):
        data = e.inference_input({'id': 'a', 'question': 'q', 'query_date': '2025-01-01',
            'required_groups': [['secret']], 'reference_answer': 'answer', 'expected_status': 'ANSWERABLE',
            'missing_facts': ['secret'], 'gold_tasks': [{'task_id': 'secret'}], 'facts': {'explicit': True}})
        self.assertEqual(set(data), {'id', 'question', 'query_date', 'facts'})

    def test_bundle_tamper_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bundle'; fixture_bundle(p)
            self.assertEqual(len(e.load_bundle(p)[1]), 1)
            with (p / 'corpus.jsonl').open('a', encoding='utf-8') as f: f.write('\n')
            with self.assertRaises(ValueError): e.load_bundle(p)

    def test_unknown_and_overlapping_qrels_rejected(self):
        q = {'id': 'x', 'question': 'Fixture question', 'query_date': '2025-01-01', 'required_groups': [['a'], ['a']]}
        with self.assertRaises(ValueError): e.validate_questions([q], {'a': {}})
        q['required_groups'] = [['unknown']]
        with self.assertRaises(ValueError): e.validate_questions([q], {'a': {}})

    def test_ablation_does_not_mutate_base_or_fabricate_audit(self):
        from vn_labor_online.config import OnlineConfig
        cfg = OnlineConfig(artifact_source='fixture')
        v = a.pipeline_variant(cfg, 'without_graph')
        self.assertFalse(v.graph.enabled)
        self.assertFalse(v.retrieval.case_law_enabled)
        self.assertFalse(v.retrieval.community_enabled)
        self.assertFalse(v.retrieval.issue_anchor_enabled)
        self.assertTrue(cfg.graph.enabled)
        self.assertTrue(cfg.retrieval.case_law_enabled)
        self.assertEqual(a.pipeline_variant(cfg, 'without_researcher').researcher.mode, 'deterministic')
        cfg.adjudication.mode = 'ollama'
        self.assertEqual(a.pipeline_variant(cfg, 'without_adjudicator').adjudication.mode, 'ollama')

    def test_unconfigured_baseline_is_explicit_na(self):
        with self.assertRaises(a.NotApplicable): a.ExternalAdapter('raptor', {}, {}, Path('.'))

    def test_unsafe_resume_changed_config_or_code_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); fixture_bundle(p / 'bundle')
            e.dump(p / 'settings.json', {'cache': str(p / 'cache'), 'device': 'cpu', 'candidate_k': 30,
                                        'embedding_identity': 'FROM_BUNDLE'})
            args = argparse.Namespace(bundle=str(p / 'bundle'), config=str(p / 'settings.json'),
                out=str(p / 'run'), task='retrieval', allow_draft=True, allow_llm=False,
                methods=['bm25'], repeats=1, k=10, limit=None, seed=42, resume=False, retry_errors=False, judge=False)
            adapter = Mock()
            adapter.prepare.return_value = {'fixture': True}
            adapter.run.return_value = {'retrieved_ids': ['u1'], 'llm_calls': 0}
            with patch('adapters.resolved_settings', return_value={}), patch('adapters.create', return_value=adapter), \
                 patch('eval_core.environment', return_value={'platform': 'fixture', 'machine': '', 'processor': '', 'cpu_count': 1,
                    'gpu': None, 'hardware_id': None, 'packages': {}}), patch('eval_core.plot_table'):
                self.assertEqual(e.execute(args), 0)
                self.assertEqual(adapter.run.call_count, 1)
                self.assertNotIn('reference_answer', adapter.run.call_args.args[0])
                args.resume = True
                self.assertEqual(e.execute(args), 0)
                self.assertEqual(adapter.run.call_count, 1)  # no cherry-picking successful answers
                args.seed = 43
                with self.assertRaises(ValueError): e.execute(args)

    def test_compare_keeps_different_protocol_groups_apart(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for name in ('a', 'b'):
                d = p / name; d.mkdir()
                e.dump(d / 'run_manifest.json', {'comparison_key': name, 'methods': [name], 'task': 'retrieval',
                    'bundle': {'label_status': 'DRAFT', 'evaluation_scope': 'DEVELOPMENT_NOT_HELD_OUT'},
                    'scheduled_queries': 1, 'repeats': 1})
                e.write_rows(d / 'responses.jsonl', [{'id': 'q', 'method': name, 'repeat': 1, 'status': 'OK',
                    'elapsed_ms': 1, 'metrics': {'recall_at_k': 1}}])
            with patch('eval_core.plot_table'):
                e.report_runs([p / 'a', p / 'b'], p / 'report')
            self.assertEqual(e.read(p / 'report/paired_deltas.json'), [])

    def test_common_reader_receives_only_retrieved_sources_not_gold(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, corpus = fixture_bundle(Path(tmp) / 'bundle')
            retriever = Mock()
            retriever.run.return_value = {'retrieved_ids': ['u1'], 'llm_calls': 0}
            provider = Mock()
            provider.structured.return_value = {'answer': 'Source A', 'answer_status': 'ANSWERABLE',
                'claims': [{'text': 'Source A', 'evidence_ids': ['u1']}], 'questions': []}
            with patch('adapters.reader', return_value=provider):
                adapter = a.CommonReader(retriever, {'reader_k': 10, 'context_char_limit': 100}, corpus)
            result = adapter.run(e.inference_input(question))
            self.assertEqual(result['llm_calls'], 1)
            payload = provider.structured.call_args.args[1]
            self.assertNotIn('NEVER SEND', payload)
            self.assertEqual(result['citations'][0]['article'], '7')
            provider.structured.return_value['claims'][0]['evidence_ids'] = ['fabricated']
            with self.assertRaises(ValueError): adapter.run(e.inference_input(question))

    def test_reader_budget_does_not_truncate_a_source_condition(self):
        retriever = Mock(); retriever.run.return_value = {'retrieved_ids': ['large'], 'llm_calls': 0}
        corpus = {'large': {'display_text': 'x' * 101}}
        provider = Mock(); provider.structured.return_value = {'answer': 'Not enough',
            'answer_status': 'INSUFFICIENT_EVIDENCE', 'claims': [], 'questions': []}
        with patch('adapters.reader', return_value=provider):
            adapter = a.CommonReader(retriever, {'context_char_limit': 100}, corpus)
        result = adapter.run({'question': 'Fixture question', 'query_date': '2025-01-01'})
        payload = json.loads(provider.structured.call_args.args[1])
        self.assertEqual(payload['evidence'], [])
        self.assertEqual(result['reader_context_chars'], 0)

    def test_native_source_identity_is_checked_before_loading_upstream(self):
        import native_worker
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); fixture_bundle(p / 'bundle')
            cfg = {'corpus': str(p / 'bundle/corpus.jsonl'), 'corpus_sha256': 'WRONG',
                   'work_dir': str(p / 'native'), 'method': 'lightrag'}
            with self.assertRaises(ValueError): native_worker.Native(cfg)
            cfg['corpus_sha256'] = e.sha(cfg['corpus'])
            native = native_worker.Native(cfg)
            self.assertIn('[SOURCE_ID=u1]', native.tagged[0])
            cfg['llm_model'] = 'changed-model'
            with self.assertRaises(ValueError): native_worker.Native(cfg)

    def test_judge_does_not_accept_false_task_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); fixture_bundle(p / 'bundle'); run = p / 'run'; run.mkdir()
            settings = {'bundle_corpus': str(p / 'bundle/corpus.jsonl'),
                'judge': {'provider': 'ollama', 'model': 'fixture', 'temperature': 0,
                          'max_output_tokens': 256, 'context_tokens': 4096}}
            e.dump(run / 'run_manifest.json', {'task': 'qa', 'source_tree': e.source_tree(), 'settings': settings})
            e.write_rows(run / 'responses.jsonl', [{'id': 'q1', 'method': 'full', 'status': 'OK',
                'metrics': {}, 'result': {'answer': 'A', 'questions': ['Which material fact?'], 'claims': [], 'citations': []}}])
            provider = Mock(); provider.structured.return_value = {'correctness': 1, 'completeness': 1,
                'evidence_support': 1, 'relevance': 1, 'temporal_application': 1,
                'reason': 'fixture', 'task_scores': [{'task_id': 'MADE_UP', 'score': 1}]}
            with patch('adapters.reader', return_value=provider), patch('eval_core.report_runs'):
                e.judge_run(run)
            result = e.rows(run / 'responses.jsonl')[0]
            self.assertEqual(result['judge']['status'], 'ERROR')
            self.assertNotIn('ai_correctness', result['metrics'])
            payload = json.loads(provider.structured.call_args.args[1])
            self.assertEqual(payload['clarification_questions'], ['Which material fact?'])

    def test_removing_drafter_keeps_independent_reviewer(self):
        from types import SimpleNamespace
        from vn_labor_online.models import AdjudicationDraft, Claim
        original = SimpleNamespace(provider=Mock(), review_provider=Mock(),
            cfg=SimpleNamespace(semantic_review=True, semantic_repair_attempts=1))
        adapter = a.ExtractiveAdjudicator(original)
        draft = AdjudicationDraft(answer_summary='Fixture', applicable_law_versions=[],
            claims=[Claim(claim_id='a', text='Source excerpt', evidence_ids=['u1'])])
        adapter.extractor = Mock(); adapter.extractor.generate.return_value = (draft, [])
        reviewed = draft.model_copy(update={'semantic_review': {'status': 'PASS'}})
        with patch('vn_labor_online.answer_review.review_answer', return_value=(reviewed, [])) as review:
            result, _ = adapter.generate(SimpleNamespace(), False)
        self.assertEqual(result.semantic_review['status'], 'PASS')
        self.assertIs(review.call_args.args[0], original.review_provider)
        original.provider.structured.assert_not_called()

    def test_quota_pause_and_retry_preserve_attempt_history(self):
        from vn_labor_online.errors import ProviderRateLimited
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); fixture_bundle(p / 'bundle')
            e.dump(p / 'settings.json', {'cache': str(p / 'cache'), 'device': 'cpu', 'candidate_k': 30,
                                        'embedding_identity': 'FROM_BUNDLE'})
            args = argparse.Namespace(bundle=str(p / 'bundle'), config=str(p / 'settings.json'),
                out=str(p / 'run'), task='retrieval', allow_draft=True, allow_llm=False,
                methods=['bm25'], repeats=1, k=10, limit=None, seed=42, resume=False, retry_errors=False, judge=False)
            adapter = Mock(); adapter.prepare.return_value = {}
            adapter.run.side_effect = ProviderRateLimited(quota_kind='DAILY')
            with patch('adapters.resolved_settings', return_value={}), patch('adapters.create', return_value=adapter), \
                 patch('eval_core.ResourceSampler') as resource, patch('eval_core.environment', return_value={
                    'platform': 'fixture', 'machine': '', 'processor': '', 'cpu_count': 1,
                    'gpu': None, 'hardware_id': None, 'packages': {}}), patch('eval_core.plot_table'):
                resource.return_value.__enter__.return_value = resource.return_value
                resource.return_value.report.return_value = {}
                self.assertEqual(e.execute(args), 2)
                self.assertEqual(e.read(p / 'run/progress.json')['paused'], 'UPSTREAM_CAPACITY_OR_CONFIGURATION')
                args.resume = args.retry_errors = True
                adapter.run.side_effect = None; adapter.run.return_value = {'retrieved_ids': ['u1'], 'llm_calls': 0}
                self.assertEqual(e.execute(args), 0)
                self.assertEqual(len(e.rows(p / 'run/attempt_history.jsonl')), 1)
                self.assertEqual(e.rows(p / 'run/responses.jsonl')[0]['status'], 'OK')

    def test_embedding_bridge_identity_normalization_and_real_token_count_contract(self):
        from types import SimpleNamespace
        from fastapi.testclient import TestClient
        import evaluate_baselines
        encoder = Mock()
        encoder.encode.return_value = {'dense_vecs': [[3., 4.]]}
        encoder.tokenizer.return_value = {'input_ids': [[1, 2, 3]]}
        model = Mock(return_value=encoder)
        with patch('eval_core.load_bundle', return_value=({'embedding_identity': {'model': 'BAAI/bge-m3', 'revision': 'fixture'}}, [], {})), \
             patch.dict('sys.modules', {'FlagEmbedding': SimpleNamespace(BGEM3FlagModel=model)}), \
             patch('huggingface_hub.snapshot_download', return_value='fixture-model-path'), patch('uvicorn.run') as serve:
            self.assertEqual(evaluate_baselines.embedding_server(['--bundle', 'fixture', '--cache', 'fixture', '--device', 'cpu']), 0)
        self.assertEqual(serve.call_args.kwargs['host'], '127.0.0.1')
        with TestClient(serve.call_args.args[0]) as client:
            self.assertEqual(client.get('/identity').json()['revision'], 'fixture')
            invalid = client.post('/v1/embeddings', json={'model': 'wrong', 'input': ['text']})
            self.assertEqual(invalid.status_code, 400)
            response = client.post('/v1/embeddings', json={'model': 'BAAI/bge-m3', 'input': ['text']})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertAlmostEqual(data['data'][0]['embedding'][0], .6, places=6)
            self.assertEqual(data['usage']['prompt_tokens'], 3)
            self.assertEqual(encoder.encode.call_args.kwargs['max_length'], 1024)


if __name__ == '__main__':
    unittest.main()
