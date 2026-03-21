"""Gap clustering for low-confidence/unmapped bibliographic metadata values.

Takes flagged items from the audit module and clusters them into actionable
groups that a librarian can review as batches. All clustering is deterministic
(no LLM calls) using heuristic rules.
"""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.metadata.audit import CoverageReport, LowConfidenceItem


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ClusterValue:
    """A single value within a cluster."""

    raw_value: str
    frequency: int
    confidence: float
    method: str


@dataclass
class Cluster:
    """A group of related low-confidence values."""

    cluster_id: str
    field: str  # "date", "place", "publisher", "agent"
    cluster_type: str  # e.g., "latin_place_names", "hebrew_dates"
    values: List[ClusterValue]
    proposed_canonical: Optional[str]  # if determinable without LLM
    evidence: Dict[str, Any]  # country codes, pattern info, etc.
    priority_score: float  # sum of frequency across all values
    total_records_affected: int


# ---------------------------------------------------------------------------
# Script detection
# ---------------------------------------------------------------------------

# Unicode block ranges for script detection
_HEBREW_RANGE = (0x0590, 0x05FF)
_ARABIC_RANGE = (0x0600, 0x06FF)
_ARABIC_SUPPLEMENT = (0x0750, 0x077F)
_ARABIC_EXTENDED_A = (0x08A0, 0x08FF)


def detect_script(text: str) -> str:
    """Detect the primary script of a text string.

    Uses Unicode block detection to classify text as one of:
    - "hebrew": Contains Hebrew Unicode characters
    - "arabic": Contains Arabic Unicode characters
    - "latin": Contains Latin characters (default)
    - "empty": Empty or whitespace-only input

    Args:
        text: Input string to analyze.

    Returns:
        Script label string.
    """
    if not text or not text.strip():
        return "empty"

    hebrew_count = 0
    arabic_count = 0
    latin_count = 0

    for ch in text:
        cp = ord(ch)
        if _HEBREW_RANGE[0] <= cp <= _HEBREW_RANGE[1]:
            hebrew_count += 1
        elif (_ARABIC_RANGE[0] <= cp <= _ARABIC_RANGE[1]
              or _ARABIC_SUPPLEMENT[0] <= cp <= _ARABIC_SUPPLEMENT[1]
              or _ARABIC_EXTENDED_A[0] <= cp <= _ARABIC_EXTENDED_A[1]):
            arabic_count += 1
        elif ch.isalpha():
            latin_count += 1

    total = hebrew_count + arabic_count + latin_count
    if total == 0:
        return "empty"

    if hebrew_count > arabic_count and hebrew_count > latin_count:
        return "hebrew"
    if arabic_count > hebrew_count and arabic_count > latin_count:
        return "arabic"
    return "latin"


# ---------------------------------------------------------------------------
# Date pattern detection
# ---------------------------------------------------------------------------

# Compiled patterns for date classification
_DATE_PATTERN_PARTIAL_CENTURY = re.compile(r"\[?\d{2}[-–]{2}\??\]?")
_DATE_PATTERN_HEBREW_GEMATRIA = re.compile(
    r"[\u0590-\u05FF\"\']+"  # Hebrew letters with geresh/gershayim
)
_DATE_PATTERN_LATIN_CONVENTION = re.compile(
    r"(?:anno|a\.d\.|m\.?d\.?c|mdcc|mdccc|mdxc|an\.|idib)",
    re.IGNORECASE,
)
_DATE_PATTERN_AMBIGUOUS_RANGE = re.compile(
    r"\d{3,4}\s*[-–/]\s*\d{1,4}"
)
_DATE_PATTERN_CIRCA = re.compile(r"(?:ca?\.\s*|circa\s+)\d{3,4}", re.IGNORECASE)


