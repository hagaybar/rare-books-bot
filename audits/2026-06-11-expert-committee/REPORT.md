# Expert Committee Review — 2026-06-11

**Charter:** Five independent expert analyses (data integration & integrity; retrieval/results quality; LLM pipeline architecture; rare-books librarianship & UX; software architecture & operations), focused on data integration and results quality. All analysis read-only and deterministic (SQL verification, code reading, replay of stored eval plans). No paid LLM calls were made; paid eval proposals are listed at the end pending approval.

**Committee:** 5 specialist agents, ~175 tool calls, all findings evidence-backed (file:line or verified SQL/replay results).

---

## Verdict in one paragraph

The system's architecture is sound and its recent quality loop (benchmark, recall measurement, relaxation ladder) is the right machinery — but the committee found **eleven verified correctness bugs**, most of them small, that together explain nearly all of the 16 zero-result benchmark queries; a **data-integrity time bomb** in the FTS triggers; a **trust gap** where the evidence contract is satisfied internally but never shown to the librarian in MARC terms; and **operational risks** (no backups of irreplaceable user data, deploys of dirty working trees, shared rate-limit identity) that are cheap to fix and expensive to ignore.

---

## A. Verified bugs (replay/SQL-confirmed, all deterministic fixes)

| # | Bug | Found by | Impact | Effort |
|---|-----|----------|--------|--------|
| A1 | **Executor queries the literal string `'$step_0'`** when entity resolution fails (`_handle_retrieve` keeps the unresolved filter). Proximate cause of zeros q01 (Bomberg), q04 (Manuzio), q25, q51 (Plantin). | results-quality | high | small |
| A2 | **Multi-value IN substitution skips `normalize_filter_value`** — `'josephus, flavius'` (comma) can never equal the comma-stripped SQL expression; 24 records lost (q02). One-line fix. | results-quality | high | small |
| A3 | **4 interpreter plans had empty `execution_steps`** at 0.9+ confidence (q14/q27/q29/q30 — trivial queries with 20–109 matching records). `_convert_llm_plan` silently drops invalid steps (warning only) — artifact can't distinguish LLM emission from conversion drops. | results-quality + llm-pipeline | high | small |
| A4 | **`curation_engine` is dead code**: `_handle_sample`'s `"notable"` branch falls back to `"earliest"` and never calls `score_for_curation`. Every lesson-set query gets "the N oldest items" instead of the designed diversity blend. | results-quality | high | small |
| A5 | **Clarification contract contradicts itself**: prompt says "you may proceed with an assumed reading + clarification + low confidence", but the pipeline short-circuits whenever clarification is set at ≤0.7 — and *silently discards* clarifications set at >0.7. The "executor confirms zero results" instruction for out-of-scope topics is unreachable. | llm-pipeline | high | small |
| A6 | **Union scope `$step_0+$step_1` is invisible to validation/remapping**: `_validate_step_refs` and `_remap_single_ref` don't split on `+` — dropped-step remapping can leave stale indices pointing at the wrong record sets (silent wrong answers). | llm-pipeline | high | small |
| A7 | **FTS triggers are broken**: `UPDATE`/`DELETE` on titles and subjects fail database-wide (`titles_fts` declares columns its content table lacks; `subjects_fts` is contentless without `contentless_delete=1`). QA fix scripts work around it by dropping triggers — a silent-desync vector (fix_04, fix_19). Tables are effectively append-only by accident. | data-integration | high | medium |
| A8 | **Eval scoring bugs**: (a) `extract_filters` serializes RANGE filters as `None` — every query expecting a `year` filter loses overlap credit (q34: overlap 0.5 beside a 5/5 judge note); (b) intent `clarification` isn't in the interpreter vocabulary and the judge never sees the clarification field — the benchmark *cannot reward* the asking behavior the typo incidents demanded. | llm-pipeline | high | small |
| A9 | **`zero_result` metric: 6 false alarms** — aggregate-only overview plans succeed with rich facets but count as 0 records (q17/q18/q36); follow-ups run without session context (q15/q16); `hi` is correct behavior (q58). Plus q07: interpreter said `date_century`, executor aliases only `century` — silent empty aggregation. | results-quality | medium | small |
| A10 | **Streaming narrator calls are never cost-logged** and per-user token quotas miss all streaming tokens (the default UI path). 0 of 4,616 log lines are `narrator_streaming`. | llm-pipeline | medium | small |
| A11 | **`deploy.sh` rollback omits the logs mount** that normal deploys include — a rollback runs with different mount config. | architecture-ops | medium | small |

