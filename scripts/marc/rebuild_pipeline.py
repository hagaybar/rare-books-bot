#!/usr/bin/env python3
"""End-to-end pipeline to rebuild the bibliographic database.

Runs M1 (parse) → M2 (normalize) → M3 (index) in sequence.
No LLM calls - all processing is deterministic and rule-based.

Usage:
    # Full pipeline (from MARC XML)
    python -m scripts.marc.rebuild_pipeline --full data/marc_source/records.xml

    # M2+M3 only (skip parsing, use existing canonical JSONL)
    python -m scripts.marc.rebuild_pipeline

    # With Wikidata enrichment (requires network)
    python -m scripts.marc.rebuild_pipeline --enrich
"""

import argparse
import sys
import time
from pathlib import Path


# Default paths (relative to project root)
DEFAULT_MARC_XML = Path("data/marc_source/records.xml")
DEFAULT_M1_OUTPUT = Path("data/canonical/records.jsonl")
DEFAULT_M1_REPORT = Path("data/canonical/extraction_report.json")
DEFAULT_M2_OUTPUT = Path("data/m2/records_m1m2.jsonl")
DEFAULT_PLACE_ALIAS = Path("data/normalization/place_aliases/place_alias_map.json")
DEFAULT_PUBLISHER_ALIAS = Path("data/normalization/publisher_aliases/publisher_alias_map.json")
DEFAULT_AGENT_ALIAS = Path("data/normalization/agent_aliases/agent_alias_map.json")
DEFAULT_DB_OUTPUT = Path("data/index/bibliographic.db")
DEFAULT_SCHEMA = Path("scripts/marc/m3_schema.sql")


def run_m1_parse(marc_xml: Path, output: Path, report: Path) -> bool:
    """Run M1: Parse MARC XML to canonical JSONL."""
    print("\n" + "=" * 60)
    print("STAGE 1: M1 - Parse MARC XML")
    print("=" * 60)

    if not marc_xml.exists():
        print(f"ERROR: MARC XML file not found: {marc_xml}")
        return False

    print(f"Input:  {marc_xml}")
    print(f"Output: {output}")
    print()

    from scripts.marc.parse import parse_marc_xml_file

    start = time.time()
    report_obj = parse_marc_xml_file(
        marc_xml_path=marc_xml,
        output_path=output,
        report_path=report
    )
    elapsed = time.time() - start

    print(f"\nM1 Complete in {elapsed:.1f}s")
    print(f"  Total records: {report_obj.total_records}")
    print(f"  Successful: {report_obj.successful_extractions}")
    print(f"  Failed: {report_obj.failed_extractions}")

    return report_obj.failed_extractions == 0


def run_m2_normalize(
    input_path: Path,
    output_path: Path,
    place_alias: Path = None,
    publisher_alias: Path = None,
    agent_alias: Path = None
) -> bool:
    """Run M2: Normalize dates, places, publishers, agents."""
    print("\n" + "=" * 60)
    print("STAGE 2: M2 - Normalize")
    print("=" * 60)

    if not input_path.exists():
        print(f"ERROR: M1 output not found: {input_path}")
        print("Hint: Run with --full to parse MARC XML first")
        return False

    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")

    # Check alias maps
    place_alias_path = place_alias if place_alias and place_alias.exists() else None
    publisher_alias_path = publisher_alias if publisher_alias and publisher_alias.exists() else None
    agent_alias_path = agent_alias if agent_alias and agent_alias.exists() else None

    if place_alias_path:
        print(f"Place aliases: {place_alias_path}")
    if publisher_alias_path:
        print(f"Publisher aliases: {publisher_alias_path}")
    if agent_alias_path:
        print(f"Agent aliases: {agent_alias_path}")
    print()

    from scripts.marc.m2_normalize import process_m1_to_m2

    start = time.time()
    stats = process_m1_to_m2(
        input_path=input_path,
        output_path=output_path,
        place_alias_path=place_alias_path,
        publisher_alias_path=publisher_alias_path,
        agent_alias_path=agent_alias_path
    )
    elapsed = time.time() - start

    print(f"\nM2 Complete in {elapsed:.1f}s")
    print(f"  Total records: {stats['total_records']}")
    print(f"  Dates normalized: {stats['dates_normalized']}")
    print(f"  Places normalized: {stats['places_normalized']}")
    print(f"  Publishers normalized: {stats['publishers_normalized']}")
    print(f"  Agents normalized: {stats['agents_normalized']}")

    return True


