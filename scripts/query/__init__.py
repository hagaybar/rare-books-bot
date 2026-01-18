"""Query module - Natural language query compilation and execution.

This module provides the query pipeline for bibliographic discovery:
- compile_query: Natural language -> QueryPlan (LLM-based)
- execute_plan: QueryPlan -> CandidateSet with evidence
- QueryService: Unified entry point for all interfaces

Usage:
    # Unified approach (recommended)
    from scripts.query import QueryService, QueryOptions, QueryResult

    service = QueryService(db_path)
    result = service.execute("books by Oxford")

    # Direct compilation/execution (legacy)
    from scripts.query import compile_query, execute_plan

    plan = compile_query("books by Oxford")
    candidate_set = execute_plan(plan, db_path)
"""

from scripts.query.compile import compile_query
from scripts.query.execute import execute_plan, execute_plan_from_file
from scripts.query.exceptions import QueryCompilationError
from scripts.query.models import (
    QueryResult,
    QueryOptions,
    QueryWarning,
    FacetCounts,
)
from scripts.query.service import QueryService

__all__ = [
    # Unified service (preferred)
    "QueryService",
    "QueryResult",
    "QueryOptions",
    "QueryWarning",
    "FacetCounts",
    # Legacy functions
    "compile_query",
    "execute_plan",
    "execute_plan_from_file",
    "QueryCompilationError",
]
