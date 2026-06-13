"""fix_30: repair D1 + D3, report D2 + D4 from the seam audit (issue #58).

The 2026-06-12 derived-invariant audit
(`audits/2026-06-12-seam-audit/derived-invariants.md`) executed 31 read-only
SQL invariants against the live DB; four are violated today. fix_30 repairs the
two that are deterministically regenerable and reports the two that need a
curator decision. None has a test, so all would silently recur on rebuild.

D1 (REPAIR) — 26 authority-linked agent_norms (bare mononyms like 'adam',
  'rené', 'יהודה') have NO row in agent_aliases anywhere. Root cause: fix_29's
  collision check (fix_29 lines 84-93) ran against the PRE-deletion alias state,
  so a mononym still held as another authority's comma-split fragment was
  classified a collision and skipped — then that fragment was deleted and never
  re-inserted. The plan is computed DYNAMICALLY: agent_norm values linked to an
  authority via agents.authority_uri -> agent_authorities that have no
  alias_form_lower anywhere. Each is inserted as a PRIMARY alias
  (alias_type='primary', is_primary=1, priority=10, script via detect_script) of
  its OWN authority, evaluated against CURRENT state. Conflicts with the unique
  alias_form_lower index are handled, not forced:
    * already an alias of a DIFFERENT authority  -> report as still-colliding;
    * claimed by two missing authorities at once -> the lowest authority_id wins
      deterministically, the loser is reported as colliding.

D3 (REPAIR) — 2 `same_place_period` network_edges reference the merged-away node
  'מנשה בן ישראל' (merged into 'manasseh ben israel' by _merge_duplicate_agents;
  the orphan sweep in build_network_tables.py:880-886 runs before the additive
  steps that re-introduced them). Network-derived, regenerable: delete the exact
  orphan rows (any edge whose endpoint is absent from network_agents).

D2 (REPORT-ONLY) — 3 Hebrew Proops forms (variants of Proops Press, authority
  229) equal the canonical names of unknown_marker placeholder authorities
  33/41/78. Retiring placeholders / re-pointing records is a curator decision.

D4 (REPORT-ONLY) — d'Alembert wikidata_id disagreement: agent_authorities
  (Q106599741) vs authority_enrichment (Q153232) for the same authority_uri.
  Which QID is correct is a curator decision.

Dry-run by default; --apply takes .pre-fix30.bak via shutil.copy2.
"""
import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scripts.metadata.seed_agent_authorities import detect_script

FIX_ID = "fix_30_repair_seam_audit_violations"


# ---------------------------------------------------------------------------
# D1 — vanished primary aliases
# ---------------------------------------------------------------------------
def _plan_d1(conn: sqlite3.Connection) -> tuple[list, list]:
    """Plan D1 against CURRENT state.

    Returns ``(insertions, collisions)`` where:
      * insertions = list of ``(auth_id, norm, script)`` — one per distinct
        repairable norm, attributed to the deterministic winning authority;
      * collisions = list of ``(auth_id, norm, holder_auth_id)`` — norms that
        cannot be inserted without violating the unique alias_form_lower index
        (already held by another authority, or lost an in-plan dual-claim).
    """
    # (norm, auth_id) candidate pairs: linked to an authority, no alias anywhere.
    # ORDER BY norm, auth_id makes winner selection deterministic.
    candidates = conn.execute(
        """SELECT DISTINCT ag.agent_norm AS norm, aa.id AS auth_id
           FROM agents ag
           JOIN agent_authorities aa ON aa.authority_uri = ag.authority_uri
           WHERE ag.agent_norm IS NOT NULL AND ag.agent_norm != ''
             AND ag.agent_norm NOT IN (
                 SELECT alias_form_lower FROM agent_aliases)
           ORDER BY ag.agent_norm, aa.id"""
    ).fetchall()

    insertions: list = []
    collisions: list = []
    claimed: dict[str, int] = {}  # norm -> auth_id that has claimed it in-plan

    for row in candidates:
        norm = row["norm"].strip()
        auth_id = row["auth_id"]
        if not norm:
            continue
        key = norm.casefold()

        # In-plan dual-claim: a prior (lower auth_id) candidate already took it.
        if key in claimed:
            collisions.append((auth_id, norm, claimed[key]))
            continue

        # Already an alias of a DIFFERENT authority in CURRENT state.
        other = conn.execute(
            "SELECT authority_id FROM agent_aliases "
            "WHERE alias_form_lower = ? AND authority_id != ?",
            (key, auth_id),
        ).fetchone()
        if other:
            collisions.append((auth_id, norm, other["authority_id"]))
            continue

        claimed[key] = auth_id
        insertions.append((auth_id, norm, detect_script(norm)))

    return insertions, collisions


