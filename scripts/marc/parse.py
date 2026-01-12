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


def _make_source_ref(tag: str, occurrence: int, subfield: str) -> str:
    """Create source reference with occurrence indexing.

    Args:
        tag: MARC tag (e.g., '500', '260')
        occurrence: Zero-based occurrence index for this tag
        subfield: Subfield code (e.g., 'a', 'b') or special notation (e.g., '35-37')

    Returns:
        Source reference string (e.g., '500[0]$a', '260[1]$b', '008/35-37')
    """
    if '/' in subfield:  # Special case for control fields like 008/35-37
        return f"{tag}/{subfield}"
    return f"{tag}[{occurrence}]${subfield}"


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
    """Extract imprint/publication data from MARC 260 or 264 fields with occurrence indexing.

    Returns array to support rare books with multiple imprints.
    """
    imprints = []

    # Try 260 first (older MARC), then 264 (newer RDA)
    # In rare books, there can be multiple imprints, so we check for multiple fields
    for tag in ['260', '264']:
        try:
            fields = record.get_fields(tag)
            for occ, field in enumerate(fields):
                # Extract each subfield with occurrence-indexed source
                place_vals = field.get_subfields('a')
                publisher_vals = field.get_subfields('b')
                date_vals = field.get_subfields('c')
                manufacturer_vals = field.get_subfields('f')

                imprint = ImprintData(
                    place=SourcedValue(value=place_vals[0], source=[_make_source_ref(tag, occ, 'a')]) if place_vals else None,
                    publisher=SourcedValue(value=publisher_vals[0], source=[_make_source_ref(tag, occ, 'b')]) if publisher_vals else None,
                    date=SourcedValue(value=date_vals[0], source=[_make_source_ref(tag, occ, 'c')]) if date_vals else None,
                    manufacturer=SourcedValue(value=manufacturer_vals[0], source=[_make_source_ref(tag, occ, 'f')]) if manufacturer_vals else SourcedValue(value=None, source=[]),
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
    """Extract subject headings from MARC 6XX fields with occurrence indexing and scheme/lang."""
    subjects = []

    # Track occurrence count per tag
    tag_occurrences = {}

    # Get all 6XX fields (600-699)
    subject_fields = record.get_fields('600', '610', '630', '650', '651')

    for field in subject_fields:
        # Get occurrence index for this tag
        tag = field.tag
        occ = tag_occurrences.get(tag, 0)
        tag_occurrences[tag] = occ + 1

        # Build both display string and structured parts
        display_parts = []
        sources = []
        parts_dict = {}
        scheme_val = None
        heading_lang_val = None

        # Subdivision subfields that should always be arrays
        subdivision_codes = {'v', 'x', 'y', 'z'}

        for subfield in field.subfields:
            code = subfield[0]
            value = subfield[1]

            # Capture scheme ($2) and heading language ($9)
            if code == '2':
                scheme_val = value
            elif code == '9':
                heading_lang_val = value
            # Skip other control subfields
            elif code not in ['0', '6', '8']:
                display_parts.append(value)
                sources.append(_make_source_ref(tag, occ, code))

                # Add to parts dictionary
                # v/x/y/z are always arrays (subdivisions can repeat)
                if code in subdivision_codes:
                    if code in parts_dict:
                        parts_dict[code].append(value)
                    else:
                        parts_dict[code] = [value]
                else:
                    # Non-subdivision codes stored as single values
                    if code in parts_dict:
                        # Handle unexpected repetition by converting to list
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
                source_tag=tag,
                scheme=SourcedValue(value=scheme_val, source=[_make_source_ref(tag, occ, '2')]) if scheme_val else None,
                heading_lang=SourcedValue(value=heading_lang_val, source=[_make_source_ref(tag, occ, '9')]) if heading_lang_val else None
            ))

    return subjects


