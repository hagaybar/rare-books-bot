# Network Map Phase 2+3 — Onboarding + Arc Visual Hierarchy

**Date**: 2026-03-27
**Status**: Approved

---

## Overview

Clean up the Network Map's default experience and arc rendering. Start with no arcs (clean dots-only view), reorganize connection types into meaningful tiers with human-readable names, add visual hierarchy to arcs, limit noisy connections, add a page header, and materialize a new "Active in Same City" connection type.

## Problems Solved

- Map starts as a mess of blue arcs — no clean first impression
- Connection type names are technical jargon
- Category connections (25K) create visual noise
- All arcs same weight — no hierarchy
- No page title or explanation
- "Same place & period" connections exist in code but aren't on the map

## Changes

### 1. Default State: No Arcs

When the page loads:
- All connection type buttons are **off** (none selected)
- Map shows only colored dots (from Phase 1) with labels
- Status bar: "Showing 150 of 2,757 agents · Select connection types to see relationships"
- This gives a clean, readable first impression

### 2. Connection Types: 6 Types in 2 Tiers

**Primary (recommended, prominent buttons):**

| Internal | Display Name | Count | Why Primary |
|----------|-------------|-------|-------------|
| `teacher_student` | Teacher & Student | 72 | Clearest scholarly relationship |
| `co_publication` | Published Together | 113 | Direct collaboration evidence |
| `same_place_period` | Active in Same City | ~500-2000 (new) | Intuitive geographic context |
| `wikilink` | Mentioned Together | 6,824 | Meaningful co-reference |

**Secondary (less useful, behind a "More" separator):**

| Internal | Display Name | Count | Why Secondary |
|----------|-------------|-------|---------------|
| `llm_extraction` | AI-Discovered | 46 | Lower confidence |
| `category` | Shared Topics | 25,245 | Noisy, overwhelms the map |

**UI layout in ControlBar:**
```
Connections: [Teacher & Student] [Published Together] [Active in Same City] [Mentioned Together]  |  More: [AI-Discovered] [Shared Topics]
```

Primary buttons are normal-sized with full color when active. Secondary buttons are smaller, muted, behind a `|` separator with "More:" label.

### 3. New Connection Type: Active in Same City

Materialize `same_place_period` connections into `network_edges` during the build step.

**Logic** (already implemented in `scripts/chat/cross_reference.py:_find_same_place_period_connections`):
- Two agents are connected if they share the same `place_norm` (via imprints) AND their active periods overlap
- Active period: from earliest `date_start` to latest `date_start` in imprints for that agent at that place
- Overlap: at least 10 years of shared activity
- Confidence: 0.70

**Build step**: Add `_build_same_place_period_edges()` to `scripts/network/build_network_tables.py` that queries the imprints table for agent-place-period overlaps and inserts into `network_edges` with `connection_type = 'same_place_period'`.

### 4. Arc Visual Hierarchy

When connections are enabled:

**Opacity by confidence:**
- Confidence >= 0.8 → opacity 200 (80%)
- Confidence >= 0.6 → opacity 130 (50%)
- Confidence < 0.6 → opacity 60 (25%)

**Width by confidence:**
- Confidence >= 0.8 → 3px
- Confidence >= 0.6 → 2px
- Confidence < 0.6 → 1px

**Volume limit for "Shared Topics":**
When `category` type is enabled, the API returns only the **top 100 strongest** category connections (by confidence, then by connection count of source+target agents). Status bar shows "(showing top 100 of 25,245)".

This is implemented in the backend: the `GET /network/map` endpoint applies a LIMIT to category edges.

### 5. Page Header

Add above the control bar:
```
Scholarly Network Map
Explore connections between 2,757 historical figures across Europe and the Middle East
```

- Title: text-xl font-semibold
- Subtitle: text-sm text-gray-500
- Compact — one line each, no excessive spacing

### 6. Updated Connection Type Config

Update `CONNECTION_TYPE_CONFIG` in `frontend/src/types/network.ts`:

```typescript
export const CONNECTION_TYPE_CONFIG = {
  teacher_student: { label: 'Teacher & Student', color: [59, 130, 246], width: 3, tier: 'primary' },
  co_publication: { label: 'Published Together', color: [16, 185, 129], width: 2, tier: 'primary' },
  same_place_period: { label: 'Active in Same City', color: [6, 182, 212], width: 2, tier: 'primary' },
  wikilink: { label: 'Mentioned Together', color: [245, 158, 11], width: 2, tier: 'primary' },
  llm_extraction: { label: 'AI-Discovered', color: [139, 92, 246], width: 2, tier: 'secondary' },
  category: { label: 'Shared Topics', color: [156, 163, 175], width: 1, tier: 'secondary' },
};
```

### 7. Default Store State

Change `connectionTypes` default from `['teacher_student']` to `[]` (empty — no connections on load).

**Critical implementation notes:**
- **Frontend**: When `connectionTypes` is empty, skip the API call entirely (or call with a special flag). Return nodes with zero edges. Don't send `connection_types=` (empty string) — it causes invalid SQL.
- **Store guard**: Remove the `if (exists && state.connectionTypes.length === 1) return state` guard in `toggleConnectionType()` — users must be able to deselect all types to return to the clean dots-only view.
- **Status bar**: When no connections selected, show "Showing N of M agents · Select connection types to see relationships". The total agent count comes from the API response (always fetch nodes even with no connection types — pass `connection_types=none` or handle empty gracefully in the backend).

## API Changes

### `GET /network/map` — Category limit

When `connection_types` includes `category`, the edge query adds `LIMIT 100` for category type only (other types return all edges). The response `meta` gains a `category_limited` boolean and `category_total` count.

### Build Script

Add `_build_same_place_period_edges()` to `scripts/network/build_network_tables.py`.

## Implementation Notes

- **Build ordering**: `_build_same_place_period_edges()` must run BEFORE `build_network_agents()` so that connection_count includes the new edge type.
- **Arc endpoints**: Update arc layer `getSourcePosition`/`getTargetPosition` to use `jitteredPositions` (same as scatter layer) so arcs land on the actual dot positions, not raw city centers.
- **Category limit SQL**: `ORDER BY confidence DESC LIMIT 100` (simple — no tiebreaker join needed).
- **Backend empty types**: Handle `connection_types=` (empty) gracefully — return nodes with zero edges instead of SQL error.

## Files

| File | Change |
|------|--------|
| `scripts/network/build_network_tables.py` | Add `_build_same_place_period_edges()`, call before `build_network_agents` |
| `app/api/network.py` | Add `same_place_period` to `VALID_CONNECTION_TYPES`, category edge limit, handle empty types |
| `app/api/network_models.py` | Add `category_limited` and `category_total` to MapMeta |
| `frontend/src/types/network.ts` | Add `same_place_period` to ConnectionType, update CONFIG with new names + tier + colors |
| `frontend/src/stores/networkStore.ts` | Default connectionTypes to `[]`, remove deselect guard |
| `frontend/src/components/network/ControlBar.tsx` | Tiered buttons, new names, "More:" separator |
| `frontend/src/components/network/MapView.tsx` | Arc opacity/width by confidence, arc endpoints from jitteredPositions |
| `frontend/src/pages/Network.tsx` | Page header, updated status bar message for empty state |
