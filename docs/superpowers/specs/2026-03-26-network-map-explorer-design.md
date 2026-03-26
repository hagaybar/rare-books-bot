# Network Map Explorer — Design Spec

**Date**: 2026-03-26
**Branch**: beta-bot-ui
**Status**: Approved

---

## Overview

A map-based interactive network explorer for the rare books agent collection. Displays agents geographically on a real map (Europe/Mediterranean), with connection arcs between cities, user-controlled filtering, and a detail panel for agent exploration.

### Goals

- **Primary audience**: Researchers/scholars discovering intellectual networks and connections between historical figures
- **Secondary audience**: General users getting an overview of what the collection contains
- **Design principle**: Sensible default view with progressive disclosure — start clean, layer complexity by user choice

### Data Foundation

- ~3,100 agents (~3,102 distinct agent_norm values; most have place associations via imprints)
- ~365 unique normalized places; top ~80 by frequency cover the vast majority of agent-place assignments
- 45,198 connections in `wikipedia_connections` (3 types: wikilink, llm_extraction, category) plus teacher/student relationships derived from `authority_enrichment.person_info`
- 1,959 agents with Wikipedia biographical summaries
- Authority enrichment: birth/death years, occupations, external links

---

## Technical Stack

### New Dependencies (Frontend)

| Package | Purpose | License |
|---------|---------|---------|
| `maplibre-gl` | WebGL map engine | BSD-3 |
| `react-map-gl` | React wrapper for MapLibre | MIT |
| `@deck.gl/core` | Core rendering framework | MIT |
| `@deck.gl/layers` | ArcLayer, ScatterplotLayer | MIT |
| `@deck.gl/react` | React integration | MIT |
| `@deck.gl/mapbox` | MapLibre interop layer | MIT |

Note: MapLibre includes supercluster internally for its built-in clustering — no separate dependency needed.

### Tile Source

OpenFreeMap Positron style — clean, light background optimized for data overlays. Free, no API key, no registration.

---

## API Layer

### `GET /network/map`

Returns filtered nodes, edges, and cluster summaries for the map view.

**Query parameters** (all optional):

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `connection_types` | comma-separated string | `teacher_student` | Types to include: `teacher_student`, `wikilink`, `llm_extraction`, `category`, `co_publication` |
| `min_confidence` | float | 0.5 | Minimum edge confidence |
| `century` | int | (none) | Filter agents active in this century (e.g., `16` = 1500-1599) |
| `place` | string | (none) | Filter to agents active in a specific city |
| `role` | string | (none) | Filter by role (e.g., `printer`, `author`) |
| `limit` | int | 150 | Max agents returned (max 500) |

**Response**:

```json
{
  "nodes": [
    {
      "agent_norm": "maimonides, moses",
      "display_name": "Moses Maimonides",
      "lat": 37.88,
      "lon": -4.77,
      "place_norm": "cordoba",
      "birth_year": 1138,
      "death_year": 1204,
      "occupations": ["philosopher", "rabbi"],
      "connection_count": 47,
      "has_wikipedia": true
    }
  ],
  "edges": [
    {
      "source": "maimonides, moses",
      "target": "ibn tibbon, samuel",
      "type": "teacher_student",
      "confidence": 0.90,
      "relationship": "teacher of",
      "bidirectional": false
    }
  ],
  "meta": {
    "total_agents": 2500,
    "showing": 150,
    "total_edges": 312
  }
}
```

**Agent ranking**: When `limit` is applied, agents are ranked by total connection count across all selected connection types. This ensures network hubs appear in the default view.

**Performance guard**: The API returns only edges between the returned agents. The frontend never receives the full 45K edge set.

### `GET /network/agent/{agent_norm}`

Returns full detail for a single agent (used by the side panel).

**Response**:

```json
{
  "agent_norm": "maimonides, moses",
  "display_name": "Moses Maimonides",
  "lat": 37.88,
  "lon": -4.77,
  "place_norm": "cordoba",
  "birth_year": 1138,
  "death_year": 1204,
  "occupations": ["philosopher", "rabbi"],
  "wikipedia_summary": "Full Wikipedia extract...",  // from wikipedia_cache.summary_extract, joined via authority_enrichment.wikidata_id
  "connections": [
    {
      "agent_norm": "ibn tibbon, samuel",
      "display_name": "Samuel ibn Tibbon",
      "type": "teacher_student",
      "relationship": "teacher of",
      "confidence": 0.90
    }
  ],
  "record_count": 7,
  "primo_url": "https://...",
  "external_links": {  // constructed from authority_enrichment: wikidata_id→URL, wikipedia_url (stored directly), viaf_id→URL
    "wikidata": "https://www.wikidata.org/wiki/Q83090",
    "wikipedia": "https://en.wikipedia.org/wiki/Maimonides",
    "viaf": "https://viaf.org/viaf/100185495"
  }
}
```

