from __future__ import annotations
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from vn_labor_online.analysis import analyze,intake,plan_evidence
from vn_labor_online.artifact_store import ArtifactStore
from vn_labor_online.config import OnlineConfig,RetrievalConfig
from vn_labor_online.evidence import state_for
from vn_labor_online.models import Claim,QueryRequest,Stop
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_online.retrieval import Retriever
from vn_labor_online.runtime import request_budget,measured_timings
from vn_labor_online.tasks import independent_partial_plan,assess_parts,merge_tasks
from vn_labor_online.taxonomy import profile_covers_issues
from vn_labor_online.topics import TOPICS,detect_topics
from tests.online.test_online_core import fixture,FakeModel
from tests.online.test_issue_taxonomy import evidence


class RequestCoverageTests(unittest.TestCase):
    def test_personal_leave_does_not_hide_separately_requested_resignation(self):
        personal=analyze(intake('Tôi muốn nghỉ việc riêng để kết hôn, có được hưởng lương không?',[]))
        self.assertNotIn('TERMINATION',personal.legal_issues)
        mixed=analyze(intake('Tôi nghỉ việc riêng để kết hôn. Sau đó tôi muốn nghỉ việc hẳn, phải báo trước bao lâu?',[]))
        self.assertIn('TERMINATION',mixed.legal_issues)

    def test_training_background_is_not_an_extra_termination_request(self):
        a=analyze(intake('Khi NLĐ đơn phương chấm dứt HĐLĐ trái pháp luật và có hợp đồng đào tạo, những điều luật nào điều chỉnh nghĩa vụ hoàn trả?',[]))
        self.assertEqual({key for task in a.answer_tasks for key in task.legal_subissues},{'TRAINING.COST_REPAYMENT'})
        self.assertFalse(any(task.topic_ids for task in a.answer_tasks))

    def test_routing_registry_does_not_claim_approved_profile_coverage(self):
        self.assertEqual(len(TOPICS),50)
        self.assertEqual(len({topic.key for topic in TOPICS}),50)
        query='Thủ tục đăng ký nội quy lao động được quy định thế nào?'
        analysis=analyze(intake(query,[]))
        self.assertIn('internal_rules',analysis.routing_topics)
        self.assertFalse(profile_covers_issues(analysis))
        self.assertTrue(analysis.answer_tasks)
        for topic in TOPICS:
            self.assertIn(topic.key,{t.key for t in detect_topics(topic.phrases[0])})

    def test_trial_pay_duration_and_end_are_separate_deterministic_requests(self):
        query='Tôi đang thử việc. Lương thử việc bao nhiêu, thử việc tối đa bao lâu và hết thử việc có lên chính thức không?'
        analysis=analyze(intake(query,[]))
        subissues={key for task in analysis.answer_tasks for key in task.legal_subissues}
        self.assertTrue({'CONTRACT.PROBATION_PAY','CONTRACT.PROBATION_DURATION','CONTRACT.PROBATION_END'}<=subissues)
        self.assertEqual(len({task.task_id for task in analysis.answer_tasks}),len(analysis.answer_tasks))

    def test_model_empty_decomposition_does_not_erase_baseline_requests(self):
        a=analyze(intake('Lương thử việc bao nhiêu và thời gian thử việc bao lâu?',[]))
        self.assertEqual(merge_tasks(a.answer_tasks,[]),a.answer_tasks)

    def test_independent_rule_can_survive_missing_other_rules(self):
        query='Tiền lương thử việc được bao nhiêu và thời gian thử việc tối đa bao lâu?'
        a=analyze(intake(query,[]),'2025-01-01')
        selected=[evidence('26',text='Tiền lương trong thời gian thử việc ít nhất phải bằng 85% mức lương của công việc đó.')]
        plan,ids=independent_partial_plan(a,selected,True)
        self.assertIsNotNone(plan)
        self.assertEqual(ids,[selected[0].unit_id])
        self.assertNotIn('probation_duration',plan.slot_requirements)
        parts=assess_parts(a,selected,[],{},True)
        pay=next(part for part in parts if 'lương' in part.description.lower())
        self.assertEqual(pay.evidence_status,'FOUND')
        self.assertEqual(pay.answer_status,'NOT_CHECKED')
        self.assertFalse(any(part.answer_status=='ANSWERED' for part in parts))

    def test_generic_keyword_hits_cannot_enable_partial_rule_fast_path(self):
        a=analyze(intake('Điều kiện hưởng trợ cấp thất nghiệp là gì?',[]),'2026-01-01')
        plan,ids=independent_partial_plan(a,[evidence('13',text='Hợp đồng lao động được thỏa thuận giữa các bên.')],True)
        self.assertIsNone(plan); self.assertEqual(ids,[])

    def test_combined_night_overtime_keeps_interaction_rules_per_task(self):
        from vn_labor_online.tasks import task_analysis
        a=analyze(intake('Một ca vừa là làm thêm giờ, vừa ban đêm, vừa rơi vào ngày lễ thì phải kết hợp các quy định nào?',[]),'2025-01-01')
        night=next(task for task in a.answer_tasks if 'WAGE.NIGHT_PAY' in task.legal_subissues)
        scoped=task_analysis(a,night)
        self.assertEqual(scoped.query_text,a.query_text)
        plan=plan_evidence(scoped)
        self.assertIn('night_overtime_pay',plan.slot_requirements)
        self.assertIn('night_overtime_formula',plan.slot_requirements)

    def test_part_answer_accounting_requires_public_checked_claims(self):
        a=analyze(intake('Lương thử việc bao nhiêu và thời gian thử việc bao lâu?',[]),'2025-01-01')
        selected=[evidence('26',text='Tiền lương thử việc ít nhất phải bằng 85% mức lương của công việc đó.')]
        pay=next(task for task in a.answer_tasks if 'CONTRACT.PROBATION_PAY' in task.legal_subissues)
        review={'iterations':[{'coverage':[{'task_id':pay.task_id,'status':'ANSWERED','claim_ids':['checked'],'missing':''}]}]}
        claims=[Claim(claim_id='checked',text=selected[0].text,evidence_ids=[selected[0].unit_id])]
        part=next(part for part in assess_parts(a,selected,claims,review,True) if part.task_id==pay.task_id)
        self.assertEqual(part.answer_status,'ANSWERED')
        self.assertEqual(part.legal_status,'PROVISIONAL')
        missing=next(part for part in assess_parts(a,selected,[],review,True) if part.task_id==pay.task_id)
        self.assertNotEqual(missing.answer_status,'ANSWERED')

    def test_pipeline_returns_independent_pay_rule_when_duration_is_missing(self):
        from vn_labor_online.config import GraphConfig
        from unittest.mock import Mock
        query='Tiền lương thử việc được bao nhiêu và thời gian thử việc tối đa bao lâu?'
        selected=evidence('26',text='Tiền lương của người lao động trong thời gian thử việc do hai bên thỏa thuận nhưng ít nhất phải bằng 85% mức lương của công việc đó.')
        selected=selected.model_copy(update={'source_url':'https://vbpl.vn/official','valid_from':'2021-01-01',
          'authority_rank':100,'binding':True,'provision_identity_id':'pid_pay','document_id':'doc_pay'})
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); build=fixture(root)
            cfg=OnlineConfig(artifact_source=str(root),expected_build_id=build,trace_dir=str(root/'traces'),
              max_verified_units=32,graph=GraphConfig(enabled=False),
              retrieval=RetrievalConfig(dense_enabled=False,issue_anchor_enabled=False,case_law_enabled=False,community_enabled=False))
            pipe=OnlinePipeline(cfg)
            pipe.retriever.policy_anchor=Mock(return_value=[selected])
            pipe.retriever.bm25=Mock(return_value=[selected])
            pipe.retriever.fusion=Mock(return_value=[selected])
            with patch('vn_labor_online.pipeline.deterministic_audit',side_effect=lambda store,items,*args:items):
                result=pipe.ask(QueryRequest(question=query,query_date='2025-01-01'))
            self.assertEqual(result.status,Stop.PARTIAL_ALLOWED,result.model_dump())
            self.assertTrue(result.claims)
            self.assertTrue(result.citations)
            self.assertIn('INDEPENDENT_TASK_RULES_ONLY',result.warnings)
            self.assertTrue(any(part.evidence_status=='MISSING' for part in result.parts))

    def test_liability_task_depends_on_classification_for_case_assessment(self):
        a=analyze(intake('Tôi ký hợp đồng lao động không xác định thời hạn và chỉ báo trước 20 ngày. '
          'Tôi không làm ngành, nghề, công việc đặc thù và không thuộc trường hợp được nghỉ không cần báo trước. '
          'Nghỉ như vậy có đúng quy định không và hậu quả pháp lý là gì?',[]))
        classification=next(task for task in a.answer_tasks if 'TERMINATION.ILLEGAL_TERMINATION' in task.legal_subissues)
        liability=next(task for task in a.answer_tasks if 'TERMINATION.EMPLOYEE_LIABILITY' in task.legal_subissues)
        self.assertIn(classification.task_id,liability.depends_on)

    def test_missing_prerequisite_prevents_complete_applied_conclusion(self):
        a=analyze(intake('Lương thử việc bao nhiêu và thời gian thử việc bao lâu?',[]),'2025-01-01')
        pay=next(task for task in a.answer_tasks if 'CONTRACT.PROBATION_PAY' in task.legal_subissues)
        duration=next(task for task in a.answer_tasks if 'CONTRACT.PROBATION_DURATION' in task.legal_subissues)
        pay.depends_on=[duration.task_id]
        selected=[evidence('26',text='Tiền lương thử việc ít nhất phải bằng 85% mức lương của công việc đó.')]
        claims=[Claim(claim_id='pay',text=selected[0].text,evidence_ids=[selected[0].unit_id])]
        review={'iterations':[{'coverage':[{'task_id':pay.task_id,'status':'ANSWERED','claim_ids':['pay'],'missing':''}]}]}
        part=next(part for part in assess_parts(a,selected,claims,review,True) if part.task_id==pay.task_id)
        self.assertEqual(part.answer_status,'PARTIAL')
        self.assertIn('prerequisite_task:'+duration.task_id,part.missing_requirements)


