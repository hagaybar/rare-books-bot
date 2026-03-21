"""DateAgent: Specialist agent for date normalization.

Handles Hebrew calendars, Latin date conventions (Anno Domini, Roman numerals),
circa patterns, date ranges, partial centuries, and publication date patterns
by era (15th-19th century).

Delegates all DB queries to the AgentHarness.grounding layer and all LLM
calls to the AgentHarness.reasoning layer. Adds date-specific logic on top.
"""

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional

from scripts.metadata.agent_harness import AgentHarness, GapRecord, ProposedMapping
from scripts.metadata.audit import (
    LowConfidenceItem,
    generate_coverage_report_from_conn,
)
from scripts.metadata.clustering import Cluster, classify_date_pattern, cluster_field_gaps


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class UnparsedDate:
    """A date record that the deterministic parser could not handle."""

    mms_id: str
    raw_value: str
    current_confidence: float
    current_method: str
    pattern_type: str  # classify_date_pattern output


@dataclass
class ProposedDate:
    """An LLM-proposed date normalization for a raw value."""

    raw_value: str
    date_start: Optional[int]
    date_end: Optional[int]
    method: str
    confidence: float
    reasoning: str


@dataclass
class DateAnalysis:
    """Full coverage analysis for date normalization."""

    total_dates: int
    parsed_count: int       # confidence >= 0.8
    unparsed_count: int     # confidence < 0.8 or method="unparsed"/"missing"
    by_method: Dict[str, int]     # counts per normalization method
    by_pattern: Dict[str, int]    # counts per unparsed pattern type
    clusters: List[Cluster]
    top_unparsed: List[UnparsedDate]  # Top 20 by frequency


# ---------------------------------------------------------------------------
# LLM system prompt for date proposals
# ---------------------------------------------------------------------------

