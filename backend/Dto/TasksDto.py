from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from uuid import UUID

class TaskDto(BaseModel):
    id: Optional[UUID] = None
    summary: str
    description: str
    location: str
    completion_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    completed: bool = False
    calendar_id: UUID

    class Config:
        orm_mode = True