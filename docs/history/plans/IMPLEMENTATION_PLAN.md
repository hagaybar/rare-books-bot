# Rare Books Bot — Unified UI Implementation Plan

> **This document supersedes all reports in reports/ and is the sole source of truth for UI implementation.**

---

## Section 1: Product Vision & Architecture

### Vision

Rare Books Bot is an evidence-based bibliographic discovery system for a collection of 2,796 rare book records spanning 780 years (1244--2025). The unified UI consolidates three separate interfaces (React Metadata Workbench, Streamlit Chat UI, Streamlit QA Tool) into a single React application with 9 screens organized across 4 tiers. Scholars interact through natural language chat; operators manage metadata quality; developers debug query pipelines; administrators maintain authority records and monitor system health. Every answer traces back to MARC field evidence with explicit confidence scores.

### Architecture Overview

- **Screens**: 9 total
- **Tiers**: 4 (Primary, Operator, Diagnostics, Admin)
- **Framework**: React (continue with existing React application)
- **Backend**: FastAPI (existing, extended with new endpoints)
- **Database**: SQLite (bibliographic.db with 10 tables, 2,796 records)

### Tech Stack

| Layer | Technology | Version | Justification |
|-------|-----------|---------|---------------|
| UI Framework | React | 19 | Already in use; no migration needed |
| Language | TypeScript | 5.9 | Already in use; type safety for complex data shapes |
| Build | Vite | 8 | Already in use; fast HMR, automatic code splitting by route |
| Server State | TanStack Query | v5 | Already in use; cache invalidation, optimistic updates proven in Workbench |
| Client State | Zustand | new | Lightweight store for session, theme, sidebar state; replaces prop drilling |
| Tables | TanStack Table | v8 | Already in use; sortable, paginated, row-selectable tables proven in Workbench |
| Routing | React Router | v7 | Already in use; supports tiered layout nesting |
| CSS | Tailwind CSS | v4 | Already in use; confidence color bands, responsive layout |
| UI Primitives | Radix UI | new | Accessible, unstyled primitives (Dialog, Popover, Select, Tabs) |
| Charts | Recharts | v3 | Already in use for pie charts; add Nivo/Observable Plot when complex charts needed |
| Testing | Vitest + RTL + Playwright + MSW | new | Unit, integration, E2E, and API mocking |
| Chat Streaming | HTTP POST /chat | existing | HTTP-only at launch; WebSocket deferred to Phase 4 |
| Additional | react-markdown, cmdk, @tanstack/react-virtual, sonner | new | Markdown rendering, command palette, virtual scrolling, toast notifications |

**No full UI component library** (e.g., MUI, Ant Design). Radix primitives + Tailwind provide sufficient coverage without bundle overhead.

### Design Principles

1. **Bot-Centered Architecture**: Chat is the primary surface; everything else supports it
2. **Progressive Disclosure**: Scholars see clean chat; operators see confidence; developers see query plans
3. **Evidence-First Display**: Confidence scores and MARC citations are first-class UI elements
4. **Observable by Default**: Query interpretation, phase transitions, and timing are visible in real-time
5. **Single Source of Truth**: One Primo URL scheme, one query path, one correction workflow
6. **Composable Over Monolithic**: Reusable components (CandidateCard, ConfidenceBadge, PrimoLink, FieldBadge)

### Navigation Structure

**Tier-based sidebar** with collapsible icon mode on narrow viewports:

```
[Chat]                          /                    ← Tier 1: Primary (sidebar hidden by default)
─── Operator ──────────────────────────────────────
  [Coverage Dashboard]          /operator/coverage   ← Tier 2
  [Issues Workbench]            /operator/workbench  ← Tier 2
  [Agent Chat]                  /operator/agent      ← Tier 2
  [Correction Review]          /operator/review      ← Tier 2
─── Diagnostics ───────────────────────────────────
  [Query Debugger]              /diagnostics/query   ← Tier 3
  [Database Explorer]           /diagnostics/db      ← Tier 3
─── Admin ─────────────────────────────────────────
  [Publisher Authorities]       /admin/publishers    ← Tier 4
  [System Health]               /admin/health        ← Tier 4
```

**Chat page** hides the sidebar by default (hamburger menu accessible). All other pages show the sidebar. System Health status feeds a green/red dot indicator in the sidebar navigation.

### File Structure

```
frontend/src/
├── pages/
│   ├── Chat.tsx
│   ├── operator/
│   │   ├── Coverage.tsx
│   │   ├── Workbench.tsx
│   │   ├── AgentChat.tsx
│   │   └── Review.tsx
│   ├── diagnostics/
│   │   ├── QueryDebugger.tsx
│   │   └── DatabaseExplorer.tsx
│   └── admin/
│       ├── Publishers.tsx
│       └── Health.tsx
├── components/
│   ├── shared/           # CandidateCard, ConfidenceBadge, PrimoLink, FieldBadge
│   ├── chat/             # MessageBubble, FollowUpChips, PhaseIndicator
│   ├── layout/           # Sidebar, TieredLayout, NavItem
│   └── ...
├── hooks/
│   ├── useChat.ts
│   ├── usePrimoUrls.ts
│   └── ...
├── stores/
│   └── appStore.ts       # Zustand: session, sidebar, theme
├── api/
│   └── ...               # TanStack Query hooks per endpoint
└── types/
    └── ...               # TypeScript interfaces matching API shapes
```

---

## Section 2: Screen Specifications

### Screen 1: Chat -- `/` (Tier: Primary)

**Alignment**: PARTIALLY_ALIGNED
**Purpose**: Natural language bibliographic discovery interface. Scholars type queries, receive evidence-backed results with MARC citations, and refine through multi-turn conversation.

**API Endpoints**:
- `POST /chat` -- send query, receive ChatResponse with candidates, evidence, and follow-ups
- `GET /sessions/{session_id}` -- retrieve session history and extract QueryPlan from messages
- `DELETE /sessions/{session_id}` -- expire session
- `GET /health` -- status check for connection indicator
- `POST /metadata/primo-urls` -- batch Primo URL resolution for result links

**Data Shape** (actual fields from empirical verification):
```typescript
// ChatResponse (from POST /chat wrapper)
{
  message: string;
  candidate_set: CandidateSet | null;
  suggested_followups: string[];
  clarification_needed: string | null;
  session_id: string;
  phase: "query_definition" | "corpus_exploration" | null;
  confidence: number | null;           // Overall interpretation confidence
  metadata: Record<string, unknown>;   // Polymorphic: varies by phase and intent
}

// Candidate (within CandidateSet)
{
  record_id: string;
  match_rationale: string;
  evidence: Evidence[];
  title: string | null;
  author: string | null;
  date_start: number | null;
  date_end: number | null;
  place_norm: string | null;
  place_raw: string | null;
  publisher: string | null;
  subjects: string[];                  // First 3 subjects
  description: string | null;
}

// Evidence
{
  field: string;
  value: any;                          // Often null for subjects (known issue)
  operator: string;
  matched_against: any;
  source: string;                      // "marc:unknown" for agents (known issue)
  confidence: number | null;
  extraction_error: string | null;
}
```