def _extract_role_from_field(field: pymarc.Field, tag: str, occurrence: int) -> tuple:
    """Extract role with source priority: $4 (relator code) > $e (relator term) > inferred from tag.

    Args:
        field: MARC field object
        tag: MARC tag (e.g., '100', '700')
        occurrence: Zero-based occurrence index

    Returns:
        (function_sourced_value, role_source) where:
        - function_sourced_value: SourcedValue with role or None
        - role_source: 'relator_code', 'relator_term', 'inferred_from_tag', or 'unknown'
    """
    # Priority 1: $4 relator code (best)
    relator_codes = field.get_subfields('4')
    if relator_codes:
        return (
            SourcedValue(value=relator_codes[0], source=[_make_source_ref(tag, occurrence, '4')]),
            'relator_code'
        )

    # Priority 2: $e relator term
    relator_terms = field.get_subfields('e')
    if relator_terms:
        return (
            SourcedValue(value=relator_terms[0], source=[_make_source_ref(tag, occurrence, 'e')]),
            'relator_term'
        )

    # Priority 3: Infer from tag type (lower confidence)
    inferred_roles = {
        '100': 'author',  # Main entry - personal name (usually author)
        '110': 'creator',  # Main entry - corporate body
        '111': 'creator',  # Main entry - meeting
    }

    if tag in inferred_roles:
        return (
            SourcedValue(value=inferred_roles[tag], source=[f"{tag}[{occurrence}](inferred)"]),
            'inferred_from_tag'
        )

    # No role information available
    return (None, 'unknown')


def _get_agent_type(tag: str) -> str:
    """Determine agent type from MARC tag.

    Args:
        tag: MARC tag (e.g., '100', '710', '111')

    Returns:
        'personal', 'corporate', or 'meeting'
    """
    if tag in ['100', '700']:
        return 'personal'
    elif tag in ['110', '710']:
        return 'corporate'
    elif tag in ['111', '711']:
        return 'meeting'
    else:
        return 'personal'  # default fallback


def _extract_personal_agent(field: pymarc.Field, tag: str, occurrence: int, entry_role: str, agent_index: int) -> Optional[AgentData]:
    """Extract personal name agent (100/700).

    Args:
        field: MARC field object
        tag: MARC tag ('100' or '700')
        occurrence: Zero-based occurrence index
        entry_role: 'main' or 'added'
        agent_index: Stable ordering index for this agent

    Returns:
        AgentData or None if extraction fails
    """
    name_vals = field.get_subfields('a')
    if not name_vals:
        return None

    dates_vals = field.get_subfields('d')
    function_sv, role_source = _extract_role_from_field(field, tag, occurrence)

    return AgentData(
        name=SourcedValue(value=name_vals[0], source=[_make_source_ref(tag, occurrence, 'a')]),
        entry_role=entry_role,
        dates=SourcedValue(value=dates_vals[0], source=[_make_source_ref(tag, occurrence, 'd')]) if dates_vals else None,
        function=function_sv,
        source_tags=[tag],
        agent_type='personal',
        agent_index=agent_index,
        role_source=role_source
    )


def _extract_corporate_agent(field: pymarc.Field, tag: str, occurrence: int, entry_role: str, agent_index: int) -> Optional[AgentData]:
    """Extract corporate body agent (110/710).

    Args:
        field: MARC field object
        tag: MARC tag ('110' or '710')
        occurrence: Zero-based occurrence index
        entry_role: 'main' or 'added'
        agent_index: Stable ordering index for this agent

    Returns:
        AgentData or None if extraction fails
    """
    # Corporate names: $a (name) + $b (subordinate unit)
    name_parts = []
    sources = []

    name_vals = field.get_subfields('a')
    if name_vals:
        name_parts.append(name_vals[0])
        sources.append(_make_source_ref(tag, occurrence, 'a'))

    # Add subordinate units if present
    subordinate_vals = field.get_subfields('b')
    if subordinate_vals:
        name_parts.append(subordinate_vals[0])
        sources.append(_make_source_ref(tag, occurrence, 'b'))

    if not name_parts:
        return None

    full_name = ' '.join(name_parts)
    function_sv, role_source = _extract_role_from_field(field, tag, occurrence)

    return AgentData(
        name=SourcedValue(value=full_name, source=sources),
        entry_role=entry_role,
        dates=None,  # Corporate bodies typically don't have dates in name field
        function=function_sv,
        source_tags=[tag],
        agent_type='corporate',
        agent_index=agent_index,
        role_source=role_source
    )


