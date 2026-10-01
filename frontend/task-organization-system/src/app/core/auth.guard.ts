import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';

import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.loadMe().pipe(map((user) => (user ? true : router.createUrlTree(['/login']))));
};

export const adminGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.loadMe().pipe(map((user) => (user?.is_admin ? true : router.createUrlTree(['/']))));
};

export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.loadMe().pipe(map((user) => (user ? router.createUrlTree(['/']) : true)));
};
