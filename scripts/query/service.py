"""Unified Query Service - Single entry point for all query execution.

This module provides QueryService, the unified entry point for query execution
across all interfaces (CLI, FastAPI, Streamlit, QA tool). It ensures consistent
query results, warnings, and facet computation regardless of the calling interface.

Usage:
    from scripts.query.service import QueryService

    service = QueryService(db_path)
    result = service.execute("books by Oxford between 1500 and 1599")

    # With options
    result = service.execute(
        "books in Paris",
        options=QueryOptions(compute_facets=True)
    )
"""

import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

from scripts.schemas import QueryPlan, CandidateSet, FilterField
from scripts.query.models import (
    QueryResult,
    QueryOptions,
    QueryWarning,
    FacetCounts,
)
from scripts.query.compile import compile_query
from scripts.query.execute import execute_plan
from scripts.query.db_adapter import build_full_query
from scripts.query.exceptions import QueryCompilationError
from scripts.utils.logger import LoggerManager

logger = LoggerManager.get_logger(__name__)


# Warning codes
WARNING_LOW_CONFIDENCE = "LOW_CONFIDENCE"
WARNING_EMPTY_FILTERS = "EMPTY_FILTERS"
WARNING_BROAD_DATE_RANGE = "BROAD_DATE_RANGE"
WARNING_VAGUE_QUERY = "VAGUE_QUERY"
WARNING_ZERO_RESULTS = "ZERO_RESULTS"


