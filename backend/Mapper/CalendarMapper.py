from backend.Model.Calendar import Calendar
from backend.Dto.CalendarDto import CalendarDto
from backend.Mapper.TasksMapper import TasksMapper
from typing import List
from datetime import timezone

class CalendarMapper:
    @staticmethod
    def remove_tz(dt):
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt and dt.tzinfo else dt

    @staticmethod
    def toModel(calendarDto: CalendarDto) -> Calendar:
        tasks = TasksMapper.toModelList(calendarDto.tasks) if calendarDto.tasks else []

        for task in tasks:
            task.calendar_id = calendarDto.id

        return Calendar(
            id=calendarDto.id,
            name=calendarDto.name,
            created_at=CalendarMapper.remove_tz(calendarDto.created_at),
            updated_at=CalendarMapper.remove_tz(calendarDto.updated_at),
            created_by=calendarDto.created_by,
            tasks=tasks
        )

    @staticmethod
    def toDto(calendar: Calendar) -> CalendarDto:
        return CalendarDto(
            id=calendar.id,
            name=calendar.name,
            created_at=CalendarMapper.remove_tz(calendar.created_at),
            updated_at=CalendarMapper.remove_tz(calendar.updated_at),
            created_by=calendar.created_by,
            tasks=TasksMapper.toDtoList(calendar.tasks) if hasattr(calendar, "tasks") else []
        )