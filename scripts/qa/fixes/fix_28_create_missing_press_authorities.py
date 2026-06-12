"""fix_28: create authorities for printers found by the fix_27 sweep.

Issue #46 follow-up: the fix_27 sweep surfaced 7 Hebrew imprint norms whose
printers have NO authority row (or an ambiguous assignment). Per curator
decision (2026-06-12): create new authorities rather than lineage-link them
to relatives' rows.

Three new authorities, with dates derived ONLY from collection evidence
(fl. years from the records themselves — no invented biography, conservative
confidence 0.7, sources left empty for later research):

- Zanetto Zanetti, Venice (fl. 1607) — Zanetti family, distinct from Daniel
- Daniel Adelkind, Venice (fl. 1552) — son of Cornelio Adelkind (19)
- Abraham Athias, Amsterdam (fl. 1728-1739) — patronymic in notes

Plus one assignment that needs no new authority: the generic 'דפוס עטיאש'
(Amsterdam, 1698) is linked to Immanuel Athias (197) — the shop was run
jointly by Joseph & Immanuel at that date; Immanuel led day-to-day printing.

Additive INSERTs only; dry-run by default; --apply takes .pre-fix28.bak.
"""
import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

FIX_ID = "fix_28_create_missing_press_authorities"

# canonical_name, type, dates_active, date_start, date_end, location, notes
AUTHORITIES = [
    ("Zanetto Zanetti, Venice", "printing_house", "fl. 1607", 1607, 1607,
     "Venice, Italy",
     "Member of the Zanetti printing family; distinct from Daniel Zanetti "
     "(authority 16). Dates from collection evidence only (1 imprint, 1607). "
     f"Created by {FIX_ID} (issue #46); needs biographical research."),
    ("Daniel Adelkind, Venice", "printing_house", "fl. 1552", 1552, 1552,
     "Venice, Italy",
     "Son of Cornelio Adelkind (authority 19); printed under his own name. "
     "Dates from collection evidence only (1 imprint, 1552). "
     f"Created by {FIX_ID} (issue #46); needs biographical research."),
    ("Abraham Athias, Amsterdam", "printing_house", "fl. 1728-1739", 1728, 1739,
     "Amsterdam, Netherlands",
     "Full form in imprints: אברהם בן רפאל חזקיהו עטיאש (Abraham ben Raphael "
     "Hezekiah Athias); later Athias-family printer, distinct from Joseph (200) "
     "and Immanuel (197). Dates from collection evidence only (4 imprints). "
     f"Created by {FIX_ID} (issue #46); needs biographical research."),
]

# variant_form -> (authority canonical_name or existing id, is_primary, note)
VARIANT_LINKS = [
    ("בבית זאניטו זאניטי", "Zanetto Zanetti, Venice", 1,
     "Primary normalized form (matches imprints.publisher_norm) — 1607"),
    ("דניאל אדיל קינד", "Daniel Adelkind, Venice", 1,
     "Primary normalized form (matches imprints.publisher_norm) — 1552"),
    ("דפוס אברהם בן רפאל חזקיהו עטיאש", "Abraham Athias, Amsterdam", 1,
     "Primary normalized form (matches imprints.publisher_norm) — 1728"),
    ("דפוס אברהם עטיאש", "Abraham Athias, Amsterdam", 0, "1737 imprint"),
    ("בבית ובדפוס ... אברהם בן רפאל חזקיהו עטיאש", "Abraham Athias, Amsterdam", 0,
     "1738 imprint (ellipsis variant)"),
    ("בבית ובדפוס אברהם בן רפאל חזקיהו עטיאש", "Abraham Athias, Amsterdam", 0,
     "1739 imprint"),
    # Existing authority — generic family form assigned per curator decision
    ("דפוס עטיאש", 197, 0,
     "Generic Athias form, Amsterdam 1698 — shop run jointly by Joseph & "
     "Immanuel; assigned to Immanuel-era authority (curator decision 2026-06-12)"),
]


