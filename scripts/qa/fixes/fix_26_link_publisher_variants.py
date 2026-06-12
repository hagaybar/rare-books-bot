"""fix_26: link orphaned imprint norms to their existing publisher authorities.

Issue #40 follow-up audit: of 2,130 distinct publisher_norms, 1,851 are
unmapped — but ALL are 1-record singletons (the curated authorities already
cover every multi-record press). Automatic surname/token linking was tested
and REJECTED (false positives: first-name tokens like 'henri'/'אברהם' link
unrelated presses). What remains safe:

- 4 punctuation-insensitive exact matches to existing canonical/variant forms
- 2 curated rows: Eliezer Soncino's Hebrew Constantinople imprints as
  variants of the Soncino Press authority (family lineage — the reported case)

Additive INSERTs only; dry-run by default; --apply takes .pre-fix26.bak.
"""
import argparse
import sqlite3
from pathlib import Path

FIX_ID = "fix_26_link_publisher_variants"

# (variant_form, authority_id, note)
LINKS = [
    ("j.f. hartknoch", 37, "punct-exact match to 'j. f. hartknoch'"),
    ("בבית עמנו-אל בן ... יוסף עטיאש", 197, "punct-exact match (ellipsis variant)"),
    ("בדפוס ... ליב זוסמנש", 80, "punct-exact match (ellipsis variant)"),
    ("י. רובינזון", 83, "punct-exact match to 'י' רובינזון'"),
    ("דפוס אליעזר שונצינו", 228, "Eliezer Soncino, Constantinople — Soncino family lineage (issue #40)"),
    ("בדפוס אליעזר שונצינו", 228, "Eliezer Soncino, Constantinople — Soncino family lineage (issue #40)"),
]


def run(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        todo = []
        for form, aid, note in LINKS:
            exists = conn.execute(
                "SELECT 1 FROM publisher_variants WHERE variant_form_lower = LOWER(?)", (form,)
            ).fetchone()
            canon = conn.execute(
                "SELECT canonical_name FROM publisher_authorities WHERE id = ?", (aid,)
            ).fetchone()
            if not canon:
                print(f"[{FIX_ID}] SKIP {form!r}: authority {aid} not found")
                continue
            if exists:
                print(f"[{FIX_ID}] already linked: {form!r}")
                continue
            todo.append((form, aid, canon[0], note))
    finally:
        conn.close()

    for form, aid, canon, note in todo:
        print(f"  + {form!r} -> [{aid}] {canon}  ({note})")
    if not apply:
        print(f"[{FIX_ID}] DRY RUN — would add {len(todo)} variant rows. Use --apply.")
        return {"fix_id": FIX_ID, "applied": False, "would_add": len(todo)}

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix26.bak")
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
        next_id = conn.execute("SELECT COALESCE(MAX(id),0)+1 FROM publisher_variants").fetchone()[0]
        for i, (form, aid, _canon, note) in enumerate(todo):
            conn.execute(
                """INSERT OR IGNORE INTO publisher_variants
                   (id, authority_id, variant_form, variant_form_lower, script,
                    language, is_primary, priority, notes, created_at)
                   VALUES (?, ?, ?, LOWER(?), ?, NULL, 0, 0, ?, date('now'))""",
                (next_id + i, aid, form, form,
                 "hebrew" if any("֐" <= ch <= "׿" for ch in form) else "latin", note),
            )
        conn.commit()
    finally:
        conn.close()
    print(f"[{FIX_ID}] applied: {len(todo)} variant rows. Backup: {backup.name}")
    return {"fix_id": FIX_ID, "applied": True, "added": len(todo)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run(args.db, apply=args.apply)


if __name__ == "__main__":
    main()
