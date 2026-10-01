from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from Model.model import TaskPriority, TaskSource, TaskStatus

AIProviderName = Literal["openai", "gemini"]


# ---------- Usuário / Auth ----------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    picture: str | None = None
    is_admin: bool
    timezone: str
    google_connected: bool
    calendar_sync_enabled: bool
    last_calendar_sync_at: datetime | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DevLoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    name: str = Field(default="", max_length=200)


class AuthConfigOut(BaseModel):
    google_enabled: bool
    dev_login_enabled: bool


class UserPreferencesIn(BaseModel):
    timezone: str | None = Field(default=None, max_length=64)
    calendar_sync_enabled: bool | None = None


# ---------- Tarefas ----------
class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    category: str | None = Field(default=None, max_length=80)
    priority: TaskPriority = TaskPriority.medium
    status: TaskStatus = TaskStatus.todo
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool = False
    estimated_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    sync_to_calendar: bool = True

    @model_validator(mode="after")
    def _check_dates(self):
        if self.end_at and not self.start_at:
            raise ValueError("end_at exige start_at")
        if self.start_at and self.end_at and self.end_at < self.start_at:
            raise ValueError("end_at deve ser posterior a start_at")
        return self


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, max_length=80)
    priority: TaskPriority | None = None
    status: TaskStatus | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    sync_to_calendar: bool | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    category: str | None
    priority: TaskPriority
    status: TaskStatus
    source: TaskSource
    start_at: datetime | None
    end_at: datetime | None
    all_day: bool
    estimated_minutes: int | None
    sync_to_calendar: bool
    google_event_id: str | None
    last_synced_at: datetime | None
    sync_error: str | None
    created_at: datetime
    updated_at: datetime


# ---------- Google Agenda ----------
class CalendarSyncResult(BaseModel):
    pushed: int = 0
    imported: int = 0
    updated: int = 0
    deleted: int = 0
    errors: list[str] = []
    synced_at: datetime


class CalendarStatusOut(BaseModel):
    google_oauth_enabled: bool
    connected: bool
    sync_enabled: bool
    last_sync_at: datetime | None


# ---------- IA ----------
class AISuggestionRequest(BaseModel):
    horizon_days: int = Field(default=7, ge=1, le=31)
    work_start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    work_end: str = Field(default="18:00", pattern=r"^\d{2}:\d{2}$")
    goal: str | None = Field(default=None, max_length=500, description="Objetivo/observação livre do usuário")


class AITaskSuggestion(BaseModel):
    task_id: int
    title: str = ""
    start_at: datetime | None = None
    end_at: datetime | None = None
    priority: TaskPriority | None = None
    reason: str = ""


class AISuggestionResponse(BaseModel):
    provider: AIProviderName
    model: str
    summary: str
    suggestions: list[AITaskSuggestion]
    tips: list[str] = []


class AIApplyItem(BaseModel):
    task_id: int
    start_at: datetime | None = None
    end_at: datetime | None = None
    priority: TaskPriority | None = None


class AIApplyRequest(BaseModel):
    items: list[AIApplyItem] = Field(min_length=1, max_length=200)


class AIParseRequest(BaseModel):
    text: str = Field(min_length=2, max_length=1000)


class AIParseResponse(BaseModel):
    provider: AIProviderName
    task: TaskCreate


# ---------- Admin ----------
class AISettingsOut(BaseModel):
    provider: AIProviderName
    openai_model: str
    gemini_model: str
    openai_configured: bool
    gemini_configured: bool


class AISettingsIn(BaseModel):
    provider: AIProviderName
    openai_model: str | None = Field(default=None, min_length=1, max_length=100)
    gemini_model: str | None = Field(default=None, min_length=1, max_length=100)


class LogEntryOut(BaseModel):
    id: str
    ts: str
    level: str
    logger: str
    message: str
    extra: dict | None = None
    exception: str | None = None


class HealthOut(BaseModel):
    status: str
    database: bool
    redis: bool
