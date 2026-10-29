"""Bounded execution facts for a request owner; never prompts or model reasoning."""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import json,os,re,threading,time
from .gemini_diagnostics import FIELDS as GEMINI_ERROR_FIELDS,HINTS as GEMINI_ERROR_REASONS,STATUSES as GEMINI_API_STATUSES

SPECS={
 'api':('Tiếp nhận yêu cầu','Backend API','FastAPI · Pydantic','QueryRequest đã kiểm tra'),
 'context':('Xác định ngữ cảnh hội thoại','Pipeline','Python · ngữ cảnh từ lời người dùng','ResolvedContext'),
 'analysis':('Phân tích câu hỏi','Pipeline / Analyzer','Python · regex · taxonomy','QueryAnalysis'),
 'researcher':('Researcher: hiểu ý hỏi','Researcher','Python · quy tắc thích nghi','QueryAnalysis bổ sung'),
 'planning':('Lập kế hoạch căn cứ','Pipeline / Planner','EvidencePlan · LegalLocator','Các ô căn cứ bắt buộc'),
 'scope_gate':('Kiểm phạm vi và dữ kiện','Pipeline','Quy tắc phạm vi / dữ kiện','Quyết định tiếp tục hoặc hỏi thêm'),
 'exact':('Tra cứu Điều/Khoản/Điểm','Retriever','Tra metadata · cây pháp lý','Evidence tìm chính xác'),
 'profile':('Kiểm chuỗi quy tắc đã biết','Retriever / Pipeline','Python · profile · kiểm tra xác định','Căn cứ mồi và độ đủ'),
 'policy':('Tìm căn cứ bắt buộc theo vấn đề','Retriever','Profile locator','Evidence theo yêu cầu'),
 'bm25':('Tìm kiếm theo từ khóa','Retriever','BM25S','Danh sách Evidence BM25'),
 'dense':('Tìm kiếm ngữ nghĩa','Retriever','BGE-M3 · FAISS','Danh sách Evidence Dense'),
 'issue':('Tìm qua vấn đề pháp lý','Retriever / Ontology','LegalIssue · RELATES_TO_ISSUE','Evidence nối với vấn đề'),
 'cases':('Tìm vụ án liên quan','Retriever / Fact Graph','Kênh CASE · khớp từ / số hiệu','Evidence vụ án'),
 'community':('Tìm qua cộng đồng vụ án','Retriever / Ontology','Community · BELONGS_TO','Evidence CASE thành viên'),
 'fusion':('Hợp nhất các kênh tìm kiếm','Retriever','RRF','Evidence đã gộp theo ID'),
 'temporal':('Lọc phiên bản theo thời điểm','Bộ kiểm tra','Khoảng hiệu lực · metadata','Nguồn giữ lại và bị loại'),
 'authority':('Lọc tính truy nguyên nguồn','Bộ kiểm tra / Document','URL · catalog · thẩm quyền','Nguồn truy nguyên được'),
 'reranker':('Xếp hạng lại bằng mô hình','Retriever','BGE reranker','Evidence sau xếp hạng lại'),
 'source_audit':('Kiểm ID, nguồn và vị trí trích','Bộ kiểm tra / Document','Python · provenance · span','Evidence vượt kiểm tra máy'),
 'auditor':('Auditor: kiểm điều kiện áp dụng','Auditor','Quy tắc · checklist; model nếu cần','PASS / FAIL / UNRESOLVED'),
 'coverage':('Đo mức đủ căn cứ','Pipeline / Evidence manager','EvidenceSlot · coverage','Ô đã đủ và ô còn thiếu'),
 'graph':('Mở rộng đồ thị theo chỗ thiếu','Graph / Pipeline','Đồ thị trong RAM · giới hạn duyệt','Nguồn bổ sung và lý do dừng'),
 'graph_round':('Duyệt một vòng đồ thị','Graph','Danh sách kề · hàng đợi ưu tiên','Node/cạnh mới và Evidence'),
 'selection':('Chọn bộ căn cứ trả lời','Pipeline / Evidence manager','Chọn theo slot · loại trùng','Nguồn được chọn'),
 'pack':('Đóng gói căn cứ đã kiểm','Pipeline','VerifiedEvidencePack','Pack cho Adjudicator'),
 'adjudicator':('Adjudicator: tạo nhận định','Adjudicator','Kết xuất quy tắc; model nếu cần','Draft có claims gắn nguồn'),
 'answer_quality':('Kiểm câu chữ và bố cục','Hậu kiểm','Quy tắc bảo toàn nội dung','Draft và cảnh báo câu chữ'),
 'semantic_review':('Kiểm nghĩa và độ đủ câu trả lời','Hậu kiểm','Semantic reviewer · JSON Schema','PASS / PARTIAL / FAIL / ERROR'),
 'reference_audit':('Kiểm trích dẫn cuối cùng','Hậu kiểm','Đối chiếu ID · locator · URL · claim','Kết quả kiểm trích dẫn'),
 'tasks':('Kiểm từng ý của câu hỏi','Pipeline / Hậu kiểm','AnswerPart · độ phủ task','Trạng thái từng ý'),
 'response':('Hoàn tất phản hồi','Backend API','AnswerResponse · JSON','Trạng thái và metadata kết quả'),
 'model_call':('Gọi mô hình có cấu trúc','LLM provider','LLM · JSON Schema','Đối tượng JSON; chưa phải kết luận pháp lý'),
}
STATUSES={'RUNNING','DONE','SKIPPED','WARNING','ERROR','CANCELLED'}
LAYERS={'rule':'Rule Graph','fact':'Fact Graph','ontology':'Ontology Graph','document':'Document','derived':'Derived'}
SAFE_ERROR_CODES={
    'GEMINI_TIMEOUT','GEMINI_CLIENT_ERROR','PROMPT_CONTEXT_BUDGET_EXCEEDED',
    'OUTPUT_TOKEN_LIMIT','INVALID_JSON','NON_OBJECT_STRUCTURED_OUTPUT',
    'DUPLICATE_JSON_KEY','NON_TEXT_STRUCTURED_OUTPUT','GEMINI_EMPTY_RESPONSE',
    'GEMINI_SCHEMA_VALIDATION_FAILED','GEMINI_PROBE_RESPONSE_MISMATCH',
    'ADAPTIVE_CLAIM_LIMIT_EXCEEDED','SEMANTIC_CLAIM_REJECTED',
}
SAFE_ERROR_REASONS={'REQUEST_CANCELLED','REQUEST_DEADLINE_EXCEEDED'}
def clean(value,depth=0):
    """Apply bounds even to internal summaries. Callers must not pass raw text."""
    if depth>3:return '[giới hạn cấu trúc]'
    if value is None or type(value) in (bool,int):return value
    if type(value) is float:return round(value,3)
    if isinstance(value,str):return value[:240]
    if isinstance(value,(list,tuple)):return [clean(v,depth+1) for v in value[:16]]
    if isinstance(value,dict):
        return {str(k)[:60]:clean(v,depth+1) for k,v in list(value.items())[:20]
            if not re.search(r'(?i)(?:key|token|secret|password|prompt|raw_query|source_quote|full_text|^answer$)',str(k))}
    return type(value).__name__

