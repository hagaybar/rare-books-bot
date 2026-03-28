import type { MapResponse, AgentDetail } from '../types/network';

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

  const res = await fetch(`${BASE}/map?${qs}`, { credentials: 'include' });
  return handleResponse<MapResponse>(res);
}

export async function fetchAgentDetail(agentNorm: string): Promise<AgentDetail> {
  const res = await fetch(`${BASE}/agent/${encodeURIComponent(agentNorm)}`, { credentials: 'include' });
  return handleResponse<AgentDetail>(res);
}
