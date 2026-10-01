export type TaskPriority = 'low' | 'medium' | 'high';
export type TaskStatus = 'todo' | 'in_progress' | 'done';
export type TaskSource = 'app' | 'google' | 'ai';
export type AIProviderName = 'openai' | 'gemini';

export interface User {
  id: number;
  email: string;
  name: string;
  picture: string | null;
  is_admin: boolean;
  timezone: string;
  google_connected: boolean;
  calendar_sync_enabled: boolean;
  last_calendar_sync_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface AuthConfig {
  google_enabled: boolean;
  dev_login_enabled: boolean;
}

export interface Task {
  id: number;
  title: string;
  description: string;
  category: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  source: TaskSource;
  start_at: string | null;
  end_at: string | null;
  all_day: boolean;
  estimated_minutes: number | null;
  sync_to_calendar: boolean;
  google_event_id: string | null;
  last_synced_at: string | null;
  sync_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskInput {
  title: string;
  description?: string;
  category?: string | null;
  priority?: TaskPriority;
  status?: TaskStatus;
  start_at?: string | null;
  end_at?: string | null;
  all_day?: boolean;
  estimated_minutes?: number | null;
  sync_to_calendar?: boolean;
}

export interface CalendarStatus {
  google_oauth_enabled: boolean;
  connected: boolean;
  sync_enabled: boolean;
  last_sync_at: string | null;
}

export interface CalendarSyncResult {
  pushed: number;
  imported: number;
  updated: number;
  deleted: number;
  errors: string[];
  synced_at: string;
}

export interface AISuggestionRequest {
  horizon_days: number;
  work_start: string;
  work_end: string;
  goal?: string | null;
}

export interface AITaskSuggestion {
  task_id: number;
  title: string;
  start_at: string | null;
  end_at: string | null;
  priority: TaskPriority | null;
  reason: string;
}

export interface AISuggestionResponse {
  provider: AIProviderName;
  model: string;
  summary: string;
  suggestions: AITaskSuggestion[];
  tips: string[];
}

export interface AIParseResponse {
  provider: AIProviderName;
  task: TaskInput;
}

export interface AIProviderInfo {
  provider: AIProviderName;
  model: string;
  available: boolean;
}

export interface AISettings {
  provider: AIProviderName;
  openai_model: string;
  gemini_model: string;
  openai_configured: boolean;
  gemini_configured: boolean;
}

export interface LogEntry {
  id: string;
  ts: string;
  level: string;
  logger: string;
  message: string;
  extra: Record<string, unknown> | null;
  exception: string | null;
}

export interface LogStats {
  stream: string;
  entries: number;
  max_entries: number;
}

export const PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: 'Baixa',
  medium: 'Média',
  high: 'Alta',
};

export const STATUS_LABELS: Record<TaskStatus, string> = {
  todo: 'A fazer',
  in_progress: 'Em andamento',
  done: 'Concluída',
};
