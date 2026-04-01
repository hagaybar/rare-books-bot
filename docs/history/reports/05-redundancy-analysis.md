# Feature Overlap and Redundancy Analysis

**Date:** 2026-03-23
**Scope:** All 6 UI surfaces in the Rare Books Bot project

## 1. UI Surface Inventory

| ID | Surface | Technology | Primary Purpose |
|----|---------|-----------|-----------------|
| CLI | `app/cli.py` | Typer | Pipeline operations (parse, index, query) + session management |
| API-HTTP | `app/api/main.py` POST /chat | FastAPI | Two-phase conversational query (intent agent + exploration) |
| API-WS | `app/api/main.py` WS /ws/chat | FastAPI WebSocket | Streaming query results with progress |
| Chat-UI | `app/ui_chat/main.py` | Streamlit | Conversational front-end over API-HTTP |
| QA-Tool | `app/ui_qa/` | Streamlit (6 pages) | Query validation, labeling, regression |
| Workbench | `frontend/` | React SPA (4 pages) | Metadata quality HITL via /metadata/* API |

---

## 2. Feature Comparison Matrix

### 2.1 Query Execution

| Feature | CLI | API-HTTP | API-WS | Chat-UI | QA-Tool | Workbench |
|---------|-----|----------|--------|---------|---------|-----------|
| NL query compilation (LLM) | Yes | Yes | Yes | via API | Yes | -- |
| SQL execution against bibliographic.db | Yes | Yes | Yes | via API | Yes | -- |
| CandidateSet + Evidence output | Yes | Yes | Yes | via API | Yes | -- |
| Query plan display | Yes (file) | Yes (JSON) | Yes | -- | Yes (inline) | -- |
| Facet computation | -- | Yes | -- | via API | -- | -- |
| Result streaming/batching | -- | -- | Yes (batches of 10) | -- | -- | -- |
| Intent interpretation with confidence | -- | Yes (interpret_query) | -- | via API | -- | -- |
| Ambiguity/clarification detection | -- | Yes (both phases) | Yes (old path) | via API | -- | -- |
| Collection overview queries | -- | Yes | -- | via API | -- | -- |

### 2.2 Session Management

| Feature | CLI | API-HTTP | API-WS | Chat-UI | QA-Tool | Workbench |
|---------|-----|----------|--------|---------|---------|-----------|
| Session create/get/expire | Yes | Yes | Yes | via API | Own impl | -- |
| Session database | data/chat/sessions.db | data/chat/sessions.db | data/chat/sessions.db | via API | data/qa/qa.db | -- |
| Multi-turn conversation | Yes (--session-id) | Yes (two-phase) | Yes | Yes | -- | -- |
| Phase tracking (query def / exploration) | -- | Yes | -- | via API | -- | -- |
| Active subgroup persistence | -- | Yes | -- | via API | -- | -- |

### 2.3 Corpus Exploration (Phase 2)

| Feature | CLI | API-HTTP | API-WS | Chat-UI | QA-Tool | Workbench |
|---------|-----|----------|--------|---------|---------|-----------|
| Aggregation (top publishers, places) | -- | Yes | -- | via API | -- | -- |
| Metadata questions (count, earliest) | -- | Yes | -- | via API | -- | -- |
| Refinement (narrow subgroup) | -- | Yes | -- | via API | -- | -- |
| Comparison (Paris vs London) | -- | Yes | -- | via API | -- | -- |
| Entity enrichment (Wikidata/VIAF) | -- | Yes | -- | via API | -- | -- |

### 2.4 Metadata Quality & Coverage

| Feature | CLI | API-HTTP | API-WS | Chat-UI | QA-Tool | Workbench |
|---------|-----|----------|--------|---------|---------|-----------|
| Coverage statistics per field | -- | /metadata/coverage | -- | -- | -- | Dashboard |
| Low-confidence records | -- | /metadata/issues | -- | -- | -- | Workbench |
| Unmapped values | -- | /metadata/unmapped | -- | -- | -- | Workbench |
| Method distribution | -- | /metadata/methods | -- | -- | -- | Dashboard |
| Gap clustering | -- | /metadata/clusters | -- | -- | -- | Workbench |
| Correction submission | -- | /metadata/corrections | -- | -- | -- | Workbench |
| Batch corrections | -- | /metadata/corrections/batch | -- | -- | -- | Workbench |
| Correction history | -- | /metadata/corrections/history | -- | -- | -- | Review page |
| Agent chat (specialist agents) | -- | /metadata/agent/chat | -- | -- | -- | AgentChat |
| Publisher authorities | -- | /metadata/publishers | -- | -- | -- | -- |

### 2.5 Quality Assurance / Regression

| Feature | CLI | API-HTTP | API-WS | Chat-UI | QA-Tool | Workbench |
|---------|-----|----------|--------|---------|---------|-----------|
| Query labeling (TP/FP/FN/UNK) | -- | -- | -- | -- | Run+Review, Wizard | -- |
| Issue tagging | -- | -- | -- | -- | Run+Review, Dashboard | -- |
| False negative search | -- | -- | -- | -- | Find Missing page | -- |
| Gold set export | -- | -- | -- | -- | Gold Set page | -- |
| Regression test execution | app/qa.py | -- | -- | -- | Gold Set page | -- |
| QA sessions (guided workflow) | -- | -- | -- | -- | Sessions + Wizard | -- |
| QA dashboard (issue analytics) | -- | -- | -- | -- | Dashboard page | -- |

### 2.6 Database Browsing

| Feature | CLI | API-HTTP | API-WS | Chat-UI | QA-Tool | Workbench |
|---------|-----|----------|--------|---------|---------|-----------|
| Read-only table browsing | -- | -- | -- | -- | DB Explorer | -- |
| Schema inspection | -- | -- | -- | -- | DB Explorer | -- |
| Column search/filter | -- | -- | -- | -- | DB Explorer | -- |
| Record-level detail (via issues) | -- | -- | -- | -- | -- | Workbench |

### 2.7 Primo URL Generation

| Feature | CLI | API-HTTP | API-WS | Chat-UI | QA-Tool | Workbench |
|---------|-----|----------|--------|---------|---------|-----------|
| Primo URL generation | -- | /metadata/primo-urls, /metadata/records/{id}/primo | -- | Yes (TAU) | -- | Yes (NLI) |
| Primo base URL | -- | TAU (default, env-configurable) | -- | TAU (hardcoded) | -- | NLI (hardcoded) |
| Institution | -- | 972TAU_INST | -- | 972TAU_INST | -- | 972NNL_INST |

### 2.8 Response Formatting

| Feature | CLI | API-HTTP | API-WS | Chat-UI | QA-Tool | Workbench |
|---------|-----|----------|--------|---------|---------|-----------|
| NL response formatting | -- | Yes (formatter.py) | Yes (formatter.py) | renders API response | -- | -- |
| Follow-up suggestions | -- | Yes (generate_followups) | Yes | Yes (buttons) | -- | -- |
| Evidence display | Yes (sample) | Yes (formatted) | Yes | Yes (in expander) | Yes (labels) | -- |

---

## 3. Exact Duplicates

### D1: Regression Test Runner
- **Locations:** `app/qa.py` (CLI) and `app/ui_qa/pages/4_gold_set.py` (Streamlit)
- **Details:** Both load `gold.json`, iterate queries, compile + execute, compare expected_includes/excludes vs actual results. The QA Tool version adds a progress bar and Streamlit display; the CLI version supports `--verbose` and `--log-file`. Both use the same gold set format.
- **Recommendation:** Keep the CLI version (`app/qa.py`) as the canonical regression runner for CI. The QA Tool's regression page should call the CLI runner or shared function and display results, not re-implement the logic.

### D2: Primo URL Generation (TAU Variant)
- **Locations:** `app/ui_chat/config.py` and `app/api/metadata.py` (lines 892-936)
- **Details:** Both generate identical TAU Primo URLs with identical parameters. The metadata.py comment explicitly says "matches app/ui_chat/config.py". This is copy-pasted code.
- **Recommendation:** Extract to a single shared module (e.g., `scripts/utils/primo.py`). Both consumers import from there.

### D3: Query Execution Pipeline
- **Locations:** CLI (`app/cli.py` query command), API-HTTP (`app/api/main.py` /chat), API-WS (`app/api/main.py` /ws/chat), QA Tool (`app/ui_qa/pages/1_run_review.py`)
- **Details:** Four places that instantiate `QueryService`, call `execute()` or `execute_plan()`, and process `CandidateSet`. The CLI uses `QueryService.execute()`, the HTTP endpoint uses intent agent + `execute_plan()`, the WebSocket uses `compile_query()` + `execute_plan()` directly, and the QA Tool uses `QueryService.execute()`.
- **Recommendation:** The CLI and QA Tool both properly use the unified `QueryService`. The API-WS endpoint directly calls lower-level functions (`compile_query`, `execute_plan`) bypassing the intent agent - this is an architectural divergence, not just a duplicate.

---

## 4. Partial Overlaps

### O1: HTTP /chat vs WebSocket /ws/chat - Two Conversation Implementations
- **Difference:** The HTTP endpoint uses the full two-phase architecture (intent agent with confidence scoring, Phase 2 corpus exploration with aggregation/enrichment/refinement). The WebSocket endpoint uses the older path: `compile_query()` directly, no intent agent, no Phase 2, no exploration. They produce fundamentally different conversation experiences.
- **Impact:** A user on WebSocket gets single-shot query results. A user on HTTP gets multi-turn exploration with aggregation, entity enrichment, and refinement. The WebSocket path is frozen at an earlier stage of development.
- **Recommendation:** Either upgrade WebSocket to use the same two-phase architecture, or deprecate it. Streaming can be layered on top of the HTTP path (e.g., SSE or chunked responses) without maintaining a separate conversation engine.

### O2: QA Tool Dashboard vs Workbench Dashboard
- **Difference:** The QA Dashboard (`app/ui_qa/pages/3_dashboard.py`) tracks query-level quality metrics: TP/FP/FN counts, issue tag distribution, worst queries. The Workbench Dashboard (`frontend/src/pages/Dashboard.tsx`) tracks field-level normalization quality: confidence distributions, method breakdowns, pie charts per field. These are complementary analytics over different quality dimensions.
- **Impact:** A user wanting a holistic quality view must look at two separate UIs. However, the two dashboards answer genuinely different questions: "Are my queries returning correct results?" vs "Is my metadata well-normalized?"
- **Recommendation:** These are not true duplicates. Keep both, but consider adding a cross-link or embedding key Workbench metrics in the QA Dashboard (and vice versa) when they are eventually unified.

### O3: QA DB Explorer vs Workbench Issues View
- **Difference:** The DB Explorer (`app/ui_qa/pages/5_db_explorer.py`) provides generic read-only browsing of all bibliographic tables with column search. The Workbench issues view shows only records below a confidence threshold, with inline editing and correction submission. Different purposes but both show records from the same database.
- **Impact:** Low. These serve different workflows: debugging/exploration vs correction authoring.
- **Recommendation:** No immediate action. The DB Explorer is a development utility; the Workbench issues view is a workflow tool.

### O4: Primo URLs - TAU vs NLI
- **Difference:** Chat UI and API generate TAU Primo URLs (`tau.primo.exlibrisgroup.com`, VID `972TAU_INST`). The Workbench hardcodes NLI Primo URLs (`primo.nli.org.il`, VID `972NNL_INST`). These point to different discovery layer instances of the same records.
- **Impact:** Users see different Primo links depending on which UI they use. This is confusing and may indicate that the project serves two institutions or that one URL scheme is outdated.
- **Recommendation:** Determine the canonical Primo instance. Make it configurable via environment variable or a shared config. The API metadata endpoint already supports `base_url` override and `PRIMO_BASE_URL` env var - extend this pattern to the Workbench.

### O5: Session Management - Chat Sessions vs QA Sessions
- **Difference:** Chat sessions (`scripts/chat/session_store.py` + `data/chat/sessions.db`) track multi-turn conversations with phase transitions, active subgroups, and message history. QA sessions (`app/ui_qa/db.py` + `data/qa/qa.db`) track guided testing workflows with steps, session types (SMOKE/RECALL), and query-label associations. These are fundamentally different session concepts.
- **Impact:** Low. The word "session" is overloaded but the implementations are appropriately separate.
- **Recommendation:** No merge needed. These represent genuinely different concepts. Could rename QA sessions to "QA workflows" for clarity.

---

## 5. Historical / Legacy Features

### H1: WebSocket /ws/chat Endpoint
- **Reason:** Built as CB-005 (Streaming Responses milestone) before the two-phase conversation architecture (intent agent, corpus exploration) was implemented. It represents the pre-Phase-2 architecture frozen in time. The HTTP endpoint has since been upgraded with intent interpretation, confidence scoring, and corpus exploration.
- **Evidence:** WebSocket still calls `compile_query()` directly (line 1129) while HTTP uses `interpret_query()` (line 453). WebSocket has no concept of ConversationPhase or ActiveSubgroup.

### H2: CLI Session Commands (chat-init, chat-history, chat-cleanup)
- **Reason:** Built during M6 (CB-001) as the first session management proof-of-concept before the API was available. Now that the API handles session lifecycle, these CLI commands are primarily useful for debugging or admin operations, not for end-user interaction.

### H3: CLI Query --session-id Flag
- **Reason:** Added to enable session tracking from the command line before the API existed. Now that conversations happen through the API, this flag is rarely used. The CLI query command itself remains useful for scripting and debugging, but session tracking in CLI is vestigial.

### H4: QA Tool DB Explorer
- **Reason:** Built as a development aid to inspect bibliographic tables when no other browsing mechanism existed. With the Workbench now providing structured views of the same data (issues, clusters, corrections), the generic DB Explorer is primarily a debugging tool.

---

## 6. Features That Fragment the User Experience

### F1: NL Query Is Available in 4 Places
- **Feature:** Natural language query execution
- **Impact:** A user can run queries via CLI, Chat UI, QA Tool Run+Review, or the API directly. Each provides different post-query capabilities: CLI gives file output, Chat UI gives follow-ups and candidate browsing, QA Tool gives labeling, API gives structured JSON. There is no clear guidance on which to use when. New users may try the wrong one and miss critical features.
- **Recommendation:** Define a clear purpose for each entry point. CLI = scripting/automation. Chat UI = end-user discovery. QA Tool = internal quality testing. API = integration point. Document this mapping prominently.

### F2: Two Primo URL Schemes
- **Feature:** Links to original catalog records
- **Impact:** Records link to TAU Primo in the Chat UI but NLI Primo in the Workbench. If a user follows a link from each UI, they land on different systems. This undermines trust in the system's consistency.
- **Recommendation:** Consolidate to one configurable Primo URL generator. Let deployment configuration determine the institution.

### F3: Two Query Conversation Paths (HTTP vs WebSocket)
- **Feature:** Conversational query interface
- **Impact:** HTTP provides the rich two-phase experience (exploration, aggregation, enrichment). WebSocket provides only basic query + clarification. If a client developer picks WebSocket for its streaming benefits, they lose Phase 2 entirely, with no warning or documentation of this gap.
- **Recommendation:** Deprecate the standalone WebSocket path. If streaming is needed, implement Server-Sent Events (SSE) on the HTTP path or upgrade the WebSocket to use the same two-phase handler.

### F4: Correction Workflows Split Across UIs
- **Feature:** Improving metadata quality
- **Impact:** The QA Tool identifies query-level issues (FP/FN caused by bad normalization). The Workbench identifies record-level issues (low-confidence normalizations, clusters). There is no bridge: when a QA tester finds a false positive caused by a bad place normalization (tagged `NORM_PLACE_BAD`), they cannot submit a correction from the QA Tool - they must switch to the Workbench or AgentChat. The feedback loop is broken across UI boundaries.
- **Recommendation:** Add a lightweight correction submission capability to the QA Tool, or add deep links from QA issue tags to the Workbench correction view.

---

## 7. Assessment: "Useful Because It Exists" vs "Important Because It Serves the Goal"

| Feature | Verdict | Rationale |
|---------|---------|-----------|
| CLI query | **Important** | Enables scripting, CI integration, debugging |
| API HTTP /chat | **Important** | Primary conversation engine with full two-phase architecture |
| API WS /ws/chat | **Useful** (legacy) | Only value is streaming; could be replaced by SSE on HTTP |
| Chat UI (Streamlit) | **Important** | Primary end-user discovery interface |
| QA Tool | **Important** | Only system for systematic query quality measurement |
| Workbench (React) | **Important** | Only system for metadata quality improvement workflow |
| CLI chat-init/history/cleanup | **Useful** (admin) | Debugging utility; API handles lifecycle |
| CLI --session-id flag | **Useful** (legacy) | Vestigial; conversations happen through API |
| DB Explorer (QA) | **Useful** (debug) | Development aid; not part of any production workflow |
| Regression in QA Gold Set page | **Useful** (duplicate) | Duplicates `app/qa.py`; adds only progress bar |
| TAU Primo URLs | **Useful** (fragmented) | One of two competing URL schemes |
| NLI Primo URLs | **Useful** (fragmented) | One of two competing URL schemes |

---

## 8. Summary of Recommended Actions

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| 1 | Extract shared Primo URL module; make institution configurable | Low | Eliminates code duplication and user confusion |
| 2 | Deprecate WebSocket /ws/chat or upgrade to two-phase architecture | Medium | Eliminates divergent conversation paths |
| 3 | Extract regression runner to shared function; QA Tool calls it | Low | Single source of truth for regression logic |
| 4 | Document which UI to use for which purpose | Low | Reduces user confusion from 4 query entry points |
| 5 | Add correction deep-links from QA Tool to Workbench | Medium | Bridges the QA-to-correction feedback gap |
| 6 | Consider CLI session commands as admin-only; document accordingly | Low | Sets correct expectations |
