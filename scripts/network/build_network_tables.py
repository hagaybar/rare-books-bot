"""Build materialized network_edges and network_agents tables for the Network Map Explorer.

Usage:
    python -m scripts.network.build_network_tables data/index/bibliographic.db data/normalization/place_geocodes.json
"""
import argparse
import json
import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def title_case_agent_norm(agent_norm: str) -> str:
    """Convert 'maimonides, moses' to 'Maimonides, Moses'."""
    return ", ".join(part.strip().title() for part in agent_norm.split(","))


def resolve_display_name(conn: sqlite3.Connection, agent_norm: str) -> str:
    """Resolve display name using 3-level fallback chain."""
    # Level 1: agent_authorities via agent_aliases
    row = conn.execute(
        """SELECT aa.canonical_name FROM agent_authorities aa
           JOIN agent_aliases al ON al.authority_id = aa.id
           WHERE al.alias_form_lower = ?
           LIMIT 1""",
        (agent_norm,),
    ).fetchone()
    if row and row[0]:
        return row[0]

    # Level 2: authority_enrichment.label via agents.authority_uri
    row = conn.execute(
        """SELECT DISTINCT ae.label FROM authority_enrichment ae
           JOIN agents a ON a.authority_uri = ae.authority_uri
           WHERE a.agent_norm = ? AND ae.label IS NOT NULL
           LIMIT 1""",
        (agent_norm,),
    ).fetchone()
    if row and row[0]:
        # Strip disambiguation suffixes like "(DNB12)"
        label = re.sub(r"\s*\([^)]*\)\s*$", "", row[0]).strip()
        if label:
            return label

    # Level 3: title-cased agent_norm
    return title_case_agent_norm(agent_norm)


def build_network_edges(conn: sqlite3.Connection) -> int:
    """Materialize all connection types into network_edges table."""
    conn.execute("DROP TABLE IF EXISTS network_edges")
    conn.execute("""
        CREATE TABLE network_edges (
            source_agent_norm TEXT NOT NULL,
            target_agent_norm TEXT NOT NULL,
            connection_type TEXT NOT NULL,
            confidence REAL NOT NULL,
            relationship TEXT,
            bidirectional INTEGER DEFAULT 0,
            evidence TEXT,
            UNIQUE(source_agent_norm, target_agent_norm, connection_type)
        )
    """)

    # 1. Wikipedia connections (wikilink, llm_extraction, category)
    conn.execute("""
        INSERT OR IGNORE INTO network_edges
            (source_agent_norm, target_agent_norm, connection_type, confidence,
             relationship, bidirectional, evidence)
        SELECT source_agent_norm, target_agent_norm, source_type, confidence,
               relationship, bidirectional, evidence
        FROM wikipedia_connections
    """)
    wiki_count = conn.execute("SELECT changes()").fetchone()[0]
    logger.info("Inserted %d wikipedia connections", wiki_count)

    # 2. Teacher/student from authority_enrichment.person_info
    ts_count = _build_teacher_student_edges(conn)
    logger.info("Inserted %d teacher/student connections", ts_count)

    # 3. Co-publication (agents sharing >= 2 records)
    copub_count = _build_co_publication_edges(conn)
    logger.info("Inserted %d co-publication connections", copub_count)

    # 4. Same place/period (agents sharing same city with >=10 year overlap)
    spp_count = _build_same_place_period_edges(conn)
    logger.info("Inserted %d same-place-period connections", spp_count)

    # Create indexes
    conn.execute("CREATE INDEX idx_network_edges_source ON network_edges(source_agent_norm)")
    conn.execute("CREATE INDEX idx_network_edges_target ON network_edges(target_agent_norm)")
    conn.execute("CREATE INDEX idx_network_edges_type ON network_edges(connection_type)")

    total = conn.execute("SELECT count(*) FROM network_edges").fetchone()[0]
    logger.info("Total network_edges: %d", total)
    return total


def _build_teacher_student_edges(conn: sqlite3.Connection) -> int:
    """Extract teacher/student relationships from authority_enrichment.person_info."""
    rows = conn.execute(
        "SELECT authority_uri, person_info FROM authority_enrichment WHERE person_info IS NOT NULL"
    ).fetchall()

    count = 0
    for authority_uri, person_info_str in rows:
        try:
            person_info = json.loads(person_info_str)
        except (json.JSONDecodeError, TypeError):
            continue

        # Resolve this authority's agent_norm
        agent_row = conn.execute(
            "SELECT DISTINCT agent_norm FROM agents WHERE authority_uri = ? LIMIT 1",
            (authority_uri,),
        ).fetchone()
        if not agent_row:
            continue
        source_norm = agent_row[0]

        # Teachers
        for teacher_name in person_info.get("teachers", []):
            target_norm = _resolve_name_to_agent_norm(conn, teacher_name)
            if target_norm and target_norm != source_norm:
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO network_edges
                           (source_agent_norm, target_agent_norm, connection_type,
                            confidence, relationship, bidirectional)
                           VALUES (?, ?, 'teacher_student', 0.85, 'student of', 0)""",
                        (source_norm, target_norm),
                    )
                    count += conn.execute("SELECT changes()").fetchone()[0]
                except sqlite3.IntegrityError:
                    pass

        # Students
        for student_name in person_info.get("students", []):
            target_norm = _resolve_name_to_agent_norm(conn, student_name)
            if target_norm and target_norm != source_norm:
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO network_edges
                           (source_agent_norm, target_agent_norm, connection_type,
                            confidence, relationship, bidirectional)
                           VALUES (?, ?, 'teacher_student', 0.85, 'teacher of', 0)""",
                        (source_norm, target_norm),
                    )
                    count += conn.execute("SELECT changes()").fetchone()[0]
                except sqlite3.IntegrityError:
                    pass

    return count


