from contextlib import asynccontextmanager
from pathlib import Path
import hashlib, json, logging, math, os, re, secrets, threading, uuid
from datetime import date
from .runtime import RequestRegistry,RequestStopped,request_budget
from .demo_progress import SPECS,step as execution_step,execution_snapshot,public_error
from .config import load_config
from .errors import OnlineError,ProviderRateLimited
from .models import AnswerResponse,QueryRequest
from .pipeline import OnlinePipeline
from .taxonomy import TAXONOMY_VERSION
from .topics import VERSION as TOPIC_REGISTRY_VERSION

logger = logging.getLogger(__name__)

_SAFE_EVENTS={
    'ONLINE_STARTUP_FAILED','ONLINE_PROCESSING_FAILED',
    'UNHANDLED_ONLINE_EXCEPTION','ASGI_FAILURE',
}

def _safe_request_id(value) -> str:
    return value if isinstance(value,str) and re.fullmatch(r'REQ_[A-Fa-f0-9]{16}',value) else '-'

def _safe_failure_step(state) -> str:
    budget=state.get('execution_budget') if isinstance(state,dict) else None
    if budget is None:return '-'
    snapshot=budget.progress.snapshot()
    failed=[item.get('step') for item in snapshot['steps']
        if item.get('status') in {'ERROR','CANCELLED'} and item.get('step') in SPECS]
    for step_name in reversed(failed):
        if step_name not in {'api','response'}:return step_name
    if failed:return failed[-1]
    return budget.stage if budget.stage in SPECS else '-'

