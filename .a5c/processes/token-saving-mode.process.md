# Token-Saving Mode — Process Document (v2)

## Goal
Reduce narrator LLM prompt size and API cost by sending lean collection records, while preserving a "No token saving" fallback that uses the current full payload.

## Current State Analysis

The narrator pipeline has 3 stages:
1. **Interpreter** (gpt-4.1): Parses user query → execution plan. Tiny user prompt (~260 chars). NOT a target.
2. **Executor**: Deterministic SQL. No LLM. NOT a target.
3. **Narrator** (gpt-4.1): Composes scholarly response from grounding data. **User prompt: ~19,829 chars / 7,351 input tokens.** THIS IS THE TARGET.

The narrator prompt is built by `_build_narrator_prompt()` in `scripts/chat/narrator.py:400-541`. It assembles:

| Section | Size (approx) | Lean strategy |
|---------|---------------|---------------|
| USER QUERY | ~100 chars | Keep unchanged |
| SCHOLARLY DIRECTIVES | ~200 chars | Keep unchanged |
| COLLECTION RECORDS | ~6,000 chars (10 records) | Selective fields per record |
| AGENT PROFILES | ~8,000 chars (16 agents w/ Wikipedia) | **0-3 agents, only if query-relevant** |
| AGGREGATION RESULTS | ~2,000 chars | Top 5 per field |
| AVAILABLE LINKS | ~3,000 chars (60+ links) | **Drop entirely** (redundant) |
| SESSION CONTEXT | ~500 chars | Keep unchanged |

## Lean Record Schema (v2)

### Per Record — Always Keep

| Field | Rationale |
|-------|-----------|
| `mms_id` | Required for evidence citation |
| `title` | Essential for scholarly response |
| `date_display` | Core bibliographic info (includes place) |
| `publisher` | Important for printing history queries |
| `primo_url` | Needed for link weaving |

### Per Record — Keep Conditionally

| Field | Rule | Rationale |
|-------|------|-----------|
| `language` | Include if query mentions language or if mixed-language result set | Short field, high value when relevant |
| `agents` (up to 2) | Select by role relevance: printer/publisher first, then author/editor if pedagogically useful. NOT first 2 blindly. | Most queries care about the printer/publisher, not all 6 contributors |
| `subjects` (up to 2) | Include only if they help justify why the item belongs in the result set | Subjects were already used by executor SQL filtering; only surface them when they add narrative value |

### Per Record — Drop by Default

| Field | Rationale |
|-------|-----------|
| Full subject strings | Already filtered in executor; rarely cited in narrative |
| Full agent lists | Noisy; 2 relevant agents suffice |
| `source_steps` | Internal metadata, never used in narrative |
| `place` (separate field) | Already folded into `date_display` |

### Agent Profiles — Radical Reduction

**Current**: 16 agents × ~500 chars each (with 800-char Wikipedia context) = ~8,000 chars

**Lean mode**: Include **0-3 agent profiles**, only when the agent materially supports the narrative.

Selection criteria:
- Agent is the direct subject of the query ("Who was Joseph Karo?")
- Agent is a key printer/publisher being discussed
- Agent provides essential context for the response

When included, each agent profile contains:
- `canonical_name`
- Role relevance to the query
- One short description line
- Birth/death years (if known)
- One useful link (Wikipedia preferred, Primo fallback)

**Do NOT**: Include all agents and trim their Wikipedia context. The gain comes from fewer agents, not shorter blobs.

### Aggregation Results
- Top 5 per field (vs top 20)
- Drop fields with only 1 value

### Available Links Section
- **Drop entirely** in lean mode. All useful URLs are already embedded in the selected records and agent profiles.

## Agent Selection Logic

The lean builder needs to decide which 0-3 agents to include. This is deterministic (no LLM needed):

1. **Query-subject agents**: If the interpreter identified a `resolve_agent` step, include that agent.
2. **High-frequency agents**: Agents that appear in 3+ records in the result set.
3. **Role-relevant agents**: If the query mentions "printer" or "publisher", include agents with those roles.
4. If none of the above apply, include **zero** agent profiles (records already list agent names).

## Process Phases (Reordered per user feedback)

### Phase 1: Implement lean record builder
- Add `build_lean_narrator_prompt()` in `scripts/chat/narrator.py`
- Implement selective agent inclusion logic
- Implement query-relevant field selection
- Add `token_saving: bool = True` parameter to `narrate()` and `_call_llm()`

### Phase 2: Add section-size logging
- Before wiring UI, measure section sizes in both modes
- Log: mode, prompt_char_count, record_count, agent_profile_count, per-section char counts
- Extend `llm_logger.py` metadata

### Phase 3: Local comparison on sample queries
- Run 3-5 representative queries in both modes
- Compare: token counts, cost, response quality
- Validate lean schema decisions before proceeding

### Phase 4: Wire UI checkbox
- Add "No token saving" checkbox to Chat.tsx
- Wire through API (HTTP + WebSocket) → narrator

### Phase 5: Build verification
- TypeScript check + production build

### Phase 6: Deploy
- Breakpoint for approval
- Commit, push, deploy, health check

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Zero agent profiles → narrative lacks biographical context | Medium | Selection logic includes agents when query is about a person |
| Query-relevant agent selection misses edge cases | Low | Fallback to full mode via checkbox; logs show which agents were included |
| Subject drop → weaker subject-based answers | Low | Subjects kept conditionally when they justify inclusion |
| Agent selection picks wrong 2 agents per record | Low | Printer/publisher prioritized; matches most query patterns in this collection |

## Testing Plan

### Sample Queries (both modes)
1. "Books published by Aldus Manutius" — publisher-focused, should include Manutius profile
2. "אני רוצה לבנות קורס על תולדות הדפוס" — broad, many records, 0-1 agent profiles expected
3. "Who was Joseph Karo?" — agent-focused, must include Karo profile
4. "Books about Sabbath printed in Venice" — subject + place, test conditional subject inclusion
5. "16th century Hebrew printing" — broad period, test aggregation trimming

### Comparison Metrics
- Input tokens (lean vs full) — target 40-60% reduction
- Output tokens (should be similar)
- Cost per query
- Which agents were included/excluded (log inspection)
- Response completeness (manual review)
- Factual accuracy (does it cite records correctly?)
