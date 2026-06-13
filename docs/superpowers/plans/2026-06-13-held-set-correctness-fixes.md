# Held-Set Correctness Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fix the three held-set defects a live two-turn prod test surfaced (B1 truncated held set, B2 explore-vs-refine misclassification, B3 disclosure conflation), so a counting follow-up over a 74-record held set answers "N of 74" instead of the circular "9 of 9".

**Architecture:** B1 is deterministic — source the held set's `record_ids` from the retrieve steps' full `mms_ids` (whose deduped-union size equals `total_record_count`) instead of the truncated display `candidate_set`. B2 is a prompt change steering counting questions to a single `aggregate scope=$previous_results`. B3 tightens the narrator disclosure (both builders) to name the held-set size distinctly. Spec: `docs/superpowers/specs/2026-06-13-held-set-correctness-fixes-design.md`.

**Tech Stack:** Python 3 / Pydantic / FastAPI (backend), pytest, prompt strings.

---

## Key facts (verified in code)
- `executor._collect_grounding` (`scripts/chat/executor.py:1946-1992`) unions every retrieve step's `RecordSet.mms_ids` into `mms_to_steps`, sets `total_record_count = len(all_mms)` (74), then truncates `all_mms` to `_MAX_GROUNDING_RECORDS` (30) **only** for building display `records`. So the full set lives in `execution_result.steps_completed[*].data.mms_ids` and in `execution_result.total_record_count`.
- `app/api/main.py` builds `candidate_set` from `grounding.records` (truncated 30) via `_build_candidate_set`, then `build_subgroup_update(plan, response.candidate_set, …)` uses `candidate_set.candidates` → 30. **This is the B1 bug.**
- `ExecutionResult` (`scripts/chat/plan_models.py:409-422`) has `steps_completed: list[StepResult]`, `total_record_count: int`. `StepResult.data` is a `RecordSet` for retrieve steps; `RecordSet.mms_ids` is the full match list.
- `build_subgroup_update(plan, candidate_set, query_text)` and `was_scoped_to_held_set(plan)` / `summarize_filters(plan)` / `subgroup_summary(sub)` live in `scripts/chat/subgroup_policy.py`. Two call sites in `app/api/main.py` (REST ~after the assistant `add_message`; WS ~after the WS `add_message` try/except), both with `execution_result` in scope.

