"""FastAPI router for entity enrichment endpoints.

Provides endpoints for inspecting Wikidata/VIAF enrichment data
associated with agents in the bibliographic database.
"""

import json
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from app.api.metadata_common import _get_db_path
from scripts.utils.primo import generate_primo_url as _generate_primo_url

router = APIRouter(prefix="/metadata/enrichment", tags=["metadata-enrichment"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_enrichment_where(
    *,
    search: str = "",
    occupation: str = "",
    century: str = "",
    role: str = "",
    has_bio: bool = False,
    has_image: bool = False,
) -> tuple[str, list]:
    """Build WHERE clause for enrichment queries. Returns (where_sql, params)."""
    where_clauses = ["ae.authority_uri IS NOT NULL"]
    params: list = []

    if has_bio:
        where_clauses.append("ae.person_info IS NOT NULL")
    if has_image:
        where_clauses.append("ae.image_url IS NOT NULL")
    if search:
        where_clauses.append(
            "(a.agent_raw LIKE ? OR a.agent_norm LIKE ? OR ae.label LIKE ? OR ae.description LIKE ?)"
        )
        term = f"%{search}%"
        params.extend([term, term, term, term])
    if role:
        if role == "(none)":
            where_clauses.append("(a.role_raw IS NULL OR a.role_raw = '')")
        else:
            where_clauses.append("a.role_raw = ?")
            params.append(role)
    if occupation:
        where_clauses.append(
            "ae.authority_uri IN ("
            "  SELECT ae2.authority_uri FROM authority_enrichment ae2, "
            "  json_each(json_extract(ae2.person_info, '$.occupations')) "
            "  WHERE json_each.value = ?)"
        )
        params.append(occupation)
    if century:
        century_ranges = {
            "before 1400": (None, 1400),
            "15th century": (1400, 1500),
            "16th century": (1500, 1600),
            "17th century": (1600, 1700),
            "18th century": (1700, 1800),
            "19th century": (1800, 1900),
            "20th century+": (1900, 2100),
        }
        rng = century_ranges.get(century)
        if rng:
            lo, hi = rng
            if lo is None:
                where_clauses.append("json_extract(ae.person_info, '$.birth_year') < ?")
                params.append(hi)
            else:
                where_clauses.append(
                    "json_extract(ae.person_info, '$.birth_year') >= ? AND "
                    "json_extract(ae.person_info, '$.birth_year') < ?"
                )
                params.extend([lo, hi])

    return " AND ".join(where_clauses), params


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/stats", summary="Enrichment statistics")
async def get_enrichment_stats():
    """Return summary statistics about entity enrichment coverage."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        stats = {}
        stats["total"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment"
        ).fetchone()[0]
        stats["with_wikidata"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE wikidata_id IS NOT NULL"
        ).fetchone()[0]
        stats["with_viaf"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE viaf_id IS NOT NULL"
        ).fetchone()[0]
        stats["with_person_info"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE person_info IS NOT NULL"
        ).fetchone()[0]
        stats["with_image"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE image_url IS NOT NULL"
        ).fetchone()[0]
        stats["with_wikipedia"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE wikipedia_url IS NOT NULL"
        ).fetchone()[0]
        stats["agents_linked"] = conn.execute(
            "SELECT count(DISTINCT a.agent_norm) FROM agents a "
            "JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri"
        ).fetchone()[0]
        stats["total_agents"] = conn.execute(
            "SELECT count(DISTINCT agent_norm) FROM agents"
        ).fetchone()[0]
        return stats
    finally:
        conn.close()


@router.get("/facets", summary="Enrichment facets for filtering")
async def get_enrichment_facets(
    search: str = "",
    occupation: str = "",
    century: str = "",
    role: str = "",
    has_bio: bool = False,
    has_image: bool = False,
):
    """Return facet values scoped to active filters (standard faceted search).

    Each facet's counts are computed with all OTHER active filters applied,
    but NOT the facet's own filter. This shows how many results each option
    would produce if selected.
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Roles: apply all filters EXCEPT role
        role_where, role_params = _build_enrichment_where(
            search=search, occupation=occupation, century=century,
            has_bio=has_bio, has_image=has_image,
        )
        roles = [
            {"value": r[0] or "(none)", "count": r[1]}
            for r in conn.execute(
                f"SELECT a.role_raw, count(DISTINCT COALESCE(ae.wikidata_id, a.agent_norm)) "
                f"FROM agents a JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri "
                f"WHERE {role_where} "
                f"GROUP BY a.role_raw ORDER BY count(DISTINCT COALESCE(ae.wikidata_id, a.agent_norm)) DESC LIMIT 15",
                role_params,
            ).fetchall()
        ]

        # Occupations: apply all filters EXCEPT occupation
        occ_where, occ_params = _build_enrichment_where(
            search=search, century=century, role=role,
            has_bio=has_bio, has_image=has_image,
        )
        occupations = [
            {"value": r[0], "count": r[1]}
            for r in conn.execute(
                f"SELECT value, count(*) as cnt FROM ("
                f"  SELECT json_each.value as value "
                f"  FROM authority_enrichment ae "
                f"  JOIN agents a ON a.authority_uri = ae.authority_uri "
                f"  , json_each(json_extract(ae.person_info, '$.occupations')) "
                f"  WHERE {occ_where}"
                f") GROUP BY value ORDER BY cnt DESC LIMIT 25",
                occ_params,
            ).fetchall()
        ]

        # Centuries: apply all filters EXCEPT century
        cent_where, cent_params = _build_enrichment_where(
            search=search, occupation=occupation, role=role,
            has_bio=has_bio, has_image=has_image,
        )
        centuries = [
            {"value": r[0], "count": r[1]}
            for r in conn.execute(
                f"SELECT "
                f"  CASE "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1400 THEN 'before 1400' "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1500 THEN '15th century' "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1600 THEN '16th century' "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1700 THEN '17th century' "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1800 THEN '18th century' "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1900 THEN '19th century' "
                f"    ELSE '20th century+' "
                f"  END as century_label, "
                f"  count(*) as cnt "
                f"FROM authority_enrichment ae "
                f"JOIN agents a ON a.authority_uri = ae.authority_uri "
                f"WHERE {cent_where} AND ae.person_info IS NOT NULL "
                f"  AND json_extract(ae.person_info, '$.birth_year') IS NOT NULL "
                f"GROUP BY century_label ORDER BY century_label",
                cent_params,
            ).fetchall()
        ]

        return {"roles": roles, "occupations": occupations, "centuries": centuries}
    finally:
        conn.close()


@router.get("/agents", summary="Enriched agents list")
async def get_enriched_agents(
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    has_bio: bool = False,
    role: str = "",
    occupation: str = "",
    century: str = "",
    has_image: bool = False,
):
    """List agents with their enrichment data from Wikidata.

    Args:
        limit: Max results (default 50)
        offset: Pagination offset
        search: Search in agent name or enrichment label
        has_bio: If true, only return agents with person_info
        role: Filter by agent role (e.g. 'author', 'printer')
        occupation: Filter by Wikidata occupation (e.g. 'rabbi', 'theologian')
        century: Filter by birth century (e.g. '16th century')
        has_image: If true, only return agents with an image
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        where_sql, params = _build_enrichment_where(
            search=search, occupation=occupation, century=century,
            role=role, has_bio=has_bio, has_image=has_image,
        )

        # Count total (deduplicated by wikidata_id to merge Hebrew/Latin name variants)
        total = conn.execute(
            f"SELECT count(DISTINCT COALESCE(ae.wikidata_id, a.agent_norm)) FROM agents a "
            f"JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri "
            f"WHERE {where_sql}",
            params,
        ).fetchone()[0]

        # Fetch agents with enrichment (deduplicated by wikidata_id to merge
        # Hebrew/Latin variants of the same person into a single card)
        rows = conn.execute(
            f"""
            SELECT
                MIN(a.agent_norm) as agent_norm,
                GROUP_CONCAT(DISTINCT a.agent_raw) as agent_raw,
                a.agent_type,
                GROUP_CONCAT(DISTINCT a.role_raw) as role_raw,
                a.authority_uri,
                ae.nli_id,
                ae.wikidata_id,
                ae.viaf_id,
                ae.isni_id,
                ae.loc_id,
                ae.label,
                ae.description,
                ae.person_info,
                ae.image_url,
                ae.wikipedia_url,
                ae.confidence,
                count(DISTINCT a.record_id) as record_count
            FROM agents a
            JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
            WHERE {where_sql}
            GROUP BY COALESCE(ae.wikidata_id, a.agent_norm)
            ORDER BY record_count DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

        items = []
        for row in rows:
            item = dict(row)
            # Parse person_info JSON
            if item.get("person_info"):
                try:
                    item["person_info"] = json.loads(item["person_info"])
                except (json.JSONDecodeError, TypeError):
                    pass
            items.append(item)

        return {"total": total, "limit": limit, "offset": offset, "items": items}
    finally:
        conn.close()


@router.get(
    "/agent/{agent_norm}",
    summary="Get enrichment for a specific agent",
)
async def get_agent_enrichment(agent_norm: str):
    """Get full enrichment data for a specific agent by normalized name."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT
                a.agent_norm, a.agent_raw, a.agent_type, a.role_raw, a.authority_uri,
                ae.nli_id, ae.wikidata_id, ae.viaf_id, ae.isni_id, ae.loc_id,
                ae.label, ae.description, ae.person_info,
                ae.image_url, ae.wikipedia_url, ae.confidence
            FROM agents a
            JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
            WHERE a.agent_norm = ?
            LIMIT 1
            """,
            (agent_norm,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_norm}' not found or not enriched")

        item = dict(row)
        if item.get("person_info"):
            try:
                item["person_info"] = json.loads(item["person_info"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Also get all records this agent appears in
        records = conn.execute(
            """
            SELECT DISTINCT r.mms_id, t.value as title, a.role_raw
            FROM agents a
            JOIN records r ON a.record_id = r.id
            LEFT JOIN titles t ON r.id = t.record_id AND t.title_type = 'main'
            WHERE a.agent_norm = ?
            ORDER BY t.value
            """,
            (agent_norm,),
        ).fetchall()

        item["records"] = [dict(r) for r in records]
        return item
    finally:
        conn.close()


@router.get("/agent-records", summary="Records for an enriched agent")
async def get_agent_records(
    wikidata_id: str = Query("", description="Wikidata ID (e.g., Q319902)"),
    agent_norm: str = Query("", description="Agent norm (fallback if no wikidata_id)"),
):
    """Get bibliographic records where this agent appears."""
    if not wikidata_id and not agent_norm:
        raise HTTPException(400, "Provide either wikidata_id or agent_norm")
    if wikidata_id and agent_norm:
        raise HTTPException(400, "Provide only one of wikidata_id or agent_norm")

    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Find all agent_norms for this entity
        if wikidata_id:
            norms = [r[0] for r in conn.execute(
                """SELECT DISTINCT a.agent_norm FROM agents a
                   JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
                   WHERE ae.wikidata_id = ?""",
                (wikidata_id,),
            ).fetchall()]
            # Get display name from enrichment
            label_row = conn.execute(
                "SELECT label FROM authority_enrichment WHERE wikidata_id = ? LIMIT 1",
                (wikidata_id,),
            ).fetchone()
            display_name = label_row["label"] if label_row else (norms[0] if norms else "Unknown")
        else:
            norms = [agent_norm]
            label_row = conn.execute(
                """SELECT ae.label FROM authority_enrichment ae
                   JOIN agents a ON a.authority_uri = ae.authority_uri
                   WHERE a.agent_norm = ? LIMIT 1""",
                (agent_norm,),
            ).fetchone()
            display_name = label_row["label"] if label_row else agent_norm

        if not norms:
            raise HTTPException(404, f"Agent not found: {wikidata_id or agent_norm}")

        placeholders = ",".join("?" for _ in norms)
        rows = conn.execute(
            f"""SELECT DISTINCT
                    r.mms_id,
                    t.value as title,
                    i.date_raw,
                    i.date_start,
                    i.place_norm,
                    i.publisher_norm,
                    a.role_raw as role
                FROM agents a
                JOIN records r ON a.record_id = r.id
                LEFT JOIN titles t ON t.record_id = r.id AND t.title_type = 'main'
                LEFT JOIN imprints i ON i.record_id = r.id
                WHERE a.agent_norm IN ({placeholders})
                ORDER BY i.date_start ASC NULLS LAST""",
            norms,
        ).fetchall()

        records = []
        seen_mms = set()
        for row in rows:
            mms = row["mms_id"]
            if mms in seen_mms:
                continue
            seen_mms.add(mms)
            records.append({
                "mms_id": mms,
                "title": row["title"],
                "date_raw": row["date_raw"],
                "date_start": row["date_start"],
                "place_norm": row["place_norm"],
                "publisher_norm": row["publisher_norm"],
                "role": row["role"],
                "primo_url": _generate_primo_url(mms) if mms else None,
            })

        return {
            "display_name": display_name,
            "record_count": len(records),
            "records": records,
        }
    finally:
        conn.close()
