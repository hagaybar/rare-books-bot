import type { MapResponse, AgentDetail } from '../types/network';
import { authenticatedFetch } from './auth';

export interface NetworkSearchResult {
  agent_norm: string;
  display_name: string;
  lat: number | null;
  lon: number | null;
  connection_count: number;
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

export async function searchNetworkAgents(query: string): Promise<NetworkSearchResult[]> {
  const res = await authenticatedFetch(
    `${BASE}/search?q=${encodeURIComponent(query)}&limit=10`,
  );
  if (!res.ok) return [];
  const data = await res.json() as { results: NetworkSearchResult[] };
  return data.results;
}