**Features**:
- Two-phase conversation flow via HTTP POST (Phase 1: query definition with intent interpretation; Phase 2: corpus exploration with aggregation, refinement, comparison, enrichment, new query)
- Overall interpretation confidence display (0.85 threshold for auto-proceed)
- Clarification prompts for ambiguous queries (empty filters, vague terms, zero results)
- Follow-up suggestion chips from `suggested_followups`
- Example query shortcuts on empty state
- CandidateCard rendering with title, author, date (smart display: single year vs range), place (canonical + raw with dedup), publisher, subjects (first 3)
- Primo URL links on each candidate (batch-resolved, client-side cached)
- Collapsible evidence panel per candidate showing MARC field citations
- Session persistence across page reloads
- Phase indicator showing current conversation phase
- Execution time display (after B1 backend task)
- Phase 2 aggregation charts using `visualization_hint` (bar_chart, pie_chart, table) -- requires B2
- SUBJECT_RETRY warning display when query was silently broadened -- requires B3
- `react-markdown` rendering for natural language responses

**Backend Prerequisites** (must be built before this screen is complete):
- **B1**: Add `execution_time_ms` to `ChatResponse.metadata` (1-2 hours)
- **B2**: Forward `FacetCounts` in `ChatResponse.metadata` for aggregation charts (2-4 hours)
- **B3**: Forward `QueryWarning[]` in `ChatResponse.metadata` (1-2 hours)
- **B4**: Add `primo_url` to Candidate model OR document batch approach (2-4 hours)

**Design Notes**:
- Launch HTTP-only; WebSocket streaming deferred to Phase 4 (B16: 2-3 days) because existing WS handler uses old single-phase code path incompatible with two-phase flow
- Drop per-filter confidence display -- `Filter.confidence` is always null in all tested queries; LLM does not produce it
- Batch-resolve Primo URLs via `POST /metadata/primo-urls` after results load; cache client-side per session
- Handle polymorphic `ChatResponse.metadata` with TypeScript type guards (different shapes per phase/intent)
- Access QueryPlan via `GET /sessions/{session_id}` workaround (plan stored in session messages, not in ChatResponse)
- Phase 2 supports 7 intent types: AGGREGATION, METADATA_QUESTION, REFINEMENT, COMPARISON, ENRICHMENT_REQUEST, RECOMMENDATION (stub), NEW_QUERY
- Fresh queries take 1.5-7.5 seconds (LLM-dominated); cached queries return in ~150ms; display loading indicator accordingly

---

### Screen 2: Coverage Dashboard -- `/operator/coverage` (Tier: Operator)

**Alignment**: PARTIALLY_ALIGNED
**Purpose**: Visual overview of metadata normalization quality across all fields, highlighting gaps and improvement opportunities for operators.

**API Endpoints**:
- `GET /metadata/coverage` -- per-field coverage stats with confidence distribution (10 bands), method distribution, and flagged item counts

**Data Shape**:
```typescript
// FieldCoverageResponse (per field: date, place, publisher, agent_name, agent_role)
{
  field: string;
  total_records: number;
  non_null_count: number;
  null_count: number;
  confidence_distribution: ConfidenceBandResponse[];  // 10 bands
  method_distribution: MethodBreakdownResponse[];
  flagged_items: FlaggedItemResponse[];               // low-confidence values with details
}

// ConfidenceBandResponse
{
  band_label: string;    // e.g. "0.00", "0.80"
  lower: number;         // inclusive lower bound
  upper: number;         // exclusive upper bound (except last band)
  count: number;
}

// MethodBreakdownResponse
{
  method: string;
  count: number;
}

// FlaggedItemResponse
{
  raw_value: string;
  norm_value: string | null;
  confidence: number;
  method: string | null;
  frequency: number;
}
```

**Features**:
- Per-field coverage bars for 5 fields: date, place, publisher, agent_name, agent_role
- Binary confidence visualization (resolved/unresolved) for place and publisher -- medium and low bands are empirically empty
- Graduated confidence bands for dates only (0.8-0.95 band contains 1,306 records = 47.1%)
- Method distribution charts per field (e.g., date: year_exact 46.1%, hebrew_gematria 20%, year_embedded 13.1%)
- Flagged item counts with drill-through links to Issues Workbench (via field filter)
- Gap cards highlighting real improvement opportunities:
  - 553 Hebrew-script publishers (un-transliterated, technically 0.95 but functionally incomplete)
  - 4,366 agents at 100% base_clean / 0% alias-mapped (largest gap)
  - 202 unresearched publisher authorities (89% of 227 total)
  - 44.1% of agent roles classified as "other" (1,924 of 4,366)
  - 41 [sine loco] records, 215 unknown-publisher imprints
- Hebrew-script publisher indicator (553 records, 20.2% of publishers)

**Backend Prerequisites**:
- None. `GET /metadata/coverage` endpoint is fully functional.

**Design Notes**:
- Replace four-band confidence visualization with binary (resolved/unresolved) for place and publisher. The 0.5-0.95 range contains zero records for both fields.
- Lead dashboard with agent normalization gaps (100% base_clean, 0% alias-mapped) as the most impactful improvement area
- Drop "trend over time" from initial scope -- no snapshot mechanism exists
- Drop "before/after correction comparison" -- no tracking infrastructure exists
- Coverage rates from empirical data: date 97.5% (2,704/2,773), place 99.3% (2,754/2,773), publisher 98.8% (2,740/2,773)

---

### Screen 3: Issues Workbench -- `/operator/workbench` (Tier: Operator)

**Alignment**: PARTIALLY_ALIGNED
**Purpose**: Triage and correct metadata quality issues through inline editing, batch corrections, and cluster-based improvements. Reframed from "issues" to "improvement opportunities."

**API Endpoints**:
- `GET /metadata/issues` -- paginated low-confidence records (params: field [required], max_confidence, limit, offset)
- `GET /metadata/unmapped` -- raw values without canonical mappings, sorted by frequency (params: field [required], sort); directly feeds Hebrew Publishers and Agent Normalization tabs
- `POST /metadata/corrections` -- submit single correction (fields: place, publisher, agent -- NOT date)
- `POST /metadata/corrections/batch` -- submit batch corrections
- `GET /metadata/clusters` -- gap clusters with priority scores

**Data Shape**:
```typescript
// Issue item
{
  mms_id: string;
  raw_value: string;
  norm_value: string;
  confidence: number;
  method: string;
}

// ClusterValueResponse
{
  raw_value: string;
  frequency: number;
  confidence: number;
  method: string;
}

// ClusterResponse
{
  cluster_id: string;
  field: string;
  cluster_type: string;
  values: ClusterValueResponse[];
  proposed_canonical: string | null;
  evidence: Record<string, any>;
  priority_score: number;
  total_records_affected: number;
}

// CorrectionRequest
{
  field: "place" | "publisher" | "agent";  // NOT date
  raw_value: string;
  canonical_value: string;
  evidence: string;
  source: string;
}

// CorrectionResponse
{
  success: boolean;
  alias_map_updated: string;    // file path to the alias map that was updated
  records_affected: number;
}
```

