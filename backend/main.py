import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from Config.database import init_db
from Config.logging_config import setup_logging, shutdown_logging
from Config.redis_client import close_redis
from Config.settings import get_settings
from Controller.admin import router as admin_router
from Controller.ai import router as ai_router
from Controller.auth import router as auth_router
from Controller.calendar import router as calendar_router
from Controller.home import router as home_router
from Controller.tasks import router as tasks_router
from Middleware.request_logging import RequestLoggingMiddleware

settings = get_settings()
logger = logging.getLogger("ideaagenda")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    if settings.secret_key == "change-me-in-production" and settings.environment == "production":
        logger.warning("SECRET_KEY padrão em produção! Defina uma chave forte no .env")
    await init_db()
    logger.info("IdeaAgenda API iniciada", extra={"event": "startup", "environment": settings.environment})
    yield
    logger.info("IdeaAgenda API finalizada", extra={"event": "shutdown"})
    await close_redis()
    shutdown_logging()


app = FastAPI(title="IdeaAgenda - Sistema de Organização de Tarefas", version="1.0.0", lifespan=lifespan)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (home_router, auth_router, tasks_router, calendar_router, ai_router, admin_router):
    app.include_router(router, prefix="/api")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
