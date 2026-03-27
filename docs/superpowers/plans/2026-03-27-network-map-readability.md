# Network Map Readability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Network Map from anonymous blue dots into a readable, color-coded visualization with labels, city jitter, dot sizing, and a legend.

**Architecture:** Add `primary_role` to network_agents table + API. Frontend gets color-by state in Zustand store, color palette configs in types, MapView applies color/size/jitter/labels via deck.gl layers, new Legend component overlays the map.

**Tech Stack:** Python/FastAPI, SQLite, React 19, deck.gl, Zustand, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-27-network-map-readability-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/network/build_network_tables.py` | Modify | Add `primary_role` column to network_agents |
| `app/api/network.py` | Modify | Include `primary_role` in node response |
| `frontend/src/types/network.ts` | Modify | Add color palettes, ColorByMode type, update MapNode |
| `frontend/src/stores/networkStore.ts` | Modify | Add `colorBy` state |
| `frontend/src/components/network/ControlBar.tsx` | Modify | Add "Color by" dropdown |
| `frontend/src/components/network/MapView.tsx` | Modify | Color dots, size by connections, jitter, labels |
| `frontend/src/components/network/Legend.tsx` | Create | Color legend overlay |
| `frontend/src/pages/Network.tsx` | Modify | Pass colorBy to MapView, render Legend |

---

### Task 1: Add primary_role to Backend

**Files:**
- Modify: `scripts/network/build_network_tables.py`
- Modify: `app/api/network.py`

- [ ] **Step 1: Add primary_role to network_agents table**

In `scripts/network/build_network_tables.py`, in the `build_network_agents` function, add `primary_role` column to the CREATE TABLE statement (after `occupations`):

```python
    primary_role TEXT,
```

Then compute primary_role during the agent loop — after the `record_count` query, add:

```python
        # Primary role (most common role for this agent)
        role_row = conn.execute(
            "SELECT role_norm, count(*) as cnt FROM agents WHERE agent_norm = ? AND role_norm IS NOT NULL GROUP BY role_norm ORDER BY cnt DESC LIMIT 1",
            (agent_norm,),
        ).fetchone()
        primary_role = role_row[0] if role_row else None
```

And include it in the INSERT statement.

- [ ] **Step 2: Rebuild network tables**

```bash
poetry run python -m scripts.network.build_network_tables data/index/bibliographic.db data/normalization/place_geocodes.json
```

Verify: `python3 -c "import sqlite3; c=sqlite3.connect('data/index/bibliographic.db'); r=c.execute('SELECT primary_role, count(*) FROM network_agents WHERE primary_role IS NOT NULL GROUP BY primary_role ORDER BY count(*) DESC LIMIT 10').fetchall(); print(r)"`

- [ ] **Step 3: Add primary_role to API response**

In `app/api/network.py`, in `get_network_map()`, add `primary_role` to the MapNode construction. The column is already in the SELECT * from network_agents.

In `app/api/network_models.py`, add to MapNode:
```python
    primary_role: str | None = None
```

- [ ] **Step 4: Commit**

```bash
git add scripts/network/build_network_tables.py app/api/network.py app/api/network_models.py
git commit -m "feat: add primary_role to network_agents and API response"
```

---

### Task 2: Frontend Types + Color Palettes + Store

**Files:**
- Modify: `frontend/src/types/network.ts`
- Modify: `frontend/src/stores/networkStore.ts`

- [ ] **Step 1: Update types with color configs**

In `frontend/src/types/network.ts`:

Add `primary_role` to MapNode:
```typescript
export interface MapNode {
  agent_norm: string;
  display_name: string;
  lat: number | null;
  lon: number | null;
  place_norm: string | null;
  birth_year: number | null;
  death_year: number | null;
  occupations: string[];
  connection_count: number;
  has_wikipedia: boolean;
  primary_role: string | null;  // NEW
}
```

Add color-by types and palettes:
```typescript
export type ColorByMode = 'century' | 'role' | 'occupation';

