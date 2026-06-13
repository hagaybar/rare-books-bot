# Held-Set Correctness Fixes

**Date**: 2026-06-13
**Status**: Approved (user, 2026-06-13; "fix all three via plan→babysitter" — design + spec + plan pre-approved in-session)
**Issue**: follow-up to #60 part 2; folds in #61. New issues to be opened for #B1/#B2/#B3.

## Origin

A live two-turn prod test of the just-shipped `active_subgroup` held-set feature
(session `280bf52a…`, feedback report `fb_20260613T155400Z_c3f018`) exposed three
real defects. Turn 1 *"books printed in Venice in the 16th century"* matched **74**
records; turn 2 *"How many are in Hebrew?"* returned the circular answer *"Among
the 9 … you are currently exploring, all 9 are in Hebrew."* Diagnosis traced this
to three causes, fixed here as one batch.

## The three defects

### B1 — Held set captures the truncated display list, not the full result (deterministic)
Turn 1 matched 74 records but the held set stored only the **30** displayed.
Root cause: the write path builds the held set's `record_ids` from
`_build_candidate_set(...).candidates`, which is sourced from
`grounding.records` — and `_collect_grounding` truncates that to
`_MAX_GROUNDING_RECORDS` (30) for display, while the true count lives in
`total_record_count` (74). So every follow-up explores 30, not 74, and counts
over the held set undercount. **This is the most serious defect and the root of
the others.**

The full set is already available: each retrieve step's `RecordSet.mms_ids`
(`execution_result.steps_completed[*].data.mms_ids`) is the complete, untruncated
match list; `total_record_count` equals the size of their deduped union.

### B2 — Aggregate questions misclassified as refine (interpreter judgment)
*"How many are in Hebrew?"* should be **explore-in-set**: a single
`aggregate scope=$previous_results` that counts within the held set and leaves it
unchanged. Instead the interpreter emitted `retrieve scope=$previous_results`
(narrow to Hebrew) **then** `aggregate scope=$step_0`. That (a) replaced the held
set with the 9 Hebrew records and (b) made the answer circular (it pre-filtered to
Hebrew, then counted Hebrew = all 9). The three-intent prompt did not steer
counting questions away from a narrowing retrieve. This is the LLM-judgment risk
the #60 spec flagged; the fix is prompt rules + few-shot, validated manually.

### B3 — Disclosure conflates held-set size with the answer count (narrator)
The prose reused "9" for both the held set and the answer. The disclosure must
name the held-set size (and its defining query) distinctly from the answer. This
only reads correctly once B1 supplies the true held-set size and B2 stops the
narrowing. Also folds in **#61**: the disclosure currently lives only in the lean
builder `build_lean_narrator_prompt`; bring the full builder `_build_narrator_prompt`
to parity.

## Fix design

### B1 — full held set
- Add `held_record_ids(execution_result)` to `scripts/chat/subgroup_policy.py`:
  the order-preserving deduped union of `sr.data.mms_ids` for every
  `steps_completed` entry whose `data` is a `RecordSet` (matches the
  `_collect_grounding` union; its length equals `total_record_count`).
- Change `build_subgroup_update` to take the `ExecutionResult` (not the truncated
  `CandidateSet`) and set `ActiveSubgroup.record_ids` = `held_record_ids(result)`,
  `candidate_count` = `result.total_record_count`. "Has a retrieve that produced
  records" becomes "`held_record_ids(result)` is non-empty". The optional
  `ActiveSubgroup.candidate_set` may stay `None` (the truncated display set is not
  the held set).
- Update both handler call sites in `app/api/main.py` to pass `execution_result`.

### B2 — explore vs refine
- In the interpreter system prompt (`scripts/chat/interpreter.py`), under the
  three-intent section, add an explicit rule + few-shot:
  *A counting/"how many"/"what are the" question about the held set is
  EXPLORE-IN-SET — emit a single `aggregate` (or `find_connections`) step with
  `scope = "$previous_results"` and do NOT precede it with a `retrieve` that
  narrows. Reserve `retrieve scope="$previous_results"` for REFINE ("only the
  Hebrew ones", "just those after 1550"), where the user wants the narrowed set
  as the new working set.*
- Few-shot: held set present + *"how many are in Hebrew?"* →
  `[aggregate field=language scope=$previous_results]` (explore, unchanged);
  *"only the Hebrew ones"* → `[retrieve <hebrew filter> scope=$previous_results]`
  (refine, replaces). Prompt-discipline test asserts the rule/keywords are present.

### B3 — disclosure clarity + full-builder parity
- Tighten the held-set disclosure block (both builders) so it states the held-set
  **size and defining query** as distinct from the answer, e.g.
  *"The user is exploring a held set of N records (defining query: '…'). If this
  answer is a count or facet over that set, phrase it as 'X of those N', never
  reusing one number for both."* Use `len(previous_record_ids)` for N (correct
  once B1 lands).
- Add the same disclosure block to `_build_narrator_prompt` (closes #61).
- Tests assert both builders disclose when a held set is present.

## Out of scope (YAGNI)
- `app_git_sha: "unknown"` in feedback reports (separate minor feedback-feature
  gap; note as a tiny follow-up, do not fix here).
- Changing the 30-record display/grounding truncation (correct for the narrator;
  only the held set must use the full set).
- Multi/named subgroups, set algebra (already out of scope for #60).

## Testing (deterministic — no live LLM)
- **B1**: `held_record_ids` returns the deduped union across retrieve steps;
  `build_subgroup_update` with a truncated grounding but full retrieve `mms_ids`
  yields a held set of the FULL size (regression for the exact 74-vs-30 bug);
  aggregate-only turn still returns `None` (unchanged).
- **B2**: prompt-discipline test asserts the explore-vs-refine rule + the
  `aggregate scope=$previous_results` few-shot for a counting question.
- **B3**: both narrator builders include the disclosure with the held-set size and
  defining query when a held set is present; the wording instruction is present.
- Full suite green + ruff clean on touched files + frontend `tsc` (no FE change
  expected; run as a guard).
- LLM judgment **quality** (B2) re-validated manually by re-running the same
  two-turn prod scenario after deploy.

## Docs to update
- `docs/current/chatbot-api.md` — held set is the full match set; explore vs
  refine semantics; disclosure phrasing.
- `docs/current/architecture.md` — `Last verified` bump; note held-set = full set.

## Rollout
- Branch `fix/held-set-correctness` off `dev`; TDD per task; full-suite gate;
  merge to `dev`; close #61 + the new B-issues with evidence. **Deploy to prod is
  the user's call after the run** (then re-run the two-turn scenario to confirm).
