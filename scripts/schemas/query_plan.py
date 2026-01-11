"""QueryPlan Pydantic models for M4.

Defines the schema for natural language query → structured plan conversion.
All filters use AND semantics. Soft filters are optional (ignored in M4).
"""

from enum import Enum
from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class FilterField(str, Enum):
    """Supported filter fields (maps to M3 database columns)."""
    PUBLISHER = "publisher"
    IMPRINT_PLACE = "imprint_place"
    YEAR = "year"
    LANGUAGE = "language"
    TITLE = "title"
    SUBJECT = "subject"
    AGENT = "agent"  # Legacy - kept for backward compatibility
    AGENT_NORM = "agent_norm"  # Stage 5: Query normalized agent names
    AGENT_ROLE = "agent_role"  # Stage 5: Query by role (printer, translator, etc.)
    AGENT_TYPE = "agent_type"  # Stage 5: Query by type (personal, corporate, meeting)


class FilterOp(str, Enum):
    """Supported filter operations."""
    EQUALS = "EQUALS"
    CONTAINS = "CONTAINS"
    RANGE = "RANGE"
    IN = "IN"


class Filter(BaseModel):
    """A single filter condition.

    Depending on the operation, different fields are required:
    - EQUALS/CONTAINS: requires value (string)
    - IN: requires value (list of strings)
    - RANGE: requires start and end (integers)
    """
    model_config = ConfigDict(extra='forbid')  # For OpenAI Responses API compatibility

    field: FilterField
    op: FilterOp
    value: Optional[Union[str, List[str]]] = None  # For EQUALS/CONTAINS/IN
    start: Optional[int] = None  # For RANGE
    end: Optional[int] = None    # For RANGE
    negate: bool = False
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    notes: Optional[str] = None

    @model_validator(mode='after')
    def validate_filter(self):
        """Validate filter based on operation type."""
        if self.op == FilterOp.RANGE:
            if self.start is None or self.end is None:
                raise ValueError("RANGE operation requires both start and end")
            if self.start > self.end:
                raise ValueError(f"RANGE start ({self.start}) must be <= end ({self.end})")

        elif self.op in [FilterOp.EQUALS, FilterOp.CONTAINS]:
            if self.value is None:
                raise ValueError(f"{self.op} operation requires value")
            if not isinstance(self.value, str):
                raise ValueError(f"{self.op} operation requires value to be a string")

        elif self.op == FilterOp.IN:
            if self.value is None:
                raise ValueError("IN operation requires value")
            if not isinstance(self.value, list):
                raise ValueError("IN operation requires value to be a list")
            if not all(isinstance(v, str) for v in self.value):
                raise ValueError("IN operation requires all values to be strings")

        return self


class QueryPlan(BaseModel):
    """Structured query plan.

    This is the validated intermediate representation between NL query and SQL.
    All normalization and validation happens here before SQL generation.
    """
    model_config = ConfigDict(extra='forbid')  # For OpenAI Responses API compatibility

    version: str = "1.0"
    query_text: str
    filters: List[Filter] = Field(default_factory=list)
    soft_filters: List[Filter] = Field(default_factory=list)  # Optional, ignored in M4
    limit: Optional[int] = Field(None, gt=0)
    # Debug field - added programmatically after LLM generation, not part of LLM schema
    debug: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('filters', 'soft_filters')
    @classmethod
    def validate_filter_list(cls, v):
        """Ensure filters is a list."""
        if not isinstance(v, list):
            raise ValueError("filters must be a list")
        return v