export const CENTURY_COLORS: Record<string, [number, number, number]> = {
  'Before 1400': [245, 158, 11],
  '15th': [249, 115, 22],
  '16th': [244, 63, 94],
  '17th': [139, 92, 246],
  '18th': [59, 130, 246],
  '19th': [20, 184, 166],
  '20th+': [34, 197, 94],
  'Unknown': [156, 163, 175],
};

export const ROLE_COLORS: Record<string, [number, number, number]> = {
  'author': [59, 130, 246],
  'printer': [34, 197, 94],
  'editor': [249, 115, 22],
  'translator': [139, 92, 246],
  'other': [156, 163, 175],
};

export const OCCUPATION_COLORS: Record<string, [number, number, number]> = {
  'rabbi': [245, 158, 11],
  'philosopher': [249, 115, 22],
  'historian': [244, 63, 94],
  'poet': [139, 92, 246],
  'printer': [59, 130, 246],
  'theologian': [20, 184, 166],
  'other': [156, 163, 175],
};

export function getCenturyLabel(birthYear: number | null): string {
  if (birthYear == null) return 'Unknown';
  if (birthYear < 1400) return 'Before 1400';
  if (birthYear < 1500) return '15th';
  if (birthYear < 1600) return '16th';
  if (birthYear < 1700) return '17th';
  if (birthYear < 1800) return '18th';
  if (birthYear < 1900) return '19th';
  return '20th+';
}

export function getAgentColor(node: MapNode, colorBy: ColorByMode): [number, number, number] {
  switch (colorBy) {
    case 'century':
      return CENTURY_COLORS[getCenturyLabel(node.birth_year)] ?? CENTURY_COLORS['Unknown'];
    case 'role':
      return ROLE_COLORS[node.primary_role ?? 'other'] ?? ROLE_COLORS['other'];
    case 'occupation': {
      const occ = node.occupations[0] ?? 'other';
      return OCCUPATION_COLORS[occ] ?? OCCUPATION_COLORS['other'];
    }
  }
}
```

- [ ] **Step 2: Add colorBy to store**

In `frontend/src/stores/networkStore.ts`, add:

```typescript
import type { ConnectionType, ColorByMode } from '../types/network';
```

Add to the interface:
```typescript
  colorBy: ColorByMode;
  setColorBy: (mode: ColorByMode) => void;
```

Add to DEFAULT_STATE:
```typescript
  colorBy: 'century' as ColorByMode,
```

Add to the create function:
```typescript
  setColorBy: (mode) => set({ colorBy: mode }),
```

- [ ] **Step 3: Verify compilation**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/network.ts frontend/src/stores/networkStore.ts
git commit -m "feat: add color-by palettes, helper functions, and store state"
```

---

### Task 3: MapView — Color, Size, Jitter, Labels

**Files:**
- Modify: `frontend/src/components/network/MapView.tsx`

This is the core visual change.

- [ ] **Step 1: Update MapView props and imports**

Add `colorBy` to Props:
```typescript
import { CONNECTION_TYPE_CONFIG, getAgentColor } from '../../types/network';
import type { MapNode, MapEdge, ColorByMode } from '../../types/network';

interface Props {
  nodes: MapNode[];
  edges: MapEdge[];
  selectedAgent: string | null;
  onAgentClick: (node: MapNode) => void;
  onBackgroundClick: () => void;
  isLoading: boolean;
  colorBy: ColorByMode;  // NEW
}
```

- [ ] **Step 2: Add jitter function**

