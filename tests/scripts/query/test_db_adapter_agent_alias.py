"""Integration tests for agent alias-aware query execution.

Validates that ``build_where_clause`` (and downstream ``build_full_query``)
correctly resolves agent names via the ``agent_aliases``/``agent_authorities``
tables, enabling:

- Word-reorder matching: 'Johann Buxtorf' finds 'buxtorf, johann'
- Cross-script matching: Latin query finds Hebrew agent_norm
- Unified authority: 'Maimonides' finds both Latin and Hebrew forms
- Latin-to-Hebrew bridging: 'Joseph Karo' finds Hebrew-only records
- Printer alias resolution: 'Aldus Manutius' resolves correctly
- Graceful degradation: queries work when alias tables don't exist

These tests are written TDD-style: they will FAIL until the alias
resolution code is added to ``scripts/query/db_adapter.py``.
"""

import json
import sqlite3
from typing import List

import pytest

from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp
from scripts.query.db_adapter import (
    build_where_clause,
    build_full_query,
    reset_agent_alias_cache,
)


# ---------------------------------------------------------------------------
# Mini-database fixture
# ---------------------------------------------------------------------------


def _create_mini_db(*, include_alias_tables: bool = True) -> sqlite3.Connection:
    """Create an in-memory SQLite database with all tables needed for
    agent alias integration tests.

    Tables created:
      - records: minimal record table
      - agents: agent entries for Buxtorf, Mendelssohn, Maimonides, Karo,
                Aldus Manutius (in various name forms and scripts)
      - agent_authorities: canonical agent identities
      - agent_aliases: name variants (primary, word_reorder, cross_script)

    When ``include_alias_tables=False``, the agent_authorities and
    agent_aliases tables are omitted to test graceful degradation.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # --- records ---
    conn.execute("""
        CREATE TABLE records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mms_id TEXT NOT NULL UNIQUE
        )
    """)

    # --- agents (M3 schema subset) ---
    conn.execute("""
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL REFERENCES records(id),
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

    # --- imprints (needed for some queries) ---
    conn.execute("""
        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL REFERENCES records(id),
            publisher_raw TEXT,
            publisher_norm TEXT,
            publisher_confidence REAL,
            publisher_method TEXT,
            place_raw TEXT,
            place_norm TEXT,
            place_confidence REAL,
            place_method TEXT,
            date_raw TEXT,
            date_start INTEGER,
            date_end INTEGER,
            date_confidence REAL,
            date_method TEXT,
            source_tags TEXT
        )
    """)

    # ---- Insert records ----
    records = [
        (1, "990001001"),  # Buxtorf rec 1
        (2, "990001002"),  # Buxtorf rec 2
        (3, "990002001"),  # Mendelssohn Latin
        (4, "990002002"),  # Mendelssohn Hebrew
        (5, "990003001"),  # Maimonides Latin
        (6, "990003002"),  # Maimonides Hebrew 1
        (7, "990003003"),  # Maimonides Hebrew 2
        (8, "990004001"),  # Karo Hebrew
        (9, "990004002"),  # Karo Hebrew 2
        (10, "990005001"),  # Aldus Manutius
    ]
    conn.executemany(
        "INSERT INTO records (id, mms_id) VALUES (?, ?)", records
    )

    # ---- Insert agents ----

    # Buxtorf: surname-first form, shared authority_uri
    agents = [
        # (record_id, agent_norm, authority_uri, agent_type)
        (1, "buxtorf, johann", "987007260000005171", "personal"),
        (2, "buxtorf, johann", "987007260000005171", "personal"),
        # Mendelssohn: Latin form
        (3, "mendelssohn, moses", "987007265100005171", "personal"),
        # Mendelssohn: Hebrew form
        (4, "מנדלסון, משה", "987007265100005171", "personal"),
        # Maimonides: Latin form
        (5, "maimonides, moses", "987007265654005171", "personal"),
        # Maimonides: Hebrew patronymic forms
        (6, "משה בן מימון", "987007265654005171", "personal"),
        (7, "משה בן מימון", "987007265654005171", "personal"),
        # Karo: Hebrew only in agents table
        (8, "קארו, יוסף בן אפרים", "987007500000005171", "personal"),
        (9, "קארו, יוסף בן אפרים", "987007500000005171", "personal"),
        # Aldus Manutius: printer
        (10, "manuzio, aldo", "987007480000005171", "personal"),
    ]
    for record_id, agent_norm, auth_uri, agent_type in agents:
        conn.execute(
            """INSERT INTO agents
               (record_id, agent_index, agent_raw, agent_norm,
                authority_uri, agent_type)
               VALUES (?, 0, ?, ?, ?, ?)""",
            (record_id, agent_norm, agent_norm, auth_uri, agent_type),
        )

    if not include_alias_tables:
        conn.commit()
        return conn

    # --- agent_authorities ---
    conn.execute("""
        CREATE TABLE agent_authorities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL,
            canonical_name_lower TEXT NOT NULL,
            agent_type TEXT NOT NULL CHECK(agent_type IN ('personal', 'corporate', 'meeting')),
            dates_active TEXT,
            date_start INTEGER,
            date_end INTEGER,
            notes TEXT,
            sources TEXT,
            confidence REAL NOT NULL DEFAULT 0.5,
            authority_uri TEXT,
            wikidata_id TEXT,
            viaf_id TEXT,
            nli_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX idx_agent_auth_canonical_lower
            ON agent_authorities(canonical_name_lower)
    """)
    conn.execute("""
        CREATE INDEX idx_agent_auth_authority_uri
            ON agent_authorities(authority_uri)
    """)

    # --- agent_aliases ---
    conn.execute("""
        CREATE TABLE agent_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            authority_id INTEGER NOT NULL REFERENCES agent_authorities(id) ON DELETE CASCADE,
            alias_form TEXT NOT NULL,
            alias_form_lower TEXT NOT NULL,
            alias_type TEXT NOT NULL CHECK(alias_type IN (
                'primary', 'variant_spelling', 'cross_script',
                'patronymic', 'acronym', 'word_reorder', 'historical'
            )),
            script TEXT DEFAULT 'latin',
            language TEXT,
            is_primary INTEGER NOT NULL DEFAULT 0,
            priority INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX idx_agent_alias_authority
            ON agent_aliases(authority_id)
    """)
    conn.execute("""
        CREATE UNIQUE INDEX idx_agent_alias_form_lower
            ON agent_aliases(alias_form_lower)
    """)

    now = "2025-01-01T00:00:00Z"

    # ---- Insert authorities ----
    authorities = [
        # (id, canonical_name, canonical_name_lower, agent_type, authority_uri)
        (1, "Buxtorf, Johann", "buxtorf, johann", "personal", "987007260000005171"),
        (2, "Mendelssohn, Moses", "mendelssohn, moses", "personal", "987007265100005171"),
        (3, "Maimonides", "maimonides", "personal", "987007265654005171"),
        (4, "Karo, Joseph ben Ephraim", "karo, joseph ben ephraim", "personal", "987007500000005171"),
        (5, "Manutius, Aldus", "manutius, aldus", "personal", "987007480000005171"),
    ]
    for auth_id, name, name_lower, atype, auth_uri in authorities:
        conn.execute(
            """INSERT INTO agent_authorities
               (id, canonical_name, canonical_name_lower, agent_type,
                authority_uri, confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0.9, ?, ?)""",
            (auth_id, name, name_lower, atype, auth_uri, now, now),
        )

    # ---- Insert aliases ----
    aliases = [
        # Buxtorf aliases
        # (authority_id, alias_form, alias_form_lower, alias_type, script, is_primary)
        (1, "buxtorf, johann", "buxtorf, johann", "primary", "latin", 1),
        (1, "Johann Buxtorf", "johann buxtorf", "word_reorder", "latin", 0),
        (1, "Johann Buxtorf the Elder", "johann buxtorf the elder", "variant_spelling", "latin", 0),

        # Mendelssohn aliases
        (2, "mendelssohn, moses", "mendelssohn, moses", "primary", "latin", 1),
        (2, "Moses Mendelssohn", "moses mendelssohn", "word_reorder", "latin", 0),
        (2, "מנדלסון, משה", "מנדלסון, משה", "primary", "hebrew", 1),
        (2, "משה מנדלסון", "משה מנדלסון", "cross_script", "hebrew", 0),

        # Maimonides aliases
        (3, "maimonides, moses", "maimonides, moses", "primary", "latin", 1),
        (3, "Moses Maimonides", "moses maimonides", "word_reorder", "latin", 0),
        (3, "Maimonides", "maimonides", "variant_spelling", "latin", 0),
        (3, "Moshe ben Maimon", "moshe ben maimon", "variant_spelling", "latin", 0),
        (3, "משה בן מימון", "משה בן מימון", "primary", "hebrew", 1),
        (3, 'רמב"ם', 'רמב"ם', "acronym", "hebrew", 0),

        # Karo aliases (Latin label from enrichment for Hebrew-only agent)
        (4, "קארו, יוסף בן אפרים", "קארו, יוסף בן אפרים", "primary", "hebrew", 1),
        (4, "Joseph ben Ephraim Karo", "joseph ben ephraim karo", "variant_spelling", "latin", 0),
        (4, "Joseph Karo", "joseph karo", "variant_spelling", "latin", 0),
        (4, "יוסף קארו", "יוסף קארו", "cross_script", "hebrew", 0),

        # Aldus Manutius aliases
        (5, "manuzio, aldo", "manuzio, aldo", "primary", "latin", 1),
        (5, "Aldo Manuzio", "aldo manuzio", "word_reorder", "latin", 0),
        (5, "Aldus Manutius", "aldus manutius", "variant_spelling", "latin", 0),
    ]
    for auth_id, form, form_lower, atype, script, is_primary in aliases:
        conn.execute(
            """INSERT INTO agent_aliases
               (authority_id, alias_form, alias_form_lower, alias_type,
                script, is_primary, priority, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
            (auth_id, form, form_lower, atype, script, is_primary, now),
        )

    conn.commit()
    return conn


def _execute_query(conn: sqlite3.Connection, plan: QueryPlan) -> List[str]:
    """Execute a QueryPlan against the mini-database and return matched mms_ids."""
    reset_agent_alias_cache()
    sql, params = build_full_query(plan, conn=conn)
    rows = conn.execute(sql, params).fetchall()
    return sorted(set(row["mms_id"] for row in rows))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgentAliasQueryResolution:
    """Integration tests for alias-aware agent queries."""

    def test_query_buxtorf_word_reorder(self):
        """Query 'Johann Buxtorf' should find records where agent_norm
        is 'buxtorf, johann' via the word_reorder alias.

        Without alias resolution, this query returns 0 results because
        the DB stores 'buxtorf, johann' (surname-first) and the query
        uses 'Johann Buxtorf' (given-name-first).
        """
        conn = _create_mini_db()
        plan = QueryPlan(
            query_text="books by Johann Buxtorf",
            filters=[
                Filter(
                    field=FilterField.AGENT_NORM,
                    op=FilterOp.EQUALS,
                    value="Johann Buxtorf",
                )
            ],
        )

        results = _execute_query(conn, plan)

        assert len(results) >= 2, (
            f"Expected at least 2 Buxtorf records (990001001, 990001002), "
            f"got {len(results)}: {results}"
        )
        assert "990001001" in results
        assert "990001002" in results

    def test_query_mendelssohn_cross_script(self):
        """Latin query 'Moses Mendelssohn' should find records with
        Hebrew agent_norm 'מנדלסון, משה' via cross-script alias linkage
        through shared authority.

        Both Latin ('mendelssohn, moses') and Hebrew ('מנדלסון, משה')
        agent_norm values share authority_uri '987007265100005171'.
        The alias table links 'Moses Mendelssohn' (word_reorder) to
        this authority, which resolves to both agent forms.
        """
        conn = _create_mini_db()
        plan = QueryPlan(
            query_text="books by Moses Mendelssohn",
            filters=[
                Filter(
                    field=FilterField.AGENT_NORM,
                    op=FilterOp.EQUALS,
                    value="Moses Mendelssohn",
                )
            ],
        )

        results = _execute_query(conn, plan)

        # Should find both Latin and Hebrew records
        assert "990002001" in results, (
            f"Latin Mendelssohn record missing from results: {results}"
        )
        assert "990002002" in results, (
            f"Hebrew Mendelssohn record missing from results: {results}"
        )
        assert len(results) >= 2

    def test_query_maimonides_all_forms(self):
        """Query 'Maimonides' should unify results from both
        'maimonides, moses' (Latin) AND 'משה בן מימון' (Hebrew)
        via shared authority_uri '987007265654005171'.

        This is the key multi-form unification test. Without alias
        resolution, querying 'maimonides' only finds the Latin form
        (3 records) and misses the Hebrew patronymic form (2 records).
        """
        conn = _create_mini_db()
        plan = QueryPlan(
            query_text="books by Maimonides",
            filters=[
                Filter(
                    field=FilterField.AGENT_NORM,
                    op=FilterOp.CONTAINS,
                    value="Maimonides",
                )
            ],
        )

        results = _execute_query(conn, plan)

        # Should find Latin records
        assert "990003001" in results, (
            f"Latin Maimonides record (990003001) missing: {results}"
        )
        # Should also find Hebrew records via authority linkage
        assert "990003002" in results, (
            f"Hebrew Maimonides record (990003002) missing: {results}"
        )
        assert "990003003" in results, (
            f"Hebrew Maimonides record (990003003) missing: {results}"
        )
        assert len(results) >= 3, (
            f"Expected at least 3 Maimonides records (Latin + Hebrew), "
            f"got {len(results)}: {results}"
        )

    def test_query_karo_latin_to_hebrew(self):
        """Latin query 'Joseph Karo' should find records that only
        have Hebrew agent_norm 'קארו, יוסף בן אפרים'.

        The enrichment provides the Latin label 'Joseph ben Ephraim Karo'
        for an agent that only exists in Hebrew in the agents table.
        The alias 'Joseph Karo' is a variant_spelling alias linking
        to the same authority.
        """
        conn = _create_mini_db()
        plan = QueryPlan(
            query_text="books by Joseph Karo",
            filters=[
                Filter(
                    field=FilterField.AGENT_NORM,
                    op=FilterOp.EQUALS,
                    value="Joseph Karo",
                )
            ],
        )

        results = _execute_query(conn, plan)

        assert len(results) >= 2, (
            f"Expected at least 2 Karo records (990004001, 990004002), "
            f"got {len(results)}: {results}"
        )
        assert "990004001" in results
        assert "990004002" in results

    def test_query_aldus_manutius(self):
        """Agent alias 'Aldus Manutius' should resolve to records with
        agent_norm 'manuzio, aldo' via variant_spelling alias."""
        conn = _create_mini_db()
        plan = QueryPlan(
            query_text="books printed by Aldus Manutius",
            filters=[
                Filter(
                    field=FilterField.AGENT_NORM,
                    op=FilterOp.EQUALS,
                    value="Aldus Manutius",
                )
            ],
        )

        results = _execute_query(conn, plan)

        assert "990005001" in results, (
            f"Aldus Manutius record (990005001) missing: {results}"
        )
        assert len(results) >= 1

    def test_query_fallback_no_alias_tables(self):
        """When agent_authorities/agent_aliases tables do not exist,
        the query should still work using the existing direct-match
        path (graceful degradation).

        This ensures backward compatibility: existing deployments
        without the new tables continue to function.
        """
        reset_agent_alias_cache()
        conn = _create_mini_db(include_alias_tables=False)
        plan = QueryPlan(
            query_text="books by Maimonides",
            filters=[
                Filter(
                    field=FilterField.AGENT_NORM,
                    op=FilterOp.CONTAINS,
                    value="maimonides",
                )
            ],
        )

        # Should NOT raise an error — pass conn so alias tables are
        # detected as missing and the alias branch is omitted.
        sql, params = build_full_query(plan, conn=conn)
        rows = conn.execute(sql, params).fetchall()
        results = sorted(set(row["mms_id"] for row in rows))

        # Should still find the Latin form via direct LIKE match
        assert "990003001" in results, (
            f"Fallback direct match should find Latin 'maimonides' record, "
            f"got {results}"
        )
        # Hebrew forms won't be found (expected without alias tables)
        # The point is: NO error, and direct matching still works


class TestAgentAliasQueryWithContains:
    """Additional tests for CONTAINS operator with aliases."""

    def test_contains_partial_name(self):
        """CONTAINS query with partial name should still leverage aliases."""
        conn = _create_mini_db()
        plan = QueryPlan(
            query_text="books by Buxtorf",
            filters=[
                Filter(
                    field=FilterField.AGENT_NORM,
                    op=FilterOp.CONTAINS,
                    value="Buxtorf",
                )
            ],
        )

        results = _execute_query(conn, plan)

        assert len(results) >= 2, (
            f"Expected at least 2 Buxtorf records via CONTAINS, "
            f"got {len(results)}: {results}"
        )


class TestAgentAliasWhereClause:
    """Tests verifying the SQL WHERE clause structure for alias queries."""

    def test_where_clause_includes_alias_subquery(self):
        """The WHERE clause for AGENT_NORM EQUALS should include an
        OR branch with an EXISTS subquery against agent_aliases when
        alias tables are present."""
        plan = QueryPlan(
            query_text="books by Johann Buxtorf",
            filters=[
                Filter(
                    field=FilterField.AGENT_NORM,
                    op=FilterOp.EQUALS,
                    value="Johann Buxtorf",
                )
            ],
        )
        where, params, joins = build_where_clause(plan)

        # The WHERE clause should reference agent_aliases for resolution
        # The exact SQL depends on implementation, but it should contain
        # either a subquery or JOIN to agent_aliases
        where_lower = where.lower()
        has_alias_ref = (
            "agent_aliases" in where_lower
            or "agent_authorities" in where_lower
        )
        assert has_alias_ref, (
            f"WHERE clause should reference agent_aliases or "
            f"agent_authorities for alias resolution. Got:\n{where}"
        )

    def test_where_clause_preserves_direct_match(self):
        """The WHERE clause should still include the direct agent_norm
        match (OR'd with alias resolution) for backward compatibility."""
        plan = QueryPlan(
            query_text="books by Buxtorf",
            filters=[
                Filter(
                    field=FilterField.AGENT_NORM,
                    op=FilterOp.CONTAINS,
                    value="Buxtorf",
                )
            ],
        )
        where, params, joins = build_where_clause(plan)

        # Should still have the direct match condition
        where_lower = where.lower()
        assert "agent_norm" in where_lower or "a.agent_norm" in where_lower, (
            f"WHERE clause should preserve direct agent_norm match. Got:\n{where}"
        )
