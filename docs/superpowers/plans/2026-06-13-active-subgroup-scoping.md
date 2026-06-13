# Deterministic Set-Scoped Follow-ups (`active_subgroup`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the dormant `active_subgroup` machinery so a scholar can explore and refine within a held result set deterministically, with the held set surfaced as a chip and resettable in one click.

**Architecture:** Three-intent model — a turn is a *new search* (full collection → held set replaced), *explore-in-set* (aggregate over the held set → unchanged), or *refine-in-set* (retrieve scoped to the held set → replaced with the narrowed result). The interpreter decides **scoping** (scope steps to the existing `$previous_results` keyword when exploring/refining); a deterministic handler-side policy decides the **lifecycle** (a retrieve producing records replaces the held set; an aggregate-only turn leaves it unchanged). The held set is written via the existing `SessionStore.set_active_subgroup`, loaded onto `ChatSession`, and surfaced via response metadata + a frontend chip with a reset endpoint.

**Tech Stack:** Python 3 / Pydantic / FastAPI / SQLite (backend), pytest (tests), React + TypeScript + Tailwind (frontend).

---

## Key decisions (read before starting — they diverge from the spec)

The spec (`docs/superpowers/specs/2026-06-13-active-subgroup-scoping-design.md`) proposed two new primitives. Research into the live code found both already exist; **reuse them, do not add new ones**:

1. **Scope keyword.** The spec §3 said to add a reserved `"active_subgroup"` scope keyword. **Do not.** `executor._resolve_scope` (`scripts/chat/executor.py:300-306`) already resolves `"$previous_results"` → `session_context.previous_record_ids` (and degrades to full collection when empty), and `interpreter.py:1035` already whitelists it in step-ref validation. The interpreter prompt (`interpreter.py:310-315, 514-524`) already documents it. The held set flows into `SessionContext.previous_record_ids` through the two existing read sites in `app/api/main.py` (~677 REST, ~1013 WS). So scope plumbing is **already complete**; this plan only makes the held set non-empty and teaches the interpreter *when* to use `$previous_results`.

2. **Clear method.** The spec §5 said to add `SessionStore.clear_active_subgroup`. **Do not.** `set_active_subgroup(session_id, None)` already deletes the row (`session_store.py:478-488`). The reset endpoint calls that.

What is genuinely missing (this plan builds it):
- `ChatSession` has no `active_subgroup` field, and `get_session` never populates it, so the read sites always see `None`.
- Nothing ever **writes** the held set after a search.
- No held-set lifecycle policy (when to replace vs. leave unchanged).
- No surfacing (response metadata, narrator disclosure, frontend chip, reset endpoint).
- The interpreter prompt teaches `$previous_results` only as a vague "follow-up refining" case, not the explicit three-intent model.

## File structure

| File | Responsibility | Change |
|---|---|---|
| `scripts/chat/subgroup_policy.py` | **New.** Pure, LLM-free held-set lifecycle policy: decide whether a turn redefines the held set, summarize filters, detect held-set scoping, build the metadata summary. | Create |
| `scripts/chat/models.py` | `ChatSession` gains `active_subgroup` field. | Modify (`ChatSession`, ~line 139-160) |
| `scripts/chat/session_store.py` | `get_session` loads the held set onto the session. | Modify (`get_session`, ~line 138-151) |
| `scripts/chat/interpreter.py` | System prompt teaches the three-intent model + held-set defining-query/count context. | Modify (prompt text ~line 310-315; context render ~514-524) |
| `scripts/chat/narrator.py` | Discloses held-set scoping in the prompt so prose says "Among the N you're exploring…". | Modify (prompt builder ~line 826) |
| `app/api/main.py` | Both chat handlers write/keep the held set after a turn, set phase, and surface the summary; new reset endpoint. | Modify (REST ~675-793, WS ~1012-1144; new route after ~893) |
| `frontend/src/types/chat.ts` | Type for the `active_subgroup` metadata summary. | Modify |
| `frontend/src/components/chat/PhaseIndicator.tsx` | Render the held-set chip with a "Search all" reset. | Modify |
| `frontend/src/pages/Chat.tsx` | Pass the summary + reset handler to `PhaseIndicator`; call the reset endpoint. | Modify |
| `docs/current/chatbot-api.md`, `docs/current/architecture.md`, `frontend/src/pages/Help.tsx` | Doc updates. | Modify |
| `tests/scripts/chat/test_subgroup_policy.py` | **New.** Unit tests for the policy module. | Create |
| `tests/scripts/chat/test_session_store.py`, `tests/scripts/chat/test_models.py`, `tests/scripts/chat/test_interpreter.py` | Round-trip, model field, prompt-discipline tests. | Modify |
| `tests/api/test_subgroup_reset.py` | **New.** Reset endpoint test. | Create |

---

## Task 1: `ChatSession.active_subgroup` field

**Files:**
- Modify: `scripts/chat/models.py` (`ChatSession`, ~line 139-160)
- Test: `tests/scripts/chat/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/scripts/chat/test_models.py`:

```python
def test_chat_session_active_subgroup_defaults_none():
    """ChatSession.active_subgroup defaults to None."""
    session = ChatSession()
    assert session.active_subgroup is None


def test_chat_session_active_subgroup_round_trips():
    """ChatSession carries an ActiveSubgroup and serializes it."""
    from scripts.chat.models import ActiveSubgroup

    sub = ActiveSubgroup(
        defining_query="books printed in Venice",
        filter_summary="place contains Venice",
        record_ids=["991", "992"],
    )
    session = ChatSession(active_subgroup=sub)
    assert session.active_subgroup is not None
    assert session.active_subgroup.record_ids == ["991", "992"]

    session2 = ChatSession.model_validate_json(session.model_dump_json())
    assert session2.active_subgroup.defining_query == "books printed in Venice"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/chat/test_models.py::test_chat_session_active_subgroup_defaults_none tests/scripts/chat/test_models.py::test_chat_session_active_subgroup_round_trips -v`
Expected: FAIL — `ChatSession() got unexpected ... active_subgroup` / `AttributeError: ... active_subgroup`.

- [ ] **Step 3: Add the field**

In `scripts/chat/models.py`, `ChatSession` (after the `metadata` field, ~line 158), add:

