# Regression Analysis Report

**Date:** 2026-04-12
**Incident:** Scholarly narration missing from chat responses after deployment
**Test query:** "ספרים בשפה העברית שהודפסו באמסטרדם" (Hebrew books printed in Amsterdam)
**Symptom:** 30 records returned as raw bullet list with Primo links; scholarly narrative absent
**Severity:** User-facing degradation (data intact, presentation broken)

---

## Summary

On 2026-04-12 between 11:19 and 11:32 UTC, the production chatbot served a degraded response to an Amsterdam Hebrew books query. Instead of the expected scholarly narrative (historical context, curated examples, analysis), the user received a raw fallback list of 30 records with catalog links. The root cause was an intermediate deployment of uncommitted working-tree code via `deploy.sh`, which pushed `narrator.py` changes that referenced new Pydantic model fields not yet synchronized across `plan_models.py` and `executor.py`. The narrator's `_fallback_response()` function activated, masking the underlying `AttributeError`. A second deployment at 11:33 UTC restored correct behavior.

---

## Timeline

All times are UTC on 2026-04-12.

| Time | Event | Evidence |
|------|-------|----------|
| 10:32:09 | Venice query succeeds: interpreter (132 output tokens) + narrator_meta logged | llm_calls.jsonl entries 4-5; appLog: "WebSocket scholar pipeline completed" at 10:32:50 |
| 11:19:15 | API shutdown (deploy) | appLog: "API shutdown" at 11:19:15 |
| 11:19:32 | API restart with new working-tree code | appLog: "API started" at 11:19:32 |
| 11:21:19 | Rabbinical literature query: "האם האוסף כולל ספרות רבנית?" | Session a45a1ef3, message id 44 |
| 11:21:24 | Interpreter runs (335 output tokens), returns "No records found" | llm_calls.jsonl entry 6; no narrator_meta follows (0 records = no narration needed) |
| 11:22:30 | Amsterdam query submitted: "ספרים בשפה העברית שהודפסו באמסטרדם" | Session 8b75fcd0, message id 45 |
| 11:22:33 | Interpreter runs (128 output tokens) -- valid plan produced | llm_calls.jsonl entry 7; appLog: "WebSocket scholar pipeline completed" at 11:22:33 |
| 11:22:33 | **REGRESSION:** Fallback response returned (24,571 chars, raw list) | Session 8b75fcd0, message id 46: content starts with "Found 30 record(s) matching your query:" |
| 11:22:33 | **No narrator_meta entry logged** -- narrator streaming failed before completion | llm_calls.jsonl: entry 7 (interpreter) has no paired narrator_meta |
| 11:32:06 | API shutdown (second deploy) | appLog: "API shutdown" at 11:32:06 |
| 11:33:58 | API restart with updated working-tree code | appLog: "API started" at 11:33:58 |
| 11:35:10 | Same Amsterdam query re-submitted | Session 7ccda602, message id 47 |
| 11:35:13 | Interpreter runs (115 output tokens) -- valid plan produced | llm_calls.jsonl entry 8 |
| 11:35:27 | **RECOVERY:** Full scholarly narrative returned (4,036 chars, Hebrew) | Session 7ccda602, message id 48; narrator_meta logged at 11:35:27 (entry 9) |

---

## Evidence

### Server Logs

**LLM call log pattern** (source: `llm_calls.jsonl` via task `01KP0RF4KWGBM0ERQ2C2KMC6XD/output.json`):

The key diagnostic is the presence or absence of `narrator_meta` entries. Since `narrator_meta` is only called *after* successful narrator streaming (`_extract_streaming_meta()` in `narrator.py`), its absence signals narrator failure:

| Query | Timestamp | Interpreter | narrator_meta | Narrator status |
|-------|-----------|-------------|---------------|-----------------|
| Venice (pre-deploy) | 10:32:09 | 132 tokens | Yes (10:32:50) | SUCCESS |
| Rabbinical lit | 11:21:24 | 335 tokens | N/A (0 records) | N/A |
| **Amsterdam (broken)** | **11:22:33** | **128 tokens** | **Missing** | **FAILED** |
| Amsterdam (fixed) | 11:35:13 | 115 tokens | Yes (11:35:27) | SUCCESS |

**App log** (source: `appLog` field in task output):

