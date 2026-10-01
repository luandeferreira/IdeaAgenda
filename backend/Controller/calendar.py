from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from Config.database import get_db
from Config.settings import get_settings
from Dto.dto import CalendarStatusOut, CalendarSyncResult
from Model.model import User
from Service import calendar_service
from Service.security import get_current_user

router = APIRouter(prefix="/calendar", tags=["google-calendar"])


@router.get("/status", response_model=CalendarStatusOut)
async def calendar_status(user: User = Depends(get_current_user)):
    return CalendarStatusOut(
        google_oauth_enabled=get_settings().google_oauth_enabled,
        connected=user.google_connected,
        sync_enabled=user.calendar_sync_enabled,
        last_sync_at=user.last_calendar_sync_at,
    )


@router.post("/sync", response_model=CalendarSyncResult)
async def sync(
    past_days: int = 365, future_days: int = 180, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    past_days = max(0, min(past_days, 730))
    future_days = max(1, min(future_days, 730))
    try:
        result = await calendar_service.full_sync(db, user, past_days=past_days, future_days=future_days)
    except calendar_service.CalendarError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CalendarSyncResult(**result)
