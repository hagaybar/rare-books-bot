"""M2 normalization functions.

Deterministic, rule-based normalization for dates, places, publishers, and agents.
No LLM calls. No web calls. All normalization is reversible and confidence-scored.
"""

import re
import unicodedata
from typing import Optional, Dict, List, Tuple

from .m2_models import (
    DateNormalization, PlaceNormalization, PublisherNormalization,
    ImprintNormalization, M2Enrichment, AgentNormalization, RoleNormalization
)
from scripts.normalization.normalize_agent import (
    normalize_agent_with_alias_map, normalize_role_base
)


def normalize_date(raw: Optional[str], evidence_path: str) -> DateNormalization:
    r"""Normalize publication date using deterministic rules.

    Args:
        raw: Raw date string from M1 record
        evidence_path: JSON path to evidence (e.g., "imprints[0].date.value")

    Returns:
        DateNormalization with start/end years, confidence, and method

    Rules (applied in order):
        1. Exact year: ^\d{4}$ → confidence=0.99
        2. Bracketed year: ^\[(\d{4})\]$ → confidence=0.95
        3. Circa: ^c\.?\s*(\d{4})$ → ±5 years, confidence=0.80
        4. Range: ^(\d{4})\s*[-/]\s*(\d{4})$ → confidence=0.90
        5. Embedded: first \d{4} anywhere → confidence=0.85 + warning
        6. Unparsed: null values, confidence=0.0 + warning
    """
    if not raw:
        return DateNormalization(
            start=None,
            end=None,
            label="",
            confidence=0.0,
            method="missing",
            evidence_paths=[evidence_path],
            warnings=["date_missing"]
        )

    raw_stripped = raw.strip()

    # Rule 1: Exact year (e.g., "1680")
    match = re.match(r'^(\d{4})$', raw_stripped)
    if match:
        year = int(match.group(1))
        return DateNormalization(
            start=year,
            end=year,
            label=str(year),
            confidence=0.99,
            method="year_exact",
            evidence_paths=[evidence_path],
            warnings=[]
        )

    # Rule 2: Bracketed year (e.g., "[1680]")
    match = re.match(r'^\[(\d{4})\]$', raw_stripped)
    if match:
        year = int(match.group(1))
        return DateNormalization(
            start=year,
            end=year,
            label=f"[{year}]",
            confidence=0.95,
            method="year_bracketed",
            evidence_paths=[evidence_path],
            warnings=[]
        )

    # Rule 3: Circa (e.g., "c1680", "c. 1680", "c.1680")
    match = re.match(r'^c\.?\s*(\d{4})$', raw_stripped, re.IGNORECASE)
    if match:
        year = int(match.group(1))
        return DateNormalization(
            start=year - 5,
            end=year + 5,
            label=f"c. {year}",
            confidence=0.80,
            method="year_circa_pm5",
            evidence_paths=[evidence_path],
            warnings=[]
        )

    # Rule 4: Range (e.g., "1680-1685", "1680/1685")
    match = re.match(r'^(\d{4})\s*[-/]\s*(\d{4})$', raw_stripped)
    if match:
        start_year = int(match.group(1))
        end_year = int(match.group(2))
        return DateNormalization(
            start=start_year,
            end=end_year,
            label=f"{start_year}-{end_year}",
            confidence=0.90,
            method="year_range",
            evidence_paths=[evidence_path],
            warnings=[]
        )

    # Rule 5: Bracketed Gregorian equivalent (Hebrew calendar dates)
    # Patterns like: "5850 [1846]", "año 5493 [1732]", "5500 [i.e. 1740]"
    # Look for [YYYY] or [i.e. YYYY] patterns - these are Gregorian equivalents
    match = re.search(r'\[(?:i\.?e\.?\s*)?(\d{4})\]', raw_stripped)
    if match:
        year = int(match.group(1))
        # Validate it's a reasonable Gregorian year (not another Hebrew date in brackets)
        if 1000 <= year <= 2100:
            return DateNormalization(
                start=year,
                end=year,
                label=str(year),
                confidence=0.90,
                method="year_bracketed_gregorian",
                evidence_paths=[evidence_path],
                warnings=["hebrew_calendar_date_converted"]
            )

    # Rule 6: Embedded year (find first \d{4} anywhere)
    # Only use years in reasonable Gregorian range to avoid Hebrew calendar dates
    for match in re.finditer(r'(\d{4})', raw_stripped):
        year = int(match.group(1))
        # Skip Hebrew calendar years (typically 5000+) and future dates
        if 1000 <= year <= 2100:
            return DateNormalization(
                start=year,
                end=year,
                label=str(year),
                confidence=0.85,
                method="year_embedded",
                evidence_paths=[evidence_path],
                warnings=["embedded_year_in_complex_string"]
            )

    # Rule 6b: If only Hebrew calendar year found, try to convert it
    match = re.search(r'(\d{4})', raw_stripped)
    if match:
        year = int(match.group(1))
        # Hebrew calendar years are typically 5000+ (Hebrew year = Gregorian + 3760)
        if year >= 5000:
            gregorian_year = year - 3760
            if 1000 <= gregorian_year <= 2100:
                return DateNormalization(
                    start=gregorian_year,
                    end=gregorian_year,
                    label=str(gregorian_year),
                    confidence=0.75,
                    method="hebrew_calendar_converted",
                    evidence_paths=[evidence_path],
                    warnings=["hebrew_calendar_date_auto_converted"]
                )

    # Rule 7: Unparsed
    return DateNormalization(
        start=None,
        end=None,
        label=raw_stripped,
        confidence=0.0,
        method="unparsed",
        evidence_paths=[evidence_path],
        warnings=["date_unparsed"]
    )