def _resolve_name_to_agent_norm(conn: sqlite3.Connection, name: str) -> str | None:
    """Try to resolve a free-text name to an agent_norm in our collection."""
    # Try direct match on agent_norm
    name_lower = name.lower().strip()
    row = conn.execute(
        "SELECT DISTINCT agent_norm FROM agents WHERE agent_norm = ? LIMIT 1",
        (name_lower,),
    ).fetchone()
    if row:
        return row[0]

    # Try alias lookup: find alias matching name -> get authority_id -> find agent_norm via sibling alias
    row = conn.execute(
        """SELECT DISTINCT a.agent_norm FROM agents a
           JOIN agent_aliases al2 ON al2.alias_form_lower = a.agent_norm
           JOIN agent_aliases al1 ON al1.authority_id = al2.authority_id
           WHERE al1.alias_form_lower = ?
           LIMIT 1""",
        (name_lower,),
    ).fetchone()
    if row:
        return row[0]

    # Try partial match: "last, first" format
    parts = name_lower.split()
    if len(parts) >= 2:
        # Try "last, first"
        candidate = f"{parts[-1]}, {parts[0]}"
        row = conn.execute(
            "SELECT DISTINCT agent_norm FROM agents WHERE agent_norm = ? LIMIT 1",
            (candidate,),
        ).fetchone()
        if row:
            return row[0]

    return None


def _build_same_place_period_edges(conn: sqlite3.Connection) -> int:
    """Find agents active in the same city during overlapping periods (>=10 years)."""
    # For each agent, get their place + date range per place
    agent_places = conn.execute("""
        SELECT a.agent_norm, i.place_norm,
               MIN(i.date_start) as earliest, MAX(i.date_start) as latest
        FROM agents a
        JOIN imprints i ON a.record_id = i.record_id
        WHERE i.place_norm IS NOT NULL AND i.date_start IS NOT NULL
          AND i.place_norm != '[sine loco]'
        GROUP BY a.agent_norm, i.place_norm
        HAVING MAX(i.date_start) - MIN(i.date_start) >= 0
    """).fetchall()

    # Group by place
    from collections import defaultdict
    place_agents = defaultdict(list)
    for norm, place, earliest, latest in agent_places:
        place_agents[place].append((norm, earliest, latest))

    count = 0
    for place, agents in place_agents.items():
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                a1_norm, a1_start, a1_end = agents[i]
                a2_norm, a2_start, a2_end = agents[j]
                # Check overlap of at least 10 years
                overlap_start = max(a1_start, a2_start)
                overlap_end = min(a1_end or a1_start, a2_end or a2_start)
                if overlap_end - overlap_start >= 10:
                    src = min(a1_norm, a2_norm)
                    tgt = max(a1_norm, a2_norm)
                    try:
                        conn.execute(
                            """INSERT OR IGNORE INTO network_edges
                               (source_agent_norm, target_agent_norm, connection_type,
                                confidence, relationship, bidirectional, evidence)
                               VALUES (?, ?, 'same_place_period', 0.70, ?, 1, ?)""",
                            (src, tgt, f"both active in {place}",
                             f"{place}: {overlap_start}-{overlap_end}"),
                        )
                        count += conn.execute("SELECT changes()").fetchone()[0]
                    except sqlite3.IntegrityError:
                        pass
    return count


def _build_co_publication_edges(conn: sqlite3.Connection) -> int:
    """Find agent pairs sharing >= 2 records."""
    conn.execute("""
        INSERT OR IGNORE INTO network_edges
            (source_agent_norm, target_agent_norm, connection_type,
             confidence, relationship, bidirectional)
        SELECT norm1, norm2, 'co_publication',
               MIN(CAST(count_shared AS REAL) / 5.0, 1.0),
               NULL, 1
        FROM (
            SELECT a1.agent_norm as norm1, a2.agent_norm as norm2,
                   count(DISTINCT a1.record_id) as count_shared
            FROM agents a1
            JOIN agents a2 ON a1.record_id = a2.record_id
                AND a1.agent_norm < a2.agent_norm
            GROUP BY a1.agent_norm, a2.agent_norm
            HAVING count(DISTINCT a1.record_id) >= 2
        )
    """)
    return conn.execute("SELECT changes()").fetchone()[0]


