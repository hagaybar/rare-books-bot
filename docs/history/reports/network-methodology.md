# Scholarly Network Map: Methodology Report

This report documents how the Scholarly Network Map is constructed, served, and rendered. It is based on a direct reading of the codebase and live data queries against `data/index/bibliographic.db` as of 2026-03-27.

---

## 1. Network Construction

The build process is implemented in `scripts/network/build_network_tables.py` and executed via:

```bash
python -m scripts.network.build_network_tables data/index/bibliographic.db data/normalization/place_geocodes.json
```

The `main()` function runs these steps in strict order:

### Step 1: Build edges (`build_network_edges`)
1. Drops and recreates the `network_edges` table.
2. Inserts edges from four sources (details in Section 2 below):
   - Wikipedia connections (wikilink, llm_extraction, category) -- bulk `INSERT OR IGNORE` from `wikipedia_connections` table
   - Teacher/student -- extracted from `authority_enrichment.person_info` JSON
   - Co-publication -- SQL join finding agent pairs sharing >= 2 records
   - Same-place-period -- Python loop finding agents with >= 10-year overlap in the same city
3. Creates indexes on `source_agent_norm`, `target_agent_norm`, and `connection_type`.

### Step 2: Build agents (`build_network_agents`)
1. Drops and recreates the `network_agents` table.
2. Iterates over every distinct `agent_norm` from the `agents` table (3,102 total).
3. For each agent, resolves:
   - `display_name` via a 3-level fallback chain (see `resolve_display_name`):
     - Level 1: `agent_authorities.canonical_name` via `agent_aliases`
     - Level 2: `authority_enrichment.label` (stripped of disambiguation suffixes like "(DNB12)")
     - Level 3: Title-cased `agent_norm` (e.g., "maimonides, moses" becomes "Maimonides, Moses")
   - `place_norm` / `lat` / `lon`: Most frequent publication place from `imprints`, with tiebreaks by earliest `date_start` then alphabetical. The first candidate that has a geocode entry wins. Places matching `[sine loco]` are excluded.
   - `birth_year`, `death_year`, `occupations`: Parsed from `authority_enrichment.person_info` JSON.
   - `has_wikipedia`: 1 if the agent's wikidata_id is found in `wikipedia_cache`, else 0.
   - `record_count`: `COUNT(DISTINCT record_id)` from `agents` table.
   - `primary_role`: Most frequent `role_norm` from `agents` table for this `agent_norm`.
   - `connection_count`: Count of edges in `network_edges` where this agent appears as source or target.
4. **Critical gate**: If no geocoded place is found for an agent, that agent is **excluded entirely** from `network_agents`. This excluded 388 of 3,102 agents, leaving 2,714 in the table.

### Step 3: Post-build cleanup
1. **Merge duplicate agents** (`_merge_duplicate_agents`): See Section 3.
2. **Remove orphan edges** (`_cleanup_orphan_edges`): Deletes edges where either endpoint is not in `network_agents`.
3. **Recompute connection counts** (`_recompute_connection_counts`): Updates `connection_count` for all agents after merges and orphan removal.
4. Commit.

### Current data counts (live)

| Metric | Value |
|--------|-------|
| Total edges | 28,945 |
| Total agents in network_agents | 2,714 |
| Agents with connections > 0 | 1,284 |
| Agents with birth_year | 1,603 |
| Agents with primary_role | 2,714 (all) |
| Orphan edges | 0 |
| Self-referencing edges | 0 |

---

## 2. Connection Types

Six connection types exist. They fall into two tiers in the UI (defined in `CONNECTION_TYPE_CONFIG` in `frontend/src/types/network.ts`):

- **Primary**: teacher_student, co_publication, same_place_period, wikilink
- **Secondary**: llm_extraction, category

### 2.1. `category` -- Shared Topics