def _clean_place_publisher(raw: Optional[str]) -> tuple[Optional[str], str]:
    """Clean place/publisher string for normalization.

    Args:
        raw: Raw place or publisher string

    Returns:
        Tuple of (cleaned_for_norm, cleaned_for_display)

    Cleaning steps:
        1. Trim whitespace
        2. Strip trailing punctuation (: , ; /)
        3. Remove surrounding brackets []
        4. Unicode normalize (NFKC)
    """
    if not raw:
        return None, ""

    # Trim whitespace
    cleaned = raw.strip()

    # Strip trailing punctuation
    cleaned = cleaned.rstrip(':,;/')

    # Strip whitespace again after punctuation removal
    cleaned = cleaned.strip()

    # Remove surrounding brackets
    if cleaned.startswith('[') and cleaned.endswith(']'):
        cleaned = cleaned[1:-1].strip()

    # Unicode normalize (NFKC)
    cleaned = unicodedata.normalize('NFKC', cleaned)

    return cleaned, cleaned


def normalize_place(
    raw: Optional[str],
    evidence_path: str,
    alias_map: Optional[Dict[str, str]] = None
) -> PlaceNormalization:
    """Normalize publication place.

    Args:
        raw: Raw place string from M1 record
        evidence_path: JSON path to evidence (e.g., "imprints[0].place.value")
        alias_map: Optional mapping of normalized keys to canonical forms

    Returns:
        PlaceNormalization with normalized key, display, confidence, and method
    """
    if not raw:
        return PlaceNormalization(
            value=None,
            display="",
            confidence=0.0,
            method="missing",
            evidence_paths=[evidence_path],
            warnings=["place_missing"]
        )

    cleaned, display = _clean_place_publisher(raw)
    if not cleaned:
        return PlaceNormalization(
            value=None,
            display="",
            confidence=0.0,
            method="empty_after_cleaning",
            evidence_paths=[evidence_path],
            warnings=["place_empty_after_cleaning"]
        )

    # Casefold for normalized key
    norm_key = cleaned.casefold()

    # Check alias map if provided
    if alias_map and norm_key in alias_map:
        canonical_key = alias_map[norm_key]
        return PlaceNormalization(
            value=canonical_key,
            display=display,
            confidence=0.95,
            method="place_alias_map",
            evidence_paths=[evidence_path],
            warnings=[]
        )

    # Base normalization
    return PlaceNormalization(
        value=norm_key,
        display=display,
        confidence=0.80,
        method="place_casefold_strip",
        evidence_paths=[evidence_path],
        warnings=[]
    )


def normalize_publisher(
    raw: Optional[str],
    evidence_path: str,
    alias_map: Optional[Dict[str, str]] = None
) -> PublisherNormalization:
    """Normalize publisher name.

    Args:
        raw: Raw publisher string from M1 record
        evidence_path: JSON path to evidence (e.g., "imprints[0].publisher.value")
        alias_map: Optional mapping of normalized keys to canonical forms

    Returns:
        PublisherNormalization with normalized key, display, confidence, and method
    """
    if not raw:
        return PublisherNormalization(
            value=None,
            display="",
            confidence=0.0,
            method="missing",
            evidence_paths=[evidence_path],
            warnings=["publisher_missing"]
        )

    cleaned, display = _clean_place_publisher(raw)
    if not cleaned:
        return PublisherNormalization(
            value=None,
            display="",
            confidence=0.0,
            method="empty_after_cleaning",
            evidence_paths=[evidence_path],
            warnings=["publisher_empty_after_cleaning"]
        )

    # Casefold for normalized key
    norm_key = cleaned.casefold()

    # Check alias map if provided
    if alias_map and norm_key in alias_map:
        canonical_key = alias_map[norm_key]
        return PublisherNormalization(
            value=canonical_key,
            display=display,
            confidence=0.95,
            method="publisher_alias_map",
            evidence_paths=[evidence_path],
            warnings=[]
        )

    # Base normalization
    return PublisherNormalization(
        value=norm_key,
        display=display,
        confidence=0.80,
        method="publisher_casefold_strip",
        evidence_paths=[evidence_path],
        warnings=[]
    )