# ---------------------------------------------------------------------------
# D3 — orphan same_place_period network edges
# ---------------------------------------------------------------------------
def _plan_d3(conn: sqlite3.Connection) -> list:
    """Return ``(source, target, connection_type)`` for orphan edges.

    An orphan edge is a network_edge whose source or target norm is absent
    from network_agents (the merged-away-node case). Restricted to
    connection_type='same_place_period' per the audit (D3 = network-derived,
    regenerable; the only orphans are the two merged-node edges)."""
    return [
        (r["source_agent_norm"], r["target_agent_norm"], r["connection_type"])
        for r in conn.execute(
            """SELECT source_agent_norm, target_agent_norm, connection_type
               FROM network_edges
               WHERE connection_type = 'same_place_period'
                 AND (source_agent_norm NOT IN
                          (SELECT agent_norm FROM network_agents)
                      OR target_agent_norm NOT IN
                          (SELECT agent_norm FROM network_agents))
               ORDER BY source_agent_norm, target_agent_norm"""
        )
    ]


# ---------------------------------------------------------------------------
# D2 / D4 — report-only
# ---------------------------------------------------------------------------
def _report_d2(conn: sqlite3.Connection) -> list:
    """Variant forms that shadow a different authority's canonical name."""
    return [
        (r["variant_form"], r["variant_authority"], r["shadowed_authority"],
         r["shadowed_type"])
        for r in conn.execute(
            """SELECT pv.variant_form AS variant_form,
                      pv.authority_id AS variant_authority,
                      pa.id AS shadowed_authority,
                      pa.type AS shadowed_type
               FROM publisher_variants pv
               JOIN publisher_authorities pa
                 ON pa.canonical_name_lower = pv.variant_form_lower
                AND pa.id != pv.authority_id
               ORDER BY pa.id"""
        )
    ]


def _report_d4(conn: sqlite3.Connection) -> list:
    """authority_uris where agent_authorities and enrichment disagree on QID."""
    return [
        (r["authority_uri"], r["canonical_name"], r["auth_qid"], r["enr_qid"])
        for r in conn.execute(
            """SELECT aa.authority_uri AS authority_uri,
                      aa.canonical_name AS canonical_name,
                      aa.wikidata_id AS auth_qid,
                      ae.wikidata_id AS enr_qid
               FROM agent_authorities aa
               JOIN authority_enrichment ae
                 ON ae.authority_uri = aa.authority_uri
               WHERE aa.wikidata_id IS NOT NULL
                 AND ae.wikidata_id IS NOT NULL
                 AND aa.wikidata_id != ae.wikidata_id
               ORDER BY aa.canonical_name"""
        )
    ]


