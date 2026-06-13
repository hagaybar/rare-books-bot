"""fix_31: safe data-curation subset from the seam audit (#58 D2/D4 + #54).

Investigation (2026-06-13) showed the bulk of the "duplicate authorities" are
genuinely DISTINCT people sharing a normalized name (Pliny Elder/Younger,
Buxtorf I/II, Manuzio Elder/Younger) — merging those would corrupt the data, so
they are deliberately left for curator judgment. This fix applies only the
three verified-safe operations:

  D4  Correct d'Alembert's wikidata_id on agent_authorities #21
      (Q106599741 -> Q153232; matches authority_enrichment and the real person).
  S   Delete the empty duplicate agent authority #3147 ("samuel") — it shares
      authority_uri with #742 ("Samuel ibn Naghrillah"), which already holds the
      'samuel' alias, and #3147 has 0 aliases. No alias moves, no enrichment loss
      (enrichment is keyed by the shared URI and stays with #742).
  D2  Delete the 3 unknown_marker placeholder publisher authorities 33/41/78 —
      their Hebrew Proops forms are already variants of the real "Proops Press,
      Amsterdam" (#229); they have 0 variants of their own. Resolves invariant P3.

Every operation's precondition is re-verified in the plan before --apply.
Dry-run by default; --apply takes .pre-fix31.bak via shutil.copy2 (the archive).
"""
import argparse
import shutil
import sqlite3
from pathlib import Path

FIX_ID = "fix_31_curation_safe_subset"

DALEMBERT_AUTH_ID = 21
DALEMBERT_WRONG = "Q106599741"
DALEMBERT_RIGHT = "Q153232"

SAMUEL_DUP_ID = 3147        # empty duplicate agent authority to delete
SAMUEL_CANON_ID = 742       # canonical (Samuel ibn Naghrillah), same URI

PROOPS_PLACEHOLDERS = [33, 41, 78]   # unknown_marker publisher_authorities
PROOPS_CANON_ID = 229                # Proops Press, Amsterdam


def _scalar(conn: sqlite3.Connection, sql: str, params=()):
    """Run a single-value SELECT and return the first column (or None)."""
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _plan(conn: sqlite3.Connection) -> dict:
    """Re-verify every precondition; return the validated action plan."""
    plan = {"d4": None, "samuel": None, "proops": [], "blocked": []}

    # D4 — d'Alembert wikidata correction
    row = conn.execute(
        "SELECT wikidata_id FROM agent_authorities WHERE id=?", (DALEMBERT_AUTH_ID,)
    ).fetchone()
    if row and row[0] == DALEMBERT_WRONG:
        plan["d4"] = (DALEMBERT_AUTH_ID, DALEMBERT_WRONG, DALEMBERT_RIGHT)
    elif row and row[0] == DALEMBERT_RIGHT:
        plan["blocked"].append("D4 already corrected (wikidata_id=Q153232)")
    else:
        plan["blocked"].append(f"D4 precondition off: #{DALEMBERT_AUTH_ID} wikidata={row[0] if row else 'missing'}")

    # S — empty samuel duplicate
    dup_uri = _scalar(conn, "SELECT authority_uri FROM agent_authorities WHERE id=?", (SAMUEL_DUP_ID,))
    canon_uri = _scalar(conn, "SELECT authority_uri FROM agent_authorities WHERE id=?", (SAMUEL_CANON_ID,))
    dup_aliases = _scalar(conn, "SELECT COUNT(*) FROM agent_aliases WHERE authority_id=?", (SAMUEL_DUP_ID,))
    if dup_uri is None:
        plan["blocked"].append(f"S: authority #{SAMUEL_DUP_ID} already gone")
    elif canon_uri is None or dup_uri != canon_uri:
        plan["blocked"].append("S: #3147 and #742 do NOT share a URI — NOT safe, skipping")
    elif dup_aliases != 0:
        plan["blocked"].append(f"S: #3147 has {dup_aliases} aliases (expected 0) — NOT safe, skipping")
    else:
        plan["samuel"] = SAMUEL_DUP_ID

    # D2 — Proops placeholders
    for pid in PROOPS_PLACEHOLDERS:
        pa = conn.execute("SELECT type, canonical_name_lower FROM publisher_authorities WHERE id=?", (pid,)).fetchone()
        if not pa:
            plan["blocked"].append(f"D2: placeholder #{pid} already gone")
            continue
        own_variants = _scalar(conn, "SELECT COUNT(*) FROM publisher_variants WHERE authority_id=?", (pid,))
        covered = _scalar(
            conn,
            "SELECT EXISTS(SELECT 1 FROM publisher_variants WHERE authority_id=? AND variant_form_lower=?)",
            (PROOPS_CANON_ID, pa[1]),
        )
        if pa[0] == "unknown_marker" and own_variants == 0 and covered:
            plan["proops"].append((pid, pa[1]))
        else:
            plan["blocked"].append(
                f"D2: #{pid} not safe (type={pa[0]}, own_variants={own_variants}, covered_by_229={covered})"
            )
    return plan


