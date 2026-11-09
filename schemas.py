from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TraceCreate(BaseModel):
    session_name: str = Field(..., min_length=1, max_length=255)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TraceEnd(BaseModel):
    status: str = "completed"


class StepCreate(BaseModel):
    trace_id: str
    thought: Optional[str] = None
    action: Optional[str] = None
    observation: Optional[str] = None
    state_snapshot: Dict[str, Any] = Field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: Optional[str] = None
    cost_usd: float = 0.0


class StepBatchCreate(BaseModel):
    steps: List[StepCreate]


class StepOut(BaseModel):
    id: int
    trace_id: str
    step_index: int
    thought: Optional[str]
    action: Optional[str]
    observation: Optional[str]
    state_snapshot: Dict[str, Any]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: Optional[str] = None
    cost_usd: float = 0.0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TraceOut(BaseModel):
    id: str
    session_name: str
    metadata: Dict[str, Any]
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    step_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class TraceDetail(TraceOut):
    steps: List[StepOut] = []