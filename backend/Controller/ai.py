from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from Config.database import get_db
from Dto.dto import AIApplyRequest, AIParseRequest, AIParseResponse, AISuggestionRequest, AISuggestionResponse, TaskOut
from Mapper.mapper import task_to_dto
from Model.model import User
from Service import task_service
from Service.ai import ai_service
from Service.security import get_current_user
from Service.settings_service import get_ai_settings

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/provider")
async def current_provider(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    s = await get_ai_settings(db)
    configured = s.gemini_configured if s.provider == "gemini" else s.openai_configured
    return {"provider": s.provider, "model": s.gemini_model if s.provider == "gemini" else s.openai_model, "available": configured}


@router.post("/suggestions", response_model=AISuggestionResponse)
async def suggestions(
    req: AISuggestionRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await ai_service.suggest(db, user, req)


@router.post("/suggestions/apply", response_model=list[TaskOut])
async def apply_suggestions(req: AIApplyRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [task_to_dto(t) for t in await task_service.apply_suggestions(db, user, req)]


@router.post("/parse", response_model=AIParseResponse)
async def parse(req: AIParseRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await ai_service.parse_task(db, user, req.text)