**Features**:
- TanStack Table with sortable, paginated, row-selectable records
- Inline editable cells for corrections (place, publisher, agent fields)
- Batch corrections via batch toolbar (select multiple rows, apply canonical value)
- Cluster view with expandable cards showing priority scores and records affected
- Method-based filtering (base_clean vs alias_map vs publisher_authority) instead of confidence slider
- Tab-based organization:
  - **Low Confidence**: 121 total records (69 dates + 19 places + 33 publishers)
  - **Hebrew Publishers**: 553 un-transliterated Hebrew-script publisher values
  - **Agent Normalization**: 4,366 base_clean-only agents
- Cross-link to Agent Chat for AI-assisted correction proposals

**Backend Prerequisites**:
- **B17** (Phase 4): Add `date` to `CorrectionRequest.field` accepted values (0.5 day)

**Design Notes**:
- Reframe from "issues" to "improvement opportunities" -- only 121 records have low confidence scores
- Confidence slider for place and publisher is functionally useless (0.5-0.95 range returns 0 results); replace with method-based filtering
- Date corrections are not currently supported via the corrections API; display date issues as read-only with "API support pending" label until B17
- The real improvement volume comes from Hebrew publishers (553), agent normalization (4,366), and unresearched authorities (202), not from low-confidence flags

---

### Screen 4: Agent Chat -- `/operator/agent` (Tier: Operator)

**Alignment**: CONFIRMED
**Purpose**: AI-assisted metadata correction through specialist agent conversations. Operators describe normalization problems, receive structured proposals, and approve corrections.

**API Endpoints**:
- `POST /metadata/agent/chat` -- send message to field-specific agent, receive proposals
- `POST /metadata/corrections` -- apply approved corrections
- `GET /metadata/coverage` -- sidebar coverage stats

**Data Shape**:
```typescript
// AgentChatRequest
{
  field: string;        // place, date, publisher, agent
  message: string;
  session_id?: string;
}

// AgentChatResponse
{
  response: string;
  proposals: Proposal[];
  clusters: ClusterResponse[];
  field: string;
  action: "analysis" | "proposals" | "answer";
}

// Proposal
{
  raw_value: string;
  canonical_value: string;
  confidence: number;
  reasoning: string;
  evidence_sources: string[];
}
```

**Features**:
- Field-specific agent selection (Place, Date, Publisher, Agent -- 4 specialist agents)
- Conversational interface with structured proposals (raw_value, canonical_value, confidence, reasoning, evidence_sources)
- Approve/reject/edit workflow for each proposal
- Cluster summaries with priority scores
- Coverage sidebar via `/metadata/coverage` showing real-time field stats
- Corrections submission with `records_affected` feedback

**Backend Prerequisites**:
- None. All endpoints are fully functional.

**Design Notes**:
- 89% of publisher authorities (202/227) are unresearched stubs; PublisherAgent has limited authority context for proposals
- `authority_enrichment` table is empty (0 rows); no VIAF/CERL data available for agent proposals
- No structural changes needed from existing React implementation

---

### Screen 5: Correction Review -- `/operator/review` (Tier: Operator)

**Alignment**: CONFIRMED
**Purpose**: Audit trail for all metadata corrections with filtering, pagination, and export. Provides accountability and traceability for normalization changes.

**API Endpoints**:
- `GET /metadata/corrections/history` -- paginated history (params: field filter only)

**Data Shape**:
```typescript
// CorrectionHistoryEntry
{
  timestamp: string;
  field: string;
  raw_value: string;
  canonical_value: string;
  evidence: string;
  source: string;
  action: string;
}
```

**Features**:
- Paginated correction history table with all audit fields
- Field-based filtering (server-side)
- Client-side CSV and JSON export
- Client-side search and date range filtering (approximation until B18)

**Backend Prerequisites**:
- **B18** (Phase 4): Add search, source, date range filter params to corrections history API (0.5 day)
- **B19** (Phase 4): Corrections revert endpoint (1 day)

**Design Notes**:
- Defer revert capability until B19 endpoint is built; display revert button as disabled with tooltip "Coming soon"
- Client-side filtering approximates server-side search, source, and date range until B18
- Export is client-side only; no server-side export endpoint exists or is planned

---

### Screen 6: Query Debugger -- `/diagnostics/query` (Tier: Diagnostics)

**Alignment**: MISALIGNED
**Purpose**: Developer tool for testing query interpretation, labeling results (TP/FP/FN/UNK), managing gold sets, and running regression tests. Replaces the Streamlit QA Tool.

**API Endpoints**:
- `POST /diagnostics/query-run` -- execute query and store run (NEW, B5)
- `GET /diagnostics/query-runs` -- list historical runs (NEW, B6)
- `POST /diagnostics/labels` -- save TP/FP/FN/UNK labels (NEW, B7)
- `GET /diagnostics/labels/{run_id}` -- retrieve labels for a run (NEW, B8)
- `POST /diagnostics/gold-set/export` -- export gold set JSON (NEW, B9)
- `POST /diagnostics/gold-set/regression` -- run regression test (NEW, B10)

**Data Shape** (to be defined during backend implementation):
```typescript
// QueryRun
{
  run_id: string;
  query_text: string;
  query_plan: QueryPlan;
  sql: string;
  candidates: Candidate[];
  execution_time_ms: number;
  warnings: QueryWarning[];
  timestamp: string;
}

// CandidateLabel
{
  run_id: string;
  record_id: string;
  label: "TP" | "FP" | "FN" | "UNK";
  issue_tags?: string[];
  notes?: string;
}

// RegressionResult
{
  query_text: string;
  expected_includes: string[];
  expected_excludes: string[];
  actual_includes: string[];
  missing: string[];
  unexpected: string[];
  pass: boolean;
}
```

**Features**:
- Three-panel layout: Query Input | Results + Labels | Plan + SQL Inspector
- Query execution with full plan visibility (QueryPlan JSON tree, generated SQL, execution time)
- TP/FP/FN/UNK labeling workflow per candidate
- Issue tagging with predefined categories (parser_error, normalization_issue, missing_filter, false_broadening)
- False negative search: database search to find records that should have matched
- Gold set management: export labeled queries to gold.json
- Regression runner: execute gold set and display pass/fail per query
- SUBJECT_RETRY warning display for false broadening detection
- Run history list with re-run capability

**Backend Prerequisites** (ALL features require new endpoints -- zero diagnostics API exists):
- **B5**: `POST /diagnostics/query-run` (1 day)
- **B6**: `GET /diagnostics/query-runs` (0.5 day)
- **B7**: `POST /diagnostics/labels` (0.5 day)
- **B8**: `GET /diagnostics/labels/{run_id}` (0.5 day)
- **B9**: `POST /diagnostics/gold-set/export` (0.5 day)
- **B10**: `POST /diagnostics/gold-set/regression` (1 day)

