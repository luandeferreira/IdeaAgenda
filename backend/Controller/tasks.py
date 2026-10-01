from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from Config.database import get_db
from Dto.dto import TaskCreate, TaskOut, TaskUpdate
from Mapper.mapper import task_to_dto
from Model.model import TaskStatus, User
from Service import task_service
from Service.security import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    start: datetime | None = None,
    end: datetime | None = None,
    q: str | None = Query(default=None, max_length=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await task_service.list_tasks(db, user, status_filter=status_filter, start=start, end=end, search=q)
    return [task_to_dto(t) for t in tasks]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(data: TaskCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return task_to_dto(await task_service.create_task(db, user, data))


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return task_to_dto(await task_service.get_task(db, user, task_id))


@router.patch("/{task_id}", response_model=TaskOut)
@router.put("/{task_id}", response_model=TaskOut, include_in_schema=False)
async def update_task(
    task_id: int, data: TaskUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return task_to_dto(await task_service.update_task(db, user, task_id, data))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await task_service.delete_task(db, user, task_id)
