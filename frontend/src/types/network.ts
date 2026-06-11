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
  filtered_count: number;
  record_count: number;
  has_wikipedia: boolean;
  primary_role: string | null;
  node_type: string; // 'person' | 'publisher'
  community: string | null; // intellectual-community color facet (issue #28)
}

export type ColorByMode = 'century' | 'role' | 'occupation' | 'community';

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

export const PUBLISHER_COLOR: [number, number, number] = [202, 138, 4]; // amber — printing houses

export const COMMUNITY_OTHER_COLOR: [number, number, number] = [203, 213, 225]; // slate-300

// Distinct categorical palette for the community-coloring facet (issue #28).
// Indexed by the position of a community in meta.communities (global order),
// so colors stay stable as filters change.
export const COMMUNITY_PALETTE: [number, number, number][] = [
  [37, 99, 235], [220, 38, 38], [22, 163, 74], [217, 119, 6],
  [147, 51, 234], [13, 148, 136], [219, 39, 119], [101, 163, 13],
  [2, 132, 199], [234, 88, 12], [86, 60, 178], [190, 18, 60],
  [4, 120, 87], [161, 98, 7], [124, 58, 237], [15, 118, 110],
  [159, 18, 57], [3, 105, 161], [180, 83, 9], [109, 40, 217],
];

/** Stable community -> color map from the global community order in meta. */
export function buildCommunityColorMap(
  communities: string[]
): Record<string, [number, number, number]> {
  const map: Record<string, [number, number, number]> = {};
  communities.forEach((name, i) => {
    map[name] = COMMUNITY_PALETTE[i % COMMUNITY_PALETTE.length];
  });
  return map;
}

export function getAgentColor(
  node: MapNode,
  colorBy: ColorByMode,
  communityColors?: Record<string, [number, number, number]>
): [number, number, number] {
  if (node.node_type === 'publisher') return PUBLISHER_COLOR;
  switch (colorBy) {
    case 'century':
      return CENTURY_COLORS[getCenturyLabel(node.birth_year)] ?? CENTURY_COLORS['Unknown'];
    case 'role':
      return ROLE_COLORS[node.primary_role ?? 'other'] ?? ROLE_COLORS['other'];
    case 'occupation': {
      const occ = node.occupations[0] ?? 'other';
      return OCCUPATION_COLORS[occ] ?? OCCUPATION_COLORS['other'];
    }
    case 'community': {
      const c = node.community ? communityColors?.[node.community] : undefined;
      return c ?? COMMUNITY_OTHER_COLOR;
    }
  }
}

export interface MapEdge {
  source: string;
  target: string;
  type: string;
  confidence: number;
  relationship: string | null;
  evidence: string | null;
  bidirectional: boolean;
}

export interface MapMeta {
  total_agents: number;
  showing: number;
  total_edges: number;
  communities: string[]; // legend palette order (issue #28)
}

export interface MapResponse {
  nodes: MapNode[];
  edges: MapEdge[];
  meta: MapMeta;
}

export interface EgoMeta {
  truncated: boolean; // neighbours exceeded the cap (issue #31)
  total_neighbors: number;
  showing: number;
}

export interface EgoResponse {
  focal: string;
  nodes: MapNode[];
  edges: MapEdge[];
  meta: EgoMeta;
}

export interface AgentConnection {
  agent_norm: string;
  display_name: string;
  type: string;
  relationship: string | null;
  evidence: string | null;
  confidence: number;
}

export interface AgentWork {
  mms_id: string;
  title: string | null;
  date_label: string | null;
  place_display: string | null;
  publisher_display: string | null;
  role_norm: string | null;
  primo_url: string | null;
}

export interface AgentDetail {
  agent_norm: string;
  display_name: string;
  name_alt: string | null; // name in the opposite script (issue #30)
  lat: number | null;
  lon: number | null;
  place_norm: string | null;
  birth_year: number | null;
  death_year: number | null;
  occupations: string[];
  wikipedia_summary: string | null;
  connections: AgentConnection[];
  record_count: number;
  works: AgentWork[];
  primo_url: string | null;
  external_links: Record<string, string>;
  node_type: string;
}

// 'category' removed (issue #28): retired from arcs into a node-coloring facet.
export type ConnectionType =
  | 'teacher_student'
  | 'wikilink'
  | 'llm_extraction'
  | 'co_publication'
  | 'same_place_period'
  | 'same_record'
  | 'printed_by';

export const CONNECTION_TYPE_CONFIG: Record<ConnectionType, {
  label: string;
  color: [number, number, number];
  width: number;
  tier: 'primary' | 'secondary';
}> = {
  same_record: { label: 'Same Book', color: [217, 70, 239], width: 2, tier: 'primary' },
  printed_by: { label: 'Printed By', color: [202, 138, 4], width: 2, tier: 'primary' },
  teacher_student: { label: 'Teacher & Student', color: [59, 130, 246], width: 3, tier: 'primary' },
  co_publication: { label: 'Published Together', color: [16, 185, 129], width: 2, tier: 'primary' },
  same_place_period: { label: 'Active in Same City', color: [6, 182, 212], width: 2, tier: 'primary' },
  wikilink: { label: 'Mentioned Together', color: [245, 158, 11], width: 2, tier: 'primary' },
  llm_extraction: { label: 'AI-Discovered', color: [139, 92, 246], width: 2, tier: 'secondary' },
};