**Design Notes**:
- This screen requires the most new backend work of any screen (4 days minimum)
- Drop per-filter confidence visualization (Filter.confidence is always null)
- Drop execution timing breakdown until backend exposes granular compile/SQL/total times
- QA database (data/qa/qa.db) has existing tables; new diagnostic API reads from it directly (no migration)
- Frontend development uses MSW mocks while backend endpoints are being built
- Must be scheduled AFTER Phase 1 (sequential, not parallel)

---

### Screen 7: Database Explorer -- `/diagnostics/db` (Tier: Diagnostics)

**Alignment**: MISALIGNED
**Purpose**: Read-only browser for all 10 database tables, enabling developers to inspect raw data, verify normalization results, and support debugging.

**API Endpoints**:
- `GET /diagnostics/tables` -- list all tables with row counts (NEW, B11)
- `GET /diagnostics/tables/{name}/rows` -- paginated row data with column search (NEW, B12)

**Data Shape**:
```typescript
// TableInfo
{
  name: string;
  row_count: number;
  columns: string[];
}

// TableRows
{
  table: string;
  rows: Record<string, any>[];
  total: number;
  offset: number;
  limit: number;
}
```

**Features**:
- Table list showing all 10 tables: records (2,796), imprints (2,773), titles (4,791), subjects (5,415), agents (4,366), languages (3,197), notes (8,037), publisher_authorities (227), publisher_variants (265), authority_enrichment (0)
- Paginated row browser with column-level search
- Column sorting
- Row count badges

**Backend Prerequisites**:
- **B11**: `GET /diagnostics/tables` (0.5 day)
- **B12**: `GET /diagnostics/tables/{name}/rows` with SQL injection protection (1 day)

**Design Notes**:
- Include all 10 tables (not 6 as originally assumed)
- SQL injection protection is critical for the rows endpoint (parameterized queries, table name allowlist)
- Data is also accessible via CLI and direct SQLite; this screen is a convenience tool
- Lowest priority within the Diagnostics tier

---

### Screen 8: Publisher Authorities -- `/admin/publishers` (Tier: Admin)

**Alignment**: PARTIALLY_ALIGNED
**Purpose**: Management interface for the publisher authority record system. Emphasizes research workflow for classifying 202 unresearched stubs and adding enrichment data.

**API Endpoints**:
- `GET /metadata/publishers` -- list authorities with variant counts, imprint counts, variants, type filter (existing, read-only)
- `POST /metadata/publishers` -- create authority (NEW, B13)
- `PUT /metadata/publishers/{id}` -- update authority (NEW, B13)
- `DELETE /metadata/publishers/{id}` -- delete authority (NEW, B13)
- `POST /metadata/publishers/match-preview` -- preview imprint match impact (NEW, B14)

**Data Shape** (existing read endpoint):
```typescript
// PublisherAuthority
{
  authority_id: number;
  canonical_name: string;
  type: string;                        // printing_house (18), unresearched (202), bibliophile_society (3), etc.
  is_missing_marker: boolean;
  variant_count: number;
  imprint_count: number;
  variants: PublisherVariant[];
  viaf_id: string | null;             // Currently ALL null
  wikidata_id: string | null;         // Currently ALL null
  cerl_id: string | null;             // Currently ALL null
}
```

**Features**:
- Authority list with TanStack Table (sortable by variant_count, imprint_count, type)
- Type filtering (printing_house: 18, unresearched: 202, bibliophile_society: 3, unknown_marker: 2, modern_publisher: 1, private_press: 1)
- Expandable variant list per authority
- Research workflow emphasis: "Not yet researched" labels for null VIAF/Wikidata/CERL fields
- Match preview: "Adding this variant would match N additional imprints" (requires B14)
- CRUD operations for authorities and variants (requires B13)

**Backend Prerequisites**:
- **B13**: Publisher authority CRUD endpoints POST/PUT/DELETE (1-2 days)
- **B14**: Match preview endpoint (0.5 day)

**Design Notes**:
- Read-only view is immediately buildable (API already exists); deploy in Phase 1 parallel track
- CRUD capabilities require B13; deploy in Phase 3
- Reframe for research workflow: 89% (202/227) are unresearched stubs needing classification
- All enrichment IDs (VIAF, Wikidata, CERL) are currently null; display as "not yet researched"
- 834 imprints are currently matchable via variant forms; match preview shows impact of adding new variants

---

### Screen 9: System Health -- `/admin/health` (Tier: Admin)

**Alignment**: PARTIALLY_ALIGNED
**Purpose**: Basic system status display and navigation bar health indicator. Scoped to essential connectivity checks.

**API Endpoints**:
- `GET /health` -- returns status, database_connected, session_store_ok (existing)
- `GET /health/extended` -- DB file size and last-modified time (NEW, B15)

**Data Shape**:
```typescript
// HealthResponse
{
  status: "healthy" | "degraded" | "unhealthy";
  database_connected: boolean;
  session_store_ok: boolean;
}

// ExtendedHealth (after B15)
{
  db_file_size_mb: number;
  db_last_modified: string;
}
```

**Features**:
- Traffic light status indicator (healthy/degraded/unhealthy)
- Database connection status
- Session store status
- DB file size and last-modified time (after B15)
- Nav bar green/red dot indicator fed from health check (visible on all pages)

**Backend Prerequisites**:
- **B15**: DB file size/last-modified endpoint (1 hour)

**Design Notes**:
- Scoped down to basic status only
- Defer log viewer, metrics dashboard, interaction viewer, and request rate charts -- no infrastructure exists for any of these
- Lowest priority screen overall
- The nav bar health indicator provides ongoing value even if this page is minimal

---

## Section 3: Backend Work Inventory

