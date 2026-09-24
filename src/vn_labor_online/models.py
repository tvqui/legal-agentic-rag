from __future__ import annotations
from datetime import date,datetime,timezone
import re
from enum import Enum
from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator

class Route(str,Enum): DIRECT="DIRECT"; STANDARD="STANDARD"; COMPLEX="COMPLEX"
class Stop(str,Enum): SUFFICIENT="SUFFICIENT"; PARTIAL_ALLOWED="PARTIAL_ALLOWED"; NEED_MORE_FACTS="NEED_MORE_FACTS"; INSUFFICIENT_EVIDENCE="INSUFFICIENT_EVIDENCE"; CONFLICTING_EVIDENCE="CONFLICTING_EVIDENCE"; ERROR="ERROR"
class SlotStatus(str,Enum): MISSING="MISSING"; CANDIDATE="CANDIDATE"; FOUND="FOUND"; FOUND_VERIFIED="FOUND_VERIFIED"; CONFLICT="CONFLICT"; UNRESOLVED="UNRESOLVED"; NOT_APPLICABLE="NOT_APPLICABLE"
class ExplicitReference(BaseModel):
    instrument_number:str|None=None; article:str|None=None; clause:str|None=None; point:str|None=None
class QueryRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question:str=Field(min_length=2,max_length=10000); query_date:str|None=None
    conversation_context:list[str]=Field(default_factory=list,max_length=20)
    facts:dict[str,Any]=Field(default_factory=dict)
    @field_validator('conversation_context')
    @classmethod
    def validate_context(cls,value):
        if any(len(turn)>10000 for turn in value): raise ValueError('each conversation turn must be at most 10000 characters')
        return value
    @field_validator('facts')
    @classmethod
    def validate_facts(cls,value):
        import json
        if len(json.dumps(value,ensure_ascii=False,default=str))>50000: raise ValueError('facts payload is too large')
        reserved={'human_reviewed','bypass_fact_gate','conditions_satisfied','exception_triggered',
          'audit_status','review_status','official_source','authority_verified'}
        forbidden=reserved&set(value)
        if forbidden: raise ValueError('facts contains reserved decision fields: '+', '.join(sorted(forbidden)))
        return value
    @field_validator('query_date')
    @classmethod
    def validate_query_date(cls,value):
        if value is None: return value
        try:
            if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value): raise ValueError
            return date.fromisoformat(value).isoformat()
        except (TypeError,ValueError) as exc: raise ValueError('query_date must use YYYY-MM-DD') from exc
class QueryEnvelope(BaseModel):
    query_id:str; raw_query:str; normalized_query:str; conversation_context:list[str]=Field(default_factory=list)
    received_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
class QueryAnalysis(BaseModel):
    legal_issues:list[str]; facts:dict[str,Any]; explicit_references:list[ExplicitReference]
    event_dates:list[str]; query_date:str|None; query_date_end:str|None=None
    requested_outcome:Literal["LOOKUP","EXPLAIN","ASSESS_LEGALITY","COMPARE","FIND_CASE","OTHER"]
    temporal_intent:Literal["CURRENT","HISTORICAL","EXPLICIT_DATE","NONE"]; missing_facts:list[str]
    route:Route; route_reason:str; query_date_precision:Literal["DAY","MONTH","YEAR","NONE"]="NONE"
class EvidencePlan(BaseModel):
    mandatory_slots:list[str]; conditional_slots:list[str]=Field(default_factory=list)
class Evidence(BaseModel):
    unit_id:str; score:float=0; retrieval_method:str; rank:int=0; component_scores:dict[str,float]=Field(default_factory=dict)
    document_id:str|None=None; instrument_id:str|None=None; provision_identity_id:str|None=None
    provision_version_id:str|None=None; document_number:str|None=None; document_title:str|None=None
    article_number:str|None=None; clause_number:str|None=None; point_number:str|None=None
    source_url:str|None=None; breadcrumb:str|None=None; text:str; source_text:str|None=None
    valid_from:str|None=None; valid_to:str|None=None; authority_rank:int=0; binding:bool=False
    temporal_verified:bool=False; provision_temporal_verified:bool=False; provenance:dict[str,Any]=Field(default_factory=dict)
    provenance_span:dict[str,Any]=Field(default_factory=dict); kind:str|None=None; level:str|None=None
    issuer:str|None=None; official_source:bool=False; source_catalog_status:str|None=None
    graph_path:list[str]=Field(default_factory=list); graph_relations:list[str]=Field(default_factory=list)
    graph_directions:list[str]=Field(default_factory=list); authority_verified:bool=False; verified:bool=False
    audit_issues:list[str]=Field(default_factory=list); audit_warnings:list[str]=Field(default_factory=list)