def run(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        new_authorities = []
        for name, typ, da, ds, de, loc, notes in AUTHORITIES:
            row = conn.execute(
                "SELECT id FROM publisher_authorities WHERE canonical_name_lower = LOWER(?)",
                (name,),
            ).fetchone()
            if row:
                print(f"[{FIX_ID}] authority exists: {name!r} (id {row['id']})")
            else:
                new_authorities.append((name, typ, da, ds, de, loc, notes))
                print(f"  + AUTHORITY {name!r} ({typ}, {da}, {loc})")

        pending_links = []
        for form, target, is_primary, note in VARIANT_LINKS:
            exists = conn.execute(
                "SELECT 1 FROM publisher_variants WHERE variant_form_lower = LOWER(?)",
                (form,),
            ).fetchone()
            if exists:
                print(f"[{FIX_ID}] already linked: {form!r}")
                continue
            recs = conn.execute(
                "SELECT COUNT(*) FROM imprints WHERE LOWER(publisher_norm) = LOWER(?)",
                (form,),
            ).fetchone()[0]
            pending_links.append((form, target, is_primary, note, recs))
            print(f"  + VARIANT {form!r} -> {target!r}  ({recs} rec)  ({note})")
    finally:
        conn.close()

    if not apply:
        print(f"[{FIX_ID}] DRY RUN — would add {len(new_authorities)} authorities "
              f"and {len(pending_links)} variant rows. Use --apply.")
        return {"fix_id": FIX_ID, "applied": False,
                "would_add_authorities": len(new_authorities),
                "would_add_variants": len(pending_links)}

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix28.bak")
    shutil.copy2(db_path, backup)
    print(f"[{FIX_ID}] backup: {backup}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        now = datetime.now(timezone.utc).isoformat()
        name_to_id = {}
        for name, typ, da, ds, de, loc, notes in new_authorities:
            cur = conn.execute(
                """INSERT INTO publisher_authorities
                   (canonical_name, canonical_name_lower, type, dates_active,
                    date_start, date_end, location, notes, sources, confidence,
                    is_missing_marker, primary_language, created_at, updated_at)
                   VALUES (?, LOWER(?), ?, ?, ?, ?, ?, ?, ?, 0.7, 0, 'heb', ?, ?)""",
                (name, name, typ, da, ds, de, loc, notes, json.dumps([]), now, now),
            )
            name_to_id[name] = cur.lastrowid

        added_variants = 0
        for form, target, is_primary, note, recs in pending_links:
            aid = target if isinstance(target, int) else name_to_id.get(target)
            if aid is None:
                row = conn.execute(
                    "SELECT id FROM publisher_authorities WHERE canonical_name_lower = LOWER(?)",
                    (target,),
                ).fetchone()
                aid = row["id"] if row else None
            if aid is None:
                print(f"[{FIX_ID}] SKIP variant {form!r}: authority {target!r} unresolved")
                continue
            conn.execute(
                """INSERT INTO publisher_variants
                   (authority_id, variant_form, variant_form_lower, script,
                    is_primary, priority, notes, created_at)
                   VALUES (?, ?, LOWER(?), 'hebrew', ?, ?, ?, ?)""",
                (aid, form, form, is_primary, 10 if is_primary else 0,
                 f"{FIX_ID}: {note}", now),
            )
            added_variants += 1
        conn.commit()

        # Verification: every linked norm reachable via its authority
        ok = True
        for form, target, is_primary, note, recs in pending_links:
            hit = conn.execute(
                """SELECT 1 FROM imprints i
                   JOIN publisher_variants pv
                     ON pv.variant_form_lower = LOWER(i.publisher_norm)
                   WHERE LOWER(i.publisher_norm) = LOWER(?)""",
                (form,),
            ).fetchone()
            if not hit:
                print(f"[{FIX_ID}] VERIFY FAIL: {form!r} not linked")
                ok = False
        print(f"[{FIX_ID}] applied {len(name_to_id)} authorities + "
              f"{added_variants} variants; verification {'OK' if ok else 'FAILED'}")
        return {"fix_id": FIX_ID, "applied": True,
                "added_authorities": len(name_to_id),
                "added_variants": added_variants, "verified": ok}
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true", help="apply (default: dry run)")
    args = parser.parse_args()
    run(args.db, apply=args.apply)