| ID | Endpoint | Method | Purpose | Effort | Screen | Blocking? |
|----|----------|--------|---------|--------|--------|-----------|
| B1 | ChatResponse.metadata | PATCH | Add execution_time_ms (already computed, not serialized) | 1-2 hours | Chat | Yes -- timing display |
| B2 | ChatResponse.metadata | PATCH | Forward FacetCounts (already computed, discarded before serialization) | 2-4 hours | Chat | Yes -- aggregation charts |
| B3 | ChatResponse.metadata | PATCH | Forward QueryWarning[] to frontend | 1-2 hours | Chat, Query Debugger | Yes -- warning display |
| B4 | Candidate model | PATCH | Add primo_url field OR document batch approach | 2-4 hours | Chat | Yes -- Primo links |
| B5 | /diagnostics/query-run | POST | Execute query and store run with plan, SQL, results, timing | 1 day | Query Debugger | Yes |
| B6 | /diagnostics/query-runs | GET | List historical query runs (paginated) | 0.5 day | Query Debugger | Yes |
| B7 | /diagnostics/labels | POST | Save TP/FP/FN/UNK labels for a run | 0.5 day | Query Debugger | Yes |
| B8 | /diagnostics/labels/{run_id} | GET | Retrieve labels for a specific run | 0.5 day | Query Debugger | Yes |
| B9 | /diagnostics/gold-set/export | POST | Export labeled queries to gold.json format | 0.5 day | Query Debugger | Yes |
| B10 | /diagnostics/gold-set/regression | POST | Run regression test against gold set, return pass/fail | 1 day | Query Debugger | Yes |
| B11 | /diagnostics/tables | GET | List all 10 tables with row counts and column names | 0.5 day | Database Explorer | Yes |
| B12 | /diagnostics/tables/{name}/rows | GET | Paginated row data with column search (SQL injection protection) | 1 day | Database Explorer | Yes |
| B13 | /metadata/publishers | POST/PUT/DELETE | CRUD operations for publisher authorities and variants | 1-2 days | Publisher Authorities | Yes -- editing |
| B14 | /metadata/publishers/match-preview | POST | Preview imprint match impact of adding a variant | 0.5 day | Publisher Authorities | Yes -- match preview |
| B15 | /health/extended | GET | DB file size and last-modified timestamp | 1 hour | System Health | Yes -- file info |
| B16 | WS /ws/chat | UPGRADE | Rewrite WebSocket handler to use two-phase flow (intent agent, facets, phase/confidence) | 2-3 days | Chat (streaming) | Yes -- WebSocket |
| B17 | CorrectionRequest.field | EXTEND | Add 'date' to accepted field values in corrections API | 0.5 day | Issues Workbench | Yes -- date corrections |
| B18 | /metadata/corrections/history | EXTEND | Add search, source, date_range query params | 0.5 day | Correction Review | No (client-side fallback) |
| B19 | /metadata/corrections/revert | POST | Revert a specific correction by ID | 1 day | Correction Review | Yes -- revert feature |
| B20 | Evidence model | FIX | Populate subject evidence.value (currently always null) | 0.5 day | Chat, Query Debugger | No (cosmetic) |
| B21 | Evidence model | FIX | Fix agent evidence.source from 'marc:unknown' to actual MARC tag | 0.5 day | Chat, Query Debugger | No (cosmetic) |
| B22 | Subject retry | FIX | Add confidence threshold to subject retry or return zero results with suggestion | 1 day | Chat | No (correctness improvement) |

### Effort Summary

| Category | Items | Effort |
|----------|-------|--------|
| Phase 1 micro-tasks (B1-B4) | 4 | 1-1.5 days |
| Phase 2 diagnostic endpoints (B5-B12) | 8 | 5.5 days |
| Phase 3 admin endpoints (B13-B15) | 3 | 2-3 days |
| Phase 4 polish (B16-B22) | 7 | 6-7.5 days |
| **Total** | **22** | **14.5-17.5 developer-days** |

---

## Section 4: Phased Implementation Plan

### Dependency Diagram

```
Week:  1       2       3       4       5       6       7       8
       ├───────┼───────┼───────┼───────┼───────┼───────┼───────┤
P0:    [=======]
       Foundation

P1:            [===============]
               Chat + B1-B4

P3a:           [=====]
               Publishers (read-only, parallel)

P2:                            [===============]
                               Debugger + B5-B12

P3b:                                   [=======]
                                       Admin CRUD + Health

P4:                                            [===============]
                                               Polish + B16-B22

P5:                                                    [=======]
                                                       Cleanup

Critical path: P0 → P1 → P2(backend) → P2(frontend) → P4 → P5
Parallel:      P3a runs alongside P1 | P3b runs alongside P2
```

---

### Phase 0: Foundation & Scaffolding

**Duration**: Week 1
**Dependencies**: None (starting point)

**Deliverables**:
1. Restructure `frontend/src/pages/` from flat (4 files) to tiered layout (Chat.tsx + operator/ + diagnostics/ + admin/ subdirectories)
2. Update `App.tsx` routing to 9 routes with React Router v7 nested layouts
3. Replace existing Sidebar component with tiered navigation (Primary / Operator / Diagnostics / Admin sections)
4. Add Zustand store (`stores/appStore.ts`) for session ID, sidebar state, theme
5. Add shared design tokens (confidence color bands, spacing, typography scales) to Tailwind config
6. Extend Vite proxy configuration for `/diagnostics/*` and `/admin/*` routes
7. Install new dependencies: Zustand, Radix UI, cmdk, sonner, MSW
8. Create temporary redirects from old routes (`/` -> `/operator/coverage`) to preserve existing Workbench user access
9. Create placeholder pages for 5 new screens (Chat, QueryDebugger, DatabaseExplorer, Publishers, Health)

**Backend Work**: Begin B1-B4 micro-tasks concurrently (complete by end of Week 1)

**Exit Criteria**:
- All 4 existing Workbench pages render at their new `/operator/*` URLs
- Placeholder pages exist and are routable for all 5 new screens
- Tiered sidebar navigation renders with correct groupings
- Zustand store holds sidebar collapse state
- `npm run build` succeeds with zero TypeScript errors
- Old routes redirect to new locations

---

### Phase 1: Chat Screen + Backend Micro-Tasks (HTTP-only)

**Duration**: Weeks 2-3
**Dependencies**: Phase 0 complete; B1-B4 complete (days 1-3)

**Deliverables**:
1. `Chat.tsx` with two-phase conversation flow via HTTP `POST /chat`
2. `CandidateCard.tsx` reusable component (title, author, smart date display, place canonical+raw, publisher, subjects, evidence panel, Primo link)
3. `ConfidenceBadge.tsx` shared component (overall confidence only, not per-filter)
4. `PrimoLink.tsx` shared component with batch URL resolution via `POST /metadata/primo-urls`
5. Follow-up suggestion chips from `suggested_followups`
6. Example query shortcuts on empty chat state
7. Phase indicator (query_definition / corpus_exploration)
8. Overall interpretation confidence display
9. Clarification prompt rendering for ambiguous queries
10. Session management (create on first query, resume via stored session_id, expire)
11. Execution time display (from B1 `metadata.execution_time_ms`)
12. SUBJECT_RETRY warning display (from B3 `metadata.warnings`)
13. Markdown rendering for natural language responses via `react-markdown`

**Concurrent Track** (Phase 3a): Publisher Authorities read-only view (1-2 days, API already exists)

**Dropped from Original Plan**:
- `useWebSocket.ts` hook (deferred to Phase 4)
- Per-filter confidence display (always null, unbuildable)
- WebSocket streaming progress indicators

**Exit Criteria**:
- Send natural language query via HTTP, see formatted results with evidence and MARC citations
- Two-phase flow works: Phase 1 interpretation followed by Phase 2 exploration
- Overall confidence score displayed; clarification prompts render for ambiguous queries
- Sessions persist across page reloads
- Primo links resolve and open correct catalog pages
- Follow-up chips trigger new queries
- Loading indicator shows during 1.5-7.5 second query execution
- Execution time displayed in collapsible metadata section
- SUBJECT_RETRY warnings displayed when present
- Publisher Authorities page (Phase 3a) shows read-only authority list with type filtering

**Enables**: Streamlit Chat UI (`app/ui_chat/`, 449 lines) marked deprecated

---

### Phase 2: Query Debugger + Diagnostics Backend

