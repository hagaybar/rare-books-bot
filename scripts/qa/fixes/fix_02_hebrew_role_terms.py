"""
Fix 02: Hebrew Role Terms

Agents where role_method='unmapped' and role_raw contains Hebrew characters.
Maps common Hebrew role terms to their English equivalents.

Raw value (role_raw) is preserved as-is.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Hebrew role_raw -> (role_norm, role_method, note)
HEBREW_ROLE_MAP: dict[str, tuple[str, str, str | None]] = {
    "מחבר": ("author", "hebrew_mapped", None),
    "עורך": ("editor", "hebrew_mapped", None),
    "מדפיס": ("printer", "hebrew_mapped", None),
    "מתרגם": ("translator", "hebrew_mapped", None),
    "מוסד מארח": ("other", "hebrew_mapped", "Hebrew: host institution"),
    "בעל האוטוגרף": ("other", "hebrew_mapped", "Hebrew: autographer"),
    "נשוא ההקדשה של הפריט": ("other", "hebrew_mapped", "Hebrew: dedicatee of item"),
    "מחבר תוכן טקסטואלי נוסף": ("other", "hebrew_mapped", "Hebrew: writer of supplementary textual content"),
    "מחבר פירוש נוסף": ("other", "hebrew_mapped", "Hebrew: writer of added commentary"),
    "محرر": ("other", "hebrew_mapped", "Arabic: editor"),  # Arabic, included since it shows up
}

# Regex: contains at least one Hebrew character (U+0590–U+05FF)
HAS_HEBREW = re.compile(r"[\u0590-\u05FF]")
# Also catch Arabic (U+0600-U+06FF) since it appears in the data
HAS_RTL = re.compile(r"[\u0590-\u05FF\u0600-\u06FF]")

DEFAULT_DB = Path("data/index/bibliographic.db")
ARCHIVE_DIR = Path("data/archive/data-quality-2026-04-02")
FIX_LOG = Path("data/qa/fix-log.jsonl")
FIX_ID = "fix_02_hebrew_role_terms"


def find_affected(conn: sqlite3.Connection) -> list[dict]:
    """Return rows where role_method='unmapped' and role_raw has Hebrew/Arabic chars."""
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
        if role_raw and HAS_RTL.search(role_raw) and role_raw in HEBREW_ROLE_MAP:
            role_norm, method, note = HEBREW_ROLE_MAP[role_raw]
            rows.append({
                "agent_id": row[0],
                "record_id": row[1],
                "agent_raw": row[2],
                "role_raw": role_raw,
                "role_norm_old": row[4],
                "role_method_old": row[5],
                "agent_notes_old": row[6],
                "mms_id": row[7],
                "role_norm_new": role_norm,
                "role_method_new": method,
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
        # Merge note with existing agent_notes
        existing = row["agent_notes_old"] or ""
        if note:
            new_notes = f"{existing}; {note}" if existing else note
        else:
            new_notes = existing or None

        conn.execute(
            """
            UPDATE agents
            SET role_norm = ?, role_method = ?, role_confidence = 0.90,
                agent_notes = ?
            WHERE id = ? AND role_method = 'unmapped'
            """,
            (row["role_norm_new"], row["role_method_new"], new_notes, row["agent_id"]),
        )
        count += 1
    conn.commit()
    return count


def append_fix_log(rows: list[dict], count: int) -> None:
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Map Hebrew/Arabic unmapped role terms to English equivalents",
        "records_affected": count,
        "mms_ids": sorted(set(r["mms_id"] for r in rows)),
        "fields_changed": ["role_norm", "role_method", "role_confidence", "agent_notes"],
        "method": "hebrew_mapped",
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

        print(f"[{FIX_ID}] Found {len(rows)} agents with Hebrew/Arabic unmapped roles:")
        for row in rows:
            print(f"  agent_id={row['agent_id']}  mms_id={row['mms_id']}  "
                  f"role_raw={row['role_raw']!r} -> role_norm={row['role_norm_new']!r}")

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
