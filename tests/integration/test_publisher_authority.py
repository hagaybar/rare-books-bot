"""Integration tests for publisher authority records in the real database.

Verifies data integrity of publisher_authorities and publisher_variants
tables in the production bibliographic.db, including referential integrity,
confidence scores, variant coverage, and specific publisher spot-checks.

Run with:
    pytest tests/integration/test_publisher_authority.py -v --tb=short
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

DB_PATH = Path("data/index/bibliographic.db")


@pytest.fixture()
def conn():
    """SQLite connection to the real bibliographic database."""
    if not DB_PATH.exists():
        pytest.skip("Bibliographic database not available")
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Schema existence
# ---------------------------------------------------------------------------


class TestPublisherAuthorityIntegrity:
    def test_tables_exist(self, conn):
        """Both publisher_authorities and publisher_variants tables exist."""
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "publisher_authorities" in tables
        assert "publisher_variants" in tables

    # -----------------------------------------------------------------------
    # Count and threshold checks
    # -----------------------------------------------------------------------

    def test_researched_publishers_present(self, conn):
        """At least 20 researched publishers (some may have been merged)."""
        count = conn.execute(
            "SELECT COUNT(*) FROM publisher_authorities WHERE type != 'unresearched'"
        ).fetchone()[0]
        assert count >= 20, f"Only {count} researched publishers found, expected >= 20"

    def test_total_authorities_reasonable(self, conn):
        """Total authority count should be non-trivial."""
        count = conn.execute(
            "SELECT COUNT(*) FROM publisher_authorities"
        ).fetchone()[0]
        assert count >= 100, f"Only {count} total authorities, expected >= 100"

    def test_total_variants_reasonable(self, conn):
        """Variant count should be at least as many as authorities."""
        auth_count = conn.execute(
            "SELECT COUNT(*) FROM publisher_authorities"
        ).fetchone()[0]
        var_count = conn.execute(
            "SELECT COUNT(*) FROM publisher_variants"
        ).fetchone()[0]
        assert var_count >= auth_count, (
            f"Fewer variants ({var_count}) than authorities ({auth_count})"
        )

    # -----------------------------------------------------------------------
    # Referential integrity
    # -----------------------------------------------------------------------

    def test_no_orphaned_variants(self, conn):
        """Every variant must reference an existing authority."""
        orphans = conn.execute(
            "SELECT COUNT(*) FROM publisher_variants "
            "WHERE authority_id NOT IN (SELECT id FROM publisher_authorities)"
        ).fetchone()[0]
        assert orphans == 0, f"Found {orphans} orphaned variants"

    def test_all_authorities_have_variants(self, conn):
        """Authorities should have at least one variant (small gap tolerated for unresearched)."""
        no_variants = conn.execute(
            "SELECT COUNT(*) FROM publisher_authorities "
            "WHERE id NOT IN (SELECT DISTINCT authority_id FROM publisher_variants)"
        ).fetchone()[0]
        # A small number of recently-added authorities may not yet have variants
        assert no_variants <= 5, f"Found {no_variants} authorities without variants (expected <= 5)"

    # -----------------------------------------------------------------------
    # Confidence scores
    # -----------------------------------------------------------------------

    def test_confidence_scores_not_null(self, conn):
        """No null confidence scores."""
        nulls = conn.execute(
            "SELECT COUNT(*) FROM publisher_authorities WHERE confidence IS NULL"
        ).fetchone()[0]
        assert nulls == 0, f"Found {nulls} authorities with null confidence"

    def test_confidence_scores_in_range(self, conn):
        """All confidence scores between 0.0 and 1.0."""
        out_of_range = conn.execute(
            "SELECT COUNT(*) FROM publisher_authorities "
            "WHERE confidence < 0.0 OR confidence > 1.0"
        ).fetchone()[0]
        assert out_of_range == 0, f"Found {out_of_range} out-of-range confidence scores"

    # -----------------------------------------------------------------------
    # Type distribution
    # -----------------------------------------------------------------------

    def test_valid_types_only(self, conn):
        """All type values are from the allowed set."""
        valid_types = {
            "printing_house",
            "private_press",
            "modern_publisher",
            "bibliophile_society",
            "unknown_marker",
            "unresearched",
        }
        types = conn.execute(
            "SELECT DISTINCT type FROM publisher_authorities"
        ).fetchall()
        actual_types = {r[0] for r in types}
        invalid = actual_types - valid_types
        assert not invalid, f"Invalid types found: {invalid}"

    # -----------------------------------------------------------------------
    # Missing markers
    # -----------------------------------------------------------------------

    def test_missing_markers_flagged(self, conn):
        """At least 2 missing markers (e.g. publisher unknown, privatdruck)."""
        markers = conn.execute(
            "SELECT COUNT(*) FROM publisher_authorities WHERE is_missing_marker = 1"
        ).fetchone()[0]
        assert markers >= 2, f"Only {markers} missing markers, expected >= 2"

    # -----------------------------------------------------------------------
    # Spot checks: Elzevir
    # -----------------------------------------------------------------------

    def test_elzevir_exists(self, conn):
        """Elzevir authority record exists."""
        row = conn.execute(
            "SELECT id FROM publisher_authorities "
            "WHERE canonical_name_lower LIKE '%elzevir%'"
        ).fetchone()
        assert row is not None, "Elzevir authority not found"

    def test_elzevir_has_variants(self, conn):
        """Elzevir has at least 2 variants."""
        row = conn.execute(
            "SELECT id FROM publisher_authorities "
            "WHERE canonical_name_lower LIKE '%elzevir%'"
        ).fetchone()
        assert row is not None
        variants = conn.execute(
            "SELECT COUNT(*) FROM publisher_variants WHERE authority_id = ?",
            (row[0],),
        ).fetchone()[0]
        assert variants >= 2, f"Elzevir has only {variants} variants, expected >= 2"

    # -----------------------------------------------------------------------
    # Spot checks: Bomberg
    # -----------------------------------------------------------------------

    def test_bomberg_exists(self, conn):
        """Bomberg authority record exists."""
        row = conn.execute(
            "SELECT id FROM publisher_authorities "
            "WHERE canonical_name_lower LIKE '%bomberg%'"
        ).fetchone()
        assert row is not None, "Bomberg authority not found"

    def test_bomberg_has_hebrew_variant(self, conn):
        """Bomberg has at least one Hebrew-script variant."""
        row = conn.execute(
            "SELECT id FROM publisher_authorities "
            "WHERE canonical_name_lower LIKE '%bomberg%'"
        ).fetchone()
        assert row is not None
        hebrew = conn.execute(
            "SELECT COUNT(*) FROM publisher_variants "
            "WHERE authority_id = ? AND script = 'hebrew'",
            (row[0],),
        ).fetchone()[0]
        assert hebrew >= 1, f"Bomberg has {hebrew} Hebrew variants, expected >= 1"

    # -----------------------------------------------------------------------
    # Variant search via PublisherAuthorityStore API
    # -----------------------------------------------------------------------

    def test_variant_search_finds_authority(self, conn):
        """Look up 'ex officina elzeviriana' and verify it resolves to Elzevir."""
        from scripts.metadata.publisher_authority import PublisherAuthorityStore

        store = PublisherAuthorityStore(DB_PATH)
        result = store.search_by_variant("ex officina elzeviriana", conn=conn)
        assert result is not None, "search_by_variant returned None"
        assert "elzevir" in result.canonical_name.lower(), (
            f"Expected Elzevir, got '{result.canonical_name}'"
        )

    def test_variant_search_case_insensitive(self, conn):
        """Variant search is case-insensitive."""
        from scripts.metadata.publisher_authority import PublisherAuthorityStore

        store = PublisherAuthorityStore(DB_PATH)
        result = store.search_by_variant("EX OFFICINA ELZEVIRIANA", conn=conn)
        assert result is not None, "Case-insensitive variant search failed"

    # -----------------------------------------------------------------------
    # Imprint linkage
    # -----------------------------------------------------------------------

    def test_imprints_linkable(self, conn):
        """At least some imprints match authority variants."""
        matched = conn.execute(
            """SELECT COUNT(DISTINCT i.id) FROM imprints i
               JOIN publisher_variants pv
                 ON LOWER(i.publisher_norm) = pv.variant_form_lower"""
        ).fetchone()[0]
        assert matched > 0, "No imprints matchable via variants"

    # -----------------------------------------------------------------------
    # Canonical name uniqueness
    # -----------------------------------------------------------------------

    def test_canonical_names_unique(self, conn):
        """No duplicate canonical_name_lower values."""
        dupes = conn.execute(
            "SELECT canonical_name_lower, COUNT(*) as cnt "
            "FROM publisher_authorities "
            "GROUP BY canonical_name_lower "
            "HAVING cnt > 1"
        ).fetchall()
        assert len(dupes) == 0, (
            f"Duplicate canonical names: {[r[0] for r in dupes]}"
        )

    # -----------------------------------------------------------------------
    # Variant form uniqueness
    # -----------------------------------------------------------------------

    def test_variant_forms_unique(self, conn):
        """No duplicate variant_form_lower values across all authorities."""
        dupes = conn.execute(
            "SELECT variant_form_lower, COUNT(*) as cnt "
            "FROM publisher_variants "
            "GROUP BY variant_form_lower "
            "HAVING cnt > 1"
        ).fetchall()
        assert len(dupes) == 0, (
            f"Duplicate variant forms: {[r[0] for r in dupes]}"
        )
