"""fix_20: rebuild both FTS tables with correct, self-consistent definitions.

Issue #9 (committee 2026-06-11): the FTS triggers were broken database-wide —
``titles_fts`` declared columns (mms_id, title_type) its content table lacks,
so any UPDATE/DELETE on titles errored; ``subjects_fts`` was contentless
WITHOUT ``contentless_delete=1``, so its delete/update triggers were illegal
FTS5 operations. Net effect: both tables were accidentally append-only, and
fix scripts worked around it by dropping triggers (a silent-desync vector).

This rebuild:
- ``titles_fts``  -> external-content ``fts5(value, content=titles,
  content_rowid=id)`` (phantom columns dropped — all query paths join on
  rowid and never select FTS columns) with proper 'delete'-command triggers.
- ``subjects_fts`` -> contentless ``fts5(mms_id, value, content='',
  contentless_delete=1)`` so the standard triggers become legal. The indexed
  text stays ``value || ' ' || COALESCE(value_he, '')`` (bilingual search).

Safety: a fixed search battery is snapshotted before and re-run after the
rebuild; ANY difference rolls the database back from the pre-rebuild backup.

Usage:
    poetry run python scripts/qa/fixes/fix_20_rebuild_fts.py [--apply] \
        [--db data/index/bibliographic.db]
(default is dry-run: print what would change, touch nothing)
"""
import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

FIX_ID = "fix_20_rebuild_fts"

SEARCH_BATTERY = [
    ("subjects_fts", '"geography"'),
    ("subjects_fts", '"printing"'),
    ("subjects_fts", '"jews"'),
    ("subjects_fts", '"censorship"'),
    ("subjects_fts", "דפוס"),
    ("subjects_fts", "תלמוד"),
    ("titles_fts", '"atlas"'),
    ("titles_fts", '"geographie"'),
    ("titles_fts", "דפוס"),
]

NEW_SCHEMA_SQL = """
DROP TRIGGER IF EXISTS titles_fts_insert;
DROP TRIGGER IF EXISTS titles_fts_update;
DROP TRIGGER IF EXISTS titles_fts_delete;
DROP TABLE IF EXISTS titles_fts;

CREATE VIRTUAL TABLE titles_fts USING fts5(
    value,
    content=titles,
    content_rowid=id
);

CREATE TRIGGER titles_fts_insert AFTER INSERT ON titles BEGIN
    INSERT INTO titles_fts(rowid, value) VALUES (new.id, new.value);
END;
CREATE TRIGGER titles_fts_delete AFTER DELETE ON titles BEGIN
    INSERT INTO titles_fts(titles_fts, rowid, value)
    VALUES ('delete', old.id, old.value);
END;
CREATE TRIGGER titles_fts_update AFTER UPDATE ON titles BEGIN
    INSERT INTO titles_fts(titles_fts, rowid, value)
    VALUES ('delete', old.id, old.value);
    INSERT INTO titles_fts(rowid, value) VALUES (new.id, new.value);
END;

DROP TRIGGER IF EXISTS subjects_fts_insert;
DROP TRIGGER IF EXISTS subjects_fts_update;
DROP TRIGGER IF EXISTS subjects_fts_delete;
DROP TABLE IF EXISTS subjects_fts;

CREATE VIRTUAL TABLE subjects_fts USING fts5(
    mms_id,
    value,
    content='',
    contentless_delete=1
);

CREATE TRIGGER subjects_fts_insert AFTER INSERT ON subjects BEGIN
    INSERT INTO subjects_fts(rowid, mms_id, value)
    SELECT NEW.id, r.mms_id,
           NEW.value || ' ' || COALESCE(NEW.value_he, '')
    FROM records r WHERE r.id = NEW.record_id;
END;
CREATE TRIGGER subjects_fts_delete AFTER DELETE ON subjects BEGIN
    DELETE FROM subjects_fts WHERE rowid = OLD.id;
END;
CREATE TRIGGER subjects_fts_update AFTER UPDATE ON subjects BEGIN
    DELETE FROM subjects_fts WHERE rowid = OLD.id;
    INSERT INTO subjects_fts(rowid, mms_id, value)
    SELECT NEW.id, r.mms_id,
           NEW.value || ' ' || COALESCE(NEW.value_he, '')
    FROM records r WHERE r.id = NEW.record_id;
END;
"""

REPOPULATE_SQL = """
INSERT INTO titles_fts(titles_fts) VALUES ('rebuild');
INSERT INTO subjects_fts(rowid, mms_id, value)
SELECT s.id, r.mms_id, s.value || ' ' || COALESCE(s.value_he, '')
FROM subjects s JOIN records r ON s.record_id = r.id;
"""


def _snapshot(conn: sqlite3.Connection) -> dict:
    snap = {}
    for table, query in SEARCH_BATTERY:
        rows = conn.execute(
            f"SELECT rowid FROM {table} WHERE {table} MATCH ? ORDER BY rowid",
            (query,),
        ).fetchall()
        snap[f"{table} MATCH {query}"] = [r[0] for r in rows]
    return snap


def rebuild(db_path: Path, apply: bool = False) -> dict:
    """Rebuild both FTS tables. Returns a report dict.

    With apply=False (dry run) only the before-snapshot and SQLite-version
    check are performed. With apply=True a ``.pre-fix20.bak`` backup is taken
    first; any search-battery difference restores it and raises.
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        version = conn.execute("SELECT sqlite_version()").fetchone()[0]
        major, minor = (int(x) for x in version.split(".")[:2])
        if (major, minor) < (3, 43):
            raise RuntimeError(
                f"SQLite {version} lacks contentless_delete (need >= 3.43)"
            )
        before = _snapshot(conn)
    finally:
        conn.close()

    report = {
        "fix_id": FIX_ID,
        "sqlite_version": version,
        "battery_queries": len(before),
        "applied": False,
        "verified": False,
    }
    if not apply:
        print(f"[{FIX_ID}] DRY RUN — battery snapshot of {len(before)} queries OK; "
              f"sqlite {version} supports contentless_delete. Use --apply.")
        return report

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix20.bak")
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(backup))
        with dst:
            src.backup(dst)
        dst.close()
    finally:
        src.close()

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(NEW_SCHEMA_SQL)
        conn.executescript(REPOPULATE_SQL)
        conn.commit()
        after = _snapshot(conn)
    finally:
        conn.close()

    if before != after:
        diffs = [k for k in before if before[k] != after.get(k)]
        shutil.copy(backup, db_path)
        raise RuntimeError(
            f"[{FIX_ID}] search battery changed for {diffs} — database "
            f"RESTORED from {backup.name}"
        )

    report["applied"] = True
    report["verified"] = True
    print(f"[{FIX_ID}] applied and verified: {len(before)} battery queries "
          f"identical. Backup: {backup.name}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true", help="actually rebuild (default: dry run)")
    args = parser.parse_args()
    try:
        rebuild(args.db, apply=args.apply)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
