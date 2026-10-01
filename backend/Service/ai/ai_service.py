"""Sugestões automáticas de organização usando o provedor de IA escolhido pelo dono."""

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from Config.redis_client import get_async_redis
from Config.settings import get_settings
from Dto.dto import (
    AISuggestionRequest,
    AISuggestionResponse,
    AITaskSuggestion,
    AIParseResponse,
    TaskCreate,
)
from Mapper.mapper import as_utc, safe_zone
from Model.model import Task, TaskPriority, TaskStatus, User
from Service.ai.providers import AIProvider, AIProviderError, build_provider
from Service.settings_service import get_ai_settings

logger = logging.getLogger("ideaagenda.ai")

SUGGEST_SYSTEM_PROMPT = """Você é o assistente de produtividade do IdeaAgenda.
Organize as tarefas pendentes do usuário na agenda dos próximos dias.
Regras:
- Agende apenas dentro do horário de trabalho informado e no futuro (depois de "agora").
- Não sobreponha horários com compromissos já agendados nem entre as sugestões.
- Priorize tarefas de prioridade alta e as mais antigas; agrupe tarefas da mesma categoria quando fizer sentido.
- Use "estimated_minutes" como duração quando existir; caso contrário estime uma duração realista (15 a 180 min).
- Ajuste a prioridade apenas se houver um bom motivo.
- Escreva em português do Brasil, de forma curta e objetiva.
Responda SOMENTE com um JSON no formato:
{"summary": "visão geral em até 3 frases",
 "suggestions": [{"task_id": 1, "start_at": "2026-01-01T09:00:00-03:00", "end_at": "2026-01-01T10:00:00-03:00", "priority": "low|medium|high", "reason": "motivo curto"}],
 "tips": ["dica curta"]}
Datas sempre em ISO 8601 com o fuso horário do usuário."""

PARSE_SYSTEM_PROMPT = """Você converte uma frase em linguagem natural (português) em uma tarefa do IdeaAgenda.
Interprete datas relativas ("amanhã", "sexta às 15h") a partir de "agora" e do fuso informado.
Responda SOMENTE com um JSON no formato:
{"title": "título curto", "description": "detalhes ou vazio", "category": "categoria curta ou null",
 "priority": "low|medium|high", "start_at": "ISO 8601 com fuso ou null", "end_at": "ISO 8601 com fuso ou null",
 "all_day": false, "estimated_minutes": 60}"""


async def enforce_rate_limit(user: User) -> None:
    limit = get_settings().ai_rate_limit_per_hour
    if limit <= 0:
        return
    key = f"ideaagenda:ai_rate:{user.id}:{datetime.now(timezone.utc):%Y%m%d%H}"
    try:
        redis = get_async_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 3600)
    except Exception:  # Redis indisponível não deve derrubar a funcionalidade
        logger.warning("Rate limit da IA indisponível (Redis)")
        return
    if count > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Limite de uso da IA atingido. Tente novamente mais tarde.")


async def _provider(db: AsyncSession) -> AIProvider:
    ai_settings = await get_ai_settings(db)
    try:
        return build_provider(ai_settings)
    except AIProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def _task_payload(task: Task, zone) -> dict:
    def fmt(dt):
        dt = as_utc(dt)
        return dt.astimezone(zone).isoformat() if dt else None

    return {
        "id": task.id,
        "title": task.title,
        "description": (task.description or "")[:300],
        "category": task.category,
        "priority": task.priority.value,
        "status": task.status.value,
        "start_at": fmt(task.start_at),
        "end_at": fmt(task.end_at),
        "estimated_minutes": task.estimated_minutes,
        "created_at": fmt(task.created_at),
    }


