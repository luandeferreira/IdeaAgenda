"""Configurações globais do sistema guardadas no banco (editáveis pelo dono)."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from Config.settings import get_settings
from Dto.dto import AISettingsIn, AISettingsOut
from Model.model import AppSetting

logger = logging.getLogger("ideaagenda.settings")

AI_SETTINGS_KEY = "ai"


async def get_ai_settings(db: AsyncSession) -> AISettingsOut:
    env = get_settings()
    row = await db.get(AppSetting, AI_SETTINGS_KEY)
    stored = row.value if row else {}
    provider = stored.get("provider") or env.ai_provider
    if provider not in ("openai", "gemini"):
        provider = "openai"
    return AISettingsOut(
        provider=provider,
        openai_model=stored.get("openai_model") or env.openai_model,
        gemini_model=stored.get("gemini_model") or env.gemini_model,
        openai_configured=bool(env.openai_api_key),
        gemini_configured=bool(env.gemini_api_key),
    )


async def update_ai_settings(db: AsyncSession, data: AISettingsIn, changed_by: str) -> AISettingsOut:
    row = await db.get(AppSetting, AI_SETTINGS_KEY)
    value = dict(row.value) if row else {}
    value["provider"] = data.provider
    if data.openai_model:
        value["openai_model"] = data.openai_model
    if data.gemini_model:
        value["gemini_model"] = data.gemini_model
    if row is None:
        db.add(AppSetting(key=AI_SETTINGS_KEY, value=value))
    else:
        row.value = value  # reatribui para o SQLAlchemy detectar a mudança no JSON
    await db.commit()
    logger.info("Configuração de IA alterada", extra={"event": "ai_settings_changed", "by": changed_by, **value})
    return await get_ai_settings(db)
