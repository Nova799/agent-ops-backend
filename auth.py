import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

try:
    from .config import API_KEY as MASTER_API_KEY
except ImportError:
    from config import API_KEY as MASTER_API_KEY
try:
    from .crud import verify_api_key
except ImportError:
    from crud import verify_api_key
try:
    from .database import get_db
except ImportError:
    from database import get_db
try:
    from .models import ApiKey, User
except ImportError:
    from models import ApiKey, User

JWT_SECRET = os.getenv("AGENT_OPS_JWT_SECRET", "change-me-in-production-please-use-a-long-secret-key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("AGENT_OPS_JWT_EXPIRE_HOURS", "24"))


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def get_current_user(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    user = db.get(User, payload["sub"]) if False else None
    try:
        from .crud import get_user
    except ImportError:
        from crud import get_user
    user = get_user(db, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    # Dev master key (env) bypass
    if MASTER_API_KEY is not None and x_api_key == MASTER_API_KEY:
        return {"user": None, "api_key": None, "scopes": ["read", "write"]}
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")
    key = verify_api_key(db, x_api_key)
    if key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key")
    return {"user": key.user, "api_key": key, "scopes": key.scopes.split(",")}