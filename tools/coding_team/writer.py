"""Stateless coding writer providers; never applies code or invokes model tools."""
from __future__ import annotations
from contextlib import nullcontext
import hashlib
import json
import math
import os
from types import SimpleNamespace

GROQ_MODEL = 'qwen/qwen3.8-27b'
FALLBACK_MODEL = 'gemini-3.5-flash'
NEW_MODELS = {GROQ_MODEL, FALLBACK_MODEL}
GROQ_ENDPOINT = 'https://api.groq.com/openai/v1/chat/completions'
FALLBACK_HTTP = {400,401,403,404,408,500,502,503,504}
JSON_INSTRUCTION = 'Return only a valid JSON object. No Markdown fences, NaN, duplicate keys or commentary outside JSON.'

class WriterFailure(RuntimeError):
    def __init__(self, reason, code=None):
        super().__init__(reason)
        self.reason=reason
        self.code=code

def load_tool_env(path):
    """Read only the user-authorized helper .env; never application settings."""
    if not path.is_file():return
    allowed={'CODING_TEAM_GOOGLE_API_KEY','CODING_TEAM_GROQ_API_KEY','GROQ_API_KEY'}
    found={}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        if line.startswith('export '):line=line[7:].lstrip()
        name, sep, value=line.partition('=')
        name=name.strip()
        if not sep or name not in allowed:continue
        if name in found:raise ValueError('Duplicate helper credential setting; values suppressed')
        value=value.strip()
        if value.startswith(('"',"'")):
            if len(value)<2 or value[-1]!=value[0]:raise ValueError('Invalid helper credential quoting; values suppressed')
            value=value[1:-1]
        elif ' #' in value:value=value.split(' #',1)[0].rstrip()
        if value:found[name]=value
    for name,value in found.items():
        if not os.environ.get(name):os.environ[name]=value


def route_for(model, output_format='text', fallback=True):
    if model not in NEW_MODELS or output_format not in {'text','json'}:
        raise ValueError('Invalid coding writer configuration')
    return {'version':1,'primary':model,
            'fallback':FALLBACK_MODEL if fallback and model==GROQ_MODEL else None,
            'format':output_format}

def route_hash(route):
    return hashlib.sha256(json.dumps(route,sort_keys=True).encode()).hexdigest()

def validate_route(route, model):
    if not isinstance(route,dict) or set(route)!={'version','primary','fallback','format'}:
        raise ValueError('Writer route missing or changed')
    if route!=route_for(model,route.get('format'),route.get('fallback') is not None):
        raise ValueError('Invalid pinned writer route')

def request_context(route, context, probe=False):
    if probe and route['format']=='json':
        return 'Connectivity check. Reply only with the JSON object {"ok":true}. Do not execute code or use tools.'
    return context


def groq_key():
    return os.environ.get('CODING_TEAM_GROQ_API_KEY') or os.environ.get('GROQ_API_KEY')

def no_duplicates(pairs):
    obj={}
    for k,v in pairs:
        if k in obj:raise ValueError('Duplicate JSON key')
        obj[k]=v
    return obj

def finite_float(value):
    result=float(value)
    if not math.isfinite(result):raise ValueError('Non-finite JSON number')
    return result