def normalize_agents(
    agents: List[dict],
    agent_alias_map: Optional[Dict[str, dict]] = None
) -> List[Tuple[int, AgentNormalization, RoleNormalization]]:
    """Normalize all agents from M1 record.

    Args:
        agents: List of agent dicts from M1 record
        agent_alias_map: Optional dict mapping normalized agent keys to canonical forms
            Expected structure: {
                "normalized_key": {
                    "decision": "KEEP" | "MAP" | "AMBIGUOUS",
                    "canonical": "canonical_form",
                    "confidence": 0.0-1.0,
                    "notes": "..."
                }
            }

    Returns:
        List of tuples: (agent_index, AgentNormalization, RoleNormalization)

    Note:
        This function does NOT modify the M1 agents. It only creates
        normalized representations to be appended as M2 enrichment.
    """
    results = []

    for agent_dict in agents:
        # Get agent_index (should always be present from Stage 2 extraction)
        agent_index = agent_dict.get('agent_index')
        if agent_index is None:
            # Skip agents without index (shouldn't happen with Stage 2 extraction)
            continue

        # Get raw agent name
        agent_raw = agent_dict.get('name', {}).get('value', '')
        if not agent_raw:
            # Skip agents without names
            continue

        # Normalize agent name
        agent_norm_str, agent_conf, agent_method, agent_notes = normalize_agent_with_alias_map(
            agent_raw,
            agent_alias_map
        )

        agent_norm = AgentNormalization(
            agent_raw=agent_raw,
            agent_norm=agent_norm_str,
            agent_confidence=agent_conf,
            agent_method=agent_method,
            agent_notes=agent_notes
        )

        # Normalize role
        function_dict = agent_dict.get('function')
        role_raw = function_dict.get('value') if function_dict else None

        role_norm_str, role_conf, role_method = normalize_role_base(role_raw)

        role_norm = RoleNormalization(
            role_raw=role_raw,
            role_norm=role_norm_str,
            role_confidence=role_conf,
            role_method=role_method
        )

        results.append((agent_index, agent_norm, role_norm))

    return results


def enrich_m2(
    m1_record: dict,
    place_alias_map: Optional[Dict[str, str]] = None,
    publisher_alias_map: Optional[Dict[str, str]] = None,
    agent_alias_map: Optional[Dict[str, dict]] = None
) -> M2Enrichment:
    """Enrich M1 canonical record with M2 normalized fields.

    Args:
        m1_record: M1 canonical record (dict)
        place_alias_map: Optional place normalization alias map
        publisher_alias_map: Optional publisher normalization alias map
        agent_alias_map: Optional agent normalization alias map (Stage 3)

    Returns:
        M2Enrichment object with normalized imprints and agents

    Note:
        This function does NOT modify the M1 record. It only creates
        the M2 enrichment object to be appended.
    """
    imprints_norm = []

    # Get imprints from M1 record
    imprints = m1_record.get('imprints', [])

    for i, imprint in enumerate(imprints):
        # Extract raw values
        date_raw = imprint.get('date', {}).get('value') if imprint.get('date') else None
        place_raw = imprint.get('place', {}).get('value') if imprint.get('place') else None
        publisher_raw = imprint.get('publisher', {}).get('value') if imprint.get('publisher') else None

        # Normalize each field
        date_norm = normalize_date(date_raw, f"imprints[{i}].date.value")
        place_norm = normalize_place(place_raw, f"imprints[{i}].place.value", place_alias_map)
        publisher_norm = normalize_publisher(publisher_raw, f"imprints[{i}].publisher.value", publisher_alias_map)

        # Create imprint normalization
        imprint_norm = ImprintNormalization(
            date_norm=date_norm,
            place_norm=place_norm,
            publisher_norm=publisher_norm
        )
        imprints_norm.append(imprint_norm)

    # Normalize agents (Stage 3)
    agents = m1_record.get('agents', [])
    agents_norm = normalize_agents(agents, agent_alias_map)

    return M2Enrichment(
        imprints_norm=imprints_norm,
        agents_norm=agents_norm
    )
