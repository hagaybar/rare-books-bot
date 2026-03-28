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

/**
 * Map raw API confidence bands to the ConfidenceBand shape expected by the UI.
 * The backend returns { band_label, lower, upper, count } but our TypeScript
 * types expect { label, min_confidence, max_confidence, count }.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapConfidenceBands(raw: any[]): CoverageReport['date_coverage']['confidence_distribution'] {
  if (!Array.isArray(raw)) return [];
  return raw.map((b) => ({
    label: b.label ?? b.band_label ?? String(b.lower ?? ''),
    min_confidence: b.min_confidence ?? b.lower ?? 0,
    max_confidence: b.max_confidence ?? b.upper ?? 1,
    count: b.count ?? 0,
  }));
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapFieldCoverage(raw: any): CoverageReport['date_coverage'] {
  return {
    ...raw,
    confidence_distribution: mapConfidenceBands(raw.confidence_distribution),
  };
}

export async function fetchCoverage(): Promise<CoverageReport> {
  const res = await fetch(`${BASE}/coverage`, { credentials: 'include' });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data: any = await handleResponse<any>(res);
  return {
    ...data,
    date_coverage: mapFieldCoverage(data.date_coverage),
    place_coverage: mapFieldCoverage(data.place_coverage),
    publisher_coverage: mapFieldCoverage(data.publisher_coverage),
    agent_name_coverage: mapFieldCoverage(data.agent_name_coverage),
    agent_role_coverage: data.agent_role_coverage
      ? mapFieldCoverage(data.agent_role_coverage)
      : data.agent_role_coverage,
  };
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
  const res = await fetch(`${BASE}/issues?${params}`, { credentials: 'include' });
  return handleResponse<{ items: IssueRecord[]; total: number }>(res);
}

export async function fetchClusters(field?: string): Promise<Cluster[]> {
  const params = field ? `?field=${encodeURIComponent(field)}` : '';
  const res = await fetch(`${BASE}/clusters${params}`, { credentials: 'include' });
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
    credentials: 'include',
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
    credentials: 'include',
    body: JSON.stringify({ field, message: message ?? '' }),
  });
  return handleResponse<AgentChatResponse>(res);
}

export interface AgentRecord {
  mms_id: string;
  title: string | null;
  date_raw: string | null;
  date_start: number | null;
  place_norm: string | null;
  publisher_norm: string | null;
  role: string | null;
  primo_url: string | null;
}

export interface AgentRecordsResponse {
  display_name: string;
  record_count: number;
  records: AgentRecord[];
}

export async function fetchAgentRecords(
  wikidataId?: string,
  agentNorm?: string
): Promise<AgentRecordsResponse> {
  const params = new URLSearchParams();
  if (wikidataId) params.set('wikidata_id', wikidataId);
  else if (agentNorm) params.set('agent_norm', agentNorm);
  const res = await fetch(`${BASE}/enrichment/agent-records?${params}`, { credentials: 'include' });
  return handleResponse<AgentRecordsResponse>(res);
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
  const res = await fetch(`${BASE}/corrections/history${qs ? `?${qs}` : ''}`, { credentials: 'include' });
  return handleResponse<CorrectionHistoryResponse>(res);
}
