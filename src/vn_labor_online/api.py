from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import os
import secrets
import threading

from .config import load_config
from .errors import OnlineError
from .models import AnswerResponse, QueryRequest
from .pipeline import OnlinePipeline


def create_app(config_path: str | Path | None = None):
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    state = {"pipeline": None, "error": None}
    try:
        max_concurrent_answers = max(1, int(os.getenv("VN_LABOR_MAX_CONCURRENT_ANSWERS", "1")))
    except ValueError:
        max_concurrent_answers = 1
    answer_slots = threading.BoundedSemaphore(max_concurrent_answers)

    @asynccontextmanager
    async def lifespan(app):
        try:
            selected = Path(config_path or os.getenv("VN_LABOR_ONLINE_CONFIG", "config/online.yaml"))
            state["pipeline"] = OnlinePipeline(load_config(selected))
        except Exception as exc:
            state["error"] = str(exc)
        yield

    app = FastAPI(title="Vietnamese Labor Legal QA", version="0.2.0", lifespan=lifespan)
    origins = [value.strip() for value in os.getenv(
        "VN_LABOR_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(",") if value.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Accept", "Content-Type", "Authorization", "ngrok-skip-browser-warning"],
        )

    @app.middleware("http")
    async def bearer_auth(request: Request, call_next):
        expected = os.getenv("VN_LABOR_API_KEY", "").strip()
        if expected and request.url.path != "/health" and request.method != "OPTIONS":
            supplied = request.headers.get("Authorization", "")
            if not supplied.startswith("Bearer ") or not secrets.compare_digest(supplied[7:], expected):
                return JSONResponse(status_code=401, content={"detail": "Invalid or missing bearer token"})
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        pipeline = state["pipeline"]
        if not pipeline:
            raise HTTPException(503, detail={"ready": False, "error": state["error"]})
        provider = pipeline.adjudicator.provider
        adjudicator = provider.readiness() if provider else {
            "status": "READY", "provider": "deterministic", "model": None
        }
        return {
            "ready": True,
            "degraded": adjudicator.get("status") == "DEGRADED",
            "components": {
                "offline_artifacts": "READY",
                "bm25": "LAZY",
                "dense": "LAZY" if pipeline.cfg.retrieval.dense_enabled else "DISABLED",
                "adjudicator": adjudicator,
            },
            "compatibility": pipeline.store.report.model_dump(mode="json"),
        }

    @app.post("/v1/answer", response_model=AnswerResponse,
              summary="Answer a Vietnamese labor-law question")
    def answer(request: QueryRequest) -> AnswerResponse:
        if not state["pipeline"]:
            raise HTTPException(503, detail="ONLINE is not ready")
        if not answer_slots.acquire(blocking=False):
            raise HTTPException(429, detail="The answer service is busy; retry after the current request finishes")
        try:
            return state["pipeline"].ask(request)
        except OnlineError as exc:
            raise HTTPException(503, detail=str(exc)) from exc
        finally:
            answer_slots.release()

    return app
