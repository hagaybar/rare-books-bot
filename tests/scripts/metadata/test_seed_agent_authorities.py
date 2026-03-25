"""Tests for agent authority seeding script.

Validates that seed_agent_authorities correctly:
- Creates authorities from enrichment data
- Groups agents by authority_uri
- Generates word-reorder aliases ('Last, First' -> 'First Last')
- Generates cross-script aliases from Hebrew labels
- Handles deduplication gracefully (INSERT OR IGNORE)
- Is idempotent (running twice produces same result)
- Skips complex names (multiple commas)
- Returns count statistics

These tests are written TDD-style: they will FAIL until
``scripts.metadata.seed_agent_authorities`` is implemented.
"""

import json
import sqlite3

import pytest

from scripts.metadata.agent_authority import AgentAuthorityStore

# Import the module under test -- will fail until implemented
from scripts.metadata.seed_agent_authorities import (
    generate_cross_script_aliases,
    generate_word_reorder_aliases,
    seed_all,
    seed_from_enrichment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> sqlite3.Connection:
    """Create an in-memory SQLite database with agents + authority_enrichment
    tables and seed them with representative data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # --- agents table (subset of M3 schema) ---
    conn.execute("""
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            agent_index INTEGER NOT NULL DEFAULT 0,
            agent_raw TEXT,
            agent_type TEXT DEFAULT 'personal',
            role_raw TEXT,
            role_source TEXT,
            authority_uri TEXT,
            agent_norm TEXT,
            agent_confidence REAL DEFAULT 0.8,
            agent_method TEXT,
            agent_notes TEXT,
            role_norm TEXT,
            role_confidence REAL,
            role_method TEXT,
            provenance_json TEXT
        )
    """)

    # --- authority_enrichment table (subset of M3 schema) ---
    conn.execute("""
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            authority_uri TEXT NOT NULL,
            nli_id TEXT,
            wikidata_id TEXT,
            viaf_id TEXT,
            isni_id TEXT,
            loc_id TEXT,
            label TEXT,
            description TEXT,
            person_info TEXT,
            place_info TEXT,
            image_url TEXT,
            wikipedia_url TEXT,
            source TEXT,
            confidence REAL,
            fetched_at TEXT,
            expires_at TEXT
        )
    """)

    # --- records table (for FK if needed) ---
    conn.execute("""
        CREATE TABLE records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mms_id TEXT NOT NULL UNIQUE
        )
    """)

    # Insert sample records
    for i in range(1, 8):
        conn.execute("INSERT INTO records (id, mms_id) VALUES (?, ?)", (i, f"99000{i}"))

    # ----- Sample agents -----

    # Buxtorf: surname-first in agent_norm, has authority_uri
    conn.execute("""
        INSERT INTO agents (record_id, agent_index, agent_raw, agent_norm, authority_uri, agent_type)
        VALUES (1, 0, 'Buxtorf, Johann, 1564-1629', 'buxtorf, johann', '987007260000005171', 'personal')
    """)
    conn.execute("""
        INSERT INTO agents (record_id, agent_index, agent_raw, agent_norm, authority_uri, agent_type)
        VALUES (2, 0, 'Buxtorf, Johann', 'buxtorf, johann', '987007260000005171', 'personal')
    """)

    # Mendelssohn: Latin and Hebrew forms sharing authority_uri
    conn.execute("""
        INSERT INTO agents (record_id, agent_index, agent_raw, agent_norm, authority_uri, agent_type)
        VALUES (3, 0, 'Mendelssohn, Moses, 1729-1786', 'mendelssohn, moses', '987007265100005171', 'personal')
    """)
    conn.execute("""
        INSERT INTO agents (record_id, agent_index, agent_raw, agent_norm, authority_uri, agent_type)
        VALUES (4, 0, 'מנדלסון, משה', 'מנדלסון, משה', '987007265100005171', 'personal')
    """)

    # Maimonides: Latin and Hebrew forms with SAME authority_uri
    conn.execute("""
        INSERT INTO agents (record_id, agent_index, agent_raw, agent_norm, authority_uri, agent_type)
        VALUES (5, 0, 'Maimonides, Moses', 'maimonides, moses', '987007265654005171', 'personal')
    """)
    conn.execute("""
        INSERT INTO agents (record_id, agent_index, agent_raw, agent_norm, authority_uri, agent_type)
        VALUES (6, 0, 'משה בן מימון', 'משה בן מימון', '987007265654005171', 'personal')
    """)

    # Karo: only Hebrew in agents table
    conn.execute("""
        INSERT INTO agents (record_id, agent_index, agent_raw, agent_norm, authority_uri, agent_type)
        VALUES (7, 0, 'קארו, יוסף בן אפרים', 'קארו, יוסף בן אפרים', '987007500000005171', 'personal')
    """)

    # ----- Sample authority_enrichment -----

    # Buxtorf enrichment with label
    conn.execute("""
        INSERT INTO authority_enrichment (authority_uri, label, wikidata_id, person_info)
        VALUES ('987007260000005171', 'Johann Buxtorf', 'Q62547', ?)
    """, (json.dumps({"birth_year": 1564, "death_year": 1629}),))

    # Mendelssohn enrichment with Hebrew label
    conn.execute("""
        INSERT INTO authority_enrichment (authority_uri, label, wikidata_id, person_info)
        VALUES ('987007265100005171', 'Moses Mendelssohn', 'Q60025', ?)
    """, (json.dumps({"hebrew_label": "משה מנדלסון", "birth_year": 1729, "death_year": 1786}),))

    # Maimonides enrichment with Hebrew label
    conn.execute("""
        INSERT INTO authority_enrichment (authority_uri, label, wikidata_id, person_info)
        VALUES ('987007265654005171', 'Moshe ben Maimon', 'Q83363', ?)
    """, (json.dumps({"hebrew_label": "רמב\"ם", "birth_year": 1138, "death_year": 1204}),))

    # Karo enrichment: provides Latin label for Hebrew-only agent
    conn.execute("""
        INSERT INTO authority_enrichment (authority_uri, label, wikidata_id, person_info)
        VALUES ('987007500000005171', 'Joseph ben Ephraim Karo', 'Q311238', ?)
    """, (json.dumps({"hebrew_label": "יוסף קארו", "birth_year": 1488, "death_year": 1575}),))

    conn.commit()

    # Init agent_authorities + agent_aliases schema
    store = AgentAuthorityStore(":memory:")
    store.init_schema(conn=conn)

    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSeedFromEnrichment:
    """Tests for seed_from_enrichment function."""

    def test_seed_from_enrichment_creates_authorities(self):
        """Seeding from enrichment data should create authority records
        for each unique authority_uri found in the agents table."""
        conn = _make_db()

        seed_from_enrichment(conn)

        # Verify authorities were created
        rows = conn.execute("SELECT * FROM agent_authorities").fetchall()
        assert len(rows) >= 4, (
            f"Expected at least 4 authorities (Buxtorf, Mendelssohn, "
            f"Maimonides, Karo), got {len(rows)}"
        )

        # Verify each has aliases
        alias_rows = conn.execute("SELECT * FROM agent_aliases").fetchall()
        assert len(alias_rows) > 0, "Expected aliases to be created"

    def test_seed_groups_by_authority_uri(self):
        """Agents sharing the same authority_uri should be grouped into
        a single authority record, not duplicated."""
        conn = _make_db()

        seed_from_enrichment(conn)

        # Buxtorf has 2 agent rows with same authority_uri
        buxtorf_auths = conn.execute(
            "SELECT * FROM agent_authorities WHERE authority_uri = '987007260000005171'"
        ).fetchall()
        assert len(buxtorf_auths) == 1, (
            f"Expected 1 authority for Buxtorf (grouped), got {len(buxtorf_auths)}"
        )

        # Maimonides has 2 agent rows (Latin + Hebrew) with same authority_uri
        maim_auths = conn.execute(
            "SELECT * FROM agent_authorities WHERE authority_uri = '987007265654005171'"
        ).fetchall()
        assert len(maim_auths) == 1, (
            f"Expected 1 authority for Maimonides (grouped), got {len(maim_auths)}"
        )


class TestWordReorderAliasGeneration:
    """Tests for word-reorder alias generation."""

    def test_word_reorder_alias_generation(self):
        """'Last, First' pattern should generate a 'First Last' alias
        with alias_type='word_reorder'."""
        aliases = generate_word_reorder_aliases("buxtorf, johann")

        # Should produce at least one word-reordered alias
        assert len(aliases) >= 1

        reordered_forms = [a.alias_form.lower() for a in aliases]
        assert "johann buxtorf" in reordered_forms, (
            f"Expected 'johann buxtorf' in word-reordered aliases, got {reordered_forms}"
        )

        # Verify alias_type
        for alias in aliases:
            assert alias.alias_type == "word_reorder"

    def test_skip_complex_names(self):
        """Names with multiple commas should NOT be word-reordered.
        E.g. 'de la Cruz, Juan, San, 1542-1591' has 3 commas."""
        aliases = generate_word_reorder_aliases(
            "de la Cruz, Juan, San, 1542-1591"
        )
        assert len(aliases) == 0, (
            f"Complex names (multiple commas) should produce no word-reorder "
            f"aliases, got {len(aliases)}: {[a.alias_form for a in aliases]}"
        )

    def test_word_reorder_single_comma_only(self):
        """Only names with exactly one comma should be reordered."""
        # Two commas: skip
        aliases_two = generate_word_reorder_aliases("Buxtorf, Johann, 1564-1629")
        # This has two commas, so it should be skipped
        assert len(aliases_two) == 0, (
            "Names with two commas (name + dates) should not be reordered"
        )

    def test_word_reorder_preserves_case(self):
        """Word-reorder aliases should preserve original casing."""
        aliases = generate_word_reorder_aliases("Mendelssohn, Moses")
        assert len(aliases) >= 1
        forms = [a.alias_form for a in aliases]
        assert "Moses Mendelssohn" in forms, (
            f"Expected 'Moses Mendelssohn' (case-preserved), got {forms}"
        )


class TestCrossScriptAlias:
    """Tests for cross-script alias generation from enrichment."""

    def test_cross_script_alias_from_hebrew_label(self):
        """Hebrew labels from authority_enrichment.person_info.hebrew_label
        should become aliases with alias_type='cross_script' and
        script='hebrew'."""
        person_info = {"hebrew_label": "רמב\"ם", "birth_year": 1138}
        aliases = generate_cross_script_aliases(
            person_info=person_info,
            enrichment_label="Moshe ben Maimon",
        )

        # Should produce at least one cross-script alias
        assert len(aliases) >= 1

        hebrew_aliases = [a for a in aliases if a.script == "hebrew"]
        assert len(hebrew_aliases) >= 1, (
            "Expected at least one Hebrew cross-script alias"
        )

        hebrew_forms = [a.alias_form for a in hebrew_aliases]
        assert 'רמב"ם' in hebrew_forms, (
            f"Expected Hebrew label in aliases, got {hebrew_forms}"
        )

    def test_cross_script_includes_enrichment_label(self):
        """The enrichment label itself should also be added as a
        variant_spelling alias if it differs from existing agent_norm."""
        person_info = {"hebrew_label": "משה מנדלסון"}
        aliases = generate_cross_script_aliases(
            person_info=person_info,
            enrichment_label="Moses Mendelssohn",
        )

        all_forms = [a.alias_form.lower() for a in aliases]
        assert "moses mendelssohn" in all_forms, (
            f"Enrichment label should be included as alias, got {all_forms}"
        )


class TestDeduplication:
    """Tests for duplicate alias handling."""

    def test_deduplication(self):
        """Attempting to insert a duplicate alias should be handled
        gracefully (INSERT OR IGNORE), not raise an error."""
        conn = _make_db()

        # First seed should succeed
        seed_from_enrichment(conn)

        # Manually try to insert a duplicate alias
        # This should NOT raise sqlite3.IntegrityError
        existing = conn.execute(
            "SELECT alias_form_lower FROM agent_aliases LIMIT 1"
        ).fetchone()

        if existing:
            # Try inserting the same form again -- should be ignored
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO agent_aliases
                       (authority_id, alias_form, alias_form_lower, alias_type,
                        script, is_primary, priority, created_at)
                       VALUES (1, ?, ?, 'primary', 'latin', 0, 0, '2025-01-01')""",
                    (existing["alias_form_lower"], existing["alias_form_lower"]),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pytest.fail(
                    "Duplicate alias insertion should use INSERT OR IGNORE, "
                    "not raise IntegrityError"
                )


