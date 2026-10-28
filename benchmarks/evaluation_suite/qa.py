"""Experimental interventions confined to this standalone evaluation process."""
from __future__ import annotations
import gc,json,time
from pathlib import Path
from common import jsonl,save,answer_summary,score_judge,redact
from gold import status_comparison

VARIANTS=('full','without_graph','without_reranker','without_auditor','without_review')

class DisabledAuditor:
    """Admit candidates experimentally, WITHOUT fabricating a PASS decision."""
    provider=None
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
    cfg.graph.enabled=name!='without_graph'
    cfg.reranker.enabled=name!='without_reranker'
    if name=='without_auditor':cfg.applicability.mode='deterministic'
    if name=='without_review':cfg.adjudication.semantic_review=False
    return cfg

def evaluate(run_dir,settings,vlsp=False):
    import sys
    from qa_worker import evaluate as execute
    return execute(sys.modules[__name__],run_dir,settings,vlsp)