| Metric | Value |
|--------|-------|
| Edge count | 22,132 |
| Confidence | fixed 0.65 (avg=0.65, min=0.65, max=0.65) |
| Bidirectional | No (stored as 0) |
| Source table | `wikipedia_connections` where `source_type = 'category'` |

**How computed**: Pre-built in the Wikipedia enrichment pipeline and stored in `wikipedia_connections`. Agents that share Wikipedia categories are linked. All category edges have a flat confidence of 0.65.

**Note on volume**: This is by far the largest edge type (76.5% of all edges). The API applies a hard `LIMIT 100` on category edges specifically (see Section 7).

### 2.2. `wikilink` -- Mentioned Together

| Metric | Value |
|--------|-------|
| Edge count | 6,190 |
| Confidence | avg=0.80, min=0.75, max=0.90 |
| Bidirectional | Mixed (4,169 unidirectional, 2,021 bidirectional) |
| Source table | `wikipedia_connections` where `source_type = 'wikilink'` |

**How computed**: Pre-built in the Wikipedia enrichment pipeline. Agents whose Wikipedia articles hyperlink to each other. Bidirectionality means both articles link to each other. Confidence varies (0.75 to 0.90).

### 2.3. `same_place_period` -- Active in Same City

| Metric | Value |
|--------|-------|
| Edge count | 438 |
| Confidence | fixed 0.70 |
| Bidirectional | Yes (all) |
| Source | Computed from `agents` + `imprints` tables |

**How computed** (`_build_same_place_period_edges`):
1. Queries each `(agent_norm, place_norm)` pair from `agents JOIN imprints`, getting `MIN(date_start)` as earliest and `MAX(date_start)` as latest. Excludes `[sine loco]` and null places/dates.
2. Groups agents by place.
3. For each pair of agents in the same place, checks if `min(a1_end, a2_end) - max(a1_start, a2_start) >= 10` (at least 10-year overlap).
4. Source and target are ordered alphabetically (`min(a1, a2)` as source) to ensure deterministic dedup.
5. Evidence string is stored as `"{place}: {overlap_start}-{overlap_end}"`.

**Ambiguity**: The "end" of an agent's activity period is `MAX(date_start)`, not a true "last active" date. An agent with a single publication in a city gets `earliest = latest`, which means the overlap formula uses `latest - overlap_start` which could be 0. The `HAVING` clause only requires `MAX - MIN >= 0`, so even a single record qualifies an agent for the place. Two agents each with a single record in the same city would have `overlap_end - overlap_start = min(latest1, latest2) - max(earliest1, earliest2)`, which would need to be >= 10.

### 2.4. `co_publication` -- Published Together

| Metric | Value |
|--------|-------|
| Edge count | 96 |
| Confidence | min=0.40, max=1.00 (formula: `MIN(shared_records / 5.0, 1.0)`) |
| Bidirectional | Yes (all) |
| Source | Computed from `agents` table self-join |

**How computed** (`_build_co_publication_edges`):
1. Self-joins `agents a1 JOIN agents a2 ON a1.record_id = a2.record_id AND a1.agent_norm < a2.agent_norm`.
2. Groups by agent pair, requires `COUNT(DISTINCT record_id) >= 2`.
3. Confidence = `MIN(count_shared / 5.0, 1.0)`. So 2 shared records = 0.40, 3 = 0.60, 4 = 0.80, 5+ = 1.00.

**Actual distribution**: 73 edges at 0.4 (2 records), 17 at 0.6 (3 records), 4 at 0.8 (4 records), 2 at 1.0 (5+ records).

### 2.5. `teacher_student` -- Teacher/Student

| Metric | Value |
|--------|-------|
| Edge count | 48 |
| Confidence | fixed 0.85 |
| Bidirectional | No |
| Source | `authority_enrichment.person_info` JSON |

