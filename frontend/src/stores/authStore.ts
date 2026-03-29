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

export const useAuthStore = create<AuthState>((set) => ({
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
    } catch {
      /* ignore */
    }
    set({ user: null });
  },
}));
