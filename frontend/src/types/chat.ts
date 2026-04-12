/**
 * TypeScript interfaces matching the backend ChatResponse API shape.
 *
 * These mirror the Pydantic models in:
 * - app/api/models.py (ChatResponseAPI, ChatRequest)
 * - scripts/chat/models.py (ChatResponse)
 * - scripts/schemas/candidate_set.py (CandidateSet, Candidate, Evidence)
 */

// ---------------------------------------------------------------------------
// Evidence
// ---------------------------------------------------------------------------

export interface Evidence {
  field: string;
  value: unknown;
  operator: string;
  matched_against: unknown;
  source: string;
  confidence: number | null;
  extraction_error: string | null;
}

// ---------------------------------------------------------------------------
// Candidate
// ---------------------------------------------------------------------------

export interface Candidate {
  record_id: string;
  match_rationale: string;
  evidence: Evidence[];
  title: string | null;
  author: string | null;
  date_start: number | null;
  date_end: number | null;
  place_norm: string | null;
  place_raw: string | null;
  publisher: string | null;
  subjects: string[];
  description: string | null;
}

// ---------------------------------------------------------------------------
// CandidateSet
// ---------------------------------------------------------------------------

export interface CandidateSet {
  query_text: string;
  plan_hash: string;
  sql: string;
  sql_parameters: Record<string, unknown>;
  generated_at: string;
  candidates: Candidate[];
  total_count: number;
}

// ---------------------------------------------------------------------------
// ChatResponse (inner response from backend)
// ---------------------------------------------------------------------------

export type ConversationPhase = 'query_definition' | 'corpus_exploration';

export interface ChatResponse {
  message: string;
  candidate_set: CandidateSet | null;
  suggested_followups: string[];
  clarification_needed: string | null;
  session_id: string;
  phase: ConversationPhase | null;
  confidence: number | null;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// API wrapper (POST /chat response)
// ---------------------------------------------------------------------------

export interface ChatResponseAPI {
  success: boolean;
  response: ChatResponse | null;
  error?: string;
}

// ---------------------------------------------------------------------------
// Grounding data (from metadata.grounding in API response)
// ---------------------------------------------------------------------------

export interface GroundingLink {
  entity_type: string;
  entity_id: string;
  label: string;
  url: string;
  source: string;
}

export interface GroundingRecord {
  mms_id: string;
  title: string;
  date_display: string | null;
  place: string | null;
  publisher: string | null;
  language: string | null;
  agents: string[];
  subjects: string[];
  primo_url: string;
  source_steps: number[];
  date_confidence?: number | null;
  place_confidence?: number | null;
  publisher_confidence?: number | null;
  title_variants?: string[];
  subjects_he?: string[];
  notes_structured?: Record<string, string[]>;
}

export interface GroundingAgent {
  canonical_name: string;
  variants: string[];
  birth_year: number | null;
  death_year: number | null;
  occupations: string[];
  description: string | null;
  record_count: number;
  links: GroundingLink[];
  image_url?: string | null;
  authority_uri?: string | null;
  hebrew_aliases?: string[];
}

export interface PublisherDetail {
  canonical_name: string;
  type?: string | null;
  dates_active?: string | null;
  location?: string | null;
  wikidata_id?: string | null;
  cerl_id?: string | null;
}

export interface GroundingData {
  records: GroundingRecord[];
  agents: GroundingAgent[];
  aggregations: Record<string, unknown[]>;
  links: GroundingLink[];
  publishers?: PublisherDetail[];
  connections?: Record<string, unknown>[];
}

// ---------------------------------------------------------------------------
// Streaming state for assistant messages
// ---------------------------------------------------------------------------

export type StreamingState = 'thinking' | 'streaming' | 'complete';

// ---------------------------------------------------------------------------
// UI-only models (not in backend)
// ---------------------------------------------------------------------------

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  candidateSet: CandidateSet | null;
  suggestedFollowups: string[];
  clarificationNeeded: string | null;
  phase: ConversationPhase | null;
  confidence: number | null;
  metadata: Record<string, unknown>;
  timestamp: Date;

  /** Streaming-related fields (only meaningful for assistant messages). */
  streamingState?: StreamingState;
  thinkingSteps?: string[];
}

// ---------------------------------------------------------------------------
// Compare Mode Types
// ---------------------------------------------------------------------------

export interface ModelPair {
  interpreter: string;
  narrator: string;
}

export interface CompareRequest {
  message: string;
  configs: ModelPair[];
  session_id?: string;
  token_saving: boolean;
}

export interface ComparisonMetrics {
  latency_ms: number;
  cost_usd: number;
  tokens: { input: number; output: number };
}

export interface ComparisonResult {
  config: ModelPair;
  response: ChatResponse | null;
  metrics: ComparisonMetrics;
  error: string | null;
}

export interface CompareResponse {
  comparisons: ComparisonResult[];
}

/** Available models for selection in compare mode. */
export const AVAILABLE_MODELS = [
  'gpt-4.1',
  'gpt-4.1-mini',
  'gpt-4.1-nano',
  'gpt-5-mini',
  'gpt-5.4',
] as const;
