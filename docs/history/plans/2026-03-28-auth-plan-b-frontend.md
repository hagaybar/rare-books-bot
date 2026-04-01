# Auth Plan B: Frontend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the frontend to the backend auth system — login page, auth state management, route protection, sidebar role filtering, and chat gating.

**Architecture:** New Login page at `/login`. Zustand auth store tracks user session (fetched via `GET /auth/me`). AuthGuard component wraps all routes, redirecting to login if no session. Sidebar filters nav items by role. Chat page shows guest/quota messages.

**Tech Stack:** React 19, TypeScript, Zustand, React Router, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-28-auth-security-design.md`
**Branch:** `feature/auth-security`

**This is Plan B of 3** (A=backend done, B=this, C=hardening+admin)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `frontend/src/api/auth.ts` | Create | Auth API client (login, guest, refresh, me, logout) |
| `frontend/src/stores/authStore.ts` | Create | Zustand store for user session |
| `frontend/src/pages/Login.tsx` | Create | Login page with guest option |
| `frontend/src/components/AuthGuard.tsx` | Create | Route protection — redirects to /login if unauthenticated |
| `frontend/src/App.tsx` | Modify | Add /login route, wrap routes in AuthGuard |
| `frontend/src/components/Sidebar.tsx` | Modify | Filter nav items by role, show user info + logout |
| `frontend/src/pages/Chat.tsx` | Modify | Guest message, quota display for limited users |
| `frontend/vite.config.ts` | Modify | Add /auth proxy |

---

### Task 1: Vite Proxy + Auth API Client + Auth Store

**Files:**
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/stores/authStore.ts`

- [ ] **Step 1: Add /auth proxy to Vite config**

In `frontend/vite.config.ts`, add alongside existing proxy entries:
```typescript
'/auth': {
  target: 'http://localhost:8000',
  changeOrigin: true,
},
```

- [ ] **Step 2: Create auth API client**

Create `frontend/src/api/auth.ts`:

```typescript
export interface AuthUser {
  user_id: number;
  username: string;
  role: 'admin' | 'full' | 'limited' | 'guest';
  is_active?: boolean;
  token_limit?: number | null;
  tokens_used_this_month?: number | null;
}

export async function loginApi(username: string, password: string): Promise<{ username: string; role: string }> {
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
```

- [ ] **Step 3: Create auth Zustand store**

Create `frontend/src/stores/authStore.ts`:

```typescript
import { create } from 'zustand';
import type { AuthUser } from '../api/auth';
import { fetchMe, logoutApi, refreshToken } from '../api/auth';

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  error: string | null;

  initialize: () => Promise<void>;
  setUser: (user: AuthUser | null) => void;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  loading: true,
  error: null,

  initialize: async () => {
    set({ loading: true, error: null });
    try {
      const user = await fetchMe();
      set({ user, loading: false });
    } catch {
      // Try refresh
      try {
        await refreshToken();
        const user = await fetchMe();
        set({ user, loading: false });
      } catch {
        set({ user: null, loading: false });
      }
    }
  },

  setUser: (user) => set({ user }),

  logout: async () => {
    try {
      await logoutApi();
    } catch { /* ignore */ }
    set({ user: null });
  },
}));
```

