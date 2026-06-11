# Ego-Network Mode — Design Spec

> Issue #31 · Drafted 2026-06-11 · Status: approved (design Q&A)

## Goal

Add a second, non-geographic way to explore the same network: click a person or
printing house and see their **force-directed 1-hop world** (a web of bubbles),
then walk node→node via breadcrumbs. A **Map ⟷ Network** toggle makes the two
peer views over one shared filter state.

This is the first slice of #31. Pathfinding ("find path between two agents") is
explicitly deferred to #33.

## User experience (plain)

- A **Map / Network** switch sits in the control bar.
- In **Network** mode you see a chosen person in the middle with the people and
  presses they're connected to floating around them; lines show the links and a
  hover tells you *why* ("printed by…", "appears in the same book…").
- **Click a neighbor** → the web re-centers on them; repeat to wander the
  collection one hop at a time.
- A **breadcrumb trail** across the top (`Spinoza › Rieuwertsz › …`) lets you
  jump back to any earlier node.
- Entering Network mode with **nothing selected** centers on the
  **most-connected node** (decision A) so there's always something to explore.
- Clicking a node also opens the existing detail panel; the panel gains an
  **"Explore connections →"** button that enters Network mode focused on it.

## Backend — `GET /network/ego/{agent_norm}`

Returns the **induced 1-hop subgraph** of the focal node.

- **Nodes:** the focal node + its directly-connected neighbors (within the
  active `connection_types` and `min_confidence`).
- **Edges:** *all* non-category edges where **both** endpoints are in
  {focal ∪ neighbors} — so neighbor↔neighbor links show clustering, not just a
  star. `category` excluded (consistent with #28).
- **Params:** `connection_types` (same vocabulary/validation as `/map`),
  `min_confidence` (default 0.5), `limit` (neighbor cap, default 60, max ~150).
- **Neighbor cap:** if the focal node has more neighbors than `limit`, keep the
  top `limit` by (max edge confidence to focal, then neighbor
  `connection_count`); `meta.truncated=true` and `meta.total_neighbors` report it.
- **Response model `EgoResponse`:** `{ focal: str, nodes: list[MapNode],
  edges: list[MapEdge], meta: EgoMeta }` where `EgoMeta = { truncated: bool,
  total_neighbors: int, showing: int }`. Reuses `MapNode`/`MapEdge` (community,
  node_type, evidence all already present).
- **Edge cases:** isolate (no neighbors in filter) → focal node only, empty
  edges. Unknown `agent_norm` → 404. Supports `pub:` and Hebrew agent_norms
  (path param `:path`).

A helper picks the default focal node for the "no selection" case:
`GET /network/ego/` is not used; instead the frontend asks `/network/map` (which
it already has) and centers on the highest `connection_count` node — no new
endpoint needed for the default.

## Frontend

New dependency: **`react-force-graph-2d`** (bundles d3-force + canvas;
zoom/pan/labels/click out of the box). Keeps deck.gl for the geo map.

- **`stores/networkStore.ts`** — add `viewMode: 'map' | 'ego'`,
  `focusAgent: string | null`, `egoTrail: {agent_norm, display_name}[]`, plus
  `setViewMode`, `focusEgo(node)` (sets focusAgent + viewMode='ego' + pushes
  trail), `popTrailTo(agent_norm)`.
- **`api/network.ts`** — `fetchEgo(agentNorm, {connectionTypes, minConfidence})`
  → `EgoResponse`; `EgoResponse`/`EgoMeta` types in `types/network.ts`.
- **`components/network/EgoView.tsx`** — wraps `ForceGraph2D`. Nodes colored by
  the same `getAgentColor(node, colorBy, communityColors)` as the map; focal node
  emphasized (ring/size); links colored by `CONNECTION_TYPE_CONFIG`; node label =
  display_name. `onNodeClick` → `selectAgent` + (if not focal) `focusEgo`. Link
  hover tooltip shows relationship/evidence. Shows a "no connections under the
  current filters" hint when only the focal node is present.
- **`components/network/ViewModeToggle`** (small, in ControlBar) — Map/Network
  segmented control bound to `viewMode`.
- **`components/network/Breadcrumbs.tsx`** — renders `egoTrail`; click a crumb →
  `popTrailTo`. Only shown in ego mode.
- **`components/network/AgentPanel.tsx`** — add "Explore connections →" that
  calls `focusEgo(agent)`.
- **`pages/Network.tsx`** — when `viewMode==='ego'`: ensure a focal node
  (selected agent, else the top-connected node from current map data), fetch ego,
  render `EgoView` + `Breadcrumbs`; else render `MapView`. URL state carries
  `view`/`focus` for shareable ego views (extends existing #24 URL sync).

## Consistency

- Coloring facet (`colorBy`, community palette), connection-type filter, and
  min-confidence are shared store state → identical semantics in both views.
- The detail panel, place panel, and search are unchanged and work in both modes.

## Testing

- **Backend (TDD):** induced subgraph includes neighbor↔neighbor edges; category
  excluded; respects connection_types/min_confidence; neighbor cap + truncated
  flag; isolate returns focal-only; unknown agent → 404; Hebrew/`pub:` focal.
- **Frontend:** typecheck + build green; live verification of toggle, click-to-
  recenter, breadcrumbs, and color/filter consistency. (Force-graph canvas
  interactions are validated live, not unit-tested.)

## Out of scope (YAGNI)

Pathfinding (#33), 2-hop expansion (reachable by clicking through), time
animation, minimap, saving/sharing trails beyond URL state.

## Acceptance

- Map/Network toggle switches views over shared filters.
- Clicking a node opens its ego graph; clicking a neighbor re-centers and extends
  the breadcrumb trail; crumbs navigate back.
- Entering Network mode with no selection centers on the most-connected node.
- Ego edges carry relationship/evidence on hover; colors match the map.
