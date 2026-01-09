"""Data models for MARC XML canonical records."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class SourcedValue(BaseModel):
    """A value with its MARC source provenance (field$subfield)."""

    value: Any = Field(..., description="The extracted value (raw)")
    source: List[str] = Field(..., description="MARC field$subfield sources (e.g., ['260$a', '260$b'])")


class ImprintData(BaseModel):
    """Raw imprint/publication data from MARC 260/264 with provenance."""

    place: Optional[SourcedValue] = Field(None, description="Place of publication with source")
    publisher: Optional[SourcedValue] = Field(None, description="Publisher name with source")
    date: Optional[SourcedValue] = Field(None, description="Publication date with source")
    manufacturer: Optional[SourcedValue] = Field(None, description="Manufacturer with source")


class AgentData(BaseModel):
    """Author/contributor data with provenance."""

    name: SourcedValue = Field(..., description="Agent name with source")
    role: Optional[str] = Field(None, description="Role (main_entry, added_entry)")
    dates: Optional[SourcedValue] = Field(None, description="Life dates with source")
    relator: Optional[SourcedValue] = Field(None, description="Relator term/code with source")


class CanonicalRecord(BaseModel):
    """Canonical bibliographic record extracted from MARC XML.

    All values are RAW - no normalization at this stage.
    Each value includes its MARC source (field$subfield).
    """

    record_id: SourcedValue = Field(..., description="Record identifier with source (001)")
    title: Optional[SourcedValue] = Field(None, description="Full title with sources (245$a$b$c)")

    imprint: Optional[ImprintData] = Field(
        None,
        description="Publication info with sources (260/264)"
    )

    languages: List[SourcedValue] = Field(
        default_factory=list,
        description="Language codes with sources (041$a or 008/35-37)"
    )

    subjects: List[SourcedValue] = Field(
        default_factory=list,
        description="Subject headings with sources (6XX$a$x$y$z)"
    )

    agents: List[AgentData] = Field(
        default_factory=list,
        description="Authors/contributors with sources (1XX/7XX)"
    )

    notes: List[SourcedValue] = Field(
        default_factory=list,
        description="Notes with sources (5XX$a)"
    )

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "record_id": {
                    "value": "990014605730204146",
                    "source": ["001"]
                },
                "title": {
                    "value": "Ferreira's falconry : being a translation...",
                    "source": ["245$a", "245$b", "245$c"]
                },
                "imprint": {
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
                    }
                },
                "languages": [
                    {"value": "eng", "source": ["041$a"]}
                ],
                "subjects": [
                    {"value": "Falconry -- Early works to 1800", "source": ["650$a", "650$v"]},
                    {"value": "Hunting -- Early works to 1800", "source": ["650$a", "650$v"]}
                ],
                "agents": [
                    {
                        "name": {"value": "Fernandes Ferreira, Diogo", "source": ["100$a"]},
                        "role": "main_entry",
                        "dates": None,
                        "relator": None
                    },
                    {
                        "name": {"value": "Jack, Anthony", "source": ["700$a"]},
                        "role": "added_entry",
                        "dates": None,
                        "relator": None
                    }
                ],
                "notes": [
                    {"value": "Limited ed. of 100 copies; copy no. 86", "source": ["500$a"]},
                    {"value": "MP/TT", "source": ["590$a"]}
                ]
            }
        }


class ExtractionReport(BaseModel):
    """Summary report of MARC XML extraction."""

    total_records: int = Field(..., description="Total records processed")
    successful_extractions: int = Field(..., description="Records successfully extracted")
    failed_extractions: int = Field(0, description="Records that failed to extract")

    # Field coverage stats
    records_with_title: int = Field(0, description="Records with title field")
    records_with_imprint: int = Field(0, description="Records with imprint data")
    records_with_languages: int = Field(0, description="Records with language codes")
    records_with_subjects: int = Field(0, description="Records with subject headings")
    records_with_agents: int = Field(0, description="Records with agents/authors")
    records_with_notes: int = Field(0, description="Records with notes")

    # Missing field details
    records_missing_title: List[str] = Field(
        default_factory=list,
        description="Record IDs missing title"
    )
    records_missing_imprint: List[str] = Field(
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
                "total_records": 100,
                "successful_extractions": 98,
                "failed_extractions": 2,
                "records_with_title": 98,
                "records_with_imprint": 95,
                "records_with_languages": 90,
                "records_with_subjects": 85,
                "records_with_agents": 92,
                "records_with_notes": 70,
                "records_missing_title": ["990014605730204146"],
                "records_missing_imprint": ["990014605730204146", "990014614110204146"],
                "field_usage_counts": {
                    "245$a": 98,
                    "245$b": 95,
                    "260$a": 90,
                    "260$b": 85,
                    "260$c": 95,
                    "041$a": 90,
                    "650$a": 120
                }
            }
        }
