"""Unit tests for fix_30 (issue #58): repair D1 + D3, report D2 + D4.

The fix runs DRY-RUN by default and never touches the live DB. These tests
build a tiny in-tmp sqlite fixture reproducing:

* D1 — authority-linked agent_norms with NO alias row anywhere (the
  fix_29 collision-order residue): a clean single-authority case that is
  repaired, PLUS two in-plan dual-claims where the same vanished norm is the
  expected primary of two distinct authorities at once (only one can hold the
  unique alias_form_lower — the lower authority_id wins, the loser is reported
  as still-colliding). This is the exact live shape: every one of the 26
  missing norms is absent from agent_aliases entirely, so the only realizable
  collision is an in-plan dual-claim, not a pre-existing foreign alias (a norm
  that is already someone's alias is, by definition, not an I1 violation).
* D3 — two `same_place_period` network_edges whose endpoint node was merged
  away (the `מנשה בן ישראל` orphan-edge shape).

Assertions: the plan inserts exactly the repairable D1 norms (one alias per
distinct form, of the authority that wins deterministically), reports the
collision/dual-claim cases instead of forcing them, and plans the two D3
deletions. The dry run must emit the literal string "DRY RUN" and must not
write to the fixture DB.
"""
import sqlite3
from pathlib import Path

