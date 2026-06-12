"""fix_27: link Hebrew imprint norms of famous presses to their authorities.

Issue #46 (gold-suite diagnostic 2026-06-12): the 1550s Alvise Bragadin
Hebrew imprints are unreachable by canonical publisher queries — their
publisher_norm is the identity Hebrew string, never linked as a variant of
'Bragadin Press, Venice'. Diagnostic TEST-STRESS-01 ("Hebrew books printed
in Venice by Bragadin 1550-1600") returned 0; ground truth is 3 records
(1553, 1554, 1574, all heb).

A systematic sweep found the same gap across six press authorities. This fix
adds the CONFIDENT links only — forms naming the exact person/press of the
authority (plus Bragadin dynasty forms under the press authority, following
the fix_26 Soncino family-lineage precedent). Ambiguous forms (Zanetto
Zanetti, Daniel Adelkind, Abraham Athias, generic 'דפוס עטיאש') are listed
in QUESTIONABLE and NOT applied — they need either a curator decision or a
new authority row.

Additive INSERTs only; dry-run by default; --apply takes .pre-fix27.bak.
"""
import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

FIX_ID = "fix_27_link_hebrew_press_variants"

# (variant_form, authority_id, note)
# variant_form must equal the orphan imprints.publisher_norm exactly so the
# resolver's variant_exact path collects it into matched publisher forms.
LINKS = [
    # --- Bragadin Press, Venice (authority 3, dates_active 1550-1710) ---
    ("נדפס במצות האדון מסיר אלוויז בראגאדין", 3,
     "Alvise Bragadin, founder — 1553 imprint (issue #46)"),
    ("נדפס בבית ... מיסיר אלויסי בראגאדין ....", 3,
     "Alvise Bragadin — 1554 imprint"),
    ("דפוס בראגאדין", 3, "Bragadin press — 1574 imprint"),
    ("במצות פייטרו ולורינצו בראגאדין בבית ייואני קאיון", 3,
     "Pietro & Lorenzo Bragadin (dynasty), printed at Caleoni's house — 1617"),
    ("במצות ... פייטרו ולורינצו בראגאדין, בבית ייואני קאיון", 3,
     "Pietro & Lorenzo Bragadin (dynasty), printed at Caleoni's house — 1618"),
    ("בדפוס בראגאדין", 3,
     "Bragadin press — 1715 imprint (slightly past authority dates_active 1710; "
     "the press historically ran to ~1750)"),
    ("בראגאדין", 3, "Bragadin press — 1743 imprint (see 1715 note)"),
    # --- Daniel Bomberg, Venice (authority 17, 1516-1549) ---
    ("דניאל בומבירגי", 17, "Daniel Bomberg — 1518 imprint"),
    ("דניאל בומברגי", 17, "Daniel Bomberg (spelling variant) — 1518 imprint"),
    # --- Marco Antonio Giustiniani, Venice (authority 21, 1545-1552) ---
    ("דפוס מארקו אנטוניו יושטיניאן", 21, "Marco Antonio Giustiniani — 1546 imprint"),
    ("בבית בן משק בית האדון מארקו אנטוניאו יושטיניאן", 21,
     "Marco Antonio Giustiniani — 1548 imprint"),
    # --- Daniel Zanetti, Venice (authority 16, 1596-1608) ---
    ("בבית דניאל זאניטי", 16, "Daniel Zanetti — 1599 imprint"),
    # --- Joseph Athias, Amsterdam (authority 200) ---
    ("בדפוס ... של ... יוסף עטיאש", 200, "Joseph Athias — 1677 imprint"),
    # --- Immanuel ben Joseph Athias, Amsterdam (authority 197) ---
    ("בבית ובמצות ... עמנואל עטיאש", 197, "Immanuel Athias — 1687 imprint"),
    ("בדפוס עמנואל בן יוסף עטיאש", 197, "Immanuel ben Joseph Athias — 1697 imprint"),
    ("בדפוס ... עמנואל בן ... יוסף עטיאש", 197, "Immanuel ben Joseph Athias — 1703 imprint"),
]