### Connection Data Sources

The 5 connection types come from **two different sources** in the database:

| Type | Source Table | Notes |
|------|-------------|-------|
| `wikilink` | `wikipedia_connections` | `source_type = 'wikilink'`, 7,011 rows |
| `llm_extraction` | `wikipedia_connections` | `source_type = 'llm_extraction'`, 12,047 rows |
| `category` | `wikipedia_connections` | `source_type = 'category'`, 26,140 rows |
| `teacher_student` | `authority_enrichment` | Derived from `person_info` JSON (teachers/students lists). Must be computed at build time. |
| `co_publication` | `agents` | Agents sharing the same `record_id`. Must be computed at build time. Minimum 2 shared records required to avoid low-signal noise. |

**Implementation strategy**: At server startup (or via a build script), materialize all 5 types into a unified `network_edges` table. This avoids expensive cross-table joins on every API request. The table is rebuilt when enrichment data changes.

```sql
CREATE TABLE network_edges (
    source_agent_norm TEXT NOT NULL,
    target_agent_norm TEXT NOT NULL,
    connection_type TEXT NOT NULL,  -- one of the 5 types above
    confidence REAL NOT NULL,
    relationship TEXT,             -- may be NULL for wikilink/category types
    bidirectional INTEGER DEFAULT 0,
    evidence TEXT,
    UNIQUE(source_agent_norm, target_agent_norm, connection_type)
);
CREATE INDEX idx_network_edges_source ON network_edges(source_agent_norm);
CREATE INDEX idx_network_edges_target ON network_edges(target_agent_norm);
CREATE INDEX idx_network_edges_type ON network_edges(connection_type);
```

The `relationship` field is populated for `teacher_student` ("teacher of"/"student of") and `llm_extraction` (LLM-extracted label). For `wikilink`, `category`, and `co_publication`, it is NULL — the frontend displays the connection type name instead.

**Confidence assignment for computed types**:
- `teacher_student`: 0.85 (Wikidata-sourced, reliable)
- `co_publication`: `min(shared_record_count / 5.0, 1.0)` — scales from 0.4 (2 shared records) to 1.0 (5+)

### Agent-to-Place Pre-computation

Agent place assignment and connection counts are **pre-computed** into a materialized table at build time (not per-request). This table is rebuilt alongside `network_edges`.

```sql
CREATE TABLE network_agents (
    agent_norm TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    place_norm TEXT,              -- primary place (may be NULL)
    lat REAL,
    lon REAL,
    birth_year INTEGER,
    death_year INTEGER,
    occupations TEXT,             -- JSON array
    has_wikipedia INTEGER DEFAULT 0,
    record_count INTEGER DEFAULT 0,     -- number of MARC records citing this agent
    connection_count INTEGER DEFAULT 0  -- total across all types
);
```

**`display_name` derivation** (fallback chain):
1. `agent_authorities.canonical_name` — joined via `agent_aliases.alias_form_lower = agent_norm` → `agent_aliases.authority_id` → `agent_authorities.id`. Covers ~428 agents via direct match; more via alias joins.
2. `authority_enrichment.label` — joined via `agents.authority_uri` → `authority_enrichment.authority_uri`. Cleaned of disambiguation suffixes (strip parenthetical like "(DNB12)"). Covers ~1,971 enriched agents.
3. Title-cased `agent_norm` (e.g., "maimonides, moses" → "Maimonides, Moses") — fallback for remainder.

### Century Filter Semantics

"Active in century X" means: the agent has at least one imprint where `date_start` falls within the century (e.g., century 16 = `date_start` between 1500 and 1599). This uses publication years from the `imprints` table, which covers all agents regardless of whether they have Wikidata birth/death data.

### URL Encoding Note

The `GET /network/agent/{agent_norm}` endpoint requires URL-encoding of `agent_norm` values since they contain commas and spaces (e.g., `maimonides%2C%20moses`). The FastAPI path parameter handles this automatically.

### Router Registration

