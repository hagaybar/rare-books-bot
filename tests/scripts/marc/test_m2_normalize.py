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
        """Test circa with dot (confidence=0.90, ±5 years)."""
        result = normalize_date("c. 1680", "test_path")
        assert result.start == 1675
        assert result.end == 1685
        assert result.method == "year_circa_pm5"
        assert result.confidence == 0.90
        assert result.warnings == []

    def test_circa_without_dot(self):
        """Test circa without dot."""
        result = normalize_date("c1680", "test_path")
        assert result.start == 1675
        assert result.end == 1685
        assert result.method == "year_circa_pm5"
        assert result.confidence == 0.90

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
        """Test embedded range detection with non-adjacent years (confidence=0.90)."""
        result = normalize_date('תרס"א 1900-תרס"ה 1904', "test_path")
        assert result.start == 1900
        assert result.end == 1904
        assert result.method == "year_embedded_range"
        assert result.confidence == 0.90
        assert "embedded_range_in_complex_string" in result.warnings

    def test_embedded_range_simple(self):
        """Test simple embedded range with other text."""
        result = normalize_date("circa 1650-1660 printed", "test_path")
        assert result.start == 1650
        assert result.end == 1660
        assert result.method == "year_embedded_range"
        assert result.confidence == 0.90

    def test_embedded_year(self):
        """Test embedded year with warning (confidence=0.92)."""
        result = normalize_date("ו\"עשו לי מק\"דש ושכנת\"י ב\"תוכם [תק\"ח] 1748", "test_path")
        assert result.start == 1748
        assert result.end == 1748
        assert result.method == "year_embedded"
        assert result.confidence == 0.92
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
        assert result.confidence == 0.90
        assert "hebrew_letter_year_converted" in result.warnings

    def test_normalize_hebrew_gematria_tasat(self):
        """Test normalizing תס"ט → 1709 (bracketed)."""
        result = normalize_date('[תס"ט]', "test_path")
        # 5469 - 3760 = 1709
        assert result.start == 1709
        assert result.end == 1709
        assert result.method == "hebrew_gematria_bracketed"
        assert result.confidence == 0.92

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

    def test_normalize_hebrew_chronogram_with_bracketed_year(self):
        """Test that bracketed Hebrew year is preferred over chronogram fragments.

        Bug fix: MMS 990012031510204146 had date string with chronogram phrase
        ב'א' ז'מ'ן' ה'י'ש'ו'ע'ה' followed by actual year [תצ"ו].
        The old code matched ב'א (gematria=3 → 5003-3760=1243) instead of
        the correct [תצ"ו] (gematria=496 → 5496-3760=1736).
        """
        result = normalize_date("ב'א' ז'מ'ן' ה'י'ש'ו'ע'ה' [תצ\"ו]", "test_path")
        # תצ"ו = ת(400) + צ(90) + ו(6) = 496 → 5496 - 3760 = 1736
        assert result.start == 1736
        assert result.end == 1736
        assert result.method == "hebrew_gematria_bracketed"
        assert result.confidence == 0.92
        assert "hebrew_letter_year_converted" in result.warnings

    def test_normalize_hebrew_chronogram_prefers_brackets(self):
        """Test another chronogram case - bracketed year takes precedence."""
        # Similar pattern: Hebrew phrase with quotes + bracketed year
        result = normalize_date("ש'נ'ת' ה'ש'מ'ח'ה' [תר\"ל]", "test_path")
        # תר"ל = ת(400) + ר(200) + ל(30) = 630 → 5630 - 3760 = 1870
        assert result.start == 1870
        assert result.end == 1870
        assert result.method == "hebrew_gematria_bracketed"


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


