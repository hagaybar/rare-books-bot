# Two-Phase Conversational Research Assistant - Implementation TODO

**Created**: 2026-01-15
**Status**: Stage 4 Complete (Core) - Ready for Stage 5 (Advanced Features)
**Last Updated**: 2026-01-16

---

## Overview

Transform the chatbot into a two-phase conversational research assistant:
- **Phase 1**: Query Definition with confidence scoring (threshold 0.85)
- **Phase 2**: Corpus Exploration with aggregation, enrichment, and recommendations

---

## Stage 1: Intent Agent Foundation ✅ COMPLETE

### 1.1 Core Models
- [x] Create `scripts/chat/intent_agent.py` with base structure
- [x] Define `IntentInterpretation` Pydantic model:
  - `overall_confidence: float` (0.0-1.0)
  - `explanation: str` (natural language)
  - `uncertainties: List[str]`
  - `query_plan: QueryPlan`
  - `proceed_to_execution: bool`
- [x] Add `ConversationPhase` enum to `scripts/chat/models.py`:
  - `QUERY_DEFINITION`
  - `CORPUS_EXPLORATION`
- [x] Add `ActiveSubgroup` model to `scripts/chat/models.py`:
  - `candidate_set: CandidateSet`
  - `defining_query: str`
  - `filter_summary: str`
  - `created_at: datetime`
- [x] Add `ExplorationIntent` enum (for Phase 2)
- [x] Add `UserGoal` model (for need elicitation)

### 1.2 Intent Agent LLM Integration
- [x] Design intent agent system prompt with confidence scoring rules
- [x] Implement `interpret_query()` function using OpenAI Responses API
- [x] Implement `generate_clarification_prompt()` for low-confidence cases
- [x] Add caching for intent interpretations (`data/intent_cache.jsonl`)
- [x] Implement `format_interpretation_for_user()` helper

### 1.3 Session Store Updates
- [x] Add `phase` column to `chat_sessions` table in schema.sql
- [x] Create `active_subgroups` table in schema.sql
- [x] Create `user_goals` table in schema.sql
- [x] Implement `get_phase()` method in SessionStore
- [x] Implement `update_phase()` method in SessionStore
- [x] Implement `set_active_subgroup()` method
- [x] Implement `get_active_subgroup()` method
- [x] Implement `add_user_goal()` method
- [x] Implement `get_user_goals()` method
- [ ] Write migration script for existing sessions (deferred - schema auto-migrates)

### 1.4 Unit Tests for Stage 1
- [ ] Test IntentInterpretation model validation
- [ ] Test confidence threshold logic (>= 0.85 proceeds)
- [ ] Test clarification prompt generation
- [ ] Test session phase tracking
- [ ] Test active subgroup storage/retrieval

**Note**: Unit tests deferred. All 16 existing API tests pass with new code.

---

## Stage 2: Phase 1 API Integration ✅ COMPLETE

### 2.1 Chat Endpoint Restructure
- [x] Refactor `/chat` endpoint to check current phase
- [x] Implement `handle_query_definition_phase()` function
- [x] Add confidence check before query execution
- [x] Implement phase transition logic (query_definition → corpus_exploration)
- [x] Return explanation of understanding with results

### 2.2 Response Formatting Updates
- [x] Update ChatResponse to include phase metadata
- [x] Add exploration prompt when transitioning to Phase 2:
  "What would you like to know about this collection?"
- [x] Include confidence score in response metadata

### 2.3 Integration Tests for Phase 1
- [x] Test low-confidence query returns clarification
- [x] Test high-confidence query executes and transitions
- [ ] Test multi-turn clarification flow (deferred)
- [ ] Test session phase persistence across requests (deferred)

**Verified**: 16 API tests pass. Manual testing confirms:
- Low-confidence queries (e.g., "old books") return clarification (confidence=0.5)
- High-confidence queries (e.g., "books from Germany") execute and transition (confidence=0.88, 705 results)

---

## Stage 3: Exploration Agent ✅ COMPLETE

