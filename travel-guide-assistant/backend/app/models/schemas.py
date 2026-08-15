from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DayPlan(BaseModel):
    day: int = Field(ge=1, le=30)
    title: str
    activities: list[str] = Field(default_factory=list)
    transport: Optional[str] = None
    budget: Optional[float] = None


class Itinerary(BaseModel):
    destination: str
    days: int = Field(ge=1, le=30)
    total_budget: Optional[float] = None
    day_plans: list[DayPlan] = Field(default_factory=list)
    tips: Optional[list[str]] = None


class Trip(Itinerary):
    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Citation(BaseModel):
    source_id: str
    title: str


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)
    session_id: Optional[str] = None

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message cannot be blank")
        return value.strip()


class ChatMessageEvent(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)


class ChatDoneEvent(BaseModel):
    id: str
    usage: dict


class ChatErrorEvent(BaseModel):
    code: str
    message: str
