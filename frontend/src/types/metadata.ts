export interface ConfidenceBand {
  label: string;
  min_confidence: number;
  max_confidence: number;
  count: number;
}

export interface MethodBreakdown {
  method: string;
  count: number;
}

export interface FlaggedItem {
  raw_value: string;
  norm_value: string | null;
  confidence: number;
  method: string;
  frequency: number;
}

export interface FieldCoverage {
  total_records: number;
  non_null_count: number;
  null_count: number;
  confidence_distribution: ConfidenceBand[];
  method_distribution: MethodBreakdown[];
  flagged_items: FlaggedItem[];
}

export interface CoverageReport {
  date_coverage: FieldCoverage;
  place_coverage: FieldCoverage;
  publisher_coverage: FieldCoverage;
  agent_name_coverage: FieldCoverage;
  agent_role_coverage: FieldCoverage;
  total_imprint_rows: number;
  total_agent_rows: number;
}

export interface IssueRecord {
  mms_id: string;
  raw_value: string;
  norm_value: string | null;
  confidence: number;
  method: string;
}

export interface ClusterValue {
  raw_value: string;
  frequency: number;
  confidence: number;
  method: string;
}

export interface Cluster {
  cluster_id: string;
  field: string;
  cluster_type: string;
  values: ClusterValue[];
  proposed_canonical: string | null;
  evidence: Record<string, unknown>;
  priority_score: number;
  total_records_affected: number;
}

export interface AgentProposal {
  raw_value: string;
  canonical_value: string;
  confidence: number;
  reasoning: string;
  evidence_sources: string[];
}

export interface AgentClusterSummary {
  cluster_id: string;
  cluster_type: string;
  value_count: number;
  total_records: number;
  priority_score: number;
}

export interface AgentChatResponse {
  response: string;
  proposals: AgentProposal[];
  clusters: AgentClusterSummary[];
  field: string;
  action: string;
}

export interface CorrectionEntry {
  timestamp: string;
  field: string;
  raw_value: string;
  canonical_value: string;
  evidence: string;
  source: string;
  action: string;
}

export interface CorrectionHistoryResponse {
  entries: CorrectionEntry[];
  total: number;
}
