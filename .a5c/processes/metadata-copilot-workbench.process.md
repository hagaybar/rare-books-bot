# Metadata Co-pilot Workbench - Process Plan

## Vision

Build an agent-driven **Metadata Quality Workbench** where specialist LLM agents analyze normalization gaps in a MARC-based rare books bibliographic database, propose evidence-grounded fixes, and a librarian approves/rejects corrections via an interactive React dashboard with a Human-In-The-Loop (HITL) feedback loop.

This is fundamentally different from a passive dashboard. The system has an **active co-pilot** that does the detective work (clustering, cross-referencing, proposing), while the librarian makes the final call.

## Context: Current State

The rare-books-bot project has a solid data pipeline:
- **M1**: MARC XML parsing to canonical JSONL
- **M2**: Rule-based normalization (dates, places, publishers, agents) with confidence scores
- **M3**: SQLite indexing with 20+ indexes on normalized fields
- **M4/M5**: LLM-based query compilation, SQL execution, evidence extraction
- **M6**: Chat UI (Streamlit) with two-phase conversations

**The problem**: Normalization is rule-complete but coverage-incomplete. There's no systematic way to identify gaps, prioritize fixes, or close the feedback loop between data analysis and alias map updates.

## Architecture Overview

```
React Frontend ──REST API──> FastAPI Backend ──> Grounding Layer + Specialist Agents + Action Layer
     │                           │                    │                │               │
  Dashboard              /metadata/*           M3 Database      LLM Reasoning     Alias Maps
  Workbench              /metadata/agent/*      Alias Maps       Strict Prompts    Review Log
  Agent Chat                                    Country Codes    Caching           Re-index
  Review                                        Authority URIs                     Coverage
```

See `metadata-copilot-workbench.diagram.md` for detailed architecture diagrams.

---

## Milestones

### Milestone 1: Normalization Coverage Audit (Backend)

**Goal**: Build deterministic analysis of current normalization state — where are the gaps, how big, what type.

| Task | Description | Deliverable | Dependencies |
|------|-------------|-------------|--------------|
| 1.1 | Build audit module | `scripts/metadata/audit.py` - CoverageReport per field with confidence band distributions | M3 schema |
| 1.2 | Run baseline audit | `data/metadata/baseline_audit.json` - Initial coverage snapshot | 1.1 |
| 1.3 | Build gap clustering | `scripts/metadata/clustering.py` - Group unmapped values by type (Latin, Hebrew, frequency) | 1.1 |

**Key data structures**:
- `CoverageReport`: per_field (date, place, publisher, agent), each with confidence_bands, method_distribution, total_records, unmapped_count
- `Cluster`: cluster_id, field, cluster_type, raw_values (with frequencies), proposed_canonical, priority_score

**Breakpoint**: Review audit results and gap clusters before proceeding.

---

### Milestone 2: FastAPI Metadata API (Backend)

**Goal**: REST endpoints that expose normalization quality data and accept corrections.

| Task | Description | Deliverable | Dependencies |
|------|-------------|-------------|--------------|
| 2.1 | Metadata API router | `app/api/metadata.py` - coverage, issues, unmapped, methods, clusters endpoints | M1 |
| 2.2 | Corrections endpoint | POST /metadata/corrections - writes to alias maps with atomic file operations | 2.1 |
| 2.3 | Primo URL endpoint | POST /metadata/primo-urls - batch Primo link generation | 2.1 |
| 2.4 | API tests | `tests/app/test_metadata_api.py` | 2.1-2.3 |
| 2.5 | Run API tests | Shell: pytest verification | 2.4 |

**Endpoints**:
| Method | Path | Purpose |
|--------|------|---------|
| GET | /metadata/coverage | Overall coverage stats per field |
| GET | /metadata/issues | Records with low-confidence normalizations (paginated, filterable) |
| GET | /metadata/unmapped | Raw values without canonical mapping (sorted by frequency) |
| GET | /metadata/clusters | Gap clusters from clustering module |
| GET | /metadata/methods | Distribution of normalization methods |
| POST | /metadata/corrections | Submit a single correction |
| POST | /metadata/corrections/batch | Batch corrections |
| GET | /metadata/corrections/history | Correction audit trail |
| POST | /metadata/primo-urls | Batch Primo URL generation |

**Breakpoint**: Review API before building frontend.

---

### Milestone 3: Specialist Metadata Agents (Backend)

**Goal**: Build field-specific agents that analyze gaps and propose fixes using grounding + LLM reasoning.

| Task | Description | Deliverable | Dependencies |
|------|-------------|-------------|--------------|
| 3.1 | Agent harness | `scripts/metadata/agent_harness.py` - shared grounding layer + LLM interface | M1, M2 |
| 3.2 | PlaceAgent | `scripts/metadata/agents/place_agent.py` - Latin toponyms, Hebrew, country codes | 3.1 |
| 3.3 | DateAgent | `scripts/metadata/agents/date_agent.py` - Hebrew calendar, Latin conventions | 3.1 |
| 3.4 | PublisherAgent | `scripts/metadata/agents/publisher_agent.py` - printer dynasties, Latin variants | 3.1 |
| 3.5 | AgentAgent (Names) | `scripts/metadata/agents/name_agent.py` - authority URIs, VIAF/NLI | 3.1 |
| 3.6 | Agent tests | `tests/scripts/metadata/agents/` | 3.2-3.5 |
| 3.7 | Agent chat API | POST /metadata/agent/chat + WS /ws/metadata/agent | 3.1-3.5, M2 |

**Agent Architecture** (each agent has):

1. **Grounding Layer** (deterministic, no LLM):
   - Query DB for gaps in its field
   - Cross-reference alias maps, country codes, authority URIs
   - Cluster values by pattern, script, frequency