def public_error(exc):
    data={'loai_loi':type(exc).__name__}
    reason=getattr(exc,'reason',None)
    if isinstance(reason,str) and reason in SAFE_ERROR_REASONS:data['ma_loi']=reason
    code=getattr(exc,'safe_code',None)
    if isinstance(code,str) and (
        code in SAFE_ERROR_CODES
        or re.fullmatch(r'GEMINI_HTTP_[45]\d\d',code)
    ):
        data['ma_loi']=code
    code=getattr(getattr(exc,'response',None),'status_code',None)
    if type(code) is int and 100<=code<=599:data['http']=code
    message=str(exc)
    if message in SAFE_ERROR_CODES or re.fullmatch(r'GEMINI_HTTP_[45]\d\d',message):
        data['ma_loi']=message
    diagnostics=getattr(exc,'safe_diagnostics',None)
    if isinstance(diagnostics,dict):
        safe={}
        api_status=diagnostics.get('api_status')
        if isinstance(api_status,str) and api_status in GEMINI_API_STATUSES:
            safe['api_status']=api_status
        error_reason=diagnostics.get('error_reason')
        if isinstance(error_reason,str) and error_reason in GEMINI_ERROR_REASONS:
            safe['error_reason']=error_reason
        fields=diagnostics.get('error_fields')
        if isinstance(fields,list):
            safe_fields=sorted({item for item in fields
                if isinstance(item,str) and item in GEMINI_ERROR_FIELDS})
            if safe_fields:safe['error_fields']=safe_fields
        if safe:data['diagnostics']=safe
    # Never str(exc): providers can embed URLs, credentials and private text.
    return data

class ProgressLog:
    def __init__(self,limit=160):
        self.limit=limit;self.events=[];self.serial=0;self.dropped=0;self.lock=threading.Lock()
        self.started=time.monotonic()
    def begin(self,key,technology=None,output=None):
        title,layer,tech,result=SPECS[key]
        with self.lock:
            self.serial+=1
            event={'id':self.serial,'step':key,'name':title,'layer':layer,
                'technology':str(technology or tech)[:140],'output_type':result,'status':'RUNNING',
                'started_ms':round((time.monotonic()-self.started)*1000,2),'elapsed_ms':None,'output':clean(output or {})}
            self.events.append(event)
            if len(self.events)>self.limit:self.events.pop(0);self.dropped+=1
            self._console(event)
            return event['id']
    def finish(self,ident,output=None,status='DONE'):
        if status not in STATUSES:raise ValueError('Invalid execution status')
        with self.lock:
            event=next((e for e in self.events if e['id']==ident),None)
            if event is not None:
                event.update(status=status,output=clean(output or {}),
                    elapsed_ms=round((time.monotonic()-self.started)*1000-event['started_ms'],2))
                self._console(event)
    def snapshot(self):
        with self.lock:
            events=deepcopy(self.events);now=(time.monotonic()-self.started)*1000
            for event in events:
                if event['status']=='RUNNING':event['elapsed_ms']=round(now-event['started_ms'],2)
            return {'version':'execution-steps-v1','steps':events,'dropped':self.dropped,'elapsed_ms':round(now,2)}
    def fail_running(self,exc):
        with self.lock:
            ids=[e['id'] for e in self.events if e['status']=='RUNNING']
        for ident in ids:self.finish(ident,public_error(exc),'CANCELLED' if getattr(exc,'reason','')=='REQUEST_CANCELLED' else 'ERROR')
    @staticmethod
    def _console(event):
        if os.getenv('VN_LABOR_DEMO_CONSOLE')=='1':
            # Optional only. A broken stdout must not change the legal outcome.
            try:print('ONLINE_STEP '+json.dumps(event,ensure_ascii=False),flush=True)
            except (OSError,UnicodeError):pass

