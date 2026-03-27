"""FastAPI router for Network Map Explorer."""
import json
import logging
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.api.network_models import (
    AgentConnection,
    AgentDetail,
    MapEdge,
    MapMeta,
    MapNode,
    MapResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network", tags=["network"])

DB_PATH = Path("data/index/bibliographic.db")

VALID_CONNECTION_TYPES = {
    "teacher_student", "wikilink", "llm_extraction", "category", "co_publication"
}


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/map", response_model=MapResponse)
async def get_network_map(
    connection_types: str = Query("teacher_student", description="Comma-separated connection types"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    century: int | None = Query(None, description="Filter by century (e.g., 16 for 1500s)"),
    place: str | None = Query(None, description="Filter by place_norm"),
    role: str | None = Query(None, description="Filter by agent role"),
    limit: int = Query(150, ge=1, le=500),
) -> MapResponse:
    """Return filtered nodes and edges for the network map."""
    types = [t.strip() for t in connection_types.split(",") if t.strip()]
    invalid = set(types) - VALID_CONNECTION_TYPES
    if invalid:
        raise HTTPException(400, f"Invalid connection types: {invalid}")

    conn = _get_db()
    try:
        # Build agent filter query
        where_clauses = ["na.lat IS NOT NULL"]
        params: list = []

        if century:
            year_start = (century - 1) * 100
            year_end = year_start + 99
            where_clauses.append("""na.agent_norm IN (
                SELECT DISTINCT a.agent_norm FROM agents a
                JOIN imprints i ON a.record_id = i.record_id
                WHERE i.date_start >= ? AND i.date_start <= ?)""")
            params.extend([year_start, year_end])

        if place:
            where_clauses.append("na.place_norm = ?")
            params.append(place)

        if role:
            where_clauses.append("""na.agent_norm IN (
                SELECT DISTINCT agent_norm FROM agents WHERE role_norm = ?)""")
            params.append(role)

        where_sql = " AND ".join(where_clauses)

        # Get top agents by connection count within selected types
        type_placeholders = ",".join("?" for _ in types)
        agents_sql = f"""
            SELECT na.*, COALESCE(ec.edge_count, 0) as filtered_count
            FROM network_agents na
            LEFT JOIN (
                SELECT agent_norm, count(*) as edge_count FROM (
                    SELECT source_agent_norm as agent_norm FROM network_edges
                    WHERE connection_type IN ({type_placeholders}) AND confidence >= ?
                    UNION ALL
                    SELECT target_agent_norm FROM network_edges
                    WHERE connection_type IN ({type_placeholders}) AND confidence >= ?
                ) GROUP BY agent_norm
            ) ec ON ec.agent_norm = na.agent_norm
            WHERE {where_sql}
            ORDER BY filtered_count DESC
            LIMIT ?
        """
        agent_params = [*types, min_confidence, *types, min_confidence, *params, limit]
        rows = conn.execute(agents_sql, agent_params).fetchall()

        agent_norms = {r["agent_norm"] for r in rows}

        nodes = []
        for r in rows:
            occupations = []
            try:
                occupations = json.loads(r["occupations"]) if r["occupations"] else []
            except (json.JSONDecodeError, TypeError):
                pass
            nodes.append(MapNode(
                agent_norm=r["agent_norm"],
                display_name=r["display_name"],
                lat=r["lat"],
                lon=r["lon"],
                place_norm=r["place_norm"],
                birth_year=r["birth_year"],
                death_year=r["death_year"],
                occupations=occupations,
                connection_count=r["connection_count"],
                has_wikipedia=bool(r["has_wikipedia"]),
                primary_role=r["primary_role"],
            ))

        # Get edges between returned agents
        if len(agent_norms) < 2:
            edges = []
        else:
            norm_list = list(agent_norms)
            norm_placeholders = ",".join("?" for _ in norm_list)
            edge_sql = f"""
                SELECT source_agent_norm, target_agent_norm, connection_type,
                       confidence, relationship, bidirectional
                FROM network_edges
                WHERE connection_type IN ({type_placeholders})
                  AND confidence >= ?
                  AND source_agent_norm IN ({norm_placeholders})
                  AND target_agent_norm IN ({norm_placeholders})
            """
            edge_params = [*types, min_confidence, *norm_list, *norm_list]
            edge_rows = conn.execute(edge_sql, edge_params).fetchall()
            edges = [
                MapEdge(
                    source=r["source_agent_norm"],
                    target=r["target_agent_norm"],
                    type=r["connection_type"],
                    confidence=r["confidence"],
                    relationship=r["relationship"],
                    bidirectional=bool(r["bidirectional"]),
                )
                for r in edge_rows
            ]

        total_agents = conn.execute(
            "SELECT count(*) FROM network_agents WHERE lat IS NOT NULL"
        ).fetchone()[0]

        return MapResponse(
            nodes=nodes,
            edges=edges,
            meta=MapMeta(
                total_agents=total_agents,
                showing=len(nodes),
                total_edges=len(edges),
            ),
        )
    finally:
        conn.close()


@router.get("/agent/{agent_norm:path}", response_model=AgentDetail)
async def get_agent_detail(agent_norm: str) -> AgentDetail:
    """Return full detail for a single agent."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM network_agents WHERE agent_norm = ?", (agent_norm,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Agent not found: {agent_norm}")

        occupations = []
        try:
            occupations = json.loads(row["occupations"]) if row["occupations"] else []
        except (json.JSONDecodeError, TypeError):
            pass

        # Wikipedia summary
        wikipedia_summary = None
        wiki_row = conn.execute(
            """SELECT wc.summary_extract FROM wikipedia_cache wc
               JOIN authority_enrichment ae ON ae.wikidata_id = wc.wikidata_id
               JOIN agents a ON a.authority_uri = ae.authority_uri
               WHERE a.agent_norm = ?
               LIMIT 1""",
            (agent_norm,),
        ).fetchone()
        if wiki_row:
            wikipedia_summary = wiki_row[0]

        # Connections
        edge_rows = conn.execute(
            """SELECT source_agent_norm, target_agent_norm, connection_type,
                      confidence, relationship
               FROM network_edges
               WHERE source_agent_norm = ? OR target_agent_norm = ?""",
            (agent_norm, agent_norm),
        ).fetchall()

        connections = []
        for er in edge_rows:
            other_norm = er["target_agent_norm"] if er["source_agent_norm"] == agent_norm else er["source_agent_norm"]
            other_row = conn.execute(
                "SELECT display_name FROM network_agents WHERE agent_norm = ?",
                (other_norm,),
            ).fetchone()
            other_display = other_row["display_name"] if other_row else other_norm
            connections.append(AgentConnection(
                agent_norm=other_norm,
                display_name=other_display,
                type=er["connection_type"],
                relationship=er["relationship"],
                confidence=er["confidence"],
            ))

        # Primo URL: link to the first record by this agent in the catalog
        primo_url = None
        try:
            from scripts.utils.primo import generate_primo_url
            first_record = conn.execute(
                "SELECT DISTINCT record_id FROM agents WHERE agent_norm = ? LIMIT 1",
                (agent_norm,),
            ).fetchone()
            if first_record:
                # record_id is the MMS ID
                primo_url = generate_primo_url(str(first_record[0]))
        except ImportError:
            pass

        # External links
        external_links = {}
        ae_row = conn.execute(
            """SELECT ae.wikidata_id, ae.wikipedia_url, ae.viaf_id
               FROM authority_enrichment ae
               JOIN agents a ON a.authority_uri = ae.authority_uri
               WHERE a.agent_norm = ?
               LIMIT 1""",
            (agent_norm,),
        ).fetchone()
        if ae_row:
            if ae_row["wikidata_id"]:
                external_links["wikidata"] = f"https://www.wikidata.org/wiki/{ae_row['wikidata_id']}"
            if ae_row["wikipedia_url"]:
                external_links["wikipedia"] = ae_row["wikipedia_url"]
            if ae_row["viaf_id"]:
                external_links["viaf"] = f"https://viaf.org/viaf/{ae_row['viaf_id']}"

        return AgentDetail(
            agent_norm=agent_norm,
            display_name=row["display_name"],
            lat=row["lat"],
            lon=row["lon"],
            place_norm=row["place_norm"],
            birth_year=row["birth_year"],
            death_year=row["death_year"],
            occupations=occupations,
            wikipedia_summary=wikipedia_summary,
            connections=connections,
            record_count=row["record_count"],
            primo_url=primo_url,
            external_links=external_links,
        )
    finally:
        conn.close()
