import type {
  CoverageReport,
  IssueRecord,
  Cluster,
  AgentChatResponse,
  CorrectionHistoryResponse,
} from '../types/metadata';

const BASE = '/metadata';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error ${response.status}: ${text}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchCoverage(): Promise<CoverageReport> {
  const res = await fetch(`${BASE}/coverage`);
  return handleResponse<CoverageReport>(res);
}

export async function fetchIssues(
  field: string,
  maxConfidence?: number,
  limit?: number,
  offset?: number
): Promise<{ items: IssueRecord[]; total: number }> {
  const params = new URLSearchParams({ field });
  if (maxConfidence !== undefined) params.set('max_confidence', String(maxConfidence));
  if (limit !== undefined) params.set('limit', String(limit));
  if (offset !== undefined) params.set('offset', String(offset));
  const res = await fetch(`${BASE}/issues?${params}`);
  return handleResponse<{ items: IssueRecord[]; total: number }>(res);
}

export async function fetchClusters(field?: string): Promise<Cluster[]> {
  const params = field ? `?field=${encodeURIComponent(field)}` : '';
  const res = await fetch(`${BASE}/clusters${params}`);
  return handleResponse<Cluster[]>(res);
}

export async function submitCorrection(
  field: string,
  rawValue: string,
  canonicalValue: string,
  evidence?: string
): Promise<{ success: boolean; records_affected: number }> {
  const res = await fetch(`${BASE}/corrections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      field,
      raw_value: rawValue,
      canonical_value: canonicalValue,
      evidence: evidence ?? null,
    }),
  });
  return handleResponse<{ success: boolean; records_affected: number }>(res);
}

export async function agentChat(
  field: string,
  message?: string
): Promise<AgentChatResponse> {
  const res = await fetch(`${BASE}/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field, message: message ?? '' }),
  });
  return handleResponse<AgentChatResponse>(res);
}

export async function fetchCorrectionHistory(
  field?: string,
  source?: string,
  limit?: number,
  offset?: number
): Promise<CorrectionHistoryResponse> {
  const params = new URLSearchParams();
  if (field) params.set('field', field);
  if (source) params.set('source', source);
  if (limit !== undefined) params.set('limit', String(limit));
  if (offset !== undefined) params.set('offset', String(offset));
  const qs = params.toString();
  const res = await fetch(`${BASE}/corrections/history${qs ? `?${qs}` : ''}`);
  return handleResponse<CorrectionHistoryResponse>(res);
}