**How computed** (`_build_teacher_student_edges`):
1. Reads all `authority_enrichment` rows with `person_info`.
2. Parses JSON to extract `teachers` and `students` arrays.
3. For `teachers`: edge direction is `teacher_norm -> source_norm` (teacher teaches student), relationship = "teacher of".
4. For `students`: edge direction is `source_norm -> student_norm` (source teaches student), relationship = "teacher of".
5. Name resolution via `_resolve_name_to_agent_norm`:
   - Direct match on `agent_norm`
   - Alias lookup through `agent_aliases` to find sibling aliases
   - Partial match: tries "last, first" reordering for multi-word names
6. Self-edges are explicitly prevented (`teacher_norm != source_norm`).

**Example edges**: Plato -> Aristotle, Colet -> Erasmus, Cappel -> Bochart.

### 2.6. `llm_extraction` -- AI-Discovered

| Metric | Value |
|--------|-------|
| Edge count | 41 |
| Confidence | avg=0.83, min=0.60, max=1.00 |
| Bidirectional | No |
| Source table | `wikipedia_connections` where `source_type = 'llm_extraction'` |

**How computed**: Pre-built in the Wikipedia enrichment pipeline. An LLM reads Wikipedia articles and extracts relationships not captured by hyperlinks or categories. Confidence varies per extraction.

---

## 3. Agent Deduplication

The function `_merge_duplicate_agents` handles cases where the same historical person appears under multiple `agent_norm` values (e.g., a Hebrew form and a Latin form) that map to the same Wikidata entity.

### Process

