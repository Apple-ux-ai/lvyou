from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class PlannedStop(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    visit_time: Optional[str] = Field(default=None, pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    category: Literal["ticket", "food", "stay", "transport", "other"] = "other"
    budget: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)


class DayPlan(BaseModel):
    day: int = Field(ge=1, le=30)
    title: str
    activities: list[str] = Field(default_factory=list)
    stops: Optional[list[PlannedStop]] = Field(default=None, max_length=100)
    transport: Optional[str] = None
    budget: Optional[float] = None


class Itinerary(BaseModel):
    destination: str
    days: int = Field(ge=1, le=30)
    total_budget: Optional[float] = None
    start_date: Optional[date] = Field(default=None, le=date(9999, 12, 1))
    adult_count: Optional[int] = Field(default=None, ge=1, le=99)
    attraction_cap_jpy: Optional[int] = Field(default=None, ge=0, le=100000000)
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