def classify_date_pattern(raw_value: str) -> str:
    """Classify a raw date string into a pattern type.

    Pattern types:
    - "partial_century": e.g., "[17--?]", "18--"
    - "hebrew_gematria": Contains Hebrew letter numerals
    - "latin_convention": e.g., "Anno Domini MDCCC"
    - "ambiguous_range": e.g., "1500-99", "1650/1660"
    - "circa": e.g., "ca. 1650", "circa 1700"
    - "empty_missing": Empty, whitespace, or None-equivalent
    - "other_unparsed": Does not match any known pattern

    Args:
        raw_value: The raw date string from MARC data.

    Returns:
        Pattern type label.
    """
    stripped = raw_value.strip() if raw_value else ""
    if not stripped:
        return "empty_missing"

    if _DATE_PATTERN_PARTIAL_CENTURY.search(stripped):
        return "partial_century"

    if _DATE_PATTERN_HEBREW_GEMATRIA.search(stripped):
        # Ensure it's mostly Hebrew, not just a stray character
        hebrew_chars = sum(1 for c in stripped if 0x0590 <= ord(c) <= 0x05FF)
        if hebrew_chars >= 2:
            return "hebrew_gematria"

    if _DATE_PATTERN_LATIN_CONVENTION.search(stripped):
        return "latin_convention"

    if _DATE_PATTERN_CIRCA.search(stripped):
        return "circa"

    if _DATE_PATTERN_AMBIGUOUS_RANGE.search(stripped):
        return "ambiguous_range"

    return "other_unparsed"


# ---------------------------------------------------------------------------
# Text normalization helpers
# ---------------------------------------------------------------------------

def _normalize_for_matching(text: str) -> str:
    """Normalize text for fuzzy matching.

    Strips punctuation, brackets, casefolding, and collapses whitespace.

    Args:
        text: Input string.

    Returns:
        Normalized string for comparison.
    """
    if not text:
        return ""
    # Casefold for case-insensitive comparison
    result = text.casefold()
    # Remove brackets and common MARC punctuation
    result = re.sub(r"[\[\](){}<>]", "", result)
    # Remove trailing/leading punctuation like : , ; .
    result = result.strip(" \t\n\r:,;./")
    # Collapse whitespace
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _find_near_matches(
    value: str,
    alias_map: Dict[str, str],
    threshold: float = 0.85,
) -> Optional[str]:
    """Find near-matches for a value in an alias map.

    Uses normalized string comparison. Returns the canonical form
    if a close match is found.

    Args:
        value: Raw value to match.
        alias_map: Mapping of raw aliases to canonical forms.
        threshold: Not used for exact-after-normalization matching,
                   but reserved for future fuzzy ratio matching.

    Returns:
        Canonical value if a near-match is found, None otherwise.
    """
    norm_value = _normalize_for_matching(value)
    if not norm_value:
        return None

    # Direct normalized match against alias map keys
    for alias_key, canonical in alias_map.items():
        if _normalize_for_matching(alias_key) == norm_value:
            return canonical

    # Try matching against canonical values
    for canonical in set(alias_map.values()):
        if _normalize_for_matching(canonical) == norm_value:
            return canonical

    return None


# ---------------------------------------------------------------------------
# Place clustering
# ---------------------------------------------------------------------------

def _cluster_places(
    items: List[LowConfidenceItem],
    alias_map: Optional[Dict[str, str]] = None,
) -> List[Cluster]:
    """Cluster place gaps by script, near-match status, and frequency.

    Strategies:
    1. Group by script type (Latin, Hebrew, Arabic)
    2. Identify near-matches against existing alias map
    3. Sort by frequency within each group

    Args:
        items: Flagged place items from audit.
        alias_map: Optional place alias map for near-match detection.

    Returns:
        List of Cluster objects for places.
    """
    if not items:
        return []

    alias_map = alias_map or {}

    # Group by script
    script_groups: Dict[str, List[LowConfidenceItem]] = defaultdict(list)
    near_match_items: List[Tuple[LowConfidenceItem, str]] = []

    for item in items:
        # Check for near-match first
        near = _find_near_matches(item.raw_value, alias_map) if alias_map else None
        if near:
            near_match_items.append((item, near))
        else:
            script = detect_script(item.raw_value)
            script_groups[script].append(item)

    clusters: List[Cluster] = []

    # Near-match cluster (highest priority -- easy wins)
    if near_match_items:
        values = [
            ClusterValue(
                raw_value=item.raw_value,
                frequency=item.frequency,
                confidence=item.confidence,
                method=item.method or "",
            )
            for item, _ in near_match_items
        ]
        total_affected = sum(v.frequency for v in values)
        clusters.append(Cluster(
            cluster_id="place_near_match",
            field="place",
            cluster_type="near_match",
            values=sorted(values, key=lambda v: v.frequency, reverse=True),
            proposed_canonical=None,
            evidence={
                "proposed_mappings": {
                    item.raw_value: canonical
                    for item, canonical in near_match_items
                },
            },
            priority_score=float(total_affected),
            total_records_affected=total_affected,
        ))

    # Script-based clusters
    script_labels = {
        "hebrew": "hebrew_place_names",
        "arabic": "arabic_place_names",
        "latin": "latin_place_names",
        "empty": "empty_place_values",
    }

    for script_key, label in script_labels.items():
        group = script_groups.get(script_key, [])
        if not group:
            continue

        values = [
            ClusterValue(
                raw_value=item.raw_value,
                frequency=item.frequency,
                confidence=item.confidence,
                method=item.method or "",
            )
            for item in group
        ]
        total_affected = sum(v.frequency for v in values)
        clusters.append(Cluster(
            cluster_id=f"place_{script_key}",
            field="place",
            cluster_type=label,
            values=sorted(values, key=lambda v: v.frequency, reverse=True),
            proposed_canonical=None,
            evidence={"script": script_key, "count": len(values)},
            priority_score=float(total_affected),
            total_records_affected=total_affected,
        ))

    return sorted(clusters, key=lambda c: c.priority_score, reverse=True)


