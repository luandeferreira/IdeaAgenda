from backend.Model.Tasks import Task
from backend.Dto.TasksDto import TaskDto
from typing import List
from datetime import timezone, datetime

class TasksMapper:
    @staticmethod
    def remove_tz(dt):
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt and dt.tzinfo else dt

    @staticmethod
    def toModel(taskDto: TaskDto) -> Task:
        return Task(
            id=taskDto.id,
            summary=taskDto.summary,
            description=taskDto.description,
            location=taskDto.location,
            completion_date=TasksMapper.remove_tz(taskDto.completion_date),
            created_at=TasksMapper.remove_tz(taskDto.created_at) or datetime.utcnow(),
            updated_at=TasksMapper.remove_tz(taskDto.updated_at) or datetime.utcnow(),
            completed_at=TasksMapper.remove_tz(taskDto.completed_at),
            completed=taskDto.completed,
            calendar_id=taskDto.calendar_id
        )

    @staticmethod
    def toDto(task: Task) -> TaskDto:
        return TaskDto(
            id=task.id,
            summary=task.summary,
            description=task.description,
            location=task.location,
            completion_date=TasksMapper.remove_tz(task.completion_date),
            created_at=TasksMapper.remove_tz(task.created_at),
            updated_at=TasksMapper.remove_tz(task.updated_at),
            completed_at=TasksMapper.remove_tz(task.completed_at),
            completed=task.completed,
            calendar_id=task.calendar_id
        )

    @staticmethod
    def toModelList(taskDtos: List[TaskDto]) -> List[Task]:
        return [TasksMapper.toModel(dto) for dto in taskDtos]

    @staticmethod
    def toDtoList(tasks: List[Task]) -> List[TaskDto]:
        return [TasksMapper.toDto(task) for task in tasks]
