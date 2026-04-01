# Cascading Enrichment Filters — Design Spec

**Date**: 2026-03-27
**Status**: Approved

---

## Overview

Make the Entity Enrichment page filters dependent/cascading. When a user selects a filter (e.g., Occupation = "rabbi"), the other filter dropdowns update their counts to reflect only the filtered set. Zero-count options remain visible with "(0)".

## Current Behavior

- `GET /metadata/enrichment/facets` returns global counts (no params accepted)
- All dropdowns always show the same counts regardless of active filters
- Selecting "rabbi" shows rabbi agents, but Century dropdown still says "17th century (378)" globally

## New Behavior

- `GET /metadata/enrichment/facets` accepts the same filter params as `/enrichment/agents`
- Each facet's counts are computed with ALL active filters EXCEPT its own applied
- Zero-count options stay visible but rendered with muted text: `"20th century+ (0)"`

## API Change

### Modify `GET /metadata/enrichment/facets`

**New query parameters** (all optional, same as `/enrichment/agents`):
- `search` — text search
- `occupation` — filter by Wikidata occupation
- `century` — filter by birth century
- `role` — filter by agent role
- `has_bio` — boolean
- `has_image` — boolean

**Facet count logic**: For each facet (occupation, century, role), apply all OTHER active filters but NOT the facet's own filter. This is standard faceted search:

- **Occupation counts**: Apply century + role + search + has_bio + has_image filters, then GROUP BY occupation
- **Century counts**: Apply occupation + role + search + has_bio + has_image filters, then GROUP BY century
- **Role counts**: Apply occupation + century + search + has_bio + has_image filters, then GROUP BY role

**Response** (same shape, just with scoped counts):
```json
{
  "roles": [{"value": "author", "count": 89}, {"value": "printer", "count": 0}, ...],
  "occupations": [{"value": "rabbi", "count": 207}, {"value": "writer", "count": 45}, ...],
  "centuries": [{"value": "16th century", "count": 12}, {"value": "20th century+", "count": 0}, ...]
}
```

## Frontend Change

### `Enrichment.tsx`

1. Pass current filter state to the facets API call (already tracked in component state)
2. Refetch facets whenever any filter changes (add filters to React Query key)
3. Update dropdown `<option>` rendering to use scoped counts
4. Zero-count options: render with same text but muted style, remain selectable

### `metadata.ts` (API client)

Modify `fetchEnrichmentFacets()` to accept filter params and pass them as query string.

## Implementation Notes

- **Shared WHERE builder**: Extract the filter logic from `get_enriched_agents()` into a shared helper `_build_enrichment_where(*, search, occupation, century, role, has_bio, has_image, exclude_facet=None)`. Reuse in both the agents endpoint and the facets endpoint. This prevents duplication and drift.
- **Boolean filters**: `has_bio` and `has_image` must also be forwarded to the facets endpoint. Only send when `true` (omit when `false`).
- **React Query key**: Use `['enrichment-facets', filters]` so facets refetch on filter changes. Add `placeholderData: (prev) => prev` to avoid dropdown flicker during refetch.
- **Debounce**: The search input should be debounced (300ms) before triggering facet refetch, consistent with existing debounce patterns in the app.

## Files

| File | Action |
|------|--------|
| `app/api/metadata.py` | Extract shared WHERE builder, modify `get_enrichment_facets()` to accept filter params |
| `frontend/src/pages/admin/Enrichment.tsx` | Pass filters to facets query, update dropdown rendering, add placeholderData |
