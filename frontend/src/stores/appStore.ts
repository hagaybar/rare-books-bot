import { create } from 'zustand';

interface AppState {
  sessionId: string | null;
  sidebarCollapsed: boolean;
  setSessionId: (id: string | null) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  sessionId: null,
  sidebarCollapsed: false,
  setSessionId: (id) => set({ sessionId: id }),
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
}));
