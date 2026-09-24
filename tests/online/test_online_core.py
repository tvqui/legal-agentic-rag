from __future__ import annotations
import json,tempfile,unittest,zipfile
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
import numpy as np
from vn_labor_online.analysis import intake,analyze,evidence_slots,plan_evidence
from vn_labor_online.artifact_store import ArtifactStore,_fingerprint
from vn_labor_online.audit import deterministic_audit,reference_audit,citations,applicability
from vn_labor_online.config import OnlineConfig,RetrievalConfig,GraphConfig,ApplicabilityConfig,AdjudicationConfig
from vn_labor_online.evidence import state_for,select_for_plan,build_verified_pack,detect_authoritative_conflicts
from vn_labor_online.errors import OfflineArtifactMismatch
from vn_labor_online.graph import GraphExplorer
from vn_labor_online.models import EvidencePlan,EvidenceState,QueryRequest,Route,SlotStatus,Stop,VerifiedEvidenceItem,VerifiedEvidencePack
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_online.retrieval import Retriever,authority_filter,temporal_filter
from vn_labor_online.api import create_app
from vn_labor_online.applicability import LegalApplicabilityAuditor
from vn_labor_online.generation import LegalAdjudicator,adjudicate

def write_jsonl(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf-8')
def fixture(root:Path):
    a=root/'artifacts'; url='https://vbpl.vn/example'
    units=[{'unit_id':'prov_1','kind':'PROVISION','text':'Bộ luật Lao động > 145/2020/ND-CP > Điều 1\nQuy định tiền lương.',
      'source_text':'Điều 1. Quy định tiền lương.','breadcrumb':'145/2020/ND-CP > Điều 1','document_id':'doc_1',
      'instrument_id':'inst_1','provision_identity_id':'pid_1','provision_version_id':'prov_1','document_number':'145/2020/ND-CP',
      'instrument_number':'145/2020/ND-CP','document_title':'Test law','level':'ARTICLE','article_number':'1','clause_number':'','point_number':'',
      'source_url':url,'valid_from':'2021-01-01','valid_to':None,'authority_rank':100,'binding':True,'temporal_verified':True,
      'provision_temporal_verified':False,'official_source':True,'source_catalog_status':'VERIFIED','provenance':{'file_id':'file_1','relative_path':'x.pdf','source_url':url},'provenance_span':{'char_start':0,'char_end':34}},
     {'unit_id':'prov_2','kind':'PROVISION','text':'Ngoại lệ về tiền lương.','source_text':'Ngoại lệ về tiền lương.',
      'breadcrumb':'Ngoại lệ','document_id':'doc_1','instrument_id':'inst_1','provision_identity_id':'pid_2','provision_version_id':'prov_2',
      'document_number':'145/2020/ND-CP','instrument_number':'145/2020/ND-CP','document_title':'Test law','level':'ARTICLE','article_number':'2',
      'source_url':url,'valid_from':'2021-01-01','valid_to':None,'authority_rank':100,'binding':True,'temporal_verified':True,
      'provision_temporal_verified':True,'official_source':True,'source_catalog_status':'VERIFIED','provenance':{'file_id':'file_1','relative_path':'x.pdf','source_url':url},'provenance_span':{'char_start':35,'char_end':60}}]
    nodes=[{'id':'doc_1','label':'DocumentVersion','properties':{}},
      {'id':'prov_1','label':'Article','properties':{'article_number':'1','clause_number':'','point_number':''}},
      {'id':'prov_2','label':'Article','properties':{'article_number':'2','clause_number':'','point_number':''}},
      {'id':'issue_1','label':'LegalIssue','properties':{'issue_key':'Termination','label_vi':'Chấm dứt hợp đồng lao động'}}]
    edges=[{'id':'e1','source':'prov_1','target':'prov_2','type':'REFERENCES','properties':{}},
      {'id':'e2','source':'prov_1','target':'issue_1','type':'RELATES_TO_ISSUE','properties':{}}]
    write_jsonl(a/'06_indexes/retrieval_units.jsonl',units); write_jsonl(a/'05_graph/nodes.jsonl',nodes); write_jsonl(a/'05_graph/edges.jsonl',edges)
    write_jsonl(a/'00_manifest/source_catalog_resolved.jsonl',[{'file_id':'file_1','relative_path':'x.pdf','sha256':'abc','source_url':url,'official_source':True,'catalog_status':'VERIFIED'}])
    write_jsonl(a/'06_indexes/dense/metadata.jsonl',units); write_jsonl(a/'06_indexes/bm25/corpus.jsonl',[{'id':x['unit_id'],'text':x['text'],'kind':x['kind']} for x in units])
    import faiss,bm25s
    vectors=np.asarray([[1,0],[0,1]],dtype='float32'); idx=faiss.IndexFlatIP(2); idx.add(vectors); (a/'06_indexes/dense/faiss.index').write_bytes(faiss.serialize_index(idx).tobytes())
    tokens=bm25s.tokenize([x['text'].lower() for x in units],stopwords=None,stemmer=None); bm=bm25s.BM25(); bm.index(tokens); bm.save(str(a/'06_indexes/bm25'),corpus=[{'id':x['unit_id'],'text':x['text'],'kind':x['kind']} for x in units])
    build=_fingerprint([nodes,edges]); (a/'reports').mkdir(parents=True)
    (a/'reports/final_outputs_validation.json').write_text(json.dumps({'stages':{x:True for x in ('registry','structure','graph','indexes')},'source_catalog_quality':{'passed':False},'semantic_quality':{'passed':False},'gold_evaluation':{'passed':False},'gold_build_id':'gold'}),encoding='utf-8')
    (a/'reports/dense_validation.json').write_text(json.dumps({'dense_passed':True,'units':2,'fingerprint':'dense'}),encoding='utf-8')
    (a/'reports/neo4j_validation.json').write_text(json.dumps({'passed':True,'build_id':build,'nodes':len(nodes),'edges':len(edges)}),encoding='utf-8')
    return build
class FakeModel:
    def encode(self,*a,**k): return {'dense_vecs':np.asarray([[1,0]],dtype='float32')}

class OnlineTests(unittest.TestCase):
    def setUp(self):
        self.env_patcher=patch.dict('os.environ',{
          'VN_LABOR_ARTIFACT_SOURCE':'',
          'VN_LABOR_ONLINE_CACHE':'',
          'VN_LABOR_APPLICABILITY_MODE':'deterministic',
          'VN_LABOR_ADJUDICATION_MODE':'deterministic',
          'VN_LABOR_API_KEY':'',
        },clear=False)
        self.env_patcher.start()
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.build=fixture(self.root)
        self.cfg=OnlineConfig(artifact_source=str(self.root),expected_build_id=self.build,cache_dir=str(self.root/'cache'),trace_dir=str(self.root/'traces'),
          retrieval=RetrievalConfig(dense_enabled=False),graph=GraphConfig(max_nodes=3,max_edges=3,max_hops=2,max_rounds=2))
        self.store=ArtifactStore(self.cfg)
    def tearDown(self):
        self.tmp.cleanup()
        self.env_patcher.stop()
    def test_offline_compatibility(self):
        self.assertTrue(self.store.report.compatible); self.assertEqual(self.store.report.build_id,self.build)
        self.assertIn('GOLD_NOT_APPROVED',self.store.report.provisional_reasons)
    def test_offline_mismatch_fails_fast(self):
        with self.assertRaises(OfflineArtifactMismatch): ArtifactStore(self.cfg.model_copy(update={'expected_build_id':'bad'}))
    def test_offline_zip_rejects_path_traversal(self):
        archive=self.root/'malicious.zip'
        with zipfile.ZipFile(archive,'w') as output: output.writestr('../outside.txt','bad')
        malicious=self.cfg.model_copy(update={'artifact_source':str(archive),'expected_build_id':None,'expected_archive_sha256':None})
        with self.assertRaisesRegex(OfflineArtifactMismatch,'path traversal'): ArtifactStore(malicious)
    def test_offline_zip_rejects_duplicate_paths(self):
        archive=self.root/'duplicate.zip'
        with zipfile.ZipFile(archive,'w') as output:
            output.writestr('same.txt','one'); output.writestr('same.txt','two')
        duplicate=self.cfg.model_copy(update={'artifact_source':str(archive),'expected_build_id':None,'expected_archive_sha256':None})
        with self.assertRaisesRegex(OfflineArtifactMismatch,'duplicate paths'): ArtifactStore(duplicate)
    def test_query_analyzer_direct(self):
        a=analyze(intake('Điều 1 của 145/2020/ND-CP quy định gì?',[])); self.assertEqual(a.route,Route.DIRECT); self.assertEqual(a.explicit_references[0].article,'1')
    def test_query_identity_includes_date_and_facts(self):
        one=intake('Câu hỏi',[],'2024-01-01',{'notice_days':10})
        two=intake('Câu hỏi',[],'2024-01-02',{'notice_days':10})
        three=intake('Câu hỏi',[],'2024-01-01',{'notice_days':20})
        self.assertEqual(len({one.query_id,two.query_id,three.query_id}),3)
    def test_reference_without_instrument_is_direct_but_requests_disambiguation(self):
        a=analyze(intake('Khoản 2 Điều 35 quy định gì?',[]))
        self.assertEqual(a.route,Route.DIRECT); self.assertTrue(a.missing_facts)
    def test_analyzer_recognizes_harassment_issue(self):
        a=analyze(intake('Người lao động bị quấy rối tình dục tại nơi làm việc thì làm gì?',[]))
        self.assertIn('HARASSMENT',a.legal_issues)
    def test_overtime_is_classified_as_wage_and_working_time(self):
        a=analyze(intake('Tiền lương làm thêm giờ được tính thế nào?',[]))
        self.assertIn('WAGE',a.legal_issues); self.assertIn('WORKING_TIME',a.legal_issues)
    def test_query_analyzer_document_type_and_date_remain_direct(self):
        a=analyze(intake('Điều 1 của Nghị định 145/2020/NĐ-CP quy định gì?',[]),'2024-01-01')
        self.assertEqual(a.route,Route.DIRECT); self.assertEqual(a.explicit_references[0].instrument_number,'145/2020/NĐ-CP')
        self.assertNotIn('event_date',a.facts)
    def test_query_date_alone_does_not_make_question_complex(self):
        a=analyze(intake('Người lao động được nghỉ phép năm bao nhiêu ngày?',[]),'2024-01-01')
        self.assertEqual(a.route,Route.STANDARD); self.assertIn('LEAVE',a.legal_issues)
    def test_current_question_is_not_contaminated_by_conversation_history(self):
        context=['Điều 1 của Nghị định 145/2020/NĐ-CP quy định gì?',
          'Câu trả lời trước có tiền lương, hợp đồng, tranh chấp và kỷ luật lao động.']
        a=analyze(intake('Người lao động làm việc 12 tháng thì được nghỉ phép năm bao nhiêu ngày?',context))
        self.assertEqual(a.route,Route.STANDARD); self.assertEqual(a.legal_issues,['LEAVE'])
        self.assertEqual(a.facts['worked_months'],12)
    def test_employee_resignation_analysis_extracts_actor_dates_and_required_slots(self):
        question=('Tôi ký hợp đồng lao động không xác định thời hạn từ năm 2022. Ngày 10/9/2026 tôi gửi thông báo nghỉ việc '
          'và muốn nghỉ chính thức vào ngày 30/9/2026. Tôi không thuộc trường hợp được nghỉ không cần báo trước. '
          'Việc tôi chỉ báo trước 20 ngày có đúng quy định không, và nếu nghỉ như vậy thì tôi có thể phải chịu hậu quả pháp lý gì?')
        result=analyze(intake(question,[])); plan=plan_evidence(result)
        self.assertEqual(result.facts['actor'],'EMPLOYEE'); self.assertEqual(result.facts['contract_type'],'INDEFINITE')
        self.assertEqual(result.facts['notice_date'],'2026-09-10'); self.assertEqual(result.facts['termination_date'],'2026-09-30')
        self.assertEqual(result.query_date,'2026-09-30'); self.assertEqual(result.facts['notice_days'],20)
        self.assertIs(result.facts['notice_exception'],False); self.assertEqual(result.requested_outcome,'ASSESS_LEGALITY')
        self.assertFalse(result.missing_facts); self.assertEqual(result.route,Route.STANDARD)
        self.assertIn('legal_classification',plan.mandatory_slots); self.assertIn('legal_consequences',plan.mandatory_slots)
    def test_fact_completeness(self):
        a=analyze(intake('Công ty chấm dứt hợp đồng có đúng luật không?',[])); self.assertTrue(a.missing_facts)
    def test_analyzer_extracts_month_notice_and_plans_termination_evidence(self):
        a=analyze(intake('Công ty cho tôi nghỉ tháng 6/2020, báo trước 10 ngày có đúng luật không?',[]))
        self.assertEqual(a.query_date,'2020-06-01'); self.assertEqual(a.query_date_end,'2020-06-30'); self.assertEqual(a.query_date_precision,'MONTH'); self.assertEqual(a.facts['notice_days'],10)
        self.assertEqual(a.route,Route.COMPLEX); self.assertIn('notice_requirement',plan_evidence(a).mandatory_slots)
        self.assertEqual(len(a.missing_facts),3)
    def test_supplied_facts_complete_the_fact_gate(self):
        a=analyze(intake('Công ty cho tôi nghỉ tháng 6/2020, báo trước 10 ngày có đúng luật không?',[]),
          supplied_facts={'contract_type':'FIXED_TERM','termination_reason':'thay đổi cơ cấu','protected_status':'NONE'})
        self.assertFalse(a.missing_facts)
        unknown=analyze(intake('Công ty cho tôi nghỉ tháng 6/2020, báo trước 10 ngày có đúng luật không?',[]),
          supplied_facts={'contract_type':'FIXED_TERM','termination_reason':'thay đổi cơ cấu','protected_status':'UNKNOWN'})
        self.assertTrue(any('bảo vệ đặc biệt' in prompt for prompt in unknown.missing_facts))
    def test_exact_lookup(self):
        a=analyze(intake('Điều 1 của 145/2020/ND-CP quy định gì?',[])); got=Retriever(self.store,self.cfg).exact(a.explicit_references); self.assertEqual(got[0].unit_id,'prov_1')
    def test_exact_hierarchy_expands_children_in_source_order(self):
        child={**self.store.units_by_id['prov_1'],'unit_id':'clause_1','provision_identity_id':'pid_clause_1',
          'provision_version_id':'clause_1','level':'CLAUSE','clause_number':'1','source_text':'1. Nội dung khoản một.',
          'text':'Điều 1 > Khoản 1\n1. Nội dung khoản một.','provenance_span':{'char_start':35,'char_end':58,'document_char_start':35}}
        self.store.units.append(child); self.store.units_by_id[child['unit_id']]=child
        node={'id':'clause_1','label':'Clause','properties':{'article_number':'1','clause_number':'1','point_number':''}}
        self.store.nodes.append(node); self.store.nodes_by_id[node['id']]=node
        self.store.edges.append({'id':'part_1','source':'clause_1','target':'prov_1','type':'PART_OF','properties':{}})
        exact=Retriever(self.store,self.cfg).exact(analyze(intake('Điều 1 của 145/2020/ND-CP quy định gì?',[])).explicit_references)
        descendants=Retriever(self.store,self.cfg).hierarchy_descendants(exact,10)
        self.assertEqual([x.unit_id for x in descendants],['clause_1'])
        self.assertEqual(descendants[0].graph_relations,['PART_OF']); self.assertEqual(descendants[0].graph_directions,['IN'])
    def test_bm25_retrieval(self): self.assertEqual(Retriever(self.store,self.cfg).bm25('Bộ luật quy định',1)[0].unit_id,'prov_1')
    def test_dense_retrieval(self):
        r=Retriever(self.store,self.cfg); r._model=FakeModel(); self.assertEqual(r.dense('x',1)[0].unit_id,'prov_1')
    def test_legal_issue_anchor(self):
        got=Retriever(self.store,self.cfg).issue_anchor(['TERMINATION']); self.assertIn('prov_1',{x.unit_id for x in got})
    def test_dedicated_case_law_retrieval(self):
        case={**self.store.units[0],'unit_id':'case_1','kind':'CASE','document_number':'03/2024/LĐ-PT',
          'document_title':'Bản án lao động','text':'Bản án về đơn phương chấm dứt hợp đồng lao động'}
        self.store.units.append(case); self.store.units_by_id['case_1']=case
        got=Retriever(self.store,self.cfg).case_law('Tìm bản án 03/2024/LĐ-PT về chấm dứt hợp đồng')
        self.assertEqual(got[0].unit_id,'case_1'); self.assertEqual(got[0].retrieval_method,'case_law')
    def test_fusion_deduplicates(self):
        r=Retriever(self.store,self.cfg); x=r.bm25('tiền lương',2); self.assertEqual(len(r.fusion([x,x])),2)
    def test_temporal_filter_rejects_unreviewed(self):
        e=Retriever(self.store,self.cfg).bm25('tiền lương',2); got,removed=temporal_filter(e,'2024-01-01'); self.assertIn('prov_1',removed); self.assertIn('prov_2',{x.unit_id for x in got})
    def test_temporal_filter_document_fallback_is_explicit(self):
        e=Retriever(self.store,self.cfg).exact([analyze(intake('Điều 1 của 145/2020/ND-CP quy định gì?',[])).explicit_references[0]])
        got,removed=temporal_filter(e,'2024-01-01',strict=False)
        self.assertFalse(removed); self.assertEqual(got[0].unit_id,'prov_1')
        audited=deterministic_audit(self.store,got,'2024-01-01',allow_document_temporal_fallback=True)
        self.assertTrue(audited[0].verified); self.assertIn('DOCUMENT_LEVEL_TEMPORAL_FALLBACK',audited[0].audit_warnings)
    def test_month_precision_uses_interval_overlap(self):
        item=Retriever(self.store,self.cfg).bm25('tiền lương',1)[0].model_copy(update={
          'valid_from':'2020-06-15','provision_temporal_verified':True})
        got,removed=temporal_filter([item],'2020-06-01',query_date_end='2020-06-30')
        self.assertFalse(removed); self.assertEqual(got[0].unit_id,item.unit_id)
        self.assertIn('IMPRECISE_QUERY_DATE_OVERLAPS_VERSION_BOUNDARY',got[0].audit_warnings)
    def test_consecutive_versions_are_not_reported_as_simultaneous_conflict(self):
        base=Retriever(self.store,self.cfg).bm25('tiền lương',1)[0]
        old=base.model_copy(update={'unit_id':'old','provision_identity_id':'same','provision_version_id':'old',
          'source_text':'Quy định cũ','text':'Quy định cũ','valid_from':'2020-01-01','valid_to':'2020-06-15','provision_temporal_verified':True})
        new=base.model_copy(update={'unit_id':'new','provision_identity_id':'same','provision_version_id':'new',
          'source_text':'Quy định mới','text':'Quy định mới','valid_from':'2020-06-15','valid_to':None,'provision_temporal_verified':True})
        self.assertFalse(detect_authoritative_conflicts([old,new],'2020-06-01','2020-06-30'))
        overlapping=old.model_copy(update={'valid_to':'2020-06-20'})
        self.assertEqual(detect_authoritative_conflicts([overlapping,new],'2020-06-01','2020-06-30'),[['old','new']])
    def test_graph_expansion_is_bounded(self):
        seed=Retriever(self.store,self.cfg).exact([analyze(intake('Điều 1 của 145/2020/ND-CP quy định gì?',[])).explicit_references[0]])
        got,stats=GraphExplorer(self.store,self.cfg.graph).expand(seed,['mandatory_reference']); self.assertLessEqual(stats['nodes_visited'],3); self.assertIn('prov_2',{x.unit_id for x in got})
        self.assertIn('REFERENCES',got[0].graph_relations); self.assertIn('OUT',got[0].graph_directions)
    def test_graph_round_honours_wall_clock_budget(self):
        explorer=GraphExplorer(self.store,self.cfg.graph)
        visited={'prov_1'}; paths={'prov_1':[]}
        with patch('vn_labor_online.graph.time.monotonic',side_effect=[0.0,0.002,0.002]):
            added,frontier,stats=explorer.expand_round(['prov_1'],['mandatory_reference'],'',visited,paths,2,3,wall_clock_ms=1)
        self.assertFalse(added); self.assertFalse(frontier); self.assertEqual(stats['stop_reason'],'TIME_BUDGET')
    def test_reference_edge_direction_is_not_silently_reversed(self):
        seed=[Retriever(self.store,self.cfg).bm25('ngoại lệ',2)[0].model_copy(update={'unit_id':'prov_2'})]
        got,_=GraphExplorer(self.store,self.cfg.graph).expand(seed,['mandatory_reference'])
        self.assertNotIn('prov_1',{x.unit_id for x in got})
    def test_deterministic_auditor_and_url(self):
        item=Retriever(self.store,self.cfg).bm25('lương',1); audited=deterministic_audit(self.store,item,None); self.assertTrue(audited[0].verified)
        fake=item[0].model_copy(update={'source_url':'https://evil.invalid'}); self.assertFalse(deterministic_audit(self.store,[fake],None)[0].verified)
        fake_span=item[0].model_copy(update={'provenance_span':{'char_start':999,'char_end':1000}})
        self.assertFalse(deterministic_audit(self.store,[fake_span],None)[0].verified)
    def test_deterministic_auditor_rejects_invalid_interval_without_query_date(self):
        item=Retriever(self.store,self.cfg).bm25('ngoại lệ',2)[0].model_copy(update={'valid_from':'2022-01-01','valid_to':'2021-01-01'})
        audited=deterministic_audit(self.store,[item],None)
        self.assertFalse(audited[0].verified); self.assertIn('INVALID_TEMPORAL_INTERVAL',audited[0].audit_issues)
    def test_issue_applicability_filters_lexical_false_positive(self):
        item=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('lương',1),None)[0]
        leave=item.model_copy(update={'unit_id':'leave','text':'Điều 113. Nghỉ hằng năm: 12 ngày làm việc.'})
        retirement=item.model_copy(update={'unit_id':'retire','text':'Thời điểm nghỉ hưu của người lao động.'})
        got=applicability([leave,retirement],'người lao động nghỉ phép năm bao nhiêu ngày',['LEAVE'])
        self.assertEqual([x.unit_id for x in got],['leave'])
    def test_applicability_rejects_under_12_month_rule_for_12_month_fact(self):
        base=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('tiền lương',1),None)[0]
        full=base.model_copy(update={'unit_id':'full','text':'Người lao động làm việc đủ 12 tháng được nghỉ hằng năm 12 ngày làm việc.',
          'source_text':'Người lao động làm việc đủ 12 tháng được nghỉ hằng năm 12 ngày làm việc.'})
        proportional=base.model_copy(update={'unit_id':'proportional','text':'Người lao động làm việc chưa đủ 12 tháng được nghỉ hằng năm theo tỷ lệ.',
          'source_text':'Người lao động làm việc chưa đủ 12 tháng được nghỉ hằng năm theo tỷ lệ.'})
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig())
        accepted,decisions,_=auditor.audit([full,proportional],'làm việc 12 tháng nghỉ phép năm',['LEAVE'],{'worked_months':12},'EXPLAIN')
        self.assertIn('full',{item.unit_id for item in accepted}); self.assertNotIn('proportional',{item.unit_id for item in accepted})
        rejected=next(item for item in decisions if item.evidence_id=='proportional')
        self.assertIn('FACT_CONTRADICTS_UNDER_12_MONTH_RULE',rejected.reasons)
    def test_employee_termination_applicability_rejects_employer_and_unproven_special_rules(self):
        base=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('tiền lương',1),None)[0]
        employee=base.model_copy(update={'unit_id':'employee','document_number':'18/VBHN-VPQH','article_number':'35','clause_number':'1','point_number':'a',
          'text':'a) Ít nhất 45 ngày nếu làm việc theo hợp đồng lao động không xác định thời hạn;',
          'source_text':'a) Ít nhất 45 ngày nếu làm việc theo hợp đồng lao động không xác định thời hạn;'})
        employer=base.model_copy(update={'unit_id':'employer','document_number':'45/2019/QH14','article_number':'36','clause_number':'2','point_number':'a',
          'text':'Người sử dụng lao động phải báo trước ít nhất 45 ngày.','source_text':'Người sử dụng lao động phải báo trước ít nhất 45 ngày.'})
        special=base.model_copy(update={'unit_id':'special','document_number':'145/2020/NĐ-CP','article_number':'7','clause_number':'2','point_number':'a',
          'text':'Ngành nghề đặc thù phải báo trước ít nhất 120 ngày.','source_text':'Ngành nghề đặc thù phải báo trước ít nhất 120 ngày.'})
        facts={'actor':'EMPLOYEE','contract_type':'INDEFINITE','notice_days':20,'notice_exception':False}
        accepted,decisions,_=LegalApplicabilityAuditor(ApplicabilityConfig()).audit([employee,employer,special],
          'người lao động nghỉ việc báo trước 20 ngày có đúng quy định không',['TERMINATION'],facts,'ASSESS_LEGALITY')
        self.assertEqual([item.unit_id for item in accepted],['employee'])
        reasons={decision.evidence_id:decision.reasons for decision in decisions}
        self.assertIn('WRONG_ACTOR_EMPLOYER_TERMINATION_RULE',reasons['employer'])
        self.assertIn('SPECIAL_OCCUPATION_NOT_ESTABLISHED',reasons['special'])
    def test_annual_leave_adjudication_summarizes_12_14_16_days(self):
        state=EvidenceState(slots={'governing_rule':{'status':SlotStatus.FOUND_VERIFIED,'evidence_ids':['a','b','c']}},
          gaps=['official_source'],coverage=.5,mandatory_slots=['governing_rule'])
        texts={
          'a':'a) 12 ngày làm việc đối với người làm công việc trong điều kiện bình thường;',
          'b':'b) 14 ngày làm việc đối với người lao động chưa thành niên, người khuyết tật, người làm nghề, công việc nặng nhọc, độc hại, nguy hiểm;',
          'c':'c) 16 ngày làm việc đối với người làm nghề, công việc đặc biệt nặng nhọc, độc hại, nguy hiểm.'}
        evidence=[VerifiedEvidenceItem(evidence_id=key,instrument_number='45/2019/QH14',article='113',clause='1',point=key,
          text=value,binding=True,official_source=True,authority_rank=100) for key,value in texts.items()]
        pack=VerifiedEvidencePack(query='Người lao động làm việc 12 tháng thì được nghỉ phép năm bao nhiêu ngày?',
          query_date='2025-01-01',facts={'worked_months':12},requested_outcome='EXPLAIN',coverage_state=state,evidence=evidence)
        draft=adjudicate(pack,True,[])
        self.assertEqual(len(draft.claims),3)
        for days in (12,14,16): self.assertIn(f'{days} ngày làm việc',draft.answer_summary)
    def test_employee_termination_adjudication_answers_legality_and_consequences(self):
        state=EvidenceState(slots={'governing_rule':{'status':SlotStatus.FOUND_VERIFIED,'evidence_ids':['n','u','c1','c2','c3']}},
          gaps=['official_source'],coverage=.8,mandatory_slots=['governing_rule'])
        rows=[
          ('n','35','1','a','Ít nhất 45 ngày nếu làm việc theo hợp đồng lao động không xác định thời hạn;'),
          ('u','39','','','Đơn phương chấm dứt hợp đồng lao động không đúng Điều 35 là trái pháp luật.'),
          ('c1','40','1','','Không được trợ cấp thôi việc.'),
          ('c2','40','2','','Phải bồi thường nửa tháng tiền lương theo hợp đồng và tiền lương trong những ngày không báo trước.'),
          ('c3','40','3','','Phải hoàn trả chi phí đào tạo quy định tại Điều 62.')]
        evidence=[VerifiedEvidenceItem(evidence_id=uid,instrument_number='18/VBHN-VPQH',article=article,clause=clause,point=point,
          text=text,binding=True,official_source=True,authority_rank=100,official_url='https://congbao.chinhphu.vn/source') for uid,article,clause,point,text in rows]
        facts={'actor':'EMPLOYEE','contract_type':'INDEFINITE','notice_days':20,'notice_exception':False,
          'notice_date':'2026-09-10','termination_date':'2026-09-30'}
        pack=VerifiedEvidencePack(query='Tôi báo trước 20 ngày có đúng quy định và hậu quả pháp lý gì?',query_date='2026-09-30',
          facts=facts,requested_outcome='ASSESS_LEGALITY',coverage_state=state,evidence=evidence)
        draft=adjudicate(pack,True,[])
        self.assertIn('Không đúng quy định',draft.answer_summary); self.assertIn('còn thiếu 25 ngày',draft.answer_summary)
        self.assertIn('Khoản 1 Điều 40',draft.answer_summary); self.assertIn('Khoản 2 Điều 40',draft.answer_summary)
        self.assertIn('Khoản 3 Điều 40',draft.answer_summary); self.assertNotIn('Điều 36',draft.answer_summary)
    def test_pipeline_defaults_undated_query_to_corpus_snapshot(self):
        cfg=self.cfg.model_copy(update={'corpus_snapshot_as_of':'2025-01-01'})
        out=OnlinePipeline(cfg).ask(QueryRequest(question='Điều 1 của 145/2020/ND-CP quy định gì?'))
        self.assertEqual(out.applicable_date,'2025-01-01')
        self.assertIn('QUERY_DATE_DEFAULTED_TO_CORPUS_SNAPSHOT',out.warnings)
    def test_evidence_state_gap(self):
        item=Retriever(self.store,self.cfg).exact([analyze(intake('Điều 1 của 145/2020/ND-CP quy định gì?',[])).explicit_references[0]])
        item=deterministic_audit(self.store,item,None); state=state_for(item,['governing_rule','applicable_version'],'2024-01-01'); self.assertIn('applicable_version',state.gaps)
    def test_coverage_is_recomputed_after_coverage_aware_selection(self):
        values=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('lương ngoại lệ',2),None)
        values=[x.model_copy(update={'provision_version_id':None,'graph_path':['e1'],'graph_relations':['REFERENCES'],'graph_directions':['OUT']}) if x.unit_id=='prov_2' else x for x in values]
        plan=EvidencePlan(mandatory_slots=['governing_rule','exceptions','mandatory_reference'])
        selected,state=select_for_plan(values,plan,None,False,2)
        self.assertFalse(state.gaps); self.assertEqual({x.unit_id for x in selected},{'prov_1','prov_2'})
        selected,state=select_for_plan(values,plan,None,False,1)
        self.assertTrue(state.gaps)
    def test_conditional_slot_remains_unresolved_without_evidence(self):
        item=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('lương',1),None)
        state=state_for(item,EvidencePlan(mandatory_slots=['governing_rule'],conditional_slots=['amendment_history']),None)
        self.assertEqual(state.slots['amendment_history'].status.value,'UNRESOLVED')
    def test_authority_filter_is_strict_only_when_requested(self):
        item=Retriever(self.store,self.cfg).bm25('lương',1)[0].model_copy(update={'official_source':False,'source_catalog_status':'UNVERIFIED'})
        self.assertEqual(len(authority_filter([item],strict=False)[0]),1)
        self.assertEqual(authority_filter([item],strict=True)[0],[])
    def test_deterministic_applicability_fails_closed_on_unknown_condition(self):
        item=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('lương',1),None)[0]
        condition_text='Khi đủ điều kiện thì người lao động được hưởng tiền lương.'
        conditioned=item.model_copy(update={'text':condition_text,'source_text':condition_text})
        auditor=LegalApplicabilityAuditor(ApplicabilityConfig())
        accepted,decisions,warnings=auditor.audit([conditioned],'tiền lương',['WAGE'],{},'ASSESS_LEGALITY')
        self.assertFalse(accepted); self.assertEqual(decisions[0].audit_status,'UNRESOLVED'); self.assertTrue(warnings)
        accepted,decisions,_=auditor.audit([conditioned],'tiền lương',['WAGE'],{'conditions_satisfied':True},'ASSESS_LEGALITY')
        self.assertFalse(accepted); self.assertEqual(decisions[0].conditions_status,'UNKNOWN')
    def test_adjudicator_rejects_evidence_outside_verified_pack(self):
        item=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('lương',1),None)[0]
        state=state_for([item],EvidencePlan(mandatory_slots=['governing_rule']),None)
        pack=build_verified_pack('lương',None,{},state,[item])
        adjudicator=LegalAdjudicator(AdjudicationConfig(mode='deterministic'))
        class BadProvider:
            def structured(self,*args):
                return {'answer_summary':'Sai [invented]','claims':[{'claim_id':'c1','text':'Sai','evidence_ids':['invented']}],
                  'applicable_law_versions':[],'assumptions':[],'limitations':[]}
        adjudicator.provider=BadProvider()
        draft,warnings=adjudicator.generate(pack,False,[])
        self.assertTrue(warnings); self.assertNotIn('invented',{evidence_id for claim in draft.claims for evidence_id in claim.evidence_ids})
    def test_adjudicator_discards_unchecked_provider_narrative(self):
        item=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('lương',1),None)[0]
        state=state_for([item],EvidencePlan(mandatory_slots=['governing_rule']),None)
        pack=build_verified_pack('lương',None,{},state,[item])
        adjudicator=LegalAdjudicator(AdjudicationConfig(mode='deterministic'))
        class Provider:
            def __init__(self,evidence_id): self.evidence_id=evidence_id
            def structured(self,*args):
                return {'answer_summary':'Điều 999 cho phép một nội dung không có trong evidence.',
                  'claims':[{'claim_id':'c1','text':'Quy định tiền lương.','evidence_ids':[self.evidence_id]}],
                  'applicable_law_versions':[],'assumptions':[],'limitations':[]}
        adjudicator.provider=Provider(item.unit_id)
        draft,warnings=adjudicator.generate(pack,False,[])
        self.assertFalse(warnings); self.assertNotIn('Điều 999',draft.answer_summary); self.assertIn(f'[{item.unit_id}]',draft.answer_summary)
    def test_reference_audit_rejects_bad_citation(self):
        item=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('lương',1),None); self.assertFalse(reference_audit('Sai [Article 999]',item,citations(item))[0])
    def test_reference_audit_ignores_bracketed_legal_formula(self):
        item=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('lương',1),None); refs=citations(item)
        answer=f'Công thức [365 - (52 + 12 + 11)] [{item[0].unit_id}]'
        self.assertTrue(reference_audit(answer,item,refs)[0])
    def test_reference_audit_requires_marker_for_every_citation(self):
        item=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('lương',2),None)
        self.assertIn('CITATION_NOT_MARKED',reference_audit(f'[{item[0].unit_id}]',item,citations(item))[1])
    def test_reference_audit_rejects_plain_fabricated_structure_and_url(self):
        item=deterministic_audit(self.store,Retriever(self.store,self.cfg).bm25('lương',1),None)
        refs=citations(item); answer=f'Điều 999 Khoản 88 Điểm z quy định tại https://evil.invalid [{item[0].unit_id}]'
        ok,issues=reference_audit(answer,item,refs)
        self.assertFalse(ok); self.assertTrue(any(x.startswith('UNSUPPORTED_ARTICLE_REFERENCE') for x in issues))
        self.assertTrue(any(x.startswith('UNSUPPORTED_CLAUSE_REFERENCE') for x in issues)); self.assertTrue(any(x.startswith('UNSUPPORTED_POINT_REFERENCE') for x in issues))
        self.assertTrue(any(x.startswith('FABRICATED_URL_IN_ANSWER') for x in issues))
    def test_pipeline_need_more_facts_skips_retrieval(self):
        p=OnlinePipeline(self.cfg); p.retriever.bm25=lambda *a,**k:self.fail('retrieval must not run'); out=p.ask(QueryRequest(question='Công ty chấm dứt hợp đồng có đúng luật không?')); self.assertEqual(out.status,Stop.NEED_MORE_FACTS)
    def test_pipeline_rejects_untrusted_review_bypass(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            QueryRequest(question='Công ty chấm dứt hợp đồng có đúng luật không?',human_reviewed=True)
        with self.assertRaises(ValidationError):
            QueryRequest(question='Công ty chấm dứt hợp đồng có đúng luật không?',facts={'conditions_satisfied':True})
    def test_pipeline_direct_and_no_fabricated_citation(self):
        out=OnlinePipeline(self.cfg).ask(QueryRequest(question='Điều 1 của 145/2020/ND-CP quy định gì?'))
        self.assertEqual(out.status,Stop.SUFFICIENT); self.assertEqual(out.citations[0].evidence_id,'prov_1'); self.assertIn('[prov_1]',out.answer); self.assertEqual(out.trace.edges_visited,0)
        self.assertTrue(out.claims); self.assertEqual(out.trace_id,out.trace.trace_id); self.assertEqual(out.trace.reference_audit,'PASS')
    def test_pipeline_direct_article_includes_clause_children(self):
        pipeline=OnlinePipeline(self.cfg)
        child={**pipeline.store.units_by_id['prov_1'],'unit_id':'clause_1','provision_identity_id':'pid_clause_1',
          'provision_version_id':'clause_1','level':'CLAUSE','clause_number':'1','source_text':'1. Nội dung khoản một.',
          'text':'Điều 1 > Khoản 1\n1. Nội dung khoản một.','provenance_span':{'char_start':35,'char_end':58,'document_char_start':35}}
        pipeline.store.units.append(child); pipeline.store.units_by_id[child['unit_id']]=child
        node={'id':'clause_1','label':'Clause','properties':{'article_number':'1','clause_number':'1','point_number':''}}
        pipeline.store.nodes.append(node); pipeline.store.nodes_by_id[node['id']]=node
        pipeline.store.edges.append({'id':'part_1','source':'clause_1','target':'prov_1','type':'PART_OF','properties':{}})
        out=pipeline.ask(QueryRequest(question='Điều 1 của 145/2020/ND-CP quy định gì?'))
        self.assertEqual([x.evidence_id for x in out.citations],['prov_1','clause_1'])
        self.assertIn('[clause_1]',out.answer); self.assertEqual(out.trace.edges_visited,1)
        self.assertIn('PART_OF',out.trace.critical_edges_followed)
    def test_pipeline_historical_abstains_on_unreviewed_version(self):
        strict=self.cfg.model_copy(update={'provisional_mode':False})
        out=OnlinePipeline(strict).ask(QueryRequest(question='Điều 1 của 145/2020/ND-CP quy định gì?',query_date='2024-01-01'))
        self.assertEqual(out.status,Stop.INSUFFICIENT_EVIDENCE); self.assertFalse(out.citations); self.assertFalse(out.claims)
        self.assertEqual(out.answer,'Không đủ bằng chứng đã xác minh để kết luận.'); self.assertEqual(out.trace.reference_audit,'PASS')
    def test_pipeline_provisional_temporal_fallback_returns_cited_partial(self):
        out=OnlinePipeline(self.cfg).ask(QueryRequest(question='Điều 1 của Nghị định 145/2020/NĐ-CP quy định gì?',query_date='2024-01-01'))
        self.assertEqual(out.status,Stop.PARTIAL_ALLOWED); self.assertEqual(out.trace.route,Route.DIRECT)
        self.assertEqual(out.citations[0].evidence_id,'prov_1'); self.assertIn('applicable_version',out.limitations)
        self.assertTrue(any(x.startswith('DOCUMENT_LEVEL_TEMPORAL_FALLBACK_USED:') for x in out.warnings))
    def test_pipeline_requests_exact_date_when_version_changes_inside_month(self):
        pipeline=OnlinePipeline(self.cfg)
        pipeline.store.units_by_id['prov_1'].update({'valid_from':'2020-06-15','provision_temporal_verified':True})
        out=pipeline.ask(QueryRequest(question='Điều 1 của 145/2020/ND-CP trong tháng 6/2020 quy định gì?'))
        self.assertEqual(out.status,Stop.NEED_MORE_FACTS); self.assertEqual(out.evidence_status,'NEED_MORE_FACTS')
        self.assertFalse(out.citations); self.assertTrue(out.questions); self.assertIn('imprecise_query_date',out.limitations)
    def test_pipeline_exposes_overlapping_authoritative_version_conflict(self):
        pipeline=OnlinePipeline(self.cfg)
        original=pipeline.store.units_by_id['prov_1']
        original.update({'valid_from':'2020-01-01','valid_to':None,'provision_temporal_verified':True})
        conflict={**original,'unit_id':'prov_conflict','provision_version_id':'prov_conflict',
          'text':'Một quy định có nội dung hoàn toàn đối lập.','source_text':'Một quy định có nội dung hoàn toàn đối lập.'}
        pipeline.store.units.append(conflict); pipeline.store.units_by_id['prov_conflict']=conflict
        node={'id':'prov_conflict','label':'Article','properties':{'article_number':'1','clause_number':'','point_number':''}}
        pipeline.store.nodes.append(node); pipeline.store.nodes_by_id['prov_conflict']=node
        out=pipeline.ask(QueryRequest(question='Điều 1 của 145/2020/ND-CP quy định gì?',query_date='2024-01-01'))
        self.assertEqual(out.status,Stop.CONFLICTING_EVIDENCE); self.assertEqual(out.evidence_status,'CONFLICTING')
        self.assertEqual({x.evidence_id for x in out.citations},{'prov_1','prov_conflict'})
        self.assertFalse(out.claims); self.assertIn('AUTHORITATIVE_EVIDENCE_CONFLICT',out.warnings)
    def test_pipeline_standard(self):
        out=OnlinePipeline(self.cfg).ask(QueryRequest(question='Giải thích quy định tiền lương.'))
        self.assertIn(out.status,{Stop.SUFFICIENT,Stop.PARTIAL_ALLOWED}); self.assertTrue(out.citations)
        self.assertLessEqual(len(out.citations),6)
    def test_pipeline_complex_is_bounded(self):
        out=OnlinePipeline(self.cfg).ask(QueryRequest(question='So sánh tiền lương và hợp đồng lao động.'))
        self.assertEqual(out.trace.route,Route.COMPLEX); self.assertLessEqual(out.trace.nodes_visited,self.cfg.graph.max_nodes)
        self.assertTrue(out.trace.evidence_gaps); self.assertIsNotNone(out.trace.stop_reason)
    def test_freshness_warning_when_snapshot_unknown(self):
        out=OnlinePipeline(self.cfg).ask(QueryRequest(question='Hiện nay quy định tiền lương như thế nào?'))
        self.assertIn('CORPUS_MAY_BE_STALE',out.warnings)
    def test_freshness_warns_when_requested_date_exceeds_snapshot(self):
        snapshot=date.today().isoformat(); requested=(date.today()+timedelta(days=1)).isoformat()
        cfg=self.cfg.model_copy(update={'corpus_snapshot_as_of':snapshot})
        out=OnlinePipeline(cfg).ask(QueryRequest(question='Điều 1 của 145/2020/ND-CP quy định gì?',query_date=requested))
        self.assertIn('CORPUS_MAY_BE_STALE',out.warnings)
    def test_current_turn_facts_override_persisted_case_state(self):
        env=intake('Tôi ký hợp đồng không xác định thời hạn.',[])
        result=analyze(env,supplied_facts={'contract_type':'FIXED_TERM','actor':'EMPLOYEE'})
        self.assertEqual(result.facts['contract_type'],'INDEFINITE')
        self.assertEqual(result.facts['actor'],'EMPLOYEE')
    def test_pipeline_returns_confirmed_fact_state(self):
        out=OnlinePipeline(self.cfg).ask(QueryRequest(
          question='Công ty chấm dứt hợp đồng có đúng luật không?',facts={'contract_type':'FIXED_TERM'}))
        self.assertEqual(out.facts['contract_type'],'FIXED_TERM')
    def test_api_optional_bearer_auth(self):
        from fastapi.testclient import TestClient
        config=self.root/'protected.json'; config.write_text(json.dumps({'online':self.cfg.model_dump()}),encoding='utf-8')
        with patch.dict('os.environ',{'VN_LABOR_API_KEY':'test-secret','VN_LABOR_ADJUDICATION_MODE':'deterministic'},clear=False):
            with TestClient(create_app(config)) as client:
                self.assertEqual(client.get('/health').status_code,200)
                self.assertEqual(client.get('/ready').status_code,401)
                headers={'Authorization':'Bearer test-secret'}
                ready=client.get('/ready',headers=headers)
                self.assertEqual(ready.status_code,200); self.assertTrue(ready.json()['ready'])
                self.assertIn('components',ready.json())
                response=client.post('/v1/answer',headers=headers,
                  json={'question':'Điều 1 của 145/2020/ND-CP quy định gì?'})
                self.assertEqual(response.status_code,200)
    def test_api_health_ready_and_answer(self):
        from fastapi.testclient import TestClient
        config=self.root/'online.json'; config.write_text(json.dumps({'online':self.cfg.model_dump()}),encoding='utf-8')
        with TestClient(create_app(config)) as client:
            self.assertEqual(client.get('/health').status_code,200)
            self.assertTrue(client.get('/ready').json()['ready'])
            schema=client.get('/openapi.json').json()['paths']['/v1/answer']['post']['responses']['200']['content']['application/json']['schema']
            self.assertEqual(schema['$ref'],'#/components/schemas/AnswerResponse')
            response=client.post('/v1/answer',json={'question':'Điều 1 của 145/2020/ND-CP quy định gì?'})
            self.assertEqual(response.status_code,200); self.assertEqual(response.json()['status'],'SUFFICIENT')
            invalid=client.post('/v1/answer',json={'question':'Kiểm tra hiệu lực','query_date':'not-a-date'})
            self.assertEqual(invalid.status_code,422)
            unknown=client.post('/v1/answer',json={'question':'Kiểm tra hiệu lực','factz':{}})
            self.assertEqual(unknown.status_code,422)
            preflight=client.options('/v1/answer',headers={'Origin':'http://localhost:5173',
              'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
            self.assertEqual(preflight.status_code,200)
            self.assertEqual(preflight.headers.get('access-control-allow-origin'),'http://localhost:5173')

if __name__=='__main__': unittest.main()
