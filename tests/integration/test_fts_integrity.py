"""Issue #9 acceptance: FTS rebuild makes titles/subjects updatable again,
keeps search results byte-identical, and the parity check guards sync.

Works on a throwaway COPY of the real DB — never the original.
"""
import shutil
import sqlite3
from pathlib import Path

import pytest

DB_PATH = Path("data/index/bibliographic.db")

pytestmark = pytest.mark.integration

SEARCH_BATTERY = [
    ("subjects_fts", '"geography"'),
    ("subjects_fts", '"printing"'),
    ("subjects_fts", "דפוס"),
    ("subjects_fts", '"jews"'),
    ("titles_fts", '"atlas"'),
    ("titles_fts", "דפוס"),
]


def _search_snapshot(conn):
    snap = {}
    for table, q in SEARCH_BATTERY:
        rows = conn.execute(
            f"SELECT rowid FROM {table} WHERE {table} MATCH ? ORDER BY rowid", (q,)
        ).fetchall()
        snap[(table, q)] = [r[0] for r in rows]
    return snap


@pytest.fixture()
def db_copy(tmp_path):
    if not DB_PATH.exists():
        pytest.skip("Bibliographic database not available")
    dst = tmp_path / "bib.db"
    shutil.copy(DB_PATH, dst)
    return dst


def test_rebuild_preserves_searches_and_enables_updates(db_copy):
    from scripts.qa.fixes.fix_20_rebuild_fts import rebuild

    before = _search_snapshot(sqlite3.connect(str(db_copy)))
    report = rebuild(db_copy, apply=True)
    assert report["verified"] is True

    conn = sqlite3.connect(str(db_copy))
    conn.row_factory = sqlite3.Row
    after = _search_snapshot(conn)
    assert before == after, "search results changed across the rebuild!"

    # The actual bug: these statements failed database-wide before the fix.
    conn.execute("UPDATE subjects SET value_he = value_he WHERE id = (SELECT MIN(id) FROM subjects)")
    conn.execute("UPDATE titles SET value = value WHERE id = (SELECT MIN(id) FROM titles)")
    # DELETE round-trip on sacrificial rows
    rec = conn.execute("SELECT MIN(id) FROM records").fetchone()[0]
    conn.execute("INSERT INTO subjects (record_id, value, source_tag, parts, source) VALUES (?, 'Zz-test-heading', '650', '{}', '[]')", (rec,))
    sid = conn.execute("SELECT id FROM subjects WHERE value='Zz-test-heading'").fetchone()[0]
    n = conn.execute("SELECT COUNT(*) FROM subjects_fts WHERE subjects_fts MATCH '\"zz-test-heading\"'").fetchone()[0]
    assert n == 1, "insert trigger did not index the new row"
    conn.execute("DELETE FROM subjects WHERE id = ?", (sid,))
    n = conn.execute("SELECT COUNT(*) FROM subjects_fts WHERE subjects_fts MATCH '\"zz-test-heading\"'").fetchone()[0]
    assert n == 0, "delete trigger did not unindex the row"
    conn.commit()

    # Hebrew update round-trip (the silent-desync scenario from the issue)
    conn.execute("UPDATE subjects SET value_he = 'בדיקת-עדכון' WHERE id = (SELECT MIN(id) FROM subjects)")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM subjects_fts WHERE subjects_fts MATCH 'בדיקת'").fetchone()[0]
    assert n == 1, "update trigger did not reindex value_he"
    conn.close()


def test_parity_check_passes_after_rebuild(db_copy):
    from scripts.qa.fixes.fix_20_rebuild_fts import rebuild
    from scripts.qa.fts_parity_check import check_parity

    rebuild(db_copy, apply=True)
    problems = check_parity(db_copy)
    assert problems == [], f"parity check found: {problems}"


def test_parity_check_detects_desync(db_copy):
    from scripts.qa.fixes.fix_20_rebuild_fts import rebuild
    from scripts.qa.fts_parity_check import check_parity

    rebuild(db_copy, apply=True)
    conn = sqlite3.connect(str(db_copy))
    # simulate a fix script bypassing triggers (the historical workaround)
    conn.execute("DROP TRIGGER subjects_fts_delete")
    conn.execute("DELETE FROM subjects WHERE id = (SELECT MIN(id) FROM subjects)")
    conn.commit(); conn.close()
    problems = check_parity(db_copy)
    assert problems, "parity check failed to detect a trigger-bypass desync"
