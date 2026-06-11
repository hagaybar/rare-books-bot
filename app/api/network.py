"""FastAPI router for Network Map Explorer."""
import json
import logging
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth_deps import require_role
from app.api.network_models import (
    AgentConnection,
    AgentDetail,
    AgentWork,
    MapEdge,
    MapMeta,
    MapNode,
    MapResponse,
    PlaceDetail,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/network",
    tags=["network"],
    dependencies=[Depends(require_role("guest"))],
)

DB_PATH = Path("data/index/bibliographic.db")

VALID_CONNECTION_TYPES = {
    "teacher_student", "wikilink", "llm_extraction", "category", "co_publication",
    "same_place_period", "same_record",
}


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _primo_url(mms_id: str) -> str | None:
    """Catalog deep link from the real MMS ID (issue #19)."""
    try:
        from scripts.utils.primo import generate_primo_url
        return generate_primo_url(mms_id)
    except ImportError:
        return None


def _works_for_agent(conn: sqlite3.Connection, agent_norm: str, limit: int = 25) -> list[AgentWork]:
    """The collection's books for an agent, newest-cataloguing first (issue #18)."""
    rows = conn.execute(
        """SELECT DISTINCT r.mms_id AS mms_id,
                  (SELECT t.value FROM titles t WHERE t.record_id = r.id
                   ORDER BY CASE t.title_type WHEN 'main' THEN 0 ELSE 1 END LIMIT 1) AS title,
                  (SELECT i.date_label FROM imprints i WHERE i.record_id = r.id LIMIT 1) AS date_label,
                  (SELECT i.place_display FROM imprints i WHERE i.record_id = r.id LIMIT 1) AS place_display,
                  (SELECT i.publisher_display FROM imprints i WHERE i.record_id = r.id LIMIT 1) AS publisher_display,
                  a.role_norm AS role_norm,
                  MIN(i2.date_start) AS sort_date
           FROM agents a
           JOIN records r ON r.id = a.record_id
           LEFT JOIN imprints i2 ON i2.record_id = r.id
           WHERE a.agent_norm = ?
           GROUP BY r.mms_id
           ORDER BY sort_date IS NULL, sort_date ASC
           LIMIT ?""",
        (agent_norm, limit),
    ).fetchall()
    return [
        AgentWork(
            mms_id=r["mms_id"], title=r["title"], date_label=r["date_label"],
            place_display=r["place_display"], publisher_display=r["publisher_display"],
            role_norm=r["role_norm"], primo_url=_primo_url(r["mms_id"]),
        )
        for r in rows
    ]



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

    # Handle empty types — return nodes only, no edges
    empty_types = not types or types == ["none"]
    if not empty_types:
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

        if empty_types:
            # No connection types selected — return agents sorted by record_count, no edges
            agents_sql = f"""
                SELECT na.*, 0 as filtered_count
                FROM network_agents na
                WHERE {where_sql}
                ORDER BY na.record_count DESC
                LIMIT ?
            """
            agent_params = [*params, limit]
        else:
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
                filtered_count=r["filtered_count"],
                record_count=r["record_count"],
                has_wikipedia=bool(r["has_wikipedia"]),
                primary_role=r["primary_role"],
            ))

        # Get edges between returned agents
        category_limited = False
        category_total = 0

        if empty_types or len(agent_norms) < 2:
            edges = []
        else:
            norm_list = list(agent_norms)
            norm_placeholders = ",".join("?" for _ in norm_list)

            # Build per-type edge queries, applying LIMIT 100 for category
            edge_queries = []
            edge_params_all: list = []

            for t in types:
                if t == "category":
                    edge_queries.append(f"""
                        SELECT source_agent_norm, target_agent_norm, connection_type,
                               confidence, relationship, evidence, bidirectional
                        FROM (
                            SELECT source_agent_norm, target_agent_norm, connection_type,
                                   confidence, relationship, evidence, bidirectional
                            FROM network_edges
                            WHERE connection_type = 'category'
                              AND confidence >= ?
                              AND source_agent_norm IN ({norm_placeholders})
                              AND target_agent_norm IN ({norm_placeholders})
                            ORDER BY confidence DESC
                            LIMIT 100
                        )
                    """)
                    edge_params_all.extend([min_confidence, *norm_list, *norm_list])
                else:
                    edge_queries.append(f"""
                        SELECT source_agent_norm, target_agent_norm, connection_type,
                               confidence, relationship, evidence, bidirectional
                        FROM network_edges
                        WHERE connection_type = ?
                          AND confidence >= ?
                          AND source_agent_norm IN ({norm_placeholders})
                          AND target_agent_norm IN ({norm_placeholders})
                    """)
                    edge_params_all.extend([t, min_confidence, *norm_list, *norm_list])

            combined_sql = " UNION ALL ".join(edge_queries)
            edge_rows = conn.execute(combined_sql, edge_params_all).fetchall()

            edges = [
                MapEdge(
                    source=r["source_agent_norm"],
                    target=r["target_agent_norm"],
                    type=r["connection_type"],
                    confidence=r["confidence"],
                    relationship=r["relationship"],
                    evidence=r["evidence"],
                    bidirectional=bool(r["bidirectional"]),
                )
                for r in edge_rows
            ]

            # Check if category was limited
            if "category" in types:
                cat_total_row = conn.execute(
                    f"""SELECT count(*) FROM network_edges
                        WHERE connection_type = 'category'
                          AND confidence >= ?
                          AND source_agent_norm IN ({norm_placeholders})
                          AND target_agent_norm IN ({norm_placeholders})""",
                    [min_confidence, *norm_list, *norm_list],
                ).fetchone()
                category_total = cat_total_row[0]
                if category_total > 100:
                    category_limited = True

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
                category_limited=category_limited,
                category_total=category_total,
            ),
        )
    finally:
        conn.close()