class QueryService:
    """Unified query service for all interfaces.

    Provides a single entry point for:
    - Query compilation (natural language -> QueryPlan)
    - Query execution (QueryPlan -> CandidateSet)
    - Warning extraction (low confidence, ambiguous filters)
    - Facet computation (optional)

    All interfaces (CLI, API, Streamlit, QA) should use this service
    to ensure consistent query results.
    """

    def __init__(
        self,
        db_path: Path,
        api_key: Optional[str] = None,
    ):
        """Initialize QueryService.

        Args:
            db_path: Path to bibliographic SQLite database
            api_key: Optional OpenAI API key for query compilation.
                     If not provided, uses OPENAI_API_KEY environment variable.
        """
        self.db_path = Path(db_path)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def execute(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        options: Optional[QueryOptions] = None,
    ) -> QueryResult:
        """Execute a natural language query.

        This is the single entry point for all query execution. It:
        1. Compiles user_message -> QueryPlan (with warnings for low confidence)
        2. Builds SQL from plan (captures sql + params)
        3. Executes -> CandidateSet with evidence/rationales
        4. Optionally computes facets over result set
        5. Returns unified QueryResult

        Args:
            user_message: Natural language query string
            session_id: Optional session ID for tracking (not used currently)
            options: Query execution options

        Returns:
            QueryResult with plan, candidates, facets, and warnings

        Raises:
            QueryCompilationError: If query compilation fails
        """
        options = options or QueryOptions()
        start_time = time.time()
        warnings: List[QueryWarning] = []

        # Step 1: Compile query to plan
        logger.info("Compiling query", extra={"query": user_message[:100]})
        plan = compile_query(
            user_message,
            limit=options.limit,
            api_key=self.api_key,
        )

        # Step 2: Extract warnings from plan
        if options.include_warnings:
            warnings = self._extract_warnings(plan)

        # Step 3: Build SQL for logging/debugging
        sql, params = build_full_query(plan)

        # Step 4: Execute query
        logger.info(
            "Executing query",
            extra={
                "filters": len(plan.filters),
                "limit": plan.limit,
            },
        )
        candidate_set = execute_plan(plan, self.db_path)

        # Step 5: Add zero results warning if applicable
        if options.include_warnings and len(candidate_set.candidates) == 0:
            warnings.append(
                QueryWarning(
                    code=WARNING_ZERO_RESULTS,
                    message="Query returned no results. Consider broadening your search criteria.",
                )
            )

        # Step 6: Compute facets if requested
        facets = None
        if options.compute_facets and candidate_set.candidates:
            record_ids = [c.record_id for c in candidate_set.candidates]
            facets = self._compute_facets(record_ids, options)

        execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "Query executed",
            extra={
                "candidates": len(candidate_set.candidates),
                "execution_time_ms": execution_time_ms,
                "warnings": len(warnings),
            },
        )

        # Convert params dict to list for the model
        params_list = list(params.values()) if isinstance(params, dict) else params

        return QueryResult(
            query_plan=plan,
            sql=sql,
            params=params_list,
            candidate_set=candidate_set,
            facets=facets,
            warnings=warnings,
            execution_time_ms=execution_time_ms,
        )

    def execute_plan(
        self,
        plan: QueryPlan,
        options: Optional[QueryOptions] = None,
    ) -> QueryResult:
        """Execute a pre-compiled QueryPlan.

        Use this when you already have a QueryPlan (e.g., from cache or
        when retrying with modified parameters).

        Args:
            plan: Pre-compiled QueryPlan
            options: Query execution options

        Returns:
            QueryResult with candidates, facets, and warnings
        """
        options = options or QueryOptions()
        start_time = time.time()
        warnings: List[QueryWarning] = []

        # Extract warnings from plan
        if options.include_warnings:
            warnings = self._extract_warnings(plan)

        # Build SQL
        sql, params = build_full_query(plan)

        # Execute query
        candidate_set = execute_plan(plan, self.db_path)

        # Add zero results warning if applicable
        if options.include_warnings and len(candidate_set.candidates) == 0:
            warnings.append(
                QueryWarning(
                    code=WARNING_ZERO_RESULTS,
                    message="Query returned no results. Consider broadening your search criteria.",
                )
            )

        # Compute facets if requested
        facets = None
        if options.compute_facets and candidate_set.candidates:
            record_ids = [c.record_id for c in candidate_set.candidates]
            facets = self._compute_facets(record_ids, options)

        execution_time_ms = (time.time() - start_time) * 1000

        params_list = list(params.values()) if isinstance(params, dict) else params

        return QueryResult(
            query_plan=plan,
            sql=sql,
            params=params_list,
            candidate_set=candidate_set,
            facets=facets,
            warnings=warnings,
            execution_time_ms=execution_time_ms,
        )

    def _extract_warnings(self, plan: QueryPlan) -> List[QueryWarning]:
        """Extract warnings from QueryPlan.

        Generates warnings for:
        - Empty filter sets
        - Low confidence filters (< 0.7)
        - Broad date ranges (> 200 years)
        - Vague queries (single-word subject/title without context)

        Args:
            plan: QueryPlan to analyze

        Returns:
            List of QueryWarning objects
        """
        warnings: List[QueryWarning] = []

        # Check for empty filters
        if not plan.filters:
            warnings.append(
                QueryWarning(
                    code=WARNING_EMPTY_FILTERS,
                    message="Query produced no specific filters. Try adding date ranges, places, or subjects.",
                )
            )
            return warnings  # No need to check other warnings if no filters

        # Check each filter for issues
        for f in plan.filters:
            # Low confidence warning
            if f.confidence is not None and f.confidence < 0.7:
                warnings.append(
                    QueryWarning(
                        code=WARNING_LOW_CONFIDENCE,
                        message=f"Filter on '{f.field.value}' has low confidence ({f.confidence:.0%})",
                        field=f.field.value,
                        confidence=f.confidence,
                    )
                )

            # Broad date range warning
            if f.field == FilterField.YEAR and f.start is not None and f.end is not None:
                date_span = f.end - f.start
                if date_span > 200:
                    warnings.append(
                        QueryWarning(
                            code=WARNING_BROAD_DATE_RANGE,
                            message=f"Date range spans {date_span} years ({f.start}-{f.end}). Consider narrowing.",
                            field=f.field.value,
                        )
                    )

            # Vague query warning (single short word for subject/title)
            if f.field in [FilterField.SUBJECT, FilterField.TITLE]:
                if f.value and isinstance(f.value, str) and len(f.value.split()) == 1 and len(f.value) < 5:
                    warnings.append(
                        QueryWarning(
                            code=WARNING_VAGUE_QUERY,
                            message=f"Search term '{f.value}' is very short. Consider using more specific terms.",
                            field=f.field.value,
                        )
                    )

        return warnings

    def _compute_facets(
        self,
        candidate_ids: List[str],
        options: QueryOptions,
    ) -> FacetCounts:
        """Compute facet counts for result set.

        Aggregates results by place, year, language, publisher, and century.

        Args:
            candidate_ids: List of MMS IDs to aggregate
            options: QueryOptions with facet_limit

        Returns:
            FacetCounts with aggregations
        """
        if not candidate_ids:
            return FacetCounts()

        limit = options.facet_limit

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        try:
            facets = FacetCounts()
            placeholders = ",".join("?" * len(candidate_ids))

            # By place
            facets.by_place = self._run_facet_query(
                conn,
                f"""
                SELECT place_norm as value, COUNT(DISTINCT record_id) as count
                FROM imprints
                WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
                  AND place_norm IS NOT NULL AND place_norm != ''
                GROUP BY place_norm
                ORDER BY count DESC
                LIMIT ?
                """,
                [*candidate_ids, limit],
            )

            # By publisher
            facets.by_publisher = self._run_facet_query(
                conn,
                f"""
                SELECT publisher_norm as value, COUNT(DISTINCT record_id) as count
                FROM imprints
                WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
                  AND publisher_norm IS NOT NULL AND publisher_norm != ''
                GROUP BY publisher_norm
                ORDER BY count DESC
                LIMIT ?
                """,
                [*candidate_ids, limit],
            )

            # By language
            facets.by_language = self._run_facet_query(
                conn,
                f"""
                SELECT l.code as value, COUNT(DISTINCT l.record_id) as count
                FROM languages l
                JOIN records r ON l.record_id = r.id
                WHERE r.mms_id IN ({placeholders})
                GROUP BY l.code
                ORDER BY count DESC
                LIMIT ?
                """,
                [*candidate_ids, limit],
            )

            # By year (decade buckets)
            facets.by_year = self._run_facet_query(
                conn,
                f"""
                SELECT
                    CAST((date_start / 10 * 10) AS TEXT) || 's' as value,
                    COUNT(DISTINCT record_id) as count
                FROM imprints
                WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
                  AND date_start IS NOT NULL
                  AND date_start <= 2100
                GROUP BY date_start / 10 * 10
                ORDER BY date_start / 10 * 10 ASC
                LIMIT ?
                """,
                [*candidate_ids, limit],
            )

            # By century
            facets.by_century = self._run_facet_query(
                conn,
                f"""
                SELECT
                    CASE
                        WHEN (date_start - 1) / 100 + 1 = 15 THEN '15th century'
                        WHEN (date_start - 1) / 100 + 1 = 16 THEN '16th century'
                        WHEN (date_start - 1) / 100 + 1 = 17 THEN '17th century'
                        WHEN (date_start - 1) / 100 + 1 = 18 THEN '18th century'
                        WHEN (date_start - 1) / 100 + 1 = 19 THEN '19th century'
                        ELSE CAST((date_start - 1) / 100 + 1 AS TEXT) || 'th century'
                    END as value,
                    COUNT(DISTINCT record_id) as count
                FROM imprints
                WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
                  AND date_start IS NOT NULL
                  AND date_start <= 2100
                GROUP BY (date_start - 1) / 100 + 1
                ORDER BY (date_start - 1) / 100 + 1 ASC
                LIMIT ?
                """,
                [*candidate_ids, limit],
            )

            return facets

        finally:
            conn.close()

    def _run_facet_query(
        self,
        conn: sqlite3.Connection,
        query: str,
        params: List,
    ) -> Dict[str, int]:
        """Execute a facet aggregation query.

        Args:
            conn: Database connection
            query: SQL query
            params: Query parameters

        Returns:
            Dict mapping facet values to counts
        """
        try:
            cursor = conn.execute(query, params)
            return {row["value"]: row["count"] for row in cursor.fetchall()}
        except Exception as e:
            logger.warning(f"Facet query failed: {e}")
            return {}
