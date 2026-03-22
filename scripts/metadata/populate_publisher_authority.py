"""Populate publisher authority database from publisher_research.json.

Reads the full research file, creates authority records for all publishers
(researched and unresearched from the file), then scans the imprints table
for any high-frequency publishers not already covered by a variant.

Usage:
    python -m scripts.metadata.populate_publisher_authority
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Project root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.metadata.publisher_authority import (
    PublisherAuthority,
    PublisherAuthorityStore,
    PublisherVariant,
    detect_script,
)

# Paths
DB_PATH = ROOT / "data" / "index" / "bibliographic.db"
RESEARCH_PATH = ROOT / "data" / "normalization" / "publisher_research.json"
LOG_PATH = ROOT / "logs" / "publisher_authority_creation.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_dates_active(dates_str: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """Parse dates_active string into (date_start, date_end) integers.

    Examples:
        "1583-1712" -> (1583, 1712)
        "1808-1870s" -> (1808, 1870)
        "17th century" -> (1600, 1699)
        "1901-present" -> (1901, None)
        "1924-1937" -> (1924, 1937)
        None -> (None, None)
    """
    if not dates_str:
        return None, None

    # "1583-1712" or "1808-1870s"
    m = re.match(r"(\d{4})\s*-\s*(\d{4})", dates_str)
    if m:
        return int(m.group(1)), int(m.group(2))

    # "1808-1870s"
    m = re.match(r"(\d{4})\s*-\s*(\d{3,4})s", dates_str)
    if m:
        return int(m.group(1)), int(m.group(2))

    # "1901-present"
    m = re.match(r"(\d{4})\s*-\s*present", dates_str, re.IGNORECASE)
    if m:
        return int(m.group(1)), None

    # "17th century"
    m = re.match(r"(\d{1,2})(?:st|nd|rd|th)\s+century", dates_str, re.IGNORECASE)
    if m:
        century = int(m.group(1))
        return (century - 1) * 100, (century - 1) * 100 + 99

    # Single year
    m = re.match(r"(\d{4})", dates_str)
    if m:
        return int(m.group(1)), int(m.group(1))

    return None, None


def determine_primary_language(canonical_name: str, variants: List[str]) -> str:
    """Determine primary language from canonical name and variants.

    Returns ISO 639-3 code: "heb", "lat", "deu", "fra", "ita", "eng", etc.
    """
    # Check canonical name script
    canonical_script = detect_script(canonical_name)
    if canonical_script == "hebrew":
        return "heb"

    # Check if most variants are Hebrew
    all_texts = [canonical_name] + variants
    hebrew_count = sum(1 for t in all_texts if detect_script(t) == "hebrew")
    if hebrew_count > len(all_texts) / 2:
        return "heb"

    # Check canonical name for Latin phrases
    latin_markers = [
        "ex officina", "apud", "in aedibus", "impensis",
        "typis", "sumpt.", "officina",
    ]
    name_lower = canonical_name.lower()
    for marker in latin_markers:
        if marker in name_lower:
            return "lat"

    # Check variant texts for Latin
    for v in variants:
        v_lower = v.lower()
        for marker in latin_markers:
            if marker in v_lower:
                return "lat"

    # Italian markers
    italian_markers = ["nella stamparia", "stamperia"]
    for marker in italian_markers:
        if marker in name_lower:
            return "ita"
    for v in variants:
        if any(marker in v.lower() for marker in italian_markers):
            return "ita"

    # German markers
    german_markers = [
        "verlag", "gesellschaft", "bibliophilen", "privatdruck",
        "gedruck", "soncino-gesellschaft",
    ]
    for marker in german_markers:
        if marker in name_lower:
            return "deu"

    # French markers
    french_markers = ["verdiere", "paris", "barrois", "delaunay", "hachette"]
    for marker in french_markers:
        if marker in name_lower:
            return "fra"

    # Default to Latin for pre-modern printing houses
    return "lat"


def determine_branch(entry: Dict[str, Any]) -> Optional[str]:
    """Determine branch for Elzevir entries based on location/notes."""
    canonical = entry.get("canonical_name", "")
    if "Elzevir" not in canonical and "elzevir" not in canonical.lower():
        return None

    location = entry.get("location", "") or ""
    notes = entry.get("notes", "") or ""
    normalized_form = entry.get("normalized_form", "").lower()

    # Check for Leiden indicators
    if "Leiden" in location and "Amsterdam" not in location:
        return "Leiden"
    if "leiden" in notes.lower():
        return "Leiden"
    if "elseviriorum" in normalized_form:
        return "Leiden"

    # Check for Amsterdam indicators
    if "Amsterdam" in location and "Leiden" not in location:
        return "Amsterdam"
    if "amsterdam" in notes.lower():
        return "Amsterdam"

    # Combined location = no specific branch
    return None


def build_authority_from_entry(
    entry: Dict[str, Any],
    all_primary_norms: Set[str],
) -> PublisherAuthority:
    """Build a PublisherAuthority from a research file entry."""
    canonical_name = entry["canonical_name"]
    normalized_form = entry["normalized_form"]
    pub_type = entry["type"]
    is_missing = entry.get("is_missing_marker", False)

    # Parse dates
    date_start, date_end = parse_dates_active(entry.get("dates_active"))

    # Build variants
    variants_list: List[PublisherVariant] = []
    seen_lower: Set[str] = set()

    # The normalized_form itself is the primary variant (matches imprints.publisher_norm)
    norm_script = detect_script(normalized_form)
    primary_variant = PublisherVariant(
        variant_form=normalized_form,
        script=norm_script,
        is_primary=True,
        priority=10,
        notes="Primary normalized form (matches imprints.publisher_norm)",
    )
    variants_list.append(primary_variant)
    seen_lower.add(normalized_form.lower())

    # Add explicit variants from research
    for v in entry.get("variants", []):
        v_lower = v.lower()
        if v_lower in seen_lower:
            continue
        # Skip if this variant is the primary normalized_form for another entry
        if v_lower in all_primary_norms and v_lower != normalized_form.lower():
            continue
        v_script = detect_script(v)
        variant = PublisherVariant(
            variant_form=v,
            script=v_script,
            is_primary=False,
            priority=0,
            notes="Known variant from research",
        )
        variants_list.append(variant)
        seen_lower.add(v_lower)

    # Determine primary language
    all_variant_texts = [v for v in entry.get("variants", [])]
    primary_language = determine_primary_language(
        canonical_name, [normalized_form] + all_variant_texts
    )

    # Determine branch (only for Elzevir)
    branch = determine_branch(entry)

    return PublisherAuthority(
        canonical_name=canonical_name,
        type=pub_type,
        confidence=entry.get("confidence", 0.5),
        dates_active=entry.get("dates_active"),
        date_start=date_start,
        date_end=date_end,
        location=entry.get("location"),
        notes=entry.get("notes"),
        sources=entry.get("sources", []),
        is_missing_marker=is_missing,
        branch=branch,
        primary_language=primary_language,
        variants=variants_list,
    )


def log_entry(log_file, action: str, data: Dict[str, Any]) -> None:
    """Append a log entry to the JSONL log file."""
    entry = {
        "timestamp": _now_iso(),
        "action": action,
        **data,
    }
    log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> Dict[str, Any]:
    """Main population function. Returns summary dict."""
    # Load research data
    with open(RESEARCH_PATH, "r", encoding="utf-8") as f:
        research = json.load(f)

    publishers = research["publishers"]

    # Separate researched vs unresearched from the file
    researched = [p for p in publishers if p["type"] != "unresearched"]
    unresearched_from_file = [p for p in publishers if p["type"] == "unresearched"]

    # Collect all primary normalized_forms to avoid cross-linking conflicts
    all_primary_norms: Set[str] = {p["normalized_form"].lower() for p in publishers}

    # Group entries that share the same canonical_name to merge them
    # (e.g., multiple Elzevir or Blaeu entries)
    canonical_groups: Dict[str, List[Dict]] = {}
    for entry in researched:
        cn = entry["canonical_name"]
        canonical_groups.setdefault(cn, []).append(entry)

    # Connect to DB
    store = PublisherAuthorityStore(DB_PATH)

    # Open a shared connection for the entire operation
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Drop and recreate tables for a fresh start
    conn.execute("DROP TABLE IF EXISTS publisher_variants")
    conn.execute("DROP TABLE IF EXISTS publisher_authorities")
    conn.commit()

    # Init schema (creates tables fresh)
    store.init_schema(conn=conn)

    # Open log file
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(LOG_PATH, "w", encoding="utf-8")

    # Counters
    researched_created = 0
    unresearched_created = 0
    total_variants = 0
    total_imprints_linked = 0
    imprint_counts: Dict[str, int] = {}  # canonical_name -> count

    # --- Step 1: Create researched authorities (merge entries with same canonical_name) ---
    created_canonical: Set[str] = set()
    all_variant_lowers: Set[str] = set()  # track all covered variants

    for canonical_name, entries in canonical_groups.items():
        if canonical_name in created_canonical:
            continue

        # Use the first entry as the base
        base_entry = entries[0]

        # Build authority from the base entry
        authority = build_authority_from_entry(base_entry, all_primary_norms)

        # Merge variants from all entries sharing this canonical name
        seen_lower = {v.variant_form.lower() for v in authority.variants}

        for extra_entry in entries[1:]:
            # Add the normalized_form of the extra entry as a variant
            nf = extra_entry["normalized_form"]
            nf_lower = nf.lower()
            if nf_lower not in seen_lower:
                nf_script = detect_script(nf)
                authority.variants.append(PublisherVariant(
                    variant_form=nf,
                    script=nf_script,
                    is_primary=False,
                    priority=5,
                    notes=f"Merged from entry: {extra_entry.get('notes', '')}",
                ))
                seen_lower.add(nf_lower)

            # Add extra entry's variants
            for v in extra_entry.get("variants", []):
                v_lower = v.lower()
                if v_lower not in seen_lower and v_lower not in all_primary_norms:
                    v_script = detect_script(v)
                    authority.variants.append(PublisherVariant(
                        variant_form=v,
                        script=v_script,
                        is_primary=False,
                        priority=0,
                        notes="Known variant from research (merged entry)",
                    ))
                    seen_lower.add(v_lower)

        # Create the authority
        try:
            auth_id = store.create(authority, conn=conn)
        except sqlite3.IntegrityError as e:
            log_entry(log_file, "error", {
                "canonical_name": canonical_name,
                "error": str(e),
            })
            continue

        researched_created += 1
        total_variants += len(authority.variants)
        all_variant_lowers.update(v.variant_form.lower() for v in authority.variants)
        all_variant_lowers.add(canonical_name.lower())

        # Link to imprints
        imprint_count = store.link_to_imprints(auth_id, conn=conn)
        total_imprints_linked += imprint_count
        imprint_counts[canonical_name] = imprint_count

        log_entry(log_file, "created_researched", {
            "authority_id": auth_id,
            "canonical_name": canonical_name,
            "type": authority.type,
            "variants_count": len(authority.variants),
            "imprints_linked": imprint_count,
            "branch": authority.branch,
            "primary_language": authority.primary_language,
        })

        created_canonical.add(canonical_name)

    # --- Step 2: Create unresearched publishers from the research file ---
    for entry in unresearched_from_file:
        nf = entry["normalized_form"]
        nf_lower = nf.lower()

        # Skip if already covered as a variant of a researched authority
        if nf_lower in all_variant_lowers:
            continue

        authority = build_authority_from_entry(entry, all_primary_norms)

        try:
            auth_id = store.create(authority, conn=conn)
        except sqlite3.IntegrityError as e:
            log_entry(log_file, "error", {
                "canonical_name": entry["canonical_name"],
                "normalized_form": nf,
                "error": str(e),
            })
            continue

        unresearched_created += 1
        total_variants += len(authority.variants)
        all_variant_lowers.add(nf_lower)

        # Link to imprints
        imprint_count = store.link_to_imprints(auth_id, conn=conn)
        total_imprints_linked += imprint_count
        imprint_counts[entry["canonical_name"]] = imprint_count

        log_entry(log_file, "created_unresearched_from_file", {
            "authority_id": auth_id,
            "canonical_name": entry["canonical_name"],
            "normalized_form": nf,
            "imprints_linked": imprint_count,
        })

    # --- Step 3: Scan for additional high-frequency publishers from imprints ---
    high_freq_rows = conn.execute("""
        SELECT publisher_norm, COUNT(*) as freq FROM imprints
        WHERE publisher_norm IS NOT NULL AND publisher_norm != ''
        GROUP BY publisher_norm HAVING freq >= 2
        ORDER BY freq DESC
    """).fetchall()

    for row in high_freq_rows:
        pub_norm = row["publisher_norm"]
        pub_lower = pub_norm.lower()

        # Skip if already covered
        if pub_lower in all_variant_lowers:
            continue

        # Create stub authority
        pub_script = detect_script(pub_norm)
        primary_lang = "heb" if pub_script == "hebrew" else "lat"

        authority = PublisherAuthority(
            canonical_name=pub_norm,
            type="unresearched",
            confidence=0.5,
            notes=f"Auto-created stub from imprints scan. Appears {row['freq']} times.",
            primary_language=primary_lang,
            variants=[
                PublisherVariant(
                    variant_form=pub_norm,
                    script=pub_script,
                    is_primary=True,
                    priority=10,
                    notes="Primary form from imprints.publisher_norm",
                )
            ],
        )

        try:
            auth_id = store.create(authority, conn=conn)
        except sqlite3.IntegrityError as e:
            log_entry(log_file, "error_imprint_scan", {
                "publisher_norm": pub_norm,
                "error": str(e),
            })
            continue

        unresearched_created += 1
        total_variants += 1
        all_variant_lowers.add(pub_lower)

        # Link to imprints
        imprint_count = store.link_to_imprints(auth_id, conn=conn)
        total_imprints_linked += imprint_count
        imprint_counts[pub_norm] = imprint_count

        log_entry(log_file, "created_unresearched_scan", {
            "authority_id": auth_id,
            "publisher_norm": pub_norm,
            "frequency": row["freq"],
            "imprints_linked": imprint_count,
        })

    # Close log
    log_file.close()

    # --- Final summary ---
    # Get top 10 by imprint count
    sorted_by_imprints = sorted(
        imprint_counts.items(), key=lambda x: x[1], reverse=True
    )[:10]

    print("\n=== PUBLISHER AUTHORITY POPULATION RESULTS ===")
    print(f"Researched authorities created: {researched_created}")
    print(f"Unresearched stubs created: {unresearched_created}")
    print(f"Total variants added: {total_variants}")
    print(f"Total imprints linked: {total_imprints_linked}")
    print()
    print("Top 10 by imprint count:")
    for i, (name, count) in enumerate(sorted_by_imprints, 1):
        print(f"  {i}. {name}: {count} imprints")
    print()
    print(f"Log file: {LOG_PATH}")

    conn.close()

    return {
        "researched_created": researched_created,
        "unresearched_created": unresearched_created,
        "total_variants": total_variants,
        "total_imprints_linked": total_imprints_linked,
        "log_path": str(LOG_PATH),
    }


if __name__ == "__main__":
    result = main()
    print()
    print(json.dumps(result, ensure_ascii=False, indent=2))