```
2026-04-12 11:19:15 | INFO | app.api.main | API shutdown
2026-04-12 11:19:32 | INFO | app.api.main | API started       <-- first deploy
2026-04-12 11:22:33 | INFO | app.api.main | WebSocket scholar pipeline completed
2026-04-12 11:32:06 | INFO | app.api.main | API shutdown
2026-04-12 11:33:58 | INFO | app.api.main | API started       <-- second deploy
2026-04-12 11:35:27 | INFO | app.api.main | WebSocket scholar pipeline completed
```

**LLM logger architecture** (source: `scripts/utils/llm_logger.py` via task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, step 7b):

- `log_call()` stores: timestamp, call_type, model, session_id, prompts (system/user), usage (tokens), cost_usd
- The `response` parameter is used ONLY to extract `usage.prompt_tokens` and `usage.completion_tokens` -- response content is NEVER stored
- Previous analyst's claim of "response: {}" was a **misread**: the field is null by design, not an empty object

**Misread correction**: The interpreter returned valid plans with 128 and 115 output tokens respectively. An empty `{}` would have crashed Pydantic validation (`InterpretationPlan` requires `intents`, `reasoning`, `execution_steps`, `directives`, `confidence` as mandatory fields with no defaults -- source: `scripts/chat/plan_models.py` via task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, step 1).

### Code Analysis

**15 changes classified** (source: task `01KP0RRGPJF0KD9HXD21TV85JE/output.json`):

| ID | File | Classification | Description |
|----|------|---------------|-------------|
| C1 | `scripts/chat/executor.py` | **BREAKING** | Added `s.value_he` to subjects SELECT; `m3_schema.sql` has no `value_he` column. Test fixtures patched (commit `f38f59b`) to add it, masking production gap. |
| C2 | `scripts/chat/executor.py` | RISKY | Auto-discover agent connections with bare `except: pass` -- failures silently swallowed, no logging |
| C3-C7 | `scripts/chat/executor.py` | SAFE | Confidence columns, title variants, notes, Hebrew aliases, image_url -- all columns exist in schema, defensive access patterns |
| C8-C10 | `scripts/chat/plan_models.py` | SAFE | `RecordSummary` extended with 6 new fields (all with defaults); new `PublisherDetail` model; `GroundingData` extended |
| C11 | `scripts/chat/narrator.py` | SAFE | Prompt enrichment: confidence qualifiers, Hebrew subjects, publisher context, relationship hints -- all conditional on data presence |
| C12 | `app/api/main.py` | SAFE | WebSocket handler: stage field, truncation-aware counts, "Composing scholarly response..." message -- cosmetic only |
| C15 | `tests/scripts/chat/test_executor.py` | RISKY | Test fixtures patched to add `value_he` column to DDL -- masks production schema gap |

**Cross-file dependency** (source: task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, rootCauseEvidence):

The metadata richness feature spans three files that must be deployed in sync:
- `plan_models.py`: 6 new `RecordSummary` fields (`date_confidence`, `place_confidence`, `publisher_confidence`, `title_variants`, `notes_structured`, `subjects_he`), new `PublisherDetail` model, new `GroundingData` fields (`publishers`, `connections`)
- `executor.py`: New SQL queries populating these fields
- `narrator.py`: `build_lean_narrator_prompt()` and `_build_narrator_prompt()` access all new fields

### Execution Path Trace

**Narrator fallback flow** (source: task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, step 5):

```
narrate_streaming()
  -> _stream_llm(query, execution_result, callback, model)
     -> build_lean_narrator_prompt(query, execution_result)  <-- EXCEPTION HERE
     -> streaming_completion(model, system, user)
  EXCEPT:
     -> logger.exception("...")   <-- logged to 'scripts.chat.narrator' logger (NOT captured in appLog)
     -> _fallback_response(query, execution_result)
     -> return ScholarResponse with fallback content
```

**Fallback output confirmation**: Session `8b75fcd0` content starts with "Found 30 record(s) matching your query:" -- this exactly matches the `_fallback_response()` function output pattern in `narrator.py` (source: task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, step 5, `fallbackTrigger`).

**Pipeline flow on main branch vs dev** (source: task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, step 2): The core pipeline (`interpret() -> execute_scholar_plan() -> narrate_streaming()`) is identical on both branches. No changes to error handling or how interpret/execute/narrate results are consumed.

---

## Root Cause