**Duration**: Weeks 4-5 (backend: Week 4; frontend: Weeks 4-5 with MSW mocks during backend development)
**Dependencies**: Phase 1 complete (SEQUENTIAL, not parallel)

**Deliverables**:
1. All diagnostic API endpoints (B5-B12): query-run, query-runs, labels, labels/{run_id}, gold-set/export, gold-set/regression, tables, tables/{name}/rows
2. `QueryDebugger.tsx` with three-panel layout (Query Input | Results + Labels | Plan + SQL)
3. TP/FP/FN/UNK labeling workflow per candidate
4. Issue tagging with predefined categories
5. False negative search (database search for missing results)
6. Gold set export to `data/qa/gold.json`
7. Regression runner with pass/fail display per query
8. Query plan inspection (JSON tree view)
9. Run history list
10. `DatabaseExplorer.tsx` for all 10 tables with paginated browsing and column search
11. CLI consolidation: merge `app/qa.py` (187 lines) into `app/cli.py` as `regression` subcommand

**Exit Criteria**:
- Execute query in debugger, see plan JSON + generated SQL + results
- Label candidates as TP/FP/FN/UNK; labels persist across page reloads
- Search for false negatives via database search
- Export gold set and run regression test; see pass/fail per query
- DB Explorer shows all 10 tables with correct row counts: records (2,796), imprints (2,773), titles (4,791), subjects (5,415), agents (4,366), languages (3,197), notes (8,037), publisher_authorities (227), publisher_variants (265), authority_enrichment (0)
- Column search filters rows in DB Explorer
- `python -m app.cli regression --gold data/qa/gold.json --db data/index/bibliographic.db` works

**Enables**: Streamlit QA Tool (`app/ui_qa/`, 3,531 lines) marked deprecated

---

### Phase 3: Admin Screens

**Duration**: Week 5 (Phase 3b; Phase 3a runs parallel with Phase 1 in Weeks 2-3)
**Dependencies**: Phase 3a (read-only publishers) already deployed; B13-B15 built in this phase

**Phase 3a (Weeks 2-3, parallel with Phase 1)**:
- Publisher Authorities read-only view (API already exists)
- Authority list with type filtering, expandable variants, research workflow labels

**Phase 3b (Week 5) Deliverables**:
1. Publisher CRUD operations (B13: create, edit, delete authorities and variants)
2. Match preview (B14: "Adding this variant would match N additional imprints")
3. `Health.tsx` with basic status display (B15: DB file size/last-modified)
4. Nav bar health indicator (green/red dot) fed from `GET /health` polling

**Backend Work Included**:
- B13: Publisher authority CRUD endpoints (1-2 days)
- B14: Match preview endpoint (0.5 day)
- B15: DB file size/last-modified endpoint (1 hour)

**Exit Criteria**:
- Create new publisher authority with variants; see imprint count update
- Edit authority type (e.g., reclassify "unresearched" to "printing_house")
- Delete authority (with confirmation dialog)
- Match preview shows correct imprint count impact
- Health page shows healthy/degraded/unhealthy status, DB file size, last-modified
- Nav bar dot is green when healthy, red when unhealthy

---

### Phase 4: Polish, Integration & Testing

**Duration**: Weeks 6-7
**Dependencies**: Phases 1, 2, 3 complete

**Deliverables**:
1. **Cross-screen navigation links**:
   - Chat -> Workbench: "Flag issue" link on candidate cards
   - Workbench -> Agent Chat: "Ask agent" link on cluster cards
   - Query Debugger -> Workbench: Link FN results to Workbench for correction
   - Coverage Dashboard -> Workbench: Gap card drill-through
2. **Shared component finalization**: ConfidenceBadge, CandidateCard, PrimoLink, FieldBadge tested across all consuming screens
3. **Testing suite**:
   - Vitest unit tests for all shared components
   - React Testing Library integration tests for each screen
   - Playwright E2E tests for critical flows (Chat query, Workbench correction, Debugger labeling)
   - MSW handlers for all API endpoints
4. **Production build validation**: Vite code splitting by route, bundle size audit
5. **Backend polish tasks**:
   - B16: WebSocket two-phase upgrade (2-3 days, if prioritized)
   - B17: Date corrections in CorrectionRequest (0.5 day)
   - B18: Corrections history search/source/date params (0.5 day)
   - B19: Corrections revert endpoint (1 day)
   - B20: Fix subject evidence.value null (0.5 day)
   - B21: Fix agent evidence.source 'marc:unknown' (0.5 day)
   - B22: Subject retry confidence threshold (1 day)
6. **Responsive layout verification**: Sidebar collapse on narrow viewports, Chat full-width on mobile

**Exit Criteria**:
- All cross-screen links work bidirectionally
- Vitest test suite passes with >80% component coverage
- At least 3 Playwright E2E tests pass (chat flow, correction flow, labeling flow)
- Production build under 500KB initial bundle (per-route splitting verified)
- WebSocket streaming works with two-phase flow (if B16 completed)
- Date corrections work in Issues Workbench (if B17 completed)

---

### Phase 5: Retirement & Cleanup

**Duration**: Week 8
**Dependencies**: Phases 1-4 complete; all Streamlit features have working React replacements

**Deliverables**:
1. **Delete**:
   - `app/ui_chat/` (449 lines) -- replaced by React Chat
   - `app/ui_qa/` (3,531 lines) -- replaced by React Query Debugger + DB Explorer
   - `app/qa.py` (187 lines) -- merged into CLI regression subcommand
   - `streamlit` from `pyproject.toml` dependencies
2. **Archive** (move to `archive/retired_streamlit/`):
   - QA Wizard code (reference)
   - QA DB schema documentation (reference)
   - Regression runner reference implementation
3. **Preserve** (do not delete):
   - `data/qa/qa.db` (historical data, read by diagnostic API)
   - `data/qa/gold.json` (active, used by CLI regression)
4. **Update `CLAUDE.md`**: Remove Streamlit references, update QA Tool section to point to React Query Debugger, update API documentation. Also correct stale numbers: publisher authorities 228->227, publisher variants 266->265, unresearched 203->202; and remove stale place normalization method references (base_clean for places does not exist in production; only place_alias_map and missing methods are used)
5. **Landing page switch**: Change default route from `/operator/coverage` to `/` (Chat)
6. **Git tag**: `ui-migration-complete`

**Exit Criteria**:
- Single React app serves all 9 screens
- Zero Streamlit dependencies in `pyproject.toml`
- `poetry install` does not install streamlit
- `CLAUDE.md` contains no references to Streamlit UI tools
- Git tagged `ui-migration-complete`
- All existing tests pass (`pytest` green)

---

### Early Wins Timeline

| Milestone | Week | Achievement |
|-----------|------|-------------|
| 9-screen skeleton | End of Week 1 | Restructured app with all routes and placeholder pages |
| Working Chat | End of Week 3 | Natural language queries with evidence-backed results |
| Streamlit Chat deprecated | End of Week 3 | React Chat replaces Streamlit Chat UI |
| Working Debugger | End of Week 5 | Query testing with labeling and regression |
| Streamlit QA deprecated | End of Week 5 | React Debugger replaces Streamlit QA Tool |
| All screens functional | End of Week 7 | Full feature set across all 9 screens |
| Clean codebase | End of Week 8 | Single unified app, no legacy code |

