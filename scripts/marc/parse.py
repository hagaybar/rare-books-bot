"""MARC XML parser for canonical record extraction.

This module implements M1: MARC XML → Canonical JSONL
"""

import json
import traceback
from pathlib import Path
from typing import List, Optional, Dict
from collections import Counter

import pymarc
from pymarc import parse_xml_to_array

from .models import (
    CanonicalRecord, ImprintData, AgentData, SubjectData, NoteData,
    SourcedValue, SourceMetadata, ExtractionReport
)


def extract_record_id(record: pymarc.Record) -> Optional[SourcedValue]:
    """Extract record ID from MARC 001 field."""
    try:
        field_001 = record['001']
        if field_001:
            return SourcedValue(
                value=str(field_001.data),
                source=["001"]
            )
    except KeyError:
        pass
    return None


def extract_title(record: pymarc.Record) -> Optional[SourcedValue]:
    """Extract title from MARC 245 field with subfield provenance."""
    try:
        field_245 = record['245']
        if not field_245:
            return None

        # Combine subfields a, b, c for full title
        title_parts = []
        sources = []
        for subfield in ['a', 'b', 'c']:
            values = field_245.get_subfields(subfield)
            if values:
                title_parts.extend(values)
                sources.append(f"245${subfield}")

        if title_parts:
            title = ' '.join(title_parts).strip()
            return SourcedValue(value=title, source=sources)
    except KeyError:
        pass
    return None


def extract_imprints(record: pymarc.Record) -> List[ImprintData]:
    """Extract imprint/publication data from MARC 260 or 264 fields with subfield provenance.

    Returns array to support rare books with multiple imprints.
    """
    imprints = []

    # Try 260 first (older MARC), then 264 (newer RDA)
    # In rare books, there can be multiple imprints, so we check for multiple fields
    for tag in ['260', '264']:
        try:
            fields = record.get_fields(tag)
            for field in fields:
                # Extract each subfield with its source
                place_vals = field.get_subfields('a')
                publisher_vals = field.get_subfields('b')
                date_vals = field.get_subfields('c')
                manufacturer_vals = field.get_subfields('f')

                imprint = ImprintData(
                    place=SourcedValue(value=place_vals[0], source=[f"{tag}$a"]) if place_vals else None,
                    publisher=SourcedValue(value=publisher_vals[0], source=[f"{tag}$b"]) if publisher_vals else None,
                    date=SourcedValue(value=date_vals[0], source=[f"{tag}$c"]) if date_vals else None,
                    manufacturer=SourcedValue(value=manufacturer_vals[0], source=[f"{tag}$f"]) if manufacturer_vals else None,
                    source_tags=[tag]
                )
                imprints.append(imprint)
        except KeyError:
            pass

    return imprints


def extract_languages(record: pymarc.Record) -> List[SourcedValue]:
    """Extract language codes from MARC 041 field (for multilingual works)."""
    try:
        field_041 = record['041']
        if field_041:
            # Subfield 'a' contains language codes
            lang_codes = field_041.get_subfields('a')
            if lang_codes:
                return [SourcedValue(value=code, source=["041$a"]) for code in lang_codes]
    except KeyError:
        pass
    return []


def extract_language_fixed(record: pymarc.Record) -> Optional[SourcedValue]:
    """Extract fixed language code from MARC 008 positions 35-37.

    This is the primary language of the item (mandatory field).
    Captured separately even if 041 is present for consistency checking.
    """
    try:
        field_008 = record['008']
        if field_008 and hasattr(field_008, 'data') and len(field_008.data) >= 38:
            # Positions 35-37 contain 3-character language code
            lang_code = field_008.data[35:38].strip()
            if lang_code and lang_code != '   ':  # Check it's not just spaces
                return SourcedValue(value=lang_code, source=["008/35-37"])
    except (KeyError, AttributeError):
        pass
    return None


def extract_subjects(record: pymarc.Record) -> List[SubjectData]:
    """Extract subject headings from MARC 6XX fields with display string and structured parts."""
    subjects = []

    # Get all 6XX fields (600-699)
    subject_fields = record.get_fields('600', '610', '630', '650', '651')

    for field in subject_fields:
        # Build both display string and structured parts
        display_parts = []
        sources = []
        parts_dict = {}

        for subfield in field.subfields:
            code = subfield[0]
            value = subfield[1]
            # Skip control subfields
            if code not in ['2', '9', '0']:
                display_parts.append(value)
                sources.append(f"{field.tag}${code}")

                # Add to parts dictionary (some subfields can repeat, so use lists)
                if code in parts_dict:
                    # Convert to list if not already
                    if not isinstance(parts_dict[code], list):
                        parts_dict[code] = [parts_dict[code]]
                    parts_dict[code].append(value)
                else:
                    parts_dict[code] = value

        if display_parts:
            subject_str = ' -- '.join(display_parts)
            subjects.append(SubjectData(
                value=subject_str,
                source=sources,
                parts=parts_dict,
                source_tag=field.tag
            ))

    return subjects


