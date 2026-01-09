"""Tests for place frequency builder.

Tests basic place normalization and frequency counting logic.
"""

import pytest
from scripts.marc.build_place_freq import normalize_place_basic


class TestPlaceNormalization:
    """Test place normalization for frequency analysis."""

    def test_normalize_paris_with_colon(self):
        """Test Paris with trailing colon (reference record)."""
        assert normalize_place_basic("Paris :") == "paris"

    def test_normalize_paris_with_comma(self):
        """Test Paris with trailing comma."""
        assert normalize_place_basic("Paris,") == "paris"

    def test_normalize_bracketed_place(self):
        """Test bracketed place."""
        assert normalize_place_basic("[S.l.]") == "s.l."
        assert normalize_place_basic("[Paris]") == "paris"

    def test_normalize_with_multiple_trailing_punct(self):
        """Test place with multiple trailing punctuation."""
        assert normalize_place_basic("Paris :,") == "paris"
        assert normalize_place_basic("London ;/") == "london"

    def test_normalize_empty_string(self):
        """Test empty string returns None."""
        assert normalize_place_basic("") is None
        assert normalize_place_basic("   ") is None
        assert normalize_place_basic(None) is None

    def test_normalize_only_brackets(self):
        """Test string that becomes empty after bracket removal."""
        assert normalize_place_basic("[]") is None
        assert normalize_place_basic("[ ]") is None

    def test_normalize_unicode(self):
        """Test unicode normalization."""
        # Hebrew places should be preserved
        assert normalize_place_basic("ירושלים") == "ירושלים"
        assert normalize_place_basic("אמשטרדם") == "אמשטרדם"

    def test_normalize_with_whitespace(self):
        """Test whitespace collapsing."""
        assert normalize_place_basic("Paris   :") == "paris"
        assert normalize_place_basic("  London  ") == "london"

    def test_normalize_latin_place(self):
        """Test Latin place names."""
        assert normalize_place_basic("Venetiis :") == "venetiis"
        assert normalize_place_basic("Lipsiae") == "lipsiae"

    def test_deterministic(self):
        """Test that normalization is deterministic."""
        inputs = ["Paris :", "London,", "[Berlin]", "Venetiis :"]
        for inp in inputs:
            result1 = normalize_place_basic(inp)
            result2 = normalize_place_basic(inp)
            assert result1 == result2, f"Normalization not deterministic for: {inp}"

    def test_casefold(self):
        """Test casefolding."""
        assert normalize_place_basic("PARIS") == "paris"
        assert normalize_place_basic("Paris") == "paris"
        assert normalize_place_basic("pArIs") == "paris"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
