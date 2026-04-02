"""
Fix 01: Role Trailing Periods

Agents where role_method='unmapped' and role_raw ends with '.' often have
a valid MARC relator term obscured by trailing punctuation. This script
maps those trailing-period roles to the correct role_norm and sets
role_method='trailing_period_fix'.

Raw value (role_raw) is preserved as-is.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Trailing-period roles to fix: raw_suffix -> role_norm
TRAILING_PERIOD_MAP: dict[str, str] = {
    "printer.": "printer",
    "editor.": "editor",
    "author.": "author",
    "translator.": "translator",
    "illustrator.": "illustrator",
    "praeses.": "praeses",
    "respondent.": "respondent",
    "engraver.": "engraver",
    "commentator.": "commentator",
    "dedicatee.": "dedicatee",
    "editor,": "editor",  # trailing comma variant
}

DEFAULT_DB = Path("data/index/bibliographic.db")
ARCHIVE_DIR = Path("data/archive/data-quality-2026-04-02")
FIX_LOG = Path("data/qa/fix-log.jsonl")
FIX_ID = "fix_01_role_trailing_periods"


def find_affected(conn: sqlite3.Connection) -> list[dict]:
    """Return rows where role_method='unmapped' and role_raw has trailing period/comma."""
    cur = conn.execute(
        """
        SELECT a.id, a.record_id, a.agent_raw, a.role_raw, a.role_norm,
               a.role_method, a.agent_notes, r.mms_id
        FROM agents a
        JOIN records r ON r.id = a.record_id
        WHERE a.role_method = 'unmapped'
          AND (a.role_raw LIKE '%.' OR a.role_raw LIKE '%,')
        ORDER BY a.id
        """
    )
    rows = []
    for row in cur.fetchall():
        role_raw = row[3]
        if role_raw and role_raw.lower() in TRAILING_PERIOD_MAP:
            rows.append({
                "agent_id": row[0],
                "record_id": row[1],
                "agent_raw": row[2],
                "role_raw": role_raw,
                "role_norm_old": row[4],
                "role_method_old": row[5],
                "agent_notes_old": row[6],
                "mms_id": row[7],
            })
    return rows


def archive(rows: list[dict], archive_dir: Path) -> Path:
    """Write original values to archive JSON."""
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
    """Update role_norm and role_method for affected agents. Returns count."""
    count = 0
    for row in rows:
        new_role_norm = TRAILING_PERIOD_MAP[row["role_raw"].lower()]
        conn.execute(
            """
            UPDATE agents
            SET role_norm = ?, role_method = 'trailing_period_fix',
                role_confidence = 0.95
            WHERE id = ? AND role_method = 'unmapped'
            """,
            (new_role_norm, row["agent_id"]),
        )
        count += 1
    conn.commit()
    return count


def append_fix_log(rows: list[dict], count: int) -> None:
    """Append one JSONL entry to the fix log."""
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Map trailing-period unmapped roles to correct role_norm",
        "records_affected": count,
        "mms_ids": sorted(set(r["mms_id"] for r in rows)),
        "fields_changed": ["role_norm", "role_method", "role_confidence"],
        "method": "trailing_period_fix",
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

        print(f"[{FIX_ID}] Found {len(rows)} agents with trailing-period unmapped roles:")
        for row in rows:
            new_norm = TRAILING_PERIOD_MAP[row["role_raw"].lower()]
            print(f"  agent_id={row['agent_id']}  mms_id={row['mms_id']}  "
                  f"role_raw={row['role_raw']!r} -> role_norm={new_norm!r}")

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN — no changes made.")
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