def _log_safe_failure(error_id: str, event: str, exc: BaseException,
                      request_id: str='-', step_name: str='-') -> None:
    summary = public_error(exc)
    code = summary.get('ma_loi')
    if code is None and type(summary.get('http')) is int:
        code = f"HTTP_{summary['http']}"
    error_type=summary.get('loai_loi',type(exc).__name__)
    error_type=error_type if isinstance(error_type,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}',error_type) else 'Exception'
    event=event if event in _SAFE_EVENTS else 'ASGI_FAILURE'
    code=code if isinstance(code,str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',code) else 'UNCLASSIFIED'
    diagnostics=summary.get('diagnostics',{})
    api_status=diagnostics.get('api_status','-')
    error_reason=diagnostics.get('error_reason','-')
    error_fields=','.join(diagnostics.get('error_fields',[])) or '-'
    logger.error(
        'error_id=%s request_id=%s step=%s event=%s error_type=%s code=%s api_status=%s error_reason=%s error_fields=%s',
        error_id,_safe_request_id(request_id),step_name if step_name in SPECS else '-',
        event,error_type,code,api_status,error_reason,error_fields,
    )

class SanitizedASGIApplication:
    def __init__(self,app):
        self.app=app

    def __getattr__(self,name):
        return getattr(self.app,name)

    async def __call__(self,scope,receive,send):
        try:
            await self.app(scope,receive,send)
        except Exception as exc:
            state=scope.get('state')
            state=state if isinstance(state,dict) else {}
            error_id=state.get('error_id')
            if not isinstance(error_id,str) or not re.fullmatch(r'ERR_[A-F0-9]{12}',error_id):
                error_id=f"ERR_{uuid.uuid4().hex[:12].upper()}"
            request_id=_safe_request_id(state.get('request_id'))
            step_name=_safe_failure_step(state)
            if not state.get('online_error_logged'):
                _log_safe_failure(error_id,'ASGI_FAILURE',exc,request_id,step_name)
            summary=public_error(exc)
            error_type=summary.get('loai_loi','Exception')
            code=summary.get('ma_loi','UNCLASSIFIED')
            error_type=error_type if isinstance(error_type,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}',error_type) else 'Exception'
            code=code if isinstance(code,str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',code) else 'UNCLASSIFIED'
            safe_message=(
                f"Online ASGI failure error_id={error_id} request_id={request_id} "
                f"step={step_name} error_type={error_type} code={code}"
            )
            raise SanitizedASGIError(safe_message) from None

class SanitizedASGIError(RuntimeError):
    pass

def _with_execution(request,payload):
    budget=getattr(request.state,'execution_budget',None)
    if budget is not None:
        snapshot=budget.progress.snapshot()
        payload['details']['execution_steps']=snapshot['steps']
        payload['details']['execution_steps_dropped']=snapshot['dropped']
    return payload

def _error_envelope(status_code: int, category: str, message: str, details: dict | None = None, error_id: str | None = None):
    eid = error_id or f"ERR_{uuid.uuid4().hex[:12].upper()}"
    return {
        "status": "error",
        "error_id": eid,
        "category": category,
        "message": message,
        "detail": message,
        "details": details or {}
    }

def _component(provider,name):
    if provider is None: return {'status':'READY','provider':'deterministic','model':None,'component':name}
    result=dict(provider.readiness()); result['component']=name
    return result

def create_app(config_path:str|Path|None=None):
    from .deployment import source_fingerprint
    online_source_fingerprint=source_fingerprint()
    from fastapi import FastAPI,HTTPException,Request
    from fastapi.encoders import jsonable_encoder
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    state={'pipeline':None,'error_id':None}
    try: max_concurrent_answers=max(1,int(os.getenv('VN_LABOR_MAX_CONCURRENT_ANSWERS','1')))
    except ValueError: max_concurrent_answers=1
    answer_slots=threading.BoundedSemaphore(max_concurrent_answers)
    requests=RequestRegistry()
    @asynccontextmanager
    async def lifespan(app):
        try:
            selected=Path(config_path or os.getenv('VN_LABOR_ONLINE_CONFIG','config/online.yaml'))
            state['pipeline']=OnlinePipeline(load_config(selected))
        except Exception as exc:
            eid=f"ERR_{uuid.uuid4().hex[:12].upper()}"
            state['error_id']=eid
            _log_safe_failure(eid,'ONLINE_STARTUP_FAILED',exc)
        try:
            yield
        finally:
            pipeline=state['pipeline']
            if pipeline is not None: pipeline.close()
    app=FastAPI(title='Vietnamese Labor Legal QA',version='0.3.0',lifespan=lifespan)
    origins=[value.strip() for value in os.getenv('VN_LABOR_CORS_ORIGINS','http://127.0.0.1:5173,http://localhost:5173').split(',') if value.strip()]
    if origins:
        app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,allow_methods=['GET','POST','OPTIONS'],
          allow_headers=['Accept','Content-Type','Authorization','ngrok-skip-browser-warning','X-Client-Session'],expose_headers=['X-Request-ID'])

    @app.exception_handler(RequestStopped)
    async def stopped_handler(request:Request,exc:RequestStopped):
        cancelled=exc.reason=='REQUEST_CANCELLED'
        eid=f"ERR_{uuid.uuid4().hex[:12].upper()}"
        request.state.error_id=eid
        reason='REQUEST_CANCELLED' if cancelled else 'REQUEST_DEADLINE_EXCEEDED'
        stage=exc.stage if exc.stage in SPECS else '-'
        logger.warning('error_id=%s request_id=%s step=%s code=%s error_type=RequestStopped',
            eid,_safe_request_id(getattr(request.state,'request_id','-')),stage,reason)
        return JSONResponse(status_code=409 if cancelled else 504,content=_with_execution(request,_error_envelope(
          409 if cancelled else 504,'CANCELLED' if cancelled else 'TIMEOUT',
          'Yêu cầu đã được dừng.' if cancelled else 'Yêu cầu vượt thời gian xử lý. Chưa có kết luận pháp lý được trả về.',
          details={'stage':stage,'request_id':getattr(request.state,'request_id',None)},error_id=eid)))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        payload = _error_envelope(
            status_code=422,
            category="VALIDATION_ERROR",
            message="Dữ liệu yêu cầu không hợp lệ hoặc thiếu trường bắt buộc.",
            details={"errors": jsonable_encoder(exc.errors())}
        )
        return JSONResponse(status_code=422, content=_with_execution(request,payload))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        category = "SERVICE_UNAVAILABLE" if exc.status_code == 503 else "SERVICE_BUSY" if exc.status_code == 429 else "CLIENT_ERROR" if exc.status_code < 500 else "INTERNAL_ERROR"
        msg = exc.detail if isinstance(exc.detail, str) else "Yêu cầu không thể xử lý."
        det = exc.detail if isinstance(exc.detail, dict) else {}
        payload = _error_envelope(
            status_code=exc.status_code,
            category=category,
            message=msg,
            details=det
        )
        return JSONResponse(status_code=exc.status_code, content=_with_execution(request,payload))

    @app.exception_handler(ProviderRateLimited)
    async def provider_rate_handler(request:Request,exc:ProviderRateLimited):
        retry=exc.retry_after_seconds
        details={'provider':'gemini','reason':'GEMINI_HTTP_429','quota_kind':exc.quota_kind}
        headers={}
        if retry is not None:
            details['retry_after_seconds']=max(1,math.ceil(retry))
            headers['Retry-After']=str(details['retry_after_seconds'])
        message=('Dịch vụ AI đã chạm hạn mức ngày hoặc hạn mức không khả dụng. Chưa có kết luận pháp lý.'
                 if exc.quota_kind in {'DAILY','QUOTA_DISABLED'} else
                 'Dịch vụ AI đang giới hạn lượt gọi hoặc lượng token; đã hết số lần thử/thời gian chờ cho yêu cầu này. Vui lòng thử lại sau.')
        payload=_error_envelope(503,'PROVIDER_RATE_LIMIT',message,details=details)
        return JSONResponse(status_code=503,content=_with_execution(request,payload),headers=headers)

    @app.exception_handler(OnlineError)
    async def online_error_handler(request: Request, exc: OnlineError):
        eid = f"ERR_{uuid.uuid4().hex[:12].upper()}"
        request.state.error_id=eid
        request.state.online_error_logged=True
        _log_safe_failure(eid,'ONLINE_PROCESSING_FAILED',exc,
            getattr(request.state,'request_id','-'),_safe_failure_step(request.scope.get('state',{})))
        payload = _error_envelope(
            status_code=503,
            category="SERVICE_UNAVAILABLE",
            message="Hệ thống trực tuyến tạm thời gián đoạn xử lý pháp lý.",
            details={"error_type": type(exc).__name__},
            error_id=eid
        )
        return JSONResponse(status_code=503, content=_with_execution(request,payload))

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        eid = f"ERR_{uuid.uuid4().hex[:12].upper()}"
        request.state.error_id=eid
        request.state.online_error_logged=True
        _log_safe_failure(eid,'UNHANDLED_ONLINE_EXCEPTION',exc,
            getattr(request.state,'request_id','-'),_safe_failure_step(request.scope.get('state',{})))
        payload = _error_envelope(
            status_code=500,
            category="INTERNAL_ERROR",
            message="Đã xảy ra lỗi hệ thống nội bộ. Vui lòng thử lại sau.",
            details={"error_id": eid},
            error_id=eid
        )
        return JSONResponse(status_code=500, content=_with_execution(request,payload))

    @app.middleware('http')
    async def bearer_auth(request:Request,call_next):
        request.state.request_id='REQ_'+uuid.uuid4().hex[:16]
        expected=os.getenv('VN_LABOR_API_KEY','').strip()
        if expected and request.url.path!='/health' and request.method!='OPTIONS':
            supplied=request.headers.get('Authorization','')
            if not supplied.startswith('Bearer ') or not secrets.compare_digest(supplied[7:],expected):
                payload = _error_envelope(
                    status_code=401,
                    category="UNAUTHORIZED",
                    message="Invalid or missing bearer token"
                )
                return JSONResponse(status_code=401,content=payload)
        response=await call_next(request)
        response.headers['X-Request-ID']=request.state.request_id
        return response
    @app.get('/health')
    def health(): return {'status':'ok'}
    @app.get('/ready')
    def ready():
        from .deployment import config_fingerprint
        pipeline=state['pipeline']
        if not pipeline: raise HTTPException(503,detail={'ready':False,'error_id':state['error_id']})
        components={'offline_artifacts':'READY','bm25':'LAZY','dense':'LAZY' if pipeline.cfg.retrieval.dense_enabled else 'DISABLED',
          'reranker':'LAZY' if pipeline.cfg.reranker.enabled else 'DISABLED',
          'researcher':_component(pipeline.researcher.provider,'researcher'),
          'auditor':_component(pipeline.applicability.provider,'auditor'),
          'adjudicator':_component(pipeline.adjudicator.provider,'adjudicator')}
        reviewer=getattr(pipeline.adjudicator,'review_provider',None)
        components['answer_reviewer']=_component(reviewer,'answer_reviewer')
        model_components=[components[x] for x in ('researcher','auditor','adjudicator','answer_reviewer')]
        degraded=any(x.get('status')=='DEGRADED' for x in model_components)
        return {'ready':not degraded,'degraded':degraded,'taxonomy_version':TAXONOMY_VERSION,
          'online_source_fingerprint':online_source_fingerprint,
          'online_config_fingerprint':config_fingerprint(pipeline.cfg),
          'online_features':{'conversation_context':'user-turns-v2-short-history','history_storage':'browser',
            'material_fact_confirmation':'confirmed-fields-v1','numeric_task_contract':'task-scoped-money-v1',
            'event_date_roles':'grounded-events-v1','confirmed_task_plan':'batched-preserved-tasks-v2','document_freshness':'dated-public-qualification-v1','dense_query_batching':'deduplicated-batch-v1','default_query_date':'vietnam-current-date-v1','relative_query_dates':'bounded-vietnam-calendar-v1',
            'request_retrieval_cache':'bounded-request-only-v1',
            'routing_topics':TOPIC_REGISTRY_VERSION,'task_completeness':'evidence-and-answer-v1',
            'literal_source_lookup':'verified-excerpt-v1',
            'assessment_fact_gate':'critical-facts-v1','probation_scope':'dated-job-group-v1',
            'answer_grounding':'source-span-selection-v1','applicability_context':'shared-user-statements-v1','gemini_schema_contract':'local-validation-v1','provider_capacity':'paced-retry-v2','gemini_readiness':'diagnostic-probe-v2',
            'request_budget_seconds':pipeline.cfg.request_timeout_seconds,'progress':True,'execution_log':'execution-steps-v1','cooperative_cancel':True,'idempotent_retry':True},
          'quality_policy':{'semantic_review':pipeline.cfg.adjudication.semantic_review and pipeline.cfg.adjudication.mode!='deterministic',
          'semantic_review_provider':pipeline.cfg.adjudication.review_provider,
          'semantic_repair_attempts':pipeline.cfg.adjudication.semantic_repair_attempts,'answer_while_clarifying':pipeline.cfg.answer_while_clarifying,
          'applicability_second_opinion':pipeline.cfg.applicability.unresolved_provider,
          'applicability_batch_size':pipeline.cfg.applicability.max_items,'applicability_max_batches':pipeline.cfg.applicability.max_batches},'components':components,
          'legal_ready':pipeline.store.report.legal_ready,
          'legal_status':pipeline.store.report.legal_status,
          'compatibility':pipeline.store.report.model_dump(mode='json')}
    def request_key(http_request,message_id):
        capability=http_request.headers.get('X-Client-Session','')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',capability):
            return None
        return (hashlib.sha256(capability.encode()).hexdigest(),message_id)

    @app.get('/v1/requests/{message_id}')
    def progress(message_id:str,http_request:Request):
        key=request_key(http_request,message_id)
        entry=requests.get(key) if key else None
        if not entry: raise HTTPException(404,detail='Request not found')
        return {**entry.budget.progress.snapshot(),'state':entry.state,'stage':entry.budget.stage,
          'cancel_requested':entry.budget.cancelled.is_set()}

    @app.post('/v1/requests/{message_id}/cancel')
    def cancel(message_id:str,http_request:Request):
        key=request_key(http_request,message_id)
        entry=requests.get(key) if key else None
        if not entry: raise HTTPException(404,detail='Request not found')
        if entry.state=='RUNNING': entry.budget.cancelled.set()
        return {'state':entry.state,'cancel_requested':entry.budget.cancelled.is_set()}

    @app.post('/v1/answer',response_model=AnswerResponse,summary='Answer a Vietnamese labor-law question')
    def answer(request:QueryRequest,http_request:Request)->AnswerResponse:
        if not state['pipeline']: raise HTTPException(503,detail='ONLINE is not ready')
        seconds=getattr(state['pipeline'].cfg,'request_timeout_seconds',180)
        key=request_key(http_request,request.message_id) if request.message_id else None
        entry=None
        if key:
            from .query_clock import today_vietnam
            identity={'request':request.model_dump(mode='json'),'day':today_vietnam().isoformat() if not request.query_date else None,
              'taxonomy':TAXONOMY_VERSION}
            fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            status,entry=requests.begin(key,fingerprint,seconds)
            if status=='CONFLICT': raise HTTPException(409,detail='Message ID already used for different input')
            if status=='DONE': return entry.result
            if status in {'RUNNING','FULL'}: raise HTTPException(429,detail='Request is already running or service is busy')
        if not answer_slots.acquire(blocking=False):
            if key: requests.finish(key,state='FAILED')
            raise HTTPException(429,detail='The answer service is busy; retry after the current request finishes')
        try:
            with request_budget(seconds,entry.budget if entry else None) as budget:
                http_request.state.execution_budget=budget
                with execution_step('api') as current_step:
                    current_step.finish({'schema':'QueryRequest','dau_ra':'Request đã hợp lệ; bắt đầu ghi sau kiểm tra schema'})
                result=state['pipeline'].ask(request)
                with execution_step('response') as current_step:
                    current_step.finish({'trang_thai':result.status.value,'so_claim':len(result.claims),
                        'so_trich_dan':len(result.citations),'so_canh_bao':len(result.warnings),
                        'legal_status':result.legal_status},'DONE' if result.status.value=='SUFFICIENT' else 'WARNING')
                snapshot=execution_snapshot()
                result.trace.execution_steps=snapshot['steps']
                result.trace.execution_steps_dropped=snapshot['dropped']
            if key: requests.finish(key,result)
            return result
        except BaseException as exc:
            budget=getattr(http_request.state,'execution_budget',None)
            if budget is not None:
                budget.progress.fail_running(exc)
                ident=budget.progress.begin('response')
                budget.progress.finish(ident,public_error(exc),'CANCELLED' if getattr(exc,'reason','')=='REQUEST_CANCELLED' else 'ERROR')
            if key: requests.finish(key,state='FAILED')
            raise
        finally:
            answer_slots.release()
    return SanitizedASGIApplication(app)
