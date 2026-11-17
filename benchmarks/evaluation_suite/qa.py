"""Experimental interventions confined to this standalone evaluation process."""
from __future__ import annotations
import gc,json,time
from pathlib import Path
from common import jsonl,save,answer_summary,score_judge,redact
from gold import status_comparison

VARIANTS=('full','without_graph','without_reranker','without_auditor','without_review')

def _pack_without_applicability_audit(query,query_date,facts,state,items,decisions=None,requested_outcome='OTHER'):
    """Experimental source-only contract; never manufacture an applicability PASS."""
    from vn_labor_online.evidence import build_verified_pack
    by_id={d.evidence_id:d for d in decisions or []}
    # Source/date/authority checks still run upstream and x.verified is required.
    # Only the deliberately disabled auditor can opt in with its explicit marker.
    candidates=[e for e in items if e.verified and e.unit_id in by_id
        and by_id[e.unit_id].audit_status=='UNRESOLVED'
        and by_id[e.unit_id].relevant and not by_id[e.unit_id].supports_claim
        and 'EXPERIMENT_AUDITOR_DISABLED' in by_id[e.unit_id].reasons]
    pack=build_verified_pack(query,query_date,facts,state,candidates,None,requested_outcome)
    evidence=[item.model_copy(update={'applicability':by_id[item.evidence_id],
        'warnings':list(dict.fromkeys(item.warnings+['EXPERIMENT_APPLICABILITY_NOT_CHECKED']))}) for item in pack.evidence]
    return pack.model_copy(update={'evidence':evidence})

class DisabledAuditor:
    """Admit candidates experimentally, WITHOUT fabricating a PASS decision."""
    provider=None
    build_evidence_pack=staticmethod(_pack_without_applicability_audit)
    def audit(self,items,*args,**kwargs):
        from vn_labor_online.models import ApplicabilityDecision
        return list(items),[ApplicabilityDecision(evidence_id=e.unit_id,relevant=True,
          supports_claim=False,audit_status='UNRESOLVED',reasons=['EXPERIMENT_AUDITOR_DISABLED']) for e in items],['EXPERIMENT_AUDITOR_DISABLED']
    _deterministic=audit

def variant_config(base,name):
    if name not in VARIANTS:raise ValueError(name)
    cfg=base.model_copy(deep=True)
    # Otherwise easy exact/profile routes may skip the component being measured.
    cfg.retrieval.profile_fast_path=False;cfg.retrieval.exact_lookup=False
    # Production recovery can use the distinct reviewer provider to draft.
    # Disable it in every arm so removing review does not also change the
    # generation provider being compared in this isolated ablation.
    cfg.adjudication.recovery_budget_seconds=0
    cfg.graph.enabled=name!='without_graph'
    cfg.reranker.enabled=name!='without_reranker'
    if name=='without_auditor':cfg.applicability.mode='deterministic'
    if name=='without_review':cfg.adjudication.semantic_review=False
    return cfg

def evaluate(run_dir,settings,vlsp=False):
    import sys
    from qa_worker import evaluate as execute
    return execute(sys.modules[__name__],run_dir,settings,vlsp)
