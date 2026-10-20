from contextlib import asynccontextmanager
from pathlib import Path
import hashlib, json, logging, os, re, secrets, threading, uuid
from datetime import date
from .runtime import RequestRegistry,RequestStopped,request_budget
from .config import load_config
from .errors import OnlineError
from .models import AnswerResponse,QueryRequest
from .pipeline import OnlinePipeline
from .taxonomy import TAXONOMY_VERSION
from .topics import VERSION as TOPIC_REGISTRY_VERSION

logger = logging.getLogger(__name__)

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
            logger.error("[%s] ONLINE startup failed: %s",eid,exc,exc_info=True)
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
        logger.warning('[%s] %s stage=%s',getattr(request.state,'request_id','unknown'),exc.reason,exc.stage)
        return JSONResponse(status_code=409 if cancelled else 504,content=_error_envelope(
          409 if cancelled else 504,'CANCELLED' if cancelled else 'TIMEOUT',
          'Yêu cầu đã được dừng.' if cancelled else 'Yêu cầu vượt thời gian xử lý. Chưa có kết luận pháp lý được trả về.',
          details={'stage':exc.stage,'request_id':getattr(request.state,'request_id',None)}))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        payload = _error_envelope(
            status_code=422,
            category="VALIDATION_ERROR",
            message="Dữ liệu yêu cầu không hợp lệ hoặc thiếu trường bắt buộc.",
            details={"errors": jsonable_encoder(exc.errors())}
        )
        return JSONResponse(status_code=422, content=payload)

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
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(OnlineError)
    async def online_error_handler(request: Request, exc: OnlineError):
        eid = f"ERR_{uuid.uuid4().hex[:12].upper()}"
        logger.error(f"[{eid}] OnlineError: {exc}", exc_info=True)
        payload = _error_envelope(
            status_code=503,
            category="SERVICE_UNAVAILABLE",
            message="Hệ thống trực tuyến tạm thời gián đoạn xử lý pháp lý.",
            details={"error_type": type(exc).__name__},
            error_id=eid
        )
        return JSONResponse(status_code=503, content=payload)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        eid = f"ERR_{uuid.uuid4().hex[:12].upper()}"
        logger.error(f"[{eid}] Unhandled exception: {exc}", exc_info=True)
        payload = _error_envelope(
            status_code=500,
            category="INTERNAL_ERROR",
            message="Đã xảy ra lỗi hệ thống nội bộ. Vui lòng thử lại sau.",
            details={"error_id": eid},
            error_id=eid
        )
        return JSONResponse(status_code=500, content=payload)

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
          'online_features':{'conversation_context':'user-turns-v2-short-history','history_storage':'browser',
            'routing_topics':TOPIC_REGISTRY_VERSION,'task_completeness':'evidence-and-answer-v1',
            'literal_source_lookup':'verified-excerpt-v1',
            'request_budget_seconds':pipeline.cfg.request_timeout_seconds,'progress':True,'cooperative_cancel':True,'idempotent_retry':True},
          'quality_policy':{'semantic_review':pipeline.cfg.adjudication.semantic_review and pipeline.cfg.adjudication.mode!='deterministic',
          'semantic_review_provider':pipeline.cfg.adjudication.review_provider,
          'semantic_repair_attempts':pipeline.cfg.adjudication.semantic_repair_attempts,'answer_while_clarifying':pipeline.cfg.answer_while_clarifying,
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
        return {'state':entry.state,'stage':entry.budget.stage,
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
            identity={'request':request.model_dump(mode='json'),'day':date.today().isoformat() if not request.query_date else None,
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
            with request_budget(seconds,entry.budget if entry else None):
                result=state['pipeline'].ask(request)
            if key: requests.finish(key,result)
            return result
        except BaseException:
            if key: requests.finish(key,state='FAILED')
            raise
        finally:
            answer_slots.release()
    return app