### 3.1 Exploration Models
- [x] Create `scripts/chat/exploration_agent.py`
- [x] Define `ExplorationIntent` enum (already in models.py)
- [x] Define `ExplorationRequest` model
- [x] Define `ExplorationResponse` model

### 3.2 Exploration Agent LLM Integration
- [x] Design exploration agent system prompt
- [x] Implement `interpret_exploration_request()` function
- [x] Handle NEW_QUERY intent (transition back to Phase 1)
- [x] Handle REFINEMENT intent (narrow current subgroup)

### 3.3 Aggregation Engine
- [x] Create `scripts/chat/aggregation.py`
- [x] Implement deterministic SQL generation (not LLM-based for reliability)
- [x] Implement `execute_aggregation()` with record_id filtering
- [x] Implement common aggregations:
  - [x] Top publishers
  - [x] Date distribution (by decade/century)
  - [x] Language breakdown
  - [x] Place of publication
  - [x] Subject clusters
  - [x] Agent (printers, authors)
- [x] Add safety checks (parameterized queries, no dynamic SQL)

### 3.4 Phase 2 API Integration
- [x] Implement `handle_corpus_exploration_phase()` function
- [x] Route exploration intents to appropriate handlers
- [x] Return structured data with visualization hints

### 3.5 Tests for Stage 3
- [x] Test exploration intent classification (verified manually)
- [x] Test aggregation query execution
- [x] Test refinement flow (subgroup narrowing)
- [x] Test NEW_QUERY transition back to Phase 1

**Verified working scenarios**:
- "top 5 publishers" → Aggregation with top 5 publishers
- "how many in Latin?" → Metadata question with count (184 books)
- "show by century" → Date aggregation by century
- "let's search for Hebrew books" → NEW_QUERY transition, finds 806 Hebrew books

**Known Issue**: Language refinement uses full names ('latin') but DB uses codes ('lat'). Needs mapping.

---

## Stage 4: Enrichment Pipeline ✅ COMPLETE (Core)

### 4.1 Enrichment Infrastructure ✅
- [x] Create `scripts/enrichment/` directory
- [x] Create `scripts/enrichment/__init__.py` with architecture docs
- [x] Create enrichment cache schema (`scripts/enrichment/schema.sql`)
- [x] Define `EnrichmentResult` model with PersonInfo, PlaceInfo
- [x] Define `EnrichmentRequest` model
- [x] Define `EnrichmentSource` enum (WIKIDATA, VIAF, NLI, LOC, ISNI, CACHE)

### 4.2 NLI Authority Integration ✅
- [x] Create `scripts/enrichment/nli_client.py`
- [x] Implement URI parsing (extract NLI ID from MARC $0)
- [x] Document JSONLD endpoint (works but lacks external IDs)
- [x] Implement manual mapping file support
- [x] **KEY DISCOVERY**: Query Wikidata P8189 (NLI J9U ID) to get Wikidata QID!

**Wikidata NLI ID Lookup (Primary Method)**:
Wikidata stores NLI authority IDs as property P8189. This means we can:
1. Extract NLI ID from MARC $0 URI (e.g., `987007261327805171`)
2. Query Wikidata: `?item wdt:P8189 "987007261327805171"` → Q705482
3. Get full enrichment from Wikidata (dates, occupations, VIAF, ISNI, LOC)

**No Cloudflare issues!** This bypasses the NLI website entirely.
~820,000+ NLI authority IDs are mapped in Wikidata.

### 4.3 Wikidata Integration ✅
- [x] Create `scripts/enrichment/wikidata_client.py`
- [x] Implement SPARQL queries for agents (birth/death, occupations, VIAF ID)
- [x] Implement SPARQL queries for places (coordinates, country)
- [x] Implement `execute_sparql()` async function
- [x] Add rate limiting (1 second delay)
- [x] Handle search results with disambiguation

### 4.4 VIAF Integration (Deferred)
- [ ] Create `scripts/enrichment/viaf_client.py`
- [ ] Implement VIAF search API client
- Note: Wikidata provides VIAF IDs, so direct VIAF API may not be needed

