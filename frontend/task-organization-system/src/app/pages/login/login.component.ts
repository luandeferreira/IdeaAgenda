import { Component, OnInit, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { errorMessage } from '../../core/auth.interceptor';
import { AuthService } from '../../core/auth.service';
import { AuthConfig } from '../../core/models';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './login.component.html',
})
export class LoginComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  /** Erro vindo do callback do Google (?error=...) */
  readonly error = input<string>();

  readonly config = signal<AuthConfig | null>(null);
  readonly message = signal<string | null>(null);
  readonly loading = signal(false);
  email = '';
  name = '';

  ngOnInit(): void {
    if (this.error()) this.message.set(this.error() ?? null);
    this.auth.config().subscribe({
      next: (cfg) => this.config.set(cfg),
      error: (err) => this.message.set(errorMessage(err)),
    });
  }

  googleLogin(): void {
    window.location.href = this.auth.googleLoginUrl();
  }

  devLogin(): void {
    if (!this.email) return;
    this.loading.set(true);
    this.auth.devLogin(this.email, this.name).subscribe({
      next: () => this.router.navigate(['/']),
      error: (err) => {
        this.loading.set(false);
        this.message.set(errorMessage(err));
      },
    });
  }
}
