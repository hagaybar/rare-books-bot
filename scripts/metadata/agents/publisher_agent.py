"""PublisherAgent: Specialist agent for publisher normalization.

Handles publisher name patterns common in early modern printing:
- Latin formulae: "ex officina...", "typis...", "apud...", "sumptibus..."
- Printer dynasties: Plantin-Moretus, Elzevir, Estienne, Aldus Manutius
- Abbreviations and contractions in publisher names
- "s.n." / "publisher not identified" as missing/unknown markers
- Vernacular variants (Hebrew, Arabic script publisher names)
- Near-matches against existing alias maps

Delegates all DB queries to the AgentHarness.grounding layer and all LLM
calls to the AgentHarness.reasoning layer. Adds publisher-specific logic on top.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from scripts.metadata.agent_harness import AgentHarness, GapRecord, ProposedMapping
from scripts.metadata.audit import (
    generate_coverage_report_from_conn,
)
from scripts.metadata.clustering import (
    Cluster,
    cluster_field_gaps,
    _normalize_for_matching,
)


# ---------------------------------------------------------------------------
# Constants: publisher patterns for early modern books
# ---------------------------------------------------------------------------

# Raw values indicating unknown/missing publisher
_MISSING_PUBLISHER_PATTERNS = re.compile(
    r"^("
    r"s\.?\s*n\.?"
    r"|sine?\s+nomine"
    r"|publisher\s+not\s+identified"
    r"|unknown"
    r"|no\s+publisher"
    r"|n/a"
    r"|not\s+identified"
    r"|\[s\.?\s*n\.?\]"
    r"|\[publisher\s+not\s+identified\]"
    r")$",
    re.IGNORECASE,
)

# Latin publishing formulae
_LATIN_FORMULAE = re.compile(
    r"(?:"
    r"ex\s+officina"
    r"|ex\s+typograph"
    r"|typis"
    r"|apud"
    r"|sumptibus"
    r"|impensis"
    r"|excudebat"
    r"|impressum\s+per"
    r"|per\s+\w+"
    r"|prostant?\s+apud"
    r"|in\s+aedibus"
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class PublisherAnalysis:
    """Full coverage analysis for publisher normalization."""

    total_publishers: int
    mapped_count: int  # Has alias map match (confidence >= 0.95)
    unmapped_count: int  # No alias map (confidence <= 0.80)
    missing_count: int  # Empty/null publisher
    clusters: List[Cluster]
    top_gaps: List[GapRecord]  # Top 20 unmapped by frequency


# ---------------------------------------------------------------------------
# PublisherAgent
# ---------------------------------------------------------------------------


class PublisherAgent:
    """Specialist agent for publisher normalization.

    Knows publisher name patterns, printer dynasties, Latin/vernacular
    variants, and publisher abbreviation patterns.
    """

    def __init__(self, harness: AgentHarness):
        """Initialize with an AgentHarness instance.

        Args:
            harness: AgentHarness providing grounding and reasoning layers.
        """
        self.harness = harness

    # -- Public API ---------------------------------------------------------

    def analyze(self) -> PublisherAnalysis:
        """Run full coverage analysis for publishers.

        Queries the M3 database for publisher confidence distributions,
        builds clusters of unmapped/low-confidence values, and returns
        a structured PublisherAnalysis.

        Returns:
            PublisherAnalysis with coverage stats, clusters, and top gaps.
        """
        conn = self.harness.grounding._connect()
        try:
            report = generate_coverage_report_from_conn(conn)
            pub_cov = report.publisher_coverage

            # Count by confidence band
            mapped = 0  # >= 0.95
            unmapped = 0  # <= 0.80
            for band in pub_cov.confidence_distribution:
                if band.lower >= 0.95:
                    mapped += band.count
                elif band.lower < 0.80:
                    unmapped += band.count

            # Count missing (NULL publisher_raw or empty string)
            missing_row = conn.execute(
                "SELECT COUNT(*) FROM imprints "
                "WHERE publisher_raw IS NULL OR TRIM(publisher_raw) = ''"
            ).fetchone()
            missing_count = missing_row[0] if missing_row else 0

            # Also count s.n. / "publisher not identified" as missing
            sn_row = conn.execute(
                "SELECT COUNT(*) FROM imprints "
                "WHERE publisher_raw IS NOT NULL AND TRIM(publisher_raw) != '' "
                "AND ("
                "  LOWER(TRIM(publisher_raw)) IN ("
                "    's.n.', '[s.n.]', 'sine nomine', 'publisher not identified', "
                "    '[publisher not identified]', 'unknown', 'no publisher', 'n/a', "
                "    'not identified', 's.n', 'sn'"
                "  )"
                ")"
            ).fetchone()
            missing_count += sn_row[0] if sn_row else 0

            # Build clusters from flagged items
            alias_map = self.harness.grounding.query_alias_map("publisher")
            clusters = cluster_field_gaps(
                field="publisher",
                flagged_items=pub_cov.flagged_items,
                alias_map=alias_map,
            )

            # Top gaps by frequency (from grounding layer)
            gaps = self.harness.grounding.query_gaps(
                "publisher", max_confidence=0.80
            )
            # Deduplicate by raw_value and count frequency
            freq_map: Dict[str, GapRecord] = {}
            freq_count: Dict[str, int] = {}
            for gap in gaps:
                key = gap.raw_value
                if key not in freq_map:
                    freq_map[key] = gap
                    freq_count[key] = 1
                else:
                    freq_count[key] += 1

            top_gaps = sorted(
                freq_map.values(),
                key=lambda g: freq_count[g.raw_value],
                reverse=True,
            )[:20]

            return PublisherAnalysis(
                total_publishers=pub_cov.total_records,
                mapped_count=mapped,
                unmapped_count=unmapped,
                missing_count=missing_count,
                clusters=clusters,
                top_gaps=top_gaps,
            )
        finally:
            conn.close()

    def get_clusters(self) -> List[Cluster]:
        """Group unmapped publishers by variant patterns.

        Returns:
            Clusters sorted by priority_score (highest first).
        """
        conn = self.harness.grounding._connect()
        try:
            report = generate_coverage_report_from_conn(conn)
            flagged = report.publisher_coverage.flagged_items
        finally:
            conn.close()

        alias_map = self.harness.grounding.query_alias_map("publisher")
        clusters = cluster_field_gaps(
            field="publisher",
            flagged_items=flagged,
            alias_map=alias_map,
        )
        return sorted(clusters, key=lambda c: c.priority_score, reverse=True)

    def propose_mappings(self, cluster: Cluster) -> List[ProposedMapping]:
        """LLM-assisted proposals for a cluster of related publishers.

        For each value in the cluster:
        1. Gather evidence (existing alias map near-matches, frequency,
           Latin formula detection)
        2. Ask LLM for canonical mapping via harness.reasoning.propose_mapping()
        3. Include evidence_sources in the proposal

        The LLM prompt context includes knowledge of:
        - Printer dynasties (Plantin, Elzevir, Estienne, Aldus)
        - Latin publishing formulae (ex officina, typis, apud, sumptibus)
        - Publisher abbreviation conventions
        - s.n. / unknown publisher patterns

        Args:
            cluster: A Cluster of publisher values to propose mappings for.

        Returns:
            List of ProposedMapping with canonical values and reasoning.
        """
        proposals: List[ProposedMapping] = []

        for value in cluster.values:
            # Build evidence dict with publisher-specific context
            evidence: Dict[str, Any] = {
                "field": "publisher",
                "cluster_type": cluster.cluster_type,
                "frequency": value.frequency,
                "is_missing_marker": self._is_missing_publisher(
                    value.raw_value
                ),
                "has_latin_formula": bool(
                    _LATIN_FORMULAE.search(value.raw_value)
                ),
            }

            # Add near-match info from cluster evidence if available
            if cluster.evidence and "proposed_mappings" in cluster.evidence:
                proposed = cluster.evidence["proposed_mappings"]
                if value.raw_value in proposed:
                    evidence["near_match_candidate"] = proposed[
                        value.raw_value
                    ]

            proposal = self.harness.reasoning.propose_mapping(
                raw_value=value.raw_value,
                field="publisher",
                evidence=evidence,
            )
            proposals.append(proposal)

        return proposals

    def find_related(self, canonical_name: str) -> List[str]:
        """Find all raw variants that likely refer to this publisher.

        Queries the DB for all raw publisher values, normalizes them
        (casefold, strip punctuation/brackets), and returns those
        matching the given canonical name after normalization.

        Args:
            canonical_name: The canonical publisher name to search for
                            (e.g., "elsevier", "plantin").

        Returns:
            List of raw publisher strings that match after normalization.
            Sorted alphabetically, deduplicated.
        """
        target_norm = _normalize_for_matching(canonical_name)
        if not target_norm:
            return []

        conn = self.harness.grounding._connect()
        try:
            rows = conn.execute(
                "SELECT DISTINCT publisher_raw FROM imprints "
                "WHERE publisher_raw IS NOT NULL AND TRIM(publisher_raw) != ''"
            ).fetchall()

            matches: List[str] = []
            for (raw_value,) in rows:
                if _normalize_for_matching(raw_value) == target_norm:
                    matches.append(raw_value)

            return sorted(matches)
        finally:
            conn.close()

    # -- Private helpers ----------------------------------------------------

    @staticmethod
    def _is_missing_publisher(raw_value: str) -> bool:
        """Check if a raw publisher value indicates missing/unknown.

        Detects patterns like "s.n.", "[s.n.]", "publisher not identified",
        "sine nomine", "unknown", etc.

        Args:
            raw_value: The raw publisher string.

        Returns:
            True if the value indicates a missing/unknown publisher.
        """
        if not raw_value or not raw_value.strip():
            return True
        cleaned = raw_value.strip()
        return bool(_MISSING_PUBLISHER_PATTERNS.match(cleaned))
