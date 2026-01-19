#!/usr/bin/env python3
"""
extract_unmapped_places.py

Extract place_norm values from the database that are NOT in the current alias map.
These are variants that need LLM-based normalization.

Outputs CSV: place_norm, count, sample_raw_values
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


def load_alias_map(alias_path: Path) -> tuple[set[str], set[str]]:
    """
    Load alias map and return:
    - set of all keys (input variants that will be mapped)
    - set of all values (canonical targets)
    """
    if not alias_path.exists():
        return set(), set()
    with alias_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.keys()), set(data.values())


def get_place_stats(db_path: Path) -> list[dict]:
    """
    Query database for distinct place_norm values with counts.
    Also gather sample raw values for context.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get counts per place_norm
    cursor.execute("""
        SELECT place_norm, COUNT(*) as count
        FROM imprints
        WHERE place_norm IS NOT NULL AND place_norm != ''
        GROUP BY place_norm
        ORDER BY count DESC
    """)
    place_counts = {row["place_norm"]: row["count"] for row in cursor.fetchall()}

    # Get sample raw values for each place_norm
    results = []
    for place_norm, count in place_counts.items():
        cursor.execute("""
            SELECT DISTINCT place_raw
            FROM imprints
            WHERE place_norm = ?
            LIMIT 3
        """, (place_norm,))
        samples = [row["place_raw"] for row in cursor.fetchall() if row["place_raw"]]
        results.append({
            "place_norm": place_norm,
            "count": count,
            "sample_raw_values": "; ".join(samples[:3]) if samples else ""
        })

    conn.close()
    return results


def filter_unmapped(
    place_stats: list[dict],
    mapped_keys: set[str],
    canonical_values: set[str]
) -> list[dict]:
    """
    Filter to only places that need normalization.

    A place_norm is "already handled" if:
    - It's a key in the alias map (will be mapped)
    - It's a value in the alias map (is the canonical target)

    Note: We do NOT skip based on "looks like canonical" because that
    incorrectly skips Latin variants like "venetiis" that should be mapped.
    """
    unmapped = []
    for item in place_stats:
        place_norm = item["place_norm"]

        # Already a key in alias map -> will be mapped
        if place_norm in mapped_keys:
            continue

        # Already a canonical value -> is a target
        if place_norm in canonical_values:
            continue

        # This variant needs to be processed
        unmapped.append(item)
    return unmapped


def write_csv(data: list[dict], output_path: Path) -> None:
    """Write unmapped places to CSV."""
    fieldnames = ["place_norm", "count", "sample_raw_values"]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract unmapped place variants")
    parser.add_argument(
        "--db",
        default="data/index/bibliographic.db",
        help="Path to bibliographic database"
    )
    parser.add_argument(
        "--alias-map",
        default="data/normalization/place_aliases/place_alias_map.json",
        help="Path to current alias map"
    )
    parser.add_argument(
        "--output",
        default="data/normalization/unmapped_places.csv",
        help="Output CSV path"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    alias_path = Path(args.alias_map)
    output_path = Path(args.output)

    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return

    # Load current alias map keys and values
    mapped_keys, canonical_values = load_alias_map(alias_path)
    print(f"Loaded {len(mapped_keys)} mappings from alias map")
    print(f"Found {len(canonical_values)} unique canonical targets")

    # Get all place_norm values from database
    place_stats = get_place_stats(db_path)
    print(f"Found {len(place_stats)} distinct place_norm values in database")

    # Filter to unmapped
    unmapped = filter_unmapped(place_stats, mapped_keys, canonical_values)
    print(f"Found {len(unmapped)} unmapped variants (needing normalization)")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    write_csv(unmapped, output_path)
    print(f"Wrote unmapped places to: {output_path}")

    # Summary statistics
    total_records = sum(item["count"] for item in unmapped)
    print(f"\nSummary:")
    print(f"  Unmapped variants: {len(unmapped)}")
    print(f"  Total records affected: {total_records}")
    if unmapped:
        print(f"\nTop 10 unmapped by frequency:")
        for item in unmapped[:10]:
            print(f"  {item['place_norm']}: {item['count']} records")


if __name__ == "__main__":
    main()
