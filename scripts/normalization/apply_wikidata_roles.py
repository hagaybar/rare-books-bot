"""
Apply cached Wikidata occupations to agents with role_norm='other' and role_source='unknown'.

Tier 1: These agents already have Wikidata occupations stored in authority_enrichment.person_info.
For agents with multiple mapped occupations, we create one row per role:
  - The original row is updated with the highest-priority role.
  - Additional rows are inserted for each extra mapped role.

Usage:
    python -m scripts.normalization.apply_wikidata_roles \
        --db data/index/bibliographic.db \
        --map data/normalization/occupation_role_map.json \
        --log data/normalization/tier1_role_changes.jsonl \
        [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.normalization.occupation_mapper import (
    load_occupation_map,
    resolve_roles,
    unpack_map,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def fetch_tier1_agents(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Fetch all Tier 1 agents: role_norm='other', role_source='unknown', with Wikidata occupations."""
    query = """
        SELECT
            a.id,
            a.record_id,
            a.agent_index,
            a.agent_raw,
            a.agent_type,
            a.role_raw,
            a.role_source,
            a.authority_uri,
            a.agent_norm,
            a.agent_confidence,
            a.agent_method,
            a.agent_notes,
            a.role_norm,
            a.role_confidence,
            a.role_method,
            a.provenance_json,
            json_extract(ae.person_info, '$.occupations') AS occupations_json
        FROM agents a
        JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
        WHERE a.role_norm = 'other'
          AND a.role_source = 'unknown'
          AND ae.person_info IS NOT NULL
          AND json_extract(ae.person_info, '$.occupations') IS NOT NULL
          AND json_extract(ae.person_info, '$.occupations') != '[]'
        ORDER BY a.id
    """
    cursor = conn.execute(query)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _existing_roles_for_record(
    conn: sqlite3.Connection, agent_norm: str, record_id: int
) -> set[str]:
    """Return set of role_norm values already assigned to this agent on this record."""
    rows = conn.execute(
        "SELECT role_norm FROM agents WHERE agent_norm = ? AND record_id = ?",
        (agent_norm, record_id),
    ).fetchall()
    return {r[0] for r in rows}