def build_network_agents(
    conn: sqlite3.Connection, geocodes: dict[str, dict]
) -> int:
    """Materialize network_agents table with pre-computed place assignments."""
    conn.execute("DROP TABLE IF EXISTS network_agents")
    conn.execute("""
        CREATE TABLE network_agents (
            agent_norm TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            place_norm TEXT,
            lat REAL,
            lon REAL,
            birth_year INTEGER,
            death_year INTEGER,
            occupations TEXT,
            primary_role TEXT,
            has_wikipedia INTEGER DEFAULT 0,
            record_count INTEGER DEFAULT 0,
            connection_count INTEGER DEFAULT 0
        )
    """)

    # Get all distinct agent_norms from agents table
    agent_norms = [
        r[0]
        for r in conn.execute("SELECT DISTINCT agent_norm FROM agents").fetchall()
    ]

    inserted = 0
    excluded_no_geocode = 0

    for agent_norm in agent_norms:
        display_name = resolve_display_name(conn, agent_norm)

        # Place assignment: most frequent, tiebreak by earliest date, then alpha
        place_row = conn.execute(
            """SELECT place_norm, count(*) as cnt, min(date_start) as earliest
               FROM imprints i
               JOIN agents a ON a.record_id = i.record_id
               WHERE a.agent_norm = ? AND i.place_norm IS NOT NULL
                 AND i.place_norm != '[sine loco]'
               GROUP BY i.place_norm
               ORDER BY cnt DESC, earliest ASC, i.place_norm ASC
               LIMIT 10""",
            (agent_norm,),
        ).fetchall()

        place_norm = None
        lat = None
        lon = None
        for p_row in place_row:
            pn = p_row[0]
            if pn in geocodes:
                place_norm = pn
                lat = geocodes[pn]["lat"]
                lon = geocodes[pn]["lon"]
                break

        # Get person info
        person_row = conn.execute(
            """SELECT ae.person_info, ae.wikidata_id
               FROM authority_enrichment ae
               JOIN agents a ON a.authority_uri = ae.authority_uri
               WHERE a.agent_norm = ?
               LIMIT 1""",
            (agent_norm,),
        ).fetchone()

        birth_year = None
        death_year = None
        occupations = "[]"
        has_wikipedia = 0

        if person_row and person_row[0]:
            try:
                pi = json.loads(person_row[0])
                birth_year = pi.get("birth_year")
                death_year = pi.get("death_year")
                occs = pi.get("occupations", [])
                occupations = json.dumps(occs) if occs else "[]"
            except (json.JSONDecodeError, TypeError):
                pass

            # Check if this agent has a Wikipedia article
            if person_row[1]:
                wiki_row = conn.execute(
                    "SELECT 1 FROM wikipedia_cache WHERE wikidata_id = ? LIMIT 1",
                    (person_row[1],),
                ).fetchone()
                if wiki_row:
                    has_wikipedia = 1

        # Record count
        record_count = conn.execute(
            "SELECT count(DISTINCT record_id) FROM agents WHERE agent_norm = ?",
            (agent_norm,),
        ).fetchone()[0]

        # Primary role (most common role for this agent)
        role_row = conn.execute(
            "SELECT role_norm, count(*) as cnt FROM agents WHERE agent_norm = ? AND role_norm IS NOT NULL GROUP BY role_norm ORDER BY cnt DESC LIMIT 1",
            (agent_norm,),
        ).fetchone()
        primary_role = role_row[0] if role_row else None

        # Connection count (from network_edges)
        connection_count = conn.execute(
            """SELECT count(*) FROM network_edges
               WHERE source_agent_norm = ? OR target_agent_norm = ?""",
            (agent_norm, agent_norm),
        ).fetchone()[0]

        if place_norm is None:
            excluded_no_geocode += 1
            continue

        conn.execute(
            """INSERT OR REPLACE INTO network_agents
               (agent_norm, display_name, place_norm, lat, lon,
                birth_year, death_year, occupations, primary_role,
                has_wikipedia, record_count, connection_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_norm, display_name, place_norm, lat, lon,
                birth_year, death_year, occupations, primary_role,
                has_wikipedia, record_count, connection_count,
            ),
        )
        inserted += 1

    logger.info("Inserted %d agents, excluded %d (no geocode + no connections)", inserted, excluded_no_geocode)
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Build network tables")
    parser.add_argument("db_path", type=Path, help="Path to bibliographic.db")
    parser.add_argument("geocodes_path", type=Path, help="Path to place_geocodes.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with open(args.geocodes_path) as f:
        geocodes = json.load(f)
    logger.info("Loaded %d geocodes", len(geocodes))

    conn = sqlite3.connect(str(args.db_path))
    try:
        edge_count = build_network_edges(conn)
        agent_count = build_network_agents(conn, geocodes)
        conn.commit()
        logger.info("Done. %d edges, %d agents", edge_count, agent_count)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