def extract_agents(record: pymarc.Record) -> List[AgentData]:
    """Extract authors/contributors from MARC 1XX and 7XX fields.

    Separates structural role (main/added entry) from bibliographic function (printer, editor, etc.).
    """
    agents = []

    # Main entry (100-130)
    main_fields = record.get_fields('100', '110', '111', '130')
    for field in main_fields:
        name_vals = field.get_subfields('a')
        if name_vals:
            dates_vals = field.get_subfields('d')

            agent = AgentData(
                name=SourcedValue(value=name_vals[0], source=[f"{field.tag}$a"]),
                entry_role='main',
                dates=SourcedValue(value=dates_vals[0], source=[f"{field.tag}$d"]) if dates_vals else None,
                function=None,  # Main entries typically don't have relator terms
                source_tags=[field.tag]
            )
            agents.append(agent)

    # Added entries (700-730)
    added_fields = record.get_fields('700', '710', '711', '730')
    for field in added_fields:
        name_vals = field.get_subfields('a')
        if name_vals:
            dates_vals = field.get_subfields('d')

            # Function/relator can be in subfield e (term) or 4 (code)
            function_vals = field.get_subfields('e')
            function_source = f"{field.tag}$e"
            if not function_vals:
                function_vals = field.get_subfields('4')
                function_source = f"{field.tag}$4"

            agent = AgentData(
                name=SourcedValue(value=name_vals[0], source=[f"{field.tag}$a"]),
                entry_role='added',
                dates=SourcedValue(value=dates_vals[0], source=[f"{field.tag}$d"]) if dates_vals else None,
                function=SourcedValue(value=function_vals[0], source=[function_source]) if function_vals else None,
                source_tags=[field.tag]
            )
            agents.append(agent)

    return agents


def extract_notes(record: pymarc.Record) -> List[NoteData]:
    """Extract notes from MARC 5XX fields with explicit tag for filtering."""
    notes = []

    # Get all 5XX fields (500-599)
    note_fields = record.get_fields('500', '501', '502', '504', '505', '520', '590')

    for field in note_fields:
        # Combine all subfields
        parts = []
        sources = []
        for subfield in field.subfields:
            code = subfield[0]
            value = subfield[1]
            # Skip control subfields
            if code not in ['2', '6', '8', '9']:
                parts.append(value)
                sources.append(f"{field.tag}${code}")

        if parts:
            note_str = ' '.join(parts)
            notes.append(NoteData(
                tag=field.tag,
                value=note_str,
                source=sources
            ))

    return notes


def parse_marc_record(record: pymarc.Record, source_file: Optional[str] = None) -> Optional[CanonicalRecord]:
    """Parse a single MARC record into CanonicalRecord with embedded provenance.

    Args:
        record: pymarc.Record object
        source_file: Optional source MARC XML filename for traceability

    Returns:
        CanonicalRecord or None if record_id missing
    """
    # Must have record ID (control number)
    control_number = extract_record_id(record)
    if not control_number:
        return None

    # Build source metadata
    source = SourceMetadata(
        source_file=source_file,
        control_number=control_number
    )

    # Extract all fields (each with embedded provenance)
    title = extract_title(record)
    imprints = extract_imprints(record)
    languages = extract_languages(record)
    language_fixed = extract_language_fixed(record)
    subjects = extract_subjects(record)
    agents = extract_agents(record)
    notes = extract_notes(record)

    # Build canonical record
    canonical = CanonicalRecord(
        source=source,
        title=title,
        imprints=imprints,
        languages=languages,
        language_fixed=language_fixed,
        subjects=subjects,
        agents=agents,
        notes=notes
    )

    return canonical


