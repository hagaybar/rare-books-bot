"""Tests for M2 normalization.

Tests all date normalization rules and place/publisher normalization
using the reference record MMS 990011964120204146 and additional cases.
"""

import json
from pathlib import Path
import pytest

from scripts.marc.normalize import (
    normalize_date, normalize_place, normalize_publisher, enrich_m2, parse_hebrew_year
)


class TestDateNormalization:
    """Test date normalization rules."""

    def test_exact_year(self):
        """Test exact year pattern (confidence=0.99)."""
        result = normalize_date("1680", "test_path")
        assert result.start == 1680
        assert result.end == 1680
        assert result.method == "year_exact"
        assert result.confidence == 0.99
        assert result.warnings == []

    def test_bracketed_year(self):
        """Test bracketed year pattern (confidence=0.95)."""
        result = normalize_date("[1680]", "test_path")
        assert result.start == 1680
        assert result.end == 1680
        assert result.method == "year_bracketed"
        assert result.confidence == 0.95
        assert result.warnings == []

    def test_circa_with_dot(self):
        """Test circa with dot (confidence=0.80, ±5 years)."""
        result = normalize_date("c. 1680", "test_path")
        assert result.start == 1675
        assert result.end == 1685
        assert result.method == "year_circa_pm5"
        assert result.confidence == 0.80
        assert result.warnings == []

    def test_circa_without_dot(self):
        """Test circa without dot."""
        result = normalize_date("c1680", "test_path")
        assert result.start == 1675
        assert result.end == 1685
        assert result.method == "year_circa_pm5"
        assert result.confidence == 0.80

    def test_range_with_hyphen(self):
        """Test year range with hyphen (confidence=0.90)."""
        result = normalize_date("1680-1685", "test_path")
        assert result.start == 1680
        assert result.end == 1685
        assert result.method == "year_range"
        assert result.confidence == 0.90
        assert result.warnings == []

    def test_range_with_slash(self):
        """Test year range with slash."""
        result = normalize_date("1680/1685", "test_path")
        assert result.start == 1680
        assert result.end == 1685
        assert result.method == "year_range"
        assert result.confidence == 0.90

    def test_bracketed_range(self):
        """Test bracketed year range (confidence=0.90)."""
        result = normalize_date("[1611-1612]", "test_path")
        assert result.start == 1611
        assert result.end == 1612
        assert result.method == "year_bracketed_range"
        assert result.confidence == 0.90
        assert result.warnings == []

    def test_bracketed_range_with_slash(self):
        """Test bracketed year range with slash."""
        result = normalize_date("[1500/1599]", "test_path")
        assert result.start == 1500
        assert result.end == 1599
        assert result.method == "year_bracketed_range"
        assert result.confidence == 0.90

    def test_bracketed_range_in_complex_string(self):
        """Test bracketed range extracted from complex string like MDCXI - MDCXII [1611-1612]."""
        result = normalize_date("MDCXI - MDCXII [1611-1612]", "test_path")
        assert result.start == 1611
        assert result.end == 1612
        assert result.method == "year_bracketed_range"
        assert result.confidence == 0.90

    def test_embedded_range(self):
        """Test embedded range detection with non-adjacent years (confidence=0.80)."""
        result = normalize_date('תרס"א 1900-תרס"ה 1904', "test_path")
        assert result.start == 1900
        assert result.end == 1904
        assert result.method == "year_embedded_range"
        assert result.confidence == 0.80  # Lower confidence for non-adjacent years
        assert "embedded_range_in_complex_string" in result.warnings

    def test_embedded_range_simple(self):
        """Test simple embedded range with other text."""
        result = normalize_date("circa 1650-1660 printed", "test_path")
        assert result.start == 1650
        assert result.end == 1660
        assert result.method == "year_embedded_range"
        assert result.confidence == 0.85

    def test_embedded_year(self):
        """Test embedded year with warning (confidence=0.85)."""
        result = normalize_date("ו\"עשו לי מק\"דש ושכנת\"י ב\"תוכם [תק\"ח] 1748", "test_path")
        assert result.start == 1748
        assert result.end == 1748
        assert result.method == "year_embedded"
        assert result.confidence == 0.85
        assert "embedded_year_in_complex_string" in result.warnings

    def test_unparsed(self):
        """Test unparsed date with warning (confidence=0.0)."""
        result = normalize_date("unknown date", "test_path")
        assert result.start is None
        assert result.end is None
        assert result.method == "unparsed"
        assert result.confidence == 0.0
        assert "date_unparsed" in result.warnings

    def test_missing_date(self):
        """Test missing/null date."""
        result = normalize_date(None, "test_path")
        assert result.start is None
        assert result.end is None
        assert result.method == "missing"
        assert result.confidence == 0.0
        assert "date_missing" in result.warnings


