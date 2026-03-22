"""NameAgent: Specialist agent for name authority normalization.

Cross-references the authority_enrichment table to validate normalized names
against canonical authority forms. Handles:
- "Last, First" vs "First Last" reordering
- Fuzzy name matching (casefold, strip punctuation)
- Authority URI lookup from MARC $0 subfields
- LLM-assisted canonical name proposals for unmatched agents

Delegates all DB queries to the AgentHarness.grounding layer and all LLM
calls to the AgentHarness.reasoning layer. Adds name-specific logic on top.
"""

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional

from scripts.metadata.agent_harness import AgentHarness, GapRecord, ProposedMapping
from scripts.metadata.audit import generate_coverage_report_from_conn
from scripts.metadata.clustering import Cluster, cluster_field_gaps


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AgentRecord:
    """A single agent entry from the agents table."""

    mms_id: str
    agent_raw: str
    agent_norm: Optional[str]
    confidence: float
    method: str
    role_raw: Optional[str]
    role_norm: Optional[str]
    authority_uri: Optional[str]


@dataclass
class ProposedAuthority:
    """An authority match proposal for a raw agent name."""

    agent_raw: str
    suggested_uri: Optional[str]
    canonical_name: Optional[str]
    confidence: float
    reasoning: str
    source: str  # "wikidata", "viaf", "nli", "llm", "authority_enrichment"


@dataclass
class ValidationResult:
    """Result of comparing a normalized name against its authority form."""

    mms_id: str
    agent_raw: str
    agent_norm: str
    authority_canonical: Optional[str]
    match: bool  # normalized matches authority
    confidence_boost: Optional[float]  # suggested new confidence if match


@dataclass
class AgentAnalysis:
    """Full coverage analysis for agent names."""

    total_agents: int
    with_authority: int  # Have authority URI
    without_authority: int
    low_confidence_count: int  # confidence <= 0.8
    missing_role_count: int
    clusters: List  # List[Cluster] — gap clusters for the dashboard
    top_gaps: List[AgentRecord]


# ---------------------------------------------------------------------------
# Name matching utilities
# ---------------------------------------------------------------------------

# Punctuation pattern: everything that is not a letter, digit, or whitespace
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
# Whitespace collapsing
_MULTI_SPACE_RE = re.compile(r"\s+")


