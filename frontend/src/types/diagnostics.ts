/**
 * TypeScript interfaces matching the diagnostic API models.
 *
 * These mirror the Pydantic models in:
 * - app/api/diagnostics_models.py
 */

// ---------------------------------------------------------------------------
// B5: POST /diagnostics/query-run
// ---------------------------------------------------------------------------

export interface QueryRunRequest {
  query_text: string;
  limit: number;
}

export interface QueryRunCandidate {
  record_id: string;
  title: string | null;
  author: string | null;
  match_rationale: string;
  date_start: number | null;
  date_end: number | null;
  place_norm: string | null;
  publisher: string | null;
  evidence: Record<string, unknown>[];
}

export interface QueryRunResponse {
  run_id: number;
  query_text: string;
  plan: Record<string, unknown>;
  sql: string;
  candidates: QueryRunCandidate[];
  total_count: number;
  execution_time_ms: number;
}

// ---------------------------------------------------------------------------
// B6: GET /diagnostics/query-runs
// ---------------------------------------------------------------------------

export interface QueryRunSummary {
  run_id: number;
  query_text: string;
  created_at: string;
  candidate_count: number;
}

export interface QueryRunsResponse {
  total: number;
  items: QueryRunSummary[];
}

// ---------------------------------------------------------------------------
// B7: POST /diagnostics/labels
// ---------------------------------------------------------------------------

export type LabelValue = 'TP' | 'FP' | 'FN' | 'UNK';

export interface LabelItem {
  record_id: string;
  label: LabelValue;
  issue_tags: string[];
}

export interface LabelsRequest {
  run_id: number;
  labels: LabelItem[];
}

export interface LabelsResponse {
  saved_count: number;
}

// ---------------------------------------------------------------------------
// B8: GET /diagnostics/labels/{run_id}
// ---------------------------------------------------------------------------

export interface LabelDetail {
  record_id: string;
  label: string;
  issue_tags: string[];
  created_at: string;
}

export interface RunLabelsResponse {
  labels: LabelDetail[];
}

// ---------------------------------------------------------------------------
// B9: GET /diagnostics/gold-set/export
// ---------------------------------------------------------------------------

export interface GoldSetResponse {
  version: string;
  exported_at: string;
  queries: Record<string, unknown>[];
}

// ---------------------------------------------------------------------------
// B10: POST /diagnostics/gold-set/regression
// ---------------------------------------------------------------------------

export interface RegressionQueryResult {
  query_text: string;
  status: 'pass' | 'fail' | 'error';
  expected_includes: string[];
  actual_includes: string[];
  missing: string[];
  unexpected: string[];
  error: string | null;
}

export interface RegressionResponse {
  total_queries: number;
  passed: number;
  failed: number;
  results: RegressionQueryResult[];
}

// ---------------------------------------------------------------------------
// B11-B12: Database tables
// ---------------------------------------------------------------------------

export interface ColumnInfo {
  name: string;
  type: string;
}

export interface TableInfo {
  name: string;
  row_count: number;
  columns: ColumnInfo[];
}

export interface TablesResponse {
  tables: TableInfo[];
}

export interface TableRowsResponse {
  table_name: string;
  total: number;
  limit: number;
  offset: number;
  rows: Record<string, unknown>[];
}

// ---------------------------------------------------------------------------
// Issue tag constants
// ---------------------------------------------------------------------------

export const ISSUE_TAGS = [
  'PARSER_MISSED_FILTER',
  'NORM_PLACE_BAD',
  'NORM_PUBLISHER_BAD',
  'NORM_DATE_BAD',
  'EVIDENCE_WRONG',
  'RELEVANCE_UNCLEAR',
] as const;

export type IssueTag = (typeof ISSUE_TAGS)[number];