class TestHebrewGematria:
    """Test Hebrew Gematria year parsing."""

    def test_parse_hebrew_year_tashlit(self):
        """Test parsing תשל"ט (5739 = 1979)."""
        result = parse_hebrew_year('תשל"ט')
        assert result == 5739

    def test_parse_hebrew_year_tasat(self):
        """Test parsing תס"ט (5469 = 1709)."""
        result = parse_hebrew_year('תס"ט')
        assert result == 5469

    def test_parse_hebrew_year_takach(self):
        """Test parsing תק"ח (5508 = 1748)."""
        result = parse_hebrew_year('תק"ח')
        assert result == 5508

    def test_parse_hebrew_year_with_brackets(self):
        """Test parsing [תס"ט] with brackets."""
        result = parse_hebrew_year('[תס"ט]')
        assert result == 5469

    def test_normalize_hebrew_gematria(self):
        """Test normalizing a pure Hebrew Gematria year."""
        result = normalize_date('תשל"ט', "test_path")
        # 5739 - 3760 = 1979
        assert result.start == 1979
        assert result.end == 1979
        assert result.method == "hebrew_gematria"
        assert result.confidence == 0.80
        assert "hebrew_letter_year_converted" in result.warnings

    def test_normalize_hebrew_gematria_tasat(self):
        """Test normalizing תס"ט → 1709."""
        result = normalize_date('[תס"ט]', "test_path")
        # 5469 - 3760 = 1709
        assert result.start == 1709
        assert result.end == 1709
        assert result.method == "hebrew_gematria"

    def test_normalize_hebrew_gematria_takach(self):
        """Test normalizing תק"ח → 1748."""
        result = normalize_date('תק"ח', "test_path")
        # 5508 - 3760 = 1748
        assert result.start == 1748
        assert result.end == 1748
        assert result.method == "hebrew_gematria"

    def test_parse_hebrew_year_empty(self):
        """Test parsing empty string returns None."""
        result = parse_hebrew_year('')
        assert result is None

    def test_parse_hebrew_year_no_hebrew_letters(self):
        """Test parsing string without Hebrew letters returns None."""
        result = parse_hebrew_year('1234')
        assert result is None


class TestPlaceNormalization:
    """Test place normalization."""

    def test_place_with_trailing_colon(self):
        """Test place with trailing colon and punctuation."""
        result = normalize_place("Paris :", "test_path")
        assert result.value == "paris"
        assert result.display == "Paris"
        assert result.method == "place_casefold_strip"
        assert result.confidence == 0.80
        assert result.warnings == []

    def test_place_with_brackets(self):
        """Test place with surrounding brackets."""
        result = normalize_place("[S.l.]", "test_path")
        assert result.value == "s.l."
        assert result.display == "S.l."
        assert result.method == "place_casefold_strip"

    def test_place_missing(self):
        """Test missing place."""
        result = normalize_place(None, "test_path")
        assert result.value is None
        assert result.method == "missing"
        assert result.confidence == 0.0
        assert "place_missing" in result.warnings

    def test_place_with_alias_map(self):
        """Test place normalization with alias map."""
        alias_map = {"paris": "paris_france"}
        result = normalize_place("Paris :", "test_path", alias_map)
        assert result.value == "paris_france"
        assert result.display == "Paris"
        assert result.method == "place_alias_map"
        assert result.confidence == 0.95

    def test_place_unicode_normalize(self):
        """Test place with unicode normalization."""
        result = normalize_place("Köln", "test_path")
        assert result.value == "köln"
        assert result.method == "place_casefold_strip"

    def test_latin_place_amstelodami(self):
        """Test Latin place name 'Amstelodami' maps to 'amsterdam'."""
        alias_map = {"amstelodami": "amsterdam"}
        result = normalize_place("Amstelodami", "test_path", alias_map)
        assert result.value == "amsterdam"
        assert result.display == "Amstelodami"
        assert result.method == "place_alias_map"
        assert result.confidence == 0.95

    def test_latin_place_bracketed_amstelodami(self):
        """Test Latin place name '[Amstelodami]' maps to 'amsterdam'."""
        alias_map = {"amstelodami": "amsterdam"}
        result = normalize_place("[Amstelodami]", "test_path", alias_map)
        assert result.value == "amsterdam"
        assert result.display == "Amstelodami"
        assert result.method == "place_alias_map"
        assert result.confidence == 0.95

    def test_latin_place_hagae_comitis(self):
        """Test Latin place name 'Hagae comitis' maps to 'the hague'."""
        alias_map = {"hagae comitis": "the hague"}
        result = normalize_place("Hagae comitis", "test_path", alias_map)
        assert result.value == "the hague"
        assert result.method == "place_alias_map"


