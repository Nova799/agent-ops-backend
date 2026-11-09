from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

try:
    from ..auth import require_api_key
    from ..routers.ws import broadcast
except ImportError:
    from auth import require_api_key
    from routers.ws import broadcast
try:
    from ..crud import add_step, create_trace, delete_trace, end_trace, get_trace, get_metrics, list_traces, log_audit, purge_old_traces, search_traces
except ImportError:
    from crud import add_step, create_trace, delete_trace, end_trace, get_trace, get_metrics, list_traces, log_audit, purge_old_traces, search_traces
try:
    from ..database import get_db
except ImportError:
    from database import get_db
try:
    from ..models import Trace
except ImportError:
    from models import Trace
try:
    from ..schemas import StepBatchCreate, StepCreate, StepOut, TraceCreate, TraceDetail, TraceEnd, TraceOut
except ImportError:
    from schemas import StepBatchCreate, StepCreate, StepOut, TraceCreate, TraceDetail, TraceEnd, TraceOut

router = APIRouter(prefix="/api", tags=["traces"], dependencies=[Depends(require_api_key)])


def _trace_out(trace: Trace) -> TraceOut:
    return TraceOut(
        id=trace.id,
        session_name=trace.session_name,
        metadata=trace.metadata_ or {},
        status=trace.status,
        started_at=trace.started_at,
        ended_at=trace.ended_at,
        step_count=len(trace.steps),
    )


@router.get("/health")
def health():
    return {"status": "ok"}


import asyncio

@router.post("/trace", response_model=TraceOut, status_code=201)
async def create_trace_endpoint(payload: TraceCreate, auth=Depends(require_api_key), db: Session = Depends(get_db)):
    user_id = auth["user"].id if auth.get("user") else None
    trace = create_trace(db, payload.session_name, payload.metadata, None, owner_user_id=user_id)
    out = _trace_out(trace)
    asyncio.create_task(broadcast({"type": "trace_created", "trace": out.model_dump(mode="json")}))
    return out


@router.post("/log", response_model=StepOut, status_code=201)
async def log_step_endpoint(payload: StepCreate, db: Session = Depends(get_db)):
    try:
        step = add_step(
            db,
            payload.trace_id,
            payload.thought,
            payload.action,
            payload.observation,
            payload.state_snapshot,
            prompt_tokens=payload.prompt_tokens,
            completion_tokens=payload.completion_tokens,
            model=payload.model,
            cost_usd=payload.cost_usd,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="trace not found")
    out = step
    asyncio.create_task(broadcast({"type": "step_logged", "step": StepOut.model_validate(step).model_dump(mode="json")}))
    return out


@router.post("/logs/batch", response_model=list[StepOut], status_code=201)
def log_batch_endpoint(payload: StepBatchCreate, db: Session = Depends(get_db)):
    try:
        steps = add_steps(db, payload.steps)
    except ValueError:
        raise HTTPException(status_code=404, detail="trace not found")
    return steps


@router.post("/trace/{trace_id}/end", response_model=TraceOut)
def end_trace_endpoint(trace_id: str, payload: TraceEnd = TraceEnd(), db: Session = Depends(get_db)):
    trace = end_trace(db, trace_id, payload.status)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return _trace_out(trace)


@router.get("/traces", response_model=list[TraceOut])
def list_traces_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    auth=Depends(require_api_key),
):
    user_id = auth["user"].id if auth.get("user") else None
    traces = list_traces(db, limit=limit, offset=offset, user_id=user_id)
    return [_trace_out(t) for t in traces]


@router.get("/traces/{trace_id}", response_model=TraceDetail)
def get_trace_endpoint(trace_id: str, db: Session = Depends(get_db)):
    trace = get_trace(db, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return TraceDetail(
        id=trace.id,
        session_name=trace.session_name,
        metadata=trace.metadata_ or {},
        status=trace.status,
        started_at=trace.started_at,
        ended_at=trace.ended_at,
        step_count=len(trace.steps),
        steps=trace.steps,
    )


@router.delete("/traces/{trace_id}", status_code=204)
def delete_trace_endpoint(trace_id: str, db: Session = Depends(get_db), auth=Depends(require_api_key)):
    if not delete_trace(db, trace_id):
        raise HTTPException(status_code=404, detail="trace not found")
    uid = auth["user"].id if auth.get("user") else None
    log_audit(db, uid, "delete_trace", trace_id)


@router.get("/traces/search", response_model=list[TraceOut])
def search_traces_endpoint(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    auth=Depends(require_api_key),
):
    user_id = auth["user"].id if auth.get("user") else None
    traces = search_traces(db, q, limit=limit, offset=offset, user_id=user_id)
    return [_trace_out(t) for t in traces]


@router.get("/metrics")
def metrics_endpoint(db: Session = Depends(get_db), auth=Depends(require_api_key)):
    user_id = auth["user"].id if auth.get("user") else None
    return get_metrics(db, user_id=user_id)


@router.post("/traces/{trace_id}/replay", response_model=TraceOut, status_code=201)
def replay_trace_endpoint(trace_id: str, db: Session = Depends(get_db), auth=Depends(require_api_key)):
    src = get_trace(db, trace_id)
    if src is None:
        raise HTTPException(status_code=404, detail="trace not found")
    user_id = auth["user"].id if auth.get("user") else None
    new_trace = create_trace(db, f"replay of {src.session_name}", src.metadata_ or {}, None, owner_user_id=user_id)
    for s in src.steps:
        add_step(
            db,
            new_trace.id,
            s.thought,
            s.action,
            s.observation,
            s.state_snapshot or {},
            prompt_tokens=s.prompt_tokens,
            completion_tokens=s.completion_tokens,
            model=s.model,
            cost_usd=float(s.cost_usd or 0),
        )
    end_trace(db, new_trace.id, "completed")
    db.refresh(new_trace)
    return _trace_out(new_trace)