@router.get("/search")
async def search_agents(q: str = Query(""), limit: int = Query(10, ge=1, le=20)) -> dict:
    """Search network agents by display name or normalized name."""
    if not q or len(q) < 2:
        return {"results": []}
    conn = _get_db()
    try:
        results = conn.execute(
            """SELECT agent_norm, display_name, lat, lon, connection_count
               FROM network_agents
               WHERE display_name LIKE ? OR agent_norm LIKE ?
               ORDER BY connection_count DESC LIMIT ?""",
            (f"%{q}%", f"%{q}%", min(limit, 20)),
        ).fetchall()
        return {"results": [dict(r) for r in results]}
    finally:
        conn.close()


@router.get("/place/{place_norm:path}", response_model=PlaceDetail)
async def get_place_detail(place_norm: str, limit: int = Query(50, ge=1, le=200)) -> PlaceDetail:
    """Books in the collection printed in a given place (issue #29)."""
    conn = _get_db()
    try:
        total = conn.execute(
            "SELECT COUNT(DISTINCT i.record_id) FROM imprints i WHERE LOWER(i.place_norm) = LOWER(?)",
            (place_norm,),
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT DISTINCT r.mms_id AS mms_id,
                      (SELECT t.value FROM titles t WHERE t.record_id = r.id
                       ORDER BY CASE t.title_type WHEN 'main' THEN 0 ELSE 1 END LIMIT 1) AS title,
                      i.date_label AS date_label, i.place_display AS place_display,
                      i.publisher_display AS publisher_display, i.date_start AS sort_date
               FROM imprints i JOIN records r ON r.id = i.record_id
               WHERE LOWER(i.place_norm) = LOWER(?)
               GROUP BY r.mms_id
               ORDER BY sort_date IS NULL, sort_date ASC
               LIMIT ?""",
            (place_norm, limit),
        ).fetchall()
        works = [
            AgentWork(
                mms_id=r["mms_id"], title=r["title"], date_label=r["date_label"],
                place_display=r["place_display"], publisher_display=r["publisher_display"],
                primo_url=_primo_url(r["mms_id"]),
            )
            for r in rows
        ]
        return PlaceDetail(place_norm=place_norm, total=total, works=works)
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
                      confidence, relationship, evidence
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
                evidence=er["evidence"],
                confidence=er["confidence"],
            ))

        # Collection holdings (issue #18) + correct Primo links (issue #19)
        works = _works_for_agent(conn, agent_norm)
        primo_url = works[0].primo_url if works else None

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
            works=works,
            primo_url=primo_url,
            external_links=external_links,
        )
    finally:
        conn.close()