2. **Reasoning Layer** (LLM-assisted, strict prompts):
   - Propose canonical mappings with evidence
   - Explain why values are related
   - Suggest investigation strategies
   - Responses cached in JSONL

3. **Key constraint**: LLM system prompts must include existing alias map vocabulary, require structured JSON responses, and return confidence < 0.7 when uncertain.

**Agent Capabilities**:

| Agent | Knows | Example Output |
|-------|-------|----------------|
| PlaceAgent | Latin toponyms, Hebrew names, historical changes, country codes | "Lugduni Batavorum with country=ne is Leiden (Latin genitive)" |
| DateAgent | Hebrew calendar, Gematria, Latin conventions, circa patterns | "תק"ע = Hebrew 5570 = 1810 CE (confidence 0.85)" |
| PublisherAgent | Printer dynasties, Latin/vernacular variants | "typis Elzevirianis = Elzevir press (8 records)" |
| AgentAgent | VIAF/NLI authority, name forms | "Validates name against authority canonical form" |

**Breakpoint**: Review agents before frontend integration.

---

### Milestone 4: React Frontend (Frontend)

**Goal**: Interactive dashboard where the librarian sees gaps, reviews proposals, and approves corrections.

| Task | Description | Deliverable | Dependencies |
|------|-------------|-------------|--------------|
| 4.1 | React scaffold | `frontend/` - Vite + TypeScript + TanStack Table + Recharts + Tailwind | None |
| 4.2 | Dashboard page | Coverage charts, gap cards, trends | 4.1, M2 |
| 4.3 | Workbench page | Data tables with inline edit, batch ops, Primo links | 4.1, M2 |
| 4.4 | Agent Chat page | Per-field agent conversations with approve/reject/edit | 4.1, M3 |
| 4.5 | Review page | Corrections history, undo, export | 4.1, M2 |

**Pages**:

1. **Dashboard** - Summary cards, coverage bars per field, gap counts, method distribution charts. Gap cards are clickable -> navigate to Workbench filtered by field.

2. **Workbench** - TanStack Table with columns: MMS ID, Raw Value, Normalized, Confidence, Method, Country Code, Primo Link. Sortable, filterable, paginated. Inline editing. Batch operations toolbar.

3. **Agent Chat** - Select specialist agent, chat interface with structured responses (proposals table with Approve/Reject/Edit per row), coverage sidebar updating in real-time.

4. **Review** - Timeline of corrections, filter by field/source/date, impact metrics, undo capability, CSV/JSON export.

**Stack**: React 18, TypeScript, Vite, TanStack Table, TanStack Query, React Router, Tailwind CSS, Recharts.

**Breakpoint**: Review frontend before integration testing.

---

### Milestone 5: Integration & Feedback Loop

**Goal**: End-to-end testing of the complete workflow: audit -> cluster -> propose -> approve -> update -> re-index -> verify.

| Task | Description | Deliverable | Dependencies |
|------|-------------|-------------|--------------|
| 5.1 | Feedback loop | `scripts/metadata/feedback_loop.py` - approve -> alias map -> re-normalize -> coverage update | M2, M3 |
| 5.2 | Integration test | `tests/integration/test_metadata_workbench.py` - full workflow validation | All |
| 5.3 | Review log | `scripts/metadata/review_log.py` - audit trail + negative signal for agents | M3, M5.1 |

**The Feedback Loop**:
```
Approve correction
  -> Write to alias map (atomic)
  -> Re-normalize affected records (incremental, not full rebuild)
  -> Update M3 database
  -> Refresh coverage stats
  -> Log to review_log.jsonl
```

**Integration Test Flow**:
1. Run coverage audit -> verify report structure
2. Run gap clustering -> verify clusters created
3. Call PlaceAgent -> verify proposals returned
4. Submit correction via API -> verify alias map updated
5. Trigger feedback loop -> verify DB updated
6. Re-run audit -> verify coverage improved

**Breakpoint**: Review integration before finalization.

---

### Milestone 6: Documentation & Polish

| Task | Description | Deliverable | Dependencies |
|------|-------------|-------------|--------------|
| 6.1 | Documentation | CLAUDE.md update + docs/metadata_workbench.md | All |

---

## Key Design Principles

1. **Agent does detective work, librarian makes the call** - No silent data changes
2. **Grounding before reasoning** - Deterministic analysis first, LLM only when needed
3. **Strict LLM harness** - System prompts include vocabulary, require structured JSON, demand confidence scores
4. **Reversible corrections** - Alias maps are version-controlled, review log tracks everything, undo is possible
5. **Incremental pipeline** - Re-normalization doesn't require full rebuild
6. **Negative signal** - Rejected proposals are logged so agents don't re-propose them
7. **Evidence-based** - Every proposal includes: source evidence, affected record count, Primo links for verification

## Files Created/Modified

**New directories**:
- `scripts/metadata/` - Audit, clustering, agent harness, feedback loop
- `scripts/metadata/agents/` - Specialist agents (place, date, publisher, name)
- `frontend/` - React SPA
- `data/metadata/` - Audit reports, review logs, LLM cache
- `tests/scripts/metadata/` - Unit tests
- `tests/integration/` - Integration tests

**Modified files**:
- `app/api/main.py` - Register metadata router
- `CLAUDE.md` - Add workbench documentation

## Estimated Scope

- **Backend**: ~2000-3000 lines Python (audit, clustering, agents, API, feedback loop)
- **Frontend**: ~2000-3000 lines TypeScript/React (4 pages + components + API client)
- **Tests**: ~1000-1500 lines (unit + integration)
- **6 milestones, ~25 tasks, 5 breakpoints**