New router `app/api/network.py` mounted at `/network` prefix in `app/api/main.py`, following the same pattern as the existing `/metadata` router.

---

## Geocoding

### Static Lookup File

`data/normalization/place_geocodes.json` — a mapping of `place_norm` values to coordinates.

The database has ~365 distinct `place_norm` values, but the distribution is heavily skewed. The geocoding file targets the **top places by frequency**, which cover the vast majority of agent-place assignments. The build script logs any agents excluded due to missing geocodes for review.

```json
{
  "amsterdam": { "lat": 52.3676, "lon": 4.9041, "display_name": "Amsterdam" },
  "venice": { "lat": 45.4408, "lon": 12.3155, "display_name": "Venice" },
  "constantinople": { "lat": 41.0082, "lon": 28.9784, "display_name": "Istanbul (Constantinople)" },
  "safed": { "lat": 32.9646, "lon": 35.4960, "display_name": "Safed" }
}
```

Generation approach: LLM-assisted for the initial batch (well-known historical cities), then hand-verified. The file grows incrementally as needed.

### Agent-to-Place Assignment

Each agent is assigned a single primary place for map positioning:

1. **Most frequent place**: The `place_norm` with the highest imprint count for that agent
2. **Tiebreaker — earliest publication**: If two places have equal imprint counts, use the one with the earliest publication date
3. **Fallback — alphabetical**: If dates are also tied, alphabetical order on `place_norm` (deterministic)
4. **No geocode for place**: If an agent's primary `place_norm` has no entry in `place_geocodes.json`, try the agent's next most frequent place. If no place can be geocoded, the agent is excluded from the map.
5. **Unplaced agents**: Agents with only `[sine loco]` or no imprint data are excluded from the map

---

## Frontend Architecture

### Screen Placement

New page at `/network` in the **Primary** tier (second item, after Chat). Added to sidebar navigation with a `GlobeAltIcon` (Heroicons outline, consistent with existing icon style).

### Page Layout

```
┌─────────────────────────────────────────────────────────┐
│  [Control Bar]                                          │
│  Connection types: [✓ Teacher/Student] [○ Wikilink]     │
│  [○ LLM-extracted] [○ Category]  Century: [All ▾]      │
│  Role: [All ▾]   Agents: [──●────] 150                 │
├───────────────────────────────────────┬─────────────────│
│                                       │                 │
│           MAP                         │  Agent Panel    │
│    (MapLibre + deck.gl arcs)          │  (slides in on  │
│                                       │   agent click)  │
│   ● Amsterdam (47)                    │                 │
│        ╲                              │                 │
│         ╲  arc                        │                 │
│          ╲                            │                 │
│           ● Venice (23)               │                 │
│                                       │                 │
├───────────────────────────────────────┴─────────────────│
│  Status: Showing 150 of 2,500 agents · 312 connections  │
└─────────────────────────────────────────────────────────┘
```

### Components

| File | Purpose |
|------|---------|
| `frontend/src/pages/Network.tsx` | Page component: layout, state orchestration, React Query data fetching |
| `frontend/src/components/network/MapView.tsx` | MapLibre + deck.gl: map rendering, ArcLayer, ScatterplotLayer, click handlers |
| `frontend/src/components/network/ControlBar.tsx` | Filter controls: connection type checkboxes, century/role dropdowns, agent count slider |
| `frontend/src/components/network/AgentPanel.tsx` | Side panel: agent bio, connections list, catalog links |
| `frontend/src/api/network.ts` | API client: `fetchMapData(params)`, `fetchAgentDetail(agentNorm)` |
| `frontend/src/types/network.ts` | TypeScript interfaces: `MapNode`, `MapEdge`, `MapResponse`, `AgentDetail` |
| `frontend/src/stores/networkStore.ts` | Zustand store for filter state (connection types, century, role, agent limit) |

### State Management

- **Filter state**: Zustand store in a new `frontend/src/stores/networkStore.ts` (connection types, century, role, agent limit) — persists across panel open/close
- **Map data**: React Query with filter params as cache key — auto-refetches on filter change
- **Selected agent**: Local component state in `Network.tsx` — cleared on map background click

### Data Flow

```
User changes filter → ControlBar updates Zustand store
  → React Query detects param change → fetches GET /network/map?params
  → Backend queries bibliographic.db
  → Returns nodes + edges + meta
  → MapView renders via deck.gl ArcLayer + ScatterplotLayer
  → User clicks agent → Network.tsx sets selectedAgent
  → React Query fetches GET /network/agent/{agent_norm}
  → AgentPanel renders details
```

