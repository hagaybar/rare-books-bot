import type { MapResponse, AgentDetail, AgentWork, EgoResponse, PathResponse, PlaceMarker } from '../types/network';
import { authenticatedFetch } from './auth';

export interface NetworkSearchResult {
  agent_norm: string;
  display_name: string;
  lat: number | null;
  lon: number | null;
  connection_count: number;
  matched_alias: string | null; // set when the hit came via a cross-script/variant alias (#30)
}

const BASE = '/network';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error ${response.status}: ${text}`);
  }
  return response.json() as Promise<T>;
}

export interface MapParams {
  connectionTypes: string[];
  minConfidence?: number;
  century?: number | null;
  place?: string | null;
  role?: string | null;
  limit?: number;
}

export async function fetchMapData(params: MapParams): Promise<MapResponse> {
  const qs = new URLSearchParams();
  if (params.connectionTypes.length === 0) {
    qs.set('connection_types', 'none');
  } else {
    qs.set('connection_types', params.connectionTypes.join(','));
  }
  if (params.minConfidence !== undefined) qs.set('min_confidence', String(params.minConfidence));
  if (params.century) qs.set('century', String(params.century));
  if (params.place) qs.set('place', params.place);
  if (params.role) qs.set('role', params.role);
  if (params.limit) qs.set('limit', String(params.limit));

  const res = await authenticatedFetch(`${BASE}/map?${qs}`);
  return handleResponse<MapResponse>(res);
}

export async function fetchAgentDetail(agentNorm: string): Promise<AgentDetail> {
  const res = await authenticatedFetch(`${BASE}/agent/${encodeURIComponent(agentNorm)}`);
  return handleResponse<AgentDetail>(res);
}

export interface EgoParams {
  connectionTypes: string[];
  minConfidence?: number;
  limit?: number;
}

export async function fetchEgo(agentNorm: string, params: EgoParams): Promise<EgoResponse> {
  const qs = new URLSearchParams();
  // ego always needs at least one type; fall back to the collection-first set
  const types = params.connectionTypes.length
    ? params.connectionTypes
    : ['same_record', 'printed_by', 'teacher_student'];
  qs.set('connection_types', types.join(','));
  if (params.minConfidence !== undefined) qs.set('min_confidence', String(params.minConfidence));
  if (params.limit) qs.set('limit', String(params.limit));
  const res = await authenticatedFetch(`${BASE}/ego/${encodeURIComponent(agentNorm)}?${qs}`);
  return handleResponse<EgoResponse>(res);
}

export async function fetchPath(
  source: string,
  target: string,
  params: { connectionTypes: string[]; minConfidence?: number },
): Promise<PathResponse> {
  const qs = new URLSearchParams();
  qs.set('source', source);
  qs.set('target', target);
  const types = params.connectionTypes.length
    ? params.connectionTypes
    : ['same_record', 'printed_by', 'teacher_student'];
  qs.set('connection_types', types.join(','));
  if (params.minConfidence !== undefined) qs.set('min_confidence', String(params.minConfidence));
  const res = await authenticatedFetch(`${BASE}/path?${qs}`);
  return handleResponse<PathResponse>(res);
}

export async function fetchPlaces(): Promise<PlaceMarker[]> {
  const res = await authenticatedFetch(`${BASE}/places`);
  return handleResponse<PlaceMarker[]>(res);
}

export async function searchNetworkAgents(query: string): Promise<NetworkSearchResult[]> {
  const res = await authenticatedFetch(
    `${BASE}/search?q=${encodeURIComponent(query)}&limit=10`,
  );
  if (!res.ok) return [];
  const data = await res.json() as { results: NetworkSearchResult[] };
  return data.results;
}


export interface PlaceDetail {
  place_norm: string;
  place_display: string | null;
  total: number;
  agent_count: number;
  year_min: number | null;
  year_max: number | null;
  decades: { decade: number; count: number }[];
  top_publishers: { name: string; count: number; agent_norm: string | null }[];
  top_agents: { agent_norm: string; display_name: string; count: number }[];
  top_subjects: { subject: string; count: number }[];
  works: AgentWork[];
}

export async function fetchPlaceDetail(placeNorm: string): Promise<PlaceDetail> {
  const res = await authenticatedFetch(`${BASE}/place/${encodeURIComponent(placeNorm)}`);
  return handleResponse<PlaceDetail>(res);
}
