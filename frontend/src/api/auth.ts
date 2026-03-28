/**
 * Auth API client -- login, guest, refresh, me, logout.
 * All calls use credentials: 'include' so HTTP-only cookies are sent.
 */

export interface AuthUser {
  user_id: number;
  username: string;
  role: 'admin' | 'full' | 'limited' | 'guest';
  is_active?: boolean;
  token_limit?: number | null;
  tokens_used_this_month?: number | null;
}

export async function loginApi(
  username: string,
  password: string,
): Promise<{ username: string; role: string }> {
  const res = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Login failed' }));
    throw new Error(err.detail || 'Login failed');
  }
  return res.json();
}

export async function guestApi(): Promise<{ role: string }> {
  const res = await fetch('/auth/guest', {
    method: 'POST',
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to create guest session');
  return res.json();
}

export async function fetchMe(): Promise<AuthUser> {
  const res = await fetch('/auth/me', { credentials: 'include' });
  if (!res.ok) throw new Error('Not authenticated');
  return res.json();
}

export async function refreshToken(): Promise<void> {
  const res = await fetch('/auth/refresh', {
    method: 'POST',
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Refresh failed');
}

export async function logoutApi(): Promise<void> {
  await fetch('/auth/logout', {
    method: 'POST',
    credentials: 'include',
  });
}
