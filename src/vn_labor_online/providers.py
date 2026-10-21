"""Optional structured LLM boundaries. Core ONLINE does not require them."""
from __future__ import annotations

import json
import logging
import math
import random
import re
import threading
import time
from copy import deepcopy
from functools import cached_property
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod

from .errors import LLMProviderError,StructuredOutputError,ProviderRateLimited
from .runtime import checkpoint,request_timeout,RequestStopped
from .gemini_quota import GeminiRatePolicy,get_gemini_limiter,quota_info

def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise StructuredOutputError('DUPLICATE_JSON_KEY')
        result[key]=value
    return result

def _decode_content(content):
    if not isinstance(content,str): raise StructuredOutputError('NON_TEXT_STRUCTURED_OUTPUT')
    try: value=json.loads(content,object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc: raise StructuredOutputError('INVALID_JSON') from exc
    if not isinstance(value,dict): raise StructuredOutputError('NON_OBJECT_STRUCTURED_OUTPUT')
    return value


class BaseProvider(ABC):
    @abstractmethod
    def structured(self, system: str, user: str, schema: dict) -> dict: ...

    def readiness(self) -> dict:
        return {"status": "UNKNOWN"}

    @cached_property
    def client(self):
        import httpx
        local=urllib.parse.urlparse(self.url).hostname in {'localhost','127.0.0.1','::1'}
        return httpx.Client(timeout=self.timeout,trust_env=not local,
          limits=httpx.Limits(max_connections=4,max_keepalive_connections=2))

    def _post(self,payload,headers):
        for attempt in range(2):
            checkpoint()
            response=self.client.post(self.url,json=payload,headers=headers,timeout=request_timeout(self.timeout))
            checkpoint()
            if response.status_code in {429,502,503,504} and attempt==0:
                time.sleep(.25); continue
            response.raise_for_status()
            return response.json()
        raise LLMProviderError('HTTP_RETRY_EXHAUSTED')

    def close(self):
        client=self.__dict__.pop('client',None)
        if client is not None: client.close()


def _request_json(url: str, *, headers: dict | None = None, timeout: float = 5) -> dict:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


class HttpJsonProvider(BaseProvider):
    def __init__(self, url: str, model: str, api_key: str | None = None,
                 timeout: float = 60, health_url: str | None = None):
        self.url = url
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.health_url = health_url

    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "ngrok-skip-browser-warning": "true",
        }
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        return headers

    def structured(self, system: str, user: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "response_format": {"type": "json_schema", "json_schema": {"name": "result", "schema": schema}},
        }
        try:
            raw=self._post(payload,self._headers())
            content = raw["choices"][0]["message"]["content"]
            return _decode_content(content)
        except (StructuredOutputError,RequestStopped):
            raise
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

    def readiness(self) -> dict:
        if not self.health_url:
            return {"status": "UNKNOWN", "provider": "http", "model": self.model}
        try:
            raw = _request_json(self.health_url, headers=self._headers(), timeout=min(self.timeout, 10))
            ready = raw.get("ready", raw.get("status") in {"ok", "ready"})
            return {"status": "READY" if ready else "DEGRADED", "provider": "http", "model": self.model}
        except Exception as exc:
            return {"status": "DEGRADED", "provider": "http", "model": self.model,
                    "error": type(exc).__name__}