```python
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # The held result set being explored (Phase 2). Loaded by
    # SessionStore.get_session; None when no set is held (issue #60 part 2).
    active_subgroup: Optional[ActiveSubgroup] = None
```

`ActiveSubgroup` and `Optional` are already defined/imported in this file (it declares `class ActiveSubgroup` at line 58 and uses `Optional` throughout) — no new import needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/scripts/chat/test_models.py -v`
Expected: PASS (all model tests, including the two new ones).

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/models.py tests/scripts/chat/test_models.py
git commit -m "$(cat <<'EOF'
feat(#60): add ChatSession.active_subgroup field

Adds the optional held-set field so SessionStore.get_session can attach a
loaded ActiveSubgroup. Defaults None (no set held). Field round-trips through
JSON serialization.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `get_session` loads the held set

**Files:**
- Modify: `scripts/chat/session_store.py` (`get_session`, ~line 138-151)
- Test: `tests/scripts/chat/test_session_store.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/scripts/chat/test_session_store.py` (the file already constructs a `SessionStore` in a tmp db; reuse its existing `store` fixture / construction pattern — match the top-of-file style):

```python
def test_get_session_attaches_active_subgroup(store):
    """get_session populates ChatSession.active_subgroup from the table."""
    from scripts.chat.models import ActiveSubgroup

    session = store.create_session(user_id="u1")
    store.set_active_subgroup(
        session.session_id,
        ActiveSubgroup(
            defining_query="printed in Venice",
            filter_summary="place contains Venice",
            record_ids=["100", "101", "102"],
        ),
    )

    loaded = store.get_session(session.session_id)
    assert loaded.active_subgroup is not None
    assert loaded.active_subgroup.record_ids == ["100", "101", "102"]
    assert loaded.active_subgroup.defining_query == "printed in Venice"


def test_get_session_active_subgroup_none_when_absent(store):
    """get_session leaves active_subgroup None when no set is held."""
    session = store.create_session(user_id="u1")
    loaded = store.get_session(session.session_id)
    assert loaded.active_subgroup is None
```

> If the existing test file constructs the store differently (e.g. a `make_store()` helper rather than a `store` fixture, or `create_session` has a different name), match that file's existing convention — read the top of `tests/scripts/chat/test_session_store.py` first and reuse its setup verbatim.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/chat/test_session_store.py::test_get_session_attaches_active_subgroup -v`
Expected: FAIL — `assert None is not None` (field exists from Task 1 but `get_session` never sets it).

- [ ] **Step 3: Populate in `get_session`**

In `scripts/chat/session_store.py`, `get_session`, replace the message-loading tail (currently lines ~147-151):

```python
        # Load messages
        messages = self._get_messages(session_id)
        session.messages = messages

        return session
```

with:

```python
        # Load messages
        messages = self._get_messages(session_id)
        session.messages = messages

        # Load the held result set being explored (issue #60 part 2)
        session.active_subgroup = self.get_active_subgroup(session_id)

        return session
```