from scripts.qa.fixes.fix_30_repair_seam_audit_violations import run


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE agent_authorities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL,
            canonical_name_lower TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            authority_uri TEXT,
            wikidata_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            authority_uri TEXT,
            agent_norm TEXT NOT NULL
        );
        CREATE TABLE agent_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            authority_id INTEGER NOT NULL,
            alias_form TEXT NOT NULL,
            alias_form_lower TEXT NOT NULL,
            alias_type TEXT NOT NULL,
            script TEXT DEFAULT 'latin',
            language TEXT,
            is_primary INTEGER NOT NULL DEFAULT 0,
            priority INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX idx_agent_alias_form_lower
            ON agent_aliases(alias_form_lower);

        CREATE TABLE network_agents (
            agent_norm TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            node_type TEXT DEFAULT 'person',
            connection_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE network_edges (
            source_agent_norm TEXT NOT NULL,
            target_agent_norm TEXT NOT NULL,
            connection_type TEXT NOT NULL,
            confidence REAL NOT NULL,
            UNIQUE(source_agent_norm, target_agent_norm, connection_type)
        );

        -- report-only tables (kept empty: D2/D4 report 0 in this fixture)
        CREATE TABLE publisher_authorities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL,
            canonical_name_lower TEXT NOT NULL,
            type TEXT NOT NULL
        );
        CREATE TABLE publisher_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            authority_id INTEGER NOT NULL,
            variant_form TEXT NOT NULL,
            variant_form_lower TEXT NOT NULL
        );
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            authority_uri TEXT NOT NULL,
            wikidata_id TEXT
        );
        """
    )
    now = "2026-06-13T00:00:00+00:00"

    # --- Authorities -------------------------------------------------------
    # 1: clean repairable case (norm 'adam' missing, no collision)
    # 2 & 3: both claim vanished Latin mononym 'rene' -> dual-claim (2 wins)
    # 4 & 5: both claim vanished Hebrew mononym 'מנשה' -> dual-claim (4 wins)
    authorities = [
        (1, "Adam de la Halle", "uri:adam"),
        (2, "Rene Descartes", "uri:rene-d"),
        (3, "Rene of Anjou", "uri:rene-a"),
        (4, "Manasseh ben Israel", "uri:manasseh"),
        (5, "Manasseh Placeholder", "uri:manasseh-2"),
    ]
    for aid, canon, uri in authorities:
        conn.execute(
            "INSERT INTO agent_authorities "
            "(id, canonical_name, canonical_name_lower, agent_type, "
            " authority_uri, created_at, updated_at) "
            "VALUES (?, ?, LOWER(?), 'personal', ?, ?, ?)",
            (aid, canon, canon, uri, now, now),
        )

    # --- Agents (authority_uri -> agent_norm) ------------------------------
    # No alias rows seeded for any of these norms: each is a true I1 violation.
    agent_rows = [
        (101, "uri:adam", "adam"),       # missing, repairable -> auth 1
        (102, "uri:rene-d", "rene"),     # missing, dual-claim -> auth 2 (wins)
        (103, "uri:rene-a", "rene"),     # missing, dual-claim -> auth 3 (loses)
        (104, "uri:manasseh", "מנשה"),    # missing, dual-claim -> auth 4 (wins)
        (105, "uri:manasseh-2", "מנשה"),  # missing, dual-claim -> auth 5 (loses)
    ]
    for rid, uri, norm in agent_rows:
        conn.execute(
            "INSERT INTO agents (record_id, authority_uri, agent_norm) "
            "VALUES (?, ?, ?)",
            (rid, uri, norm),
        )

    # --- Network nodes + edges (D3) ---------------------------------------
    # 'manasseh ben israel' survives the merge; 'מנשה בן ישראל' node is gone.
    # connection_count seeded to the true pre-deletion degree (edges touching
    # the node), so invariant N4 holds before fix_30 runs: manasseh=1 (valid
    # edge), druker=1 (orphan edge), karo=2 (orphan + valid edge).
    for norm, disp, count in [
        ("manasseh ben israel", "Manasseh ben Israel", 1),
        ("דרוקר, חיים בן יעקב", "Druker", 1),
        ("קארו, יוסף בן אפרים", "Karo", 2),
    ]:
        conn.execute(
            "INSERT INTO network_agents "
            "(agent_norm, display_name, node_type, connection_count) "
            "VALUES (?, ?, 'person', ?)",
            (norm, disp, count),
        )
    # Two orphan same_place_period edges referencing the merged-away node.
    conn.execute(
        "INSERT INTO network_edges "
        "(source_agent_norm, target_agent_norm, connection_type, confidence) "
        "VALUES ('דרוקר, חיים בן יעקב', 'מנשה בן ישראל', 'same_place_period', 0.5)"
    )
    conn.execute(
        "INSERT INTO network_edges "
        "(source_agent_norm, target_agent_norm, connection_type, confidence) "
        "VALUES ('מנשה בן ישראל', 'קארו, יוסף בן אפרים', 'same_place_period', 0.5)"
    )
    # A valid edge that must NOT be touched.
    conn.execute(
        "INSERT INTO network_edges "
        "(source_agent_norm, target_agent_norm, connection_type, confidence) "
        "VALUES ('manasseh ben israel', 'קארו, יוסף בן אפרים', 'same_place_period', 0.5)"
    )
    conn.commit()
    conn.close()


def _row_count(path: Path, table: str) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_dry_run_plan_d1_and_d3(tmp_path, capsys):
    db = tmp_path / "fixture.db"
    _make_db(db)

    before_aliases = _row_count(db, "agent_aliases")
    before_edges = _row_count(db, "network_edges")

    result = run(db, apply=False)
    out = capsys.readouterr().out

    # Literal contract: dry-run output names itself.
    assert "DRY RUN" in out

    # D1: exactly one insertion per distinct repairable norm, attributed to the
    # deterministic winner ('adam' -> auth 1; 'rene' -> auth 2; 'מנשה' -> auth 4).
    assert result["would_insert_d1"] == 3
    insert_forms = {(norm, aid) for aid, norm, _script in result["d1_insertions"]}
    assert ("adam", 1) in insert_forms
    assert ("rene", 2) in insert_forms      # lowest authority_id wins
    assert ("מנשה", 4) in insert_forms

    # The dual-claim losers are NOT planned (the unique alias_form_lower index
    # can hold each form once).
    assert ("rene", 3) not in insert_forms
    assert ("מנשה", 5) not in insert_forms
    # Each distinct form is inserted at most once.
    assert len({norm for _aid, norm, _s in result["d1_insertions"]}) == 3

    # Both losers are REPORTED as collisions needing curation, naming the holder.
    assert result["d1_collisions"] == 2
    collision_pairs = {
        (norm, aid, holder)
        for aid, norm, holder in result["d1_collisions_detail"]
    }
    assert ("rene", 3, 2) in collision_pairs   # auth 3 lost 'rene' to auth 2
    assert ("מנשה", 5, 4) in collision_pairs   # auth 5 lost 'מנשה' to auth 4

    # D3: exactly the two orphan same_place_period edges are planned for delete.
    assert result["would_delete_d3"] == 2
    deleted = {(s, t) for s, t, _ct in result["d3_deletions"]}
    assert ("דרוקר, חיים בן יעקב", "מנשה בן ישראל") in deleted
    assert ("מנשה בן ישראל", "קארו, יוסף בן אפרים") in deleted

    # DRY RUN must not have written anything.
    assert result["applied"] is False
    assert _row_count(db, "agent_aliases") == before_aliases
    assert _row_count(db, "network_edges") == before_edges


def test_d1_insertion_resolves_invariant_i1(tmp_path):
    """After applying, every authority-linked norm has an alias row.

    Runs against a throwaway tmp DB (never the live DB). Confirms the plan,
    when applied, drives the I1 violation count to its irreducible floor
    (only the genuinely-colliding norms remain unlinked under those auths).
    """
    db = tmp_path / "fixture.db"
    _make_db(db)

    run(db, apply=True)

    conn = sqlite3.connect(str(db))
    try:
        # Every distinct agent_norm now appears as an alias_form_lower.
        unlinked_distinct = conn.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT ag.agent_norm "
            "FROM agents ag JOIN agent_authorities aa "
            "ON aa.authority_uri = ag.authority_uri "
            "WHERE ag.agent_norm NOT IN "
            "(SELECT alias_form_lower FROM agent_aliases))"
        ).fetchone()[0]
        assert unlinked_distinct == 0

        # alias_form_lower stays globally unique (no forced duplicates).
        dupes = conn.execute(
            "SELECT COUNT(*) FROM (SELECT alias_form_lower FROM agent_aliases "
            "GROUP BY alias_form_lower HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        assert dupes == 0

        # The two orphan edges are gone; the valid edge survives.
        orphans = conn.execute(
            "SELECT COUNT(*) FROM network_edges e WHERE "
            "e.source_agent_norm NOT IN (SELECT agent_norm FROM network_agents) "
            "OR e.target_agent_norm NOT IN (SELECT agent_norm FROM network_agents)"
        ).fetchone()[0]
        assert orphans == 0
        assert conn.execute("SELECT COUNT(*) FROM network_edges").fetchone()[0] == 1
    finally:
        conn.close()


def test_d3_recomputes_connection_count(tmp_path):
    """Deleting orphan edges must recompute connection_count on the surviving
    endpoints so invariant N4 (connection_count == edges touching node) holds.

    Regression for the cascade the invariant battery caught: the first fix_30
    deleted edges without updating counts, leaving N4 violated by 2.
    """
    db = tmp_path / "fixture.db"
    _make_db(db)

    run(db, apply=True)

    conn = sqlite3.connect(str(db))
    try:
        n4_mismatch = conn.execute(
            "SELECT COUNT(*) FROM network_agents na WHERE na.connection_count <> "
            "(SELECT COUNT(*) FROM network_edges e WHERE "
            "e.source_agent_norm = na.agent_norm OR e.target_agent_norm = na.agent_norm)"
        ).fetchone()[0]
        assert n4_mismatch == 0

        # Druker lost its only (orphan) edge -> 0; Karo kept the valid edge -> 1.
        counts = dict(
            conn.execute("SELECT agent_norm, connection_count FROM network_agents")
        )
        assert counts["דרוקר, חיים בן יעקב"] == 0
        assert counts["קארו, יוסף בן אפרים"] == 1
        assert counts["manasseh ben israel"] == 1
    finally:
        conn.close()
