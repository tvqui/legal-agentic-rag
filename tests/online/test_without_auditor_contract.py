"""Synthetic source-only ablation contract; no live model or legal dataset."""
import json,sys,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'benchmarks/evaluation_suite'))
from qa import DisabledAuditor
from vn_labor_online.evidence import build_verified_pack
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_online.generation import LegalAdjudicator
from vn_labor_online.config import AdjudicationConfig
from vn_labor_online.models import Evidence,EvidenceState,VerifiedEvidencePack,ApplicabilityDecision

TEXT='Bên giao hồ sơ phải lập danh mục tài liệu trước khi bàn giao.'
class WithoutAuditorContractTests(unittest.TestCase):
    def source(self,uid='synthetic',verified=True):
        return Evidence(unit_id=uid,text=TEXT,source_text=TEXT,verified=verified,retrieval_method='bm25',
            document_number='TEST/2099',article_number='801',source_url='https://example.org/source',
            valid_from='2020-01-01',valid_to='2030-01-01')
    def pack(self,items=None):
        items=items or [self.source()];auditor=DisabledAuditor();accepted,decisions,_=auditor.audit(items)
        pipe=OnlinePipeline.__new__(OnlinePipeline);pipe.applicability=auditor
        return pipe._build_evidence_pack('Giải thích nghĩa vụ bàn giao hồ sơ.','2025-01-01',{},
            EvidenceState(slots={},gaps=[],coverage=1),accepted,decisions,'EXPLAIN')

    def test_experiment_keeps_sources_without_fabricating_applicability_pass(self):
        pack=self.pack();self.assertEqual(len(pack.evidence),1)
        item=pack.evidence[0]
        self.assertEqual(item.applicability.audit_status,'UNRESOLVED')
        self.assertFalse(item.applicability.supports_claim)
        self.assertIn('EXPERIMENT_APPLICABILITY_NOT_CHECKED',item.warnings)
        self.assertEqual(item.full_text,TEXT)
        self.assertEqual(item.official_url,'https://example.org/source')
        self.assertEqual(item.valid_from,'2020-01-01')

    def test_production_still_rejects_unresolved_decision(self):
        e=self.source();_,decisions,_=DisabledAuditor().audit([e])
        pipe=OnlinePipeline.__new__(OnlinePipeline);pipe.applicability=Mock()
        pack=pipe._build_evidence_pack('Question','2025-01-01',{},EvidenceState(slots={},gaps=[],coverage=1),[e],decisions)
        self.assertEqual(pack.evidence,[])

    def test_experiment_rejects_unverified_fail_foreign_or_missing_decision(self):
        for case in ('unverified','fail','foreign','missing','wrong_marker','fake_pass'):
            with self.subTest(case=case):
                item=self.source(verified=case!='unverified');_,decisions,_=DisabledAuditor().audit([item])
                if case=='fail':decisions[0]=decisions[0].model_copy(update={'audit_status':'FAIL'})
                if case=='foreign':decisions[0]=decisions[0].model_copy(update={'evidence_id':'other'})
                if case=='missing':decisions=[]
                if case=='wrong_marker':decisions[0]=decisions[0].model_copy(update={'reasons':[]})
                if case=='fake_pass':decisions[0]=decisions[0].model_copy(update={'audit_status':'PASS','supports_claim':True})
                pack=DisabledAuditor.build_evidence_pack('Question','2025-01-01',{},EvidenceState(slots={},gaps=[],coverage=1),[item],decisions)
                self.assertEqual(pack.evidence,[])

    def test_empty_pack_never_calls_drafter_or_reviewer(self):
        engine=LegalAdjudicator(AdjudicationConfig(mode='ollama'))
        engine.provider=Mock();engine._review_provider=Mock()
        pack=VerifiedEvidencePack(query='Giải thích nghĩa vụ.',evidence=[],coverage_state=EvidenceState(slots={},gaps=[],coverage=0))
        draft,warnings=engine.generate(pack,True)
        self.assertFalse(draft.claims);self.assertIn('ADJUDICATION_NO_ELIGIBLE_EVIDENCE',warnings)
        engine.provider.structured.assert_not_called();engine._review_provider.structured.assert_not_called()

    def test_five_source_only_smoke_cases_never_send_empty_citation_enum(self):
        for index in range(5):
            with self.subTest(index=index):
                pack=self.pack([self.source('synthetic_'+str(index))])
                engine=LegalAdjudicator(AdjudicationConfig(mode='ollama',semantic_review=False))
                provider=Mock(context_tokens=32768,max_output_tokens=6144,count_prompt_tokens=None)
                def respond(system,user,schema):
                    self.assertEqual(json.loads(user)['applicability_audit_status'],'NOT_CHECKED_EXPERIMENT')
                    ids=schema['$defs']['ProviderClaim']['properties']['evidence_ids']['items']['enum']
                    self.assertEqual(ids,[pack.evidence[0].evidence_id])
                    return {'claims':[{'text':TEXT,'evidence_ids':ids}]}
                provider.structured.side_effect=respond;engine.provider=provider
                draft,_=engine._generate(pack,True)
                self.assertTrue(draft.claims);self.assertEqual(provider.structured.call_count,1)

    def test_independent_review_still_accepts_or_blocks_each_experiment_draft(self):
        for supported in (True,False):
            with self.subTest(supported=supported):
                pack=self.pack();engine=LegalAdjudicator(AdjudicationConfig(mode='ollama',semantic_repair_attempts=0))
                engine.provider=Mock(context_tokens=32768,max_output_tokens=6144,count_prompt_tokens=None)
                engine.provider.structured.return_value={'claims':[{'text':TEXT,'evidence_ids':['synthetic']}]}
                reviewer=Mock(context_tokens=32768,max_output_tokens=6144,count_prompt_tokens=None)
                def respond(system,user,schema):
                    body=json.loads(user)
                    if 'draft_claims' in body:return {'claims':[{'text':TEXT,'evidence_ids':['synthetic']}]}
                    claims=body.get('claims',[])
                    return {'claims':[{'claim_id':c['claim_id'],'verdict':'SUPPORTED' if supported else 'UNSUPPORTED',
                        'grounding':[{'evidence_id':'synthetic','quote':TEXT}] if supported else [],'reason':'Synthetic verdict'} for c in claims],
                        'coverage':[{'task_id':t['task_id'],'status':'ANSWERED' if supported else 'MISSING',
                            'claim_ids':[c['claim_id'] for c in claims] if supported else [],'missing':'' if supported else 'No support'} for t in body.get('tasks',[])],
                        'question_fully_addressed':supported,'missing_requirements':[] if supported else ['governing_rule']}
                reviewer.structured.side_effect=respond;engine._review_provider=reviewer
                draft,warnings=engine.generate(pack,True)
                self.assertTrue(reviewer.structured.called)
                self.assertEqual(bool(draft.claims),supported)
                if supported:self.assertEqual(draft.semantic_review['status'],'PASS')

if __name__=='__main__':unittest.main()