class TestCenturyPartialDates:
    """Test century-level partial date patterns from QA audit."""

    def test_century_partial_bracketed_dashes(self):
        """[17--?] → 1700-1799."""
        result = normalize_date("[17--?]", "test_path")
        assert result.start == 1700
        assert result.end == 1799
        assert result.method == "century_partial"
        assert result.confidence == 0.80

    def test_century_partial_bracketed_no_question(self):
        """[19--] → 1900-1999."""
        result = normalize_date("[19--]", "test_path")
        assert result.start == 1900
        assert result.end == 1999
        assert result.method == "century_partial"

    def test_century_partial_space_variant(self):
        """[19 ?] → 1900-1999."""
        result = normalize_date("[19 ?]", "test_path")
        assert result.start == 1900
        assert result.end == 1999
        assert result.method == "century_partial"

    def test_century_partial_double_space(self):
        """[16  ?] → 1600-1699."""
        result = normalize_date("[16  ?]", "test_path")
        assert result.start == 1600
        assert result.end == 1699
        assert result.method == "century_partial"

    def test_century_partial_unbracketed_question(self):
        """17 ? → 1700-1799."""
        result = normalize_date("17 ?", "test_path")
        assert result.start == 1700
        assert result.end == 1799
        assert result.method == "century_partial"

    def test_century_partial_unbracketed_dash(self):
        """17 - → 1700-1799."""
        result = normalize_date("17 -", "test_path")
        assert result.start == 1700
        assert result.end == 1799
        assert result.method == "century_partial"

    def test_century_partial_18xx(self):
        """[18--?] → 1800-1899."""
        result = normalize_date("[18--?]", "test_path")
        assert result.start == 1800
        assert result.end == 1899
        assert result.method == "century_partial"


class TestDecadePartialDates:
    """Test decade-level partial date patterns from QA audit."""

    def test_decade_partial_unbracketed(self):
        """163-? → 1630-1639."""
        result = normalize_date("163-?", "test_path")
        assert result.start == 1630
        assert result.end == 1639
        assert result.method == "decade_partial"
        assert result.confidence == 0.85

    def test_decade_partial_bracketed(self):
        """[192-?] → 1920-1929."""
        result = normalize_date("[192-?]", "test_path")
        assert result.start == 1920
        assert result.end == 1929
        assert result.method == "decade_partial"

    def test_decade_partial_no_question(self):
        """[178-] → 1780-1789."""
        result = normalize_date("[178-]", "test_path")
        assert result.start == 1780
        assert result.end == 1789
        assert result.method == "decade_partial"

    def test_decade_partial_question_only(self):
        """[177?] → 1770-1779."""
        result = normalize_date("[177?]", "test_path")
        assert result.start == 1770
        assert result.end == 1779
        assert result.method == "decade_partial"

    def test_decade_partial_plain(self):
        """198- → 1980-1989."""
        result = normalize_date("198-", "test_path")
        assert result.start == 1980
        assert result.end == 1989
        assert result.method == "decade_partial"

    def test_decade_partial_193(self):
        """193- → 1930-1939."""
        result = normalize_date("193-", "test_path")
        assert result.start == 1930
        assert result.end == 1939
        assert result.method == "decade_partial"

    def test_decade_partial_179(self):
        """179- → 1790-1799."""
        result = normalize_date("179-", "test_path")
        assert result.start == 1790
        assert result.end == 1799
        assert result.method == "decade_partial"

    def test_decade_partial_open_ended(self):
        """[196-]- → 1960-1969."""
        result = normalize_date("[196-]-", "test_path")
        assert result.start == 1960
        assert result.end == 1969
        assert result.method == "decade_partial"

    def test_decade_partial_curly_brace(self):
        """{193-?] → 1930-1939 (typo: curly brace)."""
        result = normalize_date("{193-?]", "test_path")
        assert result.start == 1930
        assert result.end == 1939
        assert result.method == "decade_partial"

    def test_decade_partial_space_dash(self):
        """178 - → 1780-1789."""
        result = normalize_date("178 -", "test_path")
        assert result.start == 1780
        assert result.end == 1789
        assert result.method == "decade_partial"

    def test_decade_partial_open_question(self):
        """[176?]- → 1760-1769."""
        result = normalize_date("[176?]-", "test_path")
        assert result.start == 1760
        assert result.end == 1769
        assert result.method == "decade_partial"

    def test_decade_partial_186(self):
        """[186-?] → 1860-1869."""
        result = normalize_date("[186-?]", "test_path")
        assert result.start == 1860
        assert result.end == 1869
        assert result.method == "decade_partial"


