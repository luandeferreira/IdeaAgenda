"""Integração com a API do Google Calendar (REST v3)."""

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from Config.settings import get_settings
from Mapper.mapper import (
    APP_MARKER_KEY,
    as_utc,
    google_event_to_fields,
    google_event_updated_at,
    task_to_google_event,
)
from Model.model import Task, TaskSource, TaskStatus, User
from Service.auth_service import GOOGLE_TOKEN_URL
from Service.security import decrypt, encrypt

logger = logging.getLogger("ideaagenda.calendar")

CALENDAR_API = "https://www.googleapis.com/calendar/v3"


def _default_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20)


# Pode ser substituída nos testes por um cliente com MockTransport
http_client_factory = _default_http


class CalendarError(Exception):
    pass


class GoogleCalendarClient:
    def __init__(self, user: User, http: httpx.AsyncClient | None = None):
        self.user = user
        self.settings = get_settings()
        self._http = http or http_client_factory()
        self._owns_http = http is None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        if self._owns_http:
            await self._http.aclose()

    @property
    def calendar_path(self) -> str:
        return f"{CALENDAR_API}/calendars/{quote(self.settings.google_calendar_id, safe='')}/events"

    async def _access_token(self) -> str:
        user = self.user
        expires = as_utc(user.google_token_expires_at)
        token = decrypt(user.google_access_token)
        if token and expires and expires > datetime.now(timezone.utc) + timedelta(seconds=60):
            return token

        refresh = decrypt(user.google_refresh_token)
        if not refresh:
            raise CalendarError("Conta Google não conectada. Faça login com o Google novamente.")
        resp = await self._http.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code != 200:
            logger.warning("Falha ao renovar token do Google", extra={"user_id": user.id, "status": resp.status_code})
            raise CalendarError("Não foi possível renovar o acesso ao Google Agenda. Faça login novamente.")
        data = resp.json()
        user.google_access_token = encrypt(data["access_token"])
        user.google_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 3600)))
        return data["access_token"]

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        token = await self._access_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._http.request(method, url, headers=headers, **kwargs)
        if resp.status_code >= 400 and resp.status_code not in (404, 410):
            raise CalendarError(f"Google Calendar respondeu {resp.status_code}: {resp.text[:300]}")
        return resp

    async def insert_event(self, body: dict) -> dict:
        return (await self._request("POST", self.calendar_path, json=body)).json()

    async def update_event(self, event_id: str, body: dict) -> dict | None:
        resp = await self._request("PATCH", f"{self.calendar_path}/{quote(event_id, safe='')}", json=body)
        if resp.status_code in (404, 410):
            return None
        return resp.json()

    async def delete_event(self, event_id: str) -> None:
        await self._request("DELETE", f"{self.calendar_path}/{quote(event_id, safe='')}")

    async def list_events(self, time_min: datetime, time_max: datetime) -> list[dict]:
        events: list[dict] = []
        params = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "showDeleted": "true",
            "maxResults": "250",
            "orderBy": "startTime",
        }
        while True:
            data = (await self._request("GET", self.calendar_path, params=params)).json()
            events.extend(data.get("items", []))
            page = data.get("nextPageToken")
            if not page:
                return events
            params["pageToken"] = page


def can_sync(user: User, task: Task | None = None) -> bool:
    if not (get_settings().google_oauth_enabled and user.google_connected and user.calendar_sync_enabled):
        return False
    if task is not None and not task.sync_to_calendar:
        return False
    return True


async def push_task(client: GoogleCalendarClient, task: Task) -> None:
    """Cria/atualiza/remove o evento correspondente à tarefa no Google Agenda."""
    user = client.user
    try:
        if task.start_at is None or not task.sync_to_calendar:
            # Sem data (ou sincronização desligada): remove evento existente
            if task.google_event_id:
                await client.delete_event(task.google_event_id)
                task.google_event_id = None
                task.google_etag = None
        else:
            body = task_to_google_event(task, user.timezone)
            event = None
            if task.google_event_id:
                event = await client.update_event(task.google_event_id, body)
            if event is None:
                event = await client.insert_event(body)
            task.google_event_id = event.get("id")
            task.google_etag = event.get("etag")
        task.last_synced_at = datetime.now(timezone.utc)
        task.sync_error = None
    except (CalendarError, httpx.HTTPError) as exc:
        task.sync_error = str(exc)[:500]
        logger.warning("Erro ao sincronizar tarefa", extra={"user_id": user.id, "task_id": task.id, "error": str(exc)})