def apply_roles(
    db_path: Path,
    map_path: Path,
    log_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Main entry point: apply Wikidata occupation mappings to Tier 1 agents."""
    occ_map = load_occupation_map(map_path)
    direct, semantic, unmapped, priority_order = unpack_map(occ_map)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        agents = fetch_tier1_agents(conn)
        logger.info("Found %d Tier 1 agents with Wikidata occupations", len(agents))

        log_path.parent.mkdir(parents=True, exist_ok=True)

        stats = {
            "total_tier1_agents": len(agents),
            "agents_with_mapped_roles": 0,
            "agents_no_mapped_roles": 0,
            "primary_updates": 0,
            "additional_inserts": 0,
            "skipped_duplicates": 0,
            "total_role_assignments": 0,
            "role_distribution": {},
        }

        updates: list[tuple] = []
        inserts: list[tuple] = []
        timestamp = datetime.now(timezone.utc).isoformat()

        # Open log file with context manager
        log_handle = open(log_path, "w", encoding="utf-8") if not dry_run else None
        try:
            for agent in agents:
                try:
                    occupations = json.loads(agent["occupations_json"])
                except (json.JSONDecodeError, TypeError):
                    stats["agents_no_mapped_roles"] += 1
                    continue

                if not isinstance(occupations, list) or len(occupations) == 0:
                    stats["agents_no_mapped_roles"] += 1
                    continue

                roles = resolve_roles(occupations, direct, semantic, unmapped, priority_order)

                if not roles:
                    stats["agents_no_mapped_roles"] += 1
                    continue

                stats["agents_with_mapped_roles"] += 1

                # Check existing roles on this (agent_norm, record_id) to avoid duplicates
                existing = _existing_roles_for_record(
                    conn, agent["agent_norm"], agent["record_id"]
                )

                # Primary role: highest priority (first in sorted list)
                primary = roles[0]
                role_method = f"wikidata_occupation_{primary['mapping_type']}"
                role_raw_str = primary["source_occupation"]

                updates.append((
                    primary["role_norm"],
                    primary["confidence"],
                    role_method,
                    "wikidata_occupation",
                    role_raw_str,
                    agent["id"],
                ))
                stats["primary_updates"] += 1
                stats["total_role_assignments"] += 1
                stats["role_distribution"][primary["role_norm"]] = (
                    stats["role_distribution"].get(primary["role_norm"], 0) + 1
                )

                if log_handle:
                    log_handle.write(json.dumps({
                        "timestamp": timestamp,
                        "action": "update",
                        "agent_id": agent["id"],
                        "record_id": agent["record_id"],
                        "agent_norm": agent["agent_norm"],
                        "old_role_norm": "other",
                        "new_role_norm": primary["role_norm"],
                        "confidence": primary["confidence"],
                        "method": role_method,
                        "source_occupation": primary["source_occupation"],
                        "all_occupations": occupations,
                        "all_mapped_roles": [r["role_norm"] for r in roles],
                    }, ensure_ascii=False) + "\n")

                # Additional roles (index 1+): INSERT new rows, skip if role already exists
                for extra_role in roles[1:]:
                    if extra_role["role_norm"] in existing:
                        stats["skipped_duplicates"] += 1
                        continue

                    extra_method = f"wikidata_occupation_{extra_role['mapping_type']}"

                    inserts.append((
                        agent["record_id"],
                        agent["agent_index"],
                        agent["agent_raw"],
                        agent["agent_type"],
                        extra_role["source_occupation"],
                        "wikidata_occupation",
                        agent["authority_uri"],
                        agent["agent_norm"],
                        agent["agent_confidence"],
                        agent["agent_method"],
                        agent["agent_notes"],
                        extra_role["role_norm"],
                        extra_role["confidence"],
                        extra_method,
                        agent["provenance_json"],
                    ))
                    stats["additional_inserts"] += 1
                    stats["total_role_assignments"] += 1
                    stats["role_distribution"][extra_role["role_norm"]] = (
                        stats["role_distribution"].get(extra_role["role_norm"], 0) + 1
                    )
                    # Track so subsequent rows for same agent/record don't re-insert
                    existing.add(extra_role["role_norm"])

                    if log_handle:
                        log_handle.write(json.dumps({
                            "timestamp": timestamp,
                            "action": "insert",
                            "source_agent_id": agent["id"],
                            "record_id": agent["record_id"],
                            "agent_norm": agent["agent_norm"],
                            "new_role_norm": extra_role["role_norm"],
                            "confidence": extra_role["confidence"],
                            "method": extra_method,
                            "source_occupation": extra_role["source_occupation"],
                        }, ensure_ascii=False) + "\n")
        finally:
            if log_handle:
                log_handle.close()

        if dry_run:
            logger.info("[DRY RUN] Would update %d agents and insert %d additional rows",
                         len(updates), len(inserts))
        else:
            try:
                conn.execute("BEGIN")
                conn.executemany(
                    """UPDATE agents
                       SET role_norm = ?, role_confidence = ?, role_method = ?,
                           role_source = ?, role_raw = ?
                       WHERE id = ?""",
                    updates,
                )
                logger.info("Updated %d primary agent roles", len(updates))

                conn.executemany(
                    """INSERT INTO agents (
                           record_id, agent_index, agent_raw, agent_type,
                           role_raw, role_source, authority_uri,
                           agent_norm, agent_confidence, agent_method, agent_notes,
                           role_norm, role_confidence, role_method, provenance_json
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    inserts,
                )
                logger.info("Inserted %d additional role rows", len(inserts))
                conn.commit()
                logger.info("Transaction committed successfully")
            except Exception:
                conn.rollback()
                logger.exception("Transaction failed, rolled back")
                raise
    finally:
        conn.close()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply Wikidata occupations to Tier 1 agents (role_norm='other', role_source='unknown')"
    )
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--map", type=Path, default=Path("data/normalization/occupation_role_map.json"))
    parser.add_argument("--log", type=Path, default=Path("data/normalization/tier1_role_changes.jsonl"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.db.exists():
        logger.error("Database not found: %s", args.db)
        sys.exit(1)
    if not args.map.exists():
        logger.error("Mapping file not found: %s", args.map)
        sys.exit(1)

    logger.info("Applying Wikidata occupation roles (Tier 1)")
    logger.info("  DB:  %s", args.db)
    logger.info("  Map: %s", args.map)
    logger.info("  Log: %s", args.log)
    if args.dry_run:
        logger.info("  Mode: DRY RUN")

    stats = apply_roles(args.db, args.map, args.log, args.dry_run)

    logger.info("=== Summary ===")
    logger.info("Total Tier 1 agents examined: %d", stats["total_tier1_agents"])
    logger.info("Agents with mapped roles:     %d", stats["agents_with_mapped_roles"])
    logger.info("Agents with no mapped roles:  %d", stats["agents_no_mapped_roles"])
    logger.info("Primary role updates:         %d", stats["primary_updates"])
    logger.info("Additional role inserts:       %d", stats["additional_inserts"])
    logger.info("Skipped duplicates:           %d", stats["skipped_duplicates"])
    logger.info("Total role assignments:        %d", stats["total_role_assignments"])
    logger.info("Role distribution:")
    for role, count in sorted(stats["role_distribution"].items(), key=lambda x: -x[1]):
        logger.info("  %-20s %d", role, count)


if __name__ == "__main__":
    main()
