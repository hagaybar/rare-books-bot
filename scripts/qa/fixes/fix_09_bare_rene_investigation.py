"""
Fix 09: Bare First-Name Agent Investigation

Investigate agents where agent_norm has no comma AND length < 6 characters
(the "bare first name" check). For each:
1. Look at the record's other agents to see if this is a truncated name
2. Look at the authority_uri if present
3. If the bare name can be linked to a full name via authority_uri, add an alias.
   If it's genuinely just a first name, mark with agent_notes='bare_first_name_only'.

Does NOT change agent_norm -- that preserves per-record cataloging.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("data/index/bibliographic.db")
ARCHIVE_DIR = Path("data/archive/data-quality-2026-04-02")
FIX_LOG = Path("data/qa/fix-log.jsonl")
FIX_ID = "fix_09_bare_rene_investigation"

# Known classical/historical single-name agents that are legitimate
# These are genuinely known by one name (like "Aristotle", "Homer")
KNOWN_SINGLE_NAMES = {
    "ovid", "philo", "pliny", "homer", "plato", "livy", "dares",
}


def find_bare_names(conn: sqlite3.Connection) -> list[dict]:
    """Find agents with bare first names (no comma, length < 6)."""
    cur = conn.execute(
        """
        SELECT a.id, a.record_id, a.agent_norm, a.agent_raw,
               a.authority_uri, a.agent_notes, a.agent_type,
               r.mms_id
        FROM agents a
        JOIN records r ON r.id = a.record_id
        WHERE a.agent_norm NOT LIKE '%,%'
          AND LENGTH(a.agent_norm) < 6
        ORDER BY a.agent_norm, a.id
        """
    )
    rows = []
    for row in cur.fetchall():
        rows.append({
            "agent_id": row[0],
            "record_id": row[1],
            "agent_norm": row[2],
            "agent_raw": row[3],
            "authority_uri": row[4],
            "agent_notes_old": row[5],
            "agent_type": row[6],
            "mms_id": row[7],
        })
    return rows


def get_record_agents(conn: sqlite3.Connection, record_id: int) -> list[dict]:
    """Get all agents for a record."""
    cur = conn.execute(
        """
        SELECT agent_norm, agent_raw, authority_uri, role_norm
        FROM agents
        WHERE record_id = ?
        ORDER BY agent_index
        """,
        (record_id,),
    )
    return [
        {
            "agent_norm": r[0],
            "agent_raw": r[1],
            "authority_uri": r[2],
            "role_norm": r[3],
        }
        for r in cur.fetchall()
    ]


def get_record_title(conn: sqlite3.Connection, record_id: int) -> str | None:
    """Get the main title for a record."""
    cur = conn.execute(
        "SELECT value FROM titles WHERE record_id = ? AND title_type = 'main' LIMIT 1",
        (record_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def find_full_name_via_uri(
    conn: sqlite3.Connection, authority_uri: str, bare_norm: str
) -> str | None:
    """Check if another agent with the same authority_uri has a fuller name."""
    if not authority_uri:
        return None
    cur = conn.execute(
        """
        SELECT DISTINCT agent_norm
        FROM agents
        WHERE authority_uri = ?
          AND agent_norm <> ?
          AND agent_norm LIKE '%,%'
        LIMIT 5
        """,
        (authority_uri, bare_norm),
    )
    fuller_names = [r[0] for r in cur.fetchall()]
    if fuller_names:
        return max(fuller_names, key=len)
    return None


def check_authority_alias(conn: sqlite3.Connection, bare_norm: str) -> int | None:
    """Check if the bare name already has an alias entry, return authority_id."""
    cur = conn.execute(
        "SELECT authority_id FROM agent_aliases WHERE alias_form_lower = ?",
        (bare_norm.lower(),),
    )
    row = cur.fetchone()
    return row[0] if row else None


def investigate(conn: sqlite3.Connection, rows: list[dict]) -> list[dict]:
    """Investigate each bare name and determine the appropriate action."""
    findings = []

    for row in rows:
        bare_norm = row["agent_norm"]
        finding = {
            **row,
            "action": None,
            "full_name": None,
            "title": get_record_title(conn, row["record_id"]),
            "record_agents": get_record_agents(conn, row["record_id"]),
            "existing_alias_authority_id": check_authority_alias(conn, bare_norm),
        }

        # Classical single-name authors: legitimate bare names
        if bare_norm.lower() in KNOWN_SINGLE_NAMES:
            finding["action"] = "mark_classical_single_name"
            findings.append(finding)
            continue

        # Try to find a fuller name via authority_uri
        full_name = find_full_name_via_uri(
            conn, row["authority_uri"], bare_norm
        )
        if full_name:
            finding["full_name"] = full_name
            if finding["existing_alias_authority_id"]:
                finding["action"] = "already_aliased"
            else:
                finding["action"] = "link_to_full_name"
            findings.append(finding)
            continue

        # No authority link or no fuller name found
        finding["action"] = "mark_bare_first_name"
        findings.append(finding)

    return findings


def archive_data(findings: list[dict], archive_dir: Path) -> Path:
    """Write original values to archive JSON."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{FIX_ID}_archive.json"

    # Strip record_agents from archive (too verbose) -- just keep action summary
    slim_findings = []
    for f in findings:
        slim = {k: v for k, v in f.items() if k != "record_agents"}
        slim["other_agent_count"] = len(f["record_agents"])
        slim_findings.append(slim)

    payload = {
        "fix_id": FIX_ID,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(findings),
        "findings": slim_findings,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def apply_fixes(conn: sqlite3.Connection, findings: list[dict]) -> dict:
    """Apply notes and alias fixes. Returns counts by action type."""
    now = datetime.now(timezone.utc).isoformat()
    counts = {
        "marked_classical": 0,
        "marked_bare_first_name": 0,
        "linked_to_full_name": 0,
        "already_handled": 0,
    }

    for finding in findings:
        action = finding["action"]

        if action == "already_aliased":
            counts["already_handled"] += 1
            continue

        if action == "mark_classical_single_name":
            # Mark with a note identifying it as a known classical single-name author
            conn.execute(
                """
                UPDATE agents
                SET agent_notes = CASE
                    WHEN agent_notes IS NULL THEN 'classical_single_name'
                    WHEN agent_notes LIKE '%classical_single_name%' THEN agent_notes
                    ELSE agent_notes || '; classical_single_name'
                END
                WHERE id = ? AND (agent_notes IS NULL OR agent_notes NOT LIKE '%classical_single_name%')
                """,
                (finding["agent_id"],),
            )
            counts["marked_classical"] += 1
            continue

        if action == "mark_bare_first_name":
            conn.execute(
                """
                UPDATE agents
                SET agent_notes = CASE
                    WHEN agent_notes IS NULL THEN 'bare_first_name_only'
                    WHEN agent_notes LIKE '%bare_first_name_only%' THEN agent_notes
                    ELSE agent_notes || '; bare_first_name_only'
                END
                WHERE id = ? AND (agent_notes IS NULL OR agent_notes NOT LIKE '%bare_first_name_only%')
                """,
                (finding["agent_id"],),
            )
            counts["marked_bare_first_name"] += 1
            continue

        if action == "link_to_full_name":
            full_name = finding["full_name"]
            bare_norm = finding["agent_norm"]

            # Find or create authority for full name
            cur = conn.execute(
                "SELECT id FROM agent_authorities WHERE canonical_name_lower = ?",
                (full_name.lower(),),
            )
            auth_row = cur.fetchone()
            if auth_row:
                auth_id = auth_row[0]
            else:
                # Create authority entry for the full name
                cur = conn.execute(
                    """
                    INSERT INTO agent_authorities
                        (canonical_name, canonical_name_lower, agent_type,
                         authority_uri, confidence, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 0.7,
                            'auto-created by fix_09 for bare name linkage', ?, ?)
                    """,
                    (full_name, full_name.lower(), finding["agent_type"],
                     finding["authority_uri"], now, now),
                )
                auth_id = cur.lastrowid

            # Add bare name as alias if not already present
            exists = conn.execute(
                "SELECT 1 FROM agent_aliases WHERE alias_form_lower = ?",
                (bare_norm.lower(),),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO agent_aliases
                        (authority_id, alias_form, alias_form_lower, alias_type,
                         script, is_primary, priority, notes, created_at)
                    VALUES (?, ?, ?, 'variant_spelling', 'latin', 0, 0,
                            'bare first name linked by fix_09', ?)
                    """,
                    (auth_id, bare_norm, bare_norm.lower(), now),
                )

            # Also mark the agent row
            conn.execute(
                """
                UPDATE agents
                SET agent_notes = CASE
                    WHEN agent_notes IS NULL THEN 'bare_name_linked_to: ' || ?
                    WHEN agent_notes LIKE '%bare_name_linked_to%' THEN agent_notes
                    ELSE agent_notes || '; bare_name_linked_to: ' || ?
                END
                WHERE id = ?
                """,
                (full_name, full_name, finding["agent_id"]),
            )
            counts["linked_to_full_name"] += 1

    conn.commit()
    return counts


def append_fix_log(findings: list[dict], counts: dict) -> None:
    """Append one JSONL entry to the fix log."""
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Investigate and annotate bare first-name agents",
        "records_affected": len(findings),
        "action_counts": counts,
        "tables_changed": ["agents", "agent_authorities", "agent_aliases"],
        "method": "bare_name_investigation",
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
        rows = find_bare_names(conn)
        if not rows:
            print(f"[{FIX_ID}] No bare first-name agents found.")
            return

        print(f"[{FIX_ID}] Found {len(rows)} agent entries with bare first names.")

        findings = investigate(conn, rows)

        # Summarize by action
        action_summary: dict[str, int] = {}
        for f in findings:
            action_summary[f["action"]] = action_summary.get(f["action"], 0) + 1

        print(f"[{FIX_ID}] Investigation results:")
        for action, count in sorted(action_summary.items()):
            print(f"  {action}: {count}")

        print(f"\n[{FIX_ID}] Details:")
        for f in findings:
            parts = [
                f"  agent_id={f['agent_id']}",
                f"mms_id={f['mms_id']}",
                f"norm={f['agent_norm']!r}",
                f"raw={f['agent_raw']!r}",
                f"action={f['action']}",
            ]
            if f["full_name"]:
                parts.append(f"full_name={f['full_name']!r}")
            print("  ".join(parts))
            if f["title"]:
                print(f"    title: {f['title'][:80]}")

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN -- no changes made.")
            return

        archive_path = archive_data(findings, ARCHIVE_DIR)
        print(f"[{FIX_ID}] Archived {len(findings)} findings to {archive_path}")

        counts = apply_fixes(conn, findings)
        print(f"[{FIX_ID}] Applied fixes:")
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")

        append_fix_log(findings, counts)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