Inside the component, add a deterministic jitter function:
```typescript
  // Deterministic jitter for agents sharing the same city
  const jitteredPositions = useMemo(() => {
    const cityGroups = new globalThis.Map<string, MapNode[]>();
    for (const n of nodes) {
      const key = `${n.lat},${n.lon}`;
      if (!cityGroups.has(key)) cityGroups.set(key, []);
      cityGroups.get(key)!.push(n);
    }
    const positions = new globalThis.Map<string, [number, number]>();
    for (const [, group] of cityGroups) {
      if (group.length === 1) {
        positions.set(group[0].agent_norm, [group[0].lon ?? 0, group[0].lat ?? 0]);
      } else {
        const cx = group[0].lon ?? 0;
        const cy = group[0].lat ?? 0;
        const radius = Math.min(0.03 * Math.sqrt(group.length), 0.3);
        group.forEach((n, i) => {
          const angle = (2 * Math.PI * i) / group.length;
          positions.set(n.agent_norm, [
            cx + radius * Math.cos(angle),
            cy + radius * Math.sin(angle),
          ]);
        });
      }
    }
    return positions;
  }, [nodes]);
```

- [ ] **Step 3: Update ScatterplotLayer**

Replace the existing scatterLayer with color-by support and connection-count sizing:
```typescript
  const scatterLayer = useMemo(
    () =>
      new ScatterplotLayer<MapNode>({
        id: 'agents',
        data: nodes,
        getPosition: (d) => jitteredPositions.get(d.agent_norm) ?? [d.lon ?? 0, d.lat ?? 0],
        getRadius: (d) => {
          const base = 4 + Math.min(d.connection_count / 10, 10);
          return base;
        },
        getFillColor: (d) => {
          const color = getAgentColor(d, colorBy);
          if (d.agent_norm === selectedAgent) return [...color, 255];
          if (selectedAgent && connectedAgents.has(d.agent_norm)) return [...color, 220];
          if (selectedAgent) return [156, 163, 175, 50]; // fade non-connected
          return [...color, 200];
        },
        getLineColor: (d) => {
          if (d.agent_norm === selectedAgent) return [255, 255, 255, 255];
          if (selectedAgent && connectedAgents.has(d.agent_norm)) return [255, 255, 255, 180];
          return [0, 0, 0, 0];
        },
        getLineWidth: (d) => {
          if (d.agent_norm === selectedAgent) return 2;
          if (selectedAgent && connectedAgents.has(d.agent_norm)) return 1;
          return 0;
        },
        stroked: true,
        lineWidthUnits: 'pixels',
        radiusUnits: 'pixels',
        pickable: true,
        onClick: (info) => {
          if (info.object) {
            pickedRef.current = true;
            onAgentClick(info.object);
          }
        },
        updateTriggers: {
          getRadius: [selectedAgent],
          getFillColor: [selectedAgent, colorBy],
          getLineColor: [selectedAgent],
          getLineWidth: [selectedAgent],
        },
      }),
    [nodes, selectedAgent, connectedAgents, onAgentClick, colorBy, jitteredPositions]
  );
```

- [ ] **Step 4: Add TextLayer for labels (top 15 agents)**

Add import:
```typescript
import { ArcLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
```

Add labels layer:
```typescript
  const labelNodes = useMemo(() => {
    return [...nodes]
      .sort((a, b) => b.connection_count - a.connection_count)
      .slice(0, 15);
  }, [nodes]);

  const labelLayer = useMemo(
    () =>
      new TextLayer<MapNode>({
        id: 'labels',
        data: labelNodes,
        getPosition: (d) => jitteredPositions.get(d.agent_norm) ?? [d.lon ?? 0, d.lat ?? 0],
        getText: (d) => d.display_name,
        getSize: 12,
        getColor: [50, 50, 50, 220],
        getAngle: 0,
        getTextAnchor: 'start',
        getAlignmentBaseline: 'center',
        getPixelOffset: [10, 0],
        fontFamily: 'Inter, system-ui, sans-serif',
        fontWeight: 600,
        outlineWidth: 3,
        outlineColor: [255, 255, 255, 200],
        billboard: false,
        sizeUnits: 'pixels',
      }),
    [labelNodes, jitteredPositions]
  );
```

