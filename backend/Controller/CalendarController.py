from uuid import UUID
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.Dto.CalendarDto import CalendarDto
from backend.Service import CalendarService

router = APIRouter()

@router.post("/post", response_model=dict, status_code=201)
async def create_calendar(calendar_dto: CalendarDto, db: AsyncSession = Depends(get_db), request: Request=None):
    calendar = await CalendarService.create_calendar(calendar_dto, db, request)
    return {"Message: ": "Calendar successfully created", "Body: ": calendar}

@router.get("/getAll", response_model=dict, status_code=200)
async def get_all_calendars(db: AsyncSession = Depends(get_db)):
    calendars = await CalendarService.get_all_calendars(db)
    return {"Message: ": "Calendars successfully found.", "Body: ": calendars}

@router.get("/getById/{calendar_id}", response_model=dict, status_code=200)
async def get_calendar(calendar_id: UUID, db: AsyncSession = Depends(get_db)):
    calendar = await CalendarService.get_calendar_by_id(calendar_id, db)
    return {"Message: ": "Calendar successfully found", "Body: ": calendar.dict()}

@router.get("/getByCreator/{creator}", response_model=dict, status_code=200)
async def get_calendar_by_creator(creator: str, db: AsyncSession = Depends(get_db)):
    calendar = await CalendarService.get_calendar_by_creator(creator, db)
    return {"Message: ": "Calendar successfully found", "Body: ": calendar.dict()}

@router.put("/edit/{calendar_id}", response_model=dict, status_code=201)
async def edit_calendar(calendar_dto: CalendarDto, calendar_id: UUID, db: AsyncSession = Depends(get_db)):
    calendar = await CalendarService.edit_calendar(calendar_dto, calendar_id, db)
    return {"Message: ": "Calendar successfully edited", "Body: ": calendar.dict()}

@router.delete("/delete/{calendar_id}", response_model=dict, status_code=200)
async def delete_calendar(calendar_id: UUID, db: AsyncSession = Depends(get_db)):
    calendar = await CalendarService.delete_calendar(calendar_id, db)
    return calendar

@router.get("/preview_merge", response_model=dict, status_code=200)
async def preview_merge_calendar(main_id: UUID, branch_id: UUID, db: AsyncSession = Depends(get_db)):
    calendar = await CalendarService.preview_merge_calendar(main_id, branch_id, db)
    return {"Message: ": "Calendar successfully merged", "Body: ": calendar.dict()}

@router.post("/save_merge", response_model=dict, status_code=200)
async def save_merge_calendar(main_id: UUID, branch_id: UUID, db: AsyncSession = Depends(get_db)):
    calendar = await CalendarService.save_merge_calendar(main_id, branch_id, db)
    return {"Message: ": "Calendar successfully merged", "Body: ": calendar.dict()}
