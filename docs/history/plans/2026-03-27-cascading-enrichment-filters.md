# Cascading Enrichment Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Entity Enrichment filter dropdowns show scoped counts when other filters are active (standard faceted search).

**Architecture:** Extract the filter-building logic from `get_enriched_agents()` into a shared helper. Modify `get_enrichment_facets()` to accept filter params and compute each facet's counts with all OTHER filters applied. Frontend passes current filters to the facets query and uses `placeholderData` to prevent flicker.

**Tech Stack:** Python/FastAPI, SQLite, React 19, React Query

**Spec:** `docs/superpowers/specs/2026-03-27-cascading-enrichment-filters-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app/api/metadata.py` | Modify | Extract shared WHERE builder, modify facets endpoint |
| `frontend/src/pages/admin/Enrichment.tsx` | Modify | Pass filters to facets query, update query key |

---

### Task 1: Backend — Shared WHERE Builder + Scoped Facets

**Files:**
- Modify: `app/api/metadata.py`

- [ ] **Step 1: Extract shared filter builder**

Add a helper function before the `get_enriched_agents` endpoint (~line 1865):

```python
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
```

- [ ] **Step 2: Refactor `get_enriched_agents` to use the helper**

Replace lines 1892-1949 (the inline filter building) with:

```python
        where_sql, params = _build_enrichment_where(
            search=search, occupation=occupation, century=century,
            role=role, has_bio=has_bio, has_image=has_image,
        )
```

Verify existing behavior unchanged: `curl -s 'http://localhost:8000/metadata/enrichment/agents?occupation=rabbi&limit=5' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Total: {d[\"total\"]}')"` — should return same count as before.

- [ ] **Step 3: Modify `get_enrichment_facets` to accept filter params and scope counts**

Replace the existing `get_enrichment_facets` function (~line 1809-1862) with:

```python
@router.get("/enrichment/facets", summary="Enrichment facets for filtering")
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
```

- [ ] **Step 4: Test scoped facets**

```bash
# Global facets (no filters) — should match previous behavior
curl -s 'http://localhost:8000/metadata/enrichment/facets' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Occupations: {len(d[\"occupations\"])}, Centuries: {len(d[\"centuries\"])}, Roles: {len(d[\"roles\"])}')"

# Scoped: occupation=rabbi — century/role counts should be smaller
curl -s 'http://localhost:8000/metadata/enrichment/facets?occupation=rabbi' | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'  {c[\"value\"]}: {c[\"count\"]}') for c in d['centuries']]"
```

- [ ] **Step 5: Commit**

```bash
git add app/api/metadata.py
git commit -m "feat: cascading enrichment filters — shared WHERE builder + scoped facets"
```

---

### Task 2: Frontend — Pass Filters to Facets Query

**Files:**
- Modify: `frontend/src/pages/admin/Enrichment.tsx`

- [ ] **Step 1: Update `fetchFacets` to accept filter params**

Change the `fetchFacets` function (~line 80) from:

```typescript
async function fetchFacets(): Promise<Facets> {
  const res = await fetch('/metadata/enrichment/facets');
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}
```

To:

```typescript
async function fetchFacets(filters: {
  search?: string;
  occupation?: string;
  century?: string;
  role?: string;
  hasBio?: boolean;
  hasImage?: boolean;
}): Promise<Facets> {
  const params = new URLSearchParams();
  if (filters.search) params.set('search', filters.search);
  if (filters.occupation) params.set('occupation', filters.occupation);
  if (filters.century) params.set('century', filters.century);
  if (filters.role) params.set('role', filters.role);
  if (filters.hasBio) params.set('has_bio', 'true');
  if (filters.hasImage) params.set('has_image', 'true');
  const qs = params.toString();
  const res = await fetch(`/metadata/enrichment/facets${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Update the facets React Query to pass filters and prevent flicker**

Change the facets query (~line 395) from:

```typescript
const facetsQuery = useQuery({
  queryKey: ['enrichment-facets'],
  queryFn: fetchFacets,
  staleTime: 60_000,
});
```

To:

```typescript
const facetsQuery = useQuery({
  queryKey: ['enrichment-facets', filters],
  queryFn: () => fetchFacets(filters),
  placeholderData: (prev) => prev,
  staleTime: 10_000,
});
```

This ensures:
- Facets refetch whenever any filter changes (filters in the query key)
- Previous data stays visible during refetch (placeholderData prevents dropdown flicker)
- Shorter stale time since facets are now filter-dependent

- [ ] **Step 3: Verify and build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

- [ ] **Step 4: Commit and push**

```bash
git add frontend/src/pages/admin/Enrichment.tsx
git commit -m "feat: frontend cascading filters — pass filters to facets query"
git push origin main
```