class DeploymentTests(unittest.TestCase):
    def test_kaggle_refuses_to_choose_between_old_and_new_artifacts(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('online_remote_release_test',Path(__file__).resolve().parents[2]/'kaggle/online_remote.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            old=root/'vn_labor_results_v8.1(aura).zip'; old.write_bytes(b'old')
            new=root/'vn_labor_results.zip'; new.write_bytes(b'new')
            with self.assertRaisesRegex(RuntimeError,'2 candidates'):
                module.detect_artifact(None,input_root=root)
            self.assertEqual(module.detect_artifact(str(new),input_root=root),new.resolve())

    def test_kaggle_accepts_automatically_unpacked_new_result(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('online_remote_directory_test',Path(__file__).resolve().parents[2]/'kaggle/online_remote.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); artifact=root/'dataset/artifacts'
            for name in ('reports/final_outputs_validation.json','06_indexes/retrieval_units.jsonl',
              '05_graph/nodes.jsonl','reports/dense_validation.json','reports/neo4j_validation.json'):
                file=artifact/name; file.parent.mkdir(parents=True,exist_ok=True); file.write_text('{}',encoding='utf-8')
            self.assertEqual(module.detect_artifact(None,input_root=root),artifact.parent.resolve())

    def test_technical_compatibility_does_not_certify_legal_readiness(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); build=fixture(root)
            cfg=OnlineConfig(artifact_source=str(root),expected_build_id=build,cache_dir=str(root/'cache'))
            report=ArtifactStore(cfg).report
            self.assertTrue(report.technical_compatible)
            self.assertFalse(report.legal_ready)
            self.assertEqual(report.legal_status,'PROVISIONAL')

    def test_cold_and_warm_retrieval_have_separate_timing_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); build=fixture(root)
            cfg=OnlineConfig(artifact_source=str(root),expected_build_id=build)
            retriever=Retriever(ArtifactStore(cfg),cfg); retriever._model=FakeModel()
            with request_budget(30):
                self.assertTrue(retriever.bm25('tiền lương'))
                self.assertTrue(retriever.dense('tiền lương'))
                cold=measured_timings()
            with request_budget(30):
                retriever.bm25('tiền lương'); retriever.dense('tiền lương')
                warm=measured_timings()
            self.assertIn('bm25.index_load',cold); self.assertIn('dense.index_load',cold)
            self.assertNotIn('bm25.index_load',warm); self.assertNotIn('dense.index_load',warm)
            self.assertIn('dense.encode',warm); self.assertIn('dense.search',warm)

    def test_pool_sweep_does_not_change_deployment_defaults(self):
        import importlib.util
        module_path=Path(__file__).resolve().parents[2]/'scripts/benchmark_retrieval.py'
        spec=importlib.util.spec_from_file_location('retrieval_pool_review_test',module_path)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); build=fixture(root)
            cfg=OnlineConfig(artifact_source=str(root),expected_build_id=build)
            pipe=OnlinePipeline(cfg); pipe.retriever._model=FakeModel()
            try:
                report=module.pool_sweep(pipe,[{'id':'draft','question':'Tiền lương','gold_unit_ids':['prov_1']}])
                self.assertEqual(pipe.retriever.cfg,cfg)
                self.assertIn('candidate_12_12_8_12',report)
                self.assertEqual(report['baseline_30_30_20_30']['queries'],1)
            finally: pipe.close()

    @unittest.skipUnless(os.name=='nt','Windows launcher precedence')
    def test_windows_launcher_explicit_config_overrides_environment(self):
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as folder:
            fake=Path(folder)/'capture-python.cmd'
            fake.write_text('@echo off\necho %*\nexit /b 0\n',encoding='ascii')
            env={**os.environ,'VN_LABOR_PYTHON':str(fake),'VN_LABOR_ONLINE_CONFIG':'from_environment.yaml'}
            command=['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'scripts/run.ps1'),'online-check']
            first=subprocess.run(command,cwd=root,env=env,capture_output=True,timeout=20)
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertIn(b'--config from_environment.yaml',first.stdout)
            second=subprocess.run(command+['-Config','explicit.yaml'],cwd=root,env=env,capture_output=True,timeout=20)
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertIn(b'--config explicit.yaml',second.stdout)
