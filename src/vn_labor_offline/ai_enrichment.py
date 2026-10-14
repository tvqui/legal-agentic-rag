from __future__ import annotations
from datetime import datetime, timezone
import hashlib,json,os,time
from pathlib import Path
from vn_labor_online.providers import HttpJsonProvider,OllamaProvider

PROMPT_VERSION='labor-offline-ai-v2-context'

def provider_from_config(cfg):
    settings=cfg.get('knowledge',{})
    kind=os.getenv('VN_LABOR_OFFLINE_AI_PROVIDER',settings.get('ai_provider','ollama')).lower()
    url=os.getenv('VN_LABOR_OFFLINE_AI_URL',settings.get('ai_url') or ('http://127.0.0.1:11434/api/chat' if kind=='ollama' else 'https://api.openai.com/v1/chat/completions'))
    model=os.getenv('VN_LABOR_OFFLINE_AI_MODEL',settings.get('ai_model','qwen3:8b'))
    timeout=float(os.getenv('VN_LABOR_OFFLINE_AI_TIMEOUT_SECONDS',settings.get('ai_timeout_seconds',300)))
    if kind=='ollama': return OllamaProvider(url,model,timeout,settings.get('ai_health_url'),
        int(settings.get('ai_max_output_tokens',2048)),int(settings.get('ai_context_tokens',16384)))
    if kind=='http':
        key=os.getenv('VN_LABOR_OFFLINE_AI_API_KEY')
        if not key: raise RuntimeError('VN_LABOR_OFFLINE_AI_API_KEY is required for HTTP enrichment')
        return HttpJsonProvider(url,model,key,timeout,settings.get('ai_health_url'))
    raise ValueError('ai_provider must be ollama or http')

def structured_cache_key(provider,system,payload,schema,identity):
    serialized=json.dumps({'version':PROMPT_VERSION,'identity':identity,'payload':payload,'schema':schema,
      'system':system,'provider':type(provider).__name__,'model':getattr(provider,'model',None)},ensure_ascii=False,sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def cached_structured(provider,system,payload,schema,cache_dir:Path,identity:str,observer=None):
    key=structured_cache_key(provider,system,payload,schema,identity); path=cache_dir/(key+'.json')
    if path.exists():
        try:
            value=json.loads(path.read_text(encoding='utf-8'))
            validate_structured(value,schema)
            if observer: observer('cache_hit',cache_path=path,cache_key=key,identity=identity)
            return value
        except (OSError,ValueError,TypeError): pass
    started=time.monotonic()
    details={'cache_key':key,'identity':identity,'input_bytes':len(json.dumps(payload,ensure_ascii=False).encode('utf-8'))}
    try:
        if observer: observer('before',cache_path=path,**details)
        value=provider.structured(system,json.dumps(payload,ensure_ascii=False),schema)
        validate_structured(value,schema)
    except Exception as exc:
        if observer:
            from .ai_requests import error_details
            observer('error',elapsed_seconds=round(time.monotonic()-started,3),**details,**error_details(exc))
        raise
    if observer: observer('success',elapsed_seconds=round(time.monotonic()-started,3),**details)
    path.parent.mkdir(parents=True,exist_ok=True); temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True),encoding='utf-8'); os.replace(temporary,path)
    return value

def validate_structured(value,schema):
    typ=schema.get('type')
    if typ=='object':
        if not isinstance(value,dict): raise ValueError('AI_SCHEMA_OBJECT')
        if not set(schema.get('required',[]))<=set(value): raise ValueError('AI_SCHEMA_REQUIRED')
        props=schema.get('properties',{})
        if schema.get('additionalProperties') is False and set(value)-set(props): raise ValueError('AI_SCHEMA_EXTRA')
        for k,v in value.items():
            if k in props: validate_structured(v,props[k])
    elif typ=='array':
        if not isinstance(value,list): raise ValueError('AI_SCHEMA_ARRAY')
        if len(value)>min(100,schema.get('maxItems',100)): raise ValueError('AI_SCHEMA_ARRAY_LIMIT')
        for item in value: validate_structured(item,schema.get('items',{}))
    elif typ=='string':
        if not isinstance(value,str): raise ValueError('AI_SCHEMA_STRING')
        if len(value)>schema.get('maxLength',len(value)): raise ValueError('AI_SCHEMA_STRING_LIMIT')
        if len(value)<schema.get('minLength',0): raise ValueError('AI_SCHEMA_STRING_MINIMUM')
    if 'enum' in schema and value not in schema['enum']: raise ValueError('AI_SCHEMA_ENUM')

def cache_dir(cfg):
    value=cfg.get('knowledge',{}).get('ai_cache_dir','artifacts/04_knowledge/ai_cache')
    path=Path(value)
    return path if path.is_absolute() else cfg['project_root']/path

def report_ai_progress(output_dir:Path,stage:str,completed:int,total:int,**details):
    """Persist a small, atomic heartbeat that the Kaggle parent can monitor."""
    payload={
      'schema_version':1,'stage':stage,'completed':int(completed),'total':int(total),
      'updated_at':datetime.now(timezone.utc).isoformat(),**details,
    }
    path=Path(output_dir)/'reports/offline_ai_progress.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True),encoding='utf-8')
    os.replace(temporary,path)
    print('AI_PROGRESS '+json.dumps(payload,ensure_ascii=False,sort_keys=True),flush=True)
    return payload
