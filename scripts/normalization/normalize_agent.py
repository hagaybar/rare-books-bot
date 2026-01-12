"""Agent and role normalization functions.

Deterministic, rule-based normalization for agent names and roles.
No LLM calls. All normalization is reversible and confidence-scored.
"""

import re
import unicodedata
from typing import Optional, Tuple


def normalize_agent_base(agent_raw: str) -> str:
    """Deterministic base normalization for agent names.

    Args:
        agent_raw: Raw agent name string from M1 (e.g., "Manutius, Aldus, 1450?-1515")

    Returns:
        Normalized agent key (lowercase, minimal punctuation, whitespace collapsed)

    Rules:
        - Casefold (lowercase)
        - Trim leading/trailing whitespace
        - Collapse internal whitespace to single spaces
        - Strip trailing punctuation (commas, periods, colons, semicolons)
        - Remove bracket wrappers [...]
        - Keep diacritics (consistent with place normalization)
        - Keep internal commas (for name structure like "Surname, First")
        - DO NOT expand abbreviations or invent data
        - DO NOT remove dates or qualifiers (kept for disambiguation)

    Examples:
        "Manutius, Aldus, 1450?-1515" → "manutius, aldus, 1450?-1515"
        "[Oxford University Press]" → "oxford university press"
        "Elsevier, " → "elsevier"
        "Smith, John" → "smith, john"
        "Pagliarini, Marco," → "pagliarini, marco"
    """
    if not agent_raw:
        return ""

    # Remove brackets
    normalized = agent_raw.strip()
    if normalized.startswith('[') and normalized.endswith(']'):
        normalized = normalized[1:-1].strip()

    # Unicode normalize (NFKC) - same as place/publisher
    normalized = unicodedata.normalize('NFKC', normalized)

    # Casefold
    normalized = normalized.lower()

    # Strip trailing punctuation
    normalized = normalized.rstrip('.,;:')

    # Strip whitespace again
    normalized = normalized.strip()

    # Collapse internal whitespace
    normalized = ' '.join(normalized.split())

    return normalized


def normalize_role_base(role_raw: Optional[str]) -> Tuple[str, float, str]:
    """Map role string to controlled vocabulary.

    Uses explicit mapping table for common variants.
    Returns ("other", low_confidence) for unknown roles.

    Args:
        role_raw: Raw role string from M1 (relator code, term, or inferred)

    Returns:
        Tuple of (role_norm, confidence, method) where:
        - role_norm: Controlled vocabulary term
        - confidence: 0.0-1.0
        - method: Normalization method used

    Controlled vocabulary:
        author, printer, publisher, translator, editor, illustrator, commentator,
        scribe, former_owner, dedicatee, bookseller, cartographer, engraver,
        binder, annotator, other
    """
    if not role_raw:
        return ("other", 0.5, "missing_role")

    role_clean = role_raw.strip().lower()

    # Relator code mappings (ISO 639 codes - high confidence)
    RELATOR_CODE_MAP = {
        'aut': 'author',
        'prt': 'printer',
        'pbl': 'publisher',
        'trl': 'translator',
        'edt': 'editor',
        'ill': 'illustrator',
        'com': 'commentator',
        'scr': 'scribe',
        'fmo': 'former_owner',
        'dte': 'dedicatee',
        'bsl': 'bookseller',
        'ctg': 'cartographer',
        'eng': 'engraver',
        'bnd': 'binder',
        'ann': 'annotator',
        'cre': 'creator',  # Generic creator
        'asn': 'associated_name',  # Associated name
        'oth': 'other',  # Other role
    }

    if role_clean in RELATOR_CODE_MAP:
        return (RELATOR_CODE_MAP[role_clean], 0.99, "relator_code")

    # Relator term mappings (English terms - medium-high confidence)
    RELATOR_TERM_MAP = {
        'author': 'author',
        'printer': 'printer',
        'publisher': 'publisher',
        'translator': 'translator',
        'editor': 'editor',
        'illustrator': 'illustrator',
        'commentator': 'commentator',
        'scribe': 'scribe',
        'former owner': 'former_owner',
        'dedicatee': 'dedicatee',
        'bookseller': 'bookseller',
        'engraver': 'engraver',
        'binder': 'binder',
        'annotator': 'annotator',
        'cartographer': 'cartographer',
        'creator': 'creator',
        'associated name': 'associated_name',
        # Variants and abbreviations
        'impr.': 'printer',
        'impr': 'printer',
        'pub.': 'publisher',
        'pub': 'publisher',
        'ed.': 'editor',
        'ed': 'editor',
        'trans.': 'translator',
        'trans': 'translator',
        'tran.': 'translator',
        'tr.': 'translator',
        'tr': 'translator',
        'engr.': 'engraver',
        'engr': 'engraver',
        'illus.': 'illustrator',
        'illus': 'illustrator',
        'ill.': 'illustrator',
        'print.': 'printer',
        'publ.': 'publisher',
        'edit.': 'editor',
    }

    if role_clean in RELATOR_TERM_MAP:
        return (RELATOR_TERM_MAP[role_clean], 0.95, "relator_term")

    # Inferred roles from tag type (lower confidence)
    # These come from the parser when no explicit relator is present
    if role_clean == 'author':
        return ('author', 0.85, "inferred_from_tag")
    elif role_clean == 'creator':
        return ('creator', 0.85, "inferred_from_tag")

    # Unknown role
    return ("other", 0.6, "unmapped")


def normalize_agent_with_alias_map(
    agent_raw: str,
    agent_alias_map: Optional[dict] = None
) -> Tuple[str, float, str, Optional[str]]:
    """Normalize agent name with optional alias map lookup.

    Args:
        agent_raw: Raw agent name string
        agent_alias_map: Optional dict mapping normalized keys to canonical forms
            Expected structure: {
                "normalized_key": {
                    "decision": "KEEP" | "MAP" | "AMBIGUOUS",
                    "canonical": "canonical_form",
                    "confidence": 0.0-1.0,
                    "notes": "..."
                }
            }

    Returns:
        Tuple of (agent_norm, confidence, method, notes) where:
        - agent_norm: Canonical agent name (or normalized if no alias map)
        - confidence: 0.0-1.0
        - method: "base_clean", "alias_map", or "ambiguous"
        - notes: Optional notes or warnings
    """
    # Base normalization
    agent_norm_base = normalize_agent_base(agent_raw)

    if not agent_norm_base:
        return ("", 0.0, "empty_after_cleaning", "Agent name empty after cleaning")

    # Check alias map if provided
    if agent_alias_map and agent_norm_base in agent_alias_map:
        alias_entry = agent_alias_map[agent_norm_base]
        decision = alias_entry.get("decision", "KEEP")

        if decision == "MAP":
            return (
                alias_entry["canonical"],
                alias_entry.get("confidence", 0.95),
                "alias_map",
                alias_entry.get("notes")
            )
        elif decision == "AMBIGUOUS":
            return (
                "ambiguous",
                alias_entry.get("confidence", 0.5),
                "ambiguous",
                alias_entry.get("notes", "Agent identity ambiguous")
            )
        # KEEP falls through to base normalization

    # Default: base normalization only
    return (agent_norm_base, 0.80, "base_clean", None)
