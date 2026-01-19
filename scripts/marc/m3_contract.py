"""M3 Database Schema Contract.

Explicit contract between M3 schema (m3_schema.sql) and M4 query builder (db_adapter.py).
All table and column names are defined as constants here to prevent silent breakage
when schema evolves.

This module serves as the single source of truth for M3 database structure.
If you modify m3_schema.sql, you MUST update this contract accordingly.
"""


class M3Tables:
    """M3 database table names."""

    RECORDS = "records"
    TITLES = "titles"
    IMPRINTS = "imprints"
    SUBJECTS = "subjects"
    AGENTS = "agents"
    LANGUAGES = "languages"
    NOTES = "notes"
    PHYSICAL_DESCRIPTIONS = "physical_descriptions"
    AUTHORITY_ENRICHMENT = "authority_enrichment"

    # FTS5 virtual tables
    TITLES_FTS = "titles_fts"
    SUBJECTS_FTS = "subjects_fts"


class M3Columns:
    """M3 database column names organized by table."""

    # records table
    class Records:
        """Columns in records table."""
        ID = "id"
        MMS_ID = "mms_id"
        SOURCE_FILE = "source_file"
        CREATED_AT = "created_at"
        JSONL_LINE_NUMBER = "jsonl_line_number"

    # titles table
    class Titles:
        """Columns in titles table."""
        ID = "id"
        RECORD_ID = "record_id"
        TITLE_TYPE = "title_type"
        VALUE = "value"
        SOURCE = "source"

    # imprints table (M1 raw + M2 normalized)
    class Imprints:
        """Columns in imprints table."""
        ID = "id"
        RECORD_ID = "record_id"
        OCCURRENCE = "occurrence"

        # M1 raw values
        DATE_RAW = "date_raw"
        PLACE_RAW = "place_raw"
        PUBLISHER_RAW = "publisher_raw"
        MANUFACTURER_RAW = "manufacturer_raw"
        SOURCE_TAGS = "source_tags"

        # M2 normalized date
        DATE_START = "date_start"
        DATE_END = "date_end"
        DATE_LABEL = "date_label"
        DATE_CONFIDENCE = "date_confidence"
        DATE_METHOD = "date_method"

        # M2 normalized place
        PLACE_NORM = "place_norm"
        PLACE_DISPLAY = "place_display"
        PLACE_CONFIDENCE = "place_confidence"
        PLACE_METHOD = "place_method"

        # M2 normalized publisher
        PUBLISHER_NORM = "publisher_norm"
        PUBLISHER_DISPLAY = "publisher_display"
        PUBLISHER_CONFIDENCE = "publisher_confidence"
        PUBLISHER_METHOD = "publisher_method"

        # M1 country from 008/15-17
        COUNTRY_CODE = "country_code"
        COUNTRY_NAME = "country_name"

    # subjects table
    class Subjects:
        """Columns in subjects table."""
        ID = "id"
        RECORD_ID = "record_id"
        VALUE = "value"
        SOURCE_TAG = "source_tag"
        SCHEME = "scheme"
        HEADING_LANG = "heading_lang"
        AUTHORITY_URI = "authority_uri"
        PARTS = "parts"
        SOURCE = "source"

    # agents table (M1 raw + M2 normalized)
    class Agents:
        """Columns in agents table."""
        ID = "id"
        RECORD_ID = "record_id"
        AGENT_INDEX = "agent_index"

        # M1 raw fields
        AGENT_RAW = "agent_raw"
        AGENT_TYPE = "agent_type"
        ROLE_RAW = "role_raw"
        ROLE_SOURCE = "role_source"
        AUTHORITY_URI = "authority_uri"

        # M2 normalized fields
        AGENT_NORM = "agent_norm"
        AGENT_CONFIDENCE = "agent_confidence"
        AGENT_METHOD = "agent_method"
        AGENT_NOTES = "agent_notes"

        ROLE_NORM = "role_norm"
        ROLE_CONFIDENCE = "role_confidence"
        ROLE_METHOD = "role_method"

        # Provenance
        PROVENANCE_JSON = "provenance_json"

    # languages table
    class Languages:
        """Columns in languages table."""
        ID = "id"
        RECORD_ID = "record_id"
        CODE = "code"
        SOURCE = "source"

    # notes table
    class Notes:
        """Columns in notes table."""
        ID = "id"
        RECORD_ID = "record_id"
        TAG = "tag"
        VALUE = "value"
        SOURCE = "source"

    # physical_descriptions table
    class PhysicalDescriptions:
        """Columns in physical_descriptions table."""
        ID = "id"
        RECORD_ID = "record_id"
        VALUE = "value"
        SOURCE = "source"

    # authority_enrichment table
    class AuthorityEnrichment:
        """Columns in authority_enrichment table."""
        ID = "id"
        AUTHORITY_URI = "authority_uri"
        NLI_ID = "nli_id"
        WIKIDATA_ID = "wikidata_id"
        VIAF_ID = "viaf_id"
        ISNI_ID = "isni_id"
        LOC_ID = "loc_id"
        LABEL = "label"
        DESCRIPTION = "description"
        PERSON_INFO = "person_info"
        PLACE_INFO = "place_info"
        IMAGE_URL = "image_url"
        WIKIPEDIA_URL = "wikipedia_url"
        SOURCE = "source"
        CONFIDENCE = "confidence"
        FETCHED_AT = "fetched_at"
        EXPIRES_AT = "expires_at"


# Commonly used table aliases in SQL queries
class M3Aliases:
    """Common table aliases used in M4 query builder."""
    RECORDS = "r"
    IMPRINTS = "i"
    LANGUAGES = "l"
    TITLES = "t"
    SUBJECTS = "s"
    AGENTS = "a"
    AUTHORITY_ENRICHMENT = "ae"
