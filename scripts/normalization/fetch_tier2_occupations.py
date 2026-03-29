"""
Fetch Wikidata occupations for Tier 2 agents: those with authority URIs but
missing/empty occupations in the enrichment cache.  Then apply the same
occupation→role mapping used by Tier 1 (via shared occupation_mapper module).

Tier 2 agents are identified by:
  - role_norm = 'other' AND role_source = 'unknown'
  - authority_uri IS NOT NULL
  - authority_enrichment either missing, or person_info.occupations is empty/null

Pipeline per agent:
  1. extract NLI ID from authority_uri (using existing nli_client)
  2. query Wikidata (P8189) for QID
  3. fetch occupations via P106 SPARQL
  4. map occupations → role_norm via occupation_role_map.json
  5. update/insert agent rows (multi-role strategy)
  6. upsert authority_enrichment with discovered occupations

After processing all Tier 2 agents, propagate: for every agent_norm+authority_uri
that was enriched on one record, copy the new role to all other records where the
same agent still has role_norm='other'.

Usage:
    python -m scripts.normalization.fetch_tier2_occupations \\
        --db data/index/bibliographic.db \\
        --map data/normalization/occupation_role_map.json \\
        --log data/normalization/tier2_role_changes.jsonl \\
        [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from scripts.enrichment.nli_client import extract_nli_id_from_uri
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "RareBooksBot/1.0 (https://github.com/rare-books-bot; educational research)"
REQUEST_DELAY = 1.0  # seconds between Wikidata requests


# ---------------------------------------------------------------------------
# Wikidata SPARQL helpers
# ---------------------------------------------------------------------------

def _sparql_get(query: str, timeout: float = 30.0) -> dict | None:
    """Synchronous SPARQL GET against Wikidata."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    }
    params = {"query": query, "format": "json"}
    try:
        resp = httpx.get(
            WIKIDATA_SPARQL_ENDPOINT,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("SPARQL request failed: %s", exc)
        return None


def get_wikidata_id_from_nli(nli_id: str) -> str | None:
    """Resolve NLI ID → Wikidata QID via P8189."""
    query = f'''
    SELECT ?item WHERE {{
      ?item wdt:P8189 "{nli_id}" .
    }}
    LIMIT 1
    '''
    data = _sparql_get(query)
    if not data:
        return None
    bindings = data.get("results", {}).get("bindings", [])
    if bindings:
        uri = bindings[0].get("item", {}).get("value", "")
        m = re.search(r"(Q\d+)$", uri)
        if m:
            return m.group(1)
    return None


def fetch_occupations(qid: str) -> list[str]:
    """Fetch occupation labels (P106) for a Wikidata entity."""
    query = f'''
    SELECT ?occupationLabel WHERE {{
      wd:{qid} wdt:P106 ?occupation .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
    }}
    '''
    data = _sparql_get(query)
    if not data:
        return []
    bindings = data.get("results", {}).get("bindings", [])
    labels = []
    for b in bindings:
        label = b.get("occupationLabel", {}).get("value", "")
        # Skip raw QID labels (unresolved)
        if label and not label.startswith("Q"):
            labels.append(label)
    return list(set(labels))


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

def fetch_tier2_agents(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return distinct (agent_norm, authority_uri) pairs for Tier 2 agents."""
    query = """
        SELECT DISTINCT a.agent_norm, a.authority_uri
        FROM agents a
        LEFT JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
        WHERE a.role_norm = 'other'
          AND a.role_source = 'unknown'
          AND a.authority_uri IS NOT NULL
          AND a.authority_uri <> ''
          AND (ae.person_info IS NULL
               OR json_extract(ae.person_info, '$.occupations') = '[]'
               OR json_extract(ae.person_info, '$.occupations') IS NULL
               OR ae.authority_uri IS NULL)
    """
    cursor = conn.execute(query)
    return [{"agent_norm": row[0], "authority_uri": row[1]} for row in cursor.fetchall()]


def fetch_agent_rows_for_update(
    conn: sqlite3.Connection, agent_norm: str, authority_uri: str
) -> list[dict[str, Any]]:
    """Return all agent rows for a given (agent_norm, authority_uri) that need updating."""
    query = """
        SELECT id, record_id, agent_index, agent_raw, agent_type,
               role_raw, role_source, authority_uri,
               agent_norm, agent_confidence, agent_method, agent_notes,
               role_norm, role_confidence, role_method, provenance_json
        FROM agents
        WHERE agent_norm = ? AND authority_uri = ?
          AND role_norm = 'other' AND role_source = 'unknown'
        ORDER BY id
    """
    cursor = conn.execute(query, (agent_norm, authority_uri))
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


# ---------------------------------------------------------------------------
# Authority enrichment upsert
# ---------------------------------------------------------------------------

def upsert_authority_enrichment(
    conn: sqlite3.Connection,
    authority_uri: str,
    nli_id: str,
    qid: str | None,
    occupations: list[str],
) -> None:
    """Insert or update authority_enrichment with the discovered occupations."""
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()

    existing = conn.execute(
        "SELECT id, person_info FROM authority_enrichment WHERE authority_uri = ?",
        (authority_uri,),
    ).fetchone()

    if existing:
        row_id, person_info_raw = existing
        try:
            person_info = json.loads(person_info_raw) if person_info_raw else {}
        except (json.JSONDecodeError, TypeError):
            person_info = {}
        person_info["occupations"] = occupations
        conn.execute(
            "UPDATE authority_enrichment SET person_info = ?, wikidata_id = ? WHERE id = ?",
            (json.dumps(person_info, ensure_ascii=False), qid, row_id),
        )
    else:
        person_info = {"occupations": occupations}
        conn.execute(
            """INSERT INTO authority_enrichment
               (authority_uri, nli_id, wikidata_id, person_info, source, confidence, fetched_at, expires_at)
               VALUES (?, ?, ?, ?, 'wikidata_tier2', 0.90, ?, ?)""",
            (
                authority_uri, nli_id, qid,
                json.dumps(person_info, ensure_ascii=False),
                now, expires,
            ),
        )


# ---------------------------------------------------------------------------
# Cross-record propagation
# ---------------------------------------------------------------------------

def propagate_roles(conn: sqlite3.Connection, log_file, timestamp: str) -> int:
    """For agents enriched on one record, propagate to other records where
    the same (agent_norm, authority_uri) still has role_norm='other'."""
    query = """
        SELECT DISTINCT good.agent_norm, good.authority_uri,
               good.role_norm, good.role_confidence, good.role_method, good.role_source, good.role_raw
        FROM agents good
        WHERE good.role_source = 'wikidata_occupation'
          AND good.role_norm != 'other'
          AND EXISTS (
              SELECT 1 FROM agents bad
              WHERE bad.agent_norm = good.agent_norm
                AND bad.authority_uri = good.authority_uri
                AND bad.role_norm = 'other'
                AND bad.role_source = 'unknown'
          )
    """
    enriched = conn.execute(query).fetchall()
    propagated = 0

    for row in enriched:
        agent_norm, authority_uri, role_norm, role_confidence, role_method, role_source, role_raw = row
        targets = conn.execute(
            """SELECT id, record_id FROM agents
               WHERE agent_norm = ? AND authority_uri = ?
                 AND role_norm = 'other' AND role_source = 'unknown'""",
            (agent_norm, authority_uri),
        ).fetchall()

        for target_id, record_id in targets:
            conn.execute(
                """UPDATE agents
                   SET role_norm = ?, role_confidence = ?, role_method = ?,
                       role_source = ?, role_raw = ?
                   WHERE id = ?""",
                (role_norm, role_confidence, role_method + "_propagated", role_source, role_raw, target_id),
            )
            propagated += 1
            if log_file:
                log_file.write(json.dumps({
                    "timestamp": timestamp,
                    "action": "propagate",
                    "agent_id": target_id,
                    "record_id": record_id,
                    "agent_norm": agent_norm,
                    "old_role_norm": "other",
                    "new_role_norm": role_norm,
                    "confidence": role_confidence,
                    "method": role_method + "_propagated",
                }, ensure_ascii=False) + "\n")

    return propagated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    db_path: Path,
    map_path: Path,
    log_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fetch Tier 2 occupations from Wikidata and apply role mappings."""
    occ_map = load_occupation_map(map_path)
    direct, semantic, unmapped, priority_order = unpack_map(occ_map)

    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        tier2 = fetch_tier2_agents(conn)
        logger.info("Found %d distinct Tier 2 agent/URI pairs to process", len(tier2))

        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()

        stats: dict[str, Any] = {
            "processed": 0, "wikidataFound": 0, "occupationsFound": 0,
            "rolesAssigned": 0, "noNliId": 0, "noQid": 0,
            "noOccupations": 0, "noMappedRoles": 0, "errors": 0,
            "primaryUpdates": 0, "additionalInserts": 0, "skippedDuplicates": 0,
            "propagated": 0, "roleDistribution": {},
        }

        updates: list[tuple] = []
        inserts: list[tuple] = []
        enrichment_upserts: list[dict] = []

        for idx, t2 in enumerate(tier2):
            agent_norm = t2["agent_norm"]
            authority_uri = t2["authority_uri"]
            stats["processed"] += 1

            try:
                nli_id = extract_nli_id_from_uri(authority_uri)
                if not nli_id:
                    logger.debug("No NLI ID from URI: %s", authority_uri)
                    stats["noNliId"] += 1
                    continue

                time.sleep(REQUEST_DELAY)
                qid = get_wikidata_id_from_nli(nli_id)
                if not qid:
                    logger.debug("No Wikidata QID for NLI %s (%s)", nli_id, agent_norm)
                    stats["noQid"] += 1
                    continue

                stats["wikidataFound"] += 1
                logger.info("[%d/%d] %s → NLI %s → %s", idx + 1, len(tier2), agent_norm, nli_id, qid)

                time.sleep(REQUEST_DELAY)
                occupations = fetch_occupations(qid)
                enrichment_upserts.append({
                    "authority_uri": authority_uri, "nli_id": nli_id,
                    "qid": qid, "occupations": occupations,
                })
                if not occupations:
                    logger.info("  No occupations for %s (%s)", qid, agent_norm)
                    stats["noOccupations"] += 1
                    continue

                stats["occupationsFound"] += 1
                logger.info("  Occupations: %s", occupations)

                roles = resolve_roles(occupations, direct, semantic, unmapped, priority_order)
                if not roles:
                    logger.info("  No mapped roles for %s", agent_norm)
                    stats["noMappedRoles"] += 1
                    continue

                logger.info("  Mapped roles: %s", [r["role_norm"] for r in roles])

                agent_rows = fetch_agent_rows_for_update(conn, agent_norm, authority_uri)
                if not agent_rows:
                    continue

                primary = roles[0]
                role_method = f"wikidata_occupation_{primary['mapping_type']}"

                for agent in agent_rows:
                    existing = _existing_roles_for_record(
                        conn, agent["agent_norm"], agent["record_id"]
                    )

                    updates.append((
                        primary["role_norm"], primary["confidence"],
                        role_method, "wikidata_occupation",
                        primary["source_occupation"], agent["id"],
                    ))
                    stats["primaryUpdates"] += 1
                    stats["rolesAssigned"] += 1
                    stats["roleDistribution"][primary["role_norm"]] = (
                        stats["roleDistribution"].get(primary["role_norm"], 0) + 1
                    )

                    for extra_role in roles[1:]:
                        if extra_role["role_norm"] in existing:
                            stats["skippedDuplicates"] += 1
                            continue

                        extra_method = f"wikidata_occupation_{extra_role['mapping_type']}"
                        inserts.append((
                            agent["record_id"], agent["agent_index"],
                            agent["agent_raw"], agent["agent_type"],
                            extra_role["source_occupation"], "wikidata_occupation",
                            agent["authority_uri"], agent["agent_norm"],
                            agent["agent_confidence"], agent["agent_method"],
                            agent["agent_notes"], extra_role["role_norm"],
                            extra_role["confidence"], extra_method,
                            agent["provenance_json"],
                        ))
                        stats["additionalInserts"] += 1
                        stats["rolesAssigned"] += 1
                        stats["roleDistribution"][extra_role["role_norm"]] = (
                            stats["roleDistribution"].get(extra_role["role_norm"], 0) + 1
                        )
                        existing.add(extra_role["role_norm"])

            except Exception:
                logger.exception("Error processing agent %s", agent_norm)
                stats["errors"] += 1
                continue

        if dry_run:
            logger.info("[DRY RUN] Would update %d rows and insert %d rows", len(updates), len(inserts))
        else:
            with open(log_path, "w", encoding="utf-8") as log_file:
                # Write change log entries
                for u in updates:
                    log_file.write(json.dumps({
                        "timestamp": timestamp, "action": "update",
                        "agent_id": u[5], "new_role_norm": u[0],
                        "confidence": u[1], "method": u[2],
                    }, ensure_ascii=False) + "\n")
                for ins in inserts:
                    log_file.write(json.dumps({
                        "timestamp": timestamp, "action": "insert",
                        "record_id": ins[0], "agent_norm": ins[7],
                        "new_role_norm": ins[11], "confidence": ins[12],
                    }, ensure_ascii=False) + "\n")

                try:
                    conn.execute("BEGIN")

                    for eu in enrichment_upserts:
                        upsert_authority_enrichment(
                            conn, eu["authority_uri"], eu["nli_id"],
                            eu["qid"], eu["occupations"],
                        )
                    if enrichment_upserts:
                        logger.info("Upserted %d authority_enrichment rows", len(enrichment_upserts))

                    if updates:
                        conn.executemany(
                            """UPDATE agents
                               SET role_norm = ?, role_confidence = ?, role_method = ?,
                                   role_source = ?, role_raw = ?
                               WHERE id = ?""",
                            updates,
                        )
                        logger.info("Updated %d primary agent roles", len(updates))

                    if inserts:
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

                    propagated = propagate_roles(conn, log_file, timestamp)
                    stats["propagated"] = propagated
                    if propagated:
                        logger.info("Propagated roles to %d additional rows", propagated)

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
        description="Fetch Wikidata occupations for Tier 2 agents and apply role mappings"
    )
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--map", type=Path, default=Path("data/normalization/occupation_role_map.json"))
    parser.add_argument("--log", type=Path, default=Path("data/normalization/tier2_role_changes.jsonl"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.db.exists():
        logger.error("Database not found: %s", args.db)
        sys.exit(1)
    if not args.map.exists():
        logger.error("Mapping file not found: %s", args.map)
        sys.exit(1)

    logger.info("Fetching Tier 2 Wikidata occupations")
    logger.info("  DB:  %s", args.db)
    logger.info("  Map: %s", args.map)
    logger.info("  Log: %s", args.log)
    if args.dry_run:
        logger.info("  Mode: DRY RUN")

    stats = run(args.db, args.map, args.log, args.dry_run)

    logger.info("=== Summary ===")
    logger.info("Processed:          %d", stats["processed"])
    logger.info("Wikidata found:     %d", stats["wikidataFound"])
    logger.info("Occupations found:  %d", stats["occupationsFound"])
    logger.info("Roles assigned:     %d", stats["rolesAssigned"])
    logger.info("Primary updates:    %d", stats["primaryUpdates"])
    logger.info("Additional inserts: %d", stats["additionalInserts"])
    logger.info("Skipped duplicates: %d", stats["skippedDuplicates"])
    logger.info("Propagated:         %d", stats["propagated"])
    logger.info("Errors:             %d", stats["errors"])

    print(json.dumps({
        "processed": stats["processed"],
        "rolesAssigned": stats["rolesAssigned"],
        "wikidataFound": stats["wikidataFound"],
        "errors": stats["errors"],
    }))


if __name__ == "__main__":
    main()
