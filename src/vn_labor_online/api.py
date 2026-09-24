from __future__ import annotations
from pathlib import Path
import os
from contextlib import asynccontextmanager
from .config import load_config
from .errors import OnlineError
from .models import QueryRequest,AnswerResponse
from .pipeline import OnlinePipeline

def create_app(config_path:str|Path|None=None):
    from fastapi import FastAPI,HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    state={'pipeline':None,'error':None}
    @asynccontextmanager
    async def lifespan(app):
        try: state['pipeline']=OnlinePipeline(load_config(Path(config_path or os.getenv('VN_LABOR_ONLINE_CONFIG','config/online.yaml'))))
        except Exception as exc: state['error']=str(exc)
        yield
    app=FastAPI(title='Vietnamese Labor Legal QA',version='0.1.0',lifespan=lifespan)
    origins=[value.strip() for value in os.getenv(
      'VN_LABOR_CORS_ORIGINS','http://127.0.0.1:5173,http://localhost:5173').split(',') if value.strip()]
    if origins:
        app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,
          allow_methods=['GET','POST','OPTIONS'],allow_headers=['Accept','Content-Type'])
    @app.get('/health')
    def health(): return {'status':'ok'}
    @app.get('/ready')
    def ready():
        if not state['pipeline']: raise HTTPException(503,detail={'ready':False,'error':state['error']})
        return {'ready':True,'compatibility':state['pipeline'].store.report.model_dump(mode='json')}
    @app.post('/v1/answer',response_model=AnswerResponse,summary='Answer a Vietnamese labor-law question')
    def answer(request:QueryRequest)->AnswerResponse:
        if not state['pipeline']: raise HTTPException(503,detail='ONLINE is not ready')
        try: return state['pipeline'].ask(request)
        except OnlineError as exc: raise HTTPException(503,detail=str(exc)) from exc
    return app
