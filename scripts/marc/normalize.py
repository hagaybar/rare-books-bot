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


# Direct date fixes: one-off corrections for values that cannot be handled by
# general-purpose patterns (Hebrew chronograms, Roman numerals with embedded
# text, Arabic-Indic numerals, OCR errors, etc.).
# Each key is the exact raw string; value is (start, end, confidence, method).
DIRECT_DATE_FIXES: Dict[str, Tuple[Optional[int], Optional[int], float, str]] = {
    # Hebrew chronograms / abbreviations
    'לא ח\'ס\'ר\'ת\' דבר [תרס"ח-תרע"א]': (1908, 1911, 0.90, "hebrew_chronogram"),
    '[והוא י\'ש\'פ\'ו\'ט\' תבל\' בצדק? תל"ה?]': (1675, 1675, 0.85, "hebrew_chronogram"),
    '[הסכ\' שע"ה]': (1615, 1615, 0.85, "hebrew_date_abbrev"),
    # Embedded Roman numerals with surrounding text
    'an. d[omi]ni M.D. XXVJ. Die. j. me[n]sis octobris.': (1526, 1526, 0.90, "roman_numeral_embedded"),
    'AC. M D C LXXX.[-M D C LXXXIII.]': (1680, 1683, 0.90, "roman_numeral_range"),
    # Open-start ranges (unknown start, decade end)
    '[?-192]': (None, 1929, 0.80, "open_start_range"),
    '[?-189]': (None, 1899, 0.80, "open_start_range"),
    # Arabic-Indic numeral
    '[-- \u0661\u0667]': (1700, 1799, 0.75, "arabic_numerals"),
}


def _parse_roman_numeral(text: str) -> Optional[int]:
    """Parse a Roman numeral string to an integer.

    Handles standard Roman numerals with optional dots and spaces between
    groups (e.g., "MDLXI", "M.DCCXXXI", "M DC LXXIX").

    Args:
        text: Roman numeral string (possibly with dots/spaces)

    Returns:
        Integer value, or None if not a valid Roman numeral
    """
    # Remove dots, spaces, and surrounding punctuation
    cleaned = re.sub(r'[.\s]', '', text.strip().rstrip('.'))
    cleaned = cleaned.upper()

    if not cleaned or not re.match(r'^[MDCLXVI]+$', cleaned):
        return None

    roman_values = {
        'M': 1000, 'D': 500, 'C': 100, 'L': 50,
        'X': 10, 'V': 5, 'I': 1
    }

    total = 0
    prev_value = 0
    for char in reversed(cleaned):
        value = roman_values.get(char, 0)
        if value < prev_value:
            total -= value
        else:
            total += value
        prev_value = value

    return total if 1000 <= total <= 2100 else None


# Hebrew letter values for Gematria parsing
HEBREW_GEMATRIA = {
    'א': 1, 'ב': 2, 'ג': 3, 'ד': 4, 'ה': 5, 'ו': 6, 'ז': 7, 'ח': 8, 'ט': 9,
    'י': 10, 'כ': 20, 'ך': 20, 'ל': 30, 'מ': 40, 'ם': 40, 'נ': 50, 'ן': 50,
    'ס': 60, 'ע': 70, 'פ': 80, 'ף': 80, 'צ': 90, 'ץ': 90,
    'ק': 100, 'ר': 200, 'ש': 300, 'ת': 400
}