### 4.5 Enrichment Service ✅
- [x] Create `scripts/enrichment/enrichment_service.py`
- [x] Implement cache-first lookup (SQLite)
- [x] Implement `enrich_entity()` with fallback: cache → NLI → Wikidata ID → name search
- [x] Implement `enrich_batch()` for parallel enrichment
- [x] Add TTL-based cache expiration (30 days default)
- [x] Implement cache statistics and cleanup

### 4.6 Background Enrichment Worker (Deferred)
- [ ] Create `scripts/enrichment/worker.py`
- [ ] Implement enrichment queue processing
- Note: On-demand enrichment working; background worker for bulk pre-enrichment

### 4.7 Enrichment API Endpoints ✅
- [x] Integrate enrichment into exploration responses (ENRICHMENT_REQUEST intent)
- [ ] Add `POST /enrich/{entity_type}/{value}` endpoint (optional)
- [ ] Add `GET /health/enrichment` endpoint (optional)

### 4.8 Tests for Enrichment
- [x] Manual test: Wikidata SPARQL queries (Aldus Manutius, David Frishman)
- [x] Manual test: Cache hit/miss behavior
- [ ] Unit tests with mock responses
- [ ] Integration test with real APIs (optional, slow)

**Verified working scenarios**:
- "Tell me about Aldus Manutius" → Wikidata enrichment with dates, occupations, VIAF link
- "Who was David Frishman?" → Search finds Hebrew writer (1859-1922)
- Cache hits return immediately without API calls

---

## Stage 5: Advanced Features

### 5.1 Need Elicitation
- [ ] Implement goal elicitation when user intent unclear
- [ ] Add `UserGoal` model to session
- [ ] Design proactive suggestion prompts:
  - "Would you like to see top publishers?"
  - "I can analyze subject distribution..."
- [ ] Store elicited goals in session

### 5.2 Recommendations
- [ ] Implement RECOMMENDATION intent handler
- [ ] Design relevance scoring for corpus items
- [ ] Use LLM to match user needs to record metadata
- [ ] Return ranked recommendations with explanations

### 5.3 Comparisons
- [ ] Implement COMPARISON intent handler
- [ ] Support subgroup splits (e.g., Paris vs London)
- [ ] Generate comparative statistics
- [ ] Format comparison results

### 5.4 WebSocket Enhancements
- [ ] Add `phase_change` message type
- [ ] Add `enrichment_progress` message type
- [ ] Add `enrichment_result` message type
- [ ] Add `aggregation_result` message type
- [ ] Stream enrichments progressively

---

## Stage 6: Integration & Polish

### 6.1 End-to-End Testing
- [ ] Full conversation flow test (query → explore → enrich)
- [ ] Multi-turn refinement test
- [ ] Session persistence test
- [ ] Error handling test

### 6.2 Documentation
- [ ] Update CLAUDE.md with new architecture
- [ ] Document enrichment pipeline in docs/
- [ ] Add API documentation for new endpoints
- [ ] Create user guide for conversation flow

### 6.3 Performance Optimization
- [ ] Profile LLM call latency
- [ ] Optimize aggregation queries
- [ ] Tune enrichment cache TTL
- [ ] Add metrics/monitoring

---

## Issues & Learnings

*This section will be updated as we encounter issues during implementation.*

### Known Issues
- WebSocket endpoint still uses old clarification logic (needs update for intent agent)
- Language refinement: User says 'latin' but DB uses code 'lat'. Need language name → code mapping.

### Design Modifications
- Added LLM-specific Pydantic models (FilterLLM, QueryPlanLLM) to satisfy OpenAI strict schema
- Aggregation engine uses deterministic SQL (not LLM-generated) for reliability and safety

