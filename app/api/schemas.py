"""Request/response models. Validation here is the first line of defence against bad input."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

ID_PATTERN = r"^[A-Za-z0-9_.:-]{1,64}$"


class ChatRequest(BaseModel):
    user_id: str = Field(..., pattern=ID_PATTERN, examples=["user-123"])
    session_id: str = Field(..., pattern=ID_PATTERN, examples=["session-456"])
    message: str = Field(..., min_length=1, max_length=2000, examples=["What should I focus on in my career?"])

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank")
        return v.strip()


class MemoryUpdate(BaseModel):
    action: str
    kind: str
    key: str
    title: str
    detail: str = ""


class ChatResponse(BaseModel):
    response: str
    user_id: str
    session_id: str
    context_used: list[str]
    # --- extensions -----------------------------------------------------------
    context_details: list[dict[str, Any]] = []
    memory_updates: list[MemoryUpdate] = []
    intent: str
    life_areas: list[str] = []
    missing_profile_fields: list[str] = []
    llm_provider: str
    llm_model: str
    degraded: bool = False
    brain_available: bool = True
    warnings: list[str] = []
    latency_ms: int = 0


class ProfileIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    date_of_birth: Optional[date] = Field(None, examples=["1995-08-15"])
    time_of_birth: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$", examples=["10:30"])
    birth_place: Optional[str] = Field(None, min_length=1, max_length=80)
    preferred_language: Optional[str] = Field(None, min_length=2, max_length=30, examples=["Hindi"])

    @field_validator("date_of_birth")
    @classmethod
    def not_future(cls, v: Optional[date]) -> Optional[date]:
        if v and (v > date.today() or v.year < 1900):
            raise ValueError("date_of_birth must be between 1900 and today")
        return v


class UserCreate(ProfileIn):
    user_id: str = Field(..., pattern=ID_PATTERN, examples=["user-123"])


class UserOut(BaseModel):
    user_id: str
    name: Optional[str] = None
    date_of_birth: Optional[str] = None
    time_of_birth: Optional[str] = None
    birth_place: Optional[str] = None
    preferred_language: Optional[str] = None
    sun_sign: Optional[str] = None
    astrology: dict[str, Any] = {}
    missing_profile_fields: list[str] = []
