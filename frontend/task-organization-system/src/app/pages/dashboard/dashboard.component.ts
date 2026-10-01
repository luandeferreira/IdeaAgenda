import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { errorMessage } from '../../core/auth.interceptor';
import { AuthService } from '../../core/auth.service';
import {
  AIProviderInfo,
  AISuggestionResponse,
  CalendarStatus,
  PRIORITY_LABELS,
  STATUS_LABELS,
  Task,
  TaskInput,
  TaskPriority,
  TaskStatus,
} from '../../core/models';

type DateMode = 'none' | 'timed' | 'allday';
type Filter = 'open' | 'all' | 'done';

interface TaskForm {
  id: number | null;
  title: string;
  description: string;
  category: string;
  priority: TaskPriority;
  status: TaskStatus;
  dateMode: DateMode;
  start: string; // datetime-local
  end: string; // datetime-local
  day: string; // date
  estimated_minutes: number | null;
  sync_to_calendar: boolean;
}

interface TaskGroup {
  key: string;
  label: string;
  tasks: Task[];
}

const pad = (n: number) => String(n).padStart(2, '0');

/** ISO (UTC) -> valor de input datetime-local no fuso do navegador */
export function toLocalInput(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function toDateInput(iso: string | null): string {
  return toLocalInput(iso).slice(0, 10);
}

/** valor de input datetime-local/date -> ISO com fuso */
export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const d = value.length === 10 ? new Date(`${value}T00:00`) : new Date(value);
  return isNaN(d.getTime()) ? null : d.toISOString();
}

