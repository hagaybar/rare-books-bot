export interface MapNode {
  agent_norm: string;
  display_name: string;
  lat: number | null;
  lon: number | null;
  place_norm: string | null;
  birth_year: number | null;
  death_year: number | null;
  occupations: string[];
  connection_count: number;
  has_wikipedia: boolean;
}

export interface MapEdge {
  source: string;
  target: string;
  type: string;
  confidence: number;
  relationship: string | null;
  bidirectional: boolean;
}

export interface MapMeta {
  total_agents: number;
  showing: number;
  total_edges: number;
}

export interface MapResponse {
  nodes: MapNode[];
  edges: MapEdge[];
  meta: MapMeta;
}

export interface AgentConnection {
  agent_norm: string;
  display_name: string;
  type: string;
  relationship: string | null;
  confidence: number;
}

export interface AgentDetail {
  agent_norm: string;
  display_name: string;
  lat: number | null;
  lon: number | null;
  place_norm: string | null;
  birth_year: number | null;
  death_year: number | null;
  occupations: string[];
  wikipedia_summary: string | null;
  connections: AgentConnection[];
  record_count: number;
  primo_url: string | null;
  external_links: Record<string, string>;
}

export type ConnectionType =
  | 'teacher_student'
  | 'wikilink'
  | 'llm_extraction'
  | 'category'
  | 'co_publication';

export const CONNECTION_TYPE_CONFIG: Record<ConnectionType, {
  label: string;
  color: [number, number, number];
  width: number;
}> = {
  teacher_student: { label: 'Teacher/Student', color: [59, 130, 246], width: 3 },
  wikilink: { label: 'Wikipedia Link', color: [245, 158, 11], width: 2 },
  llm_extraction: { label: 'LLM Extracted', color: [139, 92, 246], width: 2 },
  category: { label: 'Category', color: [156, 163, 175], width: 1 },
  co_publication: { label: 'Co-Publication', color: [16, 185, 129], width: 2 },
};
