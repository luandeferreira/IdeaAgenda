import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from Config.database import get_db
from Config.redis_client import get_async_redis
from Dto.dto import HealthOut

router = APIRouter(tags=["home"])
logger = logging.getLogger("ideaagenda.health")


@router.get("/")
async def root():
    return {"mensagem": "IdeaAgenda API", "docs": "/docs"}


@router.get("/health", response_model=HealthOut)
async def health(db: AsyncSession = Depends(get_db)):
    db_ok = redis_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # pragma: no cover
        logger.error("Banco indisponível", extra={"error": str(exc)})
    try:
        redis_ok = bool(await get_async_redis().ping())
    except Exception as exc:  # pragma: no cover
        logger.error("Redis indisponível", extra={"error": str(exc)})
    return HealthOut(status="ok" if db_ok and redis_ok else "degraded", database=db_ok, redis=redis_ok)