### Root-cause census of the 16 "suspicious" zero-result queries
- 4 × executor `$step_0` literal passthrough (A1)
- 4 × empty plans / silent step drops (A3)
- 1 × multi-value normalization (A2)
- 3 × vocabulary/morphology gaps (Hebrew clitics: `דתות` only exists as `ודתות`; `רבני` vs `רבנית`; "commentary" vs "Commentaries" — FTS has no stemming)
- 1 × fabricated hard year range (q44: "original editions" → invented RANGE 1618-1650 excluded the only Descartes item)
- 1 × place alias gap (q53: `קושטא` vs `constantinople`; the curated place alias map is never consulted at query time)
- 1 × wrong field (q49: manuscripts searched in physical_desc; the 73 records live in subjects)
- 1 × resolution fallback gap (q51 also: token fallback ignores the variants list, so Hebrew names can't match Latin variants)

**Notably: the relaxation ladder fired correctly in all replays — its design assumptions (multi-topic single-step plans; concepts present in the 5-entry map) simply don't match what the interpreter emits (multi-step single-topic plans; long-tail topics).**

---

## B. Data integration (expert 1 — all SQL-verified)

**Healthy:** source→DB completeness exact (2,796/2,796, 0 failed); zero referential orphans; `PRAGMA integrity_check` ok; 83.6% of subjects have Hebrew equivalents and Hebrew IS searchable; normalization confidence >0.8 for ~99% of imprints with honest nulls in the tails.

**Needs work:**
1. **FTS rebuild** (A7): recreate `subjects_fts` with `contentless_delete=1` (SQLite 3.45 supports it) and fix `titles_fts`'s phantom columns; update `m3_schema.sql` (it describes a different table than production runs).
2. **Schema drift**: `m3_contract.py` lacks `subjects.value_he` and 5 live tables (network_*, wikipedia_*) — add an automated contract-vs-PRAGMA pytest.
3. **No DB drift detection**: local DB is from Apr 5; prod copy ditto; nothing records which fix scripts have been applied where. Add a `db_meta` manifest table (source hash, schema version, applied-fixes ledger) + deploy-time comparison.
4. **Publisher authority coverage is ~13%** (270/2,130 distinct publishers) vs agent coverage 85%.
5. Stop tracking the 43MB `bibliographic.db` in git; delete the stray 0-byte `data/canonical/bibliographic.db`.

---

## C. Results quality (expert 2)

Beyond the bugs in section A:
1. **Concept map starved**: 5 concepts vs ≥9 observed real-user topics with *verified catalog vocabulary waiting* — religion/דת, manuscripts/כתבי יד, prayer/תפילה, censorship/צנזורה, prohibited books, rabbinical literature (exists verbatim in value_he!), bible/commentaries (176 records), philosophy, yiddish.
2. **Ladder needs morphology rungs** (all LLM-free): FTS prefix probes (`רבני*`=7, `commentar*`=176 — verified wins), token-OR decomposition of failed phrases, Hebrew clitic variants (ו/ה/ב/ל). 
3. **Query-time place alias resolution**: load the existing curated `place_alias_map.json` in the executor; add bare modern-Hebrew forms (קושטא, ונציה, אמשטרדם).
4. **Port the dead `subject_hints.py` mechanism** to the scholar pipeline (real catalog vocabulary on zero-result).
5. **Demote speculative interpreter constraints** ("original editions" → year range) to soft filters.

## D. Librarian trust & UX (expert 4)

1. **The evidence contract isn't visible**: `match_rationale` = "Matched via scholar pipeline retrieve step(s) [0]" (not even rendered in chat); Evidence carries DB column names, never MARC tags; `CandidateSet.sql` is a placeholder string. Map columns→MARC tags (650$a, 264$b…) and write rationale in librarian language.
2. **Narrator starved of scholarly data**: `physical_description` and notes are fetched per record then dropped by the default (lean) prompt builder. One small change closes most of the pedagogy gap with the ChatGPT comparison. Also: **the DB has no shelfmarks (no 852) and no provenance fields (zero 561)** — the bot can't cite a סימול at all; flag as MARC-export enhancement.
3. **Relaxations never reach the narrator or UI** — the trust data exists in `RecordSet.relaxations` and dies in the executor. Add an amber "broadened search" banner + narrator note.
4. **Grounding truncation is first-step-dominated** (confirmed mechanism of the art-heavy display): interleave round-robin across steps before the 30-record cap.
5. **Curation weights don't encode pedagogy**: no visual-material signal (871 records have maps/plates/ill.), no language diversity, temporal curve tuned for incunabula in a 16th–19th-c. collection. (Blocked on A4 first — the scorer isn't even called.)
6. **BiDi gaps**: `dir="auto"`/`<bdi>` missing on candidate cards/grounding records — mixed Hebrew/Latin titles scramble.
7. **No export/share**: lesson-list queries (the dominant real use) produce lists trapped in chat, capped at 10 visible. CSV/RIS export + shareable session view.
8. Confidence badge: red "Low" starts at 79%, displayed as false-precision percentage.

## E. LLM pipeline (expert 3)

