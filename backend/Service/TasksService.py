from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.Mapper.TasksMapper import TasksMapper
from backend.Dto.TasksDto import TaskDto
from backend.Model.Tasks import Task
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime, timezone
from uuid import UUID

async def create_task(task_dto: TaskDto, db: AsyncSession):
    task_model = TasksMapper.toModel(task_dto)

    db.add(task_model)
    await db.commit()
    await db.refresh(task_model)

    return TasksMapper.toDto(task_model)

async def get_all_tasks(db: AsyncSession):
    result = await db.execute(select(Task).options(selectinload(Task.calendar)))
    tasks = result.scalars().all()

    return [TasksMapper.toDto(task) for task in tasks]

async def get_task(task_id: UUID, db: AsyncSession):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return TasksMapper.toDto(task)

async def update_task(task_id: UUID, task_dto: TaskDto, db: AsyncSession):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    task.title = task_dto.title
    task.description = task_dto.description
    task.completion_date = TasksMapper.remove_tz(task_dto.completion_date)
    task.completed = task_dto.completed
    task.completed_at = TasksMapper.remove_tz(task_dto.completed_at)
    task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    await db.commit()
    await db.refresh(task)

    return TasksMapper.toDto(task)

async def delete_task(task_id: UUID, db: AsyncSession):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    await db.delete(task)
    await db.commit()

    return {"Message": "Task deleted successfully", "Id": str(task_id)}