def run(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        plan = _plan(conn)
    finally:
        conn.close()

    print(f"[{FIX_ID}] PLAN:")
    if plan["d4"]:
        print(f"  ~ D4  correct agent_authorities #{plan['d4'][0]} wikidata {plan['d4'][1]} -> {plan['d4'][2]}")
    if plan["samuel"]:
        print(f"  - S   delete empty duplicate agent authority #{plan['samuel']} "
              f"(samuel; merged into #{SAMUEL_CANON_ID})")
    for pid, form in plan["proops"]:
        print(f"  - D2  delete placeholder publisher authority #{pid} ({form}) "
              f"— covered by Proops Press #{PROOPS_CANON_ID}")
    for b in plan["blocked"]:
        print(f"  ! {b}")

    n = (1 if plan["d4"] else 0) + (1 if plan["samuel"] else 0) + len(plan["proops"])
    if not apply:
        print(f"[{FIX_ID}] DRY RUN — would apply {n} operations. Use --apply.")
        return {"fix_id": FIX_ID, "applied": False, "would_apply": n, "blocked": plan["blocked"]}

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix31.bak")
    shutil.copy2(db_path, backup)
    print(f"[{FIX_ID}] backup (archive): {backup}")

    conn = sqlite3.connect(str(db_path))
    try:
        if plan["d4"]:
            conn.execute("UPDATE agent_authorities SET wikidata_id=? WHERE id=? AND wikidata_id=?",
                         (DALEMBERT_RIGHT, DALEMBERT_AUTH_ID, DALEMBERT_WRONG))
        if plan["samuel"]:
            conn.execute("DELETE FROM agent_authorities WHERE id=?", (plan["samuel"],))
        for pid, _form in plan["proops"]:
            conn.execute("DELETE FROM publisher_authorities WHERE id=?", (pid,))
        conn.commit()

        # Post-apply verification
        placeholders_csv = ",".join(map(str, PROOPS_PLACEHOLDERS))
        v = {
            "d4_ok": _scalar(conn, "SELECT wikidata_id FROM agent_authorities WHERE id=?",
                             (DALEMBERT_AUTH_ID,)) == DALEMBERT_RIGHT,
            "samuel_gone": _scalar(conn, "SELECT COUNT(*) FROM agent_authorities WHERE id=?",
                                   (SAMUEL_DUP_ID,)) == 0,
            "samuel_alias_kept": _scalar(
                conn,
                "SELECT COUNT(*) FROM agent_aliases WHERE authority_id=? AND alias_form_lower='samuel'",
                (SAMUEL_CANON_ID,)) >= 1,
            "proops_gone": _scalar(
                conn,
                f"SELECT COUNT(*) FROM publisher_authorities WHERE id IN ({placeholders_csv})") == 0,
            "p3_violations": _scalar(
                conn,
                "SELECT COUNT(*) FROM publisher_variants pv JOIN publisher_authorities pa "
                "ON pa.canonical_name_lower=pv.variant_form_lower AND pa.id<>pv.authority_id"),
            "orphan_aliases": _scalar(
                conn,
                "SELECT COUNT(*) FROM agent_aliases al LEFT JOIN agent_authorities aa "
                "ON aa.id=al.authority_id WHERE aa.id IS NULL"),
        }
        print(f"[{FIX_ID}] applied {n} ops; verify: {v}")
        return {"fix_id": FIX_ID, "applied": True, "ops": n, "verify": v}
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true", help="apply (default: dry run)")
    args = parser.parse_args()
    run(args.db, apply=args.apply)