**Primary cause (HIGH confidence):** The 11:19 deployment pushed an intermediate working-tree state where `narrator.py`'s `build_lean_narrator_prompt()` referenced new Pydantic model fields (e.g., `result.grounding.publishers`, `rec.title_variants`, `rec.subjects_he`, `rec.date_confidence`) that had not yet been added to `plan_models.py` or had not yet been populated by `executor.py`. This caused an `AttributeError` in the prompt builder, which was caught by `narrate_streaming()`'s except clause, triggering the fallback response.

**Supporting evidence:**
1. Dev branch adds 6 new `RecordSummary` fields, 1 new `PublisherDetail` model, and 2 new `GroundingData` fields -- ALL accessed by `build_lean_narrator_prompt()` (source: task `01KP0RRGPJF0KD9HXD21TV85JE/output.json`, changes C8-C11)
2. These changes span 3 files (`plan_models.py`, `executor.py`, `narrator.py`) that must be in sync
3. The working tree was being modified iteratively by the babysitter during the 11:00-13:30 window
4. `deploy.sh` rsyncs the working tree, NOT committed code -- it deploys whatever is on disk
5. The commits (`01c439b` through `26bc311`) are all timestamped 12:24-14:11, AFTER the queries at 11:22 and 11:35 (source: task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, confirmedFindings[4])
6. The 11:19 deploy was an intermediate state; the 11:33 deploy pushed a more complete version that resolved the mismatch

**Secondary concern (MEDIUM confidence):** C1 -- the `value_he` column missing from `m3_schema.sql` but queried in `executor.py` line 1339 could cause `sqlite3.OperationalError` on databases built from the schema. However, the production DB was verified to have this column (likely added via `ALTER TABLE` during development), so this did not trigger the incident. It remains a latent risk for fresh DB builds.

**What was NOT the cause:**
- **Empty interpreter JSON**: Ruled out. The interpreter returned 128 output tokens (valid plan). An empty `{}` would raise `ValidationError` from Pydantic, not silently degrade (source: task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, step 3).
- **Schema mismatch**: Ruled out for this incident. Production DB has `value_he`, `date_confidence`, `place_confidence`, `publisher_confidence` columns (source: task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, confirmedFindings[1]).
- **Narrator model/call_type change**: Ruled out. Narrator call_type and model selection logic is IDENTICAL on both branches (source: task `01KP0RRGPJF0KD9HXD21TV85JE/output.json`, riskAssessment).
- **Transient API error**: Unlikely. The pattern of "failure after deploy, success after redeploy" strongly suggests a code issue, not a transient external failure.

---

## What Worked vs What Broke

### What Worked

- **Interpreter**: Produced valid plans on both attempts (128 and 115 output tokens). No changes between branches. (source: `llm_calls.jsonl` entries 7-8)
- **Executor**: Found 30 records correctly. The fallback response includes all 30 records with correct MMS IDs and Primo links. (source: session `8b75fcd0`, message id 46)
- **Fallback mechanism**: `_fallback_response()` in `narrator.py` fired correctly and returned usable (if unscholarly) results. The user got data, not an error.
- **Recovery**: The second deploy at 11:33 fully restored scholarly narration. Session `7ccda602` shows a 4,036-character Hebrew scholarly narrative with historical context, curated examples, and catalog links.

### What Broke

- **Narrator streaming**: `build_lean_narrator_prompt()` raised an exception (most likely `AttributeError`) when accessing new model fields that did not exist in the intermediate deployment state.
- **Deploy safety**: `deploy.sh` deployed uncommitted working-tree code during active development, pushing an inconsistent state across the 3-file dependency chain.
- **Error visibility**: The narrator exception was caught and logged only to the `scripts.chat.narrator` logger, which is NOT captured in the production `appLog`. The `ScholarResponse` returned carries no metadata indicating it is a fallback.

---

## Recommendations

### Immediate (prevent recurrence)

1. **Deploy from committed code only**: Modify `deploy.sh` to deploy a specific git ref (tag or commit SHA) rather than the working tree. At minimum, add a `git diff --stat` check that warns or aborts if uncommitted changes exist.

2. **Add `value_he` to `m3_schema.sql`**: The schema file (`m3_schema.sql`) is missing the `value_he` column in the `subjects` table, even though the production DB has it. This masks a fresh-install failure. (source: task `01KP0RRGPJF0KD9HXD21TV85JE/output.json`, change C1)

