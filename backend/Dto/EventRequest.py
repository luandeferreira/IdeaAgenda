from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

class TokenRequest:
    token: str

class EventDateTime(BaseModel):
    dateTime: datetime
    timeZone: str

class Attendee(BaseModel):
    email: EmailStr

class ReminderOverride(BaseModel):
    method: str
    minutes: int

class Reminders(BaseModel):
    useDefault: bool
    overrides: List[ReminderOverride]

class EventRequest(BaseModel):
    summary: str
    location: Optional[str]
    description: Optional[str]
    start: EventDateTime
    end: EventDateTime
    attendees: Optional[List[Attendee]] = []
    reminders: Optional[Reminders]
    access_token: Optional[str] = None