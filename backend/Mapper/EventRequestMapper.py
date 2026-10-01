from backend.Dto.EventRequest import EventRequest, EventDateTime, Attendee, Reminders, ReminderOverride
from backend.Dto.TasksDto import TaskDto
from datetime import timedelta

class EventRequestMapper:

    @staticmethod
    def dto_to_request(task: TaskDto) -> EventRequest:
        time_zone = "America/Sao_Paulo"

        start = EventDateTime(
            dateTime=task.created_at,
            timeZone=time_zone
        )

        end = EventDateTime(
            dateTime=task.created_at + timedelta(hours=1),
            timeZone=time_zone
        )

        reminders = Reminders(
            useDefault=False,
            overrides=[
                ReminderOverride(method="popup", minutes=10)
            ]
        )

        return EventRequest(
            summary=task.summary,
            location=task.location if task.location else None,
            description=task.description if task.description else None,
            start=start,
            end=end,
            attendees=[],
            reminders=reminders
        )
