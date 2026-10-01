from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from Config.database import get_db
from Config.settings import get_settings
from Dto.dto import AuthConfigOut, DevLoginIn, TokenOut, UserOut, UserPreferencesIn
from Mapper.mapper import safe_zone, user_to_dto
from Model.model import User
from Service import auth_service
from Service.security import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config", response_model=AuthConfigOut)
async def auth_config():
    settings = get_settings()
    return AuthConfigOut(google_enabled=settings.google_oauth_enabled, dev_login_enabled=settings.allow_dev_login)


@router.get("/google/login")
async def google_login():
    return RedirectResponse(auth_service.build_google_login_url())


@router.get("/google/callback")
async def google_callback(
    code: str | None = None, state: str | None = None, error: str | None = None, db: AsyncSession = Depends(get_db)
):
    frontend = get_settings().frontend_url.rstrip("/")
    if error or not code or not state:
        return RedirectResponse(f"{frontend}/login?{urlencode({'error': error or 'login_cancelado'})}")
    try:
        user = await auth_service.handle_google_callback(db, code, state)
    except HTTPException as exc:
        return RedirectResponse(f"{frontend}/login?{urlencode({'error': exc.detail})}")
    token = auth_service.issue_access_token(user)
    # O token vai no fragmento (#) para não aparecer em logs de servidores/proxies
    return RedirectResponse(f"{frontend}/auth/callback#token={token}")


@router.post("/dev-login", response_model=TokenOut)
async def dev_login(data: DevLoginIn, db: AsyncSession = Depends(get_db)):
    user = await auth_service.dev_login(db, data.email, data.name)
    return TokenOut(access_token=auth_service.issue_access_token(user), user=user_to_dto(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user_to_dto(user)


@router.patch("/me", response_model=UserOut)
async def update_me(data: UserPreferencesIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if data.timezone is not None:
        if safe_zone(data.timezone).key != data.timezone:
            raise HTTPException(422, "Fuso horário inválido")
        user.timezone = data.timezone
    if data.calendar_sync_enabled is not None:
        user.calendar_sync_enabled = data.calendar_sync_enabled
    await db.commit()
    await db.refresh(user)
    return user_to_dto(user)