- [ ] **Step 4: Verify compilation**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/vite.config.ts frontend/src/api/auth.ts frontend/src/stores/authStore.ts
git commit -m "feat: add auth API client, Zustand store, and Vite proxy"
```

---

### Task 2: Login Page

**Files:**
- Create: `frontend/src/pages/Login.tsx`

- [ ] **Step 1: Create Login page**

Create `frontend/src/pages/Login.tsx`:

```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { loginApi, guestApi, fetchMe } from '../api/auth';
import { useAuthStore } from '../stores/authStore';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const setUser = useAuthStore((s) => s.setUser);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await loginApi(username, password);
      const user = await fetchMe();
      setUser(user);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGuest = async () => {
    setLoading(true);
    try {
      await guestApi();
      const user = await fetchMe();
      setUser(user);
      navigate('/network');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Guest login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-xl shadow-lg p-8 w-full max-w-sm">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Rare Books Bot</h1>
          <p className="text-sm text-gray-500 mt-1">Bibliographic discovery system</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="Enter username"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="Enter password"
            />
          </div>

          {error && (
            <div className="text-sm text-red-600 bg-red-50 p-2 rounded">{error}</div>
          )}

          <button
            type="submit"
            disabled={loading || !username || !password}
            className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>

        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-gray-200" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="bg-white px-2 text-gray-400">or</span>
          </div>
        </div>

        <button
          onClick={handleGuest}
          disabled={loading}
          className="w-full py-2 text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          Continue as Guest &rarr;
        </button>

        <p className="text-xs text-gray-400 text-center mt-4">
          Guests can browse the Network Map and Entity Enrichment
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Login.tsx
git commit -m "feat: add Login page with username/password and guest option"
```

---

### Task 3: AuthGuard + App Routing + Sidebar

**Files:**
- Create: `frontend/src/components/AuthGuard.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/pages/Chat.tsx`

- [ ] **Step 1: Create AuthGuard component**

Create `frontend/src/components/AuthGuard.tsx`:

```tsx
import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';

// Role hierarchy for page access
const PAGE_ROLES: Record<string, string> = {
  '/chat': 'limited',
  '/network': 'guest',
  '/operator/coverage': 'full',
  '/operator/workbench': 'full',
  '/operator/agent': 'full',
  '/operator/review': 'full',
  '/diagnostics/query': 'full',
  '/diagnostics/db': 'full',
  '/admin/publishers': 'full',
  '/admin/enrichment': 'guest',
  '/admin/health': 'full',
  '/admin/users': 'admin',
};

const ROLE_LEVEL: Record<string, number> = {
  admin: 4, full: 3, limited: 2, guest: 1,
};

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading, initialize } = useAuthStore();
  const location = useLocation();

  useEffect(() => {
    initialize();
  }, [initialize]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Check page-level access
  const path = location.pathname;
  const requiredRole = Object.entries(PAGE_ROLES).find(([prefix]) => path.startsWith(prefix));
  if (requiredRole) {
    const userLevel = ROLE_LEVEL[user.role] ?? 0;
    const requiredLevel = ROLE_LEVEL[requiredRole[1]] ?? 0;
    if (userLevel < requiredLevel) {
      // Redirect to the highest page they can access
      return <Navigate to={user.role === 'guest' ? '/network' : '/'} replace />;
    }
  }

  return <>{children}</>;
}
```

- [ ] **Step 2: Update App.tsx routing**

In `frontend/src/App.tsx`:
- Import Login and AuthGuard
- Add `/login` route OUTSIDE the Layout (no sidebar)
- Wrap the `<Route element={<Layout />}>` block in AuthGuard

```tsx
import Login from './pages/Login';
import AuthGuard from './components/AuthGuard';

// In the Routes:
<Route path="/login" element={<Login />} />
<Route element={<AuthGuard><Layout /></AuthGuard>}>
  {/* existing routes stay here */}
</Route>
```

Also update the default redirect: if user is guest, redirect `/` to `/network` instead of Chat.

- [ ] **Step 3: Update Sidebar — filter by role + show user info**

In `frontend/src/components/Sidebar.tsx`:
- Import `useAuthStore`
- Add `requiredRole` to each nav item config
- Filter items: only show items where user's role level >= required level
- Add at the bottom of sidebar: username badge + role + logout button

Add to NAV_SECTIONS items:
```typescript
{ to: '/chat', label: 'Chat', icon: ICONS.chat, minRole: 'limited' },
{ to: '/network', label: 'Network', icon: ICONS.network, minRole: 'guest' },
// operator items: minRole: 'full'
// admin items: minRole: 'full', except enrichment: 'guest'
// users: minRole: 'admin'
```

Filter: `items.filter(item => ROLE_LEVEL[user.role] >= ROLE_LEVEL[item.minRole])`

Add user info at bottom:
```tsx
<div className="p-3 border-t">
  <div className="text-xs text-gray-500">{user.username}</div>
  <div className="text-xs text-gray-400 capitalize">{user.role}</div>
  <button onClick={logout} className="text-xs text-red-500 mt-1 hover:text-red-700">
    Logout
  </button>
</div>
```

- [ ] **Step 4: Update Chat.tsx — guest and quota messages**

In `frontend/src/pages/Chat.tsx`:
- Import `useAuthStore`
- If user.role === 'guest': replace the chat input with a message "Login to use the chat" + a link to /login
- If user.role === 'limited' and user has quota info: show remaining tokens badge near the input

- [ ] **Step 5: Add credentials: 'include' to ALL existing fetch calls**

In `frontend/src/api/chat.ts`, `frontend/src/api/metadata.ts`, `frontend/src/api/network.ts`:
- Add `credentials: 'include'` to every `fetch()` call so cookies are sent with API requests
- This is critical — without it, the backend will reject all requests with 401

- [ ] **Step 6: Verify and build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

- [ ] **Step 7: Commit and push**

```bash
git add frontend/src/ frontend/vite.config.ts
git commit -m "feat: login page, AuthGuard, sidebar role filtering, chat gating, credentials on all fetches"
git push origin feature/auth-security
```
