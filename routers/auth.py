from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

try:
    from ..auth import create_access_token, get_current_user
except ImportError:
    from auth import create_access_token, get_current_user
try:
    from ..crud import create_api_key, create_user, get_user_by_email, list_api_keys, log_audit, revoke_api_key
except ImportError:
    from crud import create_api_key, create_user, get_user_by_email, list_api_keys, log_audit, revoke_api_key
try:
    from ..database import get_db
except ImportError:
    from database import get_db
try:
    from ..models import User
except ImportError:
    from models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str
    password: str = Field(..., min_length=8)


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ApiKeyCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    scopes: str = "read,write"


class ApiKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: str
    created_at: str
    revoked: bool


@router.post("/register", response_model=TokenOut, status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if get_user_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = create_user(db, payload.email, payload.password)
    log_audit(db, user.id, "register", payload.email)
    return TokenOut(access_token=create_access_token(user.id, user.email))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = get_user_by_email(db, payload.email)
    if user is None or not user.verify_password(payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User inactive")
    log_audit(db, user.id, "login", user.email)
    return TokenOut(access_token=create_access_token(user.id, user.email))


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email}


@router.post("/keys", status_code=201)
def create_key(payload: ApiKeyCreateIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key, raw = create_api_key(db, current_user.id, payload.name, payload.scopes)
    log_audit(db, current_user.id, "create_api_key", key.id)
    return {"id": key.id, "name": key.name, "key": raw, "key_prefix": key.key_prefix, "scopes": key.scopes}


@router.get("/keys")
def list_keys(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = list_api_keys(db, current_user.id)
    return [
        {"id": k.id, "name": k.name, "key_prefix": k.key_prefix, "scopes": k.scopes,
         "created_at": k.created_at.isoformat(), "revoked": k.is_revoked}
        for k in keys
    ]


@router.delete("/keys/{key_id}", status_code=204)
def revoke_key(key_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not revoke_api_key(db, key_id, current_user.id):
        raise HTTPException(status_code=404, detail="key not found or already revoked")
    log_audit(db, current_user.id, "revoke_api_key", key_id)