Update the DeckGL layers prop:
```typescript
  layers={[arcLayer, scatterLayer, labelLayer]}
```

- [ ] **Step 5: Verify compilation**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/network/MapView.tsx
git commit -m "feat: color-coded dots, connection-count sizing, city jitter, agent labels"
```

---

### Task 4: ControlBar — Color-by Dropdown

**Files:**
- Modify: `frontend/src/components/network/ControlBar.tsx`

- [ ] **Step 1: Add the Color-by dropdown**

Add import:
```typescript
import type { ColorByMode } from '../../types/network';
```

Add to the store destructure:
```typescript
  const { ..., colorBy, setColorBy } = useNetworkStore();
```

Add the dropdown in the control bar (before the Connections label):
```tsx
      {/* Color by */}
      <div className="flex items-center gap-1">
        <span className="text-sm text-gray-600">Color by:</span>
        <select
          value={colorBy}
          onChange={(e) => setColorBy(e.target.value as ColorByMode)}
          className="text-sm border border-gray-300 rounded px-2 py-1"
        >
          <option value="century">Life Period</option>
          <option value="role">Role</option>
          <option value="occupation">Occupation</option>
        </select>
      </div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/network/ControlBar.tsx
git commit -m "feat: add Color-by dropdown to network control bar"
```

---

### Task 5: Legend Component

**Files:**
- Create: `frontend/src/components/network/Legend.tsx`
- Modify: `frontend/src/pages/Network.tsx`

- [ ] **Step 1: Create Legend component**

Create `frontend/src/components/network/Legend.tsx`:

```tsx
import type { ColorByMode } from '../../types/network';
import { CENTURY_COLORS, ROLE_COLORS, OCCUPATION_COLORS } from '../../types/network';

interface Props {
  colorBy: ColorByMode;
}

const PALETTES: Record<ColorByMode, { label: string; entries: Record<string, [number, number, number]> }> = {
  century: { label: 'Life Period', entries: CENTURY_COLORS },
  role: { label: 'Role', entries: ROLE_COLORS },
  occupation: { label: 'Occupation', entries: OCCUPATION_COLORS },
};

export default function Legend({ colorBy }: Props) {
  const palette = PALETTES[colorBy];

  return (
    <div className="absolute bottom-12 left-3 bg-white/90 backdrop-blur-sm rounded-lg shadow-md px-3 py-2 z-10 text-xs">
      <div className="font-semibold text-gray-700 mb-1">{palette.label}</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {Object.entries(palette.entries).map(([label, color]) => (
          <div key={label} className="flex items-center gap-1.5">
            <span
              className="w-2.5 h-2.5 rounded-full inline-block flex-shrink-0"
              style={{ backgroundColor: `rgb(${color[0]},${color[1]},${color[2]})` }}
            />
            <span className="text-gray-600">{label}</span>
          </div>
        ))}
      </div>
      <div className="mt-1 text-gray-400 border-t pt-1">Size = connections</div>
    </div>
  );
}
```

- [ ] **Step 2: Wire Legend and colorBy into Network page**

In `frontend/src/pages/Network.tsx`:

Add imports:
```typescript
import Legend from '../components/network/Legend';
import { useNetworkStore } from '../stores/networkStore';
```

Inside the component, get colorBy:
```typescript
  const { colorBy } = useNetworkStore();
```

Pass colorBy to MapView:
```tsx
  <MapView
    ...
    colorBy={colorBy}
  />
```

Add Legend inside the map container div (sibling to MapView):
```tsx
  <div className="flex-1 relative">
    <MapView ... />
    <Legend colorBy={colorBy} />
    {/* empty state overlay */}
  </div>
```

- [ ] **Step 3: Verify and build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

- [ ] **Step 4: Commit and push**

```bash
git add frontend/src/components/network/Legend.tsx frontend/src/pages/Network.tsx
git commit -m "feat: add color legend overlay to Network Map"
git push origin main
```
