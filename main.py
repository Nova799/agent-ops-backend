import logging
from contextlib import asynccontextmanager
from pathlib import Path
from time import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

try:
    from .config import CORS_ORIGINS, RATE_LIMIT_PER_MIN, RETENTION_DAYS
    from .database import SessionLocal, init_db
except ImportError:
    from config import CORS_ORIGINS, RETENTION_DAYS
    from database import SessionLocal, init_db
try:
    from .routers.auth import router as auth_router
    from .routers.traces import router as traces_router
    from .routers.ws import router as ws_router
except ImportError:
    from routers.auth import router as auth_router
    from routers.traces import router as traces_router
    from routers.ws import router as ws_router

_METRICS = {"requests": 0, "errors": 0, "total_latency": 0.0, "started": time()}
_RATE_BUCKET: dict = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("agentops")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting agentops backend")
    init_db()
    if RETENTION_DAYS and RETENTION_DAYS > 0:
        from .crud import purge_old_traces
        db = SessionLocal()
        try:
            purge_old_traces(db, RETENTION_DAYS)
        finally:
            db.close()
    yield


app = FastAPI(title="AgentOps Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time()
    _METRICS["requests"] += 1
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            _METRICS["errors"] += 1
        return response
    except Exception:
        _METRICS["errors"] += 1
        raise
    finally:
        _METRICS["total_latency"] += time() - start


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if RATE_LIMIT_PER_MIN <= 0:
        return await call_next(request)
    key = request.headers.get("x-api-key") or request.client.host if request.client else "anon"
    now = time()
    window = 60.0
    bucket = _RATE_BUCKET.get(key)
    if bucket is None or now - bucket["start"] > window:
        bucket = {"start": now, "count": 0}
        _RATE_BUCKET[key] = bucket
    bucket["count"] += 1
    if bucket["count"] > RATE_LIMIT_PER_MIN:
        return Response(content='{"detail":"rate limit exceeded"}', status_code=429, media_type="application/json")
    return await call_next(request)


app.include_router(auth_router)
app.include_router(traces_router)
app.include_router(ws_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "agentops-backend"}


@app.get("/health/live")
def health_live():
    return {"status": "alive"}


@app.get("/health/ready")
def health_ready():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "ready", "database": "ok"}
    except Exception as e:  # noqa: BLE001
        return Response(content=f'{{"status":"not_ready","error":"{e}"}}', status_code=503, media_type="application/json")


@app.get("/metrics")
def metrics():
    db = SessionLocal()
    try:
        trace_count = db.execute(text("SELECT COUNT(*) FROM traces")).scalar() or 0
        step_count = db.execute(text("SELECT COUNT(*) FROM steps")).scalar() or 0
    finally:
        db.close()
    avg = (_METRICS["total_latency"] / _METRICS["requests"]) if _METRICS["requests"] else 0.0
    lines = [
        "# HELP agentops_requests_total Total HTTP requests",
        "# TYPE agentops_requests_total counter",
        f"agentops_requests_total {_METRICS['requests']}",
        "# HELP agentops_errors_total Total 5xx errors",
        "# TYPE agentops_errors_total counter",
        f"agentops_errors_total {_METRICS['errors']}",
        "# HELP agentops_request_latency_seconds_avg Average request latency",
        "# TYPE agentops_request_latency_seconds_avg gauge",
        f"agentops_request_latency_seconds_avg {avg:.6f}",
        "# HELP agentops_traces_total Total traces stored",
        "# TYPE agentops_traces_total gauge",
        f"agentops_traces_total {trace_count}",
        "# HELP agentops_steps_total Total steps stored",
        "# TYPE agentops_steps_total gauge",
        f"agentops_steps_total {step_count}",
        "# HELP agentops_uptime_seconds Uptime",
        "# TYPE agentops_uptime_seconds gauge",
        f"agentops_uptime_seconds {time() - _METRICS['started']:.2f}",
    ]
    return PlainTextResponse("\n".join(lines) + "\n")


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    index = static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)