async def sync_single_task(task: Task, user: User) -> None:
    if not can_sync(user):
        return
    async with GoogleCalendarClient(user) as client:
        await push_task(client, task)


async def delete_task_event(task: Task, user: User) -> None:
    if not (task.google_event_id and can_sync(user)):
        return
    try:
        async with GoogleCalendarClient(user) as client:
            await client.delete_event(task.google_event_id)
    except (CalendarError, httpx.HTTPError) as exc:
        logger.warning("Erro ao remover evento do Google", extra={"user_id": user.id, "task_id": task.id, "error": str(exc)})


async def full_sync(db: AsyncSession, user: User, past_days: int = 7, future_days: int = 60) -> dict:
    """Sincronização bidirecional.

    1. Envia para o Google as tarefas alteradas desde a última sincronização.
    2. Importa/atualiza tarefas a partir dos eventos do Google no intervalo.
    """
    if not can_sync(user):
        raise CalendarError("Sincronização com Google Agenda indisponível. Conecte sua conta Google.")

    result = {"pushed": 0, "imported": 0, "updated": 0, "deleted": 0, "errors": []}
    now = datetime.now(timezone.utc)
    tasks = list((await db.scalars(select(Task).where(Task.user_id == user.id))).all())
    by_event = {t.google_event_id: t for t in tasks if t.google_event_id}

    async with GoogleCalendarClient(user) as client:
        # 1) push
        for task in tasks:
            needs_push = (
                task.sync_to_calendar
                and task.start_at is not None
                and (
                    task.google_event_id is None
                    or task.last_synced_at is None
                    or as_utc(task.updated_at) > as_utc(task.last_synced_at)
                )
            )
            needs_removal = task.google_event_id and (task.start_at is None or not task.sync_to_calendar)
            if needs_push or needs_removal:
                await push_task(client, task)
                if task.sync_error:
                    result["errors"].append(f"{task.title}: {task.sync_error}")
                else:
                    result["pushed"] += 1
                    if task.google_event_id:
                        by_event[task.google_event_id] = task

        # 2) pull
        events = await client.list_events(now - timedelta(days=past_days), now + timedelta(days=future_days))
        for event in events:
            event_id = event.get("id")
            if not event_id:
                continue
            task = by_event.get(event_id)
            if task is None:
                marker = (event.get("extendedProperties") or {}).get("private", {}).get(APP_MARKER_KEY)
                if marker and marker.isdigit():
                    task = next((t for t in tasks if t.id == int(marker)), None)

            if event.get("status") == "cancelled":
                if task is not None:
                    await db.delete(task)
                    result["deleted"] += 1
                continue

            fields = google_event_to_fields(event, user.timezone)
            if task is None:
                task = Task(
                    user_id=user.id,
                    source=TaskSource.google,
                    google_event_id=event_id,
                    google_etag=event.get("etag"),
                    last_synced_at=now,
                    created_at=now,
                    updated_at=now,
                    **fields,
                )
                db.add(task)
                by_event[event_id] = task
                result["imported"] += 1
                continue

            if event.get("etag") and event.get("etag") == task.google_etag:
                continue
            event_updated = google_event_updated_at(event)
            task_updated = as_utc(task.updated_at)
            if event_updated and task_updated and event_updated <= task_updated:
                continue
            # Status: só sobrescreve quando o ✅ foi adicionado/removido no Google
            if fields["status"] == TaskStatus.todo and task.status == TaskStatus.in_progress:
                fields["status"] = TaskStatus.in_progress
            for key, value in fields.items():
                setattr(task, key, value)
            task.google_event_id = event_id
            task.google_etag = event.get("etag")
            task.last_synced_at = now
            task.sync_error = None
            result["updated"] += 1

    sync_time = datetime.now(timezone.utc)
    user.last_calendar_sync_at = sync_time
    await db.commit()
    logger.info("Sincronização com Google Agenda", extra={"event": "calendar_sync", "user_id": user.id, **{k: v for k, v in result.items() if k != "errors"}, "errors": len(result["errors"])})
    result["synced_at"] = sync_time
    return result
