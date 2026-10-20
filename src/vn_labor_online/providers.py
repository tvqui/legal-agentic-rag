"""Optional structured LLM boundaries. Core ONLINE does not require them."""
from __future__ import annotations

import json
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
        for key in ('properties','$defs','definitions','patternProperties','dependentSchemas'):
            for value in (node.get(key) or {}).values(): walk(value)
        for key in ('items','additionalProperties','contains','not','if','then','else','propertyNames'):
            walk(node.get(key))
        for key in ('allOf','anyOf','oneOf','prefixItems'):
            for value in node.get(key,[]): walk(value)
    walk(result)
    return result


class GeminiProvider(BaseProvider):
    """Optional official Google SDK, used for understanding, not source authority."""
    def __init__(self, model, api_key=None, timeout=20, max_output_tokens=2048):
        self.model, self.api_key = model, api_key
        self.timeout, self.max_output_tokens = timeout, max_output_tokens
        self.rate_policy=GeminiRatePolicy.from_env()
        self.rate_limiter=get_gemini_limiter(model,self.rate_policy)

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
                        config=types.GenerateContentConfig(system_instruction=system, temperature=0,
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
                except ValidationError:
                    raise StructuredOutputError('GEMINI_SCHEMA_VALIDATION_FAILED') from None
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
                # SDK errors can include request URLs. Never surface credentials.
                safe_code=f'GEMINI_HTTP_{status}' if type(status) is int and 400<=status<=599 else (
                  'GEMINI_TIMEOUT' if isinstance(exc,TimeoutError) else 'GEMINI_CLIENT_ERROR')
                raise LLMProviderError('GEMINI_REQUEST_FAILED:'+type(exc).__name__,safe_code=safe_code) from None
        raise AssertionError('unreachable')

    def readiness(self):
        from importlib.util import find_spec
        try: installed=find_spec('google.genai') is not None
        except ModuleNotFoundError: installed=False
        ready=bool(getattr(self,'_ready',False))
        if installed and self.model and self.api_key and not ready:
            try:
                from .runtime import request_budget
                with request_budget(min(10,self.timeout)):
                    result=self.structured('Return the requested JSON only.','Set ready to true.',
                      {'type':'object','properties':{'ready':{'type':'boolean'}},'required':['ready'],'additionalProperties':False})
                ready=result=={'ready':True}
                self._ready=ready
            except Exception:
                ready=False
        return {'status':'READY' if ready else 'DEGRADED',
                'provider':'gemini','model':self.model,'check':'INFERENCE_PROBE',
                'rate_limit':{'requests_per_minute':self.rate_limiter.rpm,
                    'max_retries':self.rate_policy.max_retries,
                    'max_wait_seconds':self.rate_policy.max_wait_seconds,
                    'scope':'SHARED_PROCESS_PROJECT_MODEL'}}
