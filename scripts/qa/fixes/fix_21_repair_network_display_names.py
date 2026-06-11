"""fix_21: repair corrupted network display names in place (issue #22).

The network builder's old display-name fallback grabbed an arbitrary
authority_enrichment.label, so agents whose records also point to a work
entity were labeled with the BOOK (Joseph Karo → "Kessef Mishneh"). The
builder is now fixed (scripts/network/build_network_tables.py:
resolve_display_name → _best_person_label, frequency-ranked + title-guarded),
but re-running the full builder regenerates coordinates/edges and is heavy.

This script re-resolves display_name for every network_agents row using the
corrected resolver and UPDATEs only the names that change — leaving nodes,
edges, and coordinates untouched. Dry-run by default; --apply takes a
backup first.

Usage:
    poetry run python scripts/qa/fixes/fix_21_repair_network_display_names.py \
        [--apply] [--db data/index/bibliographic.db]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

# resolve_display_name lives in the builder; reuse it verbatim.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.network.build_network_tables import resolve_display_name  # noqa: E402

FIX_ID = "fix_21_repair_network_display_names"


def _entity_names_ranked(conn: sqlite3.Connection, agent_norm: str) -> list[tuple[str, int]]:
    """(name, record_count) per authority entity for an agent, most-frequent first."""
    rows = conn.execute(
        """SELECT COALESCE(wc.wikipedia_title, ae.label) AS name, COUNT(*) AS n
           FROM agents a
           JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
           LEFT JOIN wikipedia_cache wc ON wc.wikidata_id = ae.wikidata_id
           WHERE a.agent_norm = ?
             AND (wc.wikipedia_title IS NOT NULL OR ae.label IS NOT NULL)
           GROUP BY ae.wikidata_id ORDER BY n DESC""",
        (agent_norm,),
    ).fetchall()
    return [(r["name"].strip(), r["n"]) for r in rows if r["name"]]


def find_changes(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Return (agent_norm, old, new) ONLY for the corruption signature: the
    current display_name is a MINORITY authority entity (typically a work),
    and a more-frequent entity yields a different, better name. This targets
    the Karo→"Kessef Mishneh" class without re-resolving (and risking
    regressing) names that are merely stylistic variants.
    """
    conn.row_factory = sqlite3.Row
    changes = []
    for row in conn.execute("SELECT agent_norm, display_name FROM network_agents"):
        agent_norm, cur = row["agent_norm"], (row["display_name"] or "").strip()
        ranked = _entity_names_ranked(conn, agent_norm)
        if len(ranked) < 2:
            continue
        top_name, top_n = ranked[0]
        # current name belongs to a strictly-less-frequent entity than the top?
        cur_n = next((n for name, n in ranked if name.lower() == cur.lower()), None)
        if cur_n is not None and cur_n < top_n and top_name.lower() != cur.lower():
            new = resolve_display_name(conn, agent_norm)
            if new and new != cur:
                changes.append((agent_norm, cur, new))
    return changes


def repair(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        changes = find_changes(conn)
    finally:
        conn.close()

    report = {"fix_id": FIX_ID, "candidates": len(changes), "applied": False}
    sample = [{"agent_norm": a, "from": o, "to": n} for a, o, n in changes[:15]]
    report["sample"] = sample

    if not apply:
        print(f"[{FIX_ID}] DRY RUN — {len(changes)} display names would change.")
        for s in sample:
            print(f"  {s['from']!r} -> {s['to']!r}  ({s['agent_norm']})")
        if len(changes) > len(sample):
            print(f"  ... and {len(changes) - len(sample)} more")
        return report

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix21.bak")
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
        conn.executemany(
            "UPDATE network_agents SET display_name = ? WHERE agent_norm = ?",
            [(n, a) for a, _o, n in changes],
        )
        conn.commit()
    finally:
        conn.close()

    report["applied"] = True
    print(f"[{FIX_ID}] applied: {len(changes)} display names repaired. "
          f"Backup: {backup.name}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repair(args.db, apply=args.apply)


if __name__ == "__main__":
    main()