def _extract_meeting_agent(field: pymarc.Field, tag: str, occurrence: int, entry_role: str, agent_index: int) -> Optional[AgentData]:
    """Extract meeting name agent (111/711).

    Args:
        field: MARC field object
        tag: MARC tag ('111' or '711')
        occurrence: Zero-based occurrence index
        entry_role: 'main' or 'added'
        agent_index: Stable ordering index for this agent

    Returns:
        AgentData or None if extraction fails
    """
    # Meeting names: $a (name) + $c (location) + $d (date) + $n (number)
    name_parts = []
    sources = []
    date_val = None
    date_source = None

    name_vals = field.get_subfields('a')
    if name_vals:
        name_parts.append(name_vals[0])
        sources.append(_make_source_ref(tag, occurrence, 'a'))

    # Add location if present
    location_vals = field.get_subfields('c')
    if location_vals:
        name_parts.append(location_vals[0])
        sources.append(_make_source_ref(tag, occurrence, 'c'))

    # Add number if present
    number_vals = field.get_subfields('n')
    if number_vals:
        name_parts.append(number_vals[0])
        sources.append(_make_source_ref(tag, occurrence, 'n'))

    # Extract date separately (for dates field)
    date_vals = field.get_subfields('d')
    if date_vals:
        date_val = date_vals[0]
        date_source = _make_source_ref(tag, occurrence, 'd')

    if not name_parts:
        return None

    full_name = ' '.join(name_parts)
    function_sv, role_source = _extract_role_from_field(field, tag, occurrence)

    return AgentData(
        name=SourcedValue(value=full_name, source=sources),
        entry_role=entry_role,
        dates=SourcedValue(value=date_val, source=[date_source]) if date_val else None,
        function=function_sv,
        source_tags=[tag],
        agent_type='meeting',
        agent_index=agent_index,
        role_source=role_source
    )


def extract_agents(record: pymarc.Record) -> List[AgentData]:
    """Extract authors/contributors from MARC 1XX and 7XX fields with occurrence indexing.

    Enhanced for agent integration (Stage 2):
    - Extracts personal names (100/700), corporate bodies (110/710), and meetings (111/711)
    - Determines role with priority: $4 relator code > $e relator term > inferred from tag
    - Tracks agent_type, agent_index, and role_source for normalization pipeline
    - Separates structural role (main/added entry) from bibliographic function (printer, editor, etc.)
    """
    agents = []
    agent_index = 0  # Stable ordering for agents within record

    # Track occurrence count per tag
    tag_occurrences = {}

    # Main entries (100, 110, 111, 130)
    # Note: 130 (uniform title) is skipped as it's not an agent
    main_tags = ['100', '110', '111']
    for tag in main_tags:
        fields = record.get_fields(tag)
        for field in fields:
            occ = tag_occurrences.get(tag, 0)
            tag_occurrences[tag] = occ + 1

            agent = None
            if tag == '100':
                agent = _extract_personal_agent(field, tag, occ, 'main', agent_index)
            elif tag == '110':
                agent = _extract_corporate_agent(field, tag, occ, 'main', agent_index)
            elif tag == '111':
                agent = _extract_meeting_agent(field, tag, occ, 'main', agent_index)

            if agent:
                agents.append(agent)
                agent_index += 1

    # Added entries (700, 710, 711, 730)
    # Note: 730 (uniform title) is skipped as it's not an agent
    added_tags = ['700', '710', '711']
    for tag in added_tags:
        fields = record.get_fields(tag)
        for field in fields:
            occ = tag_occurrences.get(tag, 0)
            tag_occurrences[tag] = occ + 1

            agent = None
            if tag == '700':
                agent = _extract_personal_agent(field, tag, occ, 'added', agent_index)
            elif tag == '710':
                agent = _extract_corporate_agent(field, tag, occ, 'added', agent_index)
            elif tag == '711':
                agent = _extract_meeting_agent(field, tag, occ, 'added', agent_index)

            if agent:
                agents.append(agent)
                agent_index += 1

    return agents


