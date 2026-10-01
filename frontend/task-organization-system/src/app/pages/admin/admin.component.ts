import { DatePipe, JsonPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { errorMessage } from '../../core/auth.interceptor';
import { AIProviderName, AISettings, LogEntry, LogStats } from '../../core/models';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [FormsModule, DatePipe, JsonPipe],
  templateUrl: './admin.component.html',
})
export class AdminComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly settings = signal<AISettings | null>(null);
  readonly saving = signal(false);
  readonly message = signal<{ kind: 'success' | 'error'; text: string } | null>(null);
  provider: AIProviderName = 'openai';
  openaiModel = '';
  geminiModel = '';

  readonly logs = signal<LogEntry[]>([]);
  readonly stats = signal<LogStats | null>(null);
  readonly logsLoading = signal(false);
  readonly expanded = signal<string | null>(null);
  filters = { level: '', q: '', limit: 100 };

  ngOnInit(): void {
    this.api.getAISettings().subscribe({
      next: (s) => this.applySettings(s),
      error: (err) => this.message.set({ kind: 'error', text: errorMessage(err) }),
    });
    this.loadLogs();
  }

  private applySettings(s: AISettings): void {
    this.settings.set(s);
    this.provider = s.provider;
    this.openaiModel = s.openai_model;
    this.geminiModel = s.gemini_model;
  }

  save(): void {
    this.saving.set(true);
    this.api
      .saveAISettings({ provider: this.provider, openai_model: this.openaiModel.trim(), gemini_model: this.geminiModel.trim() })
      .subscribe({
        next: (s) => {
          this.saving.set(false);
          this.applySettings(s);
          this.message.set({ kind: 'success', text: `Provedor de IA definido como ${s.provider === 'gemini' ? 'Google Gemini' : 'OpenAI'}.` });
        },
        error: (err) => {
          this.saving.set(false);
          this.message.set({ kind: 'error', text: errorMessage(err) });
        },
      });
  }

  loadLogs(append = false): void {
    this.logsLoading.set(true);
    const current = this.logs();
    const before = append && current.length ? current[current.length - 1].id : undefined;
    this.api.logs({ ...this.filters, before }).subscribe({
      next: (entries) => {
        this.logsLoading.set(false);
        this.logs.set(append ? [...current, ...entries] : entries);
      },
      error: (err) => {
        this.logsLoading.set(false);
        this.message.set({ kind: 'error', text: errorMessage(err) });
      },
    });
    if (!append) this.api.logStats().subscribe({ next: (s) => this.stats.set(s), error: () => undefined });
  }

  details(log: LogEntry): Record<string, unknown> {
    return log.exception ? { ...(log.extra ?? {}), exception: log.exception } : (log.extra ?? {});
  }

  toggle(id: string): void {
    this.expanded.set(this.expanded() === id ? null : id);
  }
}
