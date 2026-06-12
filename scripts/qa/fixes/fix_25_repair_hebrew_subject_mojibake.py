"""fix_25: repair mojibake Hebrew subject translations.

The fix_19 translation dictionaries were authored with 37 mangled values
(each one Hebrew letter -> 2×U+FFFD), which composed into ~117 corrupted
``subjects.value_he`` headings ('מהדור��ת מצומצמות'). The dictionaries are
now repaired in-source; this script recomputes value_he for every corrupted
heading from the corrected ``translate_subject`` and rebuilds ``subjects_fts``
so the repaired Hebrew is searchable. If a heading no longer yields a clean
translation, value_he is set to NULL (honest absence beats stored garbage).

Dry-run by default; ``--apply`` takes a ``.pre-fix25.bak`` backup first.

Usage:
    poetry run python scripts/qa/fixes/fix_25_repair_hebrew_subject_mojibake.py \
        [--apply] [--db data/index/bibliographic.db]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.qa.fixes.fix_19_add_hebrew_subjects import translate_subject  # noqa: E402
from scripts.qa.fixes.fix_20_rebuild_fts import rebuild as rebuild_fts  # noqa: E402

FIX_ID = "fix_25_repair_hebrew_subject_mojibake"
FFFD = "�"


def _plan(conn: sqlite3.Connection) -> list[tuple[str, str, str | None]]:
    """(heading, corrupted_he, repaired_he_or_None) for every corrupted heading."""
    rows = conn.execute(
        "SELECT DISTINCT value, value_he FROM subjects WHERE value_he LIKE '%' || char(65533) || '%'"
    ).fetchall()
    plan = []
    for value, old_he in rows:
        new_he = translate_subject(value)
        if new_he and FFFD in new_he:
            new_he = None
        plan.append((value, old_he, new_he))
    return plan


def run(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        plan = _plan(conn)
    finally:
        conn.close()

    repaired = [p for p in plan if p[2]]
    nulled = [p for p in plan if not p[2]]
    print(f"[{FIX_ID}] {len(plan)} corrupted headings: "
          f"{len(repaired)} repairable, {len(nulled)} -> NULL")
    for value, old, new in plan[:12]:
        print(f"  {value[:48]!r}\n    {old[:60]!r}\n    -> {new[:60]!r}" if new
              else f"  {value[:48]!r}\n    {old[:60]!r}\n    -> NULL (no clean translation)")
    if len(plan) > 12:
        print(f"  … and {len(plan) - 12} more")

    if not apply:
        print(f"[{FIX_ID}] DRY RUN — no changes. Use --apply.")
        return {"fix_id": FIX_ID, "applied": False,
                "repairable": len(repaired), "nulled": len(nulled)}

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix25.bak")
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
        for value, _old, new in plan:
            conn.execute("UPDATE subjects SET value_he = ? WHERE value = ?", (new, value))
        conn.commit()
    finally:
        conn.close()

    # Repaired Hebrew must be searchable — rebuild the FTS index.
    rebuild_fts(db_path, apply=True)

    print(f"[{FIX_ID}] applied: {len(repaired)} repaired, {len(nulled)} nulled; "
          f"subjects_fts rebuilt. Backup: {backup.name}")
    return {"fix_id": FIX_ID, "applied": True,
            "repairable": len(repaired), "nulled": len(nulled)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run(args.db, apply=args.apply)


if __name__ == "__main__":
    main()