def parse_marc_xml_file(
    marc_xml_path: Path,
    output_path: Path,
    report_path: Optional[Path] = None
) -> ExtractionReport:
    """Parse MARC XML file and output canonical JSONL.

    Args:
        marc_xml_path: Path to input MARC XML file
        output_path: Path to output JSONL file (one record per line)
        report_path: Optional path for extraction report JSON

    Returns:
        ExtractionReport with extraction statistics
    """
    canonical_records = []
    failed_records = []
    field_usage = Counter()

    # Extract source filename for traceability
    source_file = marc_xml_path.name

    # Stats for report
    stats = {
        'with_title': 0,
        'with_imprints': 0,
        'with_languages': 0,
        'with_language_fixed': 0,
        'with_subjects': 0,
        'with_agents': 0,
        'with_notes': 0,
        'missing_title': [],
        'missing_imprints': []
    }

    # Parse MARC XML file
    try:
        records = parse_xml_to_array(str(marc_xml_path))
    except Exception as e:
        print(f"Failed to parse XML file: {e}")
        records = []

    for record in records:
        try:
            canonical = parse_marc_record(record, source_file=source_file)

            if canonical:
                canonical_records.append(canonical)

                # Update stats
                if canonical.title:
                    stats['with_title'] += 1
                else:
                    stats['missing_title'].append(canonical.source.control_number.value)

                if canonical.imprints:
                    stats['with_imprints'] += 1
                else:
                    stats['missing_imprints'].append(canonical.source.control_number.value)

                if canonical.languages:
                    stats['with_languages'] += 1
                if canonical.language_fixed:
                    stats['with_language_fixed'] += 1
                if canonical.subjects:
                    stats['with_subjects'] += 1
                if canonical.agents:
                    stats['with_agents'] += 1
                if canonical.notes:
                    stats['with_notes'] += 1

                # Count field$subfield usage from embedded sources
                # Control number
                for source in canonical.source.control_number.source:
                    field_usage[source] += 1

                # Title
                if canonical.title:
                    for source in canonical.title.source:
                        field_usage[source] += 1

                # Imprints
                for imprint in canonical.imprints:
                    if imprint.place:
                        for source in imprint.place.source:
                            field_usage[source] += 1
                    if imprint.publisher:
                        for source in imprint.publisher.source:
                            field_usage[source] += 1
                    if imprint.date:
                        for source in imprint.date.source:
                            field_usage[source] += 1
                    if imprint.manufacturer:
                        for source in imprint.manufacturer.source:
                            field_usage[source] += 1

                # Languages
                for lang in canonical.languages:
                    for source in lang.source:
                        field_usage[source] += 1

                # Language fixed
                if canonical.language_fixed:
                    for source in canonical.language_fixed.source:
                        field_usage[source] += 1

                # Subjects
                for subj in canonical.subjects:
                    for source in subj.source:
                        field_usage[source] += 1

                # Agents
                for agent in canonical.agents:
                    for source in agent.name.source:
                        field_usage[source] += 1
                    if agent.dates:
                        for source in agent.dates.source:
                            field_usage[source] += 1
                    if agent.function:
                        for source in agent.function.source:
                            field_usage[source] += 1

                # Notes
                for note in canonical.notes:
                    for source in note.source:
                        field_usage[source] += 1

        except Exception as e:
            # Record failed extraction
            record_id_obj = extract_record_id(record) if record else None
            record_id = record_id_obj.value if record_id_obj else "unknown"
            failed_records.append(record_id)
            # Print full traceback for first 3 failures only
            if len(failed_records) <= 3:
                print(f"\nFailed to parse record {record_id}:")
                traceback.print_exc()
            else:
                print(f"Failed to parse record {record_id}: {type(e).__name__}: {str(e)}")

    # Write canonical records to JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for canonical in canonical_records:
            json_line = canonical.model_dump_json()
            f.write(json_line + '\n')

    # Build extraction report
    report = ExtractionReport(
        source_file=source_file,
        total_records=len(canonical_records) + len(failed_records),
        successful_extractions=len(canonical_records),
        failed_extractions=len(failed_records),
        records_with_title=stats['with_title'],
        records_with_imprints=stats['with_imprints'],
        records_with_languages=stats['with_languages'],
        records_with_language_fixed=stats['with_language_fixed'],
        records_with_subjects=stats['with_subjects'],
        records_with_agents=stats['with_agents'],
        records_with_notes=stats['with_notes'],
        records_missing_title=stats['missing_title'][:10],  # Limit to 10 examples
        records_missing_imprints=stats['missing_imprints'][:10],
        field_usage_counts=dict(field_usage)
    )

    # Write report if path provided
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report.model_dump_json(indent=2))

    return report


if __name__ == "__main__":
    # Simple CLI for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m scripts.marc.parse <marc_xml_file>")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    output_file = Path("data/canonical/records.jsonl")
    report_file = Path("data/canonical/extraction_report.json")

    print(f"Parsing {input_file}...")
    report = parse_marc_xml_file(input_file, output_file, report_file)

    print(f"\nExtraction Report:")
    print(f"  Source file: {report.source_file}")
    print(f"  Total records: {report.total_records}")
    print(f"  Successful: {report.successful_extractions}")
    print(f"  Failed: {report.failed_extractions}")
    print(f"\nField Coverage:")
    print(f"  With title: {report.records_with_title}")
    print(f"  With imprints: {report.records_with_imprints}")
    print(f"  With languages (041$a): {report.records_with_languages}")
    print(f"  With language_fixed (008): {report.records_with_language_fixed}")
    print(f"  With subjects: {report.records_with_subjects}")
    print(f"  With agents: {report.records_with_agents}")
    print(f"  With notes: {report.records_with_notes}")
    print(f"\nOutput: {output_file}")
    print(f"Report: {report_file}")
