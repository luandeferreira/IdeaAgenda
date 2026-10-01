"""Testa a sincronização bidirecional usando um Google Calendar falso (httpx.MockTransport)."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from Config.database import async_session_maker
from Config.settings import get_settings
from Model.model import User
from Service import calendar_service
from Service.security import encrypt
from tests.conftest import login


class FakeGoogleCalendar:
    def __init__(self):
        self.events: dict[str, dict] = {}
        self.counter = 0
        self.refreshes = 0

    def _now(self):
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://oauth2.googleapis.com/token"):
            self.refreshes += 1
            return httpx.Response(200, json={"access_token": "new-token", "expires_in": 3600})
        assert request.headers["Authorization"].startswith("Bearer ")
        path = request.url.path
        base = "/calendar/v3/calendars/primary/events"
        if request.method == "POST" and path == base:
            self.counter += 1
            body = json.loads(request.content)
            event = {**body, "id": f"evt{self.counter}", "etag": f'"{self.counter}"', "status": "confirmed", "updated": self._now()}
            self.events[event["id"]] = event
            return httpx.Response(200, json=event)
        if request.method == "GET" and path == base:
            return httpx.Response(200, json={"items": list(self.events.values())})
        event_id = path.rsplit("/", 1)[-1]
        if event_id not in self.events:
            return httpx.Response(404, json={})
        if request.method == "PATCH":
            self.counter += 1
            self.events[event_id].update(json.loads(request.content))
            self.events[event_id].update({"etag": f'"{self.counter}"', "updated": self._now()})
            return httpx.Response(200, json=self.events[event_id])
        if request.method == "DELETE":
            self.events[event_id]["status"] = "cancelled"
            return httpx.Response(204)
        return httpx.Response(400)

    def add_external(self, summary: str, start: datetime):
        self.counter += 1
        eid = f"ext{self.counter}"
        self.events[eid] = {
            "id": eid, "etag": f'"{self.counter}"', "status": "confirmed", "summary": summary, "updated": self._now(),
            "start": {"dateTime": start.isoformat()}, "end": {"dateTime": (start + timedelta(hours=1)).isoformat()},
        }
        return eid


@pytest.fixture
def google(monkeypatch):
    fake = FakeGoogleCalendar()
    monkeypatch.setattr(calendar_service, "http_client_factory", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "cid")
    monkeypatch.setattr(settings, "google_client_secret", "csecret")
    return fake


async def _connect_google(email: str):
    async with async_session_maker() as db:
        user = await db.scalar(select(User).where(User.email == email))
        user.google_refresh_token = encrypt("refresh")
        user.google_access_token = encrypt("old")
        user.google_token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        await db.commit()


async def test_full_calendar_sync(client, google):
    headers, _ = await login(client, "cal@x.dev")
    status = (await client.get("/api/calendar/status", headers=headers)).json()
    assert status["connected"] is False
    assert (await client.post("/api/calendar/sync", headers=headers)).status_code == 400

    await _connect_google("cal@x.dev")

    # Criar tarefa com data envia evento imediatamente
    start = datetime.now(timezone.utc) + timedelta(days=1)
    task = (await client.post("/api/tasks", headers=headers, json={"title": "Reunião", "start_at": start.isoformat()})).json()
    assert task["google_event_id"] == "evt1"
    assert google.refreshes == 1
    assert google.events["evt1"]["summary"] == "Reunião"

    # Evento criado diretamente no Google é importado
    ext = google.add_external("Dentista", start + timedelta(days=1))
    result = (await client.post("/api/calendar/sync", headers=headers)).json()
    assert result["imported"] == 1 and result["pushed"] == 0, result
    titles = {t["title"]: t for t in (await client.get("/api/tasks", headers=headers)).json()}
    assert titles["Dentista"]["source"] == "google"

    # Segunda sincronização sem mudanças não faz nada
    result = (await client.post("/api/calendar/sync", headers=headers)).json()
    assert (result["imported"], result["updated"], result["pushed"], result["deleted"]) == (0, 0, 0, 0), result

    # Edição no app atualiza o evento
    await client.patch(f"/api/tasks/{task['id']}", headers=headers, json={"title": "Reunião (editada)", "status": "done"})
    assert google.events["evt1"]["summary"] == "✅ Reunião (editada)"

    # Edição feita no Google é trazida para o app
    google.events[ext].update({"summary": "Dentista 16h", "etag": '"999"', "updated": google._now()})
    result = (await client.post("/api/calendar/sync", headers=headers)).json()
    assert result["updated"] == 1, result
    titles = [t["title"] for t in (await client.get("/api/tasks", headers=headers)).json()]
    assert "Dentista 16h" in titles

    # Exclusão no Google remove a tarefa
    google.events[ext]["status"] = "cancelled"
    result = (await client.post("/api/calendar/sync", headers=headers)).json()
    assert result["deleted"] == 1
    titles = [t["title"] for t in (await client.get("/api/tasks", headers=headers)).json()]
    assert "Dentista 16h" not in titles

    # Excluir tarefa no app remove o evento
    await client.delete(f"/api/tasks/{task['id']}", headers=headers)
    assert google.events["evt1"]["status"] == "cancelled"