# ---------------------------------------------------------------------------
# Date clustering
# ---------------------------------------------------------------------------

def _cluster_dates(items: List[LowConfidenceItem]) -> List[Cluster]:
    """Cluster date gaps by pattern type.

    Groups unparsed dates into pattern-based clusters for batch review.

    Args:
        items: Flagged date items from audit.

    Returns:
        List of Cluster objects for dates.
    """
    if not items:
        return []

    pattern_groups: Dict[str, List[LowConfidenceItem]] = defaultdict(list)
    for item in items:
        pattern = classify_date_pattern(item.raw_value)
        pattern_groups[pattern].append(item)

    clusters: List[Cluster] = []
    for pattern_type, group in pattern_groups.items():
        values = [
            ClusterValue(
                raw_value=item.raw_value,
                frequency=item.frequency,
                confidence=item.confidence,
                method=item.method or "",
            )
            for item in group
        ]
        total_affected = sum(v.frequency for v in values)
        clusters.append(Cluster(
            cluster_id=f"date_{pattern_type}",
            field="date",
            cluster_type=pattern_type,
            values=sorted(values, key=lambda v: v.frequency, reverse=True),
            proposed_canonical=None,
            evidence={
                "pattern": pattern_type,
                "distinct_values": len(values),
            },
            priority_score=float(total_affected),
            total_records_affected=total_affected,
        ))

    return sorted(clusters, key=lambda c: c.priority_score, reverse=True)


# ---------------------------------------------------------------------------
# Publisher clustering
# ---------------------------------------------------------------------------