---

## Map Behavior

### Default View

- Centered on Europe/Mediterranean: lat ~40, lon ~15, zoom ~4
- Top 150 agents by connection count
- Only teacher/student connections shown
- Clustered by city (numbered badges)

### Clustering

Cities with multiple agents display as a numbered circle (e.g., "Amsterdam (47)"). Clicking a cluster zooms in, expanding to show individual agent dots. Uses MapLibre's built-in GeoJSON source clustering (which uses supercluster internally) — clustering is computed client-side from the node coordinates returned by the API.

### Connection Arcs

Curved arcs between cities rendered by deck.gl ArcLayer. Visual encoding uses **color and width** (ArcLayer does not support dash/dot patterns natively):

| Type | Color | Width |
|------|-------|-------|
| `teacher_student` | Blue (#3B82F6) | Thick (3px) |
| `wikilink` | Orange (#F59E0B) | Medium (2px) |
| `llm_extraction` | Purple (#8B5CF6) | Medium (2px) |
| `category` | Gray (#9CA3AF) | Thin (1px), low opacity |
| `co_publication` | Green (#10B981) | Medium (2px) |

Within each type, arc opacity encodes confidence (higher confidence = more opaque).

### Agent Click Interaction

When a user clicks an agent dot:

1. **Map reacts**:
   - Selected agent's dot enlarges and brightens
   - All connections to/from this agent get emphasized (thicker, full opacity)
   - All other arcs fade to ~10% opacity
   - Connected agents also highlight

2. **Side panel opens** (300px, slides from right):
   - **Header**: Display name, life dates, primary place, occupations
   - **Wikipedia summary**: First ~500 chars, expandable to full text
   - **Connections list**: Grouped by type, each row clickable (navigates to that agent)
   - **Catalog links**: Record count, "View in Chat" (pre-fills query), "View in Primo"

3. **Reset**: Clicking map background closes panel and restores normal arc opacity

---

## Loading, Empty, and Error States

- **Initial load**: Map tiles render immediately. A subtle spinner overlays the map while the first API call completes. Control bar is visible but disabled until data arrives.
- **Filter change**: Map stays visible with current data while new data loads. A small "Updating..." indicator in the status bar. No spinner overlay (avoids flicker on fast responses).
- **Empty results**: If filters produce 0 agents, show a centered message on the map: "No agents match these filters. Try broadening your search." Control bar remains interactive.
- **API error**: Toast notification with error message. Map retains last successful data. Retry button in the status bar.
- **Agent detail 404**: If `GET /network/agent/{agent_norm}` fails, the side panel shows "Agent details unavailable" with a close button. Map highlighting still works from cached node data.
- **Filter debounce**: 300ms debounce on the agent count slider to avoid rapid API calls while dragging. Checkboxes and dropdowns trigger immediately.

---

## New Files

| File | Purpose |
|------|---------|
| `app/api/network.py` | FastAPI router: `GET /network/map`, `GET /network/agent/{agent_norm}` |
| `data/normalization/place_geocodes.json` | Static lat/lon for ~80 normalized places |
| `frontend/src/pages/Network.tsx` | Main page component |
| `frontend/src/components/network/MapView.tsx` | MapLibre + deck.gl map rendering |
| `frontend/src/components/network/ControlBar.tsx` | Filter controls |
| `frontend/src/components/network/AgentPanel.tsx` | Agent detail side panel |
| `frontend/src/api/network.ts` | API client functions |
| `frontend/src/types/network.ts` | TypeScript interfaces |
| `tests/app/test_network_api.py` | API endpoint tests |

---

## Testing Strategy

### Backend

- **Unit tests** (`tests/app/test_network_api.py`): Test API endpoints with mock DB, verify response shapes, filter logic, agent ranking, place assignment tiebreakers
- **Integration**: Test against real `bibliographic.db` to verify query correctness

### Frontend

- **Manual verification**: Visual check of map rendering, arc colors, clustering, panel content
- **Interaction testing**: Click flows (agent → panel → connected agent → panel updates)

---

## Out of Scope (Future Enhancements)

- Community detection / pre-computed clusters (Approach 3)
- Search box on map
- Chat integration ("Ask about this network")
- URL-sharable filter state
- Animated transitions
- Hebrew Wikipedia data (Step B from enrichment roadmap)
- Unplaced agents visualization
