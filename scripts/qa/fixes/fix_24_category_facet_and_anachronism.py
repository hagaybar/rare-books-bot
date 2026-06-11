"""fix_24: category-coloring facet + same_place_period anachronism fix (issue #28).

Two in-place, additive corrections to an existing bibliographic.db:

1. **Community facet** — adds ``network_agents.community`` and assigns each node
   the most-specific allow-listed Wikipedia category (maintenance/metadata
   categories excluded). Category edges stay in the table but the API stops
   serving them as arcs; this column drives node *coloring* instead.
2. **Anachronism fix** — re-derives ``same_place_period`` edges with the new
   lifespan-clamped builder, so a posthumous reprint no longer makes a dead
   agent "active" (e.g. Gravelot d.1773 "active in London 1896-1906").

Idempotent: re-running re-derives the same edges and re-assigns the same
communities. A ``.pre-fix24.bak`` backup is taken before --apply.

Usage:
    poetry run python scripts/qa/fixes/fix_24_category_facet_and_anachronism.py \
        [--apply] [--db data/index/bibliographic.db]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.network.build_network_tables import (  # noqa: E402
    assign_communities,
    _build_same_place_period_edges,
)

FIX_ID = "fix_24_category_facet_and_anachronism"


def _ensure_community_column(conn: sqlite3.Connection) -> None:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(network_agents)")]
    if "community" not in cols:
        conn.execute("ALTER TABLE network_agents ADD COLUMN community TEXT")


def _recompute_connection_count(conn: sqlite3.Connection) -> None:
    conn.execute(
        """UPDATE network_agents SET connection_count = (
               SELECT COUNT(*) FROM (
                   SELECT source_agent_norm AS a FROM network_edges
                   UNION ALL SELECT target_agent_norm FROM network_edges
               ) e WHERE e.a = network_agents.agent_norm)"""
    )


def _rederive_same_place_period(conn: sqlite3.Connection) -> tuple[int, int]:
    """Drop and rebuild same_place_period edges with lifespan clamping.

    Returns (before_count, after_count).
    """
    before = conn.execute(
        "SELECT COUNT(*) FROM network_edges WHERE connection_type='same_place_period'"
    ).fetchone()[0]
    conn.execute("DELETE FROM network_edges WHERE connection_type='same_place_period'")
    after = _build_same_place_period_edges(conn)
    return before, after


def _do(conn: sqlite3.Connection) -> dict:
    _ensure_community_column(conn)
    spp_before, spp_after = _rederive_same_place_period(conn)
    community_stats = assign_communities(conn)
    _recompute_connection_count(conn)
    return {
        "spp_before": spp_before,
        "spp_after": spp_after,
        "spp_removed": spp_before - spp_after,
        "community_assigned": community_stats["assigned"],
        "communities": community_stats["communities"],
        "community_sizes": community_stats["community_sizes"],
    }


def run(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path)
    report = {"fix_id": FIX_ID, "applied": False}

    if not apply:
        conn = sqlite3.connect(":memory:")
        src = sqlite3.connect(str(db_path))
        src.backup(conn)
        src.close()
        result = _do(conn)
        conn.rollback()
        conn.close()
        report.update(result)
        print(
            f"[{FIX_ID}] DRY RUN — same_place_period {result['spp_before']} -> "
            f"{result['spp_after']} ({result['spp_removed']} anachronistic dropped); "
            f"{result['community_assigned']} nodes colored across "
            f"{len(result['communities'])} communities. Use --apply."
        )
        print(f"[{FIX_ID}] communities: {', '.join(result['communities'])}")
        return report

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix24.bak")
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
        result = _do(conn)
        conn.commit()
    finally:
        conn.close()

    report.update(applied=True, **result)
    print(
        f"[{FIX_ID}] applied: same_place_period {result['spp_before']} -> "
        f"{result['spp_after']} ({result['spp_removed']} anachronistic dropped); "
        f"{result['community_assigned']} nodes colored across "
        f"{len(result['communities'])} communities. Backup: {backup.name}"
    )
    print(f"[{FIX_ID}] communities: {', '.join(result['communities'])}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run(args.db, apply=args.apply)


if __name__ == "__main__":
    main()