def _cluster_publishers(
    items: List[LowConfidenceItem],
    alias_map: Optional[Dict[str, str]] = None,
) -> List[Cluster]:
    """Cluster publisher gaps by normalized base form and frequency.

    Strategies:
    1. Group variants that normalize to the same base form
    2. Detect near-matches against an optional alias map
    3. Rank clusters by total frequency

    Args:
        items: Flagged publisher items from audit.
        alias_map: Optional publisher alias map for near-match detection.

    Returns:
        List of Cluster objects for publishers.
    """
    if not items:
        return []

    alias_map = alias_map or {}

    # Group by normalized base form
    base_form_groups: Dict[str, List[LowConfidenceItem]] = defaultdict(list)
    near_match_items: List[Tuple[LowConfidenceItem, str]] = []

    for item in items:
        near = _find_near_matches(item.raw_value, alias_map) if alias_map else None
        if near:
            near_match_items.append((item, near))
        else:
            base = _normalize_for_matching(item.raw_value)
            if base:
                base_form_groups[base].append(item)
            else:
                base_form_groups["__empty__"].append(item)

    clusters: List[Cluster] = []

    # Near-match cluster
    if near_match_items:
        values = [
            ClusterValue(
                raw_value=item.raw_value,
                frequency=item.frequency,
                confidence=item.confidence,
                method=item.method or "",
            )
            for item, _ in near_match_items
        ]
        total_affected = sum(v.frequency for v in values)
        clusters.append(Cluster(
            cluster_id="publisher_near_match",
            field="publisher",
            cluster_type="near_match",
            values=sorted(values, key=lambda v: v.frequency, reverse=True),
            proposed_canonical=None,
            evidence={
                "proposed_mappings": {
                    item.raw_value: canonical
                    for item, canonical in near_match_items
                },
            },
            priority_score=float(total_affected),
            total_records_affected=total_affected,
        ))

    # Variant clusters (multiple raw forms -> same base)
    for base_form, group in base_form_groups.items():
        if len(group) > 1:
            values = [
                ClusterValue(
                    raw_value=item.raw_value,
                    frequency=item.frequency,
                    confidence=item.confidence,
                    method=item.method or "",
                )
                for item in group
            ]
            total_affected = sum(v.frequency for v in values)
            clusters.append(Cluster(
                cluster_id=f"publisher_variant_{base_form[:40]}",
                field="publisher",
                cluster_type="variant_group",
                values=sorted(values, key=lambda v: v.frequency, reverse=True),
                proposed_canonical=base_form,
                evidence={
                    "base_form": base_form,
                    "variant_count": len(values),
                },
                priority_score=float(total_affected),
                total_records_affected=total_affected,
            ))

    # Singleton items grouped by frequency tier
    singletons = [
        item for base, group in base_form_groups.items()
        if len(group) == 1
        for item in group
    ]

    if singletons:
        # Split into high-frequency (>=5) and low-frequency (<5)
        high_freq = [i for i in singletons if i.frequency >= 5]
        low_freq = [i for i in singletons if i.frequency < 5]

        if high_freq:
            values = [
                ClusterValue(
                    raw_value=item.raw_value,
                    frequency=item.frequency,
                    confidence=item.confidence,
                    method=item.method or "",
                )
                for item in high_freq
            ]
            total_affected = sum(v.frequency for v in values)
            clusters.append(Cluster(
                cluster_id="publisher_high_freq_unmapped",
                field="publisher",
                cluster_type="high_frequency_unmapped",
                values=sorted(values, key=lambda v: v.frequency, reverse=True),
                proposed_canonical=None,
                evidence={"frequency_threshold": 5},
                priority_score=float(total_affected),
                total_records_affected=total_affected,
            ))

        if low_freq:
            values = [
                ClusterValue(
                    raw_value=item.raw_value,
                    frequency=item.frequency,
                    confidence=item.confidence,
                    method=item.method or "",
                )
                for item in low_freq
            ]
            total_affected = sum(v.frequency for v in values)
            clusters.append(Cluster(
                cluster_id="publisher_low_freq_unmapped",
                field="publisher",
                cluster_type="low_frequency_unmapped",
                values=sorted(values, key=lambda v: v.frequency, reverse=True),
                proposed_canonical=None,
                evidence={"frequency_threshold": "below_5"},
                priority_score=float(total_affected),
                total_records_affected=total_affected,
            ))

    return sorted(clusters, key=lambda c: c.priority_score, reverse=True)


# ---------------------------------------------------------------------------
# Agent clustering
# ---------------------------------------------------------------------------

