from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
import logging, os, secrets, threading, uuid
from .config import load_config
from .errors import OnlineError
from .models import AnswerResponse,QueryRequest
from .pipeline import OnlinePipeline

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
    @asynccontextmanager
    async def lifespan(app):
        try:
            selected=Path(config_path or os.getenv('VN_LABOR_ONLINE_CONFIG','config/online.yaml'))
            state['pipeline']=OnlinePipeline(load_config(selected))
        except Exception as exc:
            eid=f"ERR_{uuid.uuid4().hex[:12].upper()}"
            state['error_id']=eid
            logger.error("[%s] ONLINE startup failed: %s",eid,exc,exc_info=True)
        yield
    app=FastAPI(title='Vietnamese Labor Legal QA',version='0.3.0',lifespan=lifespan)
    origins=[value.strip() for value in os.getenv('VN_LABOR_CORS_ORIGINS','http://127.0.0.1:5173,http://localhost:5173').split(',') if value.strip()]
    if origins:
        app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,allow_methods=['GET','POST','OPTIONS'],
          allow_headers=['Accept','Content-Type','Authorization','ngrok-skip-browser-warning'])

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
        return await call_next(request)
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
        model_components=[components[x] for x in ('researcher','auditor','adjudicator')]
        degraded=any(x.get('status')=='DEGRADED' for x in model_components)
        return {'ready':not degraded,'degraded':degraded,'components':components,
          'compatibility':pipeline.store.report.model_dump(mode='json')}
    @app.post('/v1/answer',response_model=AnswerResponse,summary='Answer a Vietnamese labor-law question')
    def answer(request:QueryRequest)->AnswerResponse:
        if not state['pipeline']: raise HTTPException(503,detail='ONLINE is not ready')
        if not answer_slots.acquire(blocking=False): raise HTTPException(429,detail='The answer service is busy; retry after the current request finishes')
        try: return state['pipeline'].ask(request)
        finally: answer_slots.release()
    return app