1. Queries all `(agent_norm, wikidata_id)` pairs from `agents JOIN authority_enrichment`.
2. Groups by `wikidata_id`. Skips groups with only one norm.
3. For each multi-norm group, picks the **canonical norm** as the one with the highest `COUNT(DISTINCT record_id)`.
4. For each non-canonical norm:
   - `UPDATE OR IGNORE` all edges to use the canonical norm (both source and target).
   - `DELETE` any leftover edges still referencing the old norm (these would be duplicates that couldn't be updated due to the UNIQUE constraint).
5. Deduplicates edges: keeps only the row with the minimum `rowid` per `(source_agent_norm, target_agent_norm, connection_type)` triple.
6. Deletes self-referencing edges (which can arise from merging).
7. Deletes the non-canonical agent from `network_agents`.

### What is "canonical form"?

The `agent_norm` itself is always a lowercased string in "last, first" format (e.g., `"maimonides, moses"` or in Hebrew script). The canonical form among duplicates is whichever variant has the most records. The display name is resolved separately via `resolve_display_name`.

### Limitation

Deduplication depends entirely on `wikidata_id` linkage through `authority_enrichment`. Agents without authority enrichment or without Wikidata IDs will not be merged even if they are the same person. There is no fuzzy name matching during dedup.

---

## 4. Roles

### How roles are determined

Each agent's `primary_role` is the most frequent `role_norm` value in the `agents` table (per-record role assignments, e.g., "author", "printer", "editor"). The SQL:

```sql
SELECT role_norm, count(*) as cnt FROM agents
WHERE agent_norm = ? AND role_norm IS NOT NULL
GROUP BY role_norm ORDER BY cnt DESC LIMIT 1
```

### Current distribution (top 5)

| Role | Count |
|------|-------|
| author | 1,411 |
| other | 1,119 |
| creator | 50 |
| printer | 36 |
| editor | 30 |

All 2,714 agents have a `primary_role` value.

### Effect on connections

Roles **do not affect** which edges are created. No edge-building function considers the agent's role.

### Effect on appearance

Roles affect appearance in two ways:
1. **Color by Role mode**: The frontend offers a "Color by: Role" option in `ControlBar`. When selected, `getAgentColor` in `types/network.ts` maps the `primary_role` to a color using `ROLE_COLORS`: author=blue, printer=green, editor=orange, translator=purple, everything else=gray.
2. **API filtering**: The API's `role` query parameter filters agents by role via a subquery: `SELECT DISTINCT agent_norm FROM agents WHERE role_norm = ?`. This filters which agents appear on the map but does not filter edges independently.

### "Other" role ambiguity

The `other` role (1,119 agents, 41% of total) is a catch-all. In the frontend's `ROLES` array, the selectable roles are: author, printer, publisher, editor, translator. The `primary_role` values in the database include additional values like `creator`, `illustrator`, `artist`, `former_owner`, etc. -- these are not selectable in the dropdown but do appear when "All Roles" is selected.

---

## 5. Time Spans

### How time is stored

Each agent in `network_agents` has `birth_year` and `death_year` (nullable integers). These come from `authority_enrichment.person_info` JSON. Currently 1,603 of 2,714 agents have a `birth_year`.

### Birth year distribution

| Period | Count |
|--------|-------|
| Before 1400 | 74 |
| 15th century | 117 |
| 16th century | 369 |
| 17th century | 291 |
| 18th century | 349 |
| 19th century | 359 |
| 20th century+ | 44 |
| Unknown (null) | 1,111 |

### Time as a filter

The API accepts a `century` parameter (integer, e.g., 16 for the 1500s). When provided, it filters agents via:

```sql
na.agent_norm IN (
    SELECT DISTINCT a.agent_norm FROM agents a
    JOIN imprints i ON a.record_id = i.record_id
    WHERE i.date_start >= ? AND i.date_start <= ?
)
```

where `year_start = (century - 1) * 100` and `year_end = year_start + 99`. So century=16 filters to `date_start` between 1500 and 1599.

**Important distinction**: The century filter uses **publication dates** (from `imprints.date_start`), not `birth_year`. This means it answers "agents who published in this century" rather than "agents born in this century."

### Time as an attribute

`birth_year` is used for the "Color by: Life Period" mode (the default). The `getCenturyLabel` function buckets `birth_year` into: Before 1400, 15th, 16th, 17th, 18th, 19th, 20th+, Unknown.

### Time in edge construction

The `same_place_period` edge type uses `imprints.date_start` to compute activity periods and requires a 10-year overlap. No other edge type uses time.

### Time is NOT structural

Time does not affect graph topology (no temporal layers, no time-based edge weighting). It is purely a filter and a visual attribute.

---

## 6. Rendering Logic

The map is implemented in `frontend/src/components/network/MapView.tsx` using `react-map-gl/maplibre` + `@deck.gl/react`.

### Base map

- **Tile source**: OpenFreeMap Positron style (`https://tiles.openfreemap.org/styles/positron`)
- **Initial view**: lat=40, lon=15, zoom=4 (centered roughly on Italy/Mediterranean)

### Layers (rendered bottom to top)

1. **ArcLayer** (`id: 'connections'`): Edges rendered as arcs between agents.
2. **ScatterplotLayer** (`id: 'agents'`): Agents rendered as circles.
3. **TextLayer** (`id: 'labels'`): Text labels for top 15 agents by `connection_count`.

### Node positioning (jitter)

Agents at the same city share identical lat/lon. The `jitteredPositions` memo handles this:
1. Groups nodes by `"${lat},${lon}"` key.
2. Single-node groups: placed at exact coordinates.
3. Multi-node groups: distributed in a circle around the city center.
   - Radius: `Math.min(0.03 * Math.sqrt(group.length), 0.3)` degrees. For 100 agents, radius = 0.3 degrees (the cap). For 10, radius ~0.095 degrees.
   - Angle: `(2 * PI * i) / group.length` -- evenly spaced.

### Node size

Radius = `4 + Math.min(connection_count / 10, 10)` pixels. Range is 4-14px. An agent with 0 connections = 4px; an agent with 100+ connections = 14px.

### Node color

Determined by `getAgentColor(node, colorBy)` using three palettes:

- **Century** (default): Based on `birth_year`. Seven color buckets + "Unknown" (gray).
- **Role**: Based on `primary_role`. Five options: author (blue), printer (green), editor (orange), translator (purple), other (gray).
- **Occupation**: Based on `occupations[0]`. Seven options: rabbi, philosopher, historian, poet, printer, theologian, other.

### Node selection highlight

When an agent is selected:
- **Selected node**: Full opacity (255), white outline (2px).
- **Connected nodes** (determined by `connectedAgents` set built from edges): High opacity (220), thin white outline (1px).
- **Unrelated nodes**: Heavily faded (alpha=50), no outline.

### Arc color

Arcs use the `CONNECTION_TYPE_CONFIG` color per type:
- teacher_student: blue [59, 130, 246]
- co_publication: green [16, 185, 129]
- same_place_period: cyan [6, 182, 212]
- wikilink: amber [245, 158, 11]
- llm_extraction: purple [139, 92, 246]
- category: gray [156, 163, 175]

**Opacity logic** (when no agent is selected):
- confidence >= 0.8: opacity 200
- confidence >= 0.6: opacity 130
- confidence < 0.6: opacity 60

**Opacity logic** (when an agent is selected):
- Edges touching selected agent: opacity = `Math.round(confidence * 255)` (scales with confidence)
- Other edges: opacity 25 (nearly invisible)

### Arc width

- confidence >= 0.8: 3px base
- confidence >= 0.6: 2px base
- confidence < 0.6: 1px base
- If edge touches selected agent: width doubles.

### Labels

Only the top 15 nodes (sorted by `connection_count` descending) get text labels. Labels use:
- Font: Inter, system-ui, sans-serif (600 weight)
- Size: 12px
- Color: dark gray [50, 50, 50, 220]
- Offset: 10px to the right of the node
- White outline (3px) for readability
- Anchor: start (left-aligned), vertically centered

### Tooltip

On hover over a node, displays: `{display_name} ({birth_year}--{death_year})\n{place_norm}\n{connection_count} connections`.

### Legend

A `Legend` component (bottom-left corner) shows the active color palette (Life Period, Role, or Occupation) with color swatches. Includes "Size = connections" note.

### Status bar

Bottom bar shows: `"Showing X of Y agents . Z connections"`. If category edges were limited, it appends `"(Shared Topics limited to top 100 of N)"`.

---

## 7. API Filtering

The main endpoint is `GET /network/map` (in `app/api/network.py`). It accepts:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `connection_types` | `"teacher_student"` | Comma-separated types |
| `min_confidence` | 0.5 | Floor for edge inclusion |
| `century` | null | Publication century filter |
| `place` | null | Filter by `place_norm` |
| `role` | null | Filter by `role_norm` |
| `limit` | 150 | Max agents returned (1-500) |

### Node selection logic

**When connection types are provided** (the normal case):

1. Counts each agent's edges of the selected types above `min_confidence` via a UNION ALL subquery.
2. Joins this count (`filtered_count`) back to `network_agents`.
3. Applies additional WHERE clauses: `lat IS NOT NULL`, plus optional century/place/role filters.
4. Orders by `filtered_count DESC` and applies `LIMIT`.

This means agents with the most connections of the selected types are returned first. Agents with 0 connections of those types can still appear (they get `filtered_count = 0` via `LEFT JOIN`), but will be at the bottom.

**When no connection types are selected** (types = "none" or empty):

Agents are sorted by `record_count DESC` instead, with no edge counting. No edges are returned.

### Edge selection logic

After determining the node set:

1. For each selected connection type, queries edges where both endpoints are in the returned node set and confidence >= `min_confidence`.
2. **Category cap**: The `category` type is special-cased with `ORDER BY confidence DESC LIMIT 100`. If the total exceeds 100, `category_limited` is set to true in the response metadata.
3. All non-category types have no edge limit.
4. The per-type queries are combined with `UNION ALL`.

### Agent detail endpoint

`GET /network/agent/{agent_norm}` returns full detail including:
- All connections (no type filter, no confidence filter)
- Wikipedia summary (from `wikipedia_cache` via `authority_enrichment`)
- External links: Wikidata, Wikipedia, VIAF URLs
- Primo catalog URL (first record for this agent)

### Default state

The frontend Zustand store (`networkStore.ts`) initializes with:
- `connectionTypes: []` (no types selected)
- `minConfidence: 0.5`
- `century: null`
- `role: null`
- `agentLimit: 150`
- `colorBy: 'century'`

So on first load, the user sees 150 agents sorted by `record_count` with no edges, colored by life period. The user must actively toggle connection types to see edges.

**Note on API default vs. frontend default**: The API default for `connection_types` is `"teacher_student"`, but the frontend sends `"none"` when its `connectionTypes` array is empty. The API default only applies if the parameter is omitted entirely.

---

## 8. Data Quality Measures

### During build (`build_network_tables.py`)

1. **INSERT OR IGNORE**: All edge insertions use `INSERT OR IGNORE` to prevent duplicate `(source, target, type)` triples (enforced by UNIQUE constraint on the table).
2. **Self-reference prevention**: `_build_teacher_student_edges` explicitly checks `teacher_norm != source_norm`. `_merge_duplicate_agents` deletes self-referencing edges after merging.
3. **Orphan removal**: `_cleanup_orphan_edges` deletes edges where either endpoint is absent from `network_agents`. This catches agents excluded due to missing geocodes.
4. **Dedup after merge**: After agent merging, a rowid-based dedup query removes duplicate edges: `DELETE FROM network_edges WHERE rowid NOT IN (SELECT MIN(rowid) ... GROUP BY source, target, type)`.
5. **Connection count recompute**: `_recompute_connection_counts` runs after all cleanup to ensure counts match actual edges.
6. **Place exclusion**: `[sine loco]` is excluded from place assignment and same-place-period computation.
7. **Geocode gate**: Agents without any geocoded place are excluded entirely from the map. Currently 388 agents (12.5%) are dropped this way.

### During API serving

1. **Category cap**: Category edges (22,132 total) are limited to 100 per request to prevent UI overload. The response metadata signals when this limit is hit.
2. **Node limit**: Default 150, max 500 agents per request.
3. **Confidence threshold**: Default 0.5, filtering out lower-confidence edges.
4. **Input validation**: Invalid connection types return HTTP 400.
5. **Lat/lon filter**: Only agents with `lat IS NOT NULL` are returned (always true for `network_agents` since build excludes them, but the WHERE clause is an extra safety check).

### Current data health

| Check | Result |
|-------|--------|
| Orphan edges | 0 |
| Self-referencing edges | 0 |
| Agents with primary_role | 2,714 / 2,714 (100%) |
| Agents with birth_year | 1,603 / 2,714 (59%) |
| Agents with connection_count > 0 | 1,284 / 2,714 (47%) |

---

## 9. Ambiguities and Limitations

### Place assignment is lossy

Each agent is assigned a single `place_norm` -- the most frequent publication city. An agent who published in both Amsterdam (3 records) and Venice (5 records) would be placed in Venice. The 3 Amsterdam records are invisible on the map. This is a design trade-off for rendering simplicity but can mislead users about an agent's geographic scope.

### Geocode gate is silent

388 agents (12.5%) are excluded because none of their publication places have geocodes. Users see "2,714 agents" in the UI but there is no indication that others were dropped. If a user searches for an agent excluded this way, they will not find them on the map.

### "Century" filter semantics are not obvious

The century filter uses **publication dates** (from `imprints.date_start`), not birth years. An 18th-century author whose works were reprinted in the 19th century would appear when filtering for century=19. Meanwhile, the "Color by: Life Period" mode uses `birth_year`. These are different time concepts applied to the same agents, which could confuse users.

### Same-place-period overlap uses publication dates, not life dates

The `same_place_period` edge computes activity overlap from `MIN(date_start)` to `MAX(date_start)` per agent per place. This is not the same as "lived in the same city at the same time." Two agents with one publication each in the same city, 15 years apart, would show a negative overlap and would not be connected. But an author whose works span 1500-1700 (including posthumous reprints) could appear to overlap with agents who were not contemporaries.

### The "other" role is a black hole

1,119 of 2,714 agents (41%) have `primary_role = "other"`. There is no way in the UI to filter specifically for these, nor to see the actual underlying role values (creator, illustrator, artist, former_owner, etc.).

### Birth year coverage is incomplete

41% of agents lack a `birth_year`. In "Color by: Life Period" mode, these all appear gray ("Unknown"), which can dominate the visual. The legend does show "Unknown" but users may not realize this represents nearly half the dataset.

### Co-publication confidence is relative, not absolute

The formula `MIN(shared_records / 5.0, 1.0)` means 5 shared records = confidence 1.0. But "shared a record" in this context means both agents appear in the `agents` table for the same `record_id`. This could mean co-authorship, or it could mean one is the author and the other is a former owner. The relationship semantics are conflated.

### Category edge volume can overwhelm

22,132 category edges (76.5% of all edges) all have the same confidence (0.65). While the API caps them at 100 per request, even 100 gray arcs can be visually noisy. The flat confidence also means the confidence-based opacity and width logic produces uniform results for all category edges.

### Deduplication misses some cases

Agent deduplication only merges norms sharing a `wikidata_id`. Agents without Wikidata IDs, or with separate Wikidata entries for the same person, will remain as separate nodes. There is no fuzzy string matching or manual merge mechanism.

### Label collision

Only the top 15 agents by connection count get labels. All labels are offset 10px to the right. In dense areas (e.g., Amsterdam with 218 agents), multiple labeled agents could overlap. There is no collision avoidance.

### Jitter is deterministic but arbitrary

The circular jitter for co-located agents is based on array index position, not any meaningful attribute. Two agents in Paris will be placed around the city center based purely on their iteration order. This means their relative positions on the map carry no semantic meaning.

### The `bidirectional` field is stored but not rendered differently

Edges have a `bidirectional` flag (e.g., all `co_publication` and `same_place_period` edges are bidirectional). However, the rendering code treats all edges identically -- arcs always go from source to target. The bidirectionality is visible in the data model but not visually distinguished on the map.

### Agent panel connection display is truncated

The `AgentPanel` component shows at most 20 connections per type (`conns.slice(0, 20)`). For highly connected agents like Moshe ben Maimon (213 connections), most connections are hidden behind a "+N more" label with no way to expand.

### API default mismatch

The API defaults `connection_types` to `"teacher_student"`, but the frontend sends `"none"` when its store initializes with an empty `connectionTypes` array. The API default would only apply to direct API callers who omit the parameter entirely.

---

## Appendix: Top Agents by Connection Count

| Agent | Connections | Place | Role |
|-------|-------------|-------|------|
| Moshe ben Maimon | 213 | Venice | other |
| Nahmanides | 192 | Venice | other |
| Moses Mendelssohn | 184 | Berlin | author |
| Isaiah Horowitz | 184 | Amsterdam | other |
| Montesquieu | 180 | Frankfurt | author |
| Johann Wolfgang von Goethe | 176 | Leipzig | author |
| Benedictus de Spinoza | 176 | Amsterdam | author |
| Friedrich Schiller | 174 | Leipzig | author |
| Kessef Mishneh | 169 | Venice | author |
| Claude Adrian Helvetius | 168 | Paris | author |

## Appendix: Top Places by Agent Count

| Place | Agent Count |
|-------|-------------|
| Paris | 443 |
| London | 260 |
| Amsterdam | 218 |
| Venice | 190 |
| Leipzig | 140 |
| Jerusalem | 121 |
| Berlin | 108 |
| Leiden | 67 |
| Frankfurt | 52 |
| Vienna | 51 |