def run(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        d1_insertions, d1_collisions = _plan_d1(conn)
        d3_deletions = _plan_d3(conn)
        d2_shadows = _report_d2(conn)
        d4_disagreements = _report_d4(conn)
    finally:
        conn.close()

    print(f"[{FIX_ID}] D1 (REPAIR): insert {len(d1_insertions)} missing primary "
          f"aliases; {len(d1_collisions)} still colliding (need curation)")
    for auth_id, norm, script in d1_insertions[:10]:
        print(f"  + ADD  [{auth_id}] {norm!r}  (primary, script={script})")
    for auth_id, norm, holder in d1_collisions:
        print(f"  ! SKIP [{auth_id}] {norm!r} — already/also an alias of "
              f"authority {holder} (needs curation)")

    print(f"[{FIX_ID}] D3 (REPAIR): delete {len(d3_deletions)} orphan "
          f"same_place_period edges")
    for src, tgt, ctype in d3_deletions:
        print(f"  - DEL  {src!r} -> {tgt!r}  ({ctype})")

    print(f"[{FIX_ID}] D2 (REPORT-ONLY, needs curation): "
          f"{len(d2_shadows)} variant/canonical shadows")
    for variant_form, var_auth, shadowed, stype in d2_shadows:
        print(f"  ? {variant_form!r} (variant of authority {var_auth}) shadows "
              f"canonical of authority {shadowed} [{stype}]")

    print(f"[{FIX_ID}] D4 (REPORT-ONLY, needs curation): "
          f"{len(d4_disagreements)} wikidata_id disagreements")
    for uri, name, auth_qid, enr_qid in d4_disagreements:
        print(f"  ? {name!r}: agent_authorities={auth_qid} vs "
              f"authority_enrichment={enr_qid} (uri {uri})")

    result = {
        "fix_id": FIX_ID,
        "applied": False,
        "would_insert_d1": len(d1_insertions),
        "d1_insertions": d1_insertions,
        "d1_collisions": len(d1_collisions),
        "d1_collisions_detail": d1_collisions,
        "would_delete_d3": len(d3_deletions),
        "d3_deletions": d3_deletions,
        "d2_shadows": len(d2_shadows),
        "d4_disagreements": len(d4_disagreements),
    }

    if not apply:
        print(f"[{FIX_ID}] DRY RUN — would insert {len(d1_insertions)} aliases "
              f"(D1) and delete {len(d3_deletions)} edges (D3); D2/D4 "
              f"report-only. Use --apply.")
        return result

    backup = db_path.with_suffix(db_path.suffix + ".pre-fix30.bak")
    shutil.copy2(db_path, backup)
    print(f"[{FIX_ID}] backup: {backup}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        for auth_id, norm, script in d1_insertions:
            cur = conn.execute(
                """INSERT OR IGNORE INTO agent_aliases
                   (authority_id, alias_form, alias_form_lower, alias_type,
                    script, language, is_primary, priority, notes, created_at)
                   VALUES (?, ?, LOWER(?), 'primary', ?, NULL, 1, 10, ?, ?)""",
                (auth_id, norm, norm, script,
                 f"{FIX_ID}: restored vanished primary alias (D1, issue #58)",
                 now),
            )
            inserted += cur.rowcount

        deleted = 0
        for src, tgt, ctype in d3_deletions:
            cur = conn.execute(
                "DELETE FROM network_edges WHERE source_agent_norm = ? "
                "AND target_agent_norm = ? AND connection_type = ?",
                (src, tgt, ctype),
            )
            deleted += cur.rowcount
        conn.commit()

        # Post-apply verification (I1 + N1 floors).
        i1_remaining = conn.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT ag.agent_norm FROM agents ag "
            "JOIN agent_authorities aa ON aa.authority_uri = ag.authority_uri "
            "WHERE ag.agent_norm NOT IN "
            "(SELECT alias_form_lower FROM agent_aliases))"
        ).fetchone()[0]
        n1_remaining = conn.execute(
            "SELECT COUNT(*) FROM network_edges e WHERE e.source_agent_norm "
            "NOT IN (SELECT agent_norm FROM network_agents) OR e.target_agent_norm "
            "NOT IN (SELECT agent_norm FROM network_agents)"
        ).fetchone()[0]
        dupes = conn.execute(
            "SELECT COUNT(*) FROM (SELECT alias_form_lower FROM agent_aliases "
            "GROUP BY alias_form_lower HAVING COUNT(*) > 1)"
        ).fetchone()[0]

        print(f"[{FIX_ID}] applied: inserted {inserted} aliases, deleted "
              f"{deleted} edges.")
        print(f"[{FIX_ID}] verify: I1 residual={i1_remaining} "
              f"(expected: the {len(d1_collisions)} collision norms), "
              f"N1 orphan edges={n1_remaining} (expected 0), "
              f"alias_form_lower dupes={dupes} (expected 0)")
        result.update({
            "applied": True,
            "inserted": inserted,
            "deleted": deleted,
            "i1_remaining": i1_remaining,
            "n1_remaining": n1_remaining,
            "alias_dupes": dupes,
        })
        return result
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path,
                        default=Path("data/index/bibliographic.db"))
    parser.add_argument("--apply", action="store_true",
                        help="apply (default: dry run)")
    args = parser.parse_args()
    run(args.db, apply=args.apply)
