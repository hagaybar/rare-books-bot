"""Tests for gap clustering module.

Covers script detection, date pattern grouping, publisher fuzzy matching,
cluster priority scoring, and edge cases.
"""

import pytest

from scripts.metadata.audit import (
    CoverageReport,
    FieldCoverage,
    ConfidenceBand,
    LowConfidenceItem,
)
from scripts.metadata.clustering import (
    Cluster,
    ClusterValue,
    classify_date_pattern,
    cluster_all_gaps,
    cluster_field_gaps,
    detect_script,
    _cluster_agents,
    _cluster_dates,
    _cluster_places,
    _cluster_publishers,
    _find_near_matches,
    _normalize_for_matching,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(
    raw: str,
    freq: int = 1,
    conf: float = 0.80,
    method: str = "base_cleaning",
    norm: str = None,
) -> LowConfidenceItem:
    """Create a LowConfidenceItem for testing."""
    return LowConfidenceItem(
        raw_value=raw,
        norm_value=norm,
        confidence=conf,
        method=method,
        frequency=freq,
    )


def _make_empty_field_coverage() -> FieldCoverage:
    """Create a minimal FieldCoverage with no flagged items."""
    return FieldCoverage(
        total_records=0,
        non_null_count=0,
        null_count=0,
        confidence_distribution=[],
        method_distribution=[],
        flagged_items=[],
    )


def _make_field_coverage(items: list) -> FieldCoverage:
    """Create a FieldCoverage with specified flagged items."""
    return FieldCoverage(
        total_records=len(items),
        non_null_count=len(items),
        null_count=0,
        confidence_distribution=[],
        method_distribution=[],
        flagged_items=items,
    )


# ===========================================================================
# Script detection tests
# ===========================================================================

class TestDetectScript:
    """Tests for Unicode script detection."""

    def test_latin_text(self):
        assert detect_script("Paris") == "latin"

    def test_latin_with_punctuation(self):
        assert detect_script("[Amsterdam]") == "latin"

    def test_hebrew_text(self):
        assert detect_script("ירושלים") == "hebrew"

    def test_hebrew_with_brackets(self):
        assert detect_script("(ירושלים)") == "hebrew"

    def test_arabic_text(self):
        assert detect_script("القاهرة") == "arabic"

    def test_empty_string(self):
        assert detect_script("") == "empty"

    def test_whitespace_only(self):
        assert detect_script("   ") == "empty"

    def test_none_equivalent(self):
        """None input should not crash (guard in caller)."""
        assert detect_script("") == "empty"

    def test_mixed_hebrew_latin(self):
        """Majority script wins."""
        # Hebrew characters outnumber Latin
        result = detect_script("אבגד xyz")
        assert result == "hebrew"

    def test_mixed_latin_majority(self):
        """When Latin characters dominate."""
        result = detect_script("Amsterdam א")
        assert result == "latin"

    def test_numbers_only(self):
        """Pure digits have no alphabetic chars."""
        assert detect_script("1234") == "empty"

    def test_latin_with_diacritics(self):
        """Accented Latin characters should be detected as latin."""
        assert detect_script("Zürich") == "latin"
        assert detect_script("Köln") == "latin"


# ===========================================================================
# Date pattern classification tests
# ===========================================================================

class TestClassifyDatePattern:
    """Tests for date pattern grouping."""

    def test_partial_century(self):
        assert classify_date_pattern("[17--?]") == "partial_century"

    def test_partial_century_no_brackets(self):
        assert classify_date_pattern("18--") == "partial_century"

    def test_hebrew_gematria(self):
        """Hebrew letter-based date notation."""
        assert classify_date_pattern('תק"ל') == "hebrew_gematria"

    def test_hebrew_gematria_plain(self):
        assert classify_date_pattern("תקל") == "hebrew_gematria"

    def test_latin_convention_anno(self):
        assert classify_date_pattern("Anno Domini 1650") == "latin_convention"

    def test_latin_convention_mdccc(self):
        assert classify_date_pattern("MDCCC") == "latin_convention"

    def test_ambiguous_range(self):
        assert classify_date_pattern("1500-99") == "ambiguous_range"

    def test_ambiguous_range_full(self):
        assert classify_date_pattern("1650/1660") == "ambiguous_range"

    def test_circa(self):
        assert classify_date_pattern("ca. 1650") == "circa"

    def test_circa_full(self):
        assert classify_date_pattern("circa 1700") == "circa"

    def test_empty(self):
        assert classify_date_pattern("") == "empty_missing"

    def test_whitespace(self):
        assert classify_date_pattern("   ") == "empty_missing"

    def test_other_unparsed(self):
        assert classify_date_pattern("unknown date") == "other_unparsed"

    def test_just_question_mark(self):
        assert classify_date_pattern("?") == "other_unparsed"


# ===========================================================================
# Text normalization tests
# ===========================================================================

class TestNormalizeForMatching:
    """Tests for the normalization helper."""

    def test_casefolding(self):
        assert _normalize_for_matching("PARIS") == "paris"

    def test_strip_brackets(self):
        assert _normalize_for_matching("[Amsterdam]") == "amsterdam"

    def test_strip_trailing_punctuation(self):
        assert _normalize_for_matching("Berlin :") == "berlin"

    def test_collapse_whitespace(self):
        assert _normalize_for_matching("New   York") == "new york"

    def test_empty(self):
        assert _normalize_for_matching("") == ""

    def test_none(self):
        assert _normalize_for_matching(None) == ""


# ===========================================================================
# Near-match detection tests
# ===========================================================================

class TestFindNearMatches:
    """Tests for alias map near-matching."""

    def test_exact_match_after_normalization(self):
        alias_map = {"[Amsterdam]": "amsterdam", "Paris :": "paris"}
        assert _find_near_matches("[amsterdam]", alias_map) == "amsterdam"

    def test_case_insensitive_match(self):
        alias_map = {"Berlin": "berlin"}
        assert _find_near_matches("BERLIN", alias_map) == "berlin"

    def test_no_match(self):
        alias_map = {"Paris": "paris"}
        assert _find_near_matches("Tokyo", alias_map) is None

    def test_match_against_canonical_values(self):
        alias_map = {"[londini]": "london"}
        assert _find_near_matches("London", alias_map) == "london"

    def test_empty_map(self):
        assert _find_near_matches("Paris", {}) is None

    def test_empty_value(self):
        assert _find_near_matches("", {"Paris": "paris"}) is None


# ===========================================================================
# Place clustering tests
# ===========================================================================

class TestClusterPlaces:
    """Tests for place gap clustering."""

    def test_groups_by_script(self):
        items = [
            _make_item("Paris", freq=10),
            _make_item("ירושלים", freq=5),
            _make_item("القاهرة", freq=3),
        ]
        clusters = _cluster_places(items)
        types = {c.cluster_type for c in clusters}
        assert "latin_place_names" in types
        assert "hebrew_place_names" in types
        assert "arabic_place_names" in types

    def test_near_match_cluster(self):
        alias_map = {"[paris]": "paris"}
        items = [_make_item("[Paris]", freq=10)]
        clusters = _cluster_places(items, alias_map)
        near = [c for c in clusters if c.cluster_type == "near_match"]
        assert len(near) == 1
        assert "Paris" in near[0].evidence["proposed_mappings"]["[Paris]"] or \
               near[0].evidence["proposed_mappings"]["[Paris]"] == "paris"

    def test_empty_input(self):
        assert _cluster_places([]) == []

    def test_priority_ordering(self):
        items = [
            _make_item("rare_place", freq=1),
            _make_item("common_place", freq=100),
        ]
        clusters = _cluster_places(items)
        # All end up in latin cluster; check ordering within
        latin = [c for c in clusters if c.cluster_type == "latin_place_names"]
        assert len(latin) == 1
        assert latin[0].values[0].raw_value == "common_place"
        assert latin[0].total_records_affected == 101

    def test_single_item(self):
        items = [_make_item("Leiden", freq=3)]
        clusters = _cluster_places(items)
        assert len(clusters) == 1
        assert clusters[0].field == "place"


# ===========================================================================
# Date clustering tests
# ===========================================================================

class TestClusterDates:
    """Tests for date gap clustering."""

    def test_groups_by_pattern(self):
        items = [
            _make_item("[17--?]", freq=5, conf=0.0, method="unparsed"),
            _make_item('תק"ל', freq=3, conf=0.0, method="unparsed"),
            _make_item("ca. 1650", freq=2, conf=0.0, method="unparsed"),
            _make_item("", freq=10, conf=0.0, method="missing"),
        ]
        clusters = _cluster_dates(items)
        types = {c.cluster_type for c in clusters}
        assert "partial_century" in types
        assert "hebrew_gematria" in types
        assert "circa" in types
        assert "empty_missing" in types

    def test_empty_input(self):
        assert _cluster_dates([]) == []

    def test_priority_by_frequency(self):
        items = [
            _make_item("[17--?]", freq=1, conf=0.0, method="unparsed"),
            _make_item("", freq=100, conf=0.0, method="missing"),
        ]
        clusters = _cluster_dates(items)
        # empty_missing has freq 100, should be first
        assert clusters[0].cluster_type == "empty_missing"
        assert clusters[0].priority_score == 100.0


# ===========================================================================
# Publisher clustering tests
# ===========================================================================

class TestClusterPublishers:
    """Tests for publisher gap clustering."""

    def test_variant_grouping(self):
        """Multiple raw forms that normalize to same base should cluster."""
        items = [
            _make_item("C. Fosset,", freq=5),
            _make_item("C. Fosset", freq=3),
        ]
        clusters = _cluster_publishers(items)
        variant = [c for c in clusters if c.cluster_type == "variant_group"]
        assert len(variant) == 1
        assert variant[0].proposed_canonical == "c. fosset"
        assert variant[0].total_records_affected == 8

    def test_near_match_with_alias(self):
        alias_map = {"elsevier": "elsevier"}
        items = [_make_item("Elsevier:", freq=10)]
        clusters = _cluster_publishers(items, alias_map)
        near = [c for c in clusters if c.cluster_type == "near_match"]
        assert len(near) == 1

    def test_frequency_tiers(self):
        """High-freq and low-freq singletons should be in separate clusters."""
        items = [
            _make_item("UniquePublisher1", freq=10),
            _make_item("RarePublisher1", freq=1),
        ]
        clusters = _cluster_publishers(items)
        types = {c.cluster_type for c in clusters}
        assert "high_frequency_unmapped" in types
        assert "low_frequency_unmapped" in types

    def test_empty_input(self):
        assert _cluster_publishers([]) == []


# ===========================================================================
# Agent clustering tests
# ===========================================================================

class TestClusterAgents:
    """Tests for agent gap clustering."""

    def test_ambiguous_agents(self):
        items = [_make_item("John Smith", freq=5, conf=0.60, method="ambiguous")]
        clusters = _cluster_agents(items)
        assert len(clusters) == 1
        assert clusters[0].cluster_type == "ambiguous_agent"

    def test_missing_role(self):
        items = [_make_item("Unknown Author", freq=3, conf=0.30, method="inferred")]
        clusters = _cluster_agents(items)
        missing = [c for c in clusters if c.cluster_type == "missing_role"]
        assert len(missing) == 1

    def test_low_confidence(self):
        items = [_make_item("Some Agent", freq=2, conf=0.65, method="parsed")]
        clusters = _cluster_agents(items)
        low = [c for c in clusters if c.cluster_type == "low_confidence_agent"]
        assert len(low) == 1

    def test_empty_input(self):
        assert _cluster_agents([]) == []

    def test_mixed_agents(self):
        items = [
            _make_item("Agent A", freq=5, conf=0.60, method="ambiguous"),
            _make_item("Agent B", freq=3, conf=0.30, method="inferred"),
            _make_item("Agent C", freq=2, conf=0.65, method="parsed"),
        ]
        clusters = _cluster_agents(items)
        types = {c.cluster_type for c in clusters}
        assert "ambiguous_agent" in types
        assert "missing_role" in types
        assert "low_confidence_agent" in types


# ===========================================================================
# Public API tests
# ===========================================================================

class TestClusterFieldGaps:
    """Tests for the public cluster_field_gaps function."""

    def test_routes_to_place(self):
        items = [_make_item("Paris", freq=5)]
        clusters = cluster_field_gaps("place", items)
        assert all(c.field == "place" for c in clusters)

    def test_routes_to_date(self):
        items = [_make_item("[17--?]", freq=5, conf=0.0, method="unparsed")]
        clusters = cluster_field_gaps("date", items)
        assert all(c.field == "date" for c in clusters)

    def test_routes_to_publisher(self):
        items = [_make_item("Elsevier:", freq=5)]
        clusters = cluster_field_gaps("publisher", items)
        assert all(c.field == "publisher" for c in clusters)

    def test_routes_to_agent(self):
        items = [_make_item("Agent X", freq=5, conf=0.60, method="ambiguous")]
        clusters = cluster_field_gaps("agent", items)
        assert all(c.field == "agent" for c in clusters)

    def test_invalid_field_raises(self):
        with pytest.raises(ValueError, match="Unknown field"):
            cluster_field_gaps("invalid_field", [])

    def test_with_alias_map(self):
        alias_map = {"[paris]": "paris"}
        items = [_make_item("[Paris]", freq=10)]
        clusters = cluster_field_gaps("place", items, alias_map=alias_map)
        near = [c for c in clusters if c.cluster_type == "near_match"]
        assert len(near) == 1


class TestClusterAllGaps:
    """Tests for the cluster_all_gaps function."""

    def test_returns_all_fields(self):
        report = CoverageReport(
            date_coverage=_make_field_coverage([
                _make_item("", freq=5, conf=0.0, method="missing"),
            ]),
            place_coverage=_make_field_coverage([
                _make_item("Paris", freq=3),
            ]),
            publisher_coverage=_make_field_coverage([
                _make_item("Elsevier:", freq=2),
            ]),
            agent_name_coverage=_make_field_coverage([
                _make_item("Agent A", freq=1, conf=0.60, method="ambiguous"),
            ]),
            agent_role_coverage=_make_empty_field_coverage(),
            total_imprint_rows=100,
            total_agent_rows=50,
        )

        result = cluster_all_gaps(report)
        assert "date" in result
        assert "place" in result
        assert "publisher" in result
        assert "agent" in result

    def test_empty_report(self):
        report = CoverageReport(
            date_coverage=_make_empty_field_coverage(),
            place_coverage=_make_empty_field_coverage(),
            publisher_coverage=_make_empty_field_coverage(),
            agent_name_coverage=_make_empty_field_coverage(),
            agent_role_coverage=_make_empty_field_coverage(),
            total_imprint_rows=0,
            total_agent_rows=0,
        )
        result = cluster_all_gaps(report)
        for field_clusters in result.values():
            assert field_clusters == []

    def test_with_alias_maps(self):
        report = CoverageReport(
            date_coverage=_make_empty_field_coverage(),
            place_coverage=_make_field_coverage([
                _make_item("[Paris]", freq=10),
            ]),
            publisher_coverage=_make_empty_field_coverage(),
            agent_name_coverage=_make_empty_field_coverage(),
            agent_role_coverage=_make_empty_field_coverage(),
            total_imprint_rows=100,
            total_agent_rows=0,
        )
        alias_maps = {"place": {"[paris]": "paris"}}
        result = cluster_all_gaps(report, alias_maps=alias_maps)
        place_clusters = result["place"]
        near = [c for c in place_clusters if c.cluster_type == "near_match"]
        assert len(near) == 1


# ===========================================================================
# Priority scoring tests
# ===========================================================================

class TestPriorityScoring:
    """Tests for cluster priority scoring."""

    def test_priority_is_sum_of_frequencies(self):
        items = [
            _make_item("A", freq=10),
            _make_item("B", freq=20),
            _make_item("C", freq=30),
        ]
        clusters = _cluster_places(items)
        # All Latin, one cluster
        assert len(clusters) == 1
        assert clusters[0].priority_score == 60.0
        assert clusters[0].total_records_affected == 60

    def test_clusters_sorted_by_priority(self):
        """Higher-priority clusters appear first."""
        items = [
            _make_item("Paris", freq=100),
            _make_item("ירושלים", freq=1),
        ]
        clusters = _cluster_places(items)
        assert clusters[0].priority_score >= clusters[-1].priority_score


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_single_item_date(self):
        items = [_make_item("ca. 1650", freq=1, conf=0.0, method="unparsed")]
        clusters = _cluster_dates(items)
        assert len(clusters) == 1
        assert clusters[0].values[0].raw_value == "ca. 1650"

    def test_single_item_place(self):
        items = [_make_item("Leiden", freq=1)]
        clusters = _cluster_places(items)
        assert len(clusters) == 1

    def test_all_same_script(self):
        items = [
            _make_item("Paris", freq=5),
            _make_item("London", freq=3),
            _make_item("Berlin", freq=2),
        ]
        clusters = _cluster_places(items)
        assert len(clusters) == 1
        assert clusters[0].cluster_type == "latin_place_names"
        assert len(clusters[0].values) == 3

    def test_cluster_value_fields(self):
        """Verify ClusterValue dataclass fields are populated correctly."""
        items = [_make_item("test", freq=7, conf=0.75, method="base_cleaning")]
        clusters = _cluster_places(items)
        v = clusters[0].values[0]
        assert v.raw_value == "test"
        assert v.frequency == 7
        assert v.confidence == 0.75
        assert v.method == "base_cleaning"

    def test_cluster_fields(self):
        """Verify Cluster dataclass fields."""
        items = [_make_item("test", freq=5)]
        clusters = _cluster_places(items)
        c = clusters[0]
        assert c.cluster_id.startswith("place_")
        assert c.field == "place"
        assert isinstance(c.evidence, dict)
        assert c.proposed_canonical is None or isinstance(c.proposed_canonical, str)