class OllamaProvider(BaseProvider):
    def __init__(self, url: str = "http://127.0.0.1:11434/api/chat", model: str = "qwen3:4b",
                 timeout: float = 120, health_url: str | None = None, max_output_tokens: int = 2048, context_tokens: int = 16384):
        self.url = url
        self.model = model
        self.timeout = timeout
        self.health_url = health_url or urllib.parse.urljoin(url, "/api/tags")
        self.max_output_tokens=max_output_tokens
        self.context_tokens=context_tokens

    def structured(self, system: str, user: str, schema: dict) -> dict:
        input_bound=len((system+user).encode("utf-8"))+256
        if input_bound+self.max_output_tokens>self.context_tokens:
            raise StructuredOutputError("PROMPT_CONTEXT_BUDGET_EXCEEDED")
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "think": False,
            "options": {"temperature": 0, "seed": 0,"num_predict":self.max_output_tokens,"num_ctx":self.context_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        try:
            raw=self._post(payload,{"Content-Type": "application/json", "Accept": "application/json"})
            if raw.get('done_reason')=='length': raise StructuredOutputError('OUTPUT_TOKEN_LIMIT')
            return _decode_content(raw['message']['content'])
        except (StructuredOutputError,RequestStopped):
            raise
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

    def readiness(self) -> dict:
        try:
            raw = _request_json(self.health_url, timeout=min(self.timeout, 10))
            models = {row.get("name", "").split(":")[0] for row in raw.get("models", [])}
            requested = self.model.split(":")[0]
            return {"status": "READY" if requested in models else "DEGRADED",
                    "provider": "ollama", "model": self.model, "model_loaded": requested in models}
        except Exception as exc:
            return {"status": "DEGRADED", "provider": "ollama", "model": self.model,
                    "error": type(exc).__name__}


def gemini_transport_schema(schema):
    """Avoid decoder-state blowups; enforce original array limits locally.

    Model types, required keys, enums, references and minimum lengths stay on
    the wire. Never mutate the caller's schema or delete a property whose name
    happens to be a JSON Schema keyword.
    """
    result=deepcopy(schema)
    def walk(node):
        if not isinstance(node,dict): return
        node.pop('maxItems',None)
        # A singleton enum has the same accepted values as scalar const, while
        # giving the structured-output decoder an explicit choice list. The
        # original schema (including const) is still validated locally.
        if 'const' in node and 'enum' not in node and isinstance(node['const'],(str,int,float,bool,type(None))):
            node['enum']=[node.pop('const')]
        for key in ('properties','$defs','definitions','patternProperties','dependentSchemas'):
            for value in (node.get(key) or {}).values(): walk(value)
        for key in ('items','additionalProperties','contains','not','if','then','else','propertyNames'):
            walk(node.get(key))
        for key in ('allOf','anyOf','oneOf','prefixItems'):
            for value in node.get(key,[]): walk(value)
    walk(result)
    return result


def gemini_array_limits(schema):
    """Communicate bounds omitted from the decoder schema without weakening
    local validation or silently discarding generated tasks/claims.
    """
    limits=[]
    def walk(node,path):
        if not isinstance(node,dict): return
        if node.get('type')=='array' and isinstance(node.get('maxItems'),int):
            limits.append(f'{path}: at most {node["maxItems"]} items')
        for key in ('properties','$defs','definitions'):
            for name,value in (node.get(key) or {}).items():
                walk(value,f'{path}.{name}' if key=='properties' else str(name))
        walk(node.get('items'),path+'[]')
        for key in ('allOf','anyOf','oneOf','prefixItems'):
            for index,value in enumerate(node.get(key,[])): walk(value,f'{path}.{key}[{index}]')
    walk(schema,'result')
    return ('\nThe original response contract also enforces these array bounds. '
        'Respect them when planning output; do not add redundant tasks or queries:\n'+
        '\n'.join(limits)) if limits else ''


def _wait_service_retry(seconds):
    until=time.monotonic()+seconds
    while True:
        checkpoint('gemini_service_retry')
        remaining=until-time.monotonic()
        if remaining<=0: return
        time.sleep(min(.25,remaining))


class GeminiProvider(BaseProvider):
    """Optional official Google SDK, used for understanding, not source authority."""
    def __init__(self, model, api_key=None, timeout=20, max_output_tokens=2048):
        self.model, self.api_key = model, api_key
        self.timeout, self.max_output_tokens = timeout, max_output_tokens
        self.rate_policy=GeminiRatePolicy.from_env()
        self.rate_limiter=get_gemini_limiter(model,self.rate_policy)
        self._probe_lock=threading.Lock()
        self._probe_next_at=0.0
        self._probe_failure={}


    def structured(self, system, user, schema):
        if not self.model or not self.api_key:
            raise LLMProviderError('GEMINI_CONFIGURATION_MISSING')
        wait_remaining=self.rate_policy.max_wait_seconds
        for attempt in range(self.rate_policy.max_retries+1):
            checkpoint()
            wait_remaining=max(0,wait_remaining-self.rate_limiter.acquire(wait_remaining))
            try:
                from google import genai
                from google.genai import types
                from jsonschema import Draft202012Validator,ValidationError
                # Exactly one SDK attempt: all actual retries must reacquire a
                # shared project/model slot and respect the request deadline.
                with genai.Client(api_key=self.api_key, http_options=types.HttpOptions(
                        timeout=max(1, int(request_timeout(self.timeout)*1000)),
                        retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    response=client.models.generate_content(model=self.model, contents=user,
                        config=types.GenerateContentConfig(system_instruction=system+gemini_array_limits(schema), temperature=0,
                            max_output_tokens=self.max_output_tokens, response_mime_type='application/json',
                            response_json_schema=gemini_transport_schema(schema)))
                checkpoint()
                candidates=getattr(response,'candidates',None) or []
                if candidates:
                    reason=getattr(candidates[0],'finish_reason',None)
                    if getattr(reason,'value',reason)=='MAX_TOKENS':
                        raise StructuredOutputError('OUTPUT_TOKEN_LIMIT')
                if not response.text: raise StructuredOutputError('GEMINI_EMPTY_RESPONSE')
                decoded=_decode_content(response.text)
                try: Draft202012Validator(schema).validate(decoded)
                except ValidationError as exc:
                    error=StructuredOutputError('GEMINI_SCHEMA_VALIDATION_FAILED')
                    # Only the fixed validator keyword is diagnostic. Its
                    # instance/message/path may contain private query data.
                    allowed={'maxItems','minItems','type','required','enum','additionalProperties',
                        'minLength','maxLength','minimum','maximum','const','anyOf','oneOf'}
                    if exc.validator in allowed: error.validation_keyword=exc.validator
                    raise error from None
                return decoded
            except (RequestStopped,StructuredOutputError,ProviderRateLimited):
                raise
            except Exception as exc:
                status=getattr(exc,'code',None)
                if status==429:
                    info=quota_info(exc)
                    delay=(info.retry_after_seconds if info.retry_after_seconds is not None else 60) if info.retryable else None
                    if info.retryable:
                        self.rate_limiter.defer(delay,info.kind)
                    if not info.retryable or attempt>=self.rate_policy.max_retries:
                        raise ProviderRateLimited('GEMINI_HTTP_429',quota_kind=info.kind,
                            retry_after_seconds=delay) from None
                    continue
                if status in {408,500,502,503,504} and attempt<self.rate_policy.max_retries:
                    # SDK retry is disabled so every actual attempt reacquires
                    # the shared RPM gate. A service outage is not a quota error.
                    delay=max(2**attempt+random.uniform(0,.25),quota_info(exc).retry_after_seconds or 0)
                    if delay<=wait_remaining and request_timeout(delay+.01)>=delay:
                        _wait_service_retry(delay)
                        wait_remaining=max(0,wait_remaining-delay)
                        continue
                # SDK errors can include request URLs. Never surface credentials.
                safe_code=f'GEMINI_HTTP_{status}' if type(status) is int and 400<=status<=599 else (
                  'GEMINI_TIMEOUT' if isinstance(exc,TimeoutError) else 'GEMINI_CLIENT_ERROR')
                raise LLMProviderError('GEMINI_REQUEST_FAILED:'+type(exc).__name__,safe_code=safe_code) from None
        raise AssertionError('unreachable')

    def readiness(self):
        from importlib.util import find_spec
        from .runtime import request_budget
        def report(ready=False, **details):
            return {'status':'READY' if ready else 'DEGRADED',
                'provider':'gemini','model':self.model,'check':'INFERENCE_PROBE',
                'rate_limit':{'requests_per_minute':self.rate_limiter.rpm,
                    'max_retries':self.rate_policy.max_retries,
                    'max_wait_seconds':self.rate_policy.max_wait_seconds,
                    'scope':'SHARED_PROCESS_PROJECT_MODEL'}, **details}
        if not self.api_key: return report(error_code='GEMINI_API_KEY_MISSING')
        if not self.model: return report(error_code='GEMINI_MODEL_MISSING')
        try: installed=find_spec('google.genai') is not None
        except ModuleNotFoundError: installed=False
        if not installed: return report(error_code='GEMINI_SDK_MISSING')
        if not self._probe_lock.acquire(blocking=False):
            return report(error_code='GEMINI_PROBE_IN_PROGRESS',retry_after_seconds=2)
        try:
            if getattr(self,'_ready',False): return report(True)
            remaining=self._probe_next_at-time.monotonic()
            if remaining>0:
                return report(**{**self._probe_failure,'retry_after_seconds':max(1,math.ceil(remaining))})
            try:
                # A probe can wait briefly for pacing, but cannot block /ready
                # for the whole 70s quota budget. The launcher retries readiness
                # across cooldowns instead of spawning overlapping long probes.
                with request_budget(min(20,self.timeout)):
                    result=self.structured('Return the requested JSON only.','Set ready to true.',
                      {'type':'object','properties':{'ready':{'type':'boolean'}},'required':['ready'],'additionalProperties':False})
                if result!={'ready':True}: raise StructuredOutputError('GEMINI_PROBE_RESPONSE_MISMATCH')
                self._ready=True
                self._probe_failure={}
                return report(True)
            except Exception as exc:
                details={'error_type':type(exc).__name__}
                cooldown=self.rate_limiter.cooldown_snapshot()
                if isinstance(exc,ProviderRateLimited) or cooldown:
                    details['error_code']='GEMINI_HTTP_429'
                    details['quota_kind']=getattr(exc,'quota_kind',None) or cooldown.get('quota_kind','UNKNOWN')
                    delay=getattr(exc,'retry_after_seconds',None)
                    if delay is None and details['quota_kind'] not in {'DAILY','QUOTA_DISABLED'}:
                        delay=cooldown.get('retry_after_seconds')
                    if delay is not None: details['retry_after_seconds']=max(1,math.ceil(delay))
                elif isinstance(exc,RequestStopped):
                    details['error_code']='GEMINI_PROBE_CANCELLED' if exc.reason=='REQUEST_CANCELLED' else 'GEMINI_PROBE_TIMEOUT'
                elif isinstance(exc,StructuredOutputError):
                    code=str(exc)
                    details['error_code']=code if code in {'OUTPUT_TOKEN_LIMIT','GEMINI_EMPTY_RESPONSE',
                      'GEMINI_SCHEMA_VALIDATION_FAILED','GEMINI_PROBE_RESPONSE_MISMATCH','INVALID_JSON',
                      'NON_OBJECT_STRUCTURED_OUTPUT','DUPLICATE_JSON_KEY','NON_TEXT_STRUCTURED_OUTPUT'} else 'GEMINI_PROBE_INVALID_RESPONSE'
                else:
                    code=getattr(exc,'safe_code',None)
                    details['error_code']=code if isinstance(code,str) and re.fullmatch(r'GEMINI_(?:HTTP_[45]\d\d|TIMEOUT|CLIENT_ERROR)',code) else 'GEMINI_PROBE_ERROR'
                delay=details.get('retry_after_seconds',5)
                self._probe_next_at=time.monotonic()+delay
                self._probe_failure=details
                logging.getLogger(__name__).warning('Gemini readiness failed: code=%s quota_kind=%s retry_after=%s',
                    details['error_code'],details.get('quota_kind'),details.get('retry_after_seconds'))
                return report(**details)
        finally:
            self._probe_lock.release()