# Found by the same sweep but held back — curator decision or new authority
# needed. Listed here so the audit trail shows they were seen, not missed.
QUESTIONABLE = [
    ("דפוס עטיאש", "1698 — generic family form; Joseph (200) or Immanuel (197)?"),
    ("בבית זאניטו זאניטי", "1607 — Zanetto Zanetti, a distinct printer from "
     "Daniel Zanetti (16); no own authority row"),
    ("דניאל אדיל קינד", "1552 — Daniel Adelkind, son of Cornelio (19); "
     "lineage link or new authority?"),
    ("דפוס אברהם בן רפאל חזקיהו עטיאש", "1728 — Abraham Athias, later printer; no authority"),
    ("דפוס אברהם עטיאש", "1737 — Abraham Athias; no authority"),
    ("בבית ובדפוס ... אברהם בן רפאל חזקיהו עטיאש", "1738 — Abraham Athias; no authority"),
    ("בבית ובדפוס אברהם בן רפאל חזקיהו עטיאש", "1739 — Abraham Athias; no authority"),
]


def run(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        todo = []
        for form, aid, note in LINKS:
            exists = conn.execute(
                "SELECT 1 FROM publisher_variants WHERE variant_form_lower = LOWER(?)",
                (form,),
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
            recs = conn.execute(
                "SELECT COUNT(*) FROM imprints WHERE LOWER(publisher_norm) = LOWER(?)",
                (form,),
            ).fetchone()[0]
            todo.append((form, aid, canon[0], note, recs))
    finally:
        conn.close()

    for form, aid, canon, note, recs in todo:
        print(f"  + {form!r} -> [{aid}] {canon}  ({recs} rec)  ({note})")
    print(f"[{FIX_ID}] held back (QUESTIONABLE, not applied): {len(QUESTIONABLE)}")
    for form, why in QUESTIONABLE:
        print(f"  ? {form!r}  ({why})")

    if not apply:
        print(f"[{FIX_ID}] DRY RUN — would add {len(todo)} variant rows. Use --apply.")
        return {"fix_id": FIX_ID, "applied": False, "would_add": len(todo)}

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix27.bak")
    shutil.copy2(db_path, backup)
    print(f"[{FIX_ID}] backup: {backup}")

    conn = sqlite3.connect(str(db_path))
    try:
        now = datetime.now(timezone.utc).isoformat()
        for form, aid, canon, note, recs in todo:
            conn.execute(
                """INSERT INTO publisher_variants
                   (authority_id, variant_form, variant_form_lower, script,
                    is_primary, priority, notes, created_at)
                   VALUES (?, ?, LOWER(?), 'hebrew', 0, 0, ?, ?)""",
                (aid, form, form, f"{FIX_ID}: {note}", now),
            )
        conn.commit()

        # Verification: each linked norm must now resolve through its authority
        ok = True
        for form, aid, canon, note, recs in todo:
            hit = conn.execute(
                """SELECT 1 FROM imprints i
                   WHERE LOWER(i.publisher_norm) IN (
                       SELECT variant_form_lower FROM publisher_variants
                       WHERE authority_id = ?)
                   AND LOWER(i.publisher_norm) = LOWER(?)""",
                (aid, form),
            ).fetchone()
            if not hit:
                print(f"[{FIX_ID}] VERIFY FAIL: {form!r} not reachable via authority {aid}")
                ok = False
        print(f"[{FIX_ID}] applied {len(todo)} rows; verification {'OK' if ok else 'FAILED'}")
        return {"fix_id": FIX_ID, "applied": True, "added": len(todo), "verified": ok}
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true", help="apply (default: dry run)")
    args = parser.parse_args()
    run(args.db, apply=args.apply)
