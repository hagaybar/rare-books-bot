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
    COUNTRY = "country"  # Country of publication from MARC 008/15-17
    YEAR = "year"
    LANGUAGE = "language"
    TITLE = "title"
    SUBJECT = "subject"
    PHYSICAL_DESC = "physical_desc"  # MARC 300 — physical form ("maps", "plates")
    # Agent fields - use AGENT_NORM/AGENT_ROLE/AGENT_TYPE for new code
    AGENT = "agent"  # Deprecated: searches raw agent_raw column. Use AGENT_NORM instead.
    AGENT_NORM = "agent_norm"  # Preferred: Query normalized agent names (comma-insensitive)
    AGENT_ROLE = "agent_role"  # Query by role: printer, translator, editor, etc.
    AGENT_TYPE = "agent_type"  # Query by type: personal, corporate, meeting


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
        """Validate filter based on operation type and field/op contract.

        Note: ``$step_N`` references are stored as plain strings even for
        IN operations.  The executor resolves them at execution time.  We
        therefore allow a string value for IN when it matches a step ref.

        Field/op contract (issue #56): combinations that build_where_clause
        has no execution arm for, and that no upstream coercion repairs, are
        rejected HERE with a clear message instead of dying later in SQL
        generation as an unhandled ValueError (the failure class issue #44
        fixed for year EQUALS).

        Empty-string contract (issue #49): EQUALS/CONTAINS values and IN
        list members must be non-empty after stripping whitespace.  An
        empty-string filter validates against the type contract, executes,
        matches nothing, and returns a silent 0 — absence is reified in the
        DB as a sentinel (e.g. imprint_place '[sine loco]'), never as ''.
        """
        import re
        _step_ref = re.compile(r"^\$step_\d+$")

        # --- field/op contract (issue #56) ---
        if self.op == FilterOp.RANGE and self.field != FilterField.YEAR:
            raise ValueError(
                f"RANGE is only supported for field 'year', "
                f"not '{self.field.value}'"
            )
        if self.field == FilterField.YEAR and self.op in (
            FilterOp.EQUALS, FilterOp.CONTAINS,
        ):
            raise ValueError(
                f"year does not support {self.op.value}: a single year must "
                f"be expressed as RANGE start=end (the interpreter coerces "
                f"parseable values automatically) — got value {self.value!r} "
                f"which could not be interpreted as a year"
            )
        if (
            self.field == FilterField.YEAR
            and self.op == FilterOp.IN
            and isinstance(self.value, list)
        ):
            non_years = [
                v for v in self.value
                if not str(v).strip().lstrip("-").isdigit()
            ]
            if non_years:
                raise ValueError(
                    f"year IN requires integer year values; "
                    f"got {non_years!r}"
                )
        if self.field == FilterField.PHYSICAL_DESC and self.op == FilterOp.EQUALS:
            raise ValueError(
                "physical_desc supports CONTAINS (substring) or IN "
                "(any-of substring) only — MARC 300 strings are free text "
                "with no exact-match representation"
            )
        if self.field == FilterField.AGENT and self.op != FilterOp.CONTAINS:
            raise ValueError(
                f"agent (deprecated) supports CONTAINS only; "
                f"use agent_norm for {self.op.value}"
            )

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
            if not self.value.strip():
                raise ValueError(
                    f"{self.op.value} operation requires a non-empty value: "
                    f"an empty-string filter matches nothing and hides a "
                    f"planning failure as a silent 0 (issue #49). Absence is "
                    f"reified as a sentinel value (e.g. imprint_place "
                    f"'[sine loco]'), never as an empty string"
                )

        elif self.op == FilterOp.IN:
            if self.value is None:
                raise ValueError("IN operation requires value")
            # Allow string values that are $step_N references (resolved at execution time)
            if isinstance(self.value, str):
                if not _step_ref.match(self.value):
                    raise ValueError("IN operation requires value to be a list")
            elif isinstance(self.value, list):
                if not self.value:
                    raise ValueError("IN operation requires a non-empty list")
                if not all(isinstance(v, str) for v in self.value):
                    raise ValueError("IN operation requires all values to be strings")
                if any(not v.strip() for v in self.value):
                    raise ValueError(
                        "IN operation requires non-empty string values: "
                        "empty-string members match nothing and hide a "
                        "planning failure as a silent 0 (issue #49)"
                    )
            else:
                raise ValueError("IN operation requires value to be a list")

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