class TestPublisherNormalization:
    """Test publisher normalization."""

    def test_publisher_with_trailing_comma(self):
        """Test publisher with trailing comma."""
        result = normalize_publisher("C. Fosset,", "test_path")
        assert result.value == "c. fosset"
        assert result.display == "C. Fosset"
        assert result.method == "publisher_casefold_strip"
        assert result.confidence == 0.80
        assert result.warnings == []

    def test_publisher_missing(self):
        """Test missing publisher."""
        result = normalize_publisher(None, "test_path")
        assert result.value is None
        assert result.method == "missing"
        assert result.confidence == 0.0
        assert "publisher_missing" in result.warnings

    def test_publisher_with_alias_map(self):
        """Test publisher normalization with alias map."""
        alias_map = {"c. fosset": "fosset_charles"}
        result = normalize_publisher("C. Fosset,", "test_path", alias_map)
        assert result.value == "fosset_charles"
        assert result.display == "C. Fosset"
        assert result.method == "publisher_alias_map"
        assert result.confidence == 0.95


class TestM2Enrichment:
    """Test M2 enrichment of full M1 records."""

    def test_reference_record_990011964120204146(self):
        """Test M2 enrichment for reference record MMS 990011964120204146."""
        # Load the reference record from M1 JSONL
        records_path = Path("data/canonical/records.jsonl")
        assert records_path.exists(), "M1 canonical records not found"

        m1_record = None
        with open(records_path, 'r', encoding='utf-8') as f:
            for line in f:
                record = json.loads(line)
                if record['source']['control_number']['value'] == "990011964120204146":
                    m1_record = record
                    break

        assert m1_record is not None, "Reference record not found"

        # Enrich with M2
        m2 = enrich_m2(m1_record)

        # Validate M2 structure
        assert len(m2.imprints_norm) == 1, "Should have 1 normalized imprint"

        imprint_norm = m2.imprints_norm[0]

        # Validate date normalization
        assert imprint_norm.date_norm is not None
        assert imprint_norm.date_norm.start == 1680
        assert imprint_norm.date_norm.end == 1680
        assert imprint_norm.date_norm.method == "year_bracketed"
        assert imprint_norm.date_norm.confidence == 0.95
        assert imprint_norm.date_norm.evidence_paths == ["imprints[0].date.value"]

        # Validate place normalization
        assert imprint_norm.place_norm is not None
        assert imprint_norm.place_norm.value == "paris"
        assert imprint_norm.place_norm.display == "Paris"
        assert imprint_norm.place_norm.method == "place_casefold_strip"
        assert imprint_norm.place_norm.confidence == 0.80
        assert imprint_norm.place_norm.evidence_paths == ["imprints[0].place.value"]

        # Validate publisher normalization
        assert imprint_norm.publisher_norm is not None
        assert imprint_norm.publisher_norm.value == "c. fosset"
        assert imprint_norm.publisher_norm.display == "C. Fosset"
        assert imprint_norm.publisher_norm.method == "publisher_casefold_strip"
        assert imprint_norm.publisher_norm.confidence == 0.80
        assert imprint_norm.publisher_norm.evidence_paths == ["imprints[0].publisher.value"]

    def test_m2_does_not_modify_m1(self):
        """Test that enrich_m2() does not modify the input M1 record."""
        m1_record = {
            "source": {"control_number": {"value": "test"}},
            "imprints": [
                {
                    "date": {"value": "1680"},
                    "place": {"value": "Paris"},
                    "publisher": {"value": "Fosset"}
                }
            ]
        }

        # Make a copy to compare
        m1_copy = json.loads(json.dumps(m1_record))

        # Enrich
        m2 = enrich_m2(m1_record)

        # M1 record should be unchanged
        assert m1_record == m1_copy, "enrich_m2() should not modify input"

        # M2 should exist
        assert m2.imprints_norm is not None
        assert len(m2.imprints_norm) == 1

    def test_deterministic_output(self):
        """Test that normalization is deterministic (same input → same output)."""
        m1_record = {
            "source": {"control_number": {"value": "test"}},
            "imprints": [
                {
                    "date": {"value": "[1680]"},
                    "place": {"value": "Paris :"},
                    "publisher": {"value": "C. Fosset,"}
                }
            ]
        }

        # Enrich twice
        m2_first = enrich_m2(m1_record)
        m2_second = enrich_m2(m1_record)

        # Should be identical
        assert m2_first.model_dump() == m2_second.model_dump(), "Normalization should be deterministic"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
