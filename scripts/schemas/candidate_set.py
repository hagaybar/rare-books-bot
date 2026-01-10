"""CandidateSet Pydantic models for M4.

Defines the schema for query execution results.
Every candidate must include evidence showing which fields matched.
"""

from datetime import datetime, timezone
from typing import List, Optional, Any
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """Evidence for why a record matched a filter.

    Provides traceability from filter → database value → MARC field.
    """
    field: str  # e.g., "publisher_norm", "date_start"
    value: Any  # Record's value that matched
    operator: str  # e.g., "=", "BETWEEN", "LIKE", "OVERLAPS"
    matched_against: Any  # Plan value(s) that this matched
    source: str  # e.g., "db.imprints.publisher_norm" or "marc:264$b"
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class Candidate(BaseModel):
    """A single record that matched the query.

    Includes deterministic rationale and per-filter evidence.
    """
    record_id: str
    match_rationale: str  # Deterministic template-generated string
    evidence: List[Evidence] = Field(default_factory=list)


class CandidateSet(BaseModel):
    """Complete query result with evidence.

    This is the primary output of M4. Contains all records that matched
    the query plan along with evidence for each match.
    """
    query_text: str
    plan_hash: str  # SHA256 of canonicalized plan JSON
    sql: str  # Exact SQL executed (for reproducibility)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    candidates: List[Candidate] = Field(default_factory=list)
    total_count: int = 0

    @property
    def count(self) -> int:
        """Convenience property for candidate count."""
        return len(self.candidates)
