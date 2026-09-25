from __future__ import annotations
import hashlib,json,os
from pathlib import Path
from vn_labor_online.providers import HttpJsonProvider,OllamaProvider

PROMPT_VERSION='labor-offline-ai-v1'

def provider_from_config(cfg):
    settings=cfg.get('knowledge',{})
    kind=os.getenv('VN_LABOR_OFFLINE_AI_PROVIDER',settings.get('ai_provider','ollama')).lower()
    url=os.getenv('VN_LABOR_OFFLINE_AI_URL',settings.get('ai_url') or ('http://127.0.0.1:11434/api/chat' if kind=='ollama' else 'https://api.openai.com/v1/chat/completions'))
    model=os.getenv('VN_LABOR_OFFLINE_AI_MODEL',settings.get('ai_model','qwen3:8b'))
    timeout=float(os.getenv('VN_LABOR_OFFLINE_AI_TIMEOUT_SECONDS',settings.get('ai_timeout_seconds',300)))
    if kind=='ollama': return OllamaProvider(url,model,timeout,settings.get('ai_health_url'))
    if kind=='http':
        key=os.getenv('VN_LABOR_OFFLINE_AI_API_KEY')
        if not key: raise RuntimeError('VN_LABOR_OFFLINE_AI_API_KEY is required for HTTP enrichment')
        return HttpJsonProvider(url,model,key,timeout,settings.get('ai_health_url'))
    raise ValueError('ai_provider must be ollama or http')

def cached_structured(provider,system,payload,schema,cache_dir:Path,identity:str):
    serialized=json.dumps({'version':PROMPT_VERSION,'identity':identity,'payload':payload,'schema':schema,
      'provider':type(provider).__name__,'model':getattr(provider,'model',None)},ensure_ascii=False,sort_keys=True)
    key=hashlib.sha256(serialized.encode()).hexdigest(); path=cache_dir/(key+'.json')
    if path.exists(): return json.loads(path.read_text(encoding='utf-8'))
    value=provider.structured(system,json.dumps(payload,ensure_ascii=False),schema)
    path.parent.mkdir(parents=True,exist_ok=True); temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True),encoding='utf-8'); os.replace(temporary,path)
    return value

def cache_dir(cfg):
    value=cfg.get('knowledge',{}).get('ai_cache_dir','.cache/offline_ai')
    path=Path(value)
    return path if path.is_absolute() else cfg['project_root']/path
