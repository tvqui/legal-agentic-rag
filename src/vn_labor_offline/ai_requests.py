"""Bounded, resumable OFFLINE AI requests with complete source coverage."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json, time, uuid
from pathlib import Path
from .ai_enrichment import cached_structured, cache_dir, structured_cache_key


class AIRequestBlocked(RuntimeError):
    pass


def source_chunks(source: str, byte_budget: int = 3500):
    if byte_budget < 256:
        raise ValueError('AI source byte budget must be at least 256')
    start = 0
    while start < len(source):
        end = start
        used = 0
        while end < len(source) and used + len(source[end].encode('utf-8')) <= byte_budget:
            used += len(source[end].encode('utf-8')); end += 1
        # Prefer a sentence/newline boundary, without dropping the tail.
        boundary = max(source.rfind('\n', start, end), source.rfind('. ', start, end))
        if end<len(source) and boundary > start + (end-start)*.6:
            end = boundary+1
        yield start, source[start:end]
        if end == len(source):
            break
        start = max(start+1, end-min(120, (end-start)//4))


def error_details(exc: Exception) -> dict:
    chain=[]; current=exc; seen=set(); status=None
    while current is not None and id(current) not in seen:
        seen.add(id(current)); chain.append(type(current).__name__)
        response=getattr(current,'response',None)
        if response is not None:
            status=getattr(response,'status_code',None)
        current=current.__cause__ or current.__context__
    label=' '.join(chain).lower()
    if 'timeout' in label: reason='AI_REQUEST_TIMEOUT'
    elif isinstance(exc,AIRequestBlocked): reason=str(exc)
    elif status in {401,403}: reason='AI_AUTH_FAILED'
    elif status: reason='AI_HTTP_'+str(status)
    elif 'OUTPUT_TOKEN_LIMIT' in str(exc): reason='AI_OUTPUT_TOKEN_LIMIT'
    elif 'PROMPT_CONTEXT_BUDGET' in str(exc): reason='AI_CONTEXT_BUDGET_EXCEEDED'
    elif 'json' in label or 'structuredoutput' in label or 'AI_SCHEMA_' in str(exc): reason='AI_INVALID_STRUCTURED_OUTPUT'
    elif 'connect' in label: reason='AI_CONNECTION_FAILED'
    else: reason='AI_PROVIDER_FAILED'
    # Never store arbitrary exception messages, URLs, credentials or request text.
    return {'reason':reason,'exception_chain':chain,'http_status':status}


class AIRequests:
    def __init__(self,provider,cfg,output_dir: Path,stage: str):
        self.provider=provider; self.cache=cache_dir(cfg); self.stage=stage
        self.settings=cfg.get('knowledge',{}); self.started=time.monotonic()
        default=10800
        key='ai_case_budget_seconds' if stage=='case_ontology' else 'ai_checklist_budget_seconds'
        self.seconds=float(self.settings.get(key,default))
        if self.seconds<=0: raise ValueError('AI stage budget must be positive')
        self.limit=max(1,int(self.settings.get('ai_max_consecutive_failures',5)))
        self.failures=0; self.network_calls=0; self.cache_hits=0
        self.events=Path(output_dir)/'reports/offline_ai_requests.jsonl'
        self.events.parent.mkdir(parents=True,exist_ok=True)
        self.run_id=uuid.uuid4().hex; self.last_path=None

    @property
    def stop_reason(self):
        if self.failures>=self.limit: return 'AI_CIRCUIT_OPEN'
        if time.monotonic()-self.started>=self.seconds: return 'AI_STAGE_BUDGET_EXHAUSTED'
        return None

    def observe(self,event,**details):
        self.last_path=details.pop('cache_path',self.last_path)
        if event=='before':
            reason=self.stop_reason
            remaining=self.seconds-(time.monotonic()-self.started)
            timeout=getattr(self.provider,'timeout',0)
            if isinstance(timeout,(int,float)) and remaining<timeout:
                reason=reason or 'AI_STAGE_BUDGET_EXHAUSTED'
            if reason: raise AIRequestBlocked(reason)
            self.network_calls+=1
        if event=='cache_hit': self.cache_hits+=1
        if event=='success': self.failures=0
        # A length/schema problem is task-specific, not proof of provider outage.
        recoverable={'AI_OUTPUT_TOKEN_LIMIT','AI_INVALID_STRUCTURED_OUTPUT'} if self.settings.get('ai_compact_output',False) else set()
        if event=='error' and details.get('reason') not in {'AI_CIRCUIT_OPEN','AI_STAGE_BUDGET_EXHAUSTED'} | recoverable:
            self.failures+=1
        row={'schema_version':1,'run_id':self.run_id,'stage':self.stage,'event':event,
             'updated_at':datetime.now(timezone.utc).isoformat(),**details}
        with self.events.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n'); stream.flush()
        if event!='cache_hit': print('AI_REQUEST '+json.dumps(row,ensure_ascii=False),flush=True)

    def invalidate(self):
        if self.last_path is not None:
            Path(self.last_path).unlink(missing_ok=True)

    def generate(self,system,payload,schema,identity):
        """Return successful fragments and explicit uncovered fragments.

        Failures and saturated outputs can split to a bounded depth. Cache fragments are
        read even when the network circuit is open. No tail truncation occurs.
        """
        source=payload.get('source','')
        envelope=dict(payload); envelope['source']=''; envelope['source_offset']=0
        context=int(self.settings.get('ai_context_tokens',16384))
        output=int(self.settings.get('ai_max_output_tokens',2048))
        overhead=len((system+json.dumps(envelope,ensure_ascii=False)).encode('utf-8'))+1024
        budget=min(int(self.settings.get('ai_chunk_bytes',3500)),context-output-overhead)
        if budget<256:
            return [],[{'reason':'AI_ANCESTOR_CONTEXT_TOO_LARGE','source_start':0,'source_end':len(source)}],1
        completed=[]; errors=[]; planned=0
        max_depth=min(4,max(1,int(self.settings.get('ai_max_split_depth',1))))
        def visit(offset,text,depth):
            nonlocal planned
            value={**payload,'source':text,'source_offset':offset}
            key=structured_cache_key(self.provider,system,value,schema,identity)
            split_path=self.cache/(key+'.split.json')
            if depth<max_depth and split_path.exists():
                try:
                    split=json.loads(split_path.read_text(encoding='utf-8')); smaller=split['byte_budget']
                    if not isinstance(smaller,int) or not 256<=smaller<len(text.encode('utf-8')): raise ValueError('Invalid split cache')
                    for child_offset,child in source_chunks(text,smaller): visit(offset+child_offset,child,depth+1)
                    return
                except (OSError,ValueError,KeyError,TypeError): pass
            try:
                from .anchored_ai import request_fragment
                data,saturated=request_fragment(self,system,value,schema,identity)
                if saturated and self.settings.get('ai_compact_output',False):
                    if depth<max_depth and len(text.encode('utf-8'))>512:
                        smaller=max(256,len(text.encode('utf-8'))//2)
                        split_path.parent.mkdir(parents=True,exist_ok=True)
                        temporary=split_path.with_suffix('.tmp')
                        temporary.write_text(json.dumps({'byte_budget':smaller}),encoding='utf-8')
                        temporary.replace(split_path)
                        for child_offset,child in source_chunks(text,smaller): visit(offset+child_offset,child,depth+1)
                        return
                    errors.append({'reason':'AI_FRAGMENT_CAPACITY_REACHED','source_start':offset,'source_end':offset+len(text)})
                completed.append({'source_offset':offset,'source':text,'data':data}); planned+=1
            except Exception as exc:
                info=error_details(exc)
                recover=info['reason'] in {'AI_REQUEST_TIMEOUT','AI_OUTPUT_TOKEN_LIMIT','AI_HTTP_500'}
                recover=recover or (self.settings.get('ai_compact_output',False) and info['reason']=='AI_INVALID_STRUCTURED_OUTPUT')
                if recover and depth<max_depth and len(text.encode('utf-8'))>512 and not self.stop_reason:
                    smaller=max(256,len(text.encode('utf-8'))//2)
                    split_path.parent.mkdir(parents=True,exist_ok=True)
                    temporary=split_path.with_suffix('.tmp')
                    temporary.write_text(json.dumps({'byte_budget':smaller}),encoding='utf-8')
                    temporary.replace(split_path)
                    for child_offset,child in source_chunks(text,smaller): visit(offset+child_offset,child,depth+1)
                else:
                    errors.append({**info,'source_start':offset,'source_end':offset+len(text)}); planned+=1
        for offset,text in source_chunks(source,budget): visit(offset,text,0)
        if not source:
            errors.append({'reason':'AI_EMPTY_SOURCE','source_start':0,'source_end':0}); planned=1
        return completed,errors,planned