def journal():
    from .runtime import _current
    budget=_current.get()
    return budget.progress if budget is not None else None

class Step:
    def __init__(self,key,technology=None,output=None):
        self.log=journal();self.ident=self.log.begin(key,technology,output) if self.log else None
        self.done=False
    def finish(self,output=None,status='DONE'):
        if self.log and not self.done:self.log.finish(self.ident,output,status)
        self.done=True

def skip(key,reason,technology=None):
    Step(key,technology).finish({'ly_do':reason},'SKIPPED')

def skip_after_gate(reason):
    for key in ('bm25','dense','graph','adjudicator','semantic_review'):skip(key,reason)

@contextmanager
def step(key,technology=None,output=None):
    handle=Step(key,technology,output)
    try:
        yield handle
    except BaseException as exc:
        handle.finish(public_error(exc),'CANCELLED' if getattr(exc,'reason','')=='REQUEST_CANCELLED' else 'ERROR')
        raise
    finally:
        if not handle.done:handle.finish()

def call(key,fn,*args,summary=None,technology=None,status=None,**kwargs):
    with step(key,technology) as handle:
        result=fn(*args,**kwargs)
        try:output=summary(result) if summary else {}
        except Exception:output={'tom_tat':'Đã hoàn tất; tóm tắt không khả dụng'}
        try:state=status(result) if status else 'DONE'
        except Exception:state='WARNING'
        handle.finish(output,state)
        return result

def evidence_summary(items,store=None):
    counts={}
    if store:
        for item in items:
            layer=((store.nodes_by_id.get(item.unit_id) or {}).get('properties') or {}).get('layer')
            name=LAYERS.get(layer)
            if name:counts[name]=counts.get(name,0)+1
    return {'so_nguon':len(items),'evidence_ids':[x.unit_id for x in items[:8]],'loai_nguon_trong_ket_qua':counts}

def audit_summary(result):
    items,decisions,warnings=result
    return {'nguon_duoc_giu':len(items),'PASS':sum(d.audit_status=='PASS' for d in decisions),
        'FAIL':sum(d.audit_status=='FAIL' for d in decisions),'UNRESOLVED':sum(d.audit_status=='UNRESOLVED' for d in decisions),
        'so_canh_bao':len(warnings)}

def graph_summary(result,store,round_no):
    items,frontier,stats=result
    layers={}
    for uid in frontier:
        name=LAYERS.get(((store.nodes_by_id.get(uid) or {}).get('properties') or {}).get('layer'))
        if name:layers[name]=layers.get(name,0)+1
    return {**evidence_summary(items,store),'vong':round_no,'node_moi':stats['nodes_added'],
        'canh_da_xet':stats['edges_visited'],'tang_node_da_duyet':layers,'ly_do_dung':stats['stop_reason']}

def observe_model(fn):
    """An actual structured() invocation; not just a configured model name."""
    @wraps(fn)
    def wrapped(self,*args,**kwargs):
        provider={'GeminiProvider':'Gemini','OllamaProvider':'Ollama','HttpJsonProvider':'HTTP JSON'}.get(type(self).__name__,'LLM')
        name=getattr(self,'model',None)
        name=name if isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,100}',name) else 'model cấu hình'
        return call('model_call',lambda:fn(self,*args,**kwargs),technology=provider+' · '+name,
            summary=lambda result:{'kieu_du_lieu':type(result).__name__,'so_truong':len(result) if isinstance(result,dict) else 0})
    return wrapped

def execution_snapshot():
    log=journal()
    return log.snapshot() if log else {'version':'execution-steps-v1','steps':[],'dropped':0,'elapsed_ms':0}

def draft_summary(result):
    draft,warnings=result
    return {'so_claim':len(draft.claims),'so_canh_bao':len(warnings),
        'semantic_review':draft.semantic_review.get('status','NOT_RUN'),
        'ma_loi':draft.semantic_review.get('error_code')}

def observe_result(key,summary,status=None):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            return call(key,fn,*args,summary=summary,status=status,**kwargs)
        return wrapped
    return decorate
