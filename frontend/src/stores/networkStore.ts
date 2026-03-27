import { create } from 'zustand';
import type { ConnectionType, ColorByMode } from '../types/network';

interface NetworkState {
  connectionTypes: ConnectionType[];
  minConfidence: number;
  century: number | null;
  place: string | null;
  role: string | null;
  agentLimit: number;

  setConnectionTypes: (types: ConnectionType[]) => void;
  toggleConnectionType: (type: ConnectionType) => void;
  setMinConfidence: (val: number) => void;
  setCentury: (val: number | null) => void;
  setPlace: (val: string | null) => void;
  setRole: (val: string | null) => void;
  setAgentLimit: (val: number) => void;
  colorBy: ColorByMode;
  setColorBy: (mode: ColorByMode) => void;
  resetFilters: () => void;
}

const DEFAULT_STATE = {
  connectionTypes: [] as ConnectionType[],
  minConfidence: 0.5,
  century: null as number | null,
  place: null as string | null,
  role: null as string | null,
  agentLimit: 150,
  colorBy: 'century' as ColorByMode,
};

export const useNetworkStore = create<NetworkState>((set) => ({
  ...DEFAULT_STATE,

  setConnectionTypes: (types) => set({ connectionTypes: types }),
  toggleConnectionType: (type) =>
    set((state) => {
      const exists = state.connectionTypes.includes(type);
      return {
        connectionTypes: exists
          ? state.connectionTypes.filter((t) => t !== type)
          : [...state.connectionTypes, type],
      };
    }),
  setMinConfidence: (val) => set({ minConfidence: val }),
  setCentury: (val) => set({ century: val }),
  setPlace: (val) => set({ place: val }),
  setRole: (val) => set({ role: val }),
  setAgentLimit: (val) => set({ agentLimit: val }),
  setColorBy: (mode) => set({ colorBy: mode }),
  resetFilters: () => set(DEFAULT_STATE),
}));
