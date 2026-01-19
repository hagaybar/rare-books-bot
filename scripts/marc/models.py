"""Data models for MARC XML canonical records."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class SourcedValue(BaseModel):
    """A value with its MARC source provenance (field$subfield)."""

    value: Any = Field(..., description="The extracted value (raw)")
    source: List[str] = Field(..., description="MARC field$subfield sources (e.g., ['260$a', '260$b'])")


class ImprintData(BaseModel):
    """Raw imprint/publication data from MARC 260/264 with provenance.

    Note: Rare books can have multiple imprints. This represents one imprint statement.
    """

    place: Optional[SourcedValue] = Field(None, description="Place of publication with source")
    publisher: Optional[SourcedValue] = Field(None, description="Publisher name with source")
    date: Optional[SourcedValue] = Field(None, description="Publication date with source")
    manufacturer: Optional[SourcedValue] = Field(None, description="Manufacturer with source")
    source_tags: List[str] = Field(..., description="MARC tags used (e.g., ['260'] or ['264'])")


class AgentData(BaseModel):
    """Author/contributor data with provenance.

    Separates structural role (main/added entry) from bibliographic function (printer, editor, etc.).
    Enhanced for agent integration with type tracking, role source, and stable ordering.
    """

    name: SourcedValue = Field(..., description="Agent name with source")
    entry_role: str = Field(..., description="Structural role: 'main' or 'added'")
    function: Optional[SourcedValue] = Field(None, description="Bibliographic function from relator (printer, editor, etc.)")
    dates: Optional[SourcedValue] = Field(None, description="Life dates with source")
    source_tags: List[str] = Field(..., description="MARC tags used (e.g., ['100'] or ['700'])")

    # NEW FIELDS for agent integration (Stage 1)
    agent_type: str = Field(
        default="personal",
        description="Agent type: 'personal' (100/700), 'corporate' (110/710), or 'meeting' (111/711)"
    )
    agent_index: Optional[int] = Field(
        default=None,
        description="Stable ordering index for agents within a record (for repeatability)"
    )
    role_source: Optional[str] = Field(
        default=None,
        description="Source of role/function: 'relator_code' ($4), 'relator_term' ($e), 'inferred_from_tag', or 'unknown'"
    )
    authority_uri: Optional[SourcedValue] = Field(
        default=None,
        description="Authority URI from $0 subfield (e.g., NLI/VIAF/LC authority link)"
    )


class SubjectData(BaseModel):
    """Subject heading with display string and structured parts."""

    value: str = Field(..., description="Display string (e.g., 'Rare books -- Bibliography -- Catalogs')")
    source: List[str] = Field(..., description="MARC field$subfield sources with occurrence (e.g., ['650[0]$a', '650[0]$v'])")
    parts: Dict[str, Any] = Field(..., description="Structured parts by subfield code (e.g., {'a':'Rare books', 'v':['Bibliography','Catalogs']})")
    source_tag: str = Field(..., description="MARC tag (e.g., '650', '651')")
    scheme: Optional[SourcedValue] = Field(None, description="Subject scheme from $2 (e.g., 'nli', 'lcsh')")
    heading_lang: Optional[SourcedValue] = Field(None, description="Heading language from $9 (e.g., 'lat', 'eng')")
    authority_uri: Optional[SourcedValue] = Field(None, description="Authority URI from $0 subfield (e.g., NLI/VIAF/LC authority link)")


class NoteData(BaseModel):
    """Note with explicit tag for easier filtering."""

    tag: str = Field(..., description="MARC tag (e.g., '500', '590')")
    value: str = Field(..., description="Note text")
    source: List[str] = Field(..., description="MARC field$subfield sources")


class SourceMetadata(BaseModel):
    """Record-level source metadata for traceability."""

    source_file: Optional[str] = Field(None, description="Source MARC XML filename")
    control_number: SourcedValue = Field(..., description="MARC 001 control number")


class CanonicalRecord(BaseModel):
    """Canonical bibliographic record extracted from MARC XML.

    All values are RAW - no normalization at this stage.
    Each value includes its MARC source (field$subfield).
    Structure is optimized for queryability in later stages (M2 SQLite, M3 normalization).
    """

    source: SourceMetadata = Field(..., description="Record-level source metadata")

    title: Optional[SourcedValue] = Field(None, description="Full title with sources (245$a$b$c)")
    uniform_title: Optional[SourcedValue] = Field(None, description="Uniform title from 240 field")
    variant_titles: List[SourcedValue] = Field(
        default_factory=list,
        description="Variant titles from 246 field (access points)"
    )

    imprints: List[ImprintData] = Field(
        default_factory=list,
        description="Publication info with sources (260/264). Array to support multiple imprints in rare books."
    )

    languages: List[SourcedValue] = Field(
        default_factory=list,
        description="Language codes from 041$a"
    )

    language_fixed: Optional[SourcedValue] = Field(
        None,
        description="Fixed language code from 008/35-37 (when used as fallback or for consistency check)"
    )

    country_code_fixed: Optional[SourcedValue] = Field(
        None,
        description="Fixed country code from 008/15-17 (place of publication/production)"
    )

    subjects: List[SubjectData] = Field(
        default_factory=list,
        description="Subject headings with display + structured parts (6XX)"
    )

    agents: List[AgentData] = Field(
        default_factory=list,
        description="Authors/contributors with separated structural/bibliographic roles (1XX/7XX)"
    )

    notes: List[NoteData] = Field(
        default_factory=list,
        description="Notes with explicit tags (5XX)"
    )

    acquisition: List[SourcedValue] = Field(
        default_factory=list,
        description="Acquisition/provenance events from 541 field"
    )

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "source": {
                    "source_file": "BIBLIOGRAPHIC_2026_01.xml",
                    "control_number": {
                        "value": "990014605730204146",
                        "source": ["001"]
                    }
                },
                "title": {
                    "value": "Ferreira's falconry : being a translation...",
                    "source": ["245$a", "245$b", "245$c"]
                },
                "imprints": [
                    {
                        "place": {
                            "value": "[S.l.] :",
                            "source": ["260$a"]
                        },
                        "publisher": {
                            "value": "A. Jack,",
                            "source": ["260$b"]
                        },
                        "date": {
                            "value": "c1996",
                            "source": ["260$c"]
                        },
                        "manufacturer": {
                            "value": "Signet press",
                            "source": ["260$f"]
                        },
                        "source_tags": ["260"]
                    }
                ],
                "languages": [
                    {"value": "eng", "source": ["041$a"]}
                ],
                "language_fixed": {
                    "value": "eng",
                    "source": ["008/35-37"]
                },
                "subjects": [
                    {
                        "value": "Falconry -- Early works to 1800",
                        "source": ["650$a", "650$v"],
                        "parts": {
                            "a": "Falconry",
                            "v": ["Early works to 1800"]
                        },
                        "source_tag": "650"
                    }
                ],
                "agents": [
                    {
                        "name": {"value": "Fernandes Ferreira, Diogo", "source": ["100$a"]},
                        "entry_role": "main",
                        "function": None,
                        "dates": None,
                        "source_tags": ["100"]
                    },
                    {
                        "name": {"value": "Jack, Anthony", "source": ["700$a"]},
                        "entry_role": "added",
                        "function": {
                            "value": "translator",
                            "source": ["700$e"]
                        },
                        "dates": None,
                        "source_tags": ["700"]
                    }
                ],
                "notes": [
                    {
                        "tag": "500",
                        "value": "Limited ed. of 100 copies; copy no. 86",
                        "source": ["500$a"]
                    },
                    {
                        "tag": "590",
                        "value": "MP/TT",
                        "source": ["590$a"]
                    }
                ]
            }
        }


class ExtractionReport(BaseModel):
    """Summary report of MARC XML extraction."""

    source_file: str = Field(..., description="Source MARC XML filename")
    total_records: int = Field(..., description="Total records processed")
    successful_extractions: int = Field(..., description="Records successfully extracted")
    failed_extractions: int = Field(0, description="Records that failed to extract")

    # Field coverage stats
    records_with_title: int = Field(0, description="Records with title field")
    records_with_imprints: int = Field(0, description="Records with imprint data")
    records_with_languages: int = Field(0, description="Records with language codes (041$a)")
    records_with_language_fixed: int = Field(0, description="Records with fixed language (008/35-37)")
    records_with_subjects: int = Field(0, description="Records with subject headings")
    records_with_agents: int = Field(0, description="Records with agents/authors")
    records_with_notes: int = Field(0, description="Records with notes")

    # Missing field details
    records_missing_title: List[str] = Field(
        default_factory=list,
        description="Record IDs missing title"
    )
    records_missing_imprints: List[str] = Field(
        default_factory=list,
        description="Record IDs missing imprint"
    )

    # Most common MARC field$subfield combinations used
    field_usage_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of how many times each MARC field$subfield was used"
    )

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "source_file": "BIBLIOGRAPHIC_2026_01.xml",
                "total_records": 100,
                "successful_extractions": 98,
                "failed_extractions": 2,
                "records_with_title": 98,
                "records_with_imprints": 95,
                "records_with_languages": 90,
                "records_with_language_fixed": 98,
                "records_with_subjects": 85,
                "records_with_agents": 92,
                "records_with_notes": 70,
                "records_missing_title": ["990014605730204146"],
                "records_missing_imprints": ["990014605730204146", "990014614110204146"],
                "field_usage_counts": {
                    "245$a": 98,
                    "245$b": 95,
                    "260$a": 90,
                    "260$b": 85,
                    "260$c": 95,
                    "041$a": 90,
                    "008/35-37": 98,
                    "650$a": 120
                }
            }
        }