def validate_output(text, output_format, reject_secrets):
    if not isinstance(text,str) or not text.strip() or len(text.encode('utf8'))>64000:
        raise WriterFailure('INVALID_OUTPUT')
    reject_secrets(text)
    obj=None
    if output_format=='json':
        try:
            obj=json.loads(text,object_pairs_hook=no_duplicates,parse_float=finite_float,
                parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Non-finite JSON')))
        except (ValueError,TypeError,RecursionError):
            raise WriterFailure('INVALID_JSON') from None
        if not isinstance(obj,dict):raise WriterFailure('JSON_OBJECT_REQUIRED')
    return {'format':output_format,'valid':True,'json_object':isinstance(obj,dict),
            'utf8_bytes':len(text.encode('utf8')),'semantic_correctness':'NOT_VERIFIED'}

def groq_generate(context, system, output_format, timeout, probe):
    key=groq_key()
    if not key:raise WriterFailure('MISSING_GROQ_CREDENTIAL')
    import httpx
    payload={'model':GROQ_MODEL,'messages':[{'role':'system','content':system},
        {'role':'user','content':context}], 'temperature':0.2,
        'max_completion_tokens':512 if probe else 4096,
        'reasoning_effort':'none','reasoning_format':'hidden'}
    if output_format=='json':payload['response_format']={'type':'json_object'}
    with httpx.Client(timeout=httpx.Timeout(timeout,connect=min(timeout,10)),follow_redirects=False) as client:
        response=client.post(GROQ_ENDPOINT,headers={'Authorization':'Bearer '+key},json=payload)
    if response.status_code!=200:
        reason='GROQ_HTTP_ERROR'
        try:
            code=response.json().get('error',{}).get('code')
            reason={'json_validate_failed':'GROQ_JSON_VALIDATION_FAILED','model_not_found':'GROQ_MODEL_UNAVAILABLE','invalid_api_key':'GROQ_KEY_REJECTED'}.get(code,reason) if isinstance(code,str) else reason
        except (ValueError,AttributeError,TypeError):pass
        raise WriterFailure(reason,response.status_code)
    try:
        if len(response.content)>1000000:raise ValueError('Oversize response')
        data=response.json();choice=data['choices'][0]
        if choice.get('finish_reason')!='stop' or choice['message'].get('tool_calls'):
            raise ValueError('Truncated or unsupported tool response')
        text=choice['message']['content']
        if not isinstance(text,str):raise ValueError('Nontext completion')
    except (KeyError,IndexError,TypeError,ValueError):
        raise WriterFailure('INVALID_GROQ_RESPONSE') from None
    usage=data.get('usage',{})
    return SimpleNamespace(text=text,candidates=[],usage_metadata=SimpleNamespace(
        prompt_token_count=usage.get('prompt_tokens'),candidates_token_count=usage.get('completion_tokens'),
        total_token_count=usage.get('total_tokens')))

def google_generate(context, system, output_format, timeout, probe, client=None):
    from google import genai
    from google.genai import types
    key=os.environ.get('CODING_TEAM_GOOGLE_API_KEY')
    if client is None and not key:raise WriterFailure('MISSING_GOOGLE_CREDENTIAL')
    manager=nullcontext(client) if client is not None else genai.Client(api_key=key,
        http_options=types.HttpOptions(api_version='v1beta',timeout=int(timeout*1000),
            retry_options=types.HttpRetryOptions(attempts=1)))
    config=types.GenerateContentConfig(system_instruction=system,
        max_output_tokens=512 if probe else 4096,
        thinking_config=types.ThinkingConfig(thinking_level='low'),
        response_mime_type='application/json' if output_format=='json' else 'text/plain',
        http_options=types.HttpOptions(timeout=int(timeout*1000),retry_options=types.HttpRetryOptions(attempts=1)))
    with manager as google:
        response=google.models.generate_content(model=FALLBACK_MODEL,contents=context,config=config)
    candidates=getattr(response,'candidates',None) or []
    if candidates and getattr(getattr(candidates[0],'finish_reason',None),'value',getattr(candidates[0],'finish_reason',None))=='MAX_TOKENS':
        raise WriterFailure('TRUNCATED_OUTPUT')
    return response

def generate(route, context, system, record, persist, retry, reject_secrets,
             http_code, *, retries=1, sleep=None, timeout=60, probe=False, google_client=None):
    validate_route(route,route['primary'])
    if type(retries) is not int or not 0<=retries<=2 or not 10<=timeout<=300:
        raise ValueError('Invalid bounded writer request settings')
    system=system+('\n'+JSON_INSTRUCTION if route['format']=='json' else '')
    choices=[route['primary']]+([route['fallback']] if route['fallback'] else [])
    for index,model in enumerate(choices):
        provider='groq' if model==GROQ_MODEL else 'google'
        item={'provider':provider,'model':model,'status':'SENDING'}
        record.setdefault('writer_attempts',[]).append(item);persist()
        try:
            fn=(lambda:groq_generate(context,system,route['format'],timeout,probe)) if provider=='groq' else (
                lambda:google_generate(context,system,route['format'],timeout,probe,google_client))
            kwargs={'retries':retries}
            if sleep is not None:kwargs['sleep']=sleep
            response=retry(fn,item,persist,**kwargs)
            validation=validate_output(getattr(response,'text',None),route['format'],reject_secrets)
            item['status']='COMPLETE'
            record.update(writer_provider=provider,actual_model=model,fallback_used=index>0,
                          output_validation=validation)
            persist()
            return response
        except Exception as exc:
            code=http_code(exc)
            reason=exc.reason if isinstance(exc,WriterFailure) else ('HTTP_ERROR' if code else 'TRANSPORT_OR_VALIDATION_ERROR')
            item.update(status='ERROR',http_code=code,error_type=type(exc).__name__,reason=reason)
            persist()
            # No quota evasion, no duplicate requests after ambiguous transport failures.
            permitted=(code in FALLBACK_HTTP or isinstance(exc,WriterFailure) and code is None)
            if index+1>=len(choices) or code==429 or not permitted:raise
            record['fallback_reason']=reason;persist()
    raise WriterFailure('NO_WRITER_AVAILABLE')
