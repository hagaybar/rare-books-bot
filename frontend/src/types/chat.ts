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
}

export interface GroundingData {
  records: GroundingRecord[];
  agents: GroundingAgent[];
  aggregations: Record<string, unknown[]>;
  links: GroundingLink[];
}

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
}
