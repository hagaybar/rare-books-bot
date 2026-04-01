# Network Map Phase 2+3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean default (no arcs), human-readable tiered connection types, arc visual hierarchy, category limit, page header, and new "Active in Same City" connection type.

**Architecture:** Add same_place_period edges in build script. Backend handles empty types and category limits. Frontend gets tiered buttons, arc confidence-based rendering, page header, and empty-state messaging.

**Tech Stack:** Python/FastAPI, SQLite, React 19, deck.gl, Zustand, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-27-network-map-phase2-3-design.md`

---

## File Structure

| File | Action |
|------|--------|
| `scripts/network/build_network_tables.py` | Modify — add same_place_period edges |
| `app/api/network.py` | Modify — empty types handling, category limit, new valid type |
| `app/api/network_models.py` | Modify — MapMeta additions |
| `frontend/src/types/network.ts` | Modify — ConnectionType + CONFIG update |
| `frontend/src/stores/networkStore.ts` | Modify — default empty, remove guard |
| `frontend/src/components/network/ControlBar.tsx` | Modify — tiered buttons |
| `frontend/src/components/network/MapView.tsx` | Modify — arc hierarchy + jittered endpoints |
| `frontend/src/pages/Network.tsx` | Modify — header + status bar |

---

### Task 1: Backend — Same Place Period Edges + API Fixes

**Files:**
- Modify: `scripts/network/build_network_tables.py`
- Modify: `app/api/network.py`
- Modify: `app/api/network_models.py`

- [ ] **Step 1: Add _build_same_place_period_edges to build script**

In `scripts/network/build_network_tables.py`, add after `_build_co_publication_edges`:

```python
def _build_same_place_period_edges(conn: sqlite3.Connection) -> int:
    """Find agents active in the same city during overlapping periods (>=10 years)."""
    # For each agent, get their place + date range per place
    agent_places = conn.execute("""
        SELECT a.agent_norm, i.place_norm,
               MIN(i.date_start) as earliest, MAX(i.date_start) as latest
        FROM agents a
        JOIN imprints i ON a.record_id = i.record_id
        WHERE i.place_norm IS NOT NULL AND i.date_start IS NOT NULL
          AND i.place_norm != '[sine loco]'
        GROUP BY a.agent_norm, i.place_norm
        HAVING MAX(i.date_start) - MIN(i.date_start) >= 0
    """).fetchall()

    # Group by place
    from collections import defaultdict
    place_agents = defaultdict(list)
    for norm, place, earliest, latest in agent_places:
        place_agents[place].append((norm, earliest, latest))

    count = 0
    for place, agents in place_agents.items():
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                a1_norm, a1_start, a1_end = agents[i]
                a2_norm, a2_start, a2_end = agents[j]
                # Check overlap of at least 10 years
                overlap_start = max(a1_start, a2_start)
                overlap_end = min(a1_end or a1_start, a2_end or a2_start)
                if overlap_end - overlap_start >= 10:
                    src = min(a1_norm, a2_norm)
                    tgt = max(a1_norm, a2_norm)
                    try:
                        conn.execute(
                            """INSERT OR IGNORE INTO network_edges
                               (source_agent_norm, target_agent_norm, connection_type,
                                confidence, relationship, bidirectional, evidence)
                               VALUES (?, ?, 'same_place_period', 0.70, ?, 1, ?)""",
                            (src, tgt, f"both active in {place}",
                             f"{place}: {overlap_start}-{overlap_end}"),
                        )
                        count += conn.execute("SELECT changes()").fetchone()[0]
                    except sqlite3.IntegrityError:
                        pass
    return count
```

In `build_network_edges`, add call BEFORE the indexes:
```python
    spp_count = _build_same_place_period_edges(conn)
    logger.info("Inserted %d same-place-period connections", spp_count)
```

- [ ] **Step 2: Rebuild network tables**

```bash
poetry run python -m scripts.network.build_network_tables data/index/bibliographic.db data/normalization/place_geocodes.json
```

- [ ] **Step 3: Fix backend — empty types + category limit + new type**

In `app/api/network.py`:

Add `"same_place_period"` to `VALID_CONNECTION_TYPES`.

In `get_network_map()`, handle empty connection_types:
```python
    types = [t.strip() for t in connection_types.split(",") if t.strip()]
    # Handle empty types — return nodes only, no edges
    if not types or types == ['none']:
        # ... fetch agents without edge filtering, return empty edges
```

For category limit, in the edge query section, when building the edge SQL:
```python
    # Apply category limit
    edge_queries = []
    for t in types:
        if t == 'category':
            edge_queries.append(f"""
                SELECT * FROM (
                    SELECT source_agent_norm, target_agent_norm, connection_type,
                           confidence, relationship, bidirectional
                    FROM network_edges
                    WHERE connection_type = 'category'
                      AND confidence >= ?
                      AND source_agent_norm IN ({norm_placeholders})
                      AND target_agent_norm IN ({norm_placeholders})
                    ORDER BY confidence DESC
                    LIMIT 100
                )
            """)
        else:
            # normal query for this type
