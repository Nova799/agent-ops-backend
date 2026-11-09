import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean, Index
from sqlalchemy.orm import relationship

try:
    from .database import Base
except ImportError:
    from database import Base


class Trace(Base):
    __tablename__ = "traces"
    __table_args__ = (
        Index("ix_traces_started_at", "started_at"),
        Index("ix_traces_session_name", "session_name"),
    )

    id = Column(String(36), primary_key=True)
    session_name = Column(String(255), nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)
    api_key = Column(String(255), nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(32), default="active")
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)

    steps = relationship("Step", back_populates="trace", cascade="all, delete-orphan", order_by="Step.step_index")
    owner = relationship("User", back_populates="traces")


class Step(Base):
    __tablename__ = "steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(36), ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    thought = Column(Text, nullable=True)
    action = Column(String(255), nullable=True)
    observation = Column(Text, nullable=True)
    state_snapshot = Column(JSON, default=dict)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    model = Column(String(120), nullable=True)
    cost_usd = Column(String(32), default="0")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    trace = relationship("Trace", back_populates="steps")


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(64), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    traces = relationship("Trace", back_populates="owner")

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()

    def verify_password(self, password: str) -> bool:
        return secrets.compare_digest(self.password_hash, self.hash_password(password, self.salt))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=True, index=True)
    action = Column(String(120), nullable=False)
    resource = Column(String(255), nullable=True)
    ip = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    key_prefix = Column(String(12), nullable=False)
    scopes = Column(String(255), default="read,write")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    revoked_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="api_keys")

    @staticmethod
    def hash_key(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None