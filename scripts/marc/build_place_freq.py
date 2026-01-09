"""Build place frequency table from MARC XML for alias mapping preparation.

This script extracts publication places from MARC XML, normalizes them using
basic cleaning (no aliasing), and produces frequency tables to help human
experts create place alias maps.

Output:
    - places_freq.csv: place_norm, count (sorted by count desc)
    - places_examples.json: {place_norm: {count, examples}}
"""

import csv
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import pymarc
from pymarc import parse_xml_to_array


def normalize_place_basic(raw: Optional[str]) -> Optional[str]:
    """Normalize place string using basic cleaning (no aliasing).

    Args:
        raw: Raw place string from MARC

    Returns:
        Normalized place key (casefolded, cleaned) or None if empty

    Rules (applied in order):
        1. Strip whitespace
        2. Remove surrounding brackets if entire string is bracketed
        3. Strip trailing punctuation (:, ;, /)
        4. Unicode normalize (NFKC)
        5. Collapse internal whitespace to single spaces
        6. Casefold
    """
    if not raw:
        return None

    # Strip whitespace
    s = raw.strip()
    if not s:
        return None

    # Remove surrounding brackets if entire string is bracketed
    if s.startswith('[') and s.endswith(']'):
        s = s[1:-1].strip()
        if not s:
            return None

    # Strip trailing punctuation repeatedly
    trailing_punct = {':' , ',', ';', '/'}
    while s and s[-1] in trailing_punct:
        s = s[:-1]

    s = s.strip()
    if not s:
        return None

    # Unicode normalize (NFKC)
    s = unicodedata.normalize('NFKC', s)

    # Collapse internal whitespace to single spaces
    s = ' '.join(s.split())

    # Casefold
    s = s.casefold()

    return s if s else None


def extract_places_from_record(record: pymarc.Record) -> List[str]:
    """Extract publication place strings from a MARC record.

    Priority:
        1. 264 fields with ind2='1' (publication) → $a
        2. If no qualifying 264, use 260 → $a

    Args:
        record: pymarc.Record object

    Returns:
        List of raw place strings
    """
    places = []

    # Try 264 fields with ind2='1' (publication)
    try:
        fields_264 = record.get_fields('264')
        for field in fields_264:
            # Check if indicator2 is '1' (publication)
            if field.indicator2 == '1':
                place_vals = field.get_subfields('a')
                places.extend(place_vals)
    except (KeyError, AttributeError):
        pass

    # If no places from 264, try 260
    if not places:
        try:
            fields_260 = record.get_fields('260')
            for field in fields_260:
                place_vals = field.get_subfields('a')
                places.extend(place_vals)
        except (KeyError, AttributeError):
            pass

    return places


def build_place_frequency(
    marc_xml_path: Path,
    max_examples: int = 5
) -> Tuple[Counter, Dict[str, List[str]], Dict[str, int]]:
    """Build place frequency table from MARC XML.

    Args:
        marc_xml_path: Path to MARC XML file
        max_examples: Maximum number of raw examples to keep per place_norm

    Returns:
        Tuple of (frequency_counter, examples_dict, stats_dict)
    """
    frequency = Counter()
    examples = defaultdict(list)
    stats = {
        'total_records': 0,
        'records_with_places': 0,
        'records_without_places': 0,
        'total_raw_places': 0,
        'missing_place_count': 0  # Places that normalized to None
    }

    # Parse MARC XML
    try:
        records = parse_xml_to_array(str(marc_xml_path))
    except Exception as e:
        print(f"Failed to parse MARC XML: {e}")
        return frequency, dict(examples), stats

    for record in records:
        stats['total_records'] += 1

        # Extract places
        raw_places = extract_places_from_record(record)

        if raw_places:
            stats['records_with_places'] += 1
        else:
            stats['records_without_places'] += 1

        # Process each place
        for raw_place in raw_places:
            stats['total_raw_places'] += 1

            # Normalize
            place_norm = normalize_place_basic(raw_place)

            if place_norm is None:
                stats['missing_place_count'] += 1
                continue

            # Increment counter
            frequency[place_norm] += 1

            # Collect examples (unique, up to max_examples)
            if raw_place not in examples[place_norm] and len(examples[place_norm]) < max_examples:
                examples[place_norm].append(raw_place)

    return frequency, dict(examples), stats


