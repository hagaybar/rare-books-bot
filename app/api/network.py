"""FastAPI router for Network Map Explorer."""
import json
import logging
import sqlite3
from collections import defaultdict, deque
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth_deps import require_role
from app.api.network_models import (
    AgentConnection,
    AgentCount,
    AgentDetail,
    AgentWork,
    DecadeCount,
    EgoMeta,
    EgoResponse,
    MapEdge,
    MapMeta,
    MapNode,
    MapResponse,
    NameCount,
    PathResponse,
    PlaceDetail,
    PlaceMarker,
    SubjectCount,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/network",
    tags=["network"],
    dependencies=[Depends(require_role("guest"))],
)

DB_PATH = Path("data/index/bibliographic.db")

# Per-node imprint-year span for the time slider (issue #32). One subquery
# covers both node kinds: people via agents→imprints, publishers via
# imprints.publisher_norm (the `pub:` agent_norm minus its 4-char prefix).
_ACTIVE_SPAN_SELECT = """,
    (SELECT MIN(d) FROM (
        SELECT i.date_start d FROM agents a JOIN imprints i ON i.record_id = a.record_id
        WHERE a.agent_norm = na.agent_norm AND i.date_start IS NOT NULL
        UNION ALL
        SELECT i.date_start d FROM imprints i
        WHERE i.publisher_norm = substr(na.agent_norm, 5) AND i.date_start IS NOT NULL
    )) AS active_start,
    (SELECT MAX(d) FROM (
        SELECT i.date_start d FROM agents a JOIN imprints i ON i.record_id = a.record_id
        WHERE a.agent_norm = na.agent_norm AND i.date_start IS NOT NULL
        UNION ALL
        SELECT i.date_start d FROM imprints i
        WHERE i.publisher_norm = substr(na.agent_norm, 5) AND i.date_start IS NOT NULL
    )) AS active_end"""

