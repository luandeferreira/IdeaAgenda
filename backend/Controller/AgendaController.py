from fastapi.params import Depends
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from backend.Dto.EventRequest import EventRequest, Reminders, ReminderOverride, Attendee, EventDateTime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from backend.Mapper.TasksMapper import TasksMapper
from backend.Mapper.EventRequestMapper import EventRequest, EventRequestMapper
from backend.Dto.TasksDto import TaskDto
from backend.Service.CalendarService import get_calendar_by_id
from backend.Service.TasksService import create_task
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from uuid import UUID
from datetime import datetime

from fastapi import HTTPException, APIRouter, Request

router = APIRouter()

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

@router.get("/event/preview/import/{calendar_id}")
async def preview_import_google_claendar(calendar_id: UUID, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        if 'user' not in request.session:
            raise HTTPException(status_code=401, detail="Não autenticado")

        access_token = request.session['user'].get('access_token')
        if not access_token:
            raise HTTPException(status_code=400, detail="Token de acesso não encontrado")

        creds = Credentials(token=access_token, scopes=SCOPES)
        service = build("calendar", "v3", credentials=creds)

        events_result = service.events().list(
            calendarId="primary",
            maxResults=10,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        calendar = await get_calendar_by_id(calendar_id, db)

        for temp in events_result.get('items'):
            start_date = temp.get('start', {}).get('dateTime') or temp.get('start', {}).get('date')
            created_at = datetime.fromisoformat(start_date.replace("Z", "+00:00")) if start_date else datetime.utcnow()

            calendar.tasks.append(TaskDto(
                summary=temp.get('summary', 'Sem título'),
                description=temp.get('description', ''),
                location=temp.get('location', ''),
                updated_at=datetime.utcnow(),
                created_at=created_at,
                completion_date=created_at,
                completed=False,
                calendar_id=calendar.id
            ))

        return calendar

    except HttpError as error:
        raise HTTPException(status_code=400, detail=f"Erro na API do Google: {str(error)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@router.get("/event/import/{calendar_id}")
async def preview_import_google_calendar(calendar_id: UUID, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        if 'user' not in request.session:
            raise HTTPException(status_code=401, detail="Não autenticado")

        access_token = request.session['user'].get('access_token')
        if not access_token:
            raise HTTPException(status_code=400, detail="Token de acesso não encontrado")

        creds = Credentials(token=access_token, scopes=SCOPES)
        service = build("calendar", "v3", credentials=creds)

        events_result = service.events().list(
            calendarId="primary",
            maxResults=10,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        calendar = await get_calendar_by_id(calendar_id, db)
        imported_tasks = []

        for temp in events_result.get('items'):
            start_date = temp.get('start', {}).get('dateTime') or temp.get('start', {}).get('date')
            created_at = datetime.fromisoformat(start_date.replace("Z", "+00:00")) if start_date else datetime.utcnow()

            new_taskDto = TaskDto(
                summary=temp.get('summary', 'Sem título'),
                description=temp.get('description', ''),
                location=temp.get('location', ''),
                updated_at=datetime.utcnow(),
                created_at=created_at,
                completion_date=created_at,
                completed=False,
                calendar_id=calendar.id
            )

            await create_task(new_taskDto, db)
            imported_tasks.append(new_taskDto)

        return imported_tasks

    except HttpError as error:
        raise HTTPException(status_code=400, detail=f"Erro na API do Google: {str(error)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@router.get("/events/post/{calendar_id}")
async def events_post(request: Request, calendar_id: UUID, db: AsyncSession = Depends(get_db)):
    calendar = await get_calendar_by_id(calendar_id, db)
    response_list = []

    for temp in calendar.tasks:
        event_request = EventRequestMapper.dto_to_request(temp)
        event_request.access_token = request.session['user'].get('access_token')

        link = await post_google_calendar_events(request, event_request=event_request)
        response_list.append(link)

    return response_list

@router.get("/events/get")
async def get_google_calendar_events(request: Request):
    try:
        if 'user' not in request.session:
            raise HTTPException(status_code=401, detail="Não autenticado")

        access_token = request.session['user'].get('access_token')
        if not access_token:
            raise HTTPException(status_code=400, detail="Token de acesso não encontrado")

        creds = Credentials(token=access_token, scopes=SCOPES)
        service = build("calendar", "v3", credentials=creds)

        events_result = service.events().list(
            calendarId="primary",
            maxResults=50,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        return {"events": events_result.get('items', [])}

    except HttpError as error:
        raise HTTPException(status_code=400, detail=f"Erro na API do Google: {str(error)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

async def post_google_calendar_events(request: Request, event_request: EventRequest):
    try:
        if 'user' not in request.session and not event_request.access_token:
            raise HTTPException(status_code=401, detail="Não autenticado")

        access_token = (
            request.session['user'].get('access_token')
            if 'user' in request.session else event_request.access_token
        )

        if not access_token:
            raise HTTPException(status_code=400, detail="Token de acesso não encontrado")

        creds = Credentials(
            token=access_token,
            scopes=SCOPES
        )
        service = build("calendar", "v3", credentials=creds)

        event = {
            'summary': event_request.summary,
            'location': event_request.location,
            'description': event_request.description,
            'start': {
                'dateTime': event_request.start.dateTime.isoformat(),
                'timeZone': event_request.start.timeZone,
            },
            'end': {
                'dateTime': event_request.end.dateTime.isoformat(),
                'timeZone': event_request.end.timeZone,
            },
            'attendees': [{'email': attendee.email} for attendee in event_request.attendees],
            'reminders': {
                'useDefault': event_request.reminders.useDefault if event_request.reminders else True,
                'overrides': [
                    {
                        'method': r.method,
                        'minutes': r.minutes
                    } for r in event_request.reminders.overrides
                ] if event_request.reminders and event_request.reminders.overrides else []
            }
        }

        created_event = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()

        return {
            "message": "Evento criado com sucesso!",
            "event_link": created_event.get('htmlLink')
        }

    except HttpError as error:
        raise HTTPException(status_code=400, detail=f"Erro na API do Google: {str(error)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")