def _parse_dt(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt


async def suggest(db: AsyncSession, user: User, req: AISuggestionRequest) -> AISuggestionResponse:
    await enforce_rate_limit(user)
    zone = safe_zone(user.timezone)
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=req.horizon_days)

    tasks = list(
        (await db.scalars(select(Task).where(Task.user_id == user.id, Task.status != TaskStatus.done))).all()
    )
    pending = [t for t in tasks if t.start_at is None or as_utc(t.start_at) < now]
    scheduled = [t for t in tasks if t.start_at is not None and now <= as_utc(t.start_at) <= horizon]

    if not pending:
        ai_settings = await get_ai_settings(db)
        model = ai_settings.gemini_model if ai_settings.provider == "gemini" else ai_settings.openai_model
        return AISuggestionResponse(
            provider=ai_settings.provider,
            model=model,
            summary="Você não tem tarefas pendentes sem horário. Sua agenda está organizada! 🎉",
            suggestions=[],
            tips=[],
        )

    provider = await _provider(db)
    prompt = json.dumps(
        {
            "agora": now.astimezone(zone).isoformat(),
            "fuso_horario": zone.key,
            "horizonte_dias": req.horizon_days,
            "horario_trabalho": {"inicio": req.work_start, "fim": req.work_end},
            "objetivo_do_usuario": req.goal,
            "tarefas_pendentes": [_task_payload(t, zone) for t in pending[:80]],
            "compromissos_agendados": [_task_payload(t, zone) for t in scheduled[:120]],
        },
        ensure_ascii=False,
    )
    try:
        data = await provider.generate_json(SUGGEST_SYSTEM_PROMPT, prompt)
    except AIProviderError as exc:
        logger.warning("Falha ao gerar sugestões", extra={"user_id": user.id, "provider": provider.name, "error": str(exc)})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    valid_ids = {t.id: t for t in pending}
    suggestions: list[AITaskSuggestion] = []
    seen: set[int] = set()
    for raw in data.get("suggestions") or []:
        if not isinstance(raw, dict):
            continue
        try:
            task_id = int(raw.get("task_id"))
        except (TypeError, ValueError):
            continue
        if task_id not in valid_ids or task_id in seen:
            continue
        start, end = _parse_dt(raw.get("start_at")), _parse_dt(raw.get("end_at"))
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=zone)
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=zone)
        if start and end and end <= start:
            end = None
        priority = raw.get("priority")
        seen.add(task_id)
        suggestions.append(
            AITaskSuggestion(
                task_id=task_id,
                title=valid_ids[task_id].title,
                start_at=start,
                end_at=end,
                priority=priority if priority in TaskPriority._value2member_map_ else None,
                reason=str(raw.get("reason") or "")[:500],
            )
        )

    logger.info(
        "Sugestões de IA geradas",
        extra={"event": "ai_suggestions", "user_id": user.id, "provider": provider.name, "count": len(suggestions)},
    )
    tips = [str(t)[:300] for t in (data.get("tips") or []) if t][:8]
    return AISuggestionResponse(
        provider=provider.name,
        model=provider.model,
        summary=str(data.get("summary") or "")[:1500],
        suggestions=suggestions,
        tips=tips,
    )


async def parse_task(db: AsyncSession, user: User, text: str) -> AIParseResponse:
    await enforce_rate_limit(user)
    zone = safe_zone(user.timezone)
    provider = await _provider(db)
    prompt = json.dumps(
        {"agora": datetime.now(zone).isoformat(), "fuso_horario": zone.key, "frase": text}, ensure_ascii=False
    )
    try:
        data = await provider.generate_json(PARSE_SYSTEM_PROMPT, prompt)
    except AIProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    start, end = _parse_dt(data.get("start_at")), _parse_dt(data.get("end_at"))
    if start and start.tzinfo is None:
        start = start.replace(tzinfo=zone)
    if end and end.tzinfo is None:
        end = end.replace(tzinfo=zone)
    if not start or (end and end < start):
        end = None
    minutes = data.get("estimated_minutes")
    try:
        task = TaskCreate(
            title=str(data.get("title") or text)[:300],
            description=str(data.get("description") or "")[:5000],
            category=(str(data["category"])[:80] if data.get("category") else None),
            priority=data.get("priority") if data.get("priority") in TaskPriority._value2member_map_ else "medium",
            start_at=start,
            end_at=end,
            all_day=bool(data.get("all_day")) and start is not None,
            estimated_minutes=int(minutes) if isinstance(minutes, (int, float)) and 1 <= minutes <= 1440 else None,
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "A IA retornou uma tarefa inválida") from exc
    logger.info("Tarefa interpretada pela IA", extra={"event": "ai_parse", "user_id": user.id, "provider": provider.name})
    return AIParseResponse(provider=provider.name, task=task)
