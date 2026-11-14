"""Frozen, paired adaptive-expansion protocol. No production changes or answer patches."""
from __future__ import annotations
import hashlib, json, os, platform, random, sys, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
DEFAULTS=dict(device='cuda:0', cache='.cache/graph_qa', llm_model='qwen3:8b',
 ollama_url='http://127.0.0.1:11434/api/chat',review_model='gemini-3.1-flash-lite',
 semantic_review=True, request_timeout_seconds=180,provider_timeout_seconds=45,
 repetitions=1,seed=42,k=10,reranker_revision='953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e',
 judge_enabled=False,judge_model='gemini-3.1-flash-lite',judge_timeout_seconds=60)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def consumed_artifact_hashes(root):
    root=Path(root)
    paths=list((root/'06_indexes').rglob('*'))
    paths += [root/name for name in ('05_graph/nodes.jsonl','05_graph/edges.jsonl',
        '00_manifest/source_catalog_resolved.jsonl','reports/final_outputs_validation.json',
        'reports/dense_validation.json','reports/neo4j_validation.json')]
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(set(paths)) if p.is_file()}

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def fingerprint(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def rows(path):return [json.loads(x) for x in Path(path).read_text(encoding='utf-8-sig').splitlines() if x.strip()] if Path(path).exists() else []
def write(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');os.replace(tmp,path)
def append(path,value):
    with Path(path).open('a',encoding='utf-8') as f:f.write(canonical(value)+'\n');f.flush();os.fsync(f.fileno())

def settings(path):
    s=load(path)
    if set(s)-set(DEFAULTS):raise ValueError('Unknown settings: '+str(sorted(set(s)-set(DEFAULTS))))
    s={**DEFAULTS,**s}
    for field in ('seed','k','repetitions'):
        if type(s[field]) is not int or s[field]<0 or (field!='seed' and s[field]<1):raise ValueError('Invalid '+field)
    for field in ('request_timeout_seconds','provider_timeout_seconds','judge_timeout_seconds'):
        if type(s[field]) not in (int,float) or not 10<=s[field]<=(1800 if field=='request_timeout_seconds' else 180):raise ValueError('Invalid timeout')
    for field in ('semantic_review','judge_enabled'):
        if type(s[field]) is not bool:raise ValueError('Invalid boolean')
    if s['judge_enabled']:raise ValueError('Judge runs separately AFTER generation; set judge_enabled=false')
    import re
    if not re.fullmatch(r'[a-f0-9]{40}',s['reranker_revision']):raise ValueError('Reranker revision must be a commit SHA')
    from urllib.parse import urlsplit
    url=urlsplit(s['ollama_url'])
    if url.hostname not in ('localhost','127.0.0.1') or url.username or url.password or url.scheme!='http':raise ValueError('Use local Ollama URL only')
    return s

def code_hashes():
    paths=list((REPO/'src').rglob('*.py'))+list(HERE.glob('*.py'))+[HERE/'questions.jsonl',REPO/'pyproject.toml']
    return {p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths) if p.is_file()}

def verify_dataset(run):
    manifest=load(run/'manifest.json')
    if manifest.get('spec_sha256') and manifest['spec_sha256']!=sha(HERE/'questions.jsonl'):raise ValueError('Question specification changed after freeze')
    for name,expected in manifest['outputs_sha256'].items():
        if Path(name).name!=name or sha(run/name)!=expected:raise ValueError('Frozen dataset changed: '+name)
    return manifest

def schedule(inference,s,profile):
    if profile not in ('smoke','standard'):raise ValueError('Unknown profile')
    selected=inference if profile=='standard' else inference[::6]
    selected=list(selected);random.Random(s['seed']).shuffle(selected)
    jobs=[]
    for rep in range(1,s['repetitions']+1):
        for i,q in enumerate(selected):
            arms=('graph_off','graph_on') if (i+rep)%2 else ('graph_on','graph_off')
            jobs.extend(dict(id=q['id'],arm=a,repeat=rep,question=q['question'],query_date=q['query_date']) for a in arms)
    return jobs

def config(s,artifact,enabled):
    from vn_labor_online.config import OnlineConfig
    # Construct explicitly: role overrides from unrelated notebook cells must NOT change arms.
    cfg=OnlineConfig(artifact_source=str(artifact),cache_dir=s['cache'],request_timeout_seconds=s['request_timeout_seconds'],
        provisional_mode=True,corpus_snapshot_as_of='2026-09-15',max_verified_units=32,trace_dir=str(Path(s['cache'])/'traces'),
        embedding_device=s['device'])
    # Keep shared production shortcuts/channels: removing alternatives could exaggerate Graph benefit.
    cfg.retrieval.request_cache_enabled=False
    cfg.retrieval.graph_reference_selection=False
    cfg.reranker.enabled=True;cfg.reranker.device=s['device']
    cfg.graph.enabled=enabled;cfg.graph.mode='adaptive';cfg.graph.max_rounds=4;cfg.graph.max_hops=3
    cfg.graph.max_nodes=60;cfg.graph.max_edges=180;cfg.graph.wall_clock_ms=10000
    for role in (cfg.researcher,cfg.applicability,cfg.adjudication):
        role.mode='ollama';role.url=s['ollama_url'];role.model=s['llm_model'];role.timeout_seconds=s['provider_timeout_seconds']
    # Scale component budgets only when the experiment explicitly selects a larger allowance.
    # Legacy 180s/45s settings retain exactly their original budgets. Both arms share these values.
    cfg.applicability.budget_seconds=max(90,min(s['request_timeout_seconds']/2,2*s['provider_timeout_seconds']))
    cfg.applicability.reserve_seconds=max(60,min(120,s['request_timeout_seconds']/3))
    cfg.applicability.call_timeout_seconds=s['provider_timeout_seconds']
    cfg.adjudication.primary_budget_seconds=max(45,s['provider_timeout_seconds'])
    cfg.adjudication.review_reserve_seconds=max(45,min(60,s['provider_timeout_seconds']))
    cfg.adjudication.semantic_review=s['semantic_review'];cfg.adjudication.review_provider='gemini' if s['semantic_review'] else 'same'
    cfg.adjudication.review_model=s['review_model'];cfg.adjudication.review_timeout_seconds=s['provider_timeout_seconds']
    return OnlineConfig.model_validate(cfg.model_dump())

def assert_pair(s,artifact):
    off=config(s,artifact,False).model_dump();on=config(s,artifact,True).model_dump()
    off['graph']['enabled']=True
    if off!=on:raise ValueError('Arm configurations differ outside graph.enabled')
    return {'graph_off':config(s,artifact,False).model_dump(),'graph_on':on}

def safe_error(exc):
    code=getattr(exc,'safe_code',None) or getattr(exc,'error_code',None) or getattr(exc,'reason',None)
    import re
    return {'type':type(exc).__name__,'code':code if isinstance(code,str) and (re.fullmatch(r'(GEMINI|OLLAMA|LLM|INDEX|ARTIFACT)_[A-Z0-9_]{1,60}',code) or code in {'REQUEST_DEADLINE_EXCEEDED','COMPONENT_TIME_BUDGET_EXHAUSTED','GEMINI_MINIMUM_DEADLINE_BUDGET'}) else 'LOCAL_ERROR'}

def environment():
    import importlib.metadata
    result={'python':sys.version,'platform':platform.platform(),'packages':{},
        'all_distributions':{d.metadata['Name']:d.version for d in importlib.metadata.distributions() if d.metadata.get('Name')}}
    for p in ('torch','transformers','FlagEmbedding','faiss-cpu','bm25s','google-genai','pydantic','numpy'):
        try:result['packages'][p]=importlib.metadata.version(p)
        except importlib.metadata.PackageNotFoundError:result['packages'][p]=None
    try:
        import subprocess
        gpu=subprocess.check_output(['nvidia-smi','--query-gpu=name,uuid,memory.total,driver_version','--format=csv,noheader'],text=True,timeout=10).strip().splitlines()
        result['gpus']=gpu
    except Exception:result['gpus']=[]
    try:
        import torch
        result['torch_cuda']=torch.version.cuda;result['cudnn']=torch.backends.cudnn.version()
    except ImportError:result['torch_cuda']=None
    return result

class Lock:
    def __init__(self,run):self.path=Path(run)/'.controller.lock'
    def __enter__(self):
        self.fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(self.fd,str(os.getpid()).encode());return self
    def __exit__(self,*args):os.close(self.fd);self.path.unlink()
