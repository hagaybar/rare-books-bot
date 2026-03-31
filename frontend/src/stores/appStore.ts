import { create } from 'zustand';

const SESSION_STORAGE_KEY = 'rare-books-session-id';

interface AppState {
  sessionId: string | null;
  sidebarCollapsed: boolean;
  setSessionId: (id: string | null) => void;
  clearSession: () => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

function loadSessionId(): string | null {
  try {
    return localStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function saveSessionId(id: string | null): void {
  try {
    if (id) {
      localStorage.setItem(SESSION_STORAGE_KEY, id);
    } else {
      localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  } catch {
    // localStorage may be unavailable (e.g. private browsing)
  }
}

export const useAppStore = create<AppState>((set) => ({
  sessionId: loadSessionId(),
  sidebarCollapsed: false,
  setSessionId: (id) => {
    saveSessionId(id);
    set({ sessionId: id });
  },
  clearSession: () => {
    saveSessionId(null);
    set({ sessionId: null });
  },
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
}));
