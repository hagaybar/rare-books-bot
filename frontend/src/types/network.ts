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
  primary_role: string | null;
}

export type ColorByMode = 'century' | 'role' | 'occupation';

export const CENTURY_COLORS: Record<string, [number, number, number]> = {
  'Before 1400': [245, 158, 11],
  '15th': [249, 115, 22],
  '16th': [244, 63, 94],
  '17th': [139, 92, 246],
  '18th': [59, 130, 246],
  '19th': [20, 184, 166],
  '20th+': [34, 197, 94],
  'Unknown': [156, 163, 175],
};

export const ROLE_COLORS: Record<string, [number, number, number]> = {
  'author': [59, 130, 246],
  'printer': [34, 197, 94],
  'editor': [249, 115, 22],
  'translator': [139, 92, 246],
  'other': [156, 163, 175],
};

export const OCCUPATION_COLORS: Record<string, [number, number, number]> = {
  'rabbi': [245, 158, 11],
  'philosopher': [249, 115, 22],
  'historian': [244, 63, 94],
  'poet': [139, 92, 246],
  'printer': [59, 130, 246],
  'theologian': [20, 184, 166],
  'other': [156, 163, 175],
};

export function getCenturyLabel(birthYear: number | null): string {
  if (birthYear == null) return 'Unknown';
  if (birthYear < 1400) return 'Before 1400';
  if (birthYear < 1500) return '15th';
  if (birthYear < 1600) return '16th';
  if (birthYear < 1700) return '17th';
  if (birthYear < 1800) return '18th';
  if (birthYear < 1900) return '19th';
  return '20th+';
}

export function getAgentColor(node: MapNode, colorBy: ColorByMode): [number, number, number] {
  switch (colorBy) {
    case 'century':
      return CENTURY_COLORS[getCenturyLabel(node.birth_year)] ?? CENTURY_COLORS['Unknown'];
    case 'role':
      return ROLE_COLORS[node.primary_role ?? 'other'] ?? ROLE_COLORS['other'];
    case 'occupation': {
      const occ = node.occupations[0] ?? 'other';
      return OCCUPATION_COLORS[occ] ?? OCCUPATION_COLORS['other'];
    }
  }
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
