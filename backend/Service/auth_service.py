"""Login com Google (OAuth 2.0 authorization code) e login de desenvolvimento."""

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from Config.settings import get_settings
from Model.model import User
from Service.security import create_token, decode_token, encrypt

logger = logging.getLogger("ideaagenda.auth")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar.events",
]


def build_google_login_url() -> str:
    settings = get_settings()
    if not settings.google_oauth_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Login com Google não configurado")
    state = create_token("google-oauth", purpose="oauth_state", expires_minutes=10)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def _should_be_admin(db: AsyncSession, email: str) -> bool:
    settings = get_settings()
    admins = settings.admin_email_list
    if admins:
        return email.lower() in admins
    # Sem ADMIN_EMAILS configurado: o primeiro usuário vira o dono do sistema
    count = await db.scalar(select(func.count()).select_from(User))
    return (count or 0) == 0


async def upsert_user(
    db: AsyncSession,
    *,
    email: str,
    name: str = "",
    picture: str | None = None,
    google_sub: str | None = None,
) -> User:
    email = email.strip().lower()
    user = None
    if google_sub:
        user = await db.scalar(select(User).where(User.google_sub == google_sub))
    if user is None:
        user = await db.scalar(select(User).where(User.email == email))

    settings = get_settings()
    if user is None:
        user = User(
            email=email,
            name=name or email.split("@")[0],
            picture=picture,
            google_sub=google_sub,
            is_admin=await _should_be_admin(db, email),
            timezone=settings.default_timezone,
        )
        db.add(user)
        logger.info("Novo usuário cadastrado", extra={"event": "user_created", "email": email})
    else:
        user.name = name or user.name
        user.picture = picture or user.picture
        user.google_sub = google_sub or user.google_sub
        if settings.admin_email_list:
            user.is_admin = email in settings.admin_email_list
    await db.flush()
    return user


async def handle_google_callback(db: AsyncSession, code: str, state: str) -> User:
    settings = get_settings()
    decode_token(state, purpose="oauth_state")

    async with httpx.AsyncClient(timeout=20) as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            logger.warning("Falha ao trocar código OAuth", extra={"status": token_resp.status_code, "body": token_resp.text[:500]})
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Não foi possível autenticar com o Google")
        tokens = token_resp.json()

        info_resp = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        info_resp.raise_for_status()
        info = info_resp.json()

    if not info.get("email") or not info.get("email_verified", True):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "E-mail do Google não verificado")

    user = await upsert_user(
        db, email=info["email"], name=info.get("name", ""), picture=info.get("picture"), google_sub=info.get("sub")
    )
    user.google_access_token = encrypt(tokens.get("access_token"))
    if tokens.get("refresh_token"):
        user.google_refresh_token = encrypt(tokens["refresh_token"])
    user.google_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    await db.commit()
    await db.refresh(user)
    logger.info("Login com Google", extra={"event": "login", "user_id": user.id, "method": "google"})
    return user


async def dev_login(db: AsyncSession, email: str, name: str) -> User:
    if not get_settings().allow_dev_login:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Login de desenvolvimento desabilitado")
    user = await upsert_user(db, email=email, name=name)
    await db.commit()
    await db.refresh(user)
    logger.info("Login de desenvolvimento", extra={"event": "login", "user_id": user.id, "method": "dev"})
    return user


def issue_access_token(user: User) -> str:
    return create_token(str(user.id), purpose="access", email=user.email)
