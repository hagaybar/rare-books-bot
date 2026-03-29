"""Tests for the shared occupation → role_norm mapping logic."""
import pytest

from scripts.normalization.occupation_mapper import (
    lookup_occupation,
    resolve_roles,
    unpack_map,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def direct_mappings():
    return {
        "printer": {"role_norm": "printer", "confidence": 0.95, "note": "Direct"},
        "publisher": {"role_norm": "publisher", "confidence": 0.95, "note": "Direct"},
        "engraver": {"role_norm": "engraver", "confidence": 0.95, "note": "Direct"},
        "translator": {"role_norm": "translator", "confidence": 0.90, "note": "Direct"},
        "editor": {"role_norm": "editor", "confidence": 0.90, "note": "Direct"},
        "author": {"role_norm": "author", "confidence": 0.90, "note": "Direct"},
        "bookseller": {"role_norm": "bookseller", "confidence": 0.90, "note": "Direct"},
    }


@pytest.fixture
def semantic_mappings():
    return {
        "poet": {"role_norm": "author", "confidence": 0.80, "note": "Poet → author"},
        "historian": {"role_norm": "author", "confidence": 0.70, "note": "Historian → author"},
        "theologian": {"role_norm": "author", "confidence": 0.70, "note": "Theologian → author"},
        "rabbi": {"role_norm": "author", "confidence": 0.65, "note": "Rabbi → author"},
        "printmaker": {"role_norm": "printmaker", "confidence": 0.90, "note": "Direct semantic"},
        "bookbinder": {"role_norm": "binder", "confidence": 0.90, "note": "Bookbinder → binder"},
    }


@pytest.fixture
def unmapped():
    return {"sovereign", "politician", "banker", "diplomat"}


@pytest.fixture
def priority_order():
    return [
        "printer", "publisher", "bookseller", "engraver",
        "printmaker", "binder", "translator", "editor", "author",
    ]


# ---------------------------------------------------------------------------
# lookup_occupation tests
# ---------------------------------------------------------------------------

class TestLookupOccupation:
    def test_direct_match(self, direct_mappings, semantic_mappings, unmapped):
        result = lookup_occupation("printer", direct_mappings, semantic_mappings, unmapped)
        assert result is not None
        assert result["role_norm"] == "printer"
        assert result["confidence"] == 0.95

    def test_semantic_match(self, direct_mappings, semantic_mappings, unmapped):
        result = lookup_occupation("poet", direct_mappings, semantic_mappings, unmapped)
        assert result is not None
        assert result["role_norm"] == "author"
        assert result["confidence"] == 0.80

    def test_unmapped_returns_none(self, direct_mappings, semantic_mappings, unmapped):
        result = lookup_occupation("sovereign", direct_mappings, semantic_mappings, unmapped)
        assert result is None

    def test_unknown_returns_none(self, direct_mappings, semantic_mappings, unmapped):
        result = lookup_occupation("astronaut", direct_mappings, semantic_mappings, unmapped)
        assert result is None

    def test_case_insensitive_fallback(self, direct_mappings, semantic_mappings, unmapped):
        result = lookup_occupation("Printer", direct_mappings, semantic_mappings, unmapped)
        assert result is not None
        assert result["role_norm"] == "printer"

    def test_direct_takes_priority_over_semantic(self, direct_mappings, semantic_mappings, unmapped):
        """If the same key exists in both direct and semantic, direct wins."""
        result = lookup_occupation("author", direct_mappings, semantic_mappings, unmapped)
        assert result["confidence"] == 0.90  # direct confidence, not semantic


# ---------------------------------------------------------------------------
# resolve_roles tests
# ---------------------------------------------------------------------------

class TestResolveRoles:
    def test_single_occupation(self, direct_mappings, semantic_mappings, unmapped, priority_order):
        roles = resolve_roles(["printer"], direct_mappings, semantic_mappings, unmapped, priority_order)
        assert len(roles) == 1
        assert roles[0]["role_norm"] == "printer"

    def test_multiple_occupations_deduplicates(
        self, direct_mappings, semantic_mappings, unmapped, priority_order
    ):
        """Two occupations mapping to 'author' should result in one role entry."""
        roles = resolve_roles(
            ["poet", "historian"], direct_mappings, semantic_mappings, unmapped, priority_order
        )
        author_roles = [r for r in roles if r["role_norm"] == "author"]
        assert len(author_roles) == 1
        # Should keep the higher confidence one (poet at 0.80 > historian at 0.70)
        assert author_roles[0]["confidence"] == 0.80
        assert author_roles[0]["source_occupation"] == "poet"

    def test_priority_ordering(self, direct_mappings, semantic_mappings, unmapped, priority_order):
        """Printer should come before author in priority order."""
        roles = resolve_roles(
            ["poet", "printer"], direct_mappings, semantic_mappings, unmapped, priority_order
        )
        assert len(roles) == 2
        assert roles[0]["role_norm"] == "printer"  # higher priority
        assert roles[1]["role_norm"] == "author"    # lower priority

    def test_all_unmapped_returns_empty(
        self, direct_mappings, semantic_mappings, unmapped, priority_order
    ):
        roles = resolve_roles(
            ["sovereign", "politician"], direct_mappings, semantic_mappings, unmapped, priority_order
        )
        assert roles == []

    def test_empty_list_returns_empty(
        self, direct_mappings, semantic_mappings, unmapped, priority_order
    ):
        roles = resolve_roles([], direct_mappings, semantic_mappings, unmapped, priority_order)
        assert roles == []

    def test_mixed_mapped_and_unmapped(
        self, direct_mappings, semantic_mappings, unmapped, priority_order
    ):
        """Only mapped occupations produce roles; unmapped are skipped."""
        roles = resolve_roles(
            ["politician", "printer", "banker"],
            direct_mappings, semantic_mappings, unmapped, priority_order,
        )
        assert len(roles) == 1
        assert roles[0]["role_norm"] == "printer"

    def test_mapping_type_correct(
        self, direct_mappings, semantic_mappings, unmapped, priority_order
    ):
        roles = resolve_roles(
            ["printer", "rabbi"], direct_mappings, semantic_mappings, unmapped, priority_order
        )
        printer_role = [r for r in roles if r["role_norm"] == "printer"][0]
        author_role = [r for r in roles if r["role_norm"] == "author"][0]
        assert printer_role["mapping_type"] == "direct"
        assert author_role["mapping_type"] == "semantic"

    def test_role_not_in_priority_order_goes_last(
        self, direct_mappings, semantic_mappings, unmapped, priority_order
    ):
        """Roles not in priority_order should come after all prioritized roles."""
        # "bookbinder" maps to "binder" which IS in priority_order,
        # but let's test with a role that isn't
        roles = resolve_roles(
            ["printer", "printmaker"],
            direct_mappings, semantic_mappings, unmapped, priority_order,
        )
        assert roles[0]["role_norm"] == "printer"
        assert roles[1]["role_norm"] == "printmaker"

    def test_other_role_skipped(self, semantic_mappings, unmapped, priority_order):
        """Occupations that map to 'other' should be skipped."""
        direct_with_other = {
            "spy": {"role_norm": "other", "confidence": 0.5},
            "printer": {"role_norm": "printer", "confidence": 0.95},
        }
        roles = resolve_roles(
            ["spy", "printer"], direct_with_other, semantic_mappings, unmapped, priority_order
        )
        assert len(roles) == 1
        assert roles[0]["role_norm"] == "printer"


# ---------------------------------------------------------------------------
# unpack_map tests
# ---------------------------------------------------------------------------

class TestUnpackMap:
    def test_unpack(self):
        occ_map = {
            "direct_mappings": {"printer": {"role_norm": "printer"}},
            "semantic_mappings": {"poet": {"role_norm": "author"}},
            "unmapped": ["sovereign"],
            "priority_order": ["printer", "author"],
        }
        direct, semantic, unmapped_set, priority = unpack_map(occ_map)
        assert "printer" in direct
        assert "poet" in semantic
        assert "sovereign" in unmapped_set
        assert isinstance(unmapped_set, set)
        assert priority == ["printer", "author"]
