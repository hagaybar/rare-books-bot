# Deterministic Set-Scoped Follow-ups (`active_subgroup`)

**Date**: 2026-06-13
**Status**: Approved (user, 2026-06-13; design + spec + plan pre-approved in-session)
**Issue**: #60 part 2 (re-scoped) — wire the dormant `active_subgroup` Phase-2 machinery.

## Purpose

Let a scholar **explore within a held result set**. After a search produces a
corpus (e.g. "73 books printed in Venice in the 16th century"), follow-ups like
"how many are in Hebrew?", "who printed them?", "only the Hebrew ones", "compare
to Amsterdam" should operate on **exactly those records** — deterministically —
rather than the interpreter re-deriving an approximate scope from conversation
text.

The machinery already exists but is dormant: the `active_subgroups` table,
`SessionStore.set_active_subgroup` / `get_active_subgroup`, the `ActiveSubgroup`
model, the `ConversationPhase.CORPUS_EXPLORATION` / `ExplorationIntent` enums,
the executor's scoped retrieve/aggregate, and two `getattr(session,
"active_subgroup", None)` read sites in `app/api/main.py`. Nothing writes the set
and `ChatSession` has no `active_subgroup` field, so the read is always `None`.
This wires it end to end.

## The three-intent model (the core)

The interpreter classifies every turn into one intent, and that single
classification drives **both** scoping and the held-set lifecycle:

| Intent | Scope | Held set after the turn |
|---|---|---|
| **New search** (fresh topic) | full collection | **replaced** with the new result |
| **Explore-in-set** (metadata / aggregate / compare / connections over the held set) | the held set | **unchanged** |
| **Refine-in-set** ("only the Hebrew ones") | the held set | **replaced** with the narrowed result (progressive drilling) |

A turn with no result (clarification, error, honest-empty) never changes the
held set.

## Architecture — five touchpoints

### 1. Write (hold the set)
After a turn whose intent is **new search** or **refine-in-set** and which
produced a non-empty retrieve result, the chat handler calls the existing
`store.set_active_subgroup(session_id, defining_query, filter_summary,
record_ids, candidate_count, candidate_set)`. Source: the turn's
`CandidateSet` (record_ids = its candidate record_ids; candidate_count =
total_count; filter_summary = a short human description from the plan's
filters). Explore-in-set turns do **not** call it (they explore without
redefining). Clarification/empty/error turns do **not** call it.

### 2. Load + attach (read the set)
Add `active_subgroup: Optional[ActiveSubgroup] = None` to `ChatSession`
(`scripts/chat/models.py`). `SessionStore.get_session` populates it via the
existing `get_active_subgroup(session_id)`. The two read sites in
`app/api/main.py` (~677 REST, ~1013 WS) already do
`getattr(session, "active_subgroup", None)` → `SessionContext.previous_record_ids`;
they now receive real data instead of always `None`.

### 3. Scope resolution (deterministic)
Add a reserved scope keyword `"active_subgroup"` (alongside the existing
`"full_collection"` / `$step_N`). `executor._resolve_scope(params.scope,
step_results, session_context)` resolves it to
`session_context.previous_record_ids`; if that is empty/absent it degrades to
full collection (no held set → no scoping). The executor already supports
scoped retrieve/aggregate via `scope_ids`, so this only **names** the held set.

### 4. Interpreter (the LLM decision — the main risk)
`scripts/chat/interpreter.py` system prompt gains rules: *if the session context
carries a held set (its size + defining query are provided), and the user's
query explores or refines that set, set the steps' `scope` to
`"active_subgroup"` and set `phase = corpus_exploration`; if the query is a new
topic, ignore the held set (scope `full_collection`) and the held set will be
replaced.* The interpreter is given the held-set summary in its context
(defining query + count). This judgment is the feature's main risk; it is
mitigated by (a) explicit prompt rules + few-shot examples, (b) the fully
deterministic scope plumbing beneath it, and (c) the user-visible chip + reset
(section 5) making any misclassification visible and recoverable, never silent.

### 5. Surface + reset
- **Response**: carries `phase` (already present) plus a held-set summary in
  metadata: `active_subgroup` = `{defining_query, count}` (or null).
- **Narrator** (`scripts/chat/narrator.py`): when the turn was scoped, the prose
  discloses it ("Among the 73 Venice books you're exploring, 12 are in Hebrew…").
- **Frontend** (`PhaseIndicator.tsx`): a chip "Exploring N <defining query> ·
  search all" shown when a held set is active. "Search all" is a one-click
  reset.
- **Reset**: a small mechanism to clear the held set. Reuse the existing
  delete-then-insert shape — add `SessionStore.clear_active_subgroup(session_id)`
  and a `DELETE /sessions/{id}/subgroup` endpoint (auth + ownership like the
  other session routes) the chip calls. After reset, the next query is
  full-collection.

## Clearing rules
- **New-search** turn → replaced (handled by the write step).
- **Explicit reset** (chip) → cleared via the new endpoint.
- **New / expired session** → no held set (per-session, `ON DELETE CASCADE`).

## Error handling
- Empty/clarification/error turn: held set untouched.
- Held set referenced but record_ids empty/stale: scope degrades to full
  collection (never errors).
- Reset on a session with no held set: no-op, 200.

## Testing (deterministic — no live LLM)
- **Round-trip**: `set_active_subgroup` → `get_session` attaches
  `active_subgroup` → `SessionContext.previous_record_ids` populated.
- **Scope resolution**: `_resolve_scope("active_subgroup", …, session_context)`
  returns the held record_ids; empty held set → full collection.
- **Lifecycle**: a refine-intent turn replaces the held set with the narrowed
  result; an explore-intent turn leaves it unchanged; a new-search replaces it.
  (Tested by driving `execute_plan` + the handler's persistence logic with
  constructed plans/intents, not the LLM.)
- **Reset**: `clear_active_subgroup` + the endpoint clear the set; next turn is
  full-collection.
- **Interpreter prompt discipline**: assert the system prompt contains the
  held-set scoping rules and the `active_subgroup` scope keyword (matches the
  existing `TestPrompt*` style).
- **Frontend**: `npx tsc --noEmit` + targeted eslint; manual chip/reset check in
  the testing guide (no FE test infra).
- LLM judgment **quality** is validated manually / via the gold-suite, not unit
  tests.

## Out of scope (YAGNI)
- `user_goals` table / goal elicitation (the other dormant Phase-2 piece).
- Multiple/named saved subgroups per session (one active subgroup only — the
  table is `UNIQUE(session_id)`).
- Set algebra across subgroups (union/intersect of saved sets).

## Docs to update
- `docs/current/chatbot-api.md` — the held-set behavior, the reset endpoint,
  phase semantics.
- `docs/current/architecture.md` — active_subgroup now wired.
- `frontend/.../Help.tsx` §16 — tighten the follow-up claim to "scoped to exactly
  these records" once shipped.
