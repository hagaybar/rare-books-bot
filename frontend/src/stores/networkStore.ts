import { create } from 'zustand';
import type { ConnectionType, ColorByMode } from '../types/network';

export type ViewMode = 'map' | 'ego';
export interface TrailItem { agent_norm: string; display_name: string }

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

  // Ego-network mode (issue #31)
  viewMode: ViewMode;
  focusAgent: string | null;
  egoTrail: TrailItem[];
  setViewMode: (mode: ViewMode) => void;
  enterEgo: (node: TrailItem) => void;   // start a fresh ego walk at node
  pushEgo: (node: TrailItem) => void;    // re-center onto a neighbour
  popTrailTo: (agentNorm: string) => void;
}

const DEFAULT_STATE = {
  // Curated meaningful default (issue #21): not empty (no arcs), not the
  // wikilink hairball. Documented collection/teaching relationships.
  connectionTypes: ['same_record', 'printed_by', 'teacher_student'] as ConnectionType[],
  minConfidence: 0.5,
  century: null as number | null,
  place: null as string | null,
  role: null as string | null,
  agentLimit: 500, // issue #35: 150 was an arbitrary cap; the full graph is ~2,714
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

  // Ego-network mode (issue #31) — kept out of DEFAULT_STATE so resetFilters
  // (a filter reset) doesn't yank the user out of the view they're in.
  viewMode: 'map',
  focusAgent: null,
  egoTrail: [],
  setViewMode: (mode) => set({ viewMode: mode }),
  enterEgo: (node) =>
    set({ viewMode: 'ego', focusAgent: node.agent_norm, egoTrail: [node] }),
  pushEgo: (node) =>
    set((s) => {
      const last = s.egoTrail[s.egoTrail.length - 1];
      if (last && last.agent_norm === node.agent_norm) return { focusAgent: node.agent_norm };
      const existing = s.egoTrail.findIndex((t) => t.agent_norm === node.agent_norm);
      const egoTrail = existing >= 0 ? s.egoTrail.slice(0, existing + 1) : [...s.egoTrail, node];
      return { focusAgent: node.agent_norm, egoTrail };
    }),
  popTrailTo: (agentNorm) =>
    set((s) => {
      const idx = s.egoTrail.findIndex((t) => t.agent_norm === agentNorm);
      return idx >= 0
        ? { focusAgent: agentNorm, egoTrail: s.egoTrail.slice(0, idx + 1) }
        : { focusAgent: agentNorm };
    }),
}));