_DATE_PROPOSAL_PROMPT = """You are a bibliographic metadata specialist for rare books (15th-19th century).
Given an unparsed date string from a MARC record, determine the publication date range.

The following patterns are ALREADY handled by the deterministic parser - do NOT propose these:
1. Exact 4-digit years: "1650" -> 1650-1650
2. Bracketed years: "[1680]" -> 1680-1680
3. Circa dates: "c. 1650" -> 1645-1655
4. Explicit ranges: "1500-1599" -> 1500-1599
5. Embedded years: "printed in the year 1723" -> 1723-1723
6. Hebrew gematria: "שנת תק\\"ע" -> 1810-1810

The value below was NOT matched by any of these patterns.

RAW DATE VALUE: "{raw_value}"
PATTERN TYPE: "{pattern_type}"

Respond with ONLY a JSON object:
{{
  "date_start": integer or null,
  "date_end": integer or null,
  "method": "llm_proposed",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""


# ---------------------------------------------------------------------------
# DateAgent
# ---------------------------------------------------------------------------


class DateAgent:
    """Specialist agent for date normalization.

    Knows Hebrew calendars, Latin date conventions, circa patterns,
    date ranges, and publication date patterns by era.
    """

    def __init__(self, harness: AgentHarness):
        """Initialize with an AgentHarness instance.

        Args:
            harness: AgentHarness providing grounding and reasoning layers.
        """
        self.harness = harness

    # -- Public API ---------------------------------------------------------

    def analyze(self) -> DateAnalysis:
        """Run full coverage analysis for dates.

        Queries the M3 database for date confidence distributions, builds
        clusters of unparsed date values, and returns a structured
        DateAnalysis.

        Returns:
            DateAnalysis with coverage stats, clusters, and top unparsed.
        """
        conn = self.harness.grounding._connect()
        try:
            report = generate_coverage_report_from_conn(conn)
            date_cov = report.date_coverage

            # Count parsed vs unparsed
            parsed = 0
            unparsed = 0
            for band in date_cov.confidence_distribution:
                if band.lower >= 0.8:
                    parsed += band.count
                else:
                    unparsed += band.count

            # Method distribution as dict
            by_method: Dict[str, int] = {}
            for mb in date_cov.method_distribution:
                by_method[mb.method] = mb.count

            # Build clusters from flagged items
            clusters = cluster_field_gaps(
                field="date",
                flagged_items=date_cov.flagged_items,
            )

            # Get unparsed dates and classify by pattern
            unparsed_dates = self._get_unparsed_from_flagged(date_cov.flagged_items)

            # Build pattern distribution
            by_pattern: Dict[str, int] = defaultdict(int)
            for ud in unparsed_dates:
                by_pattern[ud.pattern_type] += 1
            by_pattern = dict(by_pattern)

            # Top 20 by frequency (flagged_items are already sorted by freq)
            top_unparsed = unparsed_dates[:20]

            return DateAnalysis(
                total_dates=date_cov.total_records,
                parsed_count=parsed,
                unparsed_count=unparsed,
                by_method=by_method,
                by_pattern=by_pattern,
                clusters=clusters,
                top_unparsed=top_unparsed,
            )
        finally:
            conn.close()

    def get_unparsed(self) -> List[UnparsedDate]:
        """All dates with method='unparsed'/'missing' or confidence < 0.8.

        Queries the grounding layer for date gaps and classifies each by
        pattern type using regex heuristics.

        Returns:
            List of UnparsedDate with pattern classification.
        """
        gaps = self.harness.grounding.query_gaps("date", max_confidence=0.8)
        results: List[UnparsedDate] = []
        for gap in gaps:
            pattern_type = classify_date_pattern(gap.raw_value)
            results.append(
                UnparsedDate(
                    mms_id=gap.mms_id,
                    raw_value=gap.raw_value,
                    current_confidence=gap.confidence,
                    current_method=gap.method,
                    pattern_type=pattern_type,
                )
            )
        return results

    def propose_dates(
        self, unparsed: List[UnparsedDate]
    ) -> List[ProposedDate]:
        """LLM-assisted date proposals for a batch of unparsed dates.

        The LLM system prompt includes the 6 deterministic patterns already
        handled (so it does not re-propose), Hebrew calendar conversion
        reference, and instructions to provide date_start, date_end, method,
        and confidence.

        Args:
            unparsed: List of UnparsedDate items to propose dates for.

        Returns:
            List of ProposedDate with parsed results and reasoning.
        """
        proposals: List[ProposedDate] = []

        for item in unparsed:
            evidence: Dict[str, Any] = {
                "field": "date",
                "pattern_type": item.pattern_type,
                "current_method": item.current_method,
                "current_confidence": item.current_confidence,
            }

            mapping = self.harness.reasoning.propose_mapping(
                raw_value=item.raw_value,
                field="date",
                evidence=evidence,
            )

            # Parse the LLM response into ProposedDate
            proposed = self._mapping_to_proposed_date(item.raw_value, mapping)
            proposals.append(proposed)

        return proposals

    def group_by_pattern(self) -> Dict[str, List[UnparsedDate]]:
        """Group unparsed dates by pattern type.

        Groups:
            - partial_century: [17--?], [18--]
            - hebrew_gematria: Hebrew letter numerals
            - latin_convention: Anno, MDCCC
            - ambiguous_range: 1500-99 (unclear if range or single)
            - circa: ca. 1650, circa 1700
            - empty_missing: empty strings, null-like
            - other_unparsed: anything else

        Returns:
            Dict mapping pattern type to list of UnparsedDate.
        """
        unparsed = self.get_unparsed()
        groups: Dict[str, List[UnparsedDate]] = defaultdict(list)
        for item in unparsed:
            groups[item.pattern_type].append(item)
        return dict(groups)

    @staticmethod
    def classify_date_pattern(raw_value: str) -> str:
        """Classify an unparsed date string into a pattern type.

        Delegates to the shared clustering module's classify_date_pattern.

        Args:
            raw_value: The raw date string from MARC data.

        Returns:
            Pattern type label (partial_century, hebrew_gematria,
            latin_convention, circa, ambiguous_range, empty_missing,
            other_unparsed).
        """
        return classify_date_pattern(raw_value)

    # -- Private helpers ----------------------------------------------------

    def _get_unparsed_from_flagged(
        self, flagged_items: List[LowConfidenceItem]
    ) -> List[UnparsedDate]:
        """Convert flagged items into UnparsedDate objects.

        Args:
            flagged_items: Low-confidence items from the audit report.

        Returns:
            List of UnparsedDate sorted by frequency (descending).
        """
        results: List[UnparsedDate] = []
        for item in flagged_items:
            pattern_type = classify_date_pattern(item.raw_value)
            results.append(
                UnparsedDate(
                    mms_id="",  # flagged items don't carry mms_id
                    raw_value=item.raw_value,
                    current_confidence=item.confidence,
                    current_method=item.method or "",
                    pattern_type=pattern_type,
                )
            )
        return results

    @staticmethod
    def _mapping_to_proposed_date(
        raw_value: str, mapping: ProposedMapping
    ) -> ProposedDate:
        """Convert a ProposedMapping into a ProposedDate.

        Attempts to extract date_start and date_end from the canonical_value
        string. Falls back to None if not parseable.

        Args:
            raw_value: The original raw date string.
            mapping: The LLM-proposed mapping.

        Returns:
            ProposedDate with extracted fields.
        """
        date_start: Optional[int] = None
        date_end: Optional[int] = None

        canonical = mapping.canonical_value

        # Try to parse canonical_value as JSON-like structure
        try:
            parsed = json.loads(canonical) if canonical.strip().startswith("{") else None
            if parsed and isinstance(parsed, dict):
                date_start = parsed.get("date_start")
                date_end = parsed.get("date_end")
                reasoning = parsed.get("reasoning", mapping.reasoning)
                confidence = parsed.get("confidence", mapping.confidence)
                method = parsed.get("method", "llm_proposed")
                return ProposedDate(
                    raw_value=raw_value,
                    date_start=int(date_start) if date_start is not None else None,
                    date_end=int(date_end) if date_end is not None else None,
                    method=method,
                    confidence=float(confidence),
                    reasoning=reasoning,
                )
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        # Try to extract a year range from the canonical value
        range_match = re.search(r"(\d{4})\s*[-–/]\s*(\d{4})", canonical)
        if range_match:
            date_start = int(range_match.group(1))
            date_end = int(range_match.group(2))
        else:
            # Try single year
            year_match = re.search(r"(\d{4})", canonical)
            if year_match:
                year = int(year_match.group(1))
                if 1000 <= year <= 2100:
                    date_start = year
                    date_end = year

        return ProposedDate(
            raw_value=raw_value,
            date_start=date_start,
            date_end=date_end,
            method="llm_proposed",
            confidence=mapping.confidence,
            reasoning=mapping.reasoning,
        )
