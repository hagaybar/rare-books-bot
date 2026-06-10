# Narrator Failure -- Root Cause (Confirmed)

Date: 2026-04-13
Introducing commit: `54f4338` ("feat: chat UX improvements -- truncation, progress stages, entity follow-ups")

## Exception

```
NameError: name 'agents' is not defined
```

Raised at `scripts/chat/narrator.py`, line 762, inside `build_lean_narrator_prompt()`.
The outer `except Exception` handler at line 224 catches it and returns `_fallback_response()`,
masking the error as a silent degradation (fallback narrative instead of a full scholarly response).

## Root Cause

Commit `54f4338` added an identical "Follow-up hints" block to **two** functions:

| Function | Defined at | `agents` assigned? | Outcome |
|---|---|---|---|
| `build_lean_narrator_prompt()` | line 597 | No -- variable never assigned | **NameError on line 762** |
| `_build_narrator_prompt()` | line 802 | Yes -- `agents = result.grounding.agents` at line 874 | Works correctly |

The block was copy-pasted from `_build_narrator_prompt()` into `build_lean_narrator_prompt()`
without adding the prerequisite assignment. In the lean function, `records` is assigned (line 636)
but `agents` is not.

## Evidence

1. **Diff of commit 54f4338** (`git diff 54f4338^..54f4338 -- scripts/chat/narrator.py`):
   - Lines 760-792 added to `build_lean_narrator_prompt()` -- uses bare `agents` on line 762.
   - Lines 946-978 added to `_build_narrator_prompt()` -- uses `agents` which is assigned at line 874.
2. **grep for `agents =`** in narrator.py: only two assignments exist -- line 874 (`_build_narrator_prompt`) and line 1037 (unrelated `_format_grounding_section`). Neither is in `build_lean_narrator_prompt`.
3. **Traceback** from `debug_narrator.py` confirms the exact location: line 762, `if agents:`.
4. **Pipeline state at failure**: interpret succeeded (1 step, intent=retrieval), execute succeeded (30 records, 28 agents, 2 publishers), prompt build failed with NameError.

## Fix

Insert the missing assignment before line 762 in `build_lean_narrator_prompt()`:

```python
    # --- Follow-up hints (deterministic data for better suggestions) ---
    agents = result.grounding.agents          # <-- ADD THIS LINE
    hint_lines: list[str] = []
    if agents:
```

This mirrors the pattern already present in `_build_narrator_prompt()` at line 874.

## Safe Changes (unrelated to this bug)

The same commit (`54f4338`) made three other changes that are **not affected** by this bug:

1. **`app/api/main.py`** (lines 1010-1074): Added `"stage"` field to WebSocket `thinking` messages and a new "Composing scholarly response..." thinking event before narration. These are pure additive JSON fields and do not touch prompt building.
2. **`frontend/src/components/chat/ThinkingBlock.tsx`** (lines 23-51): Added a pipeline stage indicator (Interpret -> Execute -> Narrate) to the thinking UI. Frontend-only; no backend interaction beyond reading the existing `text` field.
3. **`scripts/chat/narrator.py` truncation notice** (lines 745-750, 932-937): Changed the truncation wording from a generic note to an f-string with `len(records)` and `result.total_record_count`. This change is safe because `records` is properly assigned in both functions.
