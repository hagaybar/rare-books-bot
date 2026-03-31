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
  input_tokens_this_month?: number;
  output_tokens_this_month?: number;
  cost_usd_this_month?: number;
  model?: string;
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

/**
 * Fetch wrapper that auto-refreshes JWT on 401 and retries once.
 */
export async function authenticatedFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const opts = { ...options, credentials: 'include' as RequestCredentials };
  let res = await fetch(url, opts);

  if (res.status === 401) {
    // Try refreshing the token
    try {
      await refreshToken();
      // Retry the original request
      res = await fetch(url, opts);
    } catch {
      // Refresh failed — redirect to login
      window.location.href = '/login';
      throw new Error('Session expired');
    }
  }

  return res;
}

// ---------------------------------------------------------------------------
// User management (admin only)
// ---------------------------------------------------------------------------

export interface UserListItem {
  id: number;
  username: string;
  role: string;
  is_active: boolean;
  last_login: string | null;
  tokens_used_this_month: number;
  input_tokens_this_month: number;
  output_tokens_this_month: number;
  cost_usd_this_month: number;
  token_limit: number;
}

export async function fetchUsers(): Promise<UserListItem[]> {
  const res = await authenticatedFetch('/auth/users');
  if (!res.ok) throw new Error('Failed to fetch users');
  return res.json();
}

export async function createUserApi(data: {
  username: string;
  password: string;
  role: string;
  token_limit?: number;
}): Promise<unknown> {
  const res = await authenticatedFetch('/auth/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed' }));
    throw new Error(err.detail || 'Failed to create user');
  }
  return res.json();
}

export async function updateUserApi(
  userId: number,
  data: {
    role?: string;
    is_active?: boolean;
    token_limit?: number;
    new_password?: string;
  },
): Promise<unknown> {
  const res = await authenticatedFetch(`/auth/users/${userId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed' }));
    throw new Error(err.detail || 'Failed to update user');
  }
  return res.json();
}
