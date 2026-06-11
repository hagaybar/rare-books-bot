"""fix_22: add collection-derived same_record edges in place (issue #26).

The network's edges were 99.7% Wikipedia-derived; the collection's own
connective tissue — agents who appear on the SAME catalogue record — was
never materialized. This adds `same_record` edges (role-typed, evidenced
with MMS IDs) additively to the existing network_edges table, then
recomputes network_agents.connection_count so node sizes reflect them.

~2,100 new evidenced edges connect ~850 previously-isolated agents. No
nodes/coordinates touched; INSERT OR IGNORE so re-runs are safe.

Usage:
    poetry run python scripts/qa/fixes/fix_22_add_same_record_edges.py \
        [--apply] [--db data/index/bibliographic.db]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.network.build_network_tables import build_same_record_edges  # noqa: E402

FIX_ID = "fix_22_add_same_record_edges"


def _recompute_connection_count(conn: sqlite3.Connection) -> None:
    conn.execute(
        """UPDATE network_agents SET connection_count = (
               SELECT COUNT(*) FROM (
                   SELECT source_agent_norm AS a FROM network_edges
                   UNION ALL
                   SELECT target_agent_norm FROM network_edges
               ) e WHERE e.a = network_agents.agent_norm
           )"""
    )


def add_edges(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        before = conn.execute(
            "SELECT COUNT(*) FROM network_edges WHERE connection_type='same_record'"
        ).fetchone()[0]
    finally:
        conn.close()

    report = {"fix_id": FIX_ID, "existing_same_record": before, "applied": False}

    if not apply:
        conn = sqlite3.connect(":memory:")
        # dry-run: count what WOULD be added against a copy
        src = sqlite3.connect(str(db_path))
        src.backup(conn)
        src.close()
        conn.row_factory = sqlite3.Row
        added = build_same_record_edges(conn)
        conn.rollback()
        conn.close()
        report["would_add"] = added
        print(f"[{FIX_ID}] DRY RUN — would add {added} same_record edges "
              f"({before} already present). Use --apply.")
        return report

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix22.bak")
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(backup))
        with dst:
            src.backup(dst)
        dst.close()
    finally:
        src.close()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        added = build_same_record_edges(conn)
        _recompute_connection_count(conn)
        conn.commit()
    finally:
        conn.close()

    report["applied"] = True
    report["added"] = added
    print(f"[{FIX_ID}] applied: added {added} same_record edges; "
          f"connection_count recomputed. Backup: {backup.name}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    add_edges(args.db, apply=args.apply)


if __name__ == "__main__":
    main()
