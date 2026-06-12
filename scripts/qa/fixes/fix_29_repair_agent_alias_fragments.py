"""fix_29: repair comma-split fragments in agent_aliases (issue #53).

The seeding bug (GROUP_CONCAT + split(',')) fragmented every comma-containing
agent_norm: 'blanchard, théophile' existed only as the primary aliases
'blanchard' and 'théophile' — the latter attached to Théophile Gautier's
authority. 1,946 norms with authority URIs had no alias row at all.

Repair (surgical — preserves enrichment-derived variant/cross-script rows):
1. Per authority (joined on authority_uri), expected primaries = its distinct
   agents.agent_norm values.
2. DELETE alias rows with alias_type='primary' whose form is a comma-segment
   of an expected norm but not itself an expected norm (the split artifacts).
3. INSERT missing expected norms as primary aliases (INSERT OR IGNORE under
   the unique alias_form_lower index; cross-authority collisions reported,
   never forced).

The seeding code itself is fixed in scripts/metadata/seed_agent_authorities.py
(same commit), so re-ingest reproduces the repaired state.

Dry-run by default; --apply takes .pre-fix29.bak.
"""
import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scripts.metadata.seed_agent_authorities import detect_script

FIX_ID = "fix_29_repair_agent_alias_fragments"


def _plan(conn: sqlite3.Connection) -> tuple[list, list, list]:
    """Compute (deletions, insertions, collisions) without modifying anything."""
    # authority id -> expected primary norms (from agents via authority_uri)
    expected: dict[int, list[str]] = {}
    for row in conn.execute(
        """SELECT aa.id AS auth_id, ag.agent_norm
           FROM agent_authorities aa
           JOIN agents ag ON ag.authority_uri = aa.authority_uri
           WHERE aa.authority_uri IS NOT NULL AND aa.authority_uri != ''
             AND ag.agent_norm IS NOT NULL AND ag.agent_norm != ''
           ORDER BY ag.id"""
    ):
        norms = expected.setdefault(row["auth_id"], [])
        norm = row["agent_norm"].strip()
        if norm and norm not in norms:
            norms.append(norm)

    deletions = []   # (alias_id, auth_id, alias_form, parent_norm)
    insertions = []  # (auth_id, norm)
    collisions = []  # (auth_id, norm, other_auth_id)

    for auth_id, norms in expected.items():
        norm_set = {n.casefold() for n in norms}
        fragments = {}
        for n in norms:
            if "," in n:
                for seg in n.split(","):
                    seg = seg.strip()
                    if seg and seg.casefold() not in norm_set:
                        fragments[seg.casefold()] = n
        if fragments:
            for arow in conn.execute(
                "SELECT id, alias_form FROM agent_aliases "
                "WHERE authority_id = ? AND alias_type = 'primary'",
                (auth_id,),
            ):
                key = arow["alias_form"].casefold()
                if key in fragments:
                    deletions.append(
                        (arow["id"], auth_id, arow["alias_form"], fragments[key]))

        existing = {
            r["alias_form_lower"]
            for r in conn.execute(
                "SELECT alias_form_lower FROM agent_aliases WHERE authority_id = ?",
                (auth_id,),
            )
        }
        planned_deletes = {d[2].casefold() for d in deletions if d[1] == auth_id}
        for n in norms:
            if n.casefold() in existing and n.casefold() not in planned_deletes:
                continue
            other = conn.execute(
                "SELECT authority_id FROM agent_aliases "
                "WHERE alias_form_lower = ? AND authority_id != ?",
                (n.casefold(), auth_id),
            ).fetchone()
            if other:
                collisions.append((auth_id, n, other["authority_id"]))
            else:
                insertions.append((auth_id, n))

    return deletions, insertions, collisions


def run(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        deletions, insertions, collisions = _plan(conn)
    finally:
        conn.close()

    print(f"[{FIX_ID}] plan: delete {len(deletions)} fragment primaries, "
          f"insert {len(insertions)} missing full-norm primaries, "
          f"{len(collisions)} cross-authority collisions (reported, not forced)")
    for alias_id, auth_id, form, parent in deletions[:8]:
        print(f"  - DEL  [{auth_id}] {form!r}  (fragment of {parent!r})")
    for auth_id, norm in insertions[:8]:
        print(f"  + ADD  [{auth_id}] {norm!r}")
    for auth_id, norm, other in collisions[:8]:
        print(f"  ! SKIP [{auth_id}] {norm!r} — already an alias of authority {other}")

    if not apply:
        print(f"[{FIX_ID}] DRY RUN — use --apply.")
        return {"fix_id": FIX_ID, "applied": False,
                "would_delete": len(deletions), "would_insert": len(insertions),
                "collisions": len(collisions)}

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix29.bak")
    shutil.copy2(db_path, backup)
    print(f"[{FIX_ID}] backup: {backup}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            "DELETE FROM agent_aliases WHERE id = ?",
            [(d[0],) for d in deletions])
        inserted = 0
        for auth_id, norm in insertions:
            cur = conn.execute(
                """INSERT OR IGNORE INTO agent_aliases
                   (authority_id, alias_form, alias_form_lower, alias_type,
                    script, language, is_primary, priority, notes, created_at)
                   VALUES (?, ?, LOWER(?), 'primary', ?, NULL, 1, 10, ?, ?)""",
                (auth_id, norm, norm, detect_script(norm),
                 f"{FIX_ID}: restored full norm (comma-split repair)", now))
            inserted += cur.rowcount
        conn.commit()

        remaining_orphans = conn.execute(
            """SELECT COUNT(DISTINCT ag.agent_norm) FROM agents ag
               JOIN agent_authorities aa ON aa.authority_uri = ag.authority_uri
               WHERE ag.agent_norm LIKE '%,%'
                 AND NOT EXISTS (SELECT 1 FROM agent_aliases x
                                 WHERE x.alias_form_lower = LOWER(ag.agent_norm))"""
        ).fetchone()[0]
        print(f"[{FIX_ID}] applied: deleted {len(deletions)}, inserted {inserted}; "
              f"comma-norms still without alias: {remaining_orphans} "
              f"(expected: only the {len(collisions)} collision cases)")
        return {"fix_id": FIX_ID, "applied": True, "deleted": len(deletions),
                "inserted": inserted, "collisions": len(collisions),
                "remaining_orphans": remaining_orphans}
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true", help="apply (default: dry run)")
    args = parser.parse_args()
    run(args.db, apply=args.apply)
