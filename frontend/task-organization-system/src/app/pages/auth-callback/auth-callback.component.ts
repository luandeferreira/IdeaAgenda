import { Component, OnInit, inject } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-auth-callback',
  standalone: true,
  template: `<div class="card center-card"><div class="spinner"></div><p>Entrando com o Google…</p></div>`,
})
export class AuthCallbackComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  ngOnInit(): void {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    const token = params.get('token');
    // Remove o token da barra de endereço
    history.replaceState(null, '', window.location.pathname);
    if (!token) {
      this.router.navigate(['/login'], { queryParams: { error: 'Token não recebido' } });
      return;
    }
    this.auth.setToken(token);
    this.auth.user.set(null);
    this.auth.loadMe().subscribe((user) => this.router.navigate(user ? ['/'] : ['/login']));
  }
}
