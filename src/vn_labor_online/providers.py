"""Optional structured LLM boundaries. Core ONLINE does not require them."""
from __future__ import annotations
import json,urllib.request
from abc import ABC,abstractmethod
from .errors import LLMProviderError,StructuredOutputError
class BaseProvider(ABC):
    @abstractmethod
    def structured(self,system:str,user:str,schema:dict)->dict: ...
class HttpJsonProvider(BaseProvider):
    def __init__(self,url:str,model:str,api_key:str|None=None,timeout:float=60): self.url=url; self.model=model; self.api_key=api_key; self.timeout=timeout
    def structured(self,system:str,user:str,schema:dict)->dict:
        payload={'model':self.model,'messages':[{'role':'system','content':system},{'role':'user','content':user}],
          'temperature':0,'response_format':{'type':'json_schema','json_schema':{'name':'result','schema':schema}}}
        headers={'Content-Type':'application/json'}
        if self.api_key: headers['Authorization']='Bearer '+self.api_key
        try:
            with urllib.request.urlopen(urllib.request.Request(self.url,data=json.dumps(payload).encode(),headers=headers),timeout=self.timeout) as response: raw=json.loads(response.read())
            content=raw['choices'][0]['message']['content']; return json.loads(content) if isinstance(content,str) else content
        except Exception as exc: raise LLMProviderError(str(exc)) from exc
class OllamaProvider(BaseProvider):
    def __init__(self,url='http://127.0.0.1:11434/api/chat',model='qwen3:4b',timeout=120): self.url=url; self.model=model; self.timeout=timeout
    def structured(self,system:str,user:str,schema:dict)->dict:
        payload={'model':self.model,'stream':False,'format':schema,'messages':[{'role':'system','content':system},{'role':'user','content':user}]}
        try:
            with urllib.request.urlopen(urllib.request.Request(self.url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}),timeout=self.timeout) as response: raw=json.loads(response.read())
            return json.loads(raw['message']['content'])
        except Exception as exc: raise LLMProviderError(str(exc)) from exc
