from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from Config.database import get_db
from Dto.dto import AISettingsIn, AISettingsOut, LogEntryOut
from Model.model import User
from Service import log_service, settings_service
from Service.security import get_admin_user

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/settings/ai", response_model=AISettingsOut)
async def get_ai(admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    return await settings_service.get_ai_settings(db)


@router.put("/settings/ai", response_model=AISettingsOut)
async def put_ai(data: AISettingsIn, admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    return await settings_service.update_ai_settings(db, data, changed_by=admin.email)


@router.get("/logs", response_model=list[LogEntryOut])
async def logs(
    limit: int = Query(default=100, ge=1, le=1000),
    level: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    user_id: int | None = None,
    before: str | None = Query(default=None, pattern=r"^\d+-\d+$"),
    admin: User = Depends(get_admin_user),
):
    return await log_service.read_logs(limit=limit, level=level, search=q, user_id=user_id, before=before)


@router.get("/logs/stats")
async def logs_stats(admin: User = Depends(get_admin_user)):
    return await log_service.log_stats()
