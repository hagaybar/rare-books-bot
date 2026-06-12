# Network View

> Last verified: 2026-06-11

The Network view is a map-based explorer for the people, printing houses, and
relationships behind the collection. It renders agents as geo-located nodes over
a basemap of Europe and the Middle East, with relationship arcs between them, a
detail panel for any node or place, and several coloring facets. **It is
designed for larger screens**; mobile is a functional secondary view.

Route: `/network` (React SPA). API: all endpoints under `/network/*`, guest auth
required.

---

## 1. What it is (and isn't)

The target, per the 2026-06-11 committee review, is *the print-culture network of
**this** collection*: presses as hubs, books as evidence, people connected
because they appear on the same title pages — with Wikipedia as garnish, not the
main course. Every renderable edge is born with MARC evidence (an MMS ID, a
title) or a documented relationship; Wikipedia "shared category" links were
retired from the arc layer (issue #28).

---

## 2. Data model

Two materialized tables in `data/index/bibliographic.db`:

### `network_agents` (nodes)
| Column | Notes |
|--------|-------|
| `agent_norm` (PK) | normalized name; `pub:` prefix for publisher nodes |
| `display_name` | resolved label (see `resolve_display_name`) |
| `place_norm`, `lat`, `lon` | assigned place (most frequent, geocoded) |
| `birth_year`, `death_year` | from `authority_enrichment.person_info` |
| `occupations`, `primary_role` | coloring facets |
| `has_wikipedia`, `record_count`, `connection_count` | badges / node size |
| `node_type` | `person` \| `publisher` (issue #27) |
| `community` | intellectual-community color facet (issue #28) |

### `network_edges` (relationships)
`source_agent_norm`, `target_agent_norm`, `connection_type`, `confidence`,
`relationship`, `bidirectional`, `evidence`. Unique on
`(source, target, connection_type)`.

---

## 3. Edge taxonomy

Collection-derived edges (MARC-evidenced) are the default layers; Wikipedia
links are opt-in; `category` is **not** an arc type at all.

| `connection_type` | Source | Default on? | Notes |
|-------------------|--------|-------------|-------|
| `same_record` | same catalogue record (issue #26) | ✅ | role-typed, MMS-evidenced (~2,202) |
| `printed_by` | author → printing house (issue #27) | ✅ | ~351 |
| `teacher_student` | `authority_enrichment.person_info` | ✅ | documented relationship |
| `co_publication` | agents sharing ≥2 records | | |
| `same_place_period` | same city, overlapping **lifespans** (issue #28) | | lifespan-clamped, no anachronisms (~75) |
| `wikilink` | Wikipedia "mentioned together" | | opt-in |
| `llm_extraction` | LLM-discovered | | secondary |
| `category` | shared Wikipedia category | **never an arc** | retired to a coloring facet (issue #28) |

`category` rows are retained in `network_edges` (~22,132) but are excluded from
the map's arc layer **and** from the agent panel's connection list.

---

## 4. Nodes: people and publishers

- **People** come from `agents` → geocoded by their most-frequent imprint place.
- **Publishers / printing houses** (issue #27) are promoted from curated
  `publisher_authorities` (Bomberg, Aldine, Elzevir, Plantin…), keyed
  `pub:<name, city>`, geocoded from their city, sized by holdings, and linked to
  authors via `printed_by`. They render with a distinct gold glyph.

Node radius scales with `connection_count`; publishers get a size/outline boost.

---

## 5. Coloring facets (`colorBy`)

`century` (life period) · `role` · `occupation` · `community`.

The **community** facet (issue #28) reuses Wikipedia categories as a node color:
`assign_communities()` tags each node with the *most-specific* of the top-20
categories by membership; Wikipedia maintenance/metadata categories are denied
via regex (`_COMMUNITY_DENY_PATTERNS`). Policy: allow all meaningful families
(scholarly, institutional, demographic), deny only housekeeping noise — see the
`project_network_community_facet` memory. The API returns a stable
`meta.communities` palette order; the frontend maps name→color and shows a
scrollable legend. Publishers stay gold; uncategorized nodes are neutral slate.

---

## 6. API endpoints

All under `/network`, `require_role("guest")`, defined in `app/api/network.py`,
models in `app/api/network_models.py`.

| Endpoint | Purpose | Key params |
|----------|---------|-----------|
| `GET /network/map` | nodes + edges for the map | `connection_types`, `min_confidence`, `century`, `place`, `role`, `limit` (≤3000, default 500; issue #35) |
| `GET /network/search` | cross-script typeahead (issue #30) | `q`, `limit` |
| `GET /network/ego/{agent_norm}` | induced 1-hop subgraph for ego mode (issue #31) | `connection_types`, `min_confidence`, `limit` (neighbour cap, default 60) |
| `GET /network/path` | BFS shortest path between two agents (issue #33) | `source`, `target`, `connection_types`, `min_confidence`, `max_hops` |
| `GET /network/agent/{agent_norm}` | full node detail (works, connections, `name_alt`) | path is the agent_norm (supports `pub:` and Hebrew) |
| `GET /network/place/{place_norm}` | books printed in a place (issue #29) | `limit` |

**Ego** returns the focal node + its direct neighbours and every edge of the
active types among that set (neighbour↔neighbour included, so clustering shows).
Neighbours beyond `limit` are capped (strongest edge, then connection_count) and
flagged via `meta.truncated`. Shares `_map_node_from_row` with `/map`.

**Path** runs BFS over the active edge types and returns the fewest-hops route as
ordered `nodes` plus one evidenced `edge` per hop (oriented source→target).
`found=false` when the agents are in different components within `max_hops`.

**Search** UNIONs a direct name match with a fan-out through `agent_aliases`
(variant/word-reorder/cross-script) joined back to nodes, so
`maimonides`/`rambam`/`משה בן מימון` all resolve one node. `matched_alias` is set
only for alias hits (SQLite MIN()-bare-column rule prefers the direct match).

**Agent detail** excludes `category` connections, returns the collection's
`works` first (issue #18) with correct Primo links by MMS ID (issue #19), and a
`name_alt` opposite-script form for bilingual display (issue #30).

---

## 7. Frontend

`frontend/src/`:
- `pages/Network.tsx` — page shell, data fetch, URL state (issue #24), Map/Network
  view toggle (issue #31), panel routing
- `components/network/EgoView.tsx` — force-directed 1-hop ego graph
  (`react-force-graph-2d`); non-geographic peer of MapView (issue #31)
- `components/network/Breadcrumbs.tsx` — the ego-walk trail (issue #31)
- `components/network/PathFinder.tsx` — "find path to…" box + evidence-labeled
  chain, shown in ego mode (issue #33)
- `components/network/MapView.tsx` — deck.gl (`ScatterplotLayer` nodes,
  `ArcLayer` edges, `TextLayer` labels with `characterSet:'auto'`) over a
  maplibre/react-map-gl basemap; pickable arcs with "why connected" tooltips;
  co-located stack popover (issue #23)
- `components/network/AgentPanel.tsx` — node detail; works-first; bidi (`<bdi>`)
  names + `name_alt`; chat/Primo handoffs
- `components/network/PlacePanel.tsx` — place detail (issue #29)
- `components/network/ControlBar.tsx` — filters, color-by, cross-script search box
- `components/network/Legend.tsx` — active facet + edge legend (scrollable for community)
- `stores/networkStore.ts` — zustand filter state (default connection types:
  `same_record`, `printed_by`, `teacher_student`)
- `api/network.ts`, `types/network.ts` — client + types

BiDi work follows the `bidi-engineering` skill: dynamic mixed-script names are
isolated with `<bdi dir="auto">` to avoid neutral spillover.

---

## 8. Build & materialization

`scripts/network/build_network_tables.py` (`python -m scripts.network.build_network_tables <db> <geocodes>`):
- `build_network_edges` → wikilink/llm/category import, teacher_student,
  co_publication, `same_place_period` (lifespan-clamped)
- `build_network_agents` → nodes, places, geocoding, dedup, orphan cleanup
- `assign_communities` → community facet
- `build_same_record_edges`, `build_publisher_nodes`, `build_printed_by_edges`
  exist as functions and are currently applied to live DBs via fix scripts.

For an **existing** DB, the additive fix scripts (dry-run by default, `--apply`
takes a `.pre-fixNN.bak`) are the path — documented in
`docs/current/data-quality.md` §3 "Network fixes": **fix_20** (FTS), **fix_21**
(display-name repair), **fix_22** (`same_record`), **fix_23** (publisher nodes;
needs `place_geocodes.json`), **fix_24** (community facet + anachronism fix).

`network_agents.node_type` and `.community` are registered in
`scripts/marc/m3_contract.py`; the schema-contract test enforces parity.

### Deploy note
`deploy.sh` excludes `data/` from rsync. After deploying network code that
needs DB changes, apply the relevant fix script in the prod container
(`docker exec -w /app rare-books python3 scripts/qa/fixes/fix_NN_*.py --apply
--db /app/data/index/bibliographic.db`). The prod data volume's
`normalization/` dir is root-owned, so push reference files (e.g.
`place_geocodes.json`) with `docker cp` into the container, not scp to the host.

---

## 9. Routing

`/network/*` API calls must be proxied to the backend in **both**
`docker/nginx.conf` and `frontend/vite.config.ts` — otherwise the SPA fallback
returns `index.html` with HTTP 200 and `res.json()` throws (the root cause of
issue #17, where search was dead in every environment). When adding a new
`/network/<x>` route, add it to both proxy configs.

---

## 10. History & roadmap

Built out across issues #17–#33 (see the 2026-06-11 network review at
`audits/2026-06-11-network-review/REPORT.md`). Tier-1 honesty fixes (search
routing, works list, Primo, edge evidence, default view, display-name guardrail,
stack popover), Tier-2 collection-first edges (publishers, same_record, community
facet, cross-script search), and Tier-3 **ego-network mode** (#31, force-directed
Map ⟷ Network toggle with breadcrumb walking) + **pathfinding** (#33, "how are X
and Y connected?" with an evidence-labeled chain) are shipped.

The node cap was lifted (#35): `/map` serves up to 3,000 nodes (default 500),
and readability is managed by **zoom-aware label density** in MapView
(publishers always labelled; people labels grow 10→150 as you zoom in) rather
than an arbitrary cap.

Open: **#32** time slider · **#34** chat↔network loop · **#36** censorship MARC
audit (deferred) · **#37** chat-handoff query template.
