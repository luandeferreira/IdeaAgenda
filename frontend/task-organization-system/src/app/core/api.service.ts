import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AIParseResponse,
  AIProviderInfo,
  AISettings,
  AISuggestionRequest,
  AISuggestionResponse,
  CalendarStatus,
  CalendarSyncResult,
  LogEntry,
  LogStats,
  Task,
  TaskInput,
  TaskPriority,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  // ----- Tarefas -----
  listTasks(): Observable<Task[]> {
    return this.http.get<Task[]>('/api/tasks');
  }

  createTask(task: TaskInput): Observable<Task> {
    return this.http.post<Task>('/api/tasks', task);
  }

  updateTask(id: number, changes: Partial<TaskInput>): Observable<Task> {
    return this.http.patch<Task>(`/api/tasks/${id}`, changes);
  }

  deleteTask(id: number): Observable<void> {
    return this.http.delete<void>(`/api/tasks/${id}`);
  }

  // ----- Google Agenda -----
  calendarStatus(): Observable<CalendarStatus> {
    return this.http.get<CalendarStatus>('/api/calendar/status');
  }

  syncCalendar(): Observable<CalendarSyncResult> {
    return this.http.post<CalendarSyncResult>('/api/calendar/sync', {});
  }

  // ----- IA -----
  aiProvider(): Observable<AIProviderInfo> {
    return this.http.get<AIProviderInfo>('/api/ai/provider');
  }

  aiSuggestions(req: AISuggestionRequest): Observable<AISuggestionResponse> {
    return this.http.post<AISuggestionResponse>('/api/ai/suggestions', req);
  }

  aiApply(
    items: { task_id: number; start_at: string | null; end_at: string | null; priority: TaskPriority | null }[],
  ): Observable<Task[]> {
    return this.http.post<Task[]>('/api/ai/suggestions/apply', { items });
  }

  aiParse(text: string): Observable<AIParseResponse> {
    return this.http.post<AIParseResponse>('/api/ai/parse', { text });
  }

  // ----- Admin -----
  getAISettings(): Observable<AISettings> {
    return this.http.get<AISettings>('/api/admin/settings/ai');
  }

  saveAISettings(settings: { provider: string; openai_model?: string; gemini_model?: string }): Observable<AISettings> {
    return this.http.put<AISettings>('/api/admin/settings/ai', settings);
  }

  logs(filters: { limit?: number; level?: string; q?: string; before?: string }): Observable<LogEntry[]> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') params = params.set(key, String(value));
    }
    return this.http.get<LogEntry[]>('/api/admin/logs', { params });
  }

  logStats(): Observable<LogStats> {
    return this.http.get<LogStats>('/api/admin/logs/stats');
  }
}
