from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.Mapper.CalendarMapper import CalendarMapper
from backend.Dto.CalendarDto import CalendarDto
from backend.Model.Calendar import Calendar
from fastapi import HTTPException, status, Request
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID


async def get_all_calendars(db: AsyncSession):
    result = await db.execute(select(Calendar).options(selectinload(Calendar.tasks)))
    calendars = result.scalars().all()

    return [CalendarMapper.toDto(calendar) for calendar in calendars]

async def get_calendar_by_id(calendar_id: UUID, db: AsyncSession):
    result = await db.execute(select(Calendar).options(joinedload(Calendar.tasks)).where(Calendar.id == calendar_id))
    calendar = result.unique().scalar_one_or_none()

    return CalendarMapper.toDto(calendar)

async def get_calendar_by_creator(creator: str, db: AsyncSession):
    result = await db.execute(select(Calendar).options(joinedload(Calendar.tasks)).where(Calendar.created_by == creator))
    calendar = result.unique().scalar_one_or_none()

    if not calendar:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Calendar with creator {creator} doesn't exists")

    return CalendarMapper.toDto(calendar)


async def create_calendar(calendar_dto: CalendarDto, db: AsyncSession, request: Request):
    if calendar_dto.created_by is None:
        if request.session['user'].get('email') is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Not authenticated.")

        result = await db.execute(select(Calendar).where(Calendar.id == calendar_dto.id))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Calendar with id {calendar_dto.id} already exists")

        calendar_dto.created_by = request.session['user'].get('email')

    calendar_model = CalendarMapper.toModel(calendar_dto)

    db.add(calendar_model)
    await db.commit()
    await db.refresh(calendar_model)

    result = await db.execute(
        select(Calendar).options(selectinload(Calendar.tasks)).where(Calendar.id == calendar_model.id)
    )
    calendar_with_tasks = result.scalar_one()

    return CalendarMapper.toDto(calendar_with_tasks)

async def edit_calendar(calendar_dto: CalendarDto, calendar_id: UUID, db: AsyncSession):
    result = await db.execute(select(Calendar).where(Calendar.id == calendar_id))
    calendar = result.scalar_one_or_none()

    if not calendar:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Calendar with id {calendar_id} not found")

    calendar.id = calendar_id
    calendar.name = calendar_dto.name

    await db.commit()
    await db.refresh(calendar)

    result = await db.execute(
        select(Calendar).options(selectinload(Calendar.tasks)).where(Calendar.id == calendar.id)
    )
    calendar_with_tasks = result.scalar_one()

    return CalendarMapper.toDto(calendar_with_tasks)

async def delete_calendar(calendar_id: UUID, db: AsyncSession):
    result = await db.execute(select(Calendar).where(Calendar.id == calendar_id))
    calendar = result.scalar_one_or_none()

    if not calendar:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found")

    await db.delete(calendar)
    await db.commit()

    return {"Message": "Calendar deleted successfully", "Id": calendar_id}

async def preview_merge_calendar(id_1: UUID, id_2: UUID, db: AsyncSession):
    result_1 = await db.execute(select(Calendar).options(joinedload(Calendar.tasks)).where(Calendar.id == id_1))
    main_calendar = result_1.unique().scalar_one_or_none()

    if not main_calendar:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Main calendar not found.")

    result_2 = await db.execute(select(Calendar).options(joinedload(Calendar.tasks)).where(Calendar.id == id_2))
    branch_calendar = result_2.unique().scalar_one_or_none()

    if not branch_calendar:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch calendar not found.")

    for temp in branch_calendar.tasks:
        main_calendar.tasks.append(temp)

    return CalendarMapper.toDto(main_calendar)

async def save_merge_calendar(id_1: UUID, id_2: UUID, db: AsyncSession):
    result_1 = await db.execute(select(Calendar).options(joinedload(Calendar.tasks)).where(Calendar.id == id_1))
    main_calendar = result_1.unique().scalar_one_or_none()

    if not main_calendar:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Main calendar not found.")

    result_2 = await db.execute(select(Calendar).options(joinedload(Calendar.tasks)).where(Calendar.id == id_2))
    branch_calendar = result_2.unique().scalar_one_or_none()

    if not branch_calendar:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch calendar not found.")

    for temp in branch_calendar.tasks:
        main_calendar.tasks.append(temp)
        temp.calendar_id = id_2

    await db.commit()
    await db.refresh(main_calendar)

    result = await db.execute(
        select(Calendar).options(selectinload(Calendar.tasks)).where(Calendar.id == main_calendar.id))
    calendar_with_tasks = result.scalar_one()

    return CalendarMapper.toDto(calendar_with_tasks)
