"""
Fix 08: Merge Multi-Script Agent Variants

Agents sharing the same authority_uri but with different agent_norm values
(e.g., Latin "aristotle" vs Hebrew "אריסטו") should be bridged through
agent_authorities and agent_aliases.

Strategy:
- Find authority_uri groups with >1 distinct agent_norm
- For each group, pick the Latin/romanized form as canonical
- Ensure an agent_authorities entry exists for the canonical form
- Add cross_script aliases for all non-Latin forms
- Does NOT modify the agents table — per-record cataloging is preserved.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("data/index/bibliographic.db")
ARCHIVE_DIR = Path("data/archive/data-quality-2026-04-02")
FIX_LOG = Path("data/qa/fix-log.jsonl")
FIX_ID = "fix_08_merge_multiscript_agents"

# Regex to detect Hebrew/Arabic characters
NON_LATIN_RE = re.compile(r"[\u0590-\u05FF\u0600-\u06FF\uFB1D-\uFDFF\uFE70-\uFEFF]")


def is_latin_form(name: str) -> bool:
    """Return True if name has no Hebrew/Arabic characters."""
    return not NON_LATIN_RE.search(name)


def pick_canonical(norms: list[str]) -> tuple[str, list[str]]:
    """Pick the Latin/romanized form as canonical, return (canonical, alternates)."""
    latin_forms = [n for n in norms if is_latin_form(n)]
    non_latin_forms = [n for n in norms if not is_latin_form(n)]

    if latin_forms:
        # Prefer the longest Latin form (more descriptive)
        canonical = max(latin_forms, key=len)
        alternates = [n for n in norms if n != canonical]
    else:
        # All non-Latin; pick the longest as canonical
        canonical = max(non_latin_forms, key=len)
        alternates = [n for n in norms if n != canonical]

    return canonical, alternates


def detect_script(name: str) -> str:
    """Detect the script of a name string."""
    for ch in name:
        cat = unicodedata.category(ch)
        if cat.startswith("L"):
            cp = ord(ch)
            if 0x0590 <= cp <= 0x05FF or 0xFB1D <= cp <= 0xFB4F:
                return "hebrew"
            if 0x0600 <= cp <= 0x06FF or 0xFE70 <= cp <= 0xFEFF:
                return "arabic"
    return "latin"


def find_multiscript_groups(conn: sqlite3.Connection) -> list[dict]:
    """Find authority_uri groups with multiple distinct agent_norm values."""
    # Use a separate query to avoid GROUP_CONCAT comma-splitting issues
    # (agent_norm values themselves may contain commas like "abravanel, isaac")
    cur = conn.execute(
        """
        SELECT authority_uri
        FROM agents
        WHERE authority_uri IS NOT NULL
        GROUP BY authority_uri
        HAVING COUNT(DISTINCT agent_norm) > 1
        """
    )
    uris = [row[0] for row in cur.fetchall()]

    groups = []
    for uri in uris:
        cur2 = conn.execute(
            "SELECT DISTINCT agent_norm FROM agents WHERE authority_uri = ?",
            (uri,),
        )
        norms = [row[0] for row in cur2.fetchall()]
        if len(norms) < 2:
            continue
        canonical, alternates = pick_canonical(norms)
        groups.append({
            "authority_uri": uri,
            "all_norms": norms,
            "canonical": canonical,
            "alternates": alternates,
        })
    return groups


def get_authority_id(conn: sqlite3.Connection, canonical: str) -> int | None:
    """Look up agent_authorities by canonical_name_lower."""
    cur = conn.execute(
        "SELECT id FROM agent_authorities WHERE canonical_name_lower = ?",
        (canonical.lower(),)
    )
    row = cur.fetchone()
    return row[0] if row else None


def alias_exists(conn: sqlite3.Connection, alias_lower: str) -> bool:
    """Check if an alias already exists in agent_aliases."""
    cur = conn.execute(
        "SELECT 1 FROM agent_aliases WHERE alias_form_lower = ?",
        (alias_lower,)
    )
    return cur.fetchone() is not None


def compute_actions(conn: sqlite3.Connection, groups: list[dict]) -> list[dict]:
    """Determine what actions are needed for each group."""
    actions = []
    now = datetime.now(timezone.utc).isoformat()

    for group in groups:
        canonical = group["canonical"]
        alternates = group["alternates"]
        authority_uri = group["authority_uri"]

        # Check if authority exists for canonical form
        auth_id = get_authority_id(conn, canonical)

        # Also check if authority exists under any alternate form
        if auth_id is None:
            for alt in alternates:
                auth_id = get_authority_id(conn, alt)
                if auth_id is not None:
                    break

        action = {
            "authority_uri": authority_uri,
            "canonical": canonical,
            "alternates": alternates,
            "existing_authority_id": auth_id,
            "create_authority": auth_id is None,
            "aliases_to_add": [],
        }

        # Determine which aliases need to be added
        all_forms = [canonical] + alternates
        for form in all_forms:
            if not alias_exists(conn, form.lower()):
                script = detect_script(form)
                is_primary = (form == canonical)
                action["aliases_to_add"].append({
                    "alias_form": form,
                    "alias_form_lower": form.lower(),
                    "alias_type": "primary" if is_primary else "cross_script",
                    "script": script,
                    "is_primary": 1 if is_primary else 0,
                })

        # Only include if there's work to do
        if action["create_authority"] or action["aliases_to_add"]:
            actions.append(action)

    return actions


def archive(actions: list[dict], archive_dir: Path) -> Path:
    """Write planned actions to archive JSON."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{FIX_ID}_archive.json"
    payload = {
        "fix_id": FIX_ID,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "action_count": len(actions),
        "actions": actions,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def apply_fixes(conn: sqlite3.Connection, actions: list[dict]) -> dict:
    """Apply authority and alias changes. Returns counts."""
    now = datetime.now(timezone.utc).isoformat()
    authorities_created = 0
    aliases_added = 0

    for action in actions:
        auth_id = action["existing_authority_id"]

        # Create authority if needed
        if action["create_authority"]:
            canonical = action["canonical"]
            cur = conn.execute(
                """
                INSERT INTO agent_authorities
                    (canonical_name, canonical_name_lower, agent_type,
                     authority_uri, confidence, notes, created_at, updated_at)
                VALUES (?, ?, 'personal', ?, 0.8,
                        'auto-created by fix_08 for multiscript bridging',
                        ?, ?)
                """,
                (canonical, canonical.lower(), action["authority_uri"], now, now),
            )
            auth_id = cur.lastrowid
            authorities_created += 1

        # Add aliases
        for alias in action["aliases_to_add"]:
            conn.execute(
                """
                INSERT INTO agent_aliases
                    (authority_id, alias_form, alias_form_lower, alias_type,
                     script, is_primary, priority, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 0,
                        'auto-created by fix_08 for multiscript bridging', ?)
                """,
                (
                    auth_id,
                    alias["alias_form"],
                    alias["alias_form_lower"],
                    alias["alias_type"],
                    alias["script"],
                    alias["is_primary"],
                    now,
                ),
            )
            aliases_added += 1

    conn.commit()
    return {"authorities_created": authorities_created, "aliases_added": aliases_added}


def append_fix_log(actions: list[dict], counts: dict) -> None:
    """Append one JSONL entry to the fix log."""
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Bridge multiscript agent variants via agent_authorities + agent_aliases",
        "groups_processed": len(actions),
        "authorities_created": counts["authorities_created"],
        "aliases_added": counts["aliases_added"],
        "tables_changed": ["agent_authorities", "agent_aliases"],
        "method": "multiscript_merge",
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
        groups = find_multiscript_groups(conn)
        if not groups:
            print(f"[{FIX_ID}] No multiscript agent groups found.")
            return

        print(f"[{FIX_ID}] Found {len(groups)} authority_uri groups with multiple agent_norm values.")

        actions = compute_actions(conn, groups)
        if not actions:
            print(f"[{FIX_ID}] All groups already have authorities and aliases (idempotent).")
            return

        new_auths = sum(1 for a in actions if a["create_authority"])
        new_aliases = sum(len(a["aliases_to_add"]) for a in actions)
        print(f"[{FIX_ID}] Actions needed: {new_auths} new authorities, {new_aliases} new aliases.")

        for action in actions:
            print(f"  URI: ...{action['authority_uri'][-30:]}")
            print(f"    canonical: {action['canonical']!r}")
            print(f"    alternates: {action['alternates']}")
            if action["create_authority"]:
                print(f"    -> CREATE authority for {action['canonical']!r}")
            for alias in action["aliases_to_add"]:
                print(f"    -> ADD alias {alias['alias_form']!r} ({alias['alias_type']}, {alias['script']})")

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN -- no changes made.")
            return

        archive_path = archive(actions, ARCHIVE_DIR)
        print(f"[{FIX_ID}] Archived {len(actions)} actions to {archive_path}")

        counts = apply_fixes(conn, actions)
        print(f"[{FIX_ID}] Created {counts['authorities_created']} authorities, "
              f"added {counts['aliases_added']} aliases.")

        append_fix_log(actions, counts)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