```

In `app/api/network_models.py`, add to MapMeta:
```python
    category_limited: bool = False
    category_total: int = 0
```

- [ ] **Step 4: Test**

```bash
# Empty types — should return nodes, no edges
curl -s 'http://localhost:8000/network/map?connection_types=none&limit=5' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Nodes: {len(d[\"nodes\"])}, Edges: {len(d[\"edges\"])}')"

# Same place period
curl -s 'http://localhost:8000/network/map?connection_types=same_place_period&limit=10' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Edges: {len(d[\"edges\"])}')"

# Category limited
curl -s 'http://localhost:8000/network/map?connection_types=category&limit=50' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Edges: {len(d[\"edges\"])}, limited: {d[\"meta\"].get(\"category_limited\",False)}')"
```

- [ ] **Step 5: Commit**

```bash
git add scripts/network/build_network_tables.py app/api/network.py app/api/network_models.py
git commit -m "feat: same_place_period edges, empty types handling, category limit"
```

---

### Task 2: Frontend Types + Store

**Files:**
- Modify: `frontend/src/types/network.ts`
- Modify: `frontend/src/stores/networkStore.ts`

- [ ] **Step 1: Update ConnectionType and CONFIG**

In `frontend/src/types/network.ts`:

Update `ConnectionType` union:
```typescript
export type ConnectionType =
  | 'teacher_student'
  | 'wikilink'
  | 'llm_extraction'
  | 'category'
  | 'co_publication'
  | 'same_place_period';
```

Replace `CONNECTION_TYPE_CONFIG`:
```typescript
export const CONNECTION_TYPE_CONFIG: Record<ConnectionType, {
  label: string;
  color: [number, number, number];
  width: number;
  tier: 'primary' | 'secondary';
}> = {
  teacher_student: { label: 'Teacher & Student', color: [59, 130, 246], width: 3, tier: 'primary' },
  co_publication: { label: 'Published Together', color: [16, 185, 129], width: 2, tier: 'primary' },
  same_place_period: { label: 'Active in Same City', color: [6, 182, 212], width: 2, tier: 'primary' },
  wikilink: { label: 'Mentioned Together', color: [245, 158, 11], width: 2, tier: 'primary' },
  llm_extraction: { label: 'AI-Discovered', color: [139, 92, 246], width: 2, tier: 'secondary' },
  category: { label: 'Shared Topics', color: [156, 163, 175], width: 1, tier: 'secondary' },
};
```

- [ ] **Step 2: Update store**

In `frontend/src/stores/networkStore.ts`:

Change default:
```typescript
  connectionTypes: [] as ConnectionType[],
```

Remove the deselect guard in `toggleConnectionType`:
```typescript
  toggleConnectionType: (type) =>
    set((state) => {
      const exists = state.connectionTypes.includes(type);
      return {
        connectionTypes: exists
          ? state.connectionTypes.filter((t) => t !== type)
          : [...state.connectionTypes, type],
      };
    }),
```

- [ ] **Step 3: Update API client for empty types**

In `frontend/src/api/network.ts`, in `fetchMapData`:
```typescript
  // Handle empty connection types
  if (params.connectionTypes.length === 0) {
    qs.set('connection_types', 'none');
  } else {
    qs.set('connection_types', params.connectionTypes.join(','));
  }
```

- [ ] **Step 4: Verify**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/network.ts frontend/src/stores/networkStore.ts frontend/src/api/network.ts
git commit -m "feat: 6 connection types with tiers, empty default, remove deselect guard"
```

---

### Task 3: Frontend Components — Tiered Buttons, Arc Hierarchy, Header

**Files:**
- Modify: `frontend/src/components/network/ControlBar.tsx`
- Modify: `frontend/src/components/network/MapView.tsx`
- Modify: `frontend/src/pages/Network.tsx`

- [ ] **Step 1: Update ControlBar with tiered buttons**

In `frontend/src/components/network/ControlBar.tsx`, replace the connection type buttons section with tiered layout:

```tsx
      {/* Connection type toggles — tiered */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-medium text-gray-700">Connections:</span>
        {(Object.entries(CONNECTION_TYPE_CONFIG) as [ConnectionType, typeof CONNECTION_TYPE_CONFIG[ConnectionType]][])
          .filter(([, config]) => config.tier === 'primary')
          .map(([type, config]) => {
            const active = connectionTypes.includes(type);
            const [r, g, b] = config.color;
            return (
              <button
                key={type}
                onClick={() => toggleConnectionType(type)}
                className={`px-2 py-1 text-xs rounded border transition-colors ${
                  active
                    ? 'text-white border-transparent'
                    : 'text-gray-500 border-gray-300 bg-white hover:bg-gray-50'
                }`}
                style={active ? { backgroundColor: `rgb(${r},${g},${b})` } : undefined}
              >
                {config.label}
              </button>
            );
          })}
        <span className="text-gray-300">|</span>
        <span className="text-xs text-gray-400">More:</span>
        {(Object.entries(CONNECTION_TYPE_CONFIG) as [ConnectionType, typeof CONNECTION_TYPE_CONFIG[ConnectionType]][])
          .filter(([, config]) => config.tier === 'secondary')
          .map(([type, config]) => {
            const active = connectionTypes.includes(type);
            const [r, g, b] = config.color;
            return (
              <button
                key={type}
                onClick={() => toggleConnectionType(type)}
                className={`px-1.5 py-0.5 text-xs rounded border transition-colors ${
                  active
                    ? 'text-white border-transparent'
                    : 'text-gray-400 border-gray-200 bg-white hover:bg-gray-50'
                }`}
                style={active ? { backgroundColor: `rgb(${r},${g},${b})` } : undefined}
              >
                {config.label}
              </button>
            );
          })}
      </div>
```

- [ ] **Step 2: Update MapView arc rendering**

In `frontend/src/components/network/MapView.tsx`, update the arcLayer:

Change `getSourcePosition` and `getTargetPosition` to use jitteredPositions:
```typescript
        getSourcePosition: (d) => {
          return jitteredPositions.get(d.source) ?? (() => {
            const n = nodeMap.get(d.source);
            return [n?.lon ?? 0, n?.lat ?? 0];
          })();
        },
        getTargetPosition: (d) => {
          return jitteredPositions.get(d.target) ?? (() => {
            const n = nodeMap.get(d.target);
            return [n?.lon ?? 0, n?.lat ?? 0];
          })();
        },
```

Update `getSourceColor`/`getTargetColor` for confidence-based opacity:
```typescript
        getSourceColor: (d) => {
          const config = CONNECTION_TYPE_CONFIG[d.type as keyof typeof CONNECTION_TYPE_CONFIG];
          const baseColor = config?.color ?? [156, 163, 175];
          const isHighlighted = selectedAgent && (d.source === selectedAgent || d.target === selectedAgent);
          let opacity: number;
          if (selectedAgent) {
            opacity = isHighlighted ? Math.round(d.confidence * 255) : 25;
          } else {
            // Confidence-based opacity
            opacity = d.confidence >= 0.8 ? 200 : d.confidence >= 0.6 ? 130 : 60;
          }
          return [...baseColor, opacity] as [number, number, number, number];
        },
```

Update `getWidth` for confidence-based width:
```typescript
        getWidth: (d) => {
          const config = CONNECTION_TYPE_CONFIG[d.type as keyof typeof CONNECTION_TYPE_CONFIG];
          // Confidence-based width
          const base = d.confidence >= 0.8 ? 3 : d.confidence >= 0.6 ? 2 : 1;
          if (selectedAgent && (d.source === selectedAgent || d.target === selectedAgent))
            return base * 2;
          return base;
        },
```

- [ ] **Step 3: Update Network.tsx — header + status bar**

In `frontend/src/pages/Network.tsx`:

Add page header before ControlBar:
```tsx
      {/* Page header */}
      <div className="px-4 pt-3 pb-1">
        <h1 className="text-xl font-semibold text-gray-900">Scholarly Network Map</h1>
        <p className="text-sm text-gray-500">
          Explore connections between {mapData?.meta.total_agents?.toLocaleString() ?? '...'} historical figures across Europe and the Middle East
        </p>
      </div>
```

Update status bar for empty connections state:
```tsx
      <div className="px-4 py-2 bg-gray-50 border-t text-sm text-gray-500 flex justify-between">
        <span>
          {mapData
            ? connectionTypes.length === 0
              ? `Showing ${mapData.meta.showing} of ${mapData.meta.total_agents} agents \u00B7 Select connection types to see relationships`
              : `Showing ${mapData.meta.showing} of ${mapData.meta.total_agents} agents \u00B7 ${mapData.meta.total_edges} connections${mapData.meta.category_limited ? ` (Shared Topics limited to top 100 of ${mapData.meta.category_total})` : ''}`
            : 'Loading...'}
        </span>
        {isLoading && <span className="text-blue-500">Updating...</span>}
      </div>
```

Need to import `connectionTypes` from the store at the top of the component.

- [ ] **Step 4: Verify and build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

- [ ] **Step 5: Commit and push**

```bash
git add frontend/src/
git commit -m "feat: tiered connection buttons, arc visual hierarchy, page header, empty state"
git push origin main
```
