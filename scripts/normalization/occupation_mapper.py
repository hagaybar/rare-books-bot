"""
Shared occupation → role_norm mapping logic.

Used by both Tier 1 (apply_wikidata_roles.py) and Tier 2 (fetch_tier2_occupations.py)
to map Wikidata occupation labels to MARC-based role_norm controlled vocabulary.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_occupation_map(path: Path) -> dict[str, Any]:
    """Load the occupation-to-role mapping JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def lookup_occupation(
    occupation: str,
    direct: dict[str, dict],
    semantic: dict[str, dict],
    unmapped: set[str],
) -> dict[str, Any] | None:
    """Look up an occupation in the mapping (direct first, then semantic).

    Returns the mapping dict (role_norm, confidence, note) or None if unmapped/unrecognised.
    """
    if occupation in unmapped:
        return None
    if occupation in direct:
        return direct[occupation]
    if occupation in semantic:
        return semantic[occupation]
    # Case-insensitive fallback
    occ_lower = occupation.lower()
    for d in (direct, semantic):
        for key, val in d.items():
            if key.lower() == occ_lower:
                return val
    return None


def resolve_roles(
    occupations: list[str],
    direct: dict[str, dict],
    semantic: dict[str, dict],
    unmapped: set[str],
    priority_order: list[str],
) -> list[dict[str, Any]]:
    """Resolve a list of occupations into deduplicated, priority-sorted role mappings.

    Returns list of dicts with keys: role_norm, confidence, note, source_occupation, mapping_type.
    Sorted by priority_order (index 0 = highest priority). Roles not in priority_order
    go to the end, sorted alphabetically.
    """
    seen_roles: dict[str, dict] = {}  # role_norm -> best mapping

    for occ in occupations:
        mapping = lookup_occupation(occ, direct, semantic, unmapped)
        if mapping is None:
            continue
        role = mapping["role_norm"]
        # Skip 'other' mappings — they don't improve on the current role
        if role == "other":
            continue

        mapping_type = "direct" if occ in direct else "semantic"
        entry = {
            "role_norm": role,
            "confidence": mapping["confidence"],
            "note": mapping.get("note", ""),
            "source_occupation": occ,
            "mapping_type": mapping_type,
        }

        if role not in seen_roles or mapping["confidence"] > seen_roles[role]["confidence"]:
            seen_roles[role] = entry

    if not seen_roles:
        return []

    # Sort by priority_order
    def sort_key(item: dict) -> tuple[int, str]:
        rn = item["role_norm"]
        try:
            idx = priority_order.index(rn)
        except ValueError:
            idx = len(priority_order)
        return (idx, rn)

    return sorted(seen_roles.values(), key=sort_key)


def unpack_map(occ_map: dict[str, Any]) -> tuple[dict, dict, set, list]:
    """Unpack loaded occupation map into (direct, semantic, unmapped, priority_order)."""
    return (
        occ_map["direct_mappings"],
        occ_map["semantic_mappings"],
        set(occ_map["unmapped"]),
        occ_map["priority_order"],
    )