# 'category' is intentionally absent: issue #28 retired category from the arc
# layer (76% maintenance noise) into a node-coloring facet (network_agents.community).
VALID_CONNECTION_TYPES = {
    "teacher_student", "wikilink", "llm_extraction", "co_publication",
    "same_place_period", "same_record", "printed_by",
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


def _works_for_publisher(conn: sqlite3.Connection, name_lower: str, limit: int = 25) -> list[AgentWork]:
    """Books a printing house published (issue #27)."""
    rows = conn.execute(
        """SELECT DISTINCT r.mms_id AS mms_id,
                  (SELECT t.value FROM titles t WHERE t.record_id = r.id
                   ORDER BY CASE t.title_type WHEN 'main' THEN 0 ELSE 1 END LIMIT 1) AS title,
                  i.date_label AS date_label, i.place_display AS place_display,
                  i.publisher_display AS publisher_display, i.date_start AS sort_date
           FROM imprints i JOIN records r ON r.id = i.record_id
           WHERE i.publisher_norm = ?
              OR i.publisher_norm IN (
                  SELECT pv.variant_form_lower FROM publisher_variants pv
                  JOIN publisher_authorities pa ON pa.id = pv.authority_id
                  WHERE pa.canonical_name_lower = ?)
           GROUP BY r.mms_id
           ORDER BY sort_date IS NULL, sort_date ASC
           LIMIT ?""",
        (name_lower, name_lower, limit),
    ).fetchall()
    return [
        AgentWork(mms_id=r["mms_id"], title=r["title"], date_label=r["date_label"],
                  place_display=r["place_display"], publisher_display=r["publisher_display"],
                  role_norm="published", primo_url=_primo_url(r["mms_id"]))
        for r in rows
    ]


def _has_hebrew(s: str) -> bool:
    return any("֐" <= ch <= "׿" for ch in s)


def _alt_script_name(
    conn: sqlite3.Connection, agent_norm: str, display_name: str
) -> str | None:
    """A name form in the opposite script from display_name (issue #30).

    If the visible label is Latin we surface a Hebrew alias (and vice versa),
    so a Latin-labeled Hebrew scholar still shows their Hebrew name. Prefers a
    `cross_script` alias; ignores forms equal to the display name.
    """
    want_hebrew = not _has_hebrew(display_name)
    rows = conn.execute(
        """SELECT sa.alias_form
           FROM agents ag
           JOIN agent_authorities aa ON aa.authority_uri = ag.authority_uri
           JOIN agent_aliases sa ON sa.authority_id = aa.id
           WHERE ag.agent_norm = ?
           ORDER BY CASE sa.alias_type WHEN 'cross_script' THEN 0 ELSE 1 END""",
        (agent_norm,),
    ).fetchall()
    for (form,) in rows:
        if form and _has_hebrew(form) == want_hebrew and form.strip().lower() != display_name.strip().lower():
            return form
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


def _map_node_from_row(r: sqlite3.Row, filtered_count: int = 0) -> MapNode:
    """Build a MapNode from a network_agents row (shared by /map and /ego)."""
    try:
        occupations = json.loads(r["occupations"]) if r["occupations"] else []
    except (json.JSONDecodeError, TypeError):
        occupations = []
    keys = r.keys()
    return MapNode(
        agent_norm=r["agent_norm"],
        display_name=r["display_name"],
        lat=r["lat"],
        lon=r["lon"],
        place_norm=r["place_norm"],
        birth_year=r["birth_year"],
        death_year=r["death_year"],
        occupations=occupations,
        connection_count=r["connection_count"],
        filtered_count=(r["filtered_count"] if "filtered_count" in keys else filtered_count),
        record_count=r["record_count"],
        has_wikipedia=bool(r["has_wikipedia"]),
        primary_role=r["primary_role"],
        node_type=(r["node_type"] if "node_type" in keys else "person") or "person",
        community=(r["community"] if "community" in keys else None),
        active_start=(r["active_start"] if "active_start" in keys else None),
        active_end=(r["active_end"] if "active_end" in keys else None),
    )


@router.get("/map", response_model=MapResponse)
async def get_network_map(
    connection_types: str = Query("teacher_student", description="Comma-separated connection types"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    century: int | None = Query(None, description="Filter by century (e.g., 16 for 1500s)"),
    place: str | None = Query(None, description="Filter by place_norm"),
    role: str | None = Query(None, description="Filter by agent role"),
    limit: int = Query(500, ge=1, le=3000),
) -> MapResponse:
    """Return filtered nodes and edges for the network map.

    The node cap is generous (issue #35): the whole graph is ~2,714 nodes /
    ~6.8k non-category edges — small for deck.gl — so readability is managed by
    zoom-aware label culling client-side, not an arbitrary server cap.
    """
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
                SELECT na.*, 0 as filtered_count{_ACTIVE_SPAN_SELECT}
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
                SELECT na.*, COALESCE(ec.edge_count, 0) as filtered_count{_ACTIVE_SPAN_SELECT}
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

        nodes = [_map_node_from_row(r) for r in rows]

        # Get edges between returned agents
        if empty_types or len(agent_norms) < 2:
            edges = []
        else:
            norm_list = list(agent_norms)
            norm_placeholders = ",".join("?" for _ in norm_list)
            type_placeholders = ",".join("?" for _ in types)
            edge_rows = conn.execute(
                f"""SELECT source_agent_norm, target_agent_norm, connection_type,
                           confidence, relationship, evidence, bidirectional
                    FROM network_edges
                    WHERE connection_type IN ({type_placeholders})
                      AND confidence >= ?
                      AND source_agent_norm IN ({norm_placeholders})
                      AND target_agent_norm IN ({norm_placeholders})""",
                [*types, min_confidence, *norm_list, *norm_list],
            ).fetchall()

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

        total_agents = conn.execute(
            "SELECT count(*) FROM network_agents WHERE lat IS NOT NULL"
        ).fetchone()[0]

        # Stable community palette order (by global membership) for the legend
        communities = [
            row[0]
            for row in conn.execute(
                """SELECT community FROM network_agents
                   WHERE community IS NOT NULL
                   GROUP BY community ORDER BY COUNT(*) DESC, community ASC"""
            ).fetchall()
        ]

        # Imprint-date domain for the time slider (issue #32)
        year_min, year_max = conn.execute(
            "SELECT MIN(date_start), MAX(date_start) FROM imprints WHERE date_start IS NOT NULL"
        ).fetchone()

        return MapResponse(
            nodes=nodes,
            edges=edges,
            meta=MapMeta(
                total_agents=total_agents,
                showing=len(nodes),
                total_edges=len(edges),
                communities=communities,
                year_min=year_min,
                year_max=year_max,
            ),
        )
    finally:
        conn.close()


@router.get("/search")
async def search_agents(q: str = Query(""), limit: int = Query(10, ge=1, le=20)) -> dict:
    """Search network agents across scripts (issue #30).

    Matches the display name / normalized name directly AND fans out through
    ``agent_aliases`` (variant spellings, word reorderings, and cross-script
    forms) so "maimonides", "rambam" and "משה בן מימון" all resolve the same
    Hebrew-normed node. ``matched_alias`` is set only when the hit came via an
    alias (so the UI can show *why* it matched); a direct name match leaves it
    null. SQLite's MIN()-bare-column rule ties ``matched_alias`` to the
    lowest ``via_alias`` row, preferring a direct match when one exists.
    """
    if not q or len(q) < 2:
        return {"results": []}
    like = f"%{q}%"
    n = min(limit, 20)
    conn = _get_db()
    try:
        results = conn.execute(
            """
            SELECT agent_norm, display_name, lat, lon, connection_count,
                   matched_alias, MIN(via_alias) AS via_alias
            FROM (
                SELECT na.agent_norm, na.display_name, na.lat, na.lon,
                       na.connection_count, NULL AS matched_alias, 0 AS via_alias
                FROM network_agents na
                WHERE na.display_name LIKE ? OR na.agent_norm LIKE ?
                UNION ALL
                SELECT na.agent_norm, na.display_name, na.lat, na.lon,
                       na.connection_count, sa.alias_form AS matched_alias, 1 AS via_alias
                FROM agent_aliases sa
                JOIN agent_authorities aa ON aa.id = sa.authority_id
                JOIN agents ag ON ag.authority_uri = aa.authority_uri
                JOIN network_agents na ON na.agent_norm = ag.agent_norm
                WHERE sa.alias_form_lower LIKE ?
            )
            GROUP BY agent_norm
            ORDER BY via_alias ASC, connection_count DESC
            LIMIT ?
            """,
            (like, like, like, n),
        ).fetchall()
        return {
            "results": [
                {
                    "agent_norm": r["agent_norm"],
                    "display_name": r["display_name"],
                    "lat": r["lat"],
                    "lon": r["lon"],
                    "connection_count": r["connection_count"],
                    "matched_alias": r["matched_alias"],
                }
                for r in results
            ]
        }
    finally:
        conn.close()


@router.get("/ego/{agent_norm:path}", response_model=EgoResponse)
async def get_ego_network(
    agent_norm: str,
    connection_types: str = Query("same_record,printed_by,teacher_student"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    limit: int = Query(60, ge=1, le=150),
) -> EgoResponse:
    """Induced 1-hop neighbourhood of a focal node (issue #31).

    Nodes = the focal node + its direct neighbours under the active filters.
    Edges = every edge of those types among that node set, so
    neighbour↔neighbour links show clustering rather than a bare star. Category
    is never an allowed type, so it is excluded for free. Neighbours beyond
    `limit` are dropped (strongest edge to the focal first, then
    connection_count) and the drop is flagged via meta.truncated.
    """
    types = [t.strip() for t in connection_types.split(",") if t.strip()]
    invalid = set(types) - VALID_CONNECTION_TYPES
    if invalid:
        raise HTTPException(400, f"Invalid connection types: {invalid}")
    if not types:
        types = list(VALID_CONNECTION_TYPES)

    conn = _get_db()
    try:
        focal_row = conn.execute(
            "SELECT * FROM network_agents WHERE agent_norm = ?", (agent_norm,)
        ).fetchone()
        if not focal_row:
            raise HTTPException(404, f"Agent not found: {agent_norm}")

        tph = ",".join("?" for _ in types)
        neighbours = conn.execute(
            f"""SELECT na.agent_norm AS norm, MAX(e.conf) AS best, na.connection_count AS cc
                FROM (
                    SELECT target_agent_norm AS other, confidence AS conf
                    FROM network_edges
                    WHERE source_agent_norm = ? AND connection_type IN ({tph})
                      AND confidence >= ?
                    UNION ALL
                    SELECT source_agent_norm AS other, confidence AS conf
                    FROM network_edges
                    WHERE target_agent_norm = ? AND connection_type IN ({tph})
                      AND confidence >= ?
                ) e
                JOIN network_agents na ON na.agent_norm = e.other
                WHERE e.other != ?
                GROUP BY na.agent_norm
                ORDER BY best DESC, cc DESC, na.agent_norm ASC""",
            (agent_norm, *types, min_confidence,
             agent_norm, *types, min_confidence, agent_norm),
        ).fetchall()

        total_neighbors = len(neighbours)
        kept = neighbours[:limit]
        truncated = total_neighbors > limit
        node_norms = [agent_norm] + [r["norm"] for r in kept]

        nodes = [_map_node_from_row(focal_row)]
        if kept:
            kph = ",".join("?" for _ in kept)
            neigh_rows = conn.execute(
                f"SELECT * FROM network_agents WHERE agent_norm IN ({kph})",
                [r["norm"] for r in kept],
            ).fetchall()
            by_norm = {r["agent_norm"]: r for r in neigh_rows}
            nodes += [_map_node_from_row(by_norm[r["norm"]]) for r in kept if r["norm"] in by_norm]

        edges = []
        if len(node_norms) >= 2:
            nph = ",".join("?" for _ in node_norms)
            edge_rows = conn.execute(
                f"""SELECT source_agent_norm, target_agent_norm, connection_type,
                           confidence, relationship, evidence, bidirectional
                    FROM network_edges
                    WHERE connection_type IN ({tph}) AND confidence >= ?
                      AND source_agent_norm IN ({nph})
                      AND target_agent_norm IN ({nph})""",
                [*types, min_confidence, *node_norms, *node_norms],
            ).fetchall()
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

        return EgoResponse(
            focal=agent_norm,
            nodes=nodes,
            edges=edges,
            meta=EgoMeta(
                truncated=truncated,
                total_neighbors=total_neighbors,
                showing=len(nodes),
            ),
        )
    finally:
        conn.close()


@router.get("/path", response_model=PathResponse)
async def find_path(
    source: str = Query(...),
    target: str = Query(...),
    connection_types: str = Query("same_record,printed_by,teacher_student"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    max_hops: int = Query(8, ge=1, le=12),
) -> PathResponse:
    """Shortest path between two agents, each hop evidenced (issue #33).

    Breadth-first over the (non-category) edges of the active types — BFS yields
    the fewest-hops route. Each consecutive pair is annotated with its strongest
    edge's relationship + evidence, oriented along the path. ``found`` is false
    when the two agents are in different components within ``max_hops``.
    """
    types = [t.strip() for t in connection_types.split(",") if t.strip()]
    invalid = set(types) - VALID_CONNECTION_TYPES
    if invalid:
        raise HTTPException(400, f"Invalid connection types: {invalid}")
    if not types:
        types = list(VALID_CONNECTION_TYPES)

    conn = _get_db()
    try:
        for norm in (source, target):
            exists = conn.execute(
                "SELECT 1 FROM network_agents WHERE agent_norm = ?", (norm,)
            ).fetchone()
            if not exists:
                raise HTTPException(404, f"Agent not found: {norm}")

        def node_for(norm: str) -> MapNode:
            row = conn.execute(
                "SELECT * FROM network_agents WHERE agent_norm = ?", (norm,)
            ).fetchone()
            return _map_node_from_row(row)

        if source == target:
            return PathResponse(
                source=source, target=target, found=True, hops=0,
                nodes=[node_for(source)], edges=[],
            )

        # Adjacency over the active edge types
        tph = ",".join("?" for _ in types)
        adj: dict[str, set[str]] = defaultdict(set)
        for s, t in conn.execute(
            f"""SELECT source_agent_norm, target_agent_norm FROM network_edges
                WHERE connection_type IN ({tph}) AND confidence >= ?""",
            (*types, min_confidence),
        ).fetchall():
            adj[s].add(t)
            adj[t].add(s)

        # BFS with a depth bound
        parent: dict[str, str | None] = {source: None}
        depth = {source: 0}
        q = deque([source])
        while q:
            cur = q.popleft()
            if cur == target:
                break
            if depth[cur] >= max_hops:
                continue
            for nb in adj.get(cur, ()):  # noqa: E501
                if nb not in parent:
                    parent[nb] = cur
                    depth[nb] = depth[cur] + 1
                    q.append(nb)

        if target not in parent:
            return PathResponse(source=source, target=target, found=False)

        # Reconstruct source -> target
        chain: list[str] = []
        cur: str | None = target
        while cur is not None:
            chain.append(cur)
            cur = parent[cur]
        chain.reverse()

        # Best edge for each hop, oriented along the path
        edges: list[MapEdge] = []
        for a, b in zip(chain, chain[1:]):
            er = conn.execute(
                f"""SELECT connection_type, confidence, relationship, evidence, bidirectional
                    FROM network_edges
                    WHERE ((source_agent_norm = ? AND target_agent_norm = ?)
                        OR (source_agent_norm = ? AND target_agent_norm = ?))
                      AND connection_type IN ({tph}) AND confidence >= ?
                    ORDER BY confidence DESC LIMIT 1""",
                (a, b, b, a, *types, min_confidence),
            ).fetchone()
            edges.append(MapEdge(
                source=a, target=b,
                type=er["connection_type"] if er else "",
                confidence=er["confidence"] if er else 0.0,
                relationship=er["relationship"] if er else None,
                evidence=er["evidence"] if er else None,
                bidirectional=bool(er["bidirectional"]) if er else True,
            ))

        return PathResponse(
            source=source, target=target, found=True, hops=len(chain) - 1,
            nodes=[node_for(n) for n in chain], edges=edges,
        )
    finally:
        conn.close()


@router.get("/places", response_model=list[PlaceMarker])
async def get_places(min_books: int = Query(1, ge=1)) -> list[PlaceMarker]:
    """Aggregated printing cities for the place-first map.

    One marker per geocoded `imprints.place_norm`, sized by how many books were
    printed there — the legible "where is this collection from" overview. Coords
    come from any agent already geocoded to that place.
    """
    conn = _get_db()
    try:
        rows = conn.execute(
            """SELECT i.place_norm AS place_norm,
                      COUNT(DISTINCT i.record_id) AS record_count,
                      (SELECT na.lat FROM network_agents na
                       WHERE na.place_norm = i.place_norm AND na.lat IS NOT NULL LIMIT 1) AS lat,
                      (SELECT na.lon FROM network_agents na
                       WHERE na.place_norm = i.place_norm AND na.lon IS NOT NULL LIMIT 1) AS lon,
                      (SELECT i2.place_display FROM imprints i2
                       WHERE i2.place_norm = i.place_norm AND i2.place_display IS NOT NULL LIMIT 1) AS place_display,
                      (SELECT COUNT(*) FROM network_agents na2 WHERE na2.place_norm = i.place_norm) AS agent_count,
                      MIN(i.date_start) AS year_min, MAX(i.date_start) AS year_max
               FROM imprints i
               WHERE i.place_norm IS NOT NULL AND i.place_norm NOT IN ('[sine loco]', '')
               GROUP BY i.place_norm
               HAVING lat IS NOT NULL AND record_count >= ?
               ORDER BY record_count DESC""",
            (min_books,),
        ).fetchall()
        return [
            PlaceMarker(
                place_norm=r["place_norm"],
                place_display=r["place_display"],
                lat=r["lat"], lon=r["lon"],
                record_count=r["record_count"], agent_count=r["agent_count"],
                year_min=r["year_min"], year_max=r["year_max"],
            )
            for r in rows
        ]
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

        # --- City profile (place redesign): when/who/what for this place ---
        place_display, year_min, year_max = conn.execute(
            """SELECT (SELECT i2.place_display FROM imprints i2
                       WHERE LOWER(i2.place_norm) = LOWER(?) AND i2.place_display IS NOT NULL LIMIT 1),
                      MIN(i.date_start), MAX(i.date_start)
               FROM imprints i WHERE LOWER(i.place_norm) = LOWER(?)""",
            (place_norm, place_norm),
        ).fetchone()
        decades = [
            DecadeCount(decade=r[0], count=r[1])
            for r in conn.execute(
                """SELECT (date_start/10)*10 AS dec, COUNT(DISTINCT record_id)
                   FROM imprints WHERE LOWER(place_norm) = LOWER(?) AND date_start IS NOT NULL
                   GROUP BY dec ORDER BY dec""",
                (place_norm,),
            ).fetchall()
        ]
        # 's.n.' = sine nomine (no recorded printer) — noise, not a printer
        top_publishers = [
            NameCount(name=r[0], count=r[1])
            for r in conn.execute(
                """SELECT COALESCE(publisher_display, publisher_norm), COUNT(DISTINCT record_id) n
                   FROM imprints
                   WHERE LOWER(place_norm) = LOWER(?) AND publisher_norm IS NOT NULL
                     AND publisher_norm NOT IN ('s.n.', 's. n.', '[s.n.]')
                   GROUP BY publisher_norm ORDER BY n DESC LIMIT 8""",
                (place_norm,),
            ).fetchall()
        ]
        top_agents = [
            AgentCount(agent_norm=r[0], display_name=r[1], count=r[2])
            for r in conn.execute(
                """SELECT a.agent_norm, na.display_name, COUNT(DISTINCT i.record_id) n
                   FROM imprints i
                   JOIN agents a ON a.record_id = i.record_id
                   JOIN network_agents na ON na.agent_norm = a.agent_norm
                   WHERE LOWER(i.place_norm) = LOWER(?)
                   GROUP BY a.agent_norm ORDER BY n DESC LIMIT 8""",
                (place_norm,),
            ).fetchall()
        ]
        top_subjects = [
            SubjectCount(subject=r[0], count=r[1])
            for r in conn.execute(
                """SELECT s.value, COUNT(DISTINCT s.record_id) n
                   FROM imprints i JOIN subjects s ON s.record_id = i.record_id
                   WHERE LOWER(i.place_norm) = LOWER(?) AND s.value IS NOT NULL
                   GROUP BY s.value ORDER BY n DESC LIMIT 10""",
                (place_norm,),
            ).fetchall()
        ]
        agent_count = conn.execute(
            """SELECT COUNT(DISTINCT a.agent_norm)
               FROM imprints i JOIN agents a ON a.record_id = i.record_id
               WHERE LOWER(i.place_norm) = LOWER(?)""",
            (place_norm,),
        ).fetchone()[0]

        return PlaceDetail(
            place_norm=place_norm, place_display=place_display, total=total,
            agent_count=agent_count, year_min=year_min, year_max=year_max,
            decades=decades, top_publishers=top_publishers,
            top_agents=top_agents, top_subjects=top_subjects, works=works,
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

        # Connections (category excluded — it is a coloring facet, not a
        # relationship arc, per issue #28)
        edge_rows = conn.execute(
            """SELECT source_agent_norm, target_agent_norm, connection_type,
                      confidence, relationship, evidence
               FROM network_edges
               WHERE (source_agent_norm = ? OR target_agent_norm = ?)
                 AND connection_type != 'category'""",
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

        # Collection holdings (issue #18/#27) + correct Primo links (issue #19)
        node_type = (row["node_type"] if "node_type" in row.keys() else "person") or "person"
        if node_type == "publisher" and agent_norm.startswith("pub:"):
            works = _works_for_publisher(conn, agent_norm[len("pub:"):])
        else:
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

        name_alt = (
            None if node_type == "publisher"
            else _alt_script_name(conn, agent_norm, row["display_name"])
        )

        return AgentDetail(
            agent_norm=agent_norm,
            display_name=row["display_name"],
            name_alt=name_alt,
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
            node_type=node_type,
        )
    finally:
        conn.close()