def parse_hebrew_year(text: str) -> Optional[int]:
    """Parse Hebrew letter-based year (Gematria) to integer.

    Handles formats like: תשל"ט, [תס"ט], תק"ח
    Hebrew years typically omit the thousands (5000), so we add 5000 if < 1000.

    Args:
        text: String containing Hebrew letters representing a year

    Returns:
        Hebrew year as integer (e.g., 5739), or None if not valid
    """
    # Remove quotes, brackets, punctuation (including Hebrew geresh/gershayim)
    cleaned = re.sub(r'[\[\]"\'\״\'׳]', '', text)

    total = 0
    for char in cleaned:
        if char in HEBREW_GEMATRIA:
            total += HEBREW_GEMATRIA[char]

    if total == 0:
        return None

    # Hebrew years typically omit the 5000 (ה' אלפים)
    if total < 1000:
        total += 5000

    return total


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
        4b. Bracketed range: \[(\d{4})\s*[-/]\s*(\d{4})\] → confidence=0.90
        5. Bracketed Gregorian: \[(?:i\.?e\.?\s*)?(\d{4})\] → confidence=0.90
        5b. Embedded range (adjacent): YYYY-YYYY anywhere → confidence=0.85
        5c. Embedded range (non-adjacent): two YYYY in string → confidence=0.80
        6. Embedded year: first \d{4} anywhere → confidence=0.85 + warning
        6b. Hebrew calendar numeric: 5000+ year auto-converted → confidence=0.75
        6c. Hebrew Gematria: letter-based year (תשל"ט) → confidence=0.80
        7. Direct fixes: one-off corrections lookup table → confidence varies
        7a. Century partial: [17--?], [19--], 17 ? → confidence=0.80
        7b. Decade partial: [192-?], 163-?, 198- → confidence=0.85
        7c. Truncated range: 183 -183, 182 -190 → confidence=0.85
        7d. Roman numeral: MDLXI., Anno MDCLXXXIII. → confidence=0.95
        7e. OCR typo fix: 18O7 → 1807 → confidence=0.95
        8. Unparsed: null values, confidence=0.0 + warning
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
            confidence=0.90,
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

    # Rule 4b: Bracketed range [YYYY-YYYY] (e.g., "[1611-1612]", "[1500/1599]")
    match = re.search(r'\[(\d{4})\s*[-/]\s*(\d{4})\]', raw_stripped)
    if match:
        start_year = int(match.group(1))
        end_year = int(match.group(2))
        if 1000 <= start_year <= 2100 and 1000 <= end_year <= 2100:
            return DateNormalization(
                start=start_year,
                end=end_year,
                label=f"[{start_year}-{end_year}]",
                confidence=0.90,
                method="year_bracketed_range",
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

    # Rule 5b: Embedded range (e.g., "תרס\"א 1900-תרס\"ה 1904", "MDCXI - MDCXII [1611-1612]")
    # First try: Look for YYYY-YYYY or YYYY/YYYY pattern directly
    range_match = re.search(r'(\d{4})\s*[-/]\s*(\d{4})', raw_stripped)
    if range_match:
        start_year = int(range_match.group(1))
        end_year = int(range_match.group(2))
        # Both years must be in valid Gregorian range
        if 1000 <= start_year <= 2100 and 1000 <= end_year <= 2100:
            return DateNormalization(
                start=start_year,
                end=end_year,
                label=f"{start_year}-{end_year}",
                confidence=0.90,
                method="year_embedded_range",
                evidence_paths=[evidence_path],
                warnings=["embedded_range_in_complex_string"]
            )

    # Rule 5c: Find all Gregorian years and check if two form a range
    # Handles cases like "תרס\"א 1900-תרס\"ה 1904" where years are separated by non-numeric text
    gregorian_years = [int(m.group(1)) for m in re.finditer(r'(\d{4})', raw_stripped)
                       if 1000 <= int(m.group(1)) <= 2100]
    if len(gregorian_years) == 2:
        start_year, end_year = sorted(gregorian_years)
        # Only treat as range if end > start (not same year)
        if end_year > start_year:
            return DateNormalization(
                start=start_year,
                end=end_year,
                label=f"{start_year}-{end_year}",
                confidence=0.90,
                method="year_embedded_range",
                evidence_paths=[evidence_path],
                warnings=["embedded_range_in_complex_string"]
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
                confidence=0.92,
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

    # Rule 6c: Hebrew letter year (Gematria) - e.g., תשל"ט, [תס"ט], תק"ח
    # Hebrew years often have quotes (geresh/gershayim) within them
    # IMPORTANT: Prefer bracketed Hebrew years [תצ"ו] over loose Hebrew text
    # to avoid matching chronogram fragments like ב'א' ז'מ'ן' ה'י'ש'ו'ע'ה'

    # First, try bracketed Hebrew year (highest confidence for Hebrew dates)
    bracketed_hebrew = re.search(
        r'\[([אבגדהוזחטיכךלמםנןסעפףצץקרשת]["\'\״\'׳אבגדהוזחטיכךלמםנןסעפףצץקרשת]{1,8})["\'\״\'׳]?\]',
        raw_stripped
    )
    if bracketed_hebrew:
        hebrew_text = bracketed_hebrew.group(1)
        hebrew_year = parse_hebrew_year(hebrew_text)
        if hebrew_year and 5000 <= hebrew_year <= 6000:
            gregorian_year = hebrew_year - 3760
            if 1000 <= gregorian_year <= 2100:
                return DateNormalization(
                    start=gregorian_year,
                    end=gregorian_year,
                    label=str(gregorian_year),
                    confidence=0.92,
                    method="hebrew_gematria_bracketed",
                    evidence_paths=[evidence_path],
                    warnings=["hebrew_letter_year_converted"]
                )

    # Fall back to non-bracketed Hebrew year pattern
    # Require minimum gematria value (>=100) to avoid chronogram fragments
    hebrew_pattern = re.search(
        r'[\[\(]?([אבגדהוזחטיכךלמםנןסעפףצץקרשת]["\'\״\'׳אבגדהוזחטיכךלמםנןסעפףצץקרשת]{1,8})["\'\״\'׳]?[\]\)]?',
        raw_stripped
    )
    if hebrew_pattern:
        hebrew_text = hebrew_pattern.group(1)  # Get captured group (Hebrew year only)
        hebrew_year = parse_hebrew_year(hebrew_text)
        # Require minimum value of 100 to avoid small chronogram fragments
        if hebrew_year and 5100 <= hebrew_year <= 6000:
            # Hebrew year spans two Gregorian years (Tishrei to Elul)
            # Convert to primary Gregorian year (hebrew_year - 3760)
            gregorian_year = hebrew_year - 3760
            if 1000 <= gregorian_year <= 2100:
                return DateNormalization(
                    start=gregorian_year,
                    end=gregorian_year,
                    label=str(gregorian_year),
                    confidence=0.90,
                    method="hebrew_gematria",
                    evidence_paths=[evidence_path],
                    warnings=["hebrew_letter_year_converted"]
                )

    # Rule 7: Direct date fixes lookup (one-off corrections)
    if raw_stripped in DIRECT_DATE_FIXES:
        start, end, conf, method = DIRECT_DATE_FIXES[raw_stripped]
        return DateNormalization(
            start=start,
            end=end,
            label=f"{start or '?'}-{end}" if start != end else str(start or '?'),
            confidence=conf,
            method=method,
            evidence_paths=[evidence_path],
            warnings=["direct_fix_applied"]
        )

    # Rule 7a: Century partial — e.g., "[17--?]", "[19--]", "[16  ?]", "17 ?", "17 -"
    # Matches patterns where only the century digits are known.
    century_match = re.match(
        r'^[\[{]?(\d{2})\s*[-–_ ]{1,2}\s*[-–_?  ]{0,2}\s*[\]}\)]?\s*[-–]?$',
        raw_stripped
    )
    if century_match:
        century = int(century_match.group(1))
        if 10 <= century <= 21:
            return DateNormalization(
                start=century * 100,
                end=century * 100 + 99,
                label=f"{century}xx",
                confidence=0.80,
                method="century_partial",
                evidence_paths=[evidence_path],
                warnings=["century_level_date"]
            )

    # Rule 7b: Decade partial — e.g., "[192-?]", "163-?", "[178-]", "198-",
    # "{193-?]", "[196-]-", "[176?]-", "[177?]", "178 -", "176 -"
    decade_match = re.match(
        r'^[\[{]?(\d{3})\s*[-–_? ]*\s*[\]}\)]?\s*[-–]?$',
        raw_stripped
    )
    if decade_match:
        decade = int(decade_match.group(1))
        if 100 <= decade <= 210:
            return DateNormalization(
                start=decade * 10,
                end=decade * 10 + 9,
                label=f"{decade}x",
                confidence=0.85,
                method="decade_partial",
                evidence_paths=[evidence_path],
                warnings=["decade_level_date"]
            )

    # Rule 7c: Truncated range — e.g., "183 -183", "182 -190", "181 -183"
    # Two 3-digit decade prefixes separated by a hyphen.
    trunc_match = re.match(
        r'^(\d{3})\s*[-–]\s*(\d{3})$',
        raw_stripped
    )
    if trunc_match:
        d1 = int(trunc_match.group(1))
        d2 = int(trunc_match.group(2))
        if 100 <= d1 <= 210 and 100 <= d2 <= 210:
            return DateNormalization(
                start=d1 * 10,
                end=d2 * 10 + 9,
                label=f"{d1}x-{d2}x",
                confidence=0.85,
                method="truncated_range",
                evidence_paths=[evidence_path],
                warnings=["truncated_range_date"]
            )

    # Rule 7d: Roman numeral dates — e.g., "MDLXI.", "MDCCXLVIII.",
    # "M. DCCXXXI.", "Anno MDCLXXXIII.", "A. MDCCXIV."
    # Strip common prefixes (Anno, A., AC.) and try to parse remainder.
    roman_text = re.sub(r'^(?:Anno|A\.?|AC\.?)\s*', '', raw_stripped, flags=re.IGNORECASE)
    roman_text = roman_text.strip().rstrip('.')
    if re.search(r'[MDCLXVI]{3,}', roman_text.upper()):
        roman_year = _parse_roman_numeral(roman_text)
        if roman_year:
            return DateNormalization(
                start=roman_year,
                end=roman_year,
                label=str(roman_year),
                confidence=0.95,
                method="roman_numeral",
                evidence_paths=[evidence_path],
                warnings=["roman_numeral_date"]
            )

    # Rule 7e: OCR typo fix — e.g., "18O7" (letter O instead of digit 0)
    ocr_candidate = raw_stripped.replace('O', '0').replace('o', '0')
    ocr_match = re.match(r'^(\d{4})$', ocr_candidate)
    if ocr_match and ocr_candidate != raw_stripped:
        year = int(ocr_match.group(1))
        if 1000 <= year <= 2100:
            return DateNormalization(
                start=year,
                end=year,
                label=str(year),
                confidence=0.95,
                method="ocr_typo_fix",
                evidence_paths=[evidence_path],
                warnings=["ocr_typo_corrected"]
            )

    # Rule 8: Unparsed
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