3. **Mark fallback responses**: When `narrate_streaming()` falls back to `_fallback_response()`, add `"fallback": true` and `"error": str(exc)` to `ScholarResponse.metadata`. Send a `type: "warning"` WebSocket message to the client so the UI can indicate degraded mode. (source: task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, codeImprovementsNeeded[1])

### Short-term (improve observability)

4. **Log narrator streaming calls**: `streaming_completion()` in `scripts/models/llm_client.py` does not call `log_llm_call()`. Add logging after streaming completes, assembling a synthetic response object with token counts from the final chunk's usage field. (source: task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, codeImprovementsNeeded[0])

5. **Capture all logger output in production**: Production log capture only includes the `app.api.main` logger. The `scripts.chat.narrator` logger exception traceback was lost. Configure production logging to capture all loggers at WARNING level or above.

6. **Log exception details in auto-connections**: Change C2 (`executor.py` lines 108-121) has a bare `except: pass` for the agent connections discovery. Add `logger.debug()` at minimum. (source: task `01KP0RRGPJF0KD9HXD21TV85JE/output.json`, change C2)

### Medium-term (architectural)

7. **Deploy model-config.json**: `deploy.sh` excludes `data/` which contains `data/eval/model-config.json`. Production always uses `ModelConfig` defaults (interpreter=gpt-4.1-mini, narrator=gpt-4.1, meta_extraction=gpt-4.1-nano) rather than the configured overrides. Move the config file outside `data/` or add a specific `--include` rule. (source: task `01KP0S49JTCTDMZR4P8X8NYJVK/output.json`, codeImprovementsNeeded[2])

8. **Add integration smoke test to deploy**: After `deploy.sh` restarts the service, run a canary query and verify the response includes a scholarly narrative (not a fallback list). Abort rollout if the check fails.

---

## Logging Blind Spots

| Blind Spot | Impact | File | Remediation |
|-----------|--------|------|-------------|
| `streaming_completion()` does not call `log_llm_call()` | Narrator streaming (the primary narrative generation path) is completely invisible in `llm_calls.jsonl`. Cannot determine what model was used, what error occurred, or track token costs for narrator calls. | `scripts/models/llm_client.py` | Add `log_llm_call()` after streaming completes with assembled token usage from final chunk |
| Narrator fallback does not preserve the triggering exception | When `narrate_streaming()` catches an exception and falls back, the only trace is `logger.exception()` to the module-level logger. The returned `ScholarResponse` has no fallback indicator. | `scripts/chat/narrator.py` | Add `"fallback": true, "error": str(exc)` to `ScholarResponse.metadata`; send WebSocket warning |
| Production logs only capture `app.api.main` logger | The `scripts.chat.narrator` logger exception traceback from the failing deploy was not captured. We cannot determine the exact exception type or stack trace. | Production Docker/logging config | Configure production to capture all loggers at WARNING+ level |
| `deploy.sh` does not log deployed code state | No record exists of what code was on disk at 11:19 vs 11:33. Commits were made after the incident. | `deploy.sh` | Log `git rev-parse HEAD`, `git diff --stat`, and `git status` at deploy time |
| Auto-connections bare `except: pass` | Silent failure in `executor.py` lines 108-121; any `ImportError`, DB error, or timeout is swallowed without trace. | `scripts/chat/executor.py` | Replace bare `pass` with `logger.debug("connections failed: %s", exc)` |

---

## Remaining Uncertainties

1. **[UNCONFIRMED] Exact exception that caused narrator fallback at 11:22:33**: Most likely `AttributeError` on a missing Pydantic field, but could theoretically be a transient OpenAI API error. The Docker container logs that would contain the full traceback were not captured by the investigation.

2. **[UNCONFIRMED] Exact code state at 11:19 vs 11:33 deploys**: `deploy.sh` rsyncs the working tree, and no deploy logs exist. The git commits were created after both deploys. We infer the code state from the commit timestamps and the babysitter's modification pattern, but cannot prove it definitively.

3. **[UNCONFIRMED] Whether the `value_he` schema gap (C1) contributed**: The production DB has the column (likely added via `ALTER TABLE`), so this was not the proximate cause. However, if the column was added by one of the intermediate deploys, the ordering could matter. A fresh DB build from `m3_schema.sql` would still fail on this query.