def run_m3_index(
    input_path: Path,
    db_path: Path,
    schema_path: Path,
    enrich: bool = False
) -> bool:
    """Run M3: Build SQLite index."""
    print("\n" + "=" * 60)
    print("STAGE 3: M3 - Build SQLite Index")
    print("=" * 60)

    if not input_path.exists():
        print(f"ERROR: M2 output not found: {input_path}")
        return False

    if not schema_path.exists():
        print(f"ERROR: Schema file not found: {schema_path}")
        return False

    print(f"Input:  {input_path}")
    print(f"Output: {db_path}")
    print(f"Schema: {schema_path}")
    if enrich:
        print("Enrichment: ENABLED (Wikidata)")
    print()

    # Ensure output directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    from scripts.marc.m3_index import build_index

    start = time.time()
    stats = build_index(input_path, db_path, schema_path, enrich=enrich)
    elapsed = time.time() - start

    print(f"\nM3 Complete in {elapsed:.1f}s")
    print(f"  Records indexed: {stats['total_records']}")
    print(f"  Titles: {stats['titles']}")
    print(f"  Imprints: {stats['imprints']}")
    print(f"  Subjects: {stats['subjects']}")
    print(f"  Agents: {stats['agents']}")

    if stats.get('enrichment') and not stats['enrichment'].get('error'):
        enrich_stats = stats['enrichment']
        print(f"  Authority URIs enriched: {enrich_stats.get('enriched', 0)}")

    if stats['errors']:
        print(f"\nWARNING: {len(stats['errors'])} indexing errors")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild bibliographic database (M1 → M2 → M3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # M2+M3 only (default - assumes M1 already done)
  python -m scripts.marc.rebuild_pipeline

  # Full pipeline from MARC XML
  python -m scripts.marc.rebuild_pipeline --full data/marc_source/records.xml

  # With Wikidata enrichment
  python -m scripts.marc.rebuild_pipeline --enrich

  # Custom paths
  python -m scripts.marc.rebuild_pipeline \\
    --m1-input data/canonical/records.jsonl \\
    --db-output data/index/bibliographic.db
"""
    )

    parser.add_argument(
        "--full",
        metavar="MARC_XML",
        type=Path,
        help="Run full pipeline starting from MARC XML file"
    )
    parser.add_argument(
        "--m1-input",
        type=Path,
        default=DEFAULT_M1_OUTPUT,
        help=f"M1 canonical JSONL input (default: {DEFAULT_M1_OUTPUT})"
    )
    parser.add_argument(
        "--m2-output",
        type=Path,
        default=DEFAULT_M2_OUTPUT,
        help=f"M2 enriched JSONL output (default: {DEFAULT_M2_OUTPUT})"
    )
    parser.add_argument(
        "--db-output",
        type=Path,
        default=DEFAULT_DB_OUTPUT,
        help=f"SQLite database output (default: {DEFAULT_DB_OUTPUT})"
    )
    parser.add_argument(
        "--place-alias",
        type=Path,
        default=DEFAULT_PLACE_ALIAS,
        help=f"Place alias map JSON (default: {DEFAULT_PLACE_ALIAS})"
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Enrich authority URIs with Wikidata metadata (requires network)"
    )
    parser.add_argument(
        "--m2-only",
        action="store_true",
        help="Run only M2 normalization (skip M3 indexing)"
    )
    parser.add_argument(
        "--m3-only",
        action="store_true",
        help="Run only M3 indexing (skip M2 normalization)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("BIBLIOGRAPHIC DATABASE REBUILD PIPELINE")
    print("=" * 60)
    print("No LLM calls - all processing is deterministic")

    total_start = time.time()
    _success = True  # reserved for future stage-failure tracking

    # Determine which stages to run
    run_m1 = args.full is not None
    run_m2 = not args.m3_only
    run_m3 = not args.m2_only

    # Stage 1: M1 Parse (optional)
    if run_m1:
        if not run_m1_parse(args.full, args.m1_input, DEFAULT_M1_REPORT):
            print("\nERROR: M1 parsing failed")
            sys.exit(1)

    # Stage 2: M2 Normalize
    if run_m2:
        if not run_m2_normalize(
            args.m1_input,
            args.m2_output,
            args.place_alias,
            DEFAULT_PUBLISHER_ALIAS,
            DEFAULT_AGENT_ALIAS
        ):
            print("\nERROR: M2 normalization failed")
            sys.exit(1)

    # Stage 3: M3 Index
    if run_m3:
        if not run_m3_index(
            args.m2_output,
            args.db_output,
            DEFAULT_SCHEMA,
            enrich=args.enrich
        ):
            print("\nERROR: M3 indexing failed")
            sys.exit(1)

    total_elapsed = time.time() - total_start

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Total time: {total_elapsed:.1f}s")
    if run_m3:
        print(f"Database ready: {args.db_output}")
    print()


if __name__ == "__main__":
    main()