---

## Section 5: Features -- Keep vs Drop

### KEEP

| Feature | Source UI | New Screen | Modifications Needed |
|---------|-----------|------------|---------------------|
| TanStack Table (sortable, paginated, row-selectable) | React Workbench | Issues Workbench, Query Debugger, DB Explorer, Publishers | None -- reuse existing implementation |
| Coverage Dashboard (stat cards, coverage bars, gap cards, method charts) | React Workbench | Coverage Dashboard | Replace four-band with binary for place/publisher; add agent gaps |
| Agent Chat (proposals, approve/reject/edit, coverage sidebar) | React Workbench | Agent Chat | None |
| Correction Review (audit trail, filtering, pagination, export) | React Workbench | Correction Review | Add disabled revert button; client-side search |
| Inline editable cells + batch toolbar | React Workbench | Issues Workbench | Add Hebrew publishers tab, agent normalization tab |
| Cluster cards with priority scoring | React Workbench | Issues Workbench | None |
| TanStack Query patterns (cache invalidation, optimistic updates) | React Workbench | All screens | None |
| Tailwind CSS design system (confidence color bands) | React Workbench | All screens | Binary color scheme for place/publisher |
| Candidate card layout (title/author/date/place/publisher/subjects) | Streamlit Chat UI | Chat, Query Debugger | Extract to shared CandidateCard component |
| Smart date display (single year vs range) | Streamlit Chat UI | Shared component | None |
| Place display (canonical + raw with dedup) | Streamlit Chat UI | Shared component | None |
| Follow-up suggestion buttons | Streamlit Chat UI | Chat | Render as chip buttons from suggested_followups |
| Example query shortcuts | Streamlit Chat UI | Chat | None |
| Primo URL generation (configurable institution) | Streamlit Chat UI + API | Shared PrimoLink component | Consolidate to single scheme via POST batch |
| TP/FP/FN/UNK labeling workflow | Streamlit QA Tool | Query Debugger | New API endpoints (B5-B8) |
| Issue tagging (predefined categories) | Streamlit QA Tool | Query Debugger | Include in B7 labels endpoint |
| False negative search (DB search for missing results) | Streamlit QA Tool | Query Debugger | Via diagnostic API |
| Gold set export + regression runner display | Streamlit QA Tool | Query Debugger | New API endpoints (B9-B10) |
| Query plan inspection (JSON tree) | Streamlit QA Tool | Query Debugger | Via diagnostic query-run response |
| Read-only DB table browser with column search | Streamlit QA Tool | Database Explorer | New API endpoints (B11-B12); expanded to 10 tables |
| Two-phase conversation model | FastAPI Backend | Chat | HTTP-only at launch |
| Intent interpretation with confidence scoring | FastAPI Backend | Chat | Overall confidence only (not per-filter) |
| Clarification flow (ambiguity detection) | FastAPI Backend | Chat | None |
| Collection overview queries | FastAPI Backend | Chat | None |
| Aggregation responses (top-N publishers/places/dates) | FastAPI Backend | Chat | Text-only until B2 forwards FacetCounts |
| CLI pipeline commands (parse_marc, query) | CLI | CLI (kept) | None |
| CLI regression subcommand (merged from app/qa.py) | QA Regression Runner | CLI | Merge into app/cli.py |

### DROP

| Feature | Source UI | Reason |
|---------|-----------|--------|
| Streamlit Chat UI (app/ui_chat/) entire app | Streamlit | Replaced by React Chat screen |
| Streamlit QA Tool (app/ui_qa/) entire app | Streamlit | Replaced by React Query Debugger + DB Explorer |
| QA Sessions page (guided session management) | Streamlit QA | Overly complex; standard query run history suffices |
| QA Wizard (_wizard.py, 808 lines) | Streamlit QA | Experimental, low usage; standard labeling flow covers same ground |
| app/qa.py standalone regression runner | CLI | Merged into CLI as regression subcommand |
| Dual Primo URL schemes (TAU + NLI hardcoded) | Streamlit Chat + API | Consolidated to single configurable scheme |
| WebSocket old single-phase path | FastAPI | Uses deprecated code path; either upgrade (B16) or remove |
| Per-filter confidence display | Planned Feature | Filter.confidence is always null; unbuildable |
| Four-band confidence visualization for place/publisher | React Workbench | Confidence is binary; medium and low bands are empty |
| Trend over time on Coverage Dashboard | Planned Feature | No snapshot mechanism exists; requires infrastructure |
| Before/after correction comparison | Planned Feature | No tracking infrastructure exists |
| Rich System Health features (log viewer, metrics, interaction viewer) | Planned Feature | No infrastructure exists; defer indefinitely |
| Separate QA database concept | Streamlit QA | Exposed through unified diagnostic API |
| Hardcoded localhost:8000 API URL | React Workbench | Replaced by environment variable via Vite config |
| RAG template remnants (chunk_rules.yaml, outlook_helper.yaml, completer.py) | Template | Irrelevant to MARC bibliographic records |

---

## Section 6: Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 1 | WebSocket two-phase upgrade complexity delays streaming | ELEVATED (confirmed: WS uses entirely different code path) | Delays Chat streaming by 3-5 days | Launch HTTP-only in Phase 1; defer WebSocket to Phase 4 (B16) |
| 2 | Query Debugger scope creep | High | Delays Phase 2 by 1+ week | Strict feature parity checklist with Streamlit QA; ADD features deferred to Phase 4+ |
| 3 | Diagnostic API endpoints take longer than estimated | CRITICAL (zero endpoints exist; 4-5 days minimum, not 2-3) | Blocks Phase 2 frontend entirely | Start frontend with MSW mocks; backend and frontend in parallel within Phase 2 |
| 4 | QA data migration -- existing labels need accessibility | Low | Historical data loss or inaccessibility | New diagnostic API reads from existing qa.db directly; no migration needed |
| 5 | Streamlit retirement breaks active workflows | Medium | Lost capability during transition | Enforce deletion criteria: every feature has working React replacement before code removal |
| 6 | Performance regression as React app grows to 9 screens | Low | Slower initial page load | Vite code splitting by route is automatic; monitor bundle size in Phase 4 |
| 7 | Landing page change confuses Workbench users | Low | User confusion during transition | Phase 0 preserves /operator/coverage as landing; Chat becomes / only in Phase 5 |
| 8 | Phase 2 aggregation charts unbuildable without facets | High (confirmed: FacetCounts computed but discarded) | Degraded Chat Phase 2 UX | Backend micro-task B2 completes in Phase 1 days 1-3 |
| 9 | Issues Workbench appears empty (only 121 low-confidence items) | High (confirmed) | Perceived low value of Workbench | Reframe as improvement opportunities; add Hebrew publishers (553) and agent normalization (4,366) tabs |
| 10 | Publisher variant matching gap (1/16 Elzevir records matched) | High (confirmed) | Chat users miss historical records for publisher queries | Document as known limitation; consider publisher-authority-aware search in future |
| 11 | Subject retry false broadening produces incorrect results | Medium (confirmed: "quantum physics" returns 67 philosophy books) | Misleading results without user warning | Forward QueryWarning to frontend (B3); display retry warning prominently; fix threshold (B22) |
| 12 | Phases 1 and 2 cannot run in parallel | Confirmed | Timeline extends by 1 week (7 -> 8 weeks) | Accepted; Phase 2 backend work is substantial and competes for developer attention |