### Bugs Found
- **OpenAI additionalProperties error**: Dict[str, Any] fields in Pydantic models cause schema validation failure with OpenAI Responses API. Fixed by creating LLM-specific models with extra='forbid' and no Dict[str, Any] fields.
- **Existing sessions.db missing phase column**: CREATE TABLE IF NOT EXISTS doesn't add new columns to existing tables. Fixed by deleting old sessions.db (migration script deferred).
- **String format brace conflict**: JSON examples in system prompts with `{}` conflict with Python's `.format()`. Fixed by escaping braces as `{{}}` in JSON examples.

---

## Progress Log

| Date | Stage | Task | Status | Notes |
|------|-------|------|--------|-------|
| 2026-01-15 | 0 | Planning complete | Done | Plan reviewed and approved |
| 2026-01-16 | 1.1 | Core models | Done | IntentInterpretation, ConversationPhase, ActiveSubgroup, ExplorationIntent, UserGoal |
| 2026-01-16 | 1.2 | Intent agent LLM | Done | interpret_query(), confidence scoring prompt, caching |
| 2026-01-16 | 1.3 | Session store | Done | Phase tracking, active subgroup storage, user goals |
| 2026-01-16 | 1 | Stage 1 complete | Done | All 16 API tests pass |
| 2026-01-16 | 2.1 | Chat endpoint restructure | Done | Phase-aware routing, handle_query_definition_phase() |
| 2026-01-16 | 2.2 | Response formatting | Done | Phase metadata, exploration prompts, confidence scores |
| 2026-01-16 | 2.3 | Integration tests | Done | High/low confidence queries verified manually |
| 2026-01-16 | 2 | Stage 2 complete | Done | Phase transitions working (705 Germany books, 0.88 confidence) |
| 2026-01-16 | 3.1 | Exploration models | Done | ExplorationRequest, ExplorationResponse, LLM models |
| 2026-01-16 | 3.2 | Exploration agent | Done | interpret_exploration_request(), system prompt |
| 2026-01-16 | 3.3 | Aggregation engine | Done | Deterministic SQL, 8 aggregation types |
| 2026-01-16 | 3.4 | API integration | Done | handle_corpus_exploration_phase(), intent routing |
| 2026-01-16 | 3 | Stage 3 complete | Done | Aggregations, metadata questions, refinement, NEW_QUERY transition |
| 2026-01-16 | 4.1 | Enrichment infrastructure | Done | schema.sql, models.py with all entity types |
| 2026-01-16 | 4.2 | NLI client | Done | nli_client.py, URI parsing, manual mapping (Cloudflare blocks HTML) |
| 2026-01-16 | 4.3 | Wikidata client | Done | wikidata_client.py, SPARQL for agents/places, rate limiting |
| 2026-01-16 | 4.5 | Enrichment service | Done | Cache-first lookup, multi-source fallback, batch enrichment |
| 2026-01-16 | 4.7 | API integration | Done | ENRICHMENT_REQUEST handler with formatted output |
| 2026-01-16 | 4 | Stage 4 complete | Done | Core enrichment working (Wikidata via name search, caching) |

---

## Quick Reference

### Key Files to Create
```
scripts/chat/intent_agent.py          ✅ CREATED
scripts/chat/exploration_agent.py     ✅ CREATED
scripts/chat/aggregation.py           ✅ CREATED
scripts/enrichment/__init__.py        ✅ CREATED
scripts/enrichment/models.py          ✅ CREATED
scripts/enrichment/schema.sql         ✅ CREATED
scripts/enrichment/nli_client.py      ✅ CREATED
scripts/enrichment/wikidata_client.py ✅ CREATED
scripts/enrichment/enrichment_service.py ✅ CREATED
scripts/enrichment/viaf_client.py     (deferred - Wikidata provides VIAF IDs)
scripts/enrichment/worker.py          (deferred - on-demand working)
```

### Key Files to Modify
```
scripts/chat/models.py
scripts/chat/session_store.py
scripts/chat/schema.sql
app/api/main.py
```

### Test Commands
```bash
# Run unit tests
pytest tests/chat/test_intent_agent.py -v
pytest tests/enrichment/ -v

# Start dev server
uvicorn app.api.main:app --reload

# Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books from Naples"}'
```