`get_active_subgroup` is already defined in this class (line 533) and returns `Optional[ActiveSubgroup]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/scripts/chat/test_session_store.py -v`
Expected: PASS (existing store tests + the two new ones).

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/session_store.py tests/scripts/chat/test_session_store.py
git commit -m "$(cat <<'EOF'
feat(#60): get_session loads active_subgroup onto ChatSession

get_session now calls the existing get_active_subgroup and attaches the result,
so the read sites in app/api/main.py receive a real held set instead of always
None. None when no set is held.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Held-set lifecycle policy module (pure, LLM-free)

This is the deterministic core. It decides — from the plan's step shape and the
turn's `CandidateSet` — whether the held set is replaced or left unchanged, and
builds the surfacing summary. No LLM, fully unit-testable.

**Files:**
- Create: `scripts/chat/subgroup_policy.py`
- Test: `tests/scripts/chat/test_subgroup_policy.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/chat/test_subgroup_policy.py`:

```python
"""Unit tests for the held-set lifecycle policy (issue #60 part 2)."""

from scripts.chat.plan_models import (
    AggregateParams,
    ExecutionStep,
    InterpretationPlan,
    RetrieveParams,
    StepAction,
)
from scripts.chat.subgroup_policy import (
    build_subgroup_update,
    subgroup_summary,
    summarize_filters,
    was_scoped_to_held_set,
)
from scripts.schemas import (
    Candidate,
    CandidateSet,
    Filter,
    FilterField,
    FilterOp,
)


def _retrieve_step(scope="full_collection", filters=None):
    return ExecutionStep(
        step_index=0,
        label="retrieve",
        action=StepAction.RETRIEVE,
        params=RetrieveParams(filters=filters or [], scope=scope),
    )


def _aggregate_step(scope="$previous_results"):
    return ExecutionStep(
        step_index=0,
        label="aggregate",
        action=StepAction.AGGREGATE,
        params=AggregateParams(field="language", scope=scope),
    )


def _plan(steps):
    return InterpretationPlan(
        query_text="q",
        intents=["search"],
        execution_steps=steps,
        directives=[],
        reasoning="r",
        confidence=0.9,
    )


def _candidate_set(n):
    return CandidateSet(
        query_text="q",
        plan_hash="h",
        sql="(scholar)",
        candidates=[Candidate(record_id=str(i), match_rationale="m") for i in range(n)],
        total_count=n,
    )


def test_new_search_replaces_held_set():
    """A full-collection retrieve with results defines a new held set."""
    plan = _plan([_retrieve_step(scope="full_collection")])
    sub = build_subgroup_update(plan, _candidate_set(3), "printed in Venice")
    assert sub is not None
    assert sub.record_ids == ["0", "1", "2"]
    assert sub.defining_query == "printed in Venice"


def test_refine_in_set_replaces_held_set():
    """A retrieve scoped to the held set narrows and replaces it."""
    plan = _plan([_retrieve_step(scope="$previous_results")])
    sub = build_subgroup_update(plan, _candidate_set(2), "only the Hebrew ones")
    assert sub is not None
    assert sub.record_ids == ["0", "1"]


def test_explore_in_set_leaves_held_set_unchanged():
    """An aggregate-only turn does not redefine the held set."""
    plan = _plan([_aggregate_step(scope="$previous_results")])
    sub = build_subgroup_update(plan, _candidate_set(5), "how many are in Hebrew?")
    assert sub is None


def test_empty_result_leaves_held_set_unchanged():
    """A retrieve with zero results does not redefine the held set."""
    plan = _plan([_retrieve_step(scope="full_collection")])
    sub = build_subgroup_update(plan, _candidate_set(0), "books from Atlantis")
    assert sub is None


def test_no_candidate_set_leaves_held_set_unchanged():
    plan = _plan([_retrieve_step()])
    assert build_subgroup_update(plan, None, "q") is None


def test_was_scoped_to_held_set_true_for_previous_results():
    plan = _plan([_aggregate_step(scope="$previous_results")])
    assert was_scoped_to_held_set(plan) is True


def test_was_scoped_to_held_set_false_for_full_collection():
    plan = _plan([_retrieve_step(scope="full_collection")])
    assert was_scoped_to_held_set(plan) is False


def test_summarize_filters_describes_retrieve_filters():
    plan = _plan([_retrieve_step(filters=[
        Filter(field=FilterField.PLACE, op=FilterOp.CONTAINS, value="Venice"),
        Filter(field=FilterField.DATE, op=FilterOp.RANGE, start=1500, end=1599),
    ])])
    summary = summarize_filters(plan)
    assert "place" in summary.lower()
    assert "Venice" in summary
    assert "1500" in summary


def test_summarize_filters_empty_when_no_filters():
    plan = _plan([_retrieve_step(filters=[])])
    assert summarize_filters(plan) == ""


def test_subgroup_summary_shape():
    from scripts.chat.models import ActiveSubgroup

    sub = ActiveSubgroup(
        defining_query="printed in Venice",
        filter_summary="place contains Venice",
        record_ids=["1", "2", "3"],
    )
    assert subgroup_summary(sub) == {
        "defining_query": "printed in Venice",
        "count": 3,
    }
    assert subgroup_summary(None) is None
```

> Confirm the import surface before running: `Candidate`, `CandidateSet`, `Filter`, `FilterField`, `FilterOp` are exported from `scripts.schemas` (the existing `test_models.py` imports `CandidateSet, Filter, FilterField, FilterOp, QueryPlan` from `scripts.schemas`). `Candidate` is in the same module — if the import errors, import it from `scripts.schemas.candidate_set` and adjust. `InterpretationPlan` requires `query_text`, `intents`, `execution_steps`, `directives`, `reasoning`, `confidence` — if its constructor rejects any of these field names, read `scripts/chat/plan_models.py:282-300` and match the actual required fields.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/scripts/chat/test_subgroup_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.chat.subgroup_policy'`.

- [ ] **Step 3: Implement the policy module**

Create `scripts/chat/subgroup_policy.py`:

```python
"""Deterministic held-set ("active_subgroup") lifecycle policy.

Pure, LLM-free helpers that decide — from a completed turn's interpretation
plan and its CandidateSet — whether the held result set is redefined, and that
build the surfacing summary. The interpreter decides *scoping* (whether to
scope steps to "$previous_results"); these helpers decide the *lifecycle*
(replace vs. leave unchanged) from the resulting step shape.

Three-intent model (issue #60 part 2):
- New search      : full-collection retrieve with results -> held set replaced
- Refine-in-set   : retrieve scoped to "$previous_results" -> replaced (narrowed)
- Explore-in-set  : aggregate/connections-only over the held set -> unchanged
"""

from typing import Optional

from scripts.chat.models import ActiveSubgroup
from scripts.chat.plan_models import InterpretationPlan, StepAction
from scripts.schemas import CandidateSet

# The scope keyword that names the held set (already wired in executor +
# interpreter). Reused here rather than introducing a new "active_subgroup"
# keyword (see the plan's "Key decisions").
HELD_SET_SCOPE = "$previous_results"


def was_scoped_to_held_set(plan: InterpretationPlan) -> bool:
    """True if any execution step scoped to the held set ($previous_results).

    Drives the conversation phase: a scoped turn is corpus exploration.
    """
    for step in plan.execution_steps:
        if getattr(step.params, "scope", None) == HELD_SET_SCOPE:
            return True
    return False


def summarize_filters(plan: InterpretationPlan) -> str:
    """Short human description of a plan's retrieve filters for the chip.

    Example: "place contains Venice; date 1500-1599". Empty string when the
    plan has no retrieve filters.
    """
    parts: list[str] = []
    for step in plan.execution_steps:
        if step.action != StepAction.RETRIEVE:
            continue
        for f in getattr(step.params, "filters", []) or []:
            field = getattr(getattr(f, "field", None), "value", None) or str(
                getattr(f, "field", "")
            )
            op = getattr(getattr(f, "op", None), "value", None) or str(
                getattr(f, "op", "")
            )
            if getattr(f, "start", None) is not None:
                parts.append(f"{field} {f.start}-{f.end}")
            else:
                value = getattr(f, "value", None)
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value)
                parts.append(f"{field} {op.lower()} {value}".strip())
    return "; ".join(parts)


def build_subgroup_update(
    plan: InterpretationPlan,
    candidate_set: Optional[CandidateSet],
    query_text: str,
) -> Optional[ActiveSubgroup]:
    """Decide the held-set update for a completed turn.

    Returns an ActiveSubgroup to write/replace the held set, or None to leave
    the held set unchanged.

    A turn redefines the held set iff it has a retrieve step AND produced a
    non-empty CandidateSet (new search or refine-in-set). Aggregate/connections
    -only turns (explore-in-set) and empty/clarification turns return None.
    """
    if candidate_set is None or candidate_set.total_count == 0:
        return None

    has_retrieve = any(
        step.action == StepAction.RETRIEVE for step in plan.execution_steps
    )
    if not has_retrieve:
        return None

    return ActiveSubgroup(
        candidate_set=candidate_set,
        defining_query=query_text,
        filter_summary=summarize_filters(plan),
        record_ids=[c.record_id for c in candidate_set.candidates],
    )


def subgroup_summary(subgroup: Optional[ActiveSubgroup]) -> Optional[dict]:
    """Compact summary for the response metadata / frontend chip.

    Returns ``{"defining_query": str, "count": int}`` or None.
    """
    if subgroup is None:
        return None
    return {
        "defining_query": subgroup.defining_query,
        "count": len(subgroup.record_ids),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/scripts/chat/test_subgroup_policy.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/subgroup_policy.py tests/scripts/chat/test_subgroup_policy.py
git commit -m "$(cat <<'EOF'
feat(#60): deterministic held-set lifecycle policy

New pure module scripts/chat/subgroup_policy.py: build_subgroup_update decides
replace-vs-unchanged from plan step shape + CandidateSet; summarize_filters and
subgroup_summary build surfacing strings; was_scoped_to_held_set drives the
conversation phase. Fully LLM-free, 11 unit tests.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Wire write + surfacing into the REST handler

**Files:**
- Modify: `app/api/main.py` (REST scholar handler, ~675-793)

- [ ] **Step 1: Add the import**

Near the other `scripts.chat` imports at the top of `app/api/main.py` (the file already imports `SessionContext` at line 64), add:

```python
from scripts.chat.subgroup_policy import (
    build_subgroup_update,
    subgroup_summary,
    was_scoped_to_held_set,
)
```

- [ ] **Step 2: Surface the held set in the clarification short-circuit**

In the clarification branch (currently ~706-726), a clarification turn leaves the held set unchanged but the chip should still reflect it. After building the clarification `response` and before `return`, add the held-set summary to its metadata. Change the `metadata=` argument of that `ChatResponse(...)` (line ~714) from:

```python
            metadata={"intents": plan.intents, "reasoning": plan.reasoning},
```

to:

```python
            metadata={
                "intents": plan.intents,
                "reasoning": plan.reasoning,
                "active_subgroup": subgroup_summary(
                    getattr(session, "active_subgroup", None)
                ),
            },
```

- [ ] **Step 3: Write/keep the held set and surface it after the narrative turn**

In the narrative path, the assistant message is stored at ~786-790. Immediately **after** that `store.add_message(...)` block and before `return`, insert:

```python
    # ---- Held-set lifecycle (issue #60 part 2) ----
    # A retrieve that produced records defines/redefines the held set; an
    # aggregate-only (explore) turn leaves it unchanged.
    new_subgroup = build_subgroup_update(
        plan, response.candidate_set, chat_request.message
    )
    if new_subgroup is not None:
        store.set_active_subgroup(session.session_id, new_subgroup)
        held = new_subgroup
    else:
        held = getattr(session, "active_subgroup", None)

    # Surface: phase reflects whether this turn explored the held set; metadata
    # carries the post-turn held-set summary for the chip.
    if was_scoped_to_held_set(plan):
        response.phase = ConversationPhase.CORPUS_EXPLORATION
    response.metadata["active_subgroup"] = subgroup_summary(held)
```

(The `response.phase` is currently hardcoded to `QUERY_DEFINITION` at line ~775; this overrides it to `CORPUS_EXPLORATION` only when the turn was scoped to the held set.)

- [ ] **Step 4: Verify import + handler compile, run the API import smoke test**

Run: `python -c "import app.api.main"`
Expected: exit 0, no ImportError.

Run the existing API/handler tests to confirm no regression:
Run: `python -m pytest tests/api -q`
Expected: PASS (no failures introduced). If there is no `tests/api` dir, run `python -m pytest -k "chat or session" -q`.

- [ ] **Step 5: Commit**

```bash
git add app/api/main.py
git commit -m "$(cat <<'EOF'
feat(#60): REST handler writes/keeps held set, surfaces summary + phase

After a narrative turn, build_subgroup_update decides whether to replace the
held set (retrieve with results) or leave it (aggregate-only). Sets phase to
corpus_exploration when the turn scoped to $previous_results, and puts the
held-set summary in response.metadata.active_subgroup (also on clarifications).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Wire write + surfacing into the WebSocket handler

**Files:**
- Modify: `app/api/main.py` (WS narrative path, ~1012-1144)

- [ ] **Step 1: Write/keep the held set after the WS narrative turn**

In the WS handler, the assistant message is stored in the `try/except` at ~1129-1137. **After** that block (after the `except Exception:` log, before `await websocket.send_json({"type": "complete", ...})` at ~1139), insert:

```python
        # ---- Held-set lifecycle (issue #60 part 2) ----
        new_subgroup = build_subgroup_update(
            plan, response.candidate_set, message
        )
        if new_subgroup is not None:
            try:
                store.set_active_subgroup(session_id, new_subgroup)
            except Exception:
                logger.exception("Failed to persist active subgroup")
            held = new_subgroup
        else:
            held = getattr(session, "active_subgroup", None)

        if was_scoped_to_held_set(plan):
            response.phase = ConversationPhase.CORPUS_EXPLORATION
        response.metadata["active_subgroup"] = subgroup_summary(held)
```

> Note: the WS handler builds `response` at ~1111 before this block. Confirm the variable holding the session object in the WS scope — if the WS path loads the session into a local named `session`, use `getattr(session, "active_subgroup", None)`; if it only has `session_id`, fetch once: `held_session = store.get_session(session_id)` and read `getattr(held_session, "active_subgroup", None)`. Read `app/api/main.py:1000-1020` to confirm which local exists, and reuse it (do not add a redundant fetch if `session` is already in scope).

- [ ] **Step 2: Surface the held set in the WS clarification path**

The WS clarification branch (~1039) builds a `ChatResponse` with `candidate_set=None`. Add `"active_subgroup"` to its metadata the same way as Task 4 Step 2 (read ~1030-1045 to locate the exact `metadata=` dict and add the `subgroup_summary(...)` entry, using the WS session local confirmed in Step 1).

- [ ] **Step 3: Verify**

Run: `python -c "import app.api.main"`
Expected: exit 0.

Run: `python -m pytest tests/api -q` (or `-k "chat or session or ws or websocket"`)
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/api/main.py
git commit -m "$(cat <<'EOF'
feat(#60): WS handler writes/keeps held set, surfaces summary + phase

Mirrors the REST handler in the streaming path: persists the held set after the
narrative turn (failure-tolerant), sets corpus_exploration phase when scoped,
and surfaces the held-set summary in the complete-message metadata and the WS
clarification path.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Reset endpoint `DELETE /sessions/{session_id}/subgroup`

**Files:**
- Modify: `app/api/main.py` (new route after `expire_session`, ~893)
- Test: `tests/api/test_subgroup_reset.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_subgroup_reset.py`. Model it on the existing API test that exercises `DELETE /sessions/{id}` (the `expire_session` route) — read an existing test under `tests/api/` first and reuse its FastAPI `TestClient` + auth-cookie/login fixture verbatim. The behavior to assert:

```python
def test_reset_subgroup_clears_held_set(authed_client, store):
    """DELETE /sessions/{id}/subgroup clears the held set; next get is None."""
    from scripts.chat.models import ActiveSubgroup

    session = store.create_session(user_id=AUTHED_USER_ID)
    store.set_active_subgroup(
        session.session_id,
        ActiveSubgroup(defining_query="q", filter_summary="", record_ids=["1", "2"]),
    )

    resp = authed_client.delete(f"/sessions/{session.session_id}/subgroup")
    assert resp.status_code == 200
    assert store.get_active_subgroup(session.session_id) is None


def test_reset_subgroup_noop_when_none(authed_client, store):
    """Reset on a session with no held set is a 200 no-op."""
    session = store.create_session(user_id=AUTHED_USER_ID)
    resp = authed_client.delete(f"/sessions/{session.session_id}/subgroup")
    assert resp.status_code == 200


def test_reset_subgroup_404_for_missing_session(authed_client):
    resp = authed_client.delete("/sessions/does-not-exist/subgroup")
    assert resp.status_code == 404
```

> `authed_client`, `store`, and `AUTHED_USER_ID` must match whatever the existing API tests use. If the repo has no `tests/api/` auth fixtures, replicate the auth setup from the test that covers `GET /sessions/{id}` or `DELETE /sessions/{id}`. If no such test exists, write the endpoint test against the `expire_session` pattern using the same `require_role` override the suite already uses for authenticated routes.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_subgroup_reset.py -v`
Expected: FAIL — 404/405 (route not defined) on the reset calls.

- [ ] **Step 3: Add the endpoint**

In `app/api/main.py`, after `expire_session` (ends ~893), add:

```python
@app.delete("/sessions/{session_id}/subgroup")
async def reset_subgroup(session_id: str, user=Depends(require_role("limited"))):
    """Clear the held result set ("active subgroup") for a session.

    The frontend "Search all" reset calls this. Requires 'limited' role or
    higher; users may only reset their own sessions (admins, any). Clearing a
    session with no held set is a 200 no-op (issue #60 part 2).

    Args:
        session_id: Session identifier
        user: Authenticated user from JWT

    Returns:
        Success message

    Raises:
        HTTPException: If session not found or access denied
    """
    store = get_session_store()
    session = store.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    if str(session.user_id) != str(user["user_id"]) and user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # set_active_subgroup(None) deletes the row (no separate clear method).
    store.set_active_subgroup(session_id, None)
    return {"status": "success", "message": "Active subgroup cleared"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/api/test_subgroup_reset.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/api/main.py tests/api/test_subgroup_reset.py
git commit -m "$(cat <<'EOF'
feat(#60): DELETE /sessions/{id}/subgroup reset endpoint

Clears the held set via the existing set_active_subgroup(None) (no separate
clear method). Same auth + ownership pattern as expire_session. No-op 200 when
no set is held; 404 for unknown session.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Interpreter prompt — the three-intent model + held-set context

The scope plumbing already works; this teaches the LLM *when* to use it and
gives it the held-set defining query/count. This is the feature's main risk, so
the change is prompt-only with a prompt-discipline assertion.

**Files:**
- Modify: `scripts/chat/interpreter.py` (prompt text ~310-315; context render ~514-524)
- Test: `tests/scripts/chat/test_interpreter.py`

- [ ] **Step 1: Write the failing prompt-discipline test**

Add to `tests/scripts/chat/test_interpreter.py` (match the existing `TestPrompt*`/system-prompt test style in that file — read it first to find how the system prompt string is obtained, e.g. a `SYSTEM_PROMPT` constant or a `_build_system_prompt()` helper, and reuse it):

```python
def test_system_prompt_teaches_three_intent_model():
    """The system prompt names the three held-set intents and the keyword."""
    prompt = _get_system_prompt()  # reuse the file's existing accessor
    assert "$previous_results" in prompt
    # the three-intent vocabulary
    for token in ("new search", "explore", "refine"):
        assert token.lower() in prompt.lower()


def test_held_set_context_rendered_with_defining_query(monkeypatch):
    """When a held set is present, its defining query + count reach the prompt."""
    from scripts.chat.plan_models import SessionContext

    ctx = SessionContext(
        session_id="s1",
        previous_record_ids=[str(i) for i in range(73)],
    )
    user_prompt = _build_user_prompt("how many are in Hebrew?", ctx)  # existing builder
    assert "73" in user_prompt
    assert "$previous_results" in user_prompt
```

> Read `tests/scripts/chat/test_interpreter.py` and `scripts/chat/interpreter.py` to find the real accessor names for the system prompt and the user-prompt builder (the user-prompt builder is the function containing lines 505-533). Use those exact names; the placeholders `_get_system_prompt`/`_build_user_prompt` above must be replaced with the real ones. If a held-set *defining query* is to be rendered (not just count), the second assertion may also check a defining-query string once Step 3 passes it through — keep the count+keyword assertions regardless.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/chat/test_interpreter.py -k "three_intent or held_set_context" -v`
Expected: FAIL — the prompt lacks the "new search / explore / refine" vocabulary.

- [ ] **Step 3: Expand the FOLLOW-UP section of the system prompt**

In `scripts/chat/interpreter.py`, replace the `# FOLLOW-UP QUERIES` block (currently ~310-315):

```python
# FOLLOW-UP QUERIES

When the query is a follow-up refining previous results:
- Use scope "$previous_results" to narrow to the previous conversation's record set
- Set intents to include "follow_up"
- Consider the session context (previous messages, previous record IDs)
```

with:

```python
# FOLLOW-UP QUERIES AND THE HELD RESULT SET

When the session context includes a HELD RESULT SET (a previous result the user
is exploring — its size and defining query are given below), classify the new
query into exactly one of three intents and set scope accordingly:

1. NEW SEARCH — a fresh topic unrelated to the held set. Use scope
   "full_collection". The held set will be replaced by this turn's result.
2. EXPLORE-IN-SET — a metadata/aggregate/compare question ABOUT the held set
   ("how many are in Hebrew?", "who printed them?", "what subjects?"). Use scope
   "$previous_results" on the aggregate/find_connections step. The held set is
   left unchanged.
3. REFINE-IN-SET — a narrowing of the held set into a smaller set ("only the
   Hebrew ones", "just those after 1550"). Use scope "$previous_results" on the
   retrieve step. The narrowed result becomes the new held set (progressive
   drilling).

Rules:
- Only use scope "$previous_results" when a held set is present AND the query
  explores or refines it. Otherwise use "full_collection".
- Pronouns/anaphora ("them", "those", "these", "the Hebrew ones") referring to a
  prior result signal EXPLORE or REFINE, not a new search.
- A query naming a new entity/place/topic not in the held set is a NEW SEARCH.
- Include "follow_up" in intents for EXPLORE-IN-SET and REFINE-IN-SET.
```

- [ ] **Step 4: Render the held-set defining query in the user-prompt context**

In the user-prompt builder (~514-524), the held set's record count + IDs are
rendered. Enrich it so the LLM also sees the held set's *defining query* when
available. The `SessionContext` carries `previous_record_ids`; the defining
query lives on the session's `active_subgroup`. The cleanest path: the handlers
already build `SessionContext` from `session.active_subgroup` — extend
`SessionContext` rendering to use a defining-query string if present.

Minimal, low-risk version (no SessionContext schema change): keep rendering the
count + IDs (already present) and reword the hint to teach the three intents.
Replace lines ~518-523:

```python
            parts.append(
                f"PREVIOUS RESULT SET: {total} records (IDs: {ids_preview})"
            )
            parts.append(
                'You may use scope "$previous_results" to narrow to these records.'
            )
```

with:

```python
            parts.append(
                f"HELD RESULT SET: {total} records (IDs: {ids_preview}). "
                "The user may be exploring or refining these."
            )
            parts.append(
                'To aggregate/compare over them use scope "$previous_results" '
                "(EXPLORE-IN-SET, held set unchanged); to narrow them use scope "
                '"$previous_results" on a retrieve (REFINE-IN-SET, becomes the new '
                "held set); for a new topic use \"full_collection\" (NEW SEARCH)."
            )
```

> If you choose to surface the defining query too, add an optional
> `previous_defining_query: str | None = None` to `SessionContext`
> (`scripts/chat/plan_models.py:397-406`), have both handlers pass
> `previous_defining_query=getattr(active_sub, "defining_query", None)`, and
> render it here. This is optional polish — the count+keyword version satisfies
> the test and the feature. Do it only if time allows; otherwise skip.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/scripts/chat/test_interpreter.py -k "three_intent or held_set_context" -v`
Expected: PASS. Then run the full interpreter test file: `python -m pytest tests/scripts/chat/test_interpreter.py -v` — Expected: PASS (no regression in existing prompt tests; if an existing test asserts the old "PREVIOUS RESULT SET" / "narrow to these records" wording, update that assertion to the new wording).

- [ ] **Step 6: Commit**

```bash
git add scripts/chat/interpreter.py tests/scripts/chat/test_interpreter.py
git commit -m "$(cat <<'EOF'
feat(#60): interpreter prompt teaches the three-intent held-set model

System prompt now classifies each turn as new-search / explore-in-set /
refine-in-set and maps each to full_collection vs $previous_results scope, with
anaphora cues. User-prompt held-set hint reworded to teach the same. Reuses the
existing $previous_results keyword (no new scope keyword). Prompt-discipline
tests assert the vocabulary + keyword are present.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Narrator discloses held-set scoping

**Files:**
- Modify: `scripts/chat/narrator.py` (prompt builder, ~826)
- Test: `tests/scripts/chat/test_narrator.py` (add; or match existing narrator test file name)

- [ ] **Step 1: Write the failing test**

Find the narrator prompt-builder function (the one whose tail is at
`scripts/chat/narrator.py:837-842`, returning `"\n".join(sections)`). Read its
signature and the `ExecutionResult`/`SessionContext` it receives. Add a test to
the narrator test file (match the existing file's construction of an
`ExecutionResult` with a `session_context`):

```python
def test_narrator_prompt_discloses_held_set_when_scoped():
    """When the turn is scoped to a held set, the prompt tells the narrator
    to disclose it ('Among the N you're exploring')."""
    result = _make_execution_result_with_previous_records(count=73)  # held set present
    prompt = _build_narrator_prompt(result)  # reuse the file's real builder name
    assert "exploring" in prompt.lower()
    assert "73" in prompt
```

> Replace `_make_execution_result_with_previous_records` / `_build_narrator_prompt` with the real helpers/builders. The held set is visible to the narrator via `result.session_context.previous_record_ids` (the executor already passes `session_context` through `ExecutionResult`, see `plan_models.py:420`). If the existing narrator tests don't populate `session_context`, construct a `SessionContext(session_id="s", previous_record_ids=[...])` and attach it.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/chat/test_narrator.py -k held_set -v`
Expected: FAIL — the prompt does not mention exploring/the held-set count.

- [ ] **Step 3: Add the disclosure section to the prompt**

In `scripts/chat/narrator.py`, the `# --- Session context ---` block (~827-832)
renders recent messages. Right after it (before the final "Compose a scholarly
response…" append at ~837), add:

```python
    # --- Held-set disclosure (issue #60 part 2) ---
    if result.session_context and result.session_context.previous_record_ids:
        held_n = len(result.session_context.previous_record_ids)
        sections.append(
            f"HELD RESULT SET: this turn is scoped to {held_n} records the user "
            "is exploring. If the answer is about that subset, disclose the scope "
            f"naturally (e.g. \"Among the {held_n} you're exploring, ...\") so the "
            "user knows the count is within their held set, not the whole collection."
        )
        sections.append("")
```

> This mirrors the existing disclosure blocks (broadening notes ~811-817, truncation ~819-825). Place it adjacent to those for consistency.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/scripts/chat/test_narrator.py -k held_set -v`
Expected: PASS. Then `python -m pytest tests/scripts/chat/test_narrator.py -v` — Expected: PASS (no regression).

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/narrator.py tests/scripts/chat/test_narrator.py
git commit -m "$(cat <<'EOF'
feat(#60): narrator discloses held-set scoping in prose

When the turn is scoped to a held set (session_context.previous_record_ids),
the narrator prompt instructs disclosure ("Among the N you're exploring, ...")
so counts read as within-set, not whole-collection. Mirrors existing broadening
/ truncation disclosure blocks.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Frontend — held-set chip + reset

**Files:**
- Modify: `frontend/src/types/chat.ts`
- Modify: `frontend/src/components/chat/PhaseIndicator.tsx`
- Modify: `frontend/src/pages/Chat.tsx`

No FE test infra — verify with `npx tsc --noEmit` + targeted eslint + manual check.

- [ ] **Step 1: Add the metadata type**

In `frontend/src/types/chat.ts`, add an exported interface for the summary and
reference it where response metadata is typed. After the `ChatResponse`
interface (the file has `metadata: Record<string, unknown>` at line 71), add:

```typescript
/** Held result set summary surfaced in ChatResponse.metadata.active_subgroup. */
export interface ActiveSubgroupSummary {
  defining_query: string;
  count: number;
}
```

(Leave `metadata` as `Record<string, unknown>`; read `metadata.active_subgroup`
with a cast at the call site to avoid a broad type change.)

- [ ] **Step 2: Extend `PhaseIndicator` to render the chip + reset**

Replace `frontend/src/components/chat/PhaseIndicator.tsx` with:

```typescript
/**
 * Small pill badge showing the current conversation phase, plus an optional
 * held-set chip with a one-click reset ("Search all").
 *
 * - "Query Definition"   = purple
 * - "Exploring Results"  = emerald
 */

import type { ConversationPhase, ActiveSubgroupSummary } from '../../types/chat';

interface PhaseIndicatorProps {
  phase: ConversationPhase | null;
  heldSet?: ActiveSubgroupSummary | null;
  onReset?: () => void;
}

const PHASE_CONFIG: Record<string, { label: string; classes: string }> = {
  query_definition: {
    label: 'Query Definition',
    classes: 'bg-purple-100 text-purple-700',
  },
  corpus_exploration: {
    label: 'Exploring Results',
    classes: 'bg-emerald-100 text-emerald-700',
  },
};

export default function PhaseIndicator({ phase, heldSet, onReset }: PhaseIndicatorProps) {
  const cfg = phase ? PHASE_CONFIG[phase] : null;

  if (!cfg && !heldSet) return null;

  return (
    <span className="inline-flex items-center gap-2 flex-wrap">
      {cfg && (
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${cfg.classes}`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-current opacity-60" />
          {cfg.label}
        </span>
      )}
      {heldSet && (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-800 border border-emerald-200">
          <span>
            Exploring {heldSet.count} <bdi>{heldSet.defining_query}</bdi>
          </span>
          {onReset && (
            <button
              type="button"
              onClick={onReset}
              className="underline decoration-dotted hover:text-emerald-900 focus:outline-none focus:ring-1 focus:ring-emerald-400 rounded"
              aria-label="Clear the held result set and search the whole collection"
            >
              Search all
            </button>
          )}
        </span>
      )}
    </span>
  );
}
```

(`<bdi>` keeps Hebrew defining queries from breaking the chip's direction — per the project's BiDi convention.)

- [ ] **Step 3: Wire the summary + reset in `Chat.tsx`**

Read `frontend/src/pages/Chat.tsx` to find where `PhaseIndicator` is rendered
and where the latest `ChatResponse` (phase + metadata) is held in state. Then:

1. Derive the held set from the latest response metadata:

```typescript
const heldSet = (latestResponse?.metadata?.active_subgroup ??
  null) as ActiveSubgroupSummary | null;
```

(import `ActiveSubgroupSummary` from `../types/chat`; `latestResponse` is
whatever local already holds the most recent response — match the real name).

2. Add a reset handler that calls the endpoint and clears local held-set state:

```typescript
const handleResetSubgroup = async () => {
  if (!sessionId) return;
  try {
    await fetch(`${API_BASE}/sessions/${sessionId}/subgroup`, {
      method: 'DELETE',
      credentials: 'include',
    });
  } catch {
    /* non-fatal: next full-collection query also clears it */
  }
  // Optimistically drop the chip locally.
  setHeldSetCleared(true);
};
```

> Match the file's existing fetch convention: reuse its `API_BASE`/base-URL
> constant and its credentials/header pattern (the app authenticates via cookie;
> other calls in this file show the exact shape). If the file uses an API client
> wrapper instead of raw `fetch`, use that wrapper. `sessionId` is whatever local
> holds the current session id. For the optimistic clear, either track a
> `heldSetCleared` boolean state and gate the chip on it, or null out the stored
> response metadata — match how the file already manages response state.

3. Pass props to the indicator:

```tsx
<PhaseIndicator
  phase={latestResponse?.phase ?? null}
  heldSet={heldSetCleared ? null : heldSet}
  onReset={handleResetSubgroup}
/>
```

Reset `heldSetCleared` to `false` whenever a new response with a held set
arrives (so a subsequent search re-shows the chip).

- [ ] **Step 4: Verify types + lint**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0, no type errors.

Run: `cd frontend && npx eslint src/components/chat/PhaseIndicator.tsx src/pages/Chat.tsx src/types/chat.ts`
Expected: no new errors (pre-existing warnings in untouched code are acceptable; do not fix unrelated files).

- [ ] **Step 5: Manual check (record evidence)**

Build or dev-run the frontend and confirm: after a search, the emerald chip
shows "Exploring N <query>"; a follow-up like "how many are in Hebrew?" keeps
the chip; "Search all" removes it and the next query is full-collection. Note
the result in the testing guide (Task 10).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/chat.ts frontend/src/components/chat/PhaseIndicator.tsx frontend/src/pages/Chat.tsx
git commit -m "$(cat <<'EOF'
feat(#60): held-set chip + reset in PhaseIndicator/Chat

PhaseIndicator renders an "Exploring N <defining query>" chip with a "Search
all" reset when a held set is active (metadata.active_subgroup). Chat.tsx wires
the summary from the latest response and a reset handler hitting
DELETE /sessions/{id}/subgroup. <bdi> guards Hebrew defining queries. tsc + lint
clean.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Documentation

**Files:**
- Modify: `docs/current/chatbot-api.md`
- Modify: `docs/current/architecture.md`
- Modify: `frontend/src/pages/Help.tsx` (§16)
- Modify: `docs/testing/` manual guide (held-set chip/reset steps)

- [ ] **Step 1: `chatbot-api.md`** — add a "Held result set (active subgroup)"
subsection documenting: the three-intent model; that scoping reuses the
`$previous_results` keyword; `ChatResponse.metadata.active_subgroup =
{defining_query, count} | null`; `phase = corpus_exploration` when scoped; and
the `DELETE /sessions/{id}/subgroup` reset endpoint (auth, 200 no-op, 404).
Set `Last verified: 2026-06-13` in the header.

- [ ] **Step 2: `architecture.md`** — change the active_subgroup status from
"dormant/scaffolded" to "wired"; note the policy module
`scripts/chat/subgroup_policy.py` and the load path
`get_session → get_active_subgroup → ChatSession.active_subgroup →
SessionContext.previous_record_ids → executor $previous_results`. Set
`Last verified: 2026-06-13`.

- [ ] **Step 3: `Help.tsx` §16** — tighten the follow-up claim to state
follow-ups are "scoped to exactly these records" (the parked claim from the
spec's "Docs to update"). Keep humanities-scholar plain language; `<bdi>` any
Hebrew. Run `cd frontend && npx tsc --noEmit` after editing.

- [ ] **Step 4: Testing guide** — add a manual scenario: search → chip appears →
explore (count) keeps chip → refine narrows chip count → "Search all" clears it.

- [ ] **Step 5: Commit**

```bash
git add docs/current/chatbot-api.md docs/current/architecture.md frontend/src/pages/Help.tsx docs/testing
git commit -m "$(cat <<'EOF'
docs(#60): document the wired held-set (active_subgroup) feature

chatbot-api.md: three-intent model, $previous_results scoping, metadata summary,
reset endpoint. architecture.md: active_subgroup now wired + load path + policy
module. Help.tsx §16: follow-ups scoped to exactly the held records. Testing
guide: manual chip/reset scenario.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Full verification gate

- [ ] **Step 1: Full Python suite (non-integration)**

Run: `python -m pytest -m "not integration" -q`
Expected: all green. Read the summary line; 0 failures.

- [ ] **Step 2: Integration suite (includes the invariant battery)**

Run: `python -m pytest -m integration -q`
Expected: all green (this feature does not touch the bibliographic DB or
invariants; confirm no regression).

- [ ] **Step 3: Lint/format**

Run: `ruff check scripts/chat/subgroup_policy.py scripts/chat/models.py scripts/chat/session_store.py scripts/chat/interpreter.py scripts/chat/narrator.py app/api/main.py && ruff format --check scripts/chat/subgroup_policy.py`
Expected: no errors on the files this plan created/modified. (Pre-existing
errors elsewhere are out of scope — confirm any error is in an untouched file
before ignoring it.)

- [ ] **Step 4: Frontend types**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 5: Requirements checklist against the spec**

Re-read `docs/superpowers/specs/2026-06-13-active-subgroup-scoping-design.md` and
confirm each of the five touchpoints is implemented: (1) write — Tasks 4/5;
(2) load+attach — Tasks 1/2; (3) scope — pre-existing `$previous_results`
(reused, documented in Key Decisions); (4) interpreter — Task 7; (5)
surface+reset — Tasks 4/5/6/8/9. Confirm clearing rules (new-search replace,
explicit reset, new session) and error handling (empty/clarification untouched,
stale held set degrades, reset no-op) hold. Note any gap.

- [ ] **Step 6: Final commit if any verification fixups were needed**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore(#60): verification fixups for active_subgroup wiring

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review notes (author, 2026-06-13)

- **Spec coverage:** All five touchpoints mapped to tasks (write 4/5, load+attach
  1/2, scope reused, interpreter 7, surface+reset 4/5/6/8/9). Clearing rules and
  error handling covered by the policy module (empty → None) + reset endpoint
  (no-op) + executor's existing empty-scope degradation. Out-of-scope items
  (user_goals, multiple subgroups, set algebra) are not built.
- **Divergences from spec, intentional:** reuse `$previous_results` instead of a
  new `"active_subgroup"` scope keyword (spec §3); reuse
  `set_active_subgroup(None)` instead of a new `clear_active_subgroup` (spec §5).
  Both documented in "Key decisions" with the code evidence. The lifecycle is
  derived deterministically from step shape on the handler side rather than from
  an LLM-emitted intent string, which is more robust and testable.
- **Type consistency:** `build_subgroup_update(plan, candidate_set, query_text)`,
  `summarize_filters(plan)`, `subgroup_summary(subgroup)`,
  `was_scoped_to_held_set(plan)` are used with identical signatures across
  policy module, handlers, and tests. `ActiveSubgroup` fields
  (`candidate_set, defining_query, filter_summary, record_ids, created_at`) match
  `scripts/chat/models.py:58-86`. `ChatResponse.metadata.active_subgroup` shape
  `{defining_query, count}` matches `ActiveSubgroupSummary` in the frontend type.
- **Known edge case (documented, accepted):** a "compare to Amsterdam" turn that
  generates a full-collection retrieve will replace the held set (the spec lists
  compare under explore-in-set). The chip + one-click reset make this visible and
  recoverable, so the simple step-shape rule is kept rather than special-casing
  compare. Noted for the gold-suite manual quality pass.
- **Placeholders:** test helper names that depend on the existing test files'
  conventions (`_get_system_prompt`, `_build_user_prompt`, `_build_narrator_prompt`,
  `authed_client`, `store`) are flagged inline with "read the file and use the
  real name" — these are deliberate handoff notes, not unfilled blanks, because
  the real accessor names must be read from the test files at execution time.