function emptyForm(): TaskForm {
  return {
    id: null,
    title: '',
    description: '',
    category: '',
    priority: 'medium',
    status: 'todo',
    dateMode: 'none',
    start: '',
    end: '',
    day: '',
    estimated_minutes: null,
    sync_to_calendar: true,
  };
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [FormsModule, DatePipe],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly auth = inject(AuthService);

  readonly priorityLabels = PRIORITY_LABELS;
  readonly statusLabels = STATUS_LABELS;
  readonly priorities: TaskPriority[] = ['high', 'medium', 'low'];
  readonly statuses: TaskStatus[] = ['todo', 'in_progress', 'done'];

  readonly tasks = signal<Task[]>([]);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly toast = signal<{ kind: 'success' | 'error' | 'info'; text: string } | null>(null);
  readonly filter = signal<Filter>('open');
  readonly search = signal('');
  readonly formOpen = signal(false);
  form: TaskForm = emptyForm();

  // Google Agenda
  readonly calendar = signal<CalendarStatus | null>(null);
  readonly syncing = signal(false);

  // IA
  readonly aiInfo = signal<AIProviderInfo | null>(null);
  quickText = '';
  readonly parsing = signal(false);
  readonly aiPanelOpen = signal(false);
  readonly aiLoading = signal(false);
  readonly aiResult = signal<AISuggestionResponse | null>(null);
  readonly aiSelected = signal<Set<number>>(new Set());
  aiRequest = { horizon_days: 7, work_start: '09:00', work_end: '18:00', goal: '' };

  private toastTimer: ReturnType<typeof setTimeout> | undefined;

  readonly stats = computed(() => {
    const all = this.tasks();
    const today = startOfDay(new Date()).getTime();
    return {
      open: all.filter((t) => t.status !== 'done').length,
      done: all.filter((t) => t.status === 'done').length,
      overdue: all.filter((t) => t.status !== 'done' && t.start_at && startOfDay(new Date(t.start_at)).getTime() < today).length,
      unscheduled: all.filter((t) => t.status !== 'done' && !t.start_at).length,
    };
  });

  readonly groups = computed<TaskGroup[]>(() => {
    const term = this.search().trim().toLowerCase();
    const filter = this.filter();
    let list = this.tasks();
    if (filter === 'open') list = list.filter((t) => t.status !== 'done');
    if (filter === 'done') list = list.filter((t) => t.status === 'done');
    if (term) {
      list = list.filter((t) =>
        [t.title, t.description, t.category ?? ''].some((v) => v.toLowerCase().includes(term)),
      );
    }

    const today = startOfDay(new Date()).getTime();
    const day = 24 * 60 * 60 * 1000;
    const buckets: Record<string, TaskGroup> = {
      overdue: { key: 'overdue', label: 'Atrasadas', tasks: [] },
      today: { key: 'today', label: 'Hoje', tasks: [] },
      tomorrow: { key: 'tomorrow', label: 'Amanhã', tasks: [] },
      week: { key: 'week', label: 'Próximos 7 dias', tasks: [] },
      later: { key: 'later', label: 'Mais tarde', tasks: [] },
      unscheduled: { key: 'unscheduled', label: 'Sem data', tasks: [] },
      done: { key: 'done', label: 'Concluídas', tasks: [] },
    };

    for (const t of list) {
      if (t.status === 'done') {
        buckets['done'].tasks.push(t);
        continue;
      }
      if (!t.start_at) {
        buckets['unscheduled'].tasks.push(t);
        continue;
      }
      const startDay = startOfDay(new Date(t.start_at)).getTime();
      if (startDay < today) {
        buckets['overdue'].tasks.push(t);
      } else if (startDay === today) {
        buckets['today'].tasks.push(t);
      } else if (startDay === today + day) {
        buckets['tomorrow'].tasks.push(t);
      } else if (startDay < today + 8 * day) {
        buckets['week'].tasks.push(t);
      } else {
        buckets['later'].tasks.push(t);
      }
    }
    const order = { high: 0, medium: 1, low: 2 } as const;
    buckets['unscheduled'].tasks.sort((a, b) => order[a.priority] - order[b.priority]);
    buckets['done'].tasks.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    return Object.values(buckets).filter((g) => g.tasks.length > 0);
  });

  ngOnInit(): void {
    this.loadTasks();
    this.api.calendarStatus().subscribe({ next: (s) => this.calendar.set(s), error: () => undefined });
    this.api.aiProvider().subscribe({ next: (p) => this.aiInfo.set(p), error: () => undefined });
  }

  loadTasks(): void {
    this.loading.set(true);
    this.api.listTasks().subscribe({
      next: (tasks) => {
        this.tasks.set(tasks);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.notify('error', errorMessage(err, 'Não foi possível carregar as tarefas.'));
      },
    });
  }

  notify(kind: 'success' | 'error' | 'info', text: string): void {
    this.toast.set({ kind, text });
    clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => this.toast.set(null), 5000);
  }

  // ---------- Formulário ----------
  newTask(): void {
    this.form = emptyForm();
    this.formOpen.set(true);
  }

  editTask(task: Task): void {
    this.form = {
      id: task.id,
      title: task.title,
      description: task.description,
      category: task.category ?? '',
      priority: task.priority,
      status: task.status,
      dateMode: !task.start_at ? 'none' : task.all_day ? 'allday' : 'timed',
      start: task.all_day ? '' : toLocalInput(task.start_at),
      end: task.all_day ? '' : toLocalInput(task.end_at),
      day: task.all_day ? toDateInput(task.start_at) : '',
      estimated_minutes: task.estimated_minutes,
      sync_to_calendar: task.sync_to_calendar,
    };
    this.formOpen.set(true);
    setTimeout(() => document.getElementById('task-title')?.focus());
  }

  closeForm(): void {
    this.formOpen.set(false);
    this.form = emptyForm();
  }

  private formToInput(): TaskInput {
    const f = this.form;
    let start_at: string | null = null;
    let end_at: string | null = null;
    if (f.dateMode === 'timed') {
      start_at = fromLocalInput(f.start);
      end_at = start_at ? fromLocalInput(f.end) : null;
    } else if (f.dateMode === 'allday') {
      start_at = fromLocalInput(f.day);
    }
    return {
      title: f.title.trim(),
      description: f.description.trim(),
      category: f.category.trim() || null,
      priority: f.priority,
      status: f.status,
      start_at,
      end_at,
      all_day: f.dateMode === 'allday',
      estimated_minutes: f.estimated_minutes || null,
      sync_to_calendar: f.sync_to_calendar,
    };
  }

  saveTask(): void {
    const input = this.formToInput();
    if (!input.title) return;
    if (this.form.dateMode === 'timed' && !input.start_at) {
      this.notify('error', 'Informe a data e hora de início.');
      return;
    }
    if (input.start_at && input.end_at && input.end_at < input.start_at) {
      this.notify('error', 'O término deve ser depois do início.');
      return;
    }
    this.saving.set(true);
    const id = this.form.id;
    const request = id ? this.api.updateTask(id, input) : this.api.createTask(input);
    request.subscribe({
      next: (task) => {
        this.saving.set(false);
        this.upsertLocal(task);
        this.closeForm();
        this.notify(task.sync_error ? 'error' : 'success', task.sync_error
          ? `Tarefa salva, mas não sincronizou com o Google: ${task.sync_error}`
          : id ? 'Tarefa atualizada.' : 'Tarefa criada.');
      },
      error: (err) => {
        this.saving.set(false);
        this.notify('error', errorMessage(err));
      },
    });
  }

  private upsertLocal(task: Task): void {
    const list = this.tasks();
    const idx = list.findIndex((t) => t.id === task.id);
    this.tasks.set(idx === -1 ? [...list, task] : list.map((t) => (t.id === task.id ? task : t)));
  }

  toggleDone(task: Task): void {
    const status: TaskStatus = task.status === 'done' ? 'todo' : 'done';
    this.upsertLocal({ ...task, status });
    this.api.updateTask(task.id, { status }).subscribe({
      next: (t) => this.upsertLocal(t),
      error: (err) => {
        this.upsertLocal(task);
        this.notify('error', errorMessage(err));
      },
    });
  }

  deleteTask(task: Task): void {
    if (!confirm(`Excluir "${task.title}"?${task.google_event_id ? ' O evento também será removido do Google Agenda.' : ''}`)) return;
    this.api.deleteTask(task.id).subscribe({
      next: () => {
        this.tasks.set(this.tasks().filter((t) => t.id !== task.id));
        if (this.form.id === task.id) this.closeForm();
        this.notify('success', 'Tarefa excluída.');
      },
      error: (err) => this.notify('error', errorMessage(err)),
    });
  }

  // ---------- Google Agenda ----------
  syncCalendar(): void {
    this.syncing.set(true);
    this.api.syncCalendar().subscribe({
      next: (r) => {
        this.syncing.set(false);
        const cal = this.calendar();
        if (cal) this.calendar.set({ ...cal, last_sync_at: r.synced_at });
        const parts = [
          r.imported && `${r.imported} importada(s)`,
          r.updated && `${r.updated} atualizada(s)`,
          r.pushed && `${r.pushed} enviada(s)`,
          r.deleted && `${r.deleted} removida(s)`,
        ].filter(Boolean);
        this.notify(
          r.errors.length ? 'error' : 'success',
          r.errors.length
            ? `Sincronizado com ${r.errors.length} erro(s): ${r.errors[0]}`
            : parts.length ? `Google Agenda sincronizado: ${parts.join(', ')}.` : 'Tudo em dia com o Google Agenda.',
        );
        this.loadTasks();
      },
      error: (err) => {
        this.syncing.set(false);
        this.notify('error', errorMessage(err));
      },
    });
  }

  connectGoogle(): void {
    window.location.href = this.auth.googleLoginUrl();
  }

  toggleAutoSync(enabled: boolean): void {
    this.auth.updatePreferences({ calendar_sync_enabled: enabled }).subscribe({
      next: (u) => {
        const cal = this.calendar();
        if (cal) this.calendar.set({ ...cal, sync_enabled: u.calendar_sync_enabled });
      },
      error: (err) => this.notify('error', errorMessage(err)),
    });
  }

  // ---------- IA ----------
  quickAdd(): void {
    const text = this.quickText.trim();
    if (!text) return;
    this.parsing.set(true);
    this.api.aiParse(text).subscribe({
      next: (res) => {
        this.parsing.set(false);
        const t = res.task;
        this.form = {
          ...emptyForm(),
          title: t.title,
          description: t.description ?? '',
          category: t.category ?? '',
          priority: t.priority ?? 'medium',
          dateMode: !t.start_at ? 'none' : t.all_day ? 'allday' : 'timed',
          start: t.start_at && !t.all_day ? toLocalInput(t.start_at) : '',
          end: t.end_at && !t.all_day ? toLocalInput(t.end_at) : '',
          day: t.start_at && t.all_day ? toDateInput(t.start_at) : '',
          estimated_minutes: t.estimated_minutes ?? null,
        };
        this.quickText = '';
        this.formOpen.set(true);
        this.notify('info', 'A IA preencheu a tarefa. Revise e salve.');
      },
      error: (err) => {
        this.parsing.set(false);
        this.notify('error', errorMessage(err));
      },
    });
  }

  openAiPanel(): void {
    this.aiPanelOpen.set(true);
    this.aiResult.set(null);
  }

  requestSuggestions(): void {
    this.aiLoading.set(true);
    this.aiResult.set(null);
    this.api
      .aiSuggestions({ ...this.aiRequest, goal: this.aiRequest.goal.trim() || null })
      .subscribe({
        next: (res) => {
          this.aiLoading.set(false);
          this.aiResult.set(res);
          this.aiSelected.set(new Set(res.suggestions.filter((s) => s.start_at || s.priority).map((s) => s.task_id)));
        },
        error: (err) => {
          this.aiLoading.set(false);
          this.notify('error', errorMessage(err));
        },
      });
  }

  toggleSuggestion(taskId: number): void {
    const next = new Set(this.aiSelected());
    if (next.has(taskId)) next.delete(taskId);
    else next.add(taskId);
    this.aiSelected.set(next);
  }

  applySuggestions(): void {
    const result = this.aiResult();
    if (!result) return;
    const items = result.suggestions
      .filter((s) => this.aiSelected().has(s.task_id))
      .map((s) => ({ task_id: s.task_id, start_at: s.start_at, end_at: s.end_at, priority: s.priority }));
    if (!items.length) return;
    this.aiLoading.set(true);
    this.api.aiApply(items).subscribe({
      next: (tasks) => {
        this.aiLoading.set(false);
        tasks.forEach((t) => this.upsertLocal(t));
        this.aiPanelOpen.set(false);
        this.notify('success', `${tasks.length} sugestão(ões) aplicada(s).`);
      },
      error: (err) => {
        this.aiLoading.set(false);
        this.notify('error', errorMessage(err));
      },
    });
  }

  providerLabel(p: string | undefined): string {
    return p === 'gemini' ? 'Google Gemini' : 'OpenAI';
  }

  isSameDay(a: string | null, b: string | null): boolean {
    if (!a || !b) return true;
    return new Date(a).toDateString() === new Date(b).toDateString();
  }
}
