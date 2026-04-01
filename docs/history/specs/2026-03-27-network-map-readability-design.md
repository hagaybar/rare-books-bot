# Network Map Readability — Design Spec (Phase 1 of 3)

**Date**: 2026-03-27
**Status**: Approved

---

## Overview

Transform the Network Map from anonymous blue dots into a readable, color-coded visualization with labels, clustering, and a legend. Phase 1 of a 3-phase UX improvement.

## Problems Solved

1. **Wall of blue** — all dots same color, no visual meaning
2. **No labels** — can't identify agents without hovering each one
3. **City stacking** — multiple agents at same location overlap invisibly
4. Partial: **No legend** — no explanation of what visual encodings mean

## Changes

### 1. Color-by Dropdown

Add a "Color by" dropdown to the control bar with three options:
- **Century** (default) — 15th, 16th, 17th, 18th, 19th, 20th, unknown
- **Role** — author, printer, editor, translator, other
- **Occupation** — top occupations from Wikidata (rabbi, philosopher, historian, etc.)

**Color palettes** (distinct, colorblind-friendly):

Century (based on **birth_year** from Wikidata, labeled "Life Period" in UI to distinguish from the publication-date Century filter):
| Period | Color | Hex |
|--------|-------|-----|
| Before 1400 | Amber | #F59E0B |
| 15th | Orange | #F97316 |
| 16th | Rose | #F43F5E |
| 17th | Purple | #8B5CF6 |
| 18th | Blue | #3B82F6 |
| 19th | Teal | #14B8A6 |
| 20th+ | Green | #22C55E |
| Unknown | Gray | #9CA3AF |

**Fallback**: Agents without birth_year data (~30-40% of agents) get Gray ("Unknown"). This is expected — not all agents have Wikidata enrichment.

Role:
| Role | Color | Hex |
|------|-------|-----|
| Author | Blue | #3B82F6 |
| Printer | Green | #22C55E |
| Editor | Orange | #F97316 |
| Translator | Purple | #8B5CF6 |
| Other | Gray | #9CA3AF |

Occupation: Use the century palette mapped to top 7 occupations (rabbi, philosopher, historian, poet, printer, theologian, other).

**Fallback for all modes**: Agents missing the relevant data (no birth_year, no role, no occupation) are colored Gray (#9CA3AF) and labeled "Unknown" in the legend. Estimated ~30-40% of agents will be gray in Occupation mode (only enriched agents have this data). This is acceptable — gray dots still show geographic distribution, and users can see enrichment gaps.

### 2. Agent Labels

Show text labels on the map for the **top 15 agents by connection count**. Labels appear next to their dot, offset slightly to avoid overlap.

- Font: 11px, semi-bold, dark gray with white text shadow for readability over the map
- Only visible at zoom levels 4-8 (disappear when zoomed too far out or in)
- Labels for remaining agents appear on hover (tooltip, already implemented)

### 3. City Jitter (De-stacking)

When multiple agents share the same city coordinates, apply a **small deterministic jitter** so they spread into a visible cluster rather than stacking on a single pixel.

- Jitter: ±0.03 degrees (~3km) based on a hash of the agent_norm (deterministic — same position every render)
- Agents at a city with 1 agent: no jitter
- Agents at a city with 2+ agents: arranged in a circle pattern around the city center
- This is a coordinate transform in the frontend — no API changes needed

Full cluster badges with click-to-zoom behavior are deferred to a later phase.

### 4. Legend

Add a compact legend overlay in the bottom-left corner of the map:

```
┌─────────────────────┐
│ Color by: [Century▾] │
│ ● 15th  ● 16th      │
│ ● 17th  ● 18th      │
│ ● 19th  ● 20th+     │
│ ○ Unknown            │
│                      │
│ Size = connections   │
└─────────────────────┘
```

- Shows current color-by scheme with colored dots and labels
- "Size = connections" note explaining dot size
- Semi-transparent white background so map shows through
- Collapses to a small icon on mobile
- The "Color by" dropdown lives in the **ControlBar only** (next to existing filters). The legend displays the current scheme name as a label, not a duplicate dropdown.

### 5. Dot Size by Connection Count

Vary dot radius based on the agent's connection count:
- Min: 4px (agents with 1-5 connections)
- Max: 14px (most-connected agents)
- Scale: `4 + Math.min(connection_count / 10, 10)` pixels

This makes hub agents visually prominent without labels.

**Interaction with selection**: When an agent is selected (clicked), use a bright white ring/outline around the dot instead of changing its size. Connected agents get a thinner ring. This preserves the connection-count size while clearly showing selection state. The `connection_count` used for sizing is the **total** from `network_agents` table (not filtered by active connection types).

## API Changes

### Modify `GET /network/map` response

Add `century` and `primary_role` fields to each node (needed for color-by):

```json
{
  "agent_norm": "maimonides, moses",
  "display_name": "Moses Maimonides",
  "lat": 37.88, "lon": -4.77,
  "century": "12th",
  "primary_role": "author",
  "primary_occupation": "philosopher",
  "connection_count": 47,
  ...
}
```

The `century` is derived from `birth_year` (already in network_agents via authority_enrichment). The `primary_role` comes from the most common `role_norm` for this agent. The `primary_occupation` comes from the first occupation in authority_enrichment.person_info.

These can be pre-computed in the `network_agents` table during the build step, or computed at query time with a JOIN.

## Frontend Changes

| File | Change |
|------|--------|
| `frontend/src/components/network/MapView.tsx` | Color dots by selected dimension, vary size, add labels layer, jitter overlapping coords |
| `frontend/src/components/network/ControlBar.tsx` | Add "Color by" dropdown |
| `frontend/src/components/network/Legend.tsx` | New component — color legend overlay |
| `frontend/src/stores/networkStore.ts` | Add `colorBy` state |
| `frontend/src/types/network.ts` | Add century/role/occupation color configs, update MapNode type |
| `app/api/network.py` | Add century, primary_role, primary_occupation to node response |
| `scripts/network/build_network_tables.py` | Add century, primary_role, primary_occupation to network_agents |

## Out of Scope (Phase 2 & 3)

- Page title/description/onboarding (Phase 2)
- Renaming connection types to human language (Phase 2)
- Arc visual hierarchy / progressive disclosure (Phase 3)
- Smart arc rendering to prevent chaos (Phase 3)
