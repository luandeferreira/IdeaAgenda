from datetime import datetime, timezone

from Mapper.mapper import google_event_to_fields, task_to_google_event
from Model.model import Task, TaskPriority, TaskStatus


def test_task_to_event_timed():
    task = Task(id=7, title="Reunião", description="", priority=TaskPriority.high, status=TaskStatus.todo,
                start_at=datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc), end_at=None, all_day=False, estimated_minutes=30)
    body = task_to_google_event(task, "America/Sao_Paulo")
    assert body["start"]["dateTime"] == "2030-01-01T09:00:00-03:00"
    assert body["end"]["dateTime"] == "2030-01-01T09:30:00-03:00"
    assert body["colorId"] == "11"
    assert body["extendedProperties"]["private"]["ideaagenda_task_id"] == "7"


def test_task_to_event_all_day_and_back():
    task = Task(id=1, title="Feriado", description="", priority=TaskPriority.low, status=TaskStatus.done,
                start_at=datetime(2030, 1, 1, 3, 0, tzinfo=timezone.utc), end_at=None, all_day=True)
    body = task_to_google_event(task, "America/Sao_Paulo")
    assert body["start"] == {"date": "2030-01-01"} and body["end"] == {"date": "2030-01-02"}
    assert body["summary"] == "✅ Feriado"

    fields = google_event_to_fields(body, "America/Sao_Paulo")
    assert fields["title"] == "Feriado" and fields["status"] == TaskStatus.done
    assert fields["all_day"] is True
    assert fields["start_at"] == datetime(2030, 1, 1, 3, 0, tzinfo=timezone.utc)
    assert fields["end_at"] == fields["start_at"]
