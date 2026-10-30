import json,unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from vn_labor_online.models import *
from vn_labor_online.config import AdjudicationConfig,GraphConfig,OnlineConfig
from vn_labor_online.analysis import analyze,intake
from vn_labor_online.context_budget import fits_context
from vn_labor_online.evidence_budget import prioritize_candidates
from vn_labor_online.freshness import qualify_freshness
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.query_support import unique_retrieval_queries
from vn_labor_online.retrieval import Retriever
from vn_labor_online.providers import OllamaProvider
from vn_labor_online.graph import GraphExplorer


class PeerMechanismTests(unittest.TestCase):
    def test_unknown_multiple_event_dates_are_clarified_not_first_date_guessed(self):
        a=analyze(intake('Tôi bị sa thải ngày 01/10/2026; đồng nghiệp bị sa thải ngày 01/08/2020. Hai việc đó có đúng luật không?',[]))
        self.assertEqual(a.temporal_resolution,'AMBIGUOUS')
        self.assertIsNone(a.query_date);self.assertTrue(a.missing_facts)

    def test_explicit_api_date_has_priority_but_role_dates_remain_visible(self):
        a=analyze(intake('Tôi ký hợp đồng ngày 01/01/2020, công ty sa thải ngày 01/10/2026.',[]),'2026-09-15')
        self.assertEqual(a.query_date,'2026-09-15');self.assertEqual(len(a.temporal_events),2)

    def test_signature_date_is_background_to_newly_proposed_resignation(self):
        a=analyze(intake('Tôi ký hợp đồng ngày 01/01/2020, hiện nay muốn nghỉ việc, báo trước bao lâu?',[]))
        self.assertIsNone(a.query_date)
        self.assertEqual(a.temporal_resolution,'UNSPECIFIED')

    def test_article_criminal_context_does_not_exclude_labour_disciplinary_question(self):
        a=analyze(intake('Người lao động trộm cắp tại nơi làm việc, công ty có được xử lý kỷ luật sa thải theo Bộ luật Lao động không?',[]))
        self.assertTrue(a.in_scope)

    def test_query_dedup_keeps_negated_and_temporally_distinct_queries(self):
        self.assertEqual(unique_retrieval_queries([' Lương  thử việc ','lương thử việc','không trả lương','trả lương','trả lương năm 2020']),
            ['Lương thử việc','không trả lương','trả lương','trả lương năm 2020'])

    def test_unmatched_tokenizer_cannot_relax_prompt_guard(self):
        with self.assertRaises(ValueError):OllamaProvider(model='qwen3:8b',tokenizer_path='local',tokenizer_model='wrong-model')

    def test_model_counter_and_conservative_fallback_use_same_output_reserve(self):
        p=NS(context_tokens=1000,max_output_tokens=300,count_prompt_tokens=lambda system,user:100)
        self.assertTrue(fits_context(p,'x'*800,'y'*800))
        self.assertFalse(fits_context(NS(context_tokens=1000,max_output_tokens=300),'x'*800,'y'*800))
        self.assertFalse(fits_context(NS(context_tokens=500,max_output_tokens=300,count_prompt_tokens=lambda s,u:100),'x','y'))

    def test_after_snapshot_is_qualified_in_public_text_and_status(self):
        response=AnswerResponse(query_id='q',status=Stop.SUFFICIENT,answer='Kết luận.',query_date='2026-10-30',evidence_status='VERIFIED',build_id='b',trace_id='t',trace=Trace(trace_id='t',query_id='q',build_id='b',route=Route.STANDARD,route_reason='fixture'),
            citations=[Citation(evidence_id='a')])
        result=qualify_freshness(response,NS(units_by_id={'a':{'document_id':'doc'}}),'2026-09-15')
        self.assertEqual(result.status,Stop.PARTIAL_ALLOWED)
        self.assertIn('2026-09-15',result.answer);self.assertIn('FRESHNESS_UNVERIFIED',result.limitations)

    def test_reviewed_interval_can_cover_later_query_without_faking_snapshot(self):
        response=AnswerResponse(query_id='q',status=Stop.SUFFICIENT,answer='Kết luận.',query_date='2026-10-20',evidence_status='VERIFIED',build_id='b',trace_id='t',trace=Trace(trace_id='t',query_id='q',build_id='b',route=Route.STANDARD,route_reason='fixture'),citations=[Citation(evidence_id='a')])
        store=NS(units_by_id={'a':{'provision_temporal_verified':True,'temporal_coverage_as_of':'2026-10-30'}})
        self.assertEqual(qualify_freshness(response,store,'2026-09-15').answer,'Kết luận.')

    def test_invalid_or_unverified_coverage_cannot_certify_freshness(self):
        for reviewed,until in [(True,'2099-99-99'),('false','2099-01-01'),(False,'2099-01-01')]:
            response=NS(citations=[Citation(evidence_id='a')],query_date='2026-10-30',applicable_date=None,
                trace=None,answer='Kết luận.',warnings=[],limitations=[],legal_status='REVIEWED',status=Stop.SUFFICIENT)
            store=NS(units_by_id={'a':{'provision_temporal_verified':reviewed,'temporal_coverage_as_of':until}})
            self.assertEqual(qualify_freshness(response,store,'2026-09-15').status,Stop.PARTIAL_ALLOWED)

    def test_auditor_priority_reserves_a_different_required_group_before_duplicate(self):
        items=[Evidence(unit_id=str(i),kind='PROVISION',retrieval_method='bm25',document_number='45/2019/QH14',text='Nội dung',article_number=a) for i,a in enumerate(['35','35','40'])]
        plan=EvidencePlan(mandatory_slots=['rule','liability'],slot_requirements={
            'rule':[[LegalLocator(documents=['45/2019/QH14'],article='35')]],
            'liability':[[LegalLocator(documents=['45/2019/QH14'],article='40')]]})
        self.assertEqual([e.unit_id for e in prioritize_candidates(items,plan)][:2],['0','2'])
        self.assertFalse(any(e.verified for e in items))

    def test_adjudicator_uses_confirmed_tasks_and_plan_without_reanalysis(self):
        task=AnswerTask(task_id='new_task',request_quote='Giải thích nghĩa vụ',description='Nghĩa vụ khác đã xác nhận',retrieval_query='Nghĩa vụ khác')
        pack=VerifiedEvidencePack(query='Giải thích nghĩa vụ.',coverage_state=EvidenceState(slots={},gaps=[],coverage=1),
            evidence=[VerifiedEvidenceItem(evidence_id='e',text='Người lao động được trả đủ tiền lương.',article='99',clause='1')],answer_tasks=[task],
            evidence_plan=EvidencePlan(mandatory_slots=['governing_rule']))
        engine=LegalAdjudicator(AdjudicationConfig(mode='deterministic'))
        engine.provider=Mock();engine.provider.structured.return_value={'claims':[{'text':'Người lao động được trả đủ tiền lương.','evidence_ids':['e']}]}
        with patch('vn_labor_online.analysis.analyze',side_effect=AssertionError('Must not reconstruct confirmed plan')):
            engine._generate(pack,False)
        payload=json.loads(engine.provider.structured.call_args.args[1])
        self.assertEqual([v['task_id'] for v in payload['answer_tasks']],['new_task'])

    def test_all_task_batches_reach_generator(self):
        tasks=[AnswerTask(task_id=f't{i}',request_quote='Giải thích nghĩa vụ',description='Nghĩa vụ',retrieval_query='Nghĩa vụ') for i in range(17)]
        pack=VerifiedEvidencePack(query='Giải thích nghĩa vụ.',coverage_state=EvidenceState(slots={},gaps=[],coverage=1),
            evidence=[VerifiedEvidenceItem(evidence_id='e',text='Người lao động được trả đủ tiền lương.')],answer_tasks=tasks,
            evidence_plan=EvidencePlan(mandatory_slots=['governing_rule']))
        engine=LegalAdjudicator(AdjudicationConfig(mode='deterministic'));engine.provider=Mock()
        engine.provider.structured.return_value={'claims':[{'text':'Người lao động được trả đủ tiền lương.','evidence_ids':['e']}]}
        engine._generate(pack,False)
        sent=[t['task_id'] for call in engine.provider.structured.call_args_list for t in json.loads(call.args[1])['answer_tasks']]
        self.assertEqual(sent,[t.task_id for t in tasks]);self.assertEqual(engine.provider.structured.call_count,3)

    def test_batched_dense_keeps_each_query_and_matches_single_search(self):
        import numpy as np,faiss
        units=[{'unit_id':str(i),'text':text,'kind':'PROVISION'} for i,text in enumerate(['hợp đồng','tiền lương'])]
        store=NS(units=units,units_by_id={u['unit_id']:u for u in units},nodes=[],edges=[])
        retriever=Retriever(store,OnlineConfig(artifact_source='fixture'))
        vectors=np.eye(2,dtype='float32');index=faiss.IndexFlatIP(2);index.add(vectors);retriever._faiss=index
        def encode(queries,**kw):return {'dense_vecs':np.array([[1,0] if q=='hợp đồng' else [0,1] for q in queries],dtype='float32')}
        retriever._model=NS(encode=Mock(side_effect=encode))
        batched=retriever.dense_batch(['hợp đồng','tiền lương'],1)
        self.assertEqual(retriever._model.encode.call_count,1)
        singles=[retriever.dense(q,1) for q in ['hợp đồng','tiền lương']]
        self.assertEqual([[e.unit_id for e in row] for row in batched],[[e.unit_id for e in row] for row in singles])

    def test_graph_node_features_reused_but_query_is_not_stale(self):
        import vn_labor_online.graph as module
        units=[{'unit_id':name,'text':text,'kind':'PROVISION'} for name,text in [('a','lao động'),('b','tiền lương')]]
        edges=[{'id':str(i),'source':'a','target':'b','type':'REFERENCES'} for i in range(3)]
        store=NS(units_by_id={u['unit_id']:u for u in units},nodes_by_id={},edges=edges)
        explorer=GraphExplorer(store,GraphConfig())
        with patch.object(module,'_terms',wraps=module._terms) as tokenize:
            explorer.expand_round(['a'],['mandatory_reference'],'tiền lương',{'a'},{},4,10)
            self.assertEqual(tokenize.call_count,3)
        first=explorer._score(edges[0],'b',['mandatory_reference'],'tiền lương','a','OUT')[1]['relevance']
        second=explorer._score(edges[0],'b',['mandatory_reference'],'tai nạn','a','OUT')[1]['relevance']
        self.assertGreater(first,second)

    def test_native_faiss_loader_matches_serialized_loader(self):
        import tempfile
        from pathlib import Path
        import numpy as np,faiss
        from vn_labor_online.artifact_store import ArtifactStore
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'faiss.index';vectors=np.eye(2,dtype='float32')
            index=faiss.IndexFlatIP(2);index.add(vectors);faiss.write_index(index,str(path))
            store=ArtifactStore.__new__(ArtifactStore);store.units=[{},{}];store.path=lambda _:path
            baseline=faiss.deserialize_index(faiss.serialize_index(index))
            with patch.object(Path,'read_bytes',side_effect=AssertionError('Native loader should not copy the index to bytes')):
                loaded=store.load_faiss()
            self.assertEqual(loaded.search(vectors,2)[1].tolist(),baseline.search(vectors,2)[1].tolist())

    def test_large_task_coverage_is_batched_without_omitting_or_duplicate_ids(self):
        from tests.online.test_semantic_answer_review import sample
        from tests.online.test_review_claim_batches import BatchProvider
        from vn_labor_online.answer_review import audit_in_batches,validate_review
        pack,draft,_=sample()
        tasks=[pack.answer_tasks[0].model_copy(update={'task_id':f't{i}'}) for i in range(19)]
        pack=pack.model_copy(update={'answer_tasks':tasks})
        payload={'question':pack.query,'tasks':[t.model_dump() for t in tasks],
            'claims':[c.model_dump() for c in draft.claims]}
        provider=BatchProvider();review=audit_in_batches(provider,payload,draft,pack,tasks)
        self.assertEqual([v.task_id for v in review.coverage],[t.task_id for t in tasks])
        self.assertEqual(len(validate_review(review,draft,pack,tasks)),1)
        coverage_calls=[call for call in provider.calls if 'checked_claims' in call]
        self.assertEqual([len(c['tasks']) for c in coverage_calls],[8,8,3])

    def test_strict_mode_does_not_return_partial_verdict_for_unverified_freshness(self):
        response=NS(citations=[Citation(evidence_id='a')],query_date='2026-10-30',applicable_date=None,
            trace=None,answer='Kết luận đã xác minh.',warnings=[],limitations=[],legal_status='REVIEWED',
            status=Stop.SUFFICIENT,claims=[Claim(claim_id='c',text='Kết luận.',evidence_ids=['a'])],
            applicable_law_versions=[],parts=[])
        result=qualify_freshness(response,NS(units_by_id={'a':{}}),'2026-09-15',allow_partial=False)
        self.assertEqual(result.status,Stop.INSUFFICIENT_EVIDENCE);self.assertEqual(result.claims,[])

    def test_more_than_twelve_deterministic_tasks_are_preserved_separately(self):
        from vn_labor_online.tasks import deterministic_tasks
        from vn_labor_online.taxonomy import SUBISSUES
        keys=list(SUBISSUES)[:15]
        tasks=deterministic_tasks('Hãy giải thích từng vấn đề lao động.',keys,[],SUBISSUES,Route.COMPLEX)
        self.assertEqual(len(tasks),15)

    def test_independent_extra_task_support_is_not_dropped_by_known_profile(self):
        from vn_labor_online.evidence import select_for_plan
        items=[Evidence(unit_id='main',kind='PROVISION',retrieval_method='bm25',document_number='45/2019/QH14',article_number='35',text='Quyền chấm dứt hợp đồng.',verified=True),
            Evidence(unit_id='extra',kind='PROVISION',retrieval_method='bm25',document_number='45/2019/QH14',article_number='98',text='Tiền lương làm thêm giờ.',verified=True)]
        plan=EvidencePlan(mandatory_slots=['rule'],slot_requirements={'rule':[[LegalLocator(documents=['45/2019/QH14'],article='35')]]},task_queries={'extra_task':'Tiền lương làm thêm giờ'})
        selected,_=select_for_plan(items,plan,None,True,2)
        self.assertEqual({v.unit_id for v in selected},{'main','extra'})


if __name__=='__main__':unittest.main()
