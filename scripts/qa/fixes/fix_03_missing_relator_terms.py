"""
Fix 03: Missing MARC Relator Terms

Agents where role_method='unmapped' and role_raw contains valid MARC relator
terms that are not in the current mapping. Maps them to appropriate role_norm
values with explanatory notes where the role maps to 'other'.

Raw value (role_raw) is preserved as-is.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# role_raw -> (role_norm, note)
MISSING_RELATOR_MAP: dict[str, tuple[str, str | None]] = {
    "writer of added commentary": ("commentator", None),
    "host institution": ("other", "MARC relator: host institution"),
    "autographer": ("other", "MARC relator: autographer"),
    "writer of introduction": ("author of introduction", None),
    "issuing body": ("other", "MARC relator: issuing body"),
    "writer of supplementary textual content": ("other", "MARC relator: writer of supplementary textual content"),
    "writer of added text": ("other", "MARC relator: writer of added text"),
    "addressee": ("other", "MARC relator: addressee"),
    "seller": ("other", "MARC relator: seller"),
    "dedicatee of item": ("other", "MARC relator: dedicatee of item"),
    "writer of foreword": ("author of introduction", None),
    "degree supervisor": ("other", "MARC relator: degree supervisor"),
    "degree granting institution": ("other", "MARC relator: degree granting institution"),
    "defendant": ("other", "MARC relator: defendant"),
    "respondent": ("respondent", None),
    "praeses": ("praeses", None),
}

DEFAULT_DB = Path("data/index/bibliographic.db")
ARCHIVE_DIR = Path("data/archive/data-quality-2026-04-02")
FIX_LOG = Path("data/qa/fix-log.jsonl")
FIX_ID = "fix_03_missing_relator_terms"


def find_affected(conn: sqlite3.Connection) -> list[dict]:
    """Return rows where role_method='unmapped' and role_raw is a known missing relator."""
    cur = conn.execute(
        """
        SELECT a.id, a.record_id, a.agent_raw, a.role_raw, a.role_norm,
               a.role_method, a.agent_notes, r.mms_id
        FROM agents a
        JOIN records r ON r.id = a.record_id
        WHERE a.role_method = 'unmapped'
        ORDER BY a.id
        """
    )
    rows = []
    for row in cur.fetchall():
        role_raw = row[3]
        if role_raw and role_raw.lower() in MISSING_RELATOR_MAP:
            role_norm_new, note = MISSING_RELATOR_MAP[role_raw.lower()]
            rows.append({
                "agent_id": row[0],
                "record_id": row[1],
                "agent_raw": row[2],
                "role_raw": role_raw,
                "role_norm_old": row[4],
                "role_method_old": row[5],
                "agent_notes_old": row[6],
                "mms_id": row[7],
                "role_norm_new": role_norm_new,
                "note": note,
            })
    return rows


def archive(rows: list[dict], archive_dir: Path) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{FIX_ID}_archive.json"
    payload = {
        "fix_id": FIX_ID,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(rows),
        "records": rows,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def apply_fixes(conn: sqlite3.Connection, rows: list[dict]) -> int:
    count = 0
    for row in rows:
        note = row["note"]
        existing = row["agent_notes_old"] or ""
        if note:
            new_notes = f"{existing}; {note}" if existing else note
        else:
            new_notes = existing or None

        conn.execute(
            """
            UPDATE agents
            SET role_norm = ?, role_method = 'relator_term_fix',
                role_confidence = 0.90, agent_notes = ?
            WHERE id = ? AND role_method = 'unmapped'
            """,
            (row["role_norm_new"], new_notes, row["agent_id"]),
        )
        count += 1
    conn.commit()
    return count


def append_fix_log(rows: list[dict], count: int) -> None:
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Map missing MARC relator terms to correct role_norm",
        "records_affected": count,
        "mms_ids": sorted(set(r["mms_id"] for r in rows)),
        "fields_changed": ["role_norm", "role_method", "role_confidence", "agent_notes"],
        "method": "relator_term_fix",
    }
    with open(FIX_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true", help="Report only, no DB changes")
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: Database not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(args.db_path))
    try:
        rows = find_affected(conn)
        if not rows:
            print(f"[{FIX_ID}] No affected rows found (already fixed or no matches).")
            return

        print(f"[{FIX_ID}] Found {len(rows)} agents with missing relator terms:")
        by_role = {}
        for row in rows:
            by_role.setdefault(row["role_raw"], []).append(row)
        for role_raw, group in sorted(by_role.items(), key=lambda x: -len(x[1])):
            new_norm = group[0]["role_norm_new"]
            print(f"  {role_raw!r} ({len(group)} agents) -> role_norm={new_norm!r}")

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN — {len(rows)} agents would be updated. No changes made.")
            return

        archive_path = archive(rows, ARCHIVE_DIR)
        print(f"[{FIX_ID}] Archived {len(rows)} original values to {archive_path}")

        count = apply_fixes(conn, rows)
        print(f"[{FIX_ID}] Updated {count} agent rows.")

        append_fix_log(rows, count)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