def write_frequency_csv(frequency: Counter, output_path: Path):
    """Write place frequency table to CSV.

    Args:
        frequency: Counter of place_norm -> count
        output_path: Path to output CSV file

    Format:
        place_norm,count
        paris,123
        venetiis,98
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Sort by count desc, then place_norm asc (deterministic)
    sorted_places = sorted(frequency.items(), key=lambda x: (-x[1], x[0]))

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['place_norm', 'count'])
        for place_norm, count in sorted_places:
            writer.writerow([place_norm, count])


def write_examples_json(frequency: Counter, examples: Dict[str, List[str]], output_path: Path):
    """Write place examples JSON.

    Args:
        frequency: Counter of place_norm -> count
        examples: Dictionary of place_norm -> [raw_examples]
        output_path: Path to output JSON file

    Format:
        {
          "paris": {"count": 123, "examples": ["Paris :", "Paris"]},
          "venetiis": {"count": 98, "examples": ["Venetiis :", "Venetiis"]}
        }
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_dict = {}
    for place_norm, count in frequency.items():
        output_dict[place_norm] = {
            'count': count,
            'examples': examples.get(place_norm, [])
        }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_dict, f, ensure_ascii=False, indent=2)


def print_report(
    marc_xml_path: Path,
    frequency: Counter,
    stats: Dict[str, int],
    top_n: int = 20
):
    """Print frequency analysis report.

    Args:
        marc_xml_path: Path to input MARC XML file
        frequency: Counter of place_norm -> count
        stats: Statistics dictionary
        top_n: Number of top places to show
    """
    print("=" * 80)
    print("PLACE FREQUENCY ANALYSIS REPORT")
    print("=" * 80)
    print(f"\nInput: {marc_xml_path}")
    print(f"\nRecords:")
    print(f"  Total records processed: {stats['total_records']}")
    print(f"  Records with places: {stats['records_with_places']}")
    print(f"  Records without places: {stats['records_without_places']}")
    print(f"\nPlaces:")
    print(f"  Total raw place strings: {stats['total_raw_places']}")
    print(f"  Unique place_norm values: {len(frequency)}")
    print(f"  Missing/empty after normalization: {stats['missing_place_count']}")

    # Top places
    print(f"\nTop {top_n} Places (by frequency):")
    sorted_places = sorted(frequency.items(), key=lambda x: (-x[1], x[0]))
    for i, (place_norm, count) in enumerate(sorted_places[:top_n], 1):
        print(f"  {i:2d}. {place_norm:40s} : {count:5d}")

    print("=" * 80)


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 4:
        print("Usage: python -m scripts.marc.build_place_freq <marc_xml> <places_freq.csv> <places_examples.json>")
        print("\nExample:")
        print("  python -m scripts.marc.build_place_freq \\")
        print("    data/marc_source/BIBLIOGRAPHIC_*.xml \\")
        print("    data/frequency/places_freq.csv \\")
        print("    data/frequency/places_examples.json")
        sys.exit(1)

    marc_xml_path = Path(sys.argv[1])
    freq_csv_path = Path(sys.argv[2])
    examples_json_path = Path(sys.argv[3])

    if not marc_xml_path.exists():
        print(f"Error: MARC XML file not found: {marc_xml_path}")
        sys.exit(1)

    print(f"Building place frequency table from: {marc_xml_path}")
    print()

    # Build frequency table
    frequency, examples, stats = build_place_frequency(marc_xml_path)

    # Write outputs
    write_frequency_csv(frequency, freq_csv_path)
    write_examples_json(frequency, examples, examples_json_path)

    # Print report
    print_report(marc_xml_path, frequency, stats)

    print(f"\n✅ Output files:")
    print(f"  Frequency CSV: {freq_csv_path}")
    print(f"  Examples JSON: {examples_json_path}")


if __name__ == "__main__":
    main()
