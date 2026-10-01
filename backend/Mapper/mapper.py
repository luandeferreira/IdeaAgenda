"""Conversões entre modelos, DTOs e eventos do Google Agenda."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from Dto.dto import TaskCreate, TaskOut, UserOut
from Model.model import Task, TaskPriority, TaskStatus, User

APP_MARKER_KEY = "ideaagenda_task_id"

# Cores do Google Agenda por prioridade (colorId)
PRIORITY_COLORS = {TaskPriority.high: "11", TaskPriority.medium: "5", TaskPriority.low: "2"}


def as_utc(value: datetime | None) -> datetime | None:
    """Garante datetime com timezone UTC (bancos como SQLite devolvem datetimes 'naive')."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def safe_zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def user_to_dto(user: User) -> UserOut:
    return UserOut.model_validate(user)


def task_to_dto(task: Task) -> TaskOut:
    dto = TaskOut.model_validate(task)
    dto.start_at = as_utc(dto.start_at)
    dto.end_at = as_utc(dto.end_at)
    dto.last_synced_at = as_utc(dto.last_synced_at)
    dto.created_at = as_utc(dto.created_at)
    dto.updated_at = as_utc(dto.updated_at)
    return dto


def create_dto_to_task(dto: TaskCreate, user_id: int) -> Task:
    data = dto.model_dump()
    data["start_at"] = as_utc(data["start_at"])
    data["end_at"] = as_utc(data["end_at"])
    return Task(user_id=user_id, **data)


def default_end(task: Task) -> datetime | None:
    start = as_utc(task.start_at)
    if start is None:
        return None
    if task.end_at:
        return as_utc(task.end_at)
    minutes = task.estimated_minutes or 60
    return start + timedelta(minutes=minutes)


def task_to_google_event(task: Task, tz_name: str) -> dict:
    """Monta o corpo de um evento do Google Calendar a partir de uma tarefa."""
    zone = safe_zone(tz_name)
    start = as_utc(task.start_at)
    if start is None:
        raise ValueError("Tarefa sem data não pode ser sincronizada")

    prefix = "✅ " if task.status == TaskStatus.done else ""
    body: dict = {
        "summary": f"{prefix}{task.title}",
        "description": task.description or "",
        "colorId": PRIORITY_COLORS.get(task.priority, "5"),
        "extendedProperties": {"private": {APP_MARKER_KEY: str(task.id)}},
    }
    if task.all_day:
        start_date = start.astimezone(zone).date()
        end_dt = as_utc(task.end_at)
        end_date = end_dt.astimezone(zone).date() if end_dt else start_date
        if end_date < start_date:
            end_date = start_date
        # No Google a data final de eventos de dia inteiro é exclusiva
        body["start"] = {"date": start_date.isoformat()}
        body["end"] = {"date": (end_date + timedelta(days=1)).isoformat()}
    else:
        end = default_end(task)
        body["start"] = {"dateTime": start.astimezone(zone).isoformat(), "timeZone": zone.key}
        body["end"] = {"dateTime": end.astimezone(zone).isoformat(), "timeZone": zone.key}
    return body


def _parse_google_time(value: dict, zone: ZoneInfo) -> tuple[datetime | None, bool]:
    if not value:
        return None, False
    if "dateTime" in value:
        dt = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=safe_zone(value.get("timeZone") or zone.key))
        return dt.astimezone(timezone.utc), False
    if "date" in value:
        d = date.fromisoformat(value["date"])
        return datetime.combine(d, time.min, tzinfo=zone).astimezone(timezone.utc), True
    return None, False


def google_event_to_fields(event: dict, tz_name: str) -> dict:
    """Extrai campos de tarefa de um evento do Google."""
    zone = safe_zone(tz_name)
    start, all_day = _parse_google_time(event.get("start", {}), zone)
    end, _ = _parse_google_time(event.get("end", {}), zone)
    if all_day and end is not None:
        # converte a data final exclusiva em inclusiva
        end = end - timedelta(days=1)
    title = (event.get("summary") or "(sem título)").strip()
    status = TaskStatus.todo
    if title.startswith("✅"):
        title = title.lstrip("✅").strip() or "(sem título)"
        status = TaskStatus.done
    return {
        "title": title[:300],
        "description": (event.get("description") or "")[:5000],
        "start_at": start,
        "end_at": end,
        "all_day": all_day,
        "status": status,
    }


def google_event_updated_at(event: dict) -> datetime | None:
    raw = event.get("updated")
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
