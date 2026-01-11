"""Tests for QueryPlan Pydantic models.

Validates schema enforcement, filter validation, and edge cases.
"""

import pytest
from pydantic import ValidationError

from scripts.schemas import FilterField, FilterOp, Filter, QueryPlan


class TestFilter:
    """Tests for Filter model validation."""

    def test_valid_equals_filter(self):
        """EQUALS filter with string value should validate."""
        f = Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")
        assert f.field == FilterField.PUBLISHER
        assert f.op == FilterOp.EQUALS
        assert f.value == "oxford"
        assert f.negate is False

    def test_valid_contains_filter(self):
        """CONTAINS filter with string value should validate."""
        f = Filter(field=FilterField.TITLE, op=FilterOp.CONTAINS, value="historia")
        assert f.field == FilterField.TITLE
        assert f.op == FilterOp.CONTAINS
        assert f.value == "historia"

    def test_valid_range_filter(self):
        """RANGE filter with start and end should validate."""
        f = Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)
        assert f.field == FilterField.YEAR
        assert f.op == FilterOp.RANGE
        assert f.start == 1500
        assert f.end == 1599

    def test_valid_in_filter(self):
        """IN filter with list of strings should validate."""
        f = Filter(field=FilterField.LANGUAGE, op=FilterOp.IN, value=["lat", "heb", "eng"])
        assert f.field == FilterField.LANGUAGE
        assert f.op == FilterOp.IN
        assert f.value == ["lat", "heb", "eng"]

    def test_range_missing_start_fails(self):
        """RANGE filter missing start should fail."""
        with pytest.raises(ValidationError, match="RANGE operation requires both start and end"):
            Filter(field=FilterField.YEAR, op=FilterOp.RANGE, end=1599)

    def test_range_missing_end_fails(self):
        """RANGE filter missing end should fail."""
        with pytest.raises(ValidationError, match="RANGE operation requires both start and end"):
            Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500)

    def test_range_start_greater_than_end_fails(self):
        """RANGE filter with start > end should fail."""
        with pytest.raises(ValidationError, match="start .* must be <= end"):
            Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1600, end=1500)

    def test_equals_missing_value_fails(self):
        """EQUALS filter missing value should fail."""
        with pytest.raises(ValidationError, match="EQUALS operation requires value"):
            Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS)

    def test_contains_missing_value_fails(self):
        """CONTAINS filter missing value should fail."""
        with pytest.raises(ValidationError, match="CONTAINS operation requires value"):
            Filter(field=FilterField.TITLE, op=FilterOp.CONTAINS)

    def test_equals_with_list_value_fails(self):
        """EQUALS filter with list value should fail."""
        with pytest.raises(ValidationError, match="requires value to be a string"):
            Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value=["a", "b"])

    def test_in_missing_value_fails(self):
        """IN filter missing value should fail."""
        with pytest.raises(ValidationError, match="IN operation requires value"):
            Filter(field=FilterField.LANGUAGE, op=FilterOp.IN)

    def test_in_with_string_value_fails(self):
        """IN filter with string value should fail."""
        with pytest.raises(ValidationError, match="requires value to be a list"):
            Filter(field=FilterField.LANGUAGE, op=FilterOp.IN, value="lat")

    def test_in_with_non_string_list_fails(self):
        """IN filter with non-string list items should fail."""
        with pytest.raises(ValidationError, match="Input should be a valid string"):
            Filter(field=FilterField.LANGUAGE, op=FilterOp.IN, value=["lat", 123, "eng"])

    def test_filter_with_confidence(self):
        """Filter with valid confidence should validate."""
        f = Filter(
            field=FilterField.PUBLISHER,
            op=FilterOp.EQUALS,
            value="oxford",
            confidence=0.85
        )
        assert f.confidence == 0.85

    def test_filter_with_invalid_confidence_fails(self):
        """Filter with out-of-range confidence should fail."""
        with pytest.raises(ValidationError):
            Filter(
                field=FilterField.PUBLISHER,
                op=FilterOp.EQUALS,
                value="oxford",
                confidence=1.5
            )

    def test_filter_with_negate(self):
        """Filter with negate=True should validate."""
        f = Filter(
            field=FilterField.PUBLISHER,
            op=FilterOp.EQUALS,
            value="oxford",
            negate=True
        )
        assert f.negate is True

    def test_filter_with_notes(self):
        """Filter with notes should validate."""
        f = Filter(
            field=FilterField.PUBLISHER,
            op=FilterOp.EQUALS,
            value="oxford",
            notes="Parsed from 'published by oxford'"
        )
        assert f.notes == "Parsed from 'published by oxford'"


class TestQueryPlan:
    """Tests for QueryPlan model validation."""

    def test_minimal_valid_plan(self):
        """Minimal valid plan should validate."""
        plan = QueryPlan(query_text="test query")
        assert plan.version == "1.0"
        assert plan.query_text == "test query"
        assert plan.filters == []
        assert plan.soft_filters == []
        assert plan.limit is None
        assert plan.debug == {}  # debug defaults to empty dict

    def test_plan_with_single_filter(self):
        """Plan with one filter should validate."""
        plan = QueryPlan(
            query_text="books by oxford",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")]
        )
        assert len(plan.filters) == 1
        assert plan.filters[0].value == "oxford"

    def test_plan_with_multiple_filters(self):
        """Plan with multiple filters should validate."""
        plan = QueryPlan(
            query_text="books by oxford 1500-1599",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford"),
                Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)
            ]
        )
        assert len(plan.filters) == 2

    def test_plan_with_limit(self):
        """Plan with limit should validate."""
        plan = QueryPlan(query_text="test", limit=100)
        assert plan.limit == 100

    def test_plan_with_zero_limit_fails(self):
        """Plan with zero limit should fail."""
        with pytest.raises(ValidationError):
            QueryPlan(query_text="test", limit=0)

    def test_plan_with_negative_limit_fails(self):
        """Plan with negative limit should fail."""
        with pytest.raises(ValidationError):
            QueryPlan(query_text="test", limit=-1)

    def test_plan_with_debug_info(self):
        """Plan with debug dict should validate."""
        plan = QueryPlan(
            query_text="test",
            debug={"parser": "heuristic", "patterns_matched": ["publisher", "year_range"]}
        )
        assert plan.debug["parser"] == "heuristic"

    def test_plan_json_serialization(self):
        """Plan should serialize to JSON."""
        plan = QueryPlan(
            query_text="books by oxford 1500-1599",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford"),
                Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)
            ]
        )
        json_data = plan.model_dump()
        assert json_data["version"] == "1.0"
        assert json_data["query_text"] == "books by oxford 1500-1599"
        assert len(json_data["filters"]) == 2

    def test_plan_from_json(self):
        """Plan should deserialize from JSON."""
        json_data = {
            "version": "1.0",
            "query_text": "books by oxford",
            "filters": [
                {"field": "publisher", "op": "EQUALS", "value": "oxford", "negate": False}
            ],
            "soft_filters": [],
            "limit": None,
            "debug": {}  # debug is now a required field with default empty dict
        }
        plan = QueryPlan(**json_data)
        assert plan.query_text == "books by oxford"
        assert len(plan.filters) == 1

    def test_plan_missing_query_text_fails(self):
        """Plan missing query_text should fail."""
        with pytest.raises(ValidationError):
            QueryPlan()

    def test_plan_with_invalid_filter_fails(self):
        """Plan with invalid filter should fail during filter validation."""
        with pytest.raises(ValidationError):
            QueryPlan(
                query_text="test",
                filters=[
                    Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1600, end=1500)
                ]
            )