def _cluster_agents(items: List[LowConfidenceItem]) -> List[Cluster]:
    """Cluster agent gaps by role presence, authority URI, and confidence.

    Strategies:
    1. Group by: has authority context vs. missing
    2. Group by: missing role vs. has role
    3. Group by confidence band

    Args:
        items: Flagged agent items from audit.

    Returns:
        List of Cluster objects for agents.
    """
    if not items:
        return []

    # Classify each item
    missing_role: List[LowConfidenceItem] = []
    low_confidence: List[LowConfidenceItem] = []
    ambiguous: List[LowConfidenceItem] = []

    for item in items:
        method = (item.method or "").lower()
        if method == "ambiguous" or "ambig" in method:
            ambiguous.append(item)
        elif item.confidence < 0.5:
            missing_role.append(item)
        else:
            low_confidence.append(item)

    clusters: List[Cluster] = []

    if ambiguous:
        values = [
            ClusterValue(
                raw_value=item.raw_value,
                frequency=item.frequency,
                confidence=item.confidence,
                method=item.method or "",
            )
            for item in ambiguous
        ]
        total_affected = sum(v.frequency for v in values)
        clusters.append(Cluster(
            cluster_id="agent_ambiguous",
            field="agent",
            cluster_type="ambiguous_agent",
            values=sorted(values, key=lambda v: v.frequency, reverse=True),
            proposed_canonical=None,
            evidence={"reason": "ambiguous method tag"},
            priority_score=float(total_affected),
            total_records_affected=total_affected,
        ))

    if missing_role:
        values = [
            ClusterValue(
                raw_value=item.raw_value,
                frequency=item.frequency,
                confidence=item.confidence,
                method=item.method or "",
            )
            for item in missing_role
        ]
        total_affected = sum(v.frequency for v in values)
        clusters.append(Cluster(
            cluster_id="agent_missing_role",
            field="agent",
            cluster_type="missing_role",
            values=sorted(values, key=lambda v: v.frequency, reverse=True),
            proposed_canonical=None,
            evidence={"reason": "confidence below 0.50"},
            priority_score=float(total_affected),
            total_records_affected=total_affected,
        ))

    if low_confidence:
        values = [
            ClusterValue(
                raw_value=item.raw_value,
                frequency=item.frequency,
                confidence=item.confidence,
                method=item.method or "",
            )
            for item in low_confidence
        ]
        total_affected = sum(v.frequency for v in values)
        clusters.append(Cluster(
            cluster_id="agent_low_confidence",
            field="agent",
            cluster_type="low_confidence_agent",
            values=sorted(values, key=lambda v: v.frequency, reverse=True),
            proposed_canonical=None,
            evidence={"reason": "confidence between 0.50 and 0.80"},
            priority_score=float(total_affected),
            total_records_affected=total_affected,
        ))

    return sorted(clusters, key=lambda c: c.priority_score, reverse=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def cluster_field_gaps(
    field: str,
    flagged_items: List[LowConfidenceItem],
    db_path: Optional[Path] = None,
    alias_map: Optional[Dict[str, str]] = None,
) -> List[Cluster]:
    """Cluster gaps for a single field.

    Routes to the appropriate field-specific clustering strategy.

    Args:
        field: One of "date", "place", "publisher", "agent".
        flagged_items: Low-confidence items from the audit report.
        db_path: Optional path to SQLite database (reserved for future use).
        alias_map: Optional alias map for near-match detection.

    Returns:
        List of Cluster objects sorted by priority (descending).

    Raises:
        ValueError: If field is not recognized.
    """
    dispatchers = {
        "place": lambda: _cluster_places(flagged_items, alias_map),
        "date": lambda: _cluster_dates(flagged_items),
        "publisher": lambda: _cluster_publishers(flagged_items, alias_map),
        "agent": lambda: _cluster_agents(flagged_items),
    }

    if field not in dispatchers:
        raise ValueError(
            f"Unknown field: {field!r}. Must be one of: {list(dispatchers.keys())}"
        )

    return dispatchers[field]()


def cluster_all_gaps(
    report: CoverageReport,
    db_path: Optional[Path] = None,
    alias_maps: Optional[Dict[str, Dict]] = None,
) -> Dict[str, List[Cluster]]:
    """Cluster gaps across all fields in a coverage report.

    Args:
        report: CoverageReport from the audit module.
        db_path: Optional path to SQLite database.
        alias_maps: Optional dict of {field: alias_map} for near-match detection.
                    Keys can be "place", "publisher".

    Returns:
        Dictionary mapping field name to list of clusters, e.g.,
        {"date": [...], "place": [...], "publisher": [...], "agent": [...]}.
    """
    alias_maps = alias_maps or {}

    field_items = {
        "date": report.date_coverage.flagged_items,
        "place": report.place_coverage.flagged_items,
        "publisher": report.publisher_coverage.flagged_items,
        "agent": (
            report.agent_name_coverage.flagged_items
            + report.agent_role_coverage.flagged_items
        ),
    }

    results: Dict[str, List[Cluster]] = {}
    for field_name, items in field_items.items():
        results[field_name] = cluster_field_gaps(
            field=field_name,
            flagged_items=items,
            db_path=db_path,
            alias_map=alias_maps.get(field_name),
        )

    return results
