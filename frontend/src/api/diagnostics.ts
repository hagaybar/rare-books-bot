/**
 * API client functions for diagnostic endpoints (/diagnostics/*).
 *
 * Mirrors the FastAPI router in app/api/diagnostics.py.
 */

import type {
  QueryRunResponse,
  QueryRunsResponse,
  LabelsResponse,
  RunLabelsResponse,
  GoldSetResponse,
  RegressionResponse,
  TablesResponse,
  TableRowsResponse,
  LabelItem,
} from '../types/diagnostics.ts';
import { authenticatedFetch } from './auth';

const BASE = '/diagnostics';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error ${String(response.status)}: ${text}`);
  }
  return response.json() as Promise<T>;
}

/** B5: Execute a query, store run, return plan + SQL + candidates. */
export async function runQuery(
  queryText: string,
  limit: number = 50,
): Promise<QueryRunResponse> {
  const res = await authenticatedFetch(`${BASE}/query-run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query_text: queryText, limit }),
  });
  return handleResponse<QueryRunResponse>(res);
}

/** B6: List recent query runs (paginated). */
export async function getQueryRuns(
  limit: number = 20,
  offset: number = 0,
): Promise<QueryRunsResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  const res = await authenticatedFetch(`${BASE}/query-runs?${params.toString()}`);
  return handleResponse<QueryRunsResponse>(res);
}

/** B7: Save TP/FP/FN/UNK labels for candidates in a run. */
export async function submitLabels(
  runId: number,
  labels: LabelItem[],
): Promise<LabelsResponse> {
  const res = await authenticatedFetch(`${BASE}/labels`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId, labels }),
  });
  return handleResponse<LabelsResponse>(res);
}

/** B8: Retrieve labels for a specific run. */
export async function getLabels(runId: number): Promise<RunLabelsResponse> {
  const res = await authenticatedFetch(`${BASE}/labels/${String(runId)}`);
  return handleResponse<RunLabelsResponse>(res);
}

/** B9: Export the gold set as JSON. */
export async function exportGoldSet(): Promise<GoldSetResponse> {
  const res = await authenticatedFetch(`${BASE}/gold-set/export`);
  return handleResponse<GoldSetResponse>(res);
}

/** B10: Run regression tests against the gold set. */
export async function runRegression(): Promise<RegressionResponse> {
  const res = await authenticatedFetch(`${BASE}/gold-set/regression`, {
    method: 'POST',
  });
  return handleResponse<RegressionResponse>(res);
}

/** B11: List all database tables with row counts and columns. */
export async function getTables(): Promise<TablesResponse> {
  const res = await authenticatedFetch(`${BASE}/tables`);
  return handleResponse<TablesResponse>(res);
}

/** B12: Get paginated rows from a specific table. */
export async function getTableRows(
  tableName: string,
  limit: number = 50,
  offset: number = 0,
  search: string = '',
): Promise<TableRowsResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (search) params.set('search', search);
  const res = await authenticatedFetch(
    `${BASE}/tables/${encodeURIComponent(tableName)}/rows?${params.toString()}`,
  );
  return handleResponse<TableRowsResponse>(res);
}
