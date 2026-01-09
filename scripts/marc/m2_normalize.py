"""M2 normalization CLI script.

Reads M1 canonical JSONL records and outputs M1+M2 enriched JSONL.
All normalization is deterministic, reversible, and confidence-scored.
"""

import json
import sys
from pathlib import Path
from typing import Optional, Dict

from .normalize import enrich_m2


def load_alias_map(path: Optional[Path]) -> Optional[Dict[str, str]]:
    """Load alias map from JSON file if it exists.

    Args:
        path: Path to alias map JSON file

    Returns:
        Dictionary mapping normalized keys to canonical forms, or None if file doesn't exist
    """
    if not path or not path.exists():
        return None

    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def process_m1_to_m2(
    input_path: Path,
    output_path: Path,
    place_alias_path: Optional[Path] = None,
    publisher_alias_path: Optional[Path] = None
) -> dict:
    """Process M1 JSONL and output M1+M2 enriched JSONL.

    Args:
        input_path: Path to M1 canonical JSONL file
        output_path: Path to output M1+M2 JSONL file
        place_alias_path: Optional path to place alias map JSON
        publisher_alias_path: Optional path to publisher alias map JSON

    Returns:
        Statistics dictionary with counts
    """
    # Load alias maps if provided
    place_alias_map = load_alias_map(place_alias_path)
    publisher_alias_map = load_alias_map(publisher_alias_path)

    stats = {
        'total_records': 0,
        'enriched_records': 0,
        'total_imprints': 0,
        'dates_normalized': 0,
        'places_normalized': 0,
        'publishers_normalized': 0
    }

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(input_path, 'r', encoding='utf-8') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:

        for line in infile:
            stats['total_records'] += 1

            # Parse M1 record
            m1_record = json.loads(line.strip())

            # Enrich with M2
            m2_enrichment = enrich_m2(m1_record, place_alias_map, publisher_alias_map)

            # Append M2 to M1 record (non-destructive)
            enriched_record = m1_record.copy()
            enriched_record['m2'] = m2_enrichment.model_dump()

            # Update stats
            stats['enriched_records'] += 1
            stats['total_imprints'] += len(m2_enrichment.imprints_norm)

            for imprint_norm in m2_enrichment.imprints_norm:
                if imprint_norm.date_norm and imprint_norm.date_norm.start is not None:
                    stats['dates_normalized'] += 1
                if imprint_norm.place_norm and imprint_norm.place_norm.value is not None:
                    stats['places_normalized'] += 1
                if imprint_norm.publisher_norm and imprint_norm.publisher_norm.value is not None:
                    stats['publishers_normalized'] += 1

            # Write enriched record
            outfile.write(json.dumps(enriched_record) + '\n')

    return stats


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.marc.m2_normalize <input_m1.jsonl> <output_m1m2.jsonl> [place_alias.json] [publisher_alias.json]")
        print("\nExample:")
        print("  python -m scripts.marc.m2_normalize data/canonical/records.jsonl data/m2/records_m1m2.jsonl")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    place_alias_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    publisher_alias_path = Path(sys.argv[4]) if len(sys.argv) > 4 else None

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    print(f"Processing M1 → M1+M2 enrichment...")
    print(f"  Input:  {input_path}")
    print(f"  Output: {output_path}")
    if place_alias_path and place_alias_path.exists():
        print(f"  Place alias map: {place_alias_path}")
    if publisher_alias_path and publisher_alias_path.exists():
        print(f"  Publisher alias map: {publisher_alias_path}")
    print()

    stats = process_m1_to_m2(input_path, output_path, place_alias_path, publisher_alias_path)

    print(f"✅ M2 enrichment complete!")
    print(f"\nStatistics:")
    print(f"  Total records: {stats['total_records']}")
    print(f"  Enriched records: {stats['enriched_records']}")
    print(f"  Total imprints: {stats['total_imprints']}")
    print(f"  Dates normalized: {stats['dates_normalized']}")
    print(f"  Places normalized: {stats['places_normalized']}")
    print(f"  Publishers normalized: {stats['publishers_normalized']}")
    print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    main()
