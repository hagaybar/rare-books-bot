"""
Fix 13: Bridge Unmatched Agents

Agents whose agent_norm is not found in agent_authorities (canonical_name_lower)
or agent_aliases (alias_form_lower) cannot be linked to authority records. This
script bridges the gap using three strategies:

1. Prefix match: check if a similar name exists in agent_authorities using
   LIKE on the first 10 characters of agent_norm.
2. URI match: for agents with authority_uri, check if that URI already has an
   authority_enrichment entry and create/link an agent_authority from enrichment.
3. Stub creation: for remaining truly unmatched agents, create stub
   agent_authority entries with confidence=0.3.

Batch inserts are used for efficiency.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("data/index/bibliographic.db")
ARCHIVE_DIR = Path("data/archive/data-quality-2026-04-02")
FIX_LOG = Path("data/qa/fix-log.jsonl")
FIX_ID = "fix_13_bridge_unmatched_agents"

BATCH_SIZE = 500


def get_unmatched_agents(conn: sqlite3.Connection) -> list[dict]:
    """Get distinct agent_norm values not in authorities or aliases."""
    cur = conn.execute(
        """
        SELECT DISTINCT a.agent_norm, a.agent_type, a.authority_uri
        FROM agents a
        WHERE a.agent_norm NOT IN (SELECT canonical_name_lower FROM agent_authorities)
          AND a.agent_norm NOT IN (SELECT alias_form_lower FROM agent_aliases)
        ORDER BY a.agent_norm
        """
    )
    results = []
    for row in cur.fetchall():
        results.append({
            "agent_norm": row[0],
            "agent_type": row[1],
            "authority_uri": row[2],
        })
    return results


def deduplicate_by_norm(agents: list[dict]) -> list[dict]:
    """Deduplicate: keep the first entry per agent_norm, preferring one with authority_uri."""
    seen: dict[str, dict] = {}
    for a in agents:
        norm = a["agent_norm"]
        if norm not in seen:
            seen[norm] = a
        elif a["authority_uri"] and not seen[norm]["authority_uri"]:
            seen[norm] = a
    return list(seen.values())


def strategy_prefix_match(
    conn: sqlite3.Connection, agents: list[dict]
) -> tuple[list[dict], list[dict]]:
    """
    Strategy 1: Match agent_norm prefix (first 10 chars) against
    agent_authorities canonical_name_lower.
    Returns (matched, remaining).
    """
    matched = []
    remaining = []

    for agent in agents:
        norm = agent["agent_norm"]
        prefix = norm[:10] if len(norm) >= 10 else norm
        if len(prefix) < 4:
            remaining.append(agent)
            continue

        cur = conn.execute(
            """
            SELECT id, canonical_name_lower
            FROM agent_authorities
            WHERE canonical_name_lower LIKE ? || '%'
            LIMIT 5
            """,
            (prefix,),
        )
        candidates = cur.fetchall()

        # Require exactly one match to avoid ambiguity
        if len(candidates) == 1:
            auth_id = candidates[0][0]
            auth_name = candidates[0][1]
            matched.append({
                **agent,
                "authority_id": auth_id,
                "matched_name": auth_name,
                "strategy": "prefix_match",
            })
        else:
            remaining.append(agent)

    return matched, remaining


def strategy_uri_enrichment(
    conn: sqlite3.Connection, agents: list[dict]
) -> tuple[list[dict], list[dict]]:
    """
    Strategy 2: For agents with authority_uri, look up enrichment data
    and create authority entries from it.
    Returns (matched, remaining).
    """
    matched = []
    remaining = []

    for agent in agents:
        if not agent["authority_uri"]:
            remaining.append(agent)
            continue

        cur = conn.execute(
            """
            SELECT ae.label, ae.wikidata_id, ae.viaf_id, ae.nli_id,
                   ae.person_info, ae.description
            FROM authority_enrichment ae
            WHERE ae.authority_uri = ?
            """,
            (agent["authority_uri"],),
        )
        enr = cur.fetchone()

        if enr and (enr[0] or enr[4]):
            # We have enrichment data -- extract dates if available
            person_info = None
            date_start = None
            date_end = None
            dates_active = None
            if enr[4]:
                try:
                    person_info = json.loads(enr[4])
                    birth = person_info.get("birth_year")
                    death = person_info.get("death_year")
                    if birth:
                        date_start = int(birth)
                    if death:
                        date_end = int(death)
                    if birth and death:
                        dates_active = f"{birth}-{death}"
                    elif birth:
                        dates_active = f"{birth}-"
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

            matched.append({
                **agent,
                "label": enr[0],
                "wikidata_id": enr[1],
                "viaf_id": enr[2],
                "nli_id": enr[3],
                "description": enr[5],
                "date_start": date_start,
                "date_end": date_end,
                "dates_active": dates_active,
                "strategy": "uri_enrichment",
            })
        else:
            remaining.append(agent)

    return matched, remaining


def archive_state(
    unmatched_count: int,
    prefix_matched: list[dict],
    uri_matched: list[dict],
    stubs: list[dict],
    archive_dir: Path,
) -> Path:
    """Archive the plan before modifications."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{FIX_ID}_archive.json"
    payload = {
        "fix_id": FIX_ID,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "total_unmatched": unmatched_count,
        "prefix_matched_count": len(prefix_matched),
        "uri_matched_count": len(uri_matched),
        "stub_count": len(stubs),
        "prefix_matched_sample": prefix_matched[:20],
        "uri_matched_sample": uri_matched[:20],
        "stub_sample": stubs[:20],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def apply_prefix_matches(conn: sqlite3.Connection, matched: list[dict]) -> int:
    """Create agent_aliases linking agent_norm to the matched authority."""
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    batch = []
    for m in matched:
        batch.append((
            m["authority_id"],
            m["agent_norm"],
            m["agent_norm"],
            "variant",
            "latin",
            0,
            0,
            f"fix_13 prefix_match: matched to {m['matched_name']}",
            now,
        ))
        count += 1
        if len(batch) >= BATCH_SIZE:
            conn.executemany(
                """
                INSERT OR IGNORE INTO agent_aliases
                    (authority_id, alias_form, alias_form_lower, alias_type,
                     script, is_primary, priority, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            batch = []
    if batch:
        conn.executemany(
            """
            INSERT OR IGNORE INTO agent_aliases
                (authority_id, alias_form, alias_form_lower, alias_type,
                 script, is_primary, priority, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            batch,
        )
    return count


def apply_uri_matches(conn: sqlite3.Connection, matched: list[dict]) -> int:
    """Create agent_authorities from enrichment data, plus alias."""
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for m in matched:
        # Determine canonical name: use label from enrichment, or agent_norm
        canonical = m.get("label") or m["agent_norm"]
        canonical_lower = canonical.lower()

        # Check if authority already exists for this canonical name
        cur = conn.execute(
            "SELECT id FROM agent_authorities WHERE canonical_name_lower = ?",
            (canonical_lower,),
        )
        existing = cur.fetchone()

        if existing:
            authority_id = existing[0]
        else:
            conn.execute(
                """
                INSERT INTO agent_authorities
                    (canonical_name, canonical_name_lower, agent_type,
                     dates_active, date_start, date_end, notes, sources,
                     confidence, authority_uri, wikidata_id, viaf_id, nli_id,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.6, ?, ?, ?, ?, ?, ?)
                """,
                (
                    canonical,
                    canonical_lower,
                    m["agent_type"],
                    m.get("dates_active"),
                    m.get("date_start"),
                    m.get("date_end"),
                    f"fix_13 uri_enrichment: {m.get('description', '')}",
                    "authority_enrichment",
                    m["authority_uri"],
                    m.get("wikidata_id"),
                    m.get("viaf_id"),
                    m.get("nli_id"),
                    now, now,
                ),
            )
            authority_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create alias from agent_norm -> authority
        if m["agent_norm"] != canonical_lower:
            conn.execute(
                """
                INSERT OR IGNORE INTO agent_aliases
                    (authority_id, alias_form, alias_form_lower, alias_type,
                     script, is_primary, priority, notes, created_at)
                VALUES (?, ?, ?, 'variant', 'latin', 0, 0,
                        'fix_13 uri_enrichment link', ?)
                """,
                (authority_id, m["agent_norm"], m["agent_norm"], now),
            )
        count += 1

    return count


def apply_stubs(conn: sqlite3.Connection, agents: list[dict]) -> int:
    """Create stub agent_authority entries for remaining unmatched agents."""
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    batch = []

    for a in agents:
        norm = a["agent_norm"]
        # Double-check not already created (e.g., by earlier strategy for same session)
        batch.append((
            norm.title() if norm.isascii() else norm,
            norm,
            a["agent_type"],
            "auto-created stub, needs verification",
            "fix_13_stub",
            0.3,
            a.get("authority_uri"),
            now, now,
        ))
        count += 1

        if len(batch) >= BATCH_SIZE:
            conn.executemany(
                """
                INSERT OR IGNORE INTO agent_authorities
                    (canonical_name, canonical_name_lower, agent_type,
                     notes, sources, confidence, authority_uri,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            batch = []

    if batch:
        conn.executemany(
            """
            INSERT OR IGNORE INTO agent_authorities
                (canonical_name, canonical_name_lower, agent_type,
                 notes, sources, confidence, authority_uri,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            batch,
        )
    return count


def append_fix_log(counts: dict) -> None:
    """Append one JSONL entry to the fix log."""
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Bridge unmatched agents to authorities via prefix match, URI enrichment, and stubs",
        **counts,
        "tables_changed": ["agent_authorities", "agent_aliases"],
        "method": "multi_strategy_bridge",
    }
    with open(FIX_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report only, no DB changes")
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: Database not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(args.db_path))
    try:
        all_unmatched = get_unmatched_agents(conn)
        unique = deduplicate_by_norm(all_unmatched)

        print(f"[{FIX_ID}] Unmatched agents: {len(all_unmatched)} rows, "
              f"{len(unique)} unique agent_norm values")

        # Strategy 1: prefix match
        prefix_matched, after_prefix = strategy_prefix_match(conn, unique)
        print(f"\n  Strategy 1 (prefix match): {len(prefix_matched)} matched")
        for m in prefix_matched[:5]:
            print(f"    {m['agent_norm']!r} -> {m['matched_name']!r}")
        if len(prefix_matched) > 5:
            print(f"    ... and {len(prefix_matched) - 5} more")

        # Strategy 2: URI enrichment
        uri_matched, after_uri = strategy_uri_enrichment(conn, after_prefix)
        print(f"\n  Strategy 2 (URI enrichment): {len(uri_matched)} matched")
        for m in uri_matched[:5]:
            label = m.get("label", "?")
            print(f"    {m['agent_norm']!r} -> {label!r} ({m.get('wikidata_id', 'no wikidata')})")
        if len(uri_matched) > 5:
            print(f"    ... and {len(uri_matched) - 5} more")

        # Strategy 3: stubs for remaining
        stubs = after_uri
        print(f"\n  Strategy 3 (stubs): {len(stubs)} remaining")

        print(f"\n[{FIX_ID}] Summary:")
        print(f"  Prefix matches:  {len(prefix_matched):>5d}")
        print(f"  URI matches:     {len(uri_matched):>5d}")
        print(f"  Stubs to create: {len(stubs):>5d}")
        print(f"  Total:           {len(unique):>5d}")

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN -- no changes made.")
            return

        archive_path = archive_state(
            len(unique), prefix_matched, uri_matched, stubs, ARCHIVE_DIR
        )
        print(f"\n[{FIX_ID}] Archived state to {archive_path}")

        # Apply in order
        n_prefix = apply_prefix_matches(conn, prefix_matched)
        print(f"[{FIX_ID}] Created {n_prefix} alias rows (prefix match)")

        n_uri = apply_uri_matches(conn, uri_matched)
        print(f"[{FIX_ID}] Created/linked {n_uri} authority entries (URI enrichment)")

        n_stubs = apply_stubs(conn, stubs)
        print(f"[{FIX_ID}] Created {n_stubs} stub authority entries")

        conn.commit()

        counts = {
            "total_unmatched": len(unique),
            "prefix_matched": n_prefix,
            "uri_matched": n_uri,
            "stubs_created": n_stubs,
        }
        append_fix_log(counts)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
