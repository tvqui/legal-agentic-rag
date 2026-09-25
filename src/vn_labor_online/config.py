from __future__ import annotations
from pathlib import Path
import os
from typing import Literal
import yaml
from pydantic import BaseModel,ConfigDict,Field,field_validator

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid')

class RetrievalConfig(StrictModel):
    exact_lookup:bool=True; bm25_enabled:bool=True; bm25_top_k:int=Field(30,ge=1); dense_enabled:bool=True
    dense_top_k:int=Field(30,ge=1); issue_anchor_enabled:bool=True; issue_anchor_top_k:int=Field(20,ge=1)
    case_law_enabled:bool=True; case_law_top_k:int=Field(10,ge=1)
    community_enabled:bool=True; community_top_k:int=Field(3,ge=1,le=20)
    community_case_top_k:int=Field(10,ge=1,le=50)
    fusion_top_k:int=Field(30,ge=1); rrf_k:int=Field(60,ge=1)
    relevance_weight:float=Field(.75,ge=0); authority_weight:float=Field(.2,ge=0); temporal_weight:float=Field(.05,ge=0)

class RerankerConfig(StrictModel):
    enabled:bool=False; model:str='BAAI/bge-reranker-v2-m3'; model_path:str|None=None
    device:str='auto'; use_fp16:bool=True; top_n:int=Field(30,ge=1,le=100)

class GraphConfig(StrictModel):
    enabled:bool=True; mode:Literal['adaptive','fixed']='adaptive'
    max_rounds:int=Field(4,ge=0); max_nodes:int=Field(50,ge=1); max_edges:int=Field(100,ge=0); max_hops:int=Field(3,ge=0)
    wall_clock_ms:int=Field(1500,ge=1); hub_penalty:float=Field(.15,ge=0)
    relevance_weight:float=Field(.3,ge=0); authority_weight:float=Field(.15,ge=0); temporal_weight:float=Field(.1,ge=0)
    gap_weight:float=Field(.5,ge=0); novelty_weight:float=Field(.1,ge=0); redundancy_weight:float=Field(.1,ge=0); traversal_cost_weight:float=Field(.05,ge=0)
    edge_weights:dict[str,float]=Field(default_factory=lambda:{'AMENDS':1,'REPEALS':1,'REPLACES':1,'IMPLEMENTS':.9,'REFERENCES':.85,'PART_OF':.5,'NEXT':.3,'VERSION_OF':.7,'CITES':.5,'HAS_ISSUE':.4,'RELATES_TO_ISSUE':.4,'SIMILAR_TO':.1,'BELONGS_TO':.1})
    @field_validator('edge_weights')
    @classmethod
    def validate_edge_weights(cls,value):
        if any(not key or weight<0 for key,weight in value.items()):
            raise ValueError('edge_weights require non-empty relation names and non-negative values')
        return value

class ResearcherConfig(StrictModel):
    mode:Literal['deterministic','ollama','http']='deterministic'
    url:str|None=None; model:str|None=None; api_key:str|None=None; health_url:str|None=None
    timeout_seconds:float=120; max_queries:int=Field(2,ge=0,le=4)

class ApplicabilityConfig(StrictModel):
    mode:Literal['deterministic','ollama','http','hybrid']='deterministic'; fail_closed:bool=True
    provider:Literal['ollama','http']='ollama'
    url:str|None=None; model:str|None=None; api_key:str|None=None; health_url:str|None=None
    timeout_seconds:float=120; max_items:int=Field(10,ge=1,le=30)

class AdjudicationConfig(StrictModel):
    mode:Literal['deterministic','ollama','http']='deterministic'; fail_closed:bool=True
    url:str|None=None; model:str|None=None; api_key:str|None=None; health_url:str|None=None; timeout_seconds:float=120

class OnlineConfig(StrictModel):
    artifact_source:str=Field(min_length=1); cache_dir:str='.cache/online'; expected_build_id:str|None=None
    expected_archive_sha256:str|None=None; expected_retrieval_unit_fingerprint:str|None=None
    expected_dense_fingerprint:str|None=None; provisional_mode:bool=True
    retrieval:RetrievalConfig=Field(default_factory=RetrievalConfig)
    reranker:RerankerConfig=Field(default_factory=RerankerConfig)
    graph:GraphConfig=Field(default_factory=GraphConfig)
    researcher:ResearcherConfig=Field(default_factory=ResearcherConfig)
    applicability:ApplicabilityConfig=Field(default_factory=ApplicabilityConfig)
    adjudication:AdjudicationConfig=Field(default_factory=AdjudicationConfig)
    max_verified_units:int=Field(12,ge=1); minimum_coverage:float=Field(.5,ge=0,le=1); allow_partial:bool=True; trace_dir:str='artifacts/online_traces'
    allow_document_temporal_fallback:bool=True
    corpus_snapshot_as_of:str|None=None
    embedding_model:str='BAAI/bge-m3'; embedding_model_path:str|None=None
    embedding_device:str='auto'; embedding_use_fp16:bool=True
    @field_validator('corpus_snapshot_as_of')
    @classmethod
    def validate_snapshot_date(cls,value):
        if value is None: return value
        from datetime import date
        try: return date.fromisoformat(value).isoformat()
        except (TypeError,ValueError) as exc: raise ValueError('corpus_snapshot_as_of must use YYYY-MM-DD') from exc

def load_config(path:Path)->OnlineConfig:
    raw=yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    values=dict(raw.get('online',raw))
    if os.getenv('VN_LABOR_ARTIFACT_SOURCE'): values['artifact_source']=os.environ['VN_LABOR_ARTIFACT_SOURCE']
    if os.getenv('VN_LABOR_ONLINE_CACHE'): values['cache_dir']=os.environ['VN_LABOR_ONLINE_CACHE']
    sections=(('researcher','VN_LABOR_RESEARCHER'),('applicability','VN_LABOR_APPLICABILITY'),('adjudication','VN_LABOR_ADJUDICATION'))
    for section,prefix in sections:
        configured=dict(values.get(section) or {})
        for key in ('mode','provider','url','model','api_key','health_url'):
            env_key=f'{prefix}_{key.upper()}'
            if os.getenv(env_key): configured[key]=os.environ[env_key]
        for key in ('timeout_seconds','max_queries','max_items'):
            env_key=f'{prefix}_{key.upper()}'
            if os.getenv(env_key): configured[key]=float(os.environ[env_key]) if key=='timeout_seconds' else int(os.environ[env_key])
        if configured: values[section]=configured
    return OnlineConfig.model_validate(values)
