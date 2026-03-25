"""PlaceAgent: Specialist agent for place normalization.

Handles Latin toponyms (genitive/nominative/ablative forms), Hebrew/Arabic
place names, historical name changes, and MARC country code cross-referencing.

Delegates all DB queries to the AgentHarness.grounding layer and all LLM
calls to the AgentHarness.reasoning layer. Adds place-specific logic on top.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from scripts.metadata.agent_harness import AgentHarness, GapRecord, ProposedMapping
from scripts.metadata.audit import (
    generate_coverage_report_from_conn,
)
from scripts.metadata.clustering import Cluster, cluster_field_gaps


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class PlaceAnalysis:
    """Full coverage analysis for place normalization."""

    total_places: int
    high_confidence_count: int  # >= 0.95
    medium_confidence_count: int  # 0.80 - 0.95
    low_confidence_count: int  # < 0.80
    unmapped_count: int  # confidence <= 0.80 without alias map hit
    clusters: List[Cluster]
    top_gaps: List[GapRecord]  # Top 20 by frequency


# ---------------------------------------------------------------------------
# PlaceAgent
# ---------------------------------------------------------------------------


class PlaceAgent:
    """Specialist agent for place normalization.

    Knows Latin toponyms, Hebrew place names, historical place name changes,
    and MARC country code cross-referencing.
    """

    def __init__(self, harness: AgentHarness):
        """Initialize with an AgentHarness instance.

        Args:
            harness: AgentHarness providing grounding and reasoning layers.
        """
        self.harness = harness
        self._country_codes: Optional[Dict[str, str]] = None

    # -- Public API ---------------------------------------------------------

    def analyze(self) -> PlaceAnalysis:
        """Run full coverage analysis for places.

        Queries the M3 database for place confidence distributions, builds
        clusters of unmapped/low-confidence values, and returns a structured
        PlaceAnalysis.

        Returns:
            PlaceAnalysis with coverage stats, clusters, and top gaps.
        """
        conn = self.harness.grounding._connect()
        try:
            report = generate_coverage_report_from_conn(conn)
            place_cov = report.place_coverage

            # Count by confidence band
            high = 0
            medium = 0
            low = 0
            for band in place_cov.confidence_distribution:
                if band.lower >= 0.95:
                    high += band.count
                elif band.lower >= 0.80:
                    medium += band.count
                else:
                    low += band.count

            # Build clusters from flagged items
            alias_map = self.harness.grounding.query_alias_map("place")
            clusters = cluster_field_gaps(
                field="place",
                flagged_items=place_cov.flagged_items,
                alias_map=alias_map,
            )

            # Top gaps by frequency (from grounding layer)
            gaps = self.harness.grounding.query_gaps("place", max_confidence=0.80)
            # Deduplicate by raw_value and sum frequencies
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

            # Unmapped count: items with confidence <= 0.80
            unmapped = sum(
                item.frequency
                for item in place_cov.flagged_items
            )

            return PlaceAnalysis(
                total_places=place_cov.total_records,
                high_confidence_count=high,
                medium_confidence_count=medium,
                low_confidence_count=low,
                unmapped_count=unmapped,
                clusters=clusters,
                top_gaps=top_gaps,
            )
        finally:
            conn.close()

    def get_clusters(self) -> List[Cluster]:
        """Group unmapped places by type (Latin, Hebrew, near-match, etc.).

        Returns:
            Clusters sorted by priority_score (highest first).
        """
        conn = self.harness.grounding._connect()
        try:
            report = generate_coverage_report_from_conn(conn)
            flagged = report.place_coverage.flagged_items
        finally:
            conn.close()

        alias_map = self.harness.grounding.query_alias_map("place")
        clusters = cluster_field_gaps(
            field="place",
            flagged_items=flagged,
            alias_map=alias_map,
        )
        return sorted(clusters, key=lambda c: c.priority_score, reverse=True)

    def propose_mappings(self, cluster: Cluster) -> List[ProposedMapping]:
        """LLM-assisted proposals for a cluster of related places.

        For each value in the cluster:
        1. Gather evidence (country codes, existing alias map near-matches)
        2. Ask LLM for canonical mapping via harness.reasoning.propose_mapping()
        3. Include evidence_sources in the proposal

        Args:
            cluster: A Cluster of place values to propose mappings for.

        Returns:
            List of ProposedMapping with canonical values and reasoning.
        """
        proposals: List[ProposedMapping] = []

        for value in cluster.values:
            # Gather country codes for records with this raw value
            country_codes = self._get_country_codes_for_value(value.raw_value)

            # Build evidence dict
            evidence: Dict[str, Any] = {
                "field": "place",
                "cluster_type": cluster.cluster_type,
                "country_codes": country_codes,
                "frequency": value.frequency,
            }

            # Add near-match info from cluster evidence if available
            if cluster.evidence and "proposed_mappings" in cluster.evidence:
                proposed = cluster.evidence["proposed_mappings"]
                if value.raw_value in proposed:
                    evidence["near_match_candidate"] = proposed[value.raw_value]

            proposal = self.harness.reasoning.propose_mapping(
                raw_value=value.raw_value,
                field="place",
                evidence=evidence,
            )
            proposals.append(proposal)

        return proposals

    def get_primo_links(self, raw_value: str) -> List[str]:
        """Generate Primo links for records with this place value.

        Queries DB for MMS IDs where place_raw matches, then generates
        Primo URLs using the standard TAU Primo URL pattern.

        Args:
            raw_value: The raw place value to look up.

        Returns:
            List of Primo URL strings for matching records.
        """
        mms_ids = self._query_mms_ids_for_place(raw_value)
        return [_build_primo_url(mms_id) for mms_id in mms_ids]

    def get_country_codes_map(self) -> Dict[str, str]:
        """Load MARC country codes reference.

        Loads from data/normalization/marc_country_codes.json if it exists.
        Caches the result for subsequent calls.

        Returns:
            Dict mapping MARC country code -> country name.
        """
        if self._country_codes is not None:
            return self._country_codes

        cc_path = (
            self.harness.grounding.alias_map_dir / "marc_country_codes.json"
        )
        if not cc_path.exists():
            self._country_codes = {}
            return self._country_codes

        with open(cc_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # The file has a "codes" key containing the actual mapping
        if isinstance(data, dict) and "codes" in data:
            self._country_codes = data["codes"]
        elif isinstance(data, dict):
            # Fallback: treat the whole dict as code->name
            self._country_codes = {
                k: v for k, v in data.items() if k != "comment" and k != "source" and k != "last_updated"
            }
        else:
            self._country_codes = {}

        return self._country_codes

    def cross_reference_country_code(
        self, raw_value: str, country_code: str
    ) -> Optional[str]:
        """Cross-reference a place value against its MARC country code.

        Looks up the country code in the MARC country codes reference to
        provide additional evidence for place normalization.

        Args:
            raw_value: The raw place string.
            country_code: The MARC country code (e.g., "fr" for France).

        Returns:
            Country name if code is found, None otherwise.
        """
        codes_map = self.get_country_codes_map()
        code_clean = country_code.strip().lower() if country_code else ""
        return codes_map.get(code_clean)

    # -- Private helpers ----------------------------------------------------

    def _get_country_codes_for_value(
        self, raw_value: str
    ) -> List[str]:
        """Get unique country codes for records containing this place value.

        Args:
            raw_value: The raw place string.

        Returns:
            List of unique country code strings.
        """
        conn = self.harness.grounding._connect()
        try:
            rows = conn.execute(
                """SELECT DISTINCT i.country_code
                   FROM imprints i
                   WHERE i.place_raw = ?
                     AND i.country_code IS NOT NULL
                     AND i.country_code != ''
                """,
                (raw_value,),
            ).fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    def _query_mms_ids_for_place(self, raw_value: str) -> List[str]:
        """Query MMS IDs for records with this place_raw value.

        Args:
            raw_value: The raw place string.

        Returns:
            List of MMS ID strings.
        """
        conn = self.harness.grounding._connect()
        try:
            rows = conn.execute(
                """SELECT DISTINCT r.mms_id
                   FROM imprints i
                   JOIN records r ON r.id = i.record_id
                   WHERE i.place_raw = ?
                """,
                (raw_value,),
            ).fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Primo URL builder (standalone)
# ---------------------------------------------------------------------------

_PRIMO_BASE_URL = "https://tau.primo.exlibrisgroup.com/nde/fulldisplay"
_PRIMO_VID = "972TAU_INST:NDE"
_PRIMO_TAB = "TAU"
_PRIMO_SEARCH_SCOPE = "TAU"


def _build_primo_url(mms_id: str) -> str:
    """Generate a Primo URL for a given MMS ID.

    Uses the standard TAU Primo URL pattern.

    Args:
        mms_id: The MMS ID (e.g., "990009748710204146").

    Returns:
        Full Primo URL string.
    """
    from urllib.parse import quote

    params = {
        "query": f"{mms_id} ",
        "tab": _PRIMO_TAB,
        "search_scope": _PRIMO_SEARCH_SCOPE,
        "searchInFulltext": "true",
        "vid": _PRIMO_VID,
        "docid": f"alma{mms_id}",
        "adaptor": "Local Search Engine",
        "context": "L",
        "isFrbr": "false",
        "isHighlightedRecord": "false",
        "state": "",
    }
    query_parts = [
        f"{key}={quote(str(value), safe='')}" for key, value in params.items()
    ]
    return f"{_PRIMO_BASE_URL}?{'&'.join(query_parts)}"
