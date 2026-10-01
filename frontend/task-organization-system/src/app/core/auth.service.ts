import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, map, of, tap } from 'rxjs';

import { AuthConfig, TokenResponse, User } from './models';

const TOKEN_KEY = 'ideaagenda_token';

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  private readonly tokenSignal = signal<string | null>(readToken());
  readonly user = signal<User | null>(null);
  readonly isLoggedIn = computed(() => !!this.tokenSignal());
  readonly isAdmin = computed(() => !!this.user()?.is_admin);

  get token(): string | null {
    return this.tokenSignal();
  }

  setToken(token: string): void {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* armazenamento indisponível: mantém só em memória */
    }
    this.tokenSignal.set(token);
  }

  config(): Observable<AuthConfig> {
    return this.http.get<AuthConfig>('/api/auth/config');
  }

  googleLoginUrl(): string {
    return '/api/auth/google/login';
  }

  devLogin(email: string, name: string): Observable<User> {
    return this.http.post<TokenResponse>('/api/auth/dev-login', { email, name }).pipe(
      tap((res) => {
        this.setToken(res.access_token);
        this.user.set(res.user);
        this.syncTimezone(res.user);
      }),
      map((res) => res.user),
    );
  }

  /** Carrega o usuário logado; retorna null se o token for inválido. */
  loadMe(): Observable<User | null> {
    if (!this.token) return of(null);
    if (this.user()) return of(this.user());
    return this.http.get<User>('/api/auth/me').pipe(
      tap((u) => {
        this.user.set(u);
        this.syncTimezone(u);
      }),
      catchError(() => {
        this.clear();
        return of(null);
      }),
    );
  }

  updatePreferences(prefs: { timezone?: string; calendar_sync_enabled?: boolean }): Observable<User> {
    return this.http.patch<User>('/api/auth/me', prefs).pipe(tap((u) => this.user.set(u)));
  }

  /** Mantém o fuso do usuário igual ao do navegador (usado nos eventos do Google e pela IA). */
  private syncTimezone(user: User): void {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (tz && tz !== user.timezone) {
      this.updatePreferences({ timezone: tz }).subscribe({ error: () => undefined });
    }
  }

  clear(): void {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
    this.tokenSignal.set(null);
    this.user.set(null);
  }

  logout(): void {
    this.clear();
    this.router.navigate(['/login']);
  }
}
