"""fix_23: add printing houses as first-class network nodes (issue #27).

For a hand-press collection the printer IS a network hub. This promotes
curated publisher_authorities (Bomberg, Plantin, Aldine, Soncino, Elzevir...)
to network_agents nodes (node_type='publisher', geocoded from their city,
sized by holdings), and links authors to the house that printed them via
'printed_by' edges. Additive + idempotent (INSERT OR REPLACE / OR IGNORE);
recomputes connection_count. No person nodes or coordinates touched.

Usage:
    poetry run python scripts/qa/fixes/fix_23_add_publisher_nodes.py \
        [--apply] [--db data/index/bibliographic.db]
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.network.build_network_tables import (  # noqa: E402
    build_publisher_nodes,
    build_printed_by_edges,
)

FIX_ID = "fix_23_add_publisher_nodes"
GEOCODES_PATH = Path("data/normalization/place_geocodes.json")


def _recompute_connection_count(conn: sqlite3.Connection) -> None:
    conn.execute(
        """UPDATE network_agents SET connection_count = (
               SELECT COUNT(*) FROM (
                   SELECT source_agent_norm AS a FROM network_edges
                   UNION ALL SELECT target_agent_norm FROM network_edges
               ) e WHERE e.a = network_agents.agent_norm)"""
    )


def run(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path)
    geocodes = json.loads(GEOCODES_PATH.read_text())
    report = {"fix_id": FIX_ID, "applied": False}

    if not apply:
        conn = sqlite3.connect(":memory:")
        src = sqlite3.connect(str(db_path))
        src.backup(conn)
        src.close()
        nodes = build_publisher_nodes(conn, geocodes)
        edges = build_printed_by_edges(conn)
        conn.rollback()
        conn.close()
        report.update(would_add_nodes=nodes, would_add_edges=edges)
        print(f"[{FIX_ID}] DRY RUN — would add {nodes} publisher nodes and "
              f"{edges} printed_by edges. Use --apply.")
        return report

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix23.bak")
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
        nodes = build_publisher_nodes(conn, geocodes)
        edges = build_printed_by_edges(conn)
        _recompute_connection_count(conn)
        conn.commit()
    finally:
        conn.close()

    report.update(applied=True, added_nodes=nodes, added_edges=edges)
    print(f"[{FIX_ID}] applied: {nodes} publisher nodes, {edges} printed_by "
          f"edges; connection_count recomputed. Backup: {backup.name}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run(args.db, apply=args.apply)


if __name__ == "__main__":
    main()