class TestIdempotency:
    """Tests for seeding idempotency."""

    def test_idempotency(self):
        """Running seed_all twice should produce the same number of
        authorities and aliases (no duplicates created)."""
        conn = _make_db()

        stats1 = seed_all(conn)

        auth_count_1 = conn.execute(
            "SELECT COUNT(*) as c FROM agent_authorities"
        ).fetchone()["c"]
        alias_count_1 = conn.execute(
            "SELECT COUNT(*) as c FROM agent_aliases"
        ).fetchone()["c"]

        # Run again
        stats2 = seed_all(conn)

        auth_count_2 = conn.execute(
            "SELECT COUNT(*) as c FROM agent_authorities"
        ).fetchone()["c"]
        alias_count_2 = conn.execute(
            "SELECT COUNT(*) as c FROM agent_aliases"
        ).fetchone()["c"]

        assert auth_count_1 == auth_count_2, (
            f"Authority count changed after second seed: {auth_count_1} -> {auth_count_2}"
        )
        assert alias_count_1 == alias_count_2, (
            f"Alias count changed after second seed: {alias_count_1} -> {alias_count_2}"
        )


class TestSeedStatistics:
    """Tests for seed_all statistics reporting."""

    def test_seed_statistics(self):
        """seed_all should return a dict with count statistics."""
        conn = _make_db()

        stats = seed_all(conn)

        assert isinstance(stats, dict), f"Expected dict, got {type(stats)}"
        assert "authorities_created" in stats, (
            f"Stats should include 'authorities_created', got keys: {list(stats.keys())}"
        )
        assert "aliases_created" in stats, (
            f"Stats should include 'aliases_created', got keys: {list(stats.keys())}"
        )
        assert stats["authorities_created"] >= 4, (
            f"Expected at least 4 authorities, got {stats['authorities_created']}"
        )
        assert stats["aliases_created"] >= 4, (
            f"Expected at least 4 aliases (one per agent_norm minimum), "
            f"got {stats['aliases_created']}"
        )

    def test_seed_statistics_include_types(self):
        """Statistics should break down aliases by type."""
        conn = _make_db()

        stats = seed_all(conn)

        # Should report primary aliases (from agent_norm values)
        assert "primary_aliases" in stats or "aliases_by_type" in stats, (
            f"Stats should report alias type breakdown, got keys: {list(stats.keys())}"
        )