## File structure
| File | Change |
|---|---|
| `scripts/chat/subgroup_policy.py` | Add `held_record_ids(execution_result)`; change `build_subgroup_update` to take `ExecutionResult` and use the full id set. (B1) |
| `app/api/main.py` | Both `build_subgroup_update(...)` calls pass `execution_result` instead of `response.candidate_set`. (B1) |
| `scripts/chat/interpreter.py` | System-prompt explore-vs-refine rule + few-shot. (B2) |
| `scripts/chat/narrator.py` | Tighten disclosure (size vs answer) in `build_lean_narrator_prompt`; add the same block to `_build_narrator_prompt`. (B3, #61) |
| `tests/scripts/chat/test_subgroup_policy.py` | B1 tests incl. the 74-vs-30 regression. |
| `tests/scripts/chat/test_interpreter.py` | B2 prompt-discipline test. |
| `tests/scripts/chat/test_narrator.py` | B3 both-builder disclosure tests. |
| `docs/current/chatbot-api.md`, `docs/current/architecture.md` | Doc updates. |

---

## Task 1: B1 — held set uses the full result, not the truncated display

**Files:**
- Modify: `scripts/chat/subgroup_policy.py`
- Modify: `app/api/main.py` (two call sites)
- Test: `tests/scripts/chat/test_subgroup_policy.py`

- [ ] **Step 1: Write the failing tests**

In `tests/scripts/chat/test_subgroup_policy.py`, the existing helpers build plans and candidate sets. Add an `ExecutionResult` helper and the new tests. First add imports at the top (alongside existing imports):

```python
from scripts.chat.plan_models import (
    ExecutionResult,
    GroundingData,
    RecordSet,
    StepResult,
)
```

Then add a helper and tests (match the file's existing helper style — `_plan`, `_retrieve_step`, etc.):

```python
def _exec_result(retrieve_ids_per_step, total_record_count):
    """Build an ExecutionResult with one retrieve StepResult per id-list."""
    steps = []
    for i, ids in enumerate(retrieve_ids_per_step):
        steps.append(StepResult(
            step_index=i,
            label="retrieve",
            action="retrieve",
            status="ok",
            data=RecordSet(mms_ids=list(ids), total_count=len(ids), filters_applied=[]),
        ))
    return ExecutionResult(
        steps_completed=steps,
        directives=[],
        grounding=GroundingData(records=[], agents=[], aggregations={}),
        original_query="q",
        total_record_count=total_record_count,
    )


def test_held_record_ids_unions_retrieve_steps_dedup_order():
    from scripts.chat.subgroup_policy import held_record_ids
    result = _exec_result([["1", "2", "3"], ["3", "4"]], total_record_count=4)
    assert held_record_ids(result) == ["1", "2", "3", "4"]


def test_held_record_ids_empty_when_no_retrieve():
    from scripts.chat.subgroup_policy import held_record_ids
    result = _exec_result([], total_record_count=0)
    assert held_record_ids(result) == []


def test_build_subgroup_update_uses_full_set_not_truncated_display():
    """Regression for the 74-vs-30 bug: held set is the FULL retrieve set,
    even though the display/grounding (and any candidate_set) was truncated."""
    plan = _plan([_retrieve_step(scope="full_collection")])
    full_ids = [str(i) for i in range(74)]
    result = _exec_result([full_ids], total_record_count=74)
    sub = build_subgroup_update(plan, result, "printed in Venice")
    assert sub is not None
    assert len(sub.record_ids) == 74           # NOT 30
    assert sub.record_ids == full_ids


def test_build_subgroup_update_none_when_no_records():
    plan = _plan([_retrieve_step(scope="full_collection")])
    result = _exec_result([[]], total_record_count=0)
    assert build_subgroup_update(plan, result, "q") is None


def test_build_subgroup_update_none_for_aggregate_only_turn():
    plan = _plan([_aggregate_step(scope="$previous_results")])
    # An aggregate-only turn has no retrieve RecordSet -> no held-set redefinition
    result = _exec_result([], total_record_count=0)
    assert build_subgroup_update(plan, result, "how many in Hebrew?") is None
```

> Note: the existing tests pass `candidate_set` to `build_subgroup_update`; Step 3 changes the signature, so UPDATE the existing `test_new_search_replaces_held_set` / `test_refine_in_set_replaces_held_set` / `test_explore_in_set_leaves_held_set_unchanged` / `test_empty_result_leaves_held_set_unchanged` / `test_no_candidate_set_leaves_held_set_unchanged` to build an `ExecutionResult` via `_exec_result(...)` and pass it instead of a `CandidateSet`. Keep their intent: new-search/refine (retrieve with ids) → replace; explore (no retrieve ids) / empty → None. Delete `test_no_candidate_set_leaves_held_set_unchanged` or repurpose it as "no retrieve steps → None".

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `PYTHONPATH=. poetry run pytest tests/scripts/chat/test_subgroup_policy.py -q 2>&1 | tail -8`
Expected: the new tests FAIL (`held_record_ids` undefined; `build_subgroup_update` still expects a `CandidateSet`).

- [ ] **Step 3: Implement `held_record_ids` and rework `build_subgroup_update`**

In `scripts/chat/subgroup_policy.py`, update the imports:

```python
from scripts.chat.plan_models import ExecutionResult, InterpretationPlan, RecordSet, StepAction
```

(remove the now-unused `CandidateSet` import if nothing else uses it — check the file).

Add the helper:

```python
def held_record_ids(execution_result: ExecutionResult) -> list[str]:
    """The full held-set ids: order-preserving deduped union of every retrieve
    step's RecordSet.mms_ids. Its length equals total_record_count — this is the
    UNtruncated set, unlike the display grounding (capped at 30)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for step in execution_result.steps_completed:
        data = getattr(step, "data", None)
        if isinstance(data, RecordSet):
            for mms in data.mms_ids:
                if mms not in seen:
                    seen.add(mms)
                    ordered.append(mms)
    return ordered
```

Replace `build_subgroup_update` with:

```python
def build_subgroup_update(
    plan: InterpretationPlan,
    execution_result: ExecutionResult,
    query_text: str,
) -> Optional[ActiveSubgroup]:
    """Decide the held-set update for a completed turn.

    Returns an ActiveSubgroup to replace the held set, or None to leave it
    unchanged. A turn redefines the held set iff it produced a non-empty retrieve
    result (new search or refine-in-set). The held set's record_ids are the FULL
    match set (held_record_ids), NOT the truncated display set — fixes the
    74-vs-30 defect. Aggregate-only (explore) and empty/clarification turns return
    None.
    """
    has_retrieve = any(
        step.action == StepAction.RETRIEVE for step in plan.execution_steps
    )
    if not has_retrieve:
        return None

    record_ids = held_record_ids(execution_result)
    if not record_ids:
        return None

    return ActiveSubgroup(
        candidate_set=None,
        defining_query=query_text,
        filter_summary=summarize_filters(plan),
        record_ids=record_ids,
    )
```

(`ActiveSubgroup(candidate_set=None, …, record_ids=record_ids)` — the model's `__init__` only derives `record_ids` from `candidate_set` when `record_ids` is empty, so passing `record_ids` explicitly is honored.)

- [ ] **Step 4: Update both handler call sites**

In `app/api/main.py`, the REST write block:

```python
    new_subgroup = build_subgroup_update(
        plan, response.candidate_set, chat_request.message
    )
```
becomes
```python
    new_subgroup = build_subgroup_update(
        plan, execution_result, chat_request.message
    )
```

And the WS write block:
```python
        new_subgroup = build_subgroup_update(
            plan, response.candidate_set, message
        )
```
becomes
```python
        new_subgroup = build_subgroup_update(
            plan, execution_result, message
        )
```

(`execution_result` is already in scope at both sites. `subgroup_summary` still takes the `ActiveSubgroup` and now reports the true count.)

- [ ] **Step 5: Run tests to verify pass + handler imports**

Run: `PYTHONPATH=. poetry run pytest tests/scripts/chat/test_subgroup_policy.py -q 2>&1 | tail -6`
Expected: PASS (all, incl. the 74-record regression).
Run: `PYTHONPATH=. poetry run python -c "import app.api.main"` — Expected: exit 0.
Run: `poetry run ruff check scripts/chat/subgroup_policy.py 2>&1 | tail -3` — Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add scripts/chat/subgroup_policy.py app/api/main.py tests/scripts/chat/test_subgroup_policy.py
git commit -m "$(cat <<'EOF'
fix(B1): held set captures the full result, not the truncated display

build_subgroup_update now takes the ExecutionResult and sources record_ids from
held_record_ids() — the deduped union of retrieve steps' full mms_ids (== total_
record_count) — instead of the candidate_set built from the 30-record display
grounding. Fixes the 74-vs-30 defect where follow-ups explored only the displayed
subset. Both REST+WS handlers pass execution_result.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: B2 — counting questions explore (aggregate), not refine (narrow)

**Files:**
- Modify: `scripts/chat/interpreter.py` (three-intent section of the system prompt)
- Test: `tests/scripts/chat/test_interpreter.py`

- [ ] **Step 1: Write the failing prompt-discipline test**

In `tests/scripts/chat/test_interpreter.py` (reuse the `INTERPRETER_SYSTEM_PROMPT` accessor the existing `TestPromptThreeIntentHeldSet` tests use):

```python
def test_system_prompt_steers_counting_questions_to_aggregate():
    """Counting/'how many' questions over the held set must aggregate over
    $previous_results, not retrieve-then-narrow (B2)."""
    prompt = INTERPRETER_SYSTEM_PROMPT
    low = prompt.lower()
    assert "how many" in low
    assert "aggregate" in low
    # The rule must explicitly tie counting questions to scope $previous_results
    # without a narrowing retrieve.
    assert "$previous_results" in prompt
    assert ("do not" in low) or ("don't" in low) or ("never" in low)
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=. poetry run pytest tests/scripts/chat/test_interpreter.py -k counting -v 2>&1 | tail -6`
Expected: FAIL (the prompt lacks the "how many … aggregate, do not narrow" rule).

- [ ] **Step 3: Add the rule + few-shot to the three-intent section**

In `scripts/chat/interpreter.py`, within the `# FOLLOW-UP QUERIES AND THE HELD RESULT SET` block (added in #60), append after the three intents list and before the "Rules:" list (or extend "Rules:"):

```python
EXPLORE vs REFINE — the critical distinction:
- A COUNTING or FACET question about the held set ("how many are in Hebrew?",
  "what languages?", "who printed them?", "how many per century?") is
  EXPLORE-IN-SET. Emit a SINGLE `aggregate` (or `find_connections`) step with
  scope "$previous_results". Do NOT precede it with a `retrieve` that narrows the
  set first — that corrupts the count (it would count within the narrowed subset)
  and wrongly replaces the held set.
- Only REFINE ("only the Hebrew ones", "just those after 1550", "keep the folios")
  uses `retrieve` with scope "$previous_results": the user wants the narrowed SET
  itself as the new working set.

Examples (a held set of 74 Venice 16th-century books is active):
- "How many are in Hebrew?"  ->  [ aggregate field=language scope="$previous_results" ]
  (EXPLORE: counts Hebrew among all 74; held set stays 74)
- "Only the Hebrew ones"     ->  [ retrieve <language=Hebrew filter> scope="$previous_results" ]
  (REFINE: held set becomes the Hebrew subset)
```

- [ ] **Step 4: Run to verify pass + full interpreter file**

Run: `PYTHONPATH=. poetry run pytest tests/scripts/chat/test_interpreter.py -q 2>&1 | tail -5`
Expected: PASS (new test + existing prompt tests). If an existing test asserts exact prompt wording that this insertion shifts, update that assertion.

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/interpreter.py tests/scripts/chat/test_interpreter.py
git commit -m "$(cat <<'EOF'
fix(B2): steer counting questions to aggregate-over-held-set, not narrow

The interpreter prompt now explicitly classifies "how many / what are the X"
follow-ups as EXPLORE-IN-SET (single aggregate, scope $previous_results, held set
unchanged) and reserves retrieve+$previous_results for REFINE only, with a
two-example few-shot. Fixes the circular "among the 9, all 9 are Hebrew" answer
where a counting question narrowed-then-counted.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: B3 — disclosure names held-set size distinctly + full-builder parity (#61)

**Files:**
- Modify: `scripts/chat/narrator.py` (`build_lean_narrator_prompt` and `_build_narrator_prompt`)
- Test: `tests/scripts/chat/test_narrator.py`

- [ ] **Step 1: Write the failing tests**

In `tests/scripts/chat/test_narrator.py` (reuse the `_make_execution_result` helper + `SessionContext` import added in #60). The lean builder is `build_lean_narrator_prompt`; the full builder is `_build_narrator_prompt`. Add:

```python
def test_lean_builder_discloses_held_set_size_distinctly():
    result = _make_execution_result(
        session_context=SessionContext(session_id="s", previous_record_ids=[str(i) for i in range(74)]),
    )
    prompt = build_lean_narrator_prompt("how many are in Hebrew?", result)
    low = prompt.lower()
    assert "74" in prompt
    assert "held set" in low or "exploring" in low
    # instruction to not reuse one number for both
    assert "of those" in low or "never reusing" in low or "distinct" in low


def test_full_builder_also_discloses_held_set():
    """#61: the non-lean builder must disclose too."""
    result = _make_execution_result(
        session_context=SessionContext(session_id="s", previous_record_ids=[str(i) for i in range(74)]),
    )
    prompt = _build_narrator_prompt("how many are in Hebrew?", result)
    low = prompt.lower()
    assert "74" in prompt
    assert "held set" in low or "exploring" in low
```

> Confirm the full builder's real name/signature by reading `scripts/chat/narrator.py` (the lean one's tail is ~837-842; the full one is the separate builder, ~line 850). If `_build_narrator_prompt` takes a different argument order than `build_lean_narrator_prompt`, match it in the test.

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=. poetry run pytest tests/scripts/chat/test_narrator.py -k "held_set or builder_also or distinctly" -v 2>&1 | tail -8`
Expected: FAIL — the tightened wording is absent and the full builder has no disclosure.

- [ ] **Step 3: Tighten the lean block and add it to the full builder**

Define the disclosure text once and use it in both builders. In `scripts/chat/narrator.py`, replace the existing lean-builder disclosure block (added in #60, after `# --- Session context ---`) with this tightened version, and add the identical block at the equivalent point in `_build_narrator_prompt`:

```python
    # --- Held-set disclosure (issue #60; tightened B3; full-builder parity #61) ---
    if result.session_context and result.session_context.previous_record_ids:
        held_n = len(result.session_context.previous_record_ids)
        sections.append(
            f"HELD RESULT SET: the user is exploring a held set of {held_n} records. "
            f"This turn is scoped to that set. If the answer is a count or facet over "
            f"the set, phrase it as 'X of those {held_n}' (e.g. \"Of the {held_n} you're "
            f"exploring, X are in Hebrew\") — state the held-set size and the answer as "
            f"DISTINCT numbers; never reuse one number for both."
        )
        sections.append("")
```

If extracting a shared helper is cleaner than duplicating, define `def _held_set_disclosure(result) -> list[str]:` returning the two `sections` lines and call it in both builders — but only if both builders use the same `sections` list idiom (verify first).

- [ ] **Step 4: Run to verify pass + full file**

Run: `PYTHONPATH=. poetry run pytest tests/scripts/chat/test_narrator.py -q 2>&1 | tail -5`
Expected: PASS (new + existing, incl. the #60 `test_narrator_prompt_discloses_held_set_when_scoped` — update it if its assertion conflicts with the new wording, keeping the "exploring"+count checks).

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/narrator.py tests/scripts/chat/test_narrator.py
git commit -m "$(cat <<'EOF'
fix(B3,#61): disclose held-set size distinctly; full-builder parity

Both narrator builders now disclose the held-set size as a number DISTINCT from
the answer count ("Of the N you're exploring, X are ..."), preventing the
"among the 9, all 9 are Hebrew" conflation. The disclosure block was added to the
full builder _build_narrator_prompt (closes #61), not just the lean one.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Docs

**Files:** `docs/current/chatbot-api.md`, `docs/current/architecture.md`

- [ ] **Step 1:** In `chatbot-api.md` (held-set subsection from #60): state the held set is the **full** match set (not the displayed subset); clarify explore (aggregate, unchanged) vs refine (retrieve, replaces); note the disclosure phrases size and answer as distinct numbers. `Last verified: 2026-06-13`.
- [ ] **Step 2:** In `architecture.md`: note `subgroup_policy.held_record_ids` sources the full retrieve union; `Last verified: 2026-06-13`.
- [ ] **Step 3: Commit**

```bash
git add docs/current/chatbot-api.md docs/current/architecture.md
git commit -m "docs(B1/B2/B3): held set is the full match set; explore vs refine; disclosure phrasing

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Full verification gate

- [ ] **Step 1:** `PYTHONPATH=. poetry run pytest -q -m "not integration" 2>&1 | tail -4` — 0 failures.
- [ ] **Step 2:** `PYTHONPATH=. poetry run pytest -q -m integration 2>&1 | tail -3` — 0 failures.
- [ ] **Step 3:** `poetry run ruff check scripts/chat/subgroup_policy.py scripts/chat/interpreter.py scripts/chat/narrator.py app/api/main.py 2>&1 | tail -4` — no NEW errors in touched lines (pre-existing debt acceptable; confirm any error is on an untouched line).
- [ ] **Step 4:** `cd frontend && npx tsc --noEmit 2>&1 | tail -3` — exit 0 (guard; no FE change expected).
- [ ] **Step 5:** Re-read the spec; confirm B1/B2/B3 each implemented and the 74-vs-30 regression is locked by a test.

---

## Self-review notes (author, 2026-06-13)
- **Spec coverage:** B1 (Task 1), B2 (Task 2), B3 + #61 (Task 3), docs (Task 4), gate (Task 5). All mapped.
- **Type consistency:** `build_subgroup_update(plan, execution_result, query_text)` used identically in policy, both handlers, and tests; `held_record_ids(execution_result) -> list[str]`; `ActiveSubgroup(candidate_set=None, defining_query, filter_summary, record_ids)`.
- **Signature-change risk:** changing `build_subgroup_update`'s 2nd arg from `CandidateSet` to `ExecutionResult` breaks the existing #60 policy tests — Task 1 Step 1 explicitly updates them. Grep for other callers before finishing (`grep -rn build_subgroup_update`): only the two handler sites + tests should exist.
- **B2 is judgment, not determinism:** the prompt rule is verified by a discipline test; true behavior is re-validated by re-running the two-turn prod scenario after deploy (out of band).
- **Placeholders:** narrator full-builder name and the `_make_execution_result`/`INTERPRETER_SYSTEM_PROMPT` accessors are flagged "read the file and use the real name" — deliberate handoff notes (the #60 batch already established these real names: `INTERPRETER_SYSTEM_PROMPT`, `build_lean_narrator_prompt`, `_build_narrator_prompt`, `_make_execution_result`).