def extract_notes(record: pymarc.Record) -> List[NoteData]:
    """Extract notes from MARC 5XX fields with occurrence indexing."""
    notes = []

    # Track occurrence count per tag
    tag_occurrences = {}

    # Get all 5XX fields (500-599)
    note_fields = record.get_fields('500', '501', '502', '504', '505', '520', '590')

    for field in note_fields:
        tag = field.tag
        occ = tag_occurrences.get(tag, 0)
        tag_occurrences[tag] = occ + 1

        # Combine all subfields
        parts = []
        sources = []
        for subfield in field.subfields:
            code = subfield[0]
            value = subfield[1]
            # Skip control subfields
            if code not in ['2', '6', '8', '9']:
                parts.append(value)
                sources.append(_make_source_ref(tag, occ, code))

        if parts:
            note_str = ' '.join(parts)
            notes.append(NoteData(
                tag=tag,
                value=note_str,
                source=sources
            ))

    return notes


def extract_uniform_title(record: pymarc.Record) -> Optional[SourcedValue]:
    """Extract uniform title from MARC 240 field."""
    try:
        field_240 = record['240']
        if field_240:
            # Combine all subfields for uniform title
            title_parts = []
            sources = []
            for subfield in field_240.subfields:
                code = subfield[0]
                value = subfield[1]
                # Skip control subfields
                if code not in ['0', '6', '8', '9']:
                    title_parts.append(value)
                    sources.append(_make_source_ref('240', 0, code))

            if title_parts:
                return SourcedValue(value=' '.join(title_parts), source=sources)
    except KeyError:
        pass
    return None


def extract_variant_titles(record: pymarc.Record) -> List[SourcedValue]:
    """Extract variant titles from MARC 246 field (access points)."""
    variant_titles = []

    try:
        fields_246 = record.get_fields('246')
        for occ, field in enumerate(fields_246):
            # Combine all subfields for variant title
            title_parts = []
            sources = []
            for subfield in field.subfields:
                code = subfield[0]
                value = subfield[1]
                # Skip control subfields
                if code not in ['6', '8']:
                    title_parts.append(value)
                    sources.append(_make_source_ref('246', occ, code))

            if title_parts:
                variant_titles.append(SourcedValue(value=' '.join(title_parts), source=sources))
    except KeyError:
        pass

    return variant_titles


def extract_acquisition(record: pymarc.Record) -> List[SourcedValue]:
    """Extract acquisition/provenance events from MARC 541 field."""
    acquisitions = []

    try:
        fields_541 = record.get_fields('541')
        for occ, field in enumerate(fields_541):
            # Combine all subfields for acquisition info
            acq_parts = []
            sources = []
            for subfield in field.subfields:
                code = subfield[0]
                value = subfield[1]
                # Skip control subfields
                if code not in ['6', '8']:
                    acq_parts.append(value)
                    sources.append(_make_source_ref('541', occ, code))

            if acq_parts:
                acquisitions.append(SourcedValue(value=' '.join(acq_parts), source=sources))
    except KeyError:
        pass

    return acquisitions


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
    uniform_title = extract_uniform_title(record)
    variant_titles = extract_variant_titles(record)
    imprints = extract_imprints(record)
    languages = extract_languages(record)
    language_fixed = extract_language_fixed(record)
    subjects = extract_subjects(record)
    agents = extract_agents(record)
    notes = extract_notes(record)
    acquisition = extract_acquisition(record)

    # Build canonical record
    canonical = CanonicalRecord(
        source=source,
        title=title,
        uniform_title=uniform_title,
        variant_titles=variant_titles,
        imprints=imprints,
        languages=languages,
        language_fixed=language_fixed,
        subjects=subjects,
        agents=agents,
        notes=notes,
        acquisition=acquisition
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
