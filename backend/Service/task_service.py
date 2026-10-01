import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from Dto.dto import AIApplyRequest, TaskCreate, TaskUpdate
from Mapper.mapper import as_utc, create_dto_to_task
from Model.model import Task, TaskStatus, User
from Service import calendar_service

logger = logging.getLogger("ideaagenda.tasks")


async def list_tasks(
    db: AsyncSession,
    user: User,
    *,
    status_filter: TaskStatus | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    search: str | None = None,
) -> list[Task]:
    query = select(Task).where(Task.user_id == user.id)
    if status_filter:
        query = query.where(Task.status == status_filter)
    if start:
        query = query.where(Task.start_at >= as_utc(start))
    if end:
        query = query.where(Task.start_at <= as_utc(end))
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(Task.title.ilike(like), Task.description.ilike(like)))
    query = query.order_by(Task.start_at.is_(None), Task.start_at, Task.created_at)
    return list((await db.scalars(query)).all())


async def get_task(db: AsyncSession, user: User, task_id: int) -> Task:
    task = await db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarefa não encontrada")
    return task


async def create_task(db: AsyncSession, user: User, data: TaskCreate) -> Task:
    task = create_dto_to_task(data, user.id)
    db.add(task)
    await db.flush()  # gera o id usado no marcador do evento
    await calendar_service.sync_single_task(task, user)
    await db.commit()
    await db.refresh(task)
    logger.info("Tarefa criada", extra={"event": "task_created", "user_id": user.id, "task_id": task.id})
    return task


def _validate_dates(task: Task) -> None:
    start, end = as_utc(task.start_at), as_utc(task.end_at)
    if end and not start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end_at exige start_at")
    if start and end and end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end_at deve ser posterior a start_at")


async def update_task(db: AsyncSession, user: User, task_id: int, data: TaskUpdate) -> Task:
    task = await get_task(db, user, task_id)
    changes = data.model_dump(exclude_unset=True)
    for field in ("title", "priority", "status", "all_day", "sync_to_calendar", "description"):
        if field in changes and changes[field] is None:
            changes.pop(field)
    for key, value in changes.items():
        if key in ("start_at", "end_at"):
            value = as_utc(value)
        setattr(task, key, value)
    if "start_at" in changes and changes["start_at"] is None:
        task.end_at = None
        task.all_day = False
    _validate_dates(task)
    task.updated_at = datetime.now(timezone.utc)
    await calendar_service.sync_single_task(task, user)
    await db.commit()
    await db.refresh(task)
    logger.info("Tarefa atualizada", extra={"event": "task_updated", "user_id": user.id, "task_id": task.id, "fields": list(changes)})
    return task


async def delete_task(db: AsyncSession, user: User, task_id: int) -> None:
    task = await get_task(db, user, task_id)
    await calendar_service.delete_task_event(task, user)
    await db.delete(task)
    await db.commit()
    logger.info("Tarefa removida", extra={"event": "task_deleted", "user_id": user.id, "task_id": task_id})


async def apply_suggestions(db: AsyncSession, user: User, req: AIApplyRequest) -> list[Task]:
    ids = [item.task_id for item in req.items]
    tasks = {t.id: t for t in (await db.scalars(select(Task).where(Task.user_id == user.id, Task.id.in_(ids)))).all()}
    updated: list[Task] = []
    now = datetime.now(timezone.utc)
    for item in req.items:
        task = tasks.get(item.task_id)
        if task is None:
            continue
        if item.start_at:
            task.start_at = as_utc(item.start_at)
            task.end_at = as_utc(item.end_at) if item.end_at and item.end_at > item.start_at else None
            task.all_day = False
        if item.priority:
            task.priority = item.priority
        task.updated_at = now
        updated.append(task)

    if updated and calendar_service.can_sync(user):
        async with calendar_service.GoogleCalendarClient(user) as client:
            for task in updated:
                if task.sync_to_calendar:
                    await calendar_service.push_task(client, task)
    await db.commit()
    for task in updated:
        await db.refresh(task)
    logger.info("Sugestões da IA aplicadas", extra={"event": "ai_applied", "user_id": user.id, "count": len(updated)})
    return updated
