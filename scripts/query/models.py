"""Extended query result schemas for unified QueryService.

This module defines the schemas for unified query execution results,
including warnings, facet counts, and options.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from scripts.schemas import QueryPlan, CandidateSet


class QueryWarning(BaseModel):
    """Warning generated during query execution.

    Warnings are generated for:
    - Low confidence filters
    - Ambiguous query terms
    - Empty filter sets
    - Broad date ranges
    """
    code: str  # e.g., "LOW_CONFIDENCE", "AMBIGUOUS_FILTER", "EMPTY_FILTERS"
    message: str
    field: Optional[str] = None
    confidence: Optional[float] = None


class FacetCounts(BaseModel):
    """Facet aggregations over query results.

    Computed over the CandidateSet when requested via QueryOptions.
    """
    by_place: Dict[str, int] = Field(default_factory=dict)
    by_year: Dict[str, int] = Field(default_factory=dict)
    by_language: Dict[str, int] = Field(default_factory=dict)
    by_publisher: Dict[str, int] = Field(default_factory=dict)
    by_century: Dict[str, int] = Field(default_factory=dict)


class QueryOptions(BaseModel):
    """Options for query execution.

    Controls facet computation and other optional behaviors.
    """
    compute_facets: bool = False
    facet_limit: int = 10
    include_warnings: bool = True
    # Limit for query results (None = no limit, use plan default)
    limit: Optional[int] = None


class QueryResult(BaseModel):
    """Unified result from QueryService.execute().

    This is the single result type returned by all query operations,
    ensuring consistency across CLI, API, Streamlit, and QA interfaces.
    """
    query_plan: QueryPlan
    sql: str
    params: List[Any] = Field(default_factory=list)
    candidate_set: CandidateSet
    facets: Optional[FacetCounts] = None
    warnings: List[QueryWarning] = Field(default_factory=list)
    execution_time_ms: float = 0.0