def normalize_name_for_comparison(name: str) -> str:
    """Normalize a name string for fuzzy comparison.

    Steps:
    1. Unicode NFC normalization
    2. Casefold
    3. Strip punctuation (commas, periods, brackets, etc.)
    4. Collapse whitespace
    5. Strip leading/trailing whitespace

    Args:
        name: Raw or normalized name string.

    Returns:
        Cleaned lowercase string suitable for comparison.
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFC", name)
    s = s.casefold()
    s = _PUNCT_RE.sub(" ", s)
    s = _MULTI_SPACE_RE.sub(" ", s)
    return s.strip()


def reorder_name(name: str) -> str:
    """Convert 'Last, First Middle' to 'First Middle Last'.

    If the name contains a comma, splits on the first comma and swaps
    the parts. Otherwise returns the name unchanged (after normalization).

    Args:
        name: Name string, possibly in 'Last, First' form.

    Returns:
        Name in 'First Last' order, normalized for comparison.
    """
    if not name:
        return ""

    if "," not in name:
        return normalize_name_for_comparison(name)

    # Split on the original comma BEFORE stripping punctuation
    parts = name.split(",", 1)
    if len(parts) == 2:
        last = normalize_name_for_comparison(parts[0])
        first = normalize_name_for_comparison(parts[1])
        if first and last:
            return f"{first} {last}"
        return last or first
    return normalize_name_for_comparison(name)


def names_match(name_a: str, name_b: str) -> bool:
    """Check if two name strings refer to the same person.

    Tries direct comparison after normalization, then tries reordering
    (Last, First vs First Last).

    Args:
        name_a: First name string.
        name_b: Second name string.

    Returns:
        True if the names match under any ordering.
    """
    if not name_a or not name_b:
        return False

    norm_a = normalize_name_for_comparison(name_a)
    norm_b = normalize_name_for_comparison(name_b)

    # Direct match
    if norm_a == norm_b:
        return True

    # Try reordered match (Last, First vs First Last)
    reorder_a = reorder_name(name_a)
    reorder_b = reorder_name(name_b)

    if reorder_a == reorder_b:
        return True

    # Cross-check: one normalized, one reordered
    if norm_a == reorder_b or reorder_a == norm_b:
        return True

    return False


# ---------------------------------------------------------------------------
# NameAgent
# ---------------------------------------------------------------------------


class NameAgent:
    """Specialist agent for name authority normalization.

    Knows name authority conventions (VIAF, NLI, LCNAF),
    leverages authority URIs from MARC $0 subfields,
    and validates normalized names against authority canonical forms.
    """

    def __init__(self, harness: AgentHarness):
        """Initialize with an AgentHarness instance.

        Args:
            harness: AgentHarness providing grounding and reasoning layers.
        """
        self.harness = harness

    # -- Public API ---------------------------------------------------------

    def analyze(self) -> AgentAnalysis:
        """Run full coverage analysis for agent names.

        Queries the agents table for:
        - Total agent count
        - With/without authority URIs
        - Low confidence (< 0.8)
        - Missing roles
        - Top gaps by frequency

        Returns:
            AgentAnalysis with coverage stats and top gaps.
        """
        conn = self.harness.grounding._connect()
        try:
            # Total agents
            total = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]

            # With authority URI
            with_auth = conn.execute(
                "SELECT COUNT(*) FROM agents "
                "WHERE authority_uri IS NOT NULL AND authority_uri != ''"
            ).fetchone()[0]

            # Without authority URI
            without_auth = total - with_auth

            # Low confidence (<= 0.8)
            low_conf = conn.execute(
                "SELECT COUNT(*) FROM agents WHERE agent_confidence <= 0.8"
            ).fetchone()[0]

            # Missing role
            missing_role = conn.execute(
                "SELECT COUNT(*) FROM agents "
                "WHERE role_raw IS NULL OR role_raw = ''"
            ).fetchone()[0]

            # Top gaps: low confidence agents, deduplicated by raw value,
            # sorted by frequency
            gap_rows = conn.execute(
                """
                SELECT r.mms_id, a.agent_raw, a.agent_norm,
                       a.agent_confidence, a.agent_method,
                       a.role_raw, a.role_norm, a.authority_uri
                FROM agents a
                JOIN records r ON r.id = a.record_id
                WHERE a.agent_confidence <= 0.8
                  AND a.agent_raw IS NOT NULL
                  AND a.agent_raw != ''
                """
            ).fetchall()

            # Deduplicate by raw value, count frequency
            freq_map: Dict[str, AgentRecord] = {}
            freq_count: Dict[str, int] = {}
            for row in gap_rows:
                key = row[1]  # agent_raw
                if key not in freq_map:
                    freq_map[key] = AgentRecord(
                        mms_id=row[0],
                        agent_raw=row[1],
                        agent_norm=row[2],
                        confidence=row[3] if row[3] is not None else 0.0,
                        method=row[4] or "",
                        role_raw=row[5],
                        role_norm=row[6],
                        authority_uri=row[7],
                    )
                    freq_count[key] = 1
                else:
                    freq_count[key] += 1

            top_gaps = sorted(
                freq_map.values(),
                key=lambda g: freq_count[g.agent_raw],
                reverse=True,
            )[:20]

            # Build clusters from audit flagged items
            report = generate_coverage_report_from_conn(conn)
            clusters = cluster_field_gaps(
                field="agent",
                flagged_items=report.agent_name_coverage.flagged_items,
            )

            return AgentAnalysis(
                total_agents=total,
                with_authority=with_auth,
                without_authority=without_auth,
                low_confidence_count=low_conf,
                missing_role_count=missing_role,
                clusters=clusters,
                top_gaps=top_gaps,
            )
        finally:
            conn.close()

    def get_clusters(self) -> List[Cluster]:
        """Group low-confidence agent names into clusters for the dashboard.

        Returns clusters sorted by priority_score (highest first).
        """
        conn = self.harness.grounding._connect()
        try:
            report = generate_coverage_report_from_conn(conn)
            return cluster_field_gaps(
                field="agent",
                flagged_items=report.agent_name_coverage.flagged_items,
            )
        finally:
            conn.close()

    def propose_mappings(self, cluster: Cluster) -> List[ProposedMapping]:
        """LLM-assisted proposals for a cluster of agent name values.

        For each value in the cluster, asks the LLM for a canonical name form.
        """
        proposals: List[ProposedMapping] = []
        for value in cluster.values:
            evidence = {
                "field": "agent",
                "cluster_type": cluster.cluster_type,
                "frequency": value.frequency,
            }
            proposal = self.harness.reasoning.propose_mapping(
                raw_value=value.raw_value,
                field="agent",
                evidence=evidence,
            )
            proposals.append(proposal)
        return proposals

    def get_without_authority(self) -> List[AgentRecord]:
        """Agents missing authority URIs.

        Returns:
            List of AgentRecord where authority_uri is NULL or empty.
        """
        conn = self.harness.grounding._connect()
        try:
            rows = conn.execute(
                """
                SELECT r.mms_id, a.agent_raw, a.agent_norm,
                       a.agent_confidence, a.agent_method,
                       a.role_raw, a.role_norm, a.authority_uri
                FROM agents a
                JOIN records r ON r.id = a.record_id
                WHERE a.authority_uri IS NULL OR a.authority_uri = ''
                """
            ).fetchall()
            return [self._row_to_agent_record(row) for row in rows]
        finally:
            conn.close()

    def get_low_confidence(self, threshold: float = 0.8) -> List[AgentRecord]:
        """Agents with low confidence normalization.

        Args:
            threshold: Confidence threshold (exclusive). Default 0.8.

        Returns:
            List of AgentRecord where agent_confidence < threshold.
        """
        conn = self.harness.grounding._connect()
        try:
            rows = conn.execute(
                """
                SELECT r.mms_id, a.agent_raw, a.agent_norm,
                       a.agent_confidence, a.agent_method,
                       a.role_raw, a.role_norm, a.authority_uri
                FROM agents a
                JOIN records r ON r.id = a.record_id
                WHERE a.agent_confidence < ?
                """,
                (threshold,),
            ).fetchall()
            return [self._row_to_agent_record(row) for row in rows]
        finally:
            conn.close()

    def propose_authority_match(self, agent_raw: str) -> ProposedAuthority:
        """Suggest authority URI based on existing enrichment data.

        1. Check authority_enrichment table for existing matches
           (by comparing agent_raw against enrichment labels).
        2. If found, return with high confidence.
        3. If not found, use LLM to suggest a canonical name form.

        Args:
            agent_raw: Raw agent name string from MARC.

        Returns:
            ProposedAuthority with suggested URI and canonical name.
        """
        # Step 1: Search authority_enrichment for matching labels
        match = self._search_enrichment_by_name(agent_raw)
        if match is not None:
            return ProposedAuthority(
                agent_raw=agent_raw,
                suggested_uri=match.get("authority_uri"),
                canonical_name=match.get("label"),
                confidence=0.90,
                reasoning=(
                    f"Matched against authority_enrichment label "
                    f"'{match.get('label')}' via fuzzy name comparison"
                ),
                source=match.get("source", "authority_enrichment"),
            )

        # Step 2: Fall back to LLM proposal
        proposal = self.harness.reasoning.propose_mapping(
            raw_value=agent_raw,
            field="agent",
            evidence={
                "context": "name_authority_normalization",
                "request": "suggest canonical name form for authority matching",
            },
        )

        return ProposedAuthority(
            agent_raw=agent_raw,
            suggested_uri=None,
            canonical_name=proposal.canonical_value,
            confidence=proposal.confidence,
            reasoning=proposal.reasoning,
            source="llm",
        )

    def validate_against_authority(
        self, mms_ids: List[str]
    ) -> List[ValidationResult]:
        """Compare normalized names against authority canonical forms.

        For agents that HAVE authority URIs:
        1. Look up canonical name from authority_enrichment table.
        2. Compare agent_norm against authority canonical name.
        3. If they match: suggest confidence boost.
        4. If they diverge: flag for review (match=False).

        Args:
            mms_ids: List of MMS ID strings to validate.

        Returns:
            List of ValidationResult for agents with authority URIs.
        """
        if not mms_ids:
            return []

        conn = self.harness.grounding._connect()
        try:
            placeholders = ",".join("?" for _ in mms_ids)
            rows = conn.execute(
                f"""
                SELECT r.mms_id, a.agent_raw, a.agent_norm,
                       a.authority_uri, a.agent_confidence
                FROM agents a
                JOIN records r ON r.id = a.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND a.authority_uri IS NOT NULL
                  AND a.authority_uri != ''
                """,
                mms_ids,
            ).fetchall()

            results: List[ValidationResult] = []
            for row in rows:
                mms_id = row[0]
                agent_raw = row[1]
                agent_norm = row[2] or ""
                authority_uri = row[3]
                current_confidence = row[4] if row[4] is not None else 0.0

                # Look up canonical name from authority_enrichment
                canonical = self._get_authority_label(conn, authority_uri)

                if canonical is None:
                    # No enrichment data for this URI
                    results.append(
                        ValidationResult(
                            mms_id=mms_id,
                            agent_raw=agent_raw,
                            agent_norm=agent_norm,
                            authority_canonical=None,
                            match=False,
                            confidence_boost=None,
                        )
                    )
                    continue

                # Compare using fuzzy name matching
                match = names_match(agent_norm, canonical)

                # Suggest confidence boost if match
                confidence_boost: Optional[float] = None
                if match and current_confidence < 0.95:
                    confidence_boost = min(0.95, current_confidence + 0.10)

                results.append(
                    ValidationResult(
                        mms_id=mms_id,
                        agent_raw=agent_raw,
                        agent_norm=agent_norm,
                        authority_canonical=canonical,
                        match=match,
                        confidence_boost=confidence_boost,
                    )
                )

            return results
        finally:
            conn.close()

    # -- Private helpers ----------------------------------------------------

    @staticmethod
    def _row_to_agent_record(row) -> AgentRecord:
        """Convert a database row to AgentRecord.

        Args:
            row: SQLite row tuple with 8 columns.

        Returns:
            AgentRecord instance.
        """
        return AgentRecord(
            mms_id=row[0],
            agent_raw=row[1] or "",
            agent_norm=row[2],
            confidence=row[3] if row[3] is not None else 0.0,
            method=row[4] or "",
            role_raw=row[5],
            role_norm=row[6],
            authority_uri=row[7],
        )

    def _search_enrichment_by_name(
        self, agent_raw: str
    ) -> Optional[Dict[str, Any]]:
        """Search authority_enrichment table for a matching label.

        Uses fuzzy name matching (casefold, strip punctuation, reorder)
        to find enrichment entries whose label matches the raw agent name.

        Args:
            agent_raw: Raw agent name to search for.

        Returns:
            Dict with authority_uri, label, source if found, None otherwise.
        """
        conn = self.harness.grounding._connect()
        try:
            rows = conn.execute(
                """
                SELECT authority_uri, label, source
                FROM authority_enrichment
                WHERE label IS NOT NULL AND label != ''
                """
            ).fetchall()

            for row in rows:
                authority_uri = row[0]
                label = row[1]
                source = row[2]

                if names_match(agent_raw, label):
                    return {
                        "authority_uri": authority_uri,
                        "label": label,
                        "source": source,
                    }

            return None
        finally:
            conn.close()

    @staticmethod
    def _get_authority_label(
        conn: sqlite3.Connection, authority_uri: str
    ) -> Optional[str]:
        """Look up the canonical label for an authority URI.

        Args:
            conn: Open database connection.
            authority_uri: Authority URI to look up.

        Returns:
            Label string if found, None otherwise.
        """
        row = conn.execute(
            "SELECT label FROM authority_enrichment WHERE authority_uri = ?",
            (authority_uri,),
        ).fetchone()
        if row and row[0]:
            return row[0]
        return None
