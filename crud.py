import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from .models import ApiKey, AuditLog, Trace, Step, User
except ImportError:
    from models import ApiKey, Trace, Step, User


def create_trace(db: Session, session_name: str, metadata: dict, api_key: Optional[str], owner_user_id: Optional[str] = None) -> Trace:
    trace = Trace(
        id=str(uuid.uuid4()),
        session_name=session_name,
        metadata_=metadata or {},
        api_key=api_key,
        owner_user_id=owner_user_id,
        status="active",
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    db.execute(
        text("INSERT INTO trace_fts(trace_id, session_name, content) VALUES (:tid, :sn, :c)"),
        {"tid": trace.id, "sn": trace.session_name, "c": ""},
    )
    db.commit()
    return trace


def get_trace(db: Session, trace_id: str) -> Optional[Trace]:
    return db.get(Trace, trace_id)


def list_traces(db: Session, limit: int = 50, offset: int = 0, api_key: Optional[str] = None, user_id: Optional[str] = None) -> List[Trace]:
    q = db.query(Trace)
    if user_id is not None:
        q = q.filter(Trace.owner_user_id == user_id)
    elif api_key is not None:
        q = q.filter(Trace.api_key == api_key)
    return q.order_by(Trace.started_at.desc()).offset(offset).limit(limit).all()


def end_trace(db: Session, trace_id: str, status: str = "completed") -> Optional[Trace]:
    trace = db.get(Trace, trace_id)
    if trace is None:
        return None
    trace.status = status
    trace.ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(trace)
    return trace


def delete_trace(db: Session, trace_id: str) -> bool:
    trace = db.get(Trace, trace_id)
    if trace is None:
        return False
    db.execute(text("DELETE FROM trace_fts WHERE trace_id = :tid"), {"tid": trace_id})
    db.delete(trace)
    db.commit()
    return True


def add_step(db: Session, trace_id: str, thought, action, observation, state_snapshot,
             prompt_tokens=0, completion_tokens=0, model=None, cost_usd=0.0) -> Step:
    trace = db.get(Trace, trace_id)
    if trace is None:
        raise ValueError("trace not found")
    next_index = len(trace.steps)
    step = Step(
        trace_id=trace_id,
        step_index=next_index,
        thought=thought,
        action=action,
        observation=observation,
        state_snapshot=state_snapshot or {},
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=model,
        cost_usd=str(cost_usd),
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    db.refresh(trace)
    _rebuild_fts(db, trace)
    return step


def add_steps(db: Session, items: list) -> list:
    results = []
    traces_to_rebuild = set()
    for it in items:
        trace = db.get(Trace, it.trace_id)
        if trace is None:
            raise ValueError("trace not found")
        next_index = len(trace.steps)
        step = Step(
            trace_id=it.trace_id,
            step_index=next_index,
            thought=it.thought,
            action=it.action,
            observation=it.observation,
            state_snapshot=it.state_snapshot or {},
            prompt_tokens=getattr(it, "prompt_tokens", 0),
            completion_tokens=getattr(it, "completion_tokens", 0),
            model=getattr(it, "model", None),
            cost_usd=str(getattr(it, "cost_usd", 0.0)),
        )
        db.add(step)
        traces_to_rebuild.add(it.trace_id)
        results.append(step)
    db.commit()
    for tid in traces_to_rebuild:
        t = db.get(Trace, tid)
        if t is not None:
            db.refresh(t)
            _rebuild_fts(db, t)
    return results


def _rebuild_fts(db: Session, trace: Trace):
    parts = []
    for s in trace.steps:
        parts.extend([s.thought or "", s.action or "", s.observation or ""])
    content = " ".join(p for p in parts if p)
    db.execute(text("DELETE FROM trace_fts WHERE trace_id = :tid"), {"tid": trace.id})
    db.execute(
        text("INSERT INTO trace_fts(trace_id, session_name, content) VALUES (:tid, :sn, :c)"),
        {"tid": trace.id, "sn": trace.session_name, "c": content},
    )
    db.commit()


def search_traces(db: Session, q: str, limit: int = 50, offset: int = 0, user_id: Optional[str] = None) -> List[Trace]:
    if not q.strip():
        return list_traces(db, limit=limit, offset=offset, user_id=user_id)
    rows = db.execute(
        text("SELECT trace_id FROM trace_fts WHERE trace_fts MATCH :q"),
        {"q": q},
    ).fetchall()
    ids = [r[0] for r in rows]
    if not ids:
        return []
    query = db.query(Trace).filter(Trace.id.in_(ids))
    if user_id is not None:
        query = query.filter(Trace.owner_user_id == user_id)
    return query.order_by(Trace.started_at.desc()).offset(offset).limit(limit).all()


def get_metrics(db: Session, user_id: Optional[str] = None) -> dict:
    q = db.query(Trace)
    if user_id is not None:
        q = q.filter(Trace.owner_user_id == user_id)
    traces = q.all()
    total_steps = sum(len(t.steps) for t in traces)
    errors = sum(1 for t in traces if t.status == "error")
    completed = sum(1 for t in traces if t.status == "completed")
    return {
        "trace_count": len(traces),
        "step_count": total_steps,
        "avg_steps": (total_steps / len(traces)) if traces else 0,
        "completed": completed,
        "errors": errors,
    }


def purge_old_traces(db: Session, days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    old = db.query(Trace).filter(Trace.started_at < cutoff).all()
    count = 0
    for t in old:
        db.execute(text("DELETE FROM trace_fts WHERE trace_id = :tid"), {"tid": t.id})
        db.delete(t)
        count += 1
    db.commit()
    return count


# ---- Users & API keys ----

def create_user(db: Session, email: str, password: str) -> User:
    salt = secrets.token_hex(16)
    user = User(
        id=str(uuid.uuid4()),
        email=email.lower().strip(),
        password_hash=User.hash_password(password, salt),
        salt=salt,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.lower().strip()).first()


def get_user(db: Session, user_id: str) -> Optional[User]:
    return db.get(User, user_id)


def create_api_key(db: Session, user_id: str, name: str, scopes: str = "read,write") -> tuple[ApiKey, str]:
    raw = "ak_" + secrets.token_urlsafe(32)
    key = ApiKey(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        key_hash=ApiKey.hash_key(raw),
        key_prefix=raw[:10],
        scopes=scopes,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return key, raw


def list_api_keys(db: Session, user_id: str) -> List[ApiKey]:
    return db.query(ApiKey).filter(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc()).all()


def revoke_api_key(db: Session, key_id: str, user_id: str) -> bool:
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user_id).first()
    if key is None or key.is_revoked:
        return False
    key.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True


def log_audit(db: Session, user_id: Optional[str], action: str, resource: Optional[str] = None, ip: Optional[str] = None):
    entry = AuditLog(user_id=user_id, action=action, resource=resource, ip=ip)
    db.add(entry)
    db.commit()


def verify_api_key(db: Session, raw_key: str) -> Optional[ApiKey]:
    key_hash = ApiKey.hash_key(raw_key)
    key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
    if key is None or key.is_revoked:
        return None
    return key