---

## Section 6b: Known Limitations

Empirical findings that do not block implementation but must be accounted for in UI design:

1. **Frankfurt / Frankfurt am Main deduplication**: 78 records split across these two place forms. A future alias map entry should merge them, but the UI must display them as separate values until then.
2. **Imprint-less Faitlovitch manuscripts**: 38 records have no imprint data at all (no date, place, or publisher). CandidateCard must handle the empty-state gracefully -- display "No imprint data" rather than blank fields.
3. **LOW_CONFIDENCE warning is dead code**: The `LOW_CONFIDENCE` QueryWarning can never fire because `Filter.confidence` is always null in practice. No UI handling is needed for this warning type; it can be ignored in warning display logic.

---

## Section 7: Verification Stamp

- **Verification date**: 2026-03-23
- **Checks passed**: 22 of 25
- **Checks with warnings**: 4 (data shape simplifications corrected, CLAUDE.md stale docs)
- **Missing findings addressed**: 5 (added as Known Limitations)
- **Statement**: This plan has been verified against empirical database probes (report 08), pipeline tests (report 09), API response analysis (report 10), cross-reference alignment checks (report 11), and refinement corrections (report 12).
- **Final line**: This document supersedes all reports in `reports/` and is the sole source of truth for UI implementation.

---

## Section 8: Appendix -- Contradiction Log

All contradictions between original design reports and empirical verification findings, with resolutions applied throughout this document.

| # | Topic | Original Assumption | Empirical Finding | Resolution |
|---|-------|--------------------|--------------------|------------|
| 1 | WebSocket streaming | Reports 06-07 assume WebSocket supports two-phase flow with phase transitions, confidence, and facets from Phase 1 | WebSocket uses old single-phase compile_query() path. No intent agent, no Phase 2, no facets, no phase/confidence. Completely separate code path from HTTP /chat. | Launch Chat HTTP-only; defer WebSocket to Phase 4 after handler upgrade (B16: 2-3 days) |
| 2 | Per-filter confidence | Reports 06-07 specify per-filter confidence visualization in Chat and Query Debugger | Filter.confidence is always null in all tested queries. LLM does not produce per-filter confidence. LOW_CONFIDENCE warning can never fire. | Drop per-filter confidence from all screens. Show only overall ChatResponse.confidence. |
| 3 | Confidence distribution shape | Report 06 assumes four meaningful confidence bands with records across all bands | Place and publisher confidence is BINARY -- records are either <0.5 or >=0.95, with 0.5-0.95 range completely empty. | Replace four-band with binary (resolved/unresolved) for place and publisher. Keep graduated bands only for dates (0.8-0.95 has 1,306 records). |
| 4 | Issues Workbench volume | Reports 06-07 assume substantial volume of issues requiring triage | Only 121 total low-confidence records (69 dates + 19 places + 33 publishers). Workbench will be nearly empty. | Reframe as improvement opportunities. Real gaps: 553 Hebrew publishers, 4,366 un-aliased agents, 202 unresearched authorities, 44.1% "other" agent roles. |
| 5 | Diagnostic API endpoints | Reports 06-07 treat diagnostic endpoints as minor additions; estimated 2-3 days | ZERO diagnostic endpoints exist. No /diagnostics/* at all. QA database has no HTTP layer. | Backend expanded to 4-5 days. Phase 2 must be sequential after Phase 1. Timeline extended from 7 to 8 weeks. |
| 6 | FacetCounts in ChatResponse | Report 06 assumes Phase 2 aggregation charts can be built from API data | FacetCounts computed by QueryService but NOT serialized into ChatResponse. Discarded before reaching frontend. | Backend micro-task B2: forward FacetCounts in ChatResponse.metadata (2-4 hours). |
| 7 | Execution timing exposure | Report 06 specifies execution timing display in Chat | execution_time_ms computed by QueryService but NOT exposed in ChatResponse. Logged internally only. | Backend micro-task B1: add to ChatResponse.metadata (1-2 hours). |
| 8 | Primo URLs on Candidates | Report 06 assumes candidate titles link directly to Primo | Primo URLs NOT on Candidate objects. Require separate API call (batch or per-record). | Use POST /metadata/primo-urls batch call; cache client-side. Alternatively B4: add primo_url to Candidate model. |
| 9 | Number of database tables | Report 06 lists 6 tables for DB Explorer | Database has 10 tables (adds notes, publisher_authorities, publisher_variants, authority_enrichment). | DB Explorer expanded to 10 tables. |
| 10 | Phases 1 and 2 parallelism | Report 07 states Phases 1 and 2 can overlap | Phase 2 backend work is substantial (all diagnostic endpoints from scratch); should not compete with Phase 1 micro-tasks. | Sequential, not parallel. Timeline extended by 1 week. |
| 11 | CorrectionRequest.field coverage | Reports imply corrections work for all four fields | CorrectionRequest.field accepts only place, publisher, agent -- NOT date. | B17 (Phase 4): add date support. Display date issues as read-only until then. |
| 12 | Corrections history filtering | Report 06 specifies filter bar with field, source, search, date range | GET /metadata/corrections/history only supports field filter. No search, source, or date range. | Client-side filtering approximates until B18 (Phase 4). |
| 13 | QueryPlan in API response | Reports assume QueryPlan accessible from ChatResponse | QueryPlan NOT in ChatResponse. Stored in session messages, accessible via GET /sessions/{session_id}. | Workaround: fetch session, extract plan. Or add plan to diagnostics query-run response. |
| 14 | Place normalization methods | CLAUDE.md mentions base_clean (0.80) and alias_map (0.95) as place methods | Only 2 methods in production: place_alias_map (99.3%) and missing (0.7%). No base_clean records for places. | Confidence slider for places is meaningless. Replace with method-based filtering. |
| 15 | Agent normalization state | Reports 01-07 focus on date/place/publisher normalization gaps | ALL 4,366 agents use base_clean only. 0% alias-mapped. 44.1% agent roles are "other". Largest normalization gap. | Lead Coverage Dashboard with agent gaps. Add agent normalization tab to Workbench. |
| 16 | Publisher authority completeness | Reports mention 228 authorities as working system | 227 authorities but 202 (89%) are unresearched stubs. authority_enrichment table has 0 rows. Only 18 classified as printing_house. | Publisher screen emphasizes research workflow, not simple CRUD. |

**Total contradictions resolved**: 16