class EvidenceSlot(BaseModel): status:SlotStatus; evidence_ids:list[str]=Field(default_factory=list)
class EvidenceState(BaseModel):
    slots:dict[str,EvidenceSlot]; gaps:list[str]; coverage:float
    mandatory_slots:list[str]=Field(default_factory=list); conditional_slots:list[str]=Field(default_factory=list)
class ApplicableLawVersion(BaseModel):
    model_config=ConfigDict(extra='forbid')
    instrument_number:str|None=None; valid_from:str|None=None; valid_to:str|None=None
    temporal_status:Literal["PROVISION_VERIFIED","DOCUMENT_LEVEL_FALLBACK","NOT_CHECKED"]="NOT_CHECKED"
class Citation(BaseModel):
    evidence_id:str; title:str|None=None; document_number:str|None=None; article:str|None=None
    clause:str|None=None; point:str|None=None; law_version:str|None=None; official_url:str|None=None
    instrument_number:str|None=None; source_span:dict[str,Any]=Field(default_factory=dict)
class Claim(BaseModel):
    model_config=ConfigDict(extra='forbid')
    claim_id:str; text:str; evidence_ids:list[str]=Field(min_length=1)
class ApplicabilityDecision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    evidence_id:str; relevant:bool; supports_claim:bool
    conditions_status:Literal["SATISFIED","NOT_SATISFIED","UNKNOWN","NOT_APPLICABLE"]="UNKNOWN"
    exception_status:Literal["TRIGGERED","NOT_TRIGGERED","UNKNOWN","NOT_APPLICABLE"]="UNKNOWN"
    audit_status:Literal["PASS","FAIL","UNRESOLVED"]; reasons:list[str]=Field(default_factory=list)
class VerifiedEvidenceItem(BaseModel):
    evidence_id:str; instrument_number:str|None=None; article:str|None=None; clause:str|None=None
    point:str|None=None; text:str; valid_from:str|None=None; valid_to:str|None=None
    official_url:str|None=None; authority_rank:int=0; binding:bool=False; official_source:bool=False
    provenance_span:dict[str,Any]=Field(default_factory=dict)
    applicability:ApplicabilityDecision|None=None
    audit_status:Literal["PASS"]="PASS"; warnings:list[str]=Field(default_factory=list)
class VerifiedEvidencePack(BaseModel):
    query:str; query_date:str|None=None; facts:dict[str,Any]=Field(default_factory=dict)
    requested_outcome:Literal["LOOKUP","EXPLAIN","ASSESS_LEGALITY","COMPARE","FIND_CASE","OTHER"]="OTHER"
    coverage_state:EvidenceState; evidence:list[VerifiedEvidenceItem]
class AdjudicationDraft(BaseModel):
    model_config=ConfigDict(extra='forbid')
    answer_summary:str; claims:list[Claim]; applicable_law_versions:list[ApplicableLawVersion]
    assumptions:list[str]=Field(default_factory=list); limitations:list[str]=Field(default_factory=list)
class Trace(BaseModel):
    trace_id:str; query_id:str; build_id:str; route:Route; route_reason:str; retrieval_rounds:int=0
    nodes_visited:int=0; edges_visited:int=0; timings_ms:dict[str,float]=Field(default_factory=dict); events:list[dict[str,Any]]=Field(default_factory=list)
    seed_results:int=0; critical_edges_followed:list[str]=Field(default_factory=list)
    evidence_gaps:list[dict[str,Any]]=Field(default_factory=list); stop_reason:str|None=None
    verified_evidence_count:int=0; reference_audit:str="NOT_RUN"
    config_fingerprint:str|None=None; budget_stop_reason:str|None=None
    retrieval_candidates:list[dict[str,Any]]=Field(default_factory=list)
    graph_round_details:list[dict[str,Any]]=Field(default_factory=list)
class AnswerResponse(BaseModel):
    query_id:str; status:Stop; answer:str; citations:list[Citation]=Field(default_factory=list); evidence_status:str
    applicable_date:str|None=None; query_date:str|None=None
    applicable_law_versions:list[ApplicableLawVersion]=Field(default_factory=list)
    claims:list[Claim]=Field(default_factory=list); assumptions:list[str]=Field(default_factory=list)
    limitations:list[str]=Field(default_factory=list); questions:list[str]=Field(default_factory=list); warnings:list[str]=Field(default_factory=list)
    facts:dict[str,Any]=Field(default_factory=dict)
    build_id:str; trace_id:str; trace:Trace
class CompatibilityReport(BaseModel):
    compatible:bool; build_id:str|None=None; graph_fingerprint:str|None=None
    retrieval_unit_fingerprint:str|None=None; dense_fingerprint:str|None=None
    gold_build_id:str|None=None; issues:list[str]=Field(default_factory=list); provisional_reasons:list[str]=Field(default_factory=list)
    source_catalog_records:int=0; corpus_snapshot_as_of:str|None=None