1. **Interpreter prompt**: 20.7KB / ~5.2k tokens (~80% of every call's input); rules stated 3×; examples lag the newest rules; OPERATIONS stranded mid-section. Consolidation target ~3k tokens (−40% cost) — gated on an A/B eval.
2. **No temperature pinning, no retries** on any structured call — production planning and the judge are nondeterministic; one malformed output kills the turn.
3. **Model config fragmentation**: dataclass default `gpt-4.1-mini`, JSON-fallback default `gpt-4.1`, local file `gpt-4.1`, prod (no file) `gpt-4.1-mini`; cwd-relative path; re-read on every call. Single source of truth + boot-time log.
4. **Narrator prompt contradiction**: system prompt forbids follow-ups; both prompt builders still *demand* them and ship FOLLOW-UP HINT DATA; schema has nowhere to put them — pure token waste (leftover from the follow-up removal).
5. **Eval framework**: n=1 nondeterministic runs, ±1.0 heuristic without significance, gpt-4.1 judging gpt-4.1 (self-preference), narrator judge sees only 10 title/date/place lines (can't verify groundedness); runs fully sequential.
6. Typical turn cost ≈ $0.013–0.019; no plan caching on the scholar path.

## F. Operations (expert 5)

1. **No backups of `auth.db`/`sessions.db`** — irreplaceable user data on one disk; `cp` is unsafe under WAL; use `sqlite3 .backup` nightly + off-server copy + documented restore.
2. **deploy.sh ships the dirty working tree** while tagging the image with HEAD SHA (tag can lie); no test gate; rollback mount bug (A11); no image pruning; no container memory/CPU limits on a shared box; no log rotation anywhere (logs share a disk with SQLite — disk-full corrupts).
3. **No CI** (.github absent): a ~30-line workflow (ruff + unit tests + frontend build) catches most regressions in an AI-assisted solo workflow; integration tests silently skip without the DB — CI must surface skip counts.
4. **Rate limiting**: all users share one IP (proxy headers not honored); login lockout is a site-wide DoS; key limits by authenticated user_id, add `--proxy-headers`, verify nginx forwards.
5. **REST/WS chat duplication**: two hand-maintained near-identical pipelines in a 1,193-line main.py — every security change costs 2×. Extract one transport-agnostic pipeline. Then split executor.py (1,756 lines) along its natural handler boundaries.
6. Hygiene: 332MB `.a5c/` with 1,647 run artifacts tracked in git; `supervisord.conf` dead config binding 127.0.0.1; completed Apr specs/plans not archived per protocol; `uesrs_feedbacks` typo dir; shared admin login (already known — create personal accounts, rotate).

---

## Recommended roadmap

**Sprint 1 — "Make the zeros non-zero" (all deterministic, ~1 day of work):** A1, A2, A3 (+observability), A4, A9, q07 alias, concept-map +9 entries, morphology rungs, query-time place aliases. *Acceptance: deterministic replay of the 16 zero plans; expected ≥12 become non-zero.*

**Sprint 2 — "Make the evidence visible" (trust):** relaxations→UI+narrator, MARC-tag evidence mapping, physical_description/notes into the narrator prompt, grounding interleave, BiDi on cards, clarification contract reconciliation (A5), eval scoring fixes (A8) + re-baseline.

**Sprint 3 — "Don't lose the data, don't break prod" (ops):** backups + restore doc, deploy hardening (dirty guard, git archive, rollback mount, log rotation, image prune), CI workflow, X-Forwarded-For + user-keyed limits, FTS rebuild + parity gate + schema-contract test, DB manifest.

**Sprint 4 — structural:** REST/WS pipeline unification → main.py/executor.py splits, interpreter prompt consolidation (with A/B eval gate), curation pedagogy weights, export/share features, model-config single source of truth, temperature pinning + retries, plan caching.

---

## Paid-eval proposals (require approval; deterministic ones will just be done as part of fixes)

| ID | Question | Method | Est. cost |
|----|----------|--------|-----------|
| E1 | What is the benchmark's run-to-run noise band, and does temperature=0 change results? (Foundational: without it, every future comparison is unproven.) | 3× runs at current temp + 3× at temp=0, interpreter stage, gpt-4.1-mini + judge | ~$3–5 |
| E2 | Does the consolidated ~3k-token prompt match the current 5.2k one? | A/B over 59 queries, temp=0, n=3 | ~$3–5 (after consolidation work) |
| E3 | Is the narrator judge measuring groundedness? Does gpt-4.1 self-judging inflate scores? | 15-query narrator slice, dual judges + free deterministic hallucination check | ~$0.50–1 |
| E4 | Pedagogical quality vs the ChatGPT benchmark answer (rubric: per-item rationale, physical features, no fabricated IDs) | 4 curation queries × rubric judge | ~$0.50–1 |
| E5 | Empty-plan rate per intent/model (after A3 observability lands) | 1 benchmark run per candidate model | ~$0.10–0.30/model |

Free (no approval needed, will be done with the fixes): replay-based re-verification of the 16 zeros; FTS parity gate; schema-contract test; evidence-fidelity audit; re-scoring existing runs with fixed metrics; BiDi snapshot tests; REST/WS parity harness (mocked LLM).
