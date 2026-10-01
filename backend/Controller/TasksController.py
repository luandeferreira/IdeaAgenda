from fastapi import APIRouter
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.Dto.TasksDto import TaskDto
from backend.Service import TasksService
from typing import List
from fastapi.responses import JSONResponse
from backend.database import get_db
from uuid import UUID  # Importando o UUID

router = APIRouter()

@router.post("/post", response_model=dict, status_code=201)
async def create_task(task_dto: TaskDto, db: AsyncSession = Depends(get_db)):
    task = await TasksService.create_task(task_dto, db)

    return {"Message: ": "Task successfully created", "Body: ": task}

@router.get("/get", response_model=dict, status_code=200)
async def get_all_tasks(db: AsyncSession = Depends(get_db)):
    tasks = await TasksService.get_all_tasks(db)

    return {"Message: ": "Tasks successfully found", "Body: ": tasks}

@router.get("/getById/{task_id}", response_model=dict, status_code=200)
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    task = await TasksService.get_task(task_id, db)

    return {"Message: ": "Task successfully found", "Body: ": task}

@router.put("/edit/{task_id}", response_model=dict, status_code=201)
async def update_task(task_id: UUID, task_dto: TaskDto, db: AsyncSession = Depends(get_db)):
    task = await TasksService.update_task(task_id, task_dto, db)

    return {"Message: ": "Task successfully updated", "Body: ": task}

@router.delete("/delete/{task_id}", response_model=dict, status_code=200)
async def delete_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await TasksService.delete_task(task_id, db)

    return result
