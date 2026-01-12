"""Build SQLite bibliographic index from M1+M2 JSONL records.

This script creates a queryable SQLite database from enriched canonical records.
The database supports fielded queries on both M1 raw values and M2 normalized values.
"""

import json
import sqlite3
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, Optional


def create_database(db_path: Path, schema_path: Path) -> sqlite3.Connection:
    """Create SQLite database with M3 schema.

    Args:
        db_path: Path to SQLite database file
        schema_path: Path to SQL schema file

    Returns:
        Database connection
    """
    # Remove existing database if it exists
    if db_path.exists():
        db_path.unlink()

    # Create database and execute schema
    conn = sqlite3.connect(str(db_path))

    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    conn.executescript(schema_sql)
    conn.commit()

    return conn


def index_record(conn: sqlite3.Connection, record: dict, source_file: str, line_number: int) -> dict:
    """Index a single M1+M2 record into SQLite.

    Args:
        conn: SQLite connection
        record: M1+M2 record (dict)
        source_file: Source JSONL filename
        line_number: Line number in source file

    Returns:
        Statistics dict with counts
    """
    stats = {
        'titles': 0,
        'imprints': 0,
        'subjects': 0,
        'agents': 0,
        'languages': 0,
        'notes': 0,
        'physical_descriptions': 0
    }

    cursor = conn.cursor()

    # Insert record
    mms_id = record['source']['control_number']['value']
    created_at = datetime.now(UTC).isoformat()

    cursor.execute(
        "INSERT INTO records (mms_id, source_file, created_at, jsonl_line_number) VALUES (?, ?, ?, ?)",
        (mms_id, source_file, created_at, line_number)
    )
    record_id = cursor.lastrowid

    # Insert main title
    if record.get('title'):
        title_data = record['title']
        cursor.execute(
            "INSERT INTO titles (record_id, title_type, value, source) VALUES (?, ?, ?, ?)",
            (record_id, 'main', title_data['value'], json.dumps(title_data['source']))
        )
        stats['titles'] += 1

    # Insert uniform title
    if record.get('uniform_title'):
        uniform_title_data = record['uniform_title']
        cursor.execute(
            "INSERT INTO titles (record_id, title_type, value, source) VALUES (?, ?, ?, ?)",
            (record_id, 'uniform', uniform_title_data['value'], json.dumps(uniform_title_data['source']))
        )
        stats['titles'] += 1

    # Insert variant titles
    for variant_title in record.get('variant_titles', []):
        cursor.execute(
            "INSERT INTO titles (record_id, title_type, value, source) VALUES (?, ?, ?, ?)",
            (record_id, 'variant', variant_title['value'], json.dumps(variant_title['source']))
        )
        stats['titles'] += 1

    # Insert imprints (M1 + M2)
    m2_data = record.get('m2', {})
    imprints_norm = m2_data.get('imprints_norm', [])

    for i, imprint in enumerate(record.get('imprints', [])):
        # M1 raw values
        date_raw = imprint.get('date', {}).get('value') if imprint.get('date') else None
        place_raw = imprint.get('place', {}).get('value') if imprint.get('place') else None
        publisher_raw = imprint.get('publisher', {}).get('value') if imprint.get('publisher') else None
        manufacturer_raw = imprint.get('manufacturer', {}).get('value') if imprint.get('manufacturer') else None
        source_tags = json.dumps(imprint.get('source_tags', []))

        # M2 normalized values (if available)
        imprint_norm = imprints_norm[i] if i < len(imprints_norm) else None

        date_start = None
        date_end = None
        date_label = None
        date_confidence = None
        date_method = None

        place_norm = None
        place_display = None
        place_confidence = None
        place_method = None

        publisher_norm = None
        publisher_display = None
        publisher_confidence = None
        publisher_method = None

        if imprint_norm:
            # Date normalization
            date_norm = imprint_norm.get('date_norm')
            if date_norm:
                date_start = date_norm.get('start')
                date_end = date_norm.get('end')
                date_label = date_norm.get('label')
                date_confidence = date_norm.get('confidence')
                date_method = date_norm.get('method')

            # Place normalization
            place_norm_data = imprint_norm.get('place_norm')
            if place_norm_data:
                place_norm = place_norm_data.get('value')
                place_display = place_norm_data.get('display')
                place_confidence = place_norm_data.get('confidence')
                place_method = place_norm_data.get('method')

            # Publisher normalization
            publisher_norm_data = imprint_norm.get('publisher_norm')
            if publisher_norm_data:
                publisher_norm = publisher_norm_data.get('value')
                publisher_display = publisher_norm_data.get('display')
                publisher_confidence = publisher_norm_data.get('confidence')
                publisher_method = publisher_norm_data.get('method')

        cursor.execute("""
            INSERT INTO imprints (
                record_id, occurrence,
                date_raw, place_raw, publisher_raw, manufacturer_raw, source_tags,
                date_start, date_end, date_label, date_confidence, date_method,
                place_norm, place_display, place_confidence, place_method,
                publisher_norm, publisher_display, publisher_confidence, publisher_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record_id, i,
            date_raw, place_raw, publisher_raw, manufacturer_raw, source_tags,
            date_start, date_end, date_label, date_confidence, date_method,
            place_norm, place_display, place_confidence, place_method,
            publisher_norm, publisher_display, publisher_confidence, publisher_method
        ))
        stats['imprints'] += 1

    # Insert subjects
    for subject in record.get('subjects', []):
        scheme = subject.get('scheme', {}).get('value') if subject.get('scheme') else None
        heading_lang = subject.get('heading_lang', {}).get('value') if subject.get('heading_lang') else None

        cursor.execute("""
            INSERT INTO subjects (record_id, value, source_tag, scheme, heading_lang, parts, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            record_id,
            subject['value'],
            subject['source_tag'],
            scheme,
            heading_lang,
            json.dumps(subject['parts']),
            json.dumps(subject['source'])
        ))
        stats['subjects'] += 1

    # Insert agents (Stage 4: M1 + M2 fields)
    agents_m1 = record.get('agents', [])
    agents_m2 = m2_data.get('agents_norm', [])

    # Build lookup: agent_index → (agent_norm, role_norm) from M2
    agents_m2_lookup = {}
    for agent_tuple in agents_m2:
        if len(agent_tuple) == 3:
            idx, agent_norm_obj, role_norm_obj = agent_tuple
            agents_m2_lookup[idx] = (agent_norm_obj, role_norm_obj)

    # Insert each agent with M1 + M2 data
    for idx, agent_m1 in enumerate(agents_m1):
        agent_index = agent_m1.get('agent_index')
        if agent_index is None:
            # Backward compatibility: use enumeration index if agent_index not present
            agent_index = idx

        # M1 fields
        agent_raw = agent_m1.get('name', {}).get('value', '')
        if not agent_raw:
            continue

        agent_type = agent_m1.get('agent_type', 'personal')
        role_raw = agent_m1.get('function', {}).get('value') if agent_m1.get('function') else None
        role_source = agent_m1.get('role_source', 'unknown')

        # Build provenance JSON from M1 sources
        name_sources = agent_m1.get('name', {}).get('source', []) if agent_m1.get('name') else []
        provenance = [{"source": src} for src in name_sources]

        # M2 fields (with fallback if M2 not available)
        if agent_index in agents_m2_lookup:
            agent_norm_obj, role_norm_obj = agents_m2_lookup[agent_index]
            agent_norm = agent_norm_obj.get('agent_norm', agent_raw.lower())
            agent_confidence = agent_norm_obj.get('agent_confidence', 0.5)
            agent_method = agent_norm_obj.get('agent_method', 'fallback')
            agent_notes = agent_norm_obj.get('agent_notes')

            role_norm = role_norm_obj.get('role_norm', 'other')
            role_confidence = role_norm_obj.get('role_confidence', 0.5)
            role_method = role_norm_obj.get('role_method', 'fallback')
        else:
            # Fallback if M2 not available (shouldn't happen in normal flow)
            agent_norm = agent_raw.lower()
            agent_confidence = 0.5
            agent_method = 'fallback'
            agent_notes = 'M2 enrichment not available'

            role_norm = 'other'
            role_confidence = 0.5
            role_method = 'fallback'

        cursor.execute("""
            INSERT INTO agents (
                record_id, agent_index,
                agent_raw, agent_type, role_raw, role_source,
                agent_norm, agent_confidence, agent_method, agent_notes,
                role_norm, role_confidence, role_method,
                provenance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record_id,
            agent_index,
            agent_raw,
            agent_type,
            role_raw,
            role_source,
            agent_norm,
            agent_confidence,
            agent_method,
            agent_notes,
            role_norm,
            role_confidence,
            role_method,
            json.dumps(provenance)
        ))
        stats['agents'] += 1

    # Insert languages
    for lang in record.get('languages', []):
        cursor.execute("""
            INSERT INTO languages (record_id, code, source)
            VALUES (?, ?, ?)
        """, (
            record_id,
            lang['value'],  # Changed from lang['code'] to lang['value']
            json.dumps(lang['source'])
        ))
        stats['languages'] += 1

    # Insert notes
    for note in record.get('notes', []):
        cursor.execute("""
            INSERT INTO notes (record_id, tag, value, source)
            VALUES (?, ?, ?, ?)
        """, (
            record_id,
            note['tag'],
            note['value'],
            json.dumps(note['source'])
        ))
        stats['notes'] += 1

    # Insert physical descriptions
    for phys_desc in record.get('physical_description', []):
        cursor.execute("""
            INSERT INTO physical_descriptions (record_id, value, source)
            VALUES (?, ?, ?)
        """, (
            record_id,
            phys_desc['value'],
            json.dumps(phys_desc['source'])
        ))
        stats['physical_descriptions'] += 1

    return stats


def build_index(jsonl_path: Path, db_path: Path, schema_path: Path) -> dict:
    """Build SQLite index from M1+M2 JSONL.

    Args:
        jsonl_path: Path to M1+M2 JSONL file
        db_path: Path to output SQLite database
        schema_path: Path to SQL schema file

    Returns:
        Statistics dict
    """
    stats = {
        'total_records': 0,
        'titles': 0,
        'imprints': 0,
        'subjects': 0,
        'agents': 0,
        'languages': 0,
        'notes': 0,
        'physical_descriptions': 0,
        'errors': []
    }

    # Create database
    print(f"Creating database: {db_path}")
    conn = create_database(db_path, schema_path)

    # Process JSONL
    print(f"Indexing records from: {jsonl_path}")

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_number, line in enumerate(f, 1):
            try:
                record = json.loads(line.strip())

                # Index record
                record_stats = index_record(
                    conn,
                    record,
                    jsonl_path.name,
                    line_number
                )

                # Update totals
                stats['total_records'] += 1
                for key in record_stats:
                    stats[key] += record_stats[key]

                # Progress indicator
                if stats['total_records'] % 500 == 0:
                    print(f"  Indexed {stats['total_records']} records...")

            except Exception as e:
                error_msg = f"Line {line_number}: {str(e)}"
                stats['errors'].append(error_msg)
                print(f"  ERROR: {error_msg}")

    # Commit and close
    conn.commit()
    conn.close()

    return stats


def print_report(stats: dict, db_path: Path):
    """Print indexing report.

    Args:
        stats: Statistics dictionary
        db_path: Path to created database
    """
    print()
    print("=" * 80)
    print("M3 INDEXING REPORT")
    print("=" * 80)
    print(f"\nDatabase: {db_path}")
    print(f"\nRecords:")
    print(f"  Total records indexed: {stats['total_records']}")
    print(f"\nIndexed entities:")
    print(f"  Titles: {stats['titles']}")
    print(f"  Imprints: {stats['imprints']}")
    print(f"  Subjects: {stats['subjects']}")
    print(f"  Agents: {stats['agents']}")
    print(f"  Languages: {stats['languages']}")
    print(f"  Notes: {stats['notes']}")
    print(f"  Physical descriptions: {stats['physical_descriptions']}")

    if stats['errors']:
        print(f"\nErrors: {len(stats['errors'])}")
        for error in stats['errors'][:10]:  # Show first 10
            print(f"  - {error}")
        if len(stats['errors']) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more")

    print("=" * 80)


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 4:
        print("Usage: python -m scripts.marc.m3_index <m1m2_jsonl> <output_db> <schema_sql>")
        print("\nExample:")
        print("  python -m scripts.marc.m3_index \\")
        print("    data/canonical/m1m2_enriched.jsonl \\")
        print("    data/index/bibliographic.db \\")
        print("    scripts/marc/m3_schema.sql")
        sys.exit(1)

    jsonl_path = Path(sys.argv[1])
    db_path = Path(sys.argv[2])
    schema_path = Path(sys.argv[3])

    if not jsonl_path.exists():
        print(f"Error: JSONL file not found: {jsonl_path}")
        sys.exit(1)

    if not schema_path.exists():
        print(f"Error: Schema file not found: {schema_path}")
        sys.exit(1)

    # Create output directory
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Build index
    stats = build_index(jsonl_path, db_path, schema_path)

    # Print report
    print_report(stats, db_path)

    if stats['errors']:
        print(f"\nWARNING: Indexing completed with {len(stats['errors'])} errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