class TestTruncatedRangeDates:
    """Test truncated range date patterns from QA audit."""

    def test_truncated_range_same_decade(self):
        """183 -183 → 1830-1839."""
        result = normalize_date("183 -183", "test_path")
        assert result.start == 1830
        assert result.end == 1839
        assert result.method == "truncated_range"
        assert result.confidence == 0.85

    def test_truncated_range_wide(self):
        """182 -190 → 1820-1909."""
        result = normalize_date("182 -190", "test_path")
        assert result.start == 1820
        assert result.end == 1909
        assert result.method == "truncated_range"

    def test_truncated_range_cross_decade(self):
        """181 -183 → 1810-1839."""
        result = normalize_date("181 -183", "test_path")
        assert result.start == 1810
        assert result.end == 1839
        assert result.method == "truncated_range"

    def test_truncated_range_century_boundary(self):
        """179 -181 → 1790-1819."""
        result = normalize_date("179 -181", "test_path")
        assert result.start == 1790
        assert result.end == 1819
        assert result.method == "truncated_range"

    def test_truncated_range_180_181(self):
        """180 -181 → 1800-1819."""
        result = normalize_date("180 -181", "test_path")
        assert result.start == 1800
        assert result.end == 1819
        assert result.method == "truncated_range"


class TestRomanNumeralDates:
    """Test Roman numeral date patterns from QA audit."""

    def test_roman_simple(self):
        """MDLXI. → 1561."""
        result = normalize_date("MDLXI.", "test_path")
        assert result.start == 1561
        assert result.end == 1561
        assert result.method == "roman_numeral"
        assert result.confidence == 0.95

    def test_roman_long(self):
        """MDCCXLVIII. → 1748."""
        result = normalize_date("MDCCXLVIII.", "test_path")
        assert result.start == 1748
        assert result.end == 1748
        assert result.method == "roman_numeral"

    def test_roman_with_dots(self):
        """M. DCCXXXI. → 1731."""
        result = normalize_date("M. DCCXXXI.", "test_path")
        assert result.start == 1731
        assert result.end == 1731
        assert result.method == "roman_numeral"

    def test_roman_anno_prefix(self):
        """Anno MDCLXXXIII. → 1683."""
        result = normalize_date("Anno MDCLXXXIII.", "test_path")
        assert result.start == 1683
        assert result.end == 1683
        assert result.method == "roman_numeral"

    def test_roman_anno_with_dots(self):
        """Anno M. DC. LXXIX. → 1679."""
        result = normalize_date("Anno M. DC. LXXIX.", "test_path")
        assert result.start == 1679
        assert result.end == 1679
        assert result.method == "roman_numeral"

    def test_roman_a_prefix(self):
        """A. MDCCXIV. → 1714."""
        result = normalize_date("A. MDCCXIV.", "test_path")
        assert result.start == 1714
        assert result.end == 1714
        assert result.method == "roman_numeral"


class TestOcrTypoFix:
    """Test OCR typo fix patterns from QA audit."""

    def test_ocr_letter_o_for_zero(self):
        """18O7 → 1807 (letter O instead of digit 0)."""
        result = normalize_date("18O7", "test_path")
        assert result.start == 1807
        assert result.end == 1807
        assert result.method == "ocr_typo_fix"
        assert result.confidence == 0.95
        assert "ocr_typo_corrected" in result.warnings


class TestDirectDateFixes:
    """Test direct date fixes from QA audit (lookup table)."""

    def test_hebrew_chronogram_range(self):
        """Hebrew chronogram with date range."""
        result = normalize_date('לא ח\'ס\'ר\'ת\' דבר [תרס"ח-תרע"א]', "test_path")
        assert result.start == 1908
        assert result.end == 1911
        assert result.method == "hebrew_chronogram"
        assert result.confidence == 0.90

    def test_open_start_range(self):
        """[?-192] → unknown start, end 1929."""
        result = normalize_date("[?-192]", "test_path")
        assert result.start is None
        assert result.end == 1929
        assert result.method == "open_start_range"

    def test_open_start_range_189(self):
        """[?-189] → unknown start, end 1899."""
        result = normalize_date("[?-189]", "test_path")
        assert result.start is None
        assert result.end == 1899
        assert result.method == "open_start_range"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
