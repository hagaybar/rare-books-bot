# Contract Register — Seam Audit Synthesis

Date: 2026-06-12 | Branch: dev | Synthesized from three sweeps in `audits/2026-06-12-seam-audit/`:
`fallback-inventory.md` (107 fallback rows, ~200 sites), `cross-layer-seams.md` (Seam A schema refs + 48-cell field-op matrix + 13 JSON-shape seams), `derived-invariants.md` (31 invariants executed read-only against live DBs).

Issue dedup baseline: `gh issue list --state open` run 2026-06-12 — open: #54 #52 #51 #50 #49 #48 #47 #45 #41 #39 #14.

---

## 1. Executive summary

**What was audited**

| Sweep | Subjects examined | OK | Findings |
|---|---|---|---|
| Silent-fallback inventory | 107 inventory rows (5 HIGH, 23 MEDIUM, 79 LOW) across 70 files with `except` | 79 LOW mostly correct-by-design | 5 HIGH + 4 invariant-encoding MEDIUM carried into this register |
| Cross-layer seams | Seam A: ~17 DB-column seams; Seam B: 12 fields x 4 ops = 48 matrix cells; Seam C: 13 JSON-shape seams | Seam A: 0 findings; matrix: 22 supported/coerced cells; Seam C: 9 OK | 9 matrix findings (B1-B9) + 4 JSON-shape drifts (C9-C12) |
| Derived-artifact invariants | 31 invariants (alias, publisher, FTS, network, enrichment, value_he, imprints, referential) | 27 hold at 0 violations | 4 data violations (I1 n=26, P3 n=3, N1 n=2, E1 n=1) |

**Register totals**: 59 contracts (SEAM-01..SEAM-59); 33 OK, 26 FINDING. Findings dedupe to 22 distinct defects (Section 3): 21 NEW, 1 partially COVERED-BY-#51. Only 8 of 59 contracts have any existing test enforcement; 0 have a deploy gate beyond `validate_schema`.

**Top 5 risks (ranked)**

1. **Whole-file MARC parse failure proceeds with empty data** (SEAM-01, scripts/marc/parse.py:769-771) — violates an explicit CLAUDE.md hard rule; a corrupt export inside `/marc-ingest --yolo` would rebuild an empty database with only a stdout print as trace.
2. **Agent alias expansion silently disabled by a cached swallowed exception** (SEAM-02, scripts/query/db_adapter.py:52-53) — one transient DB error removes cross-script/variant matching for the process lifetime; two identical queries can return different CandidateSets, breaking the primary success criterion.
3. **Planner-emittable filter combinations that always die** (SEAM-19..24, scripts/query/db_adapter.py:236-483) — six op-matrix gaps (subject EQUALS, year IN, residual year EQUALS, list->IN promotion to four unrepaired fields, negated multi-value IN, three CONTAINS gaps) each fail exactly the way #44's `year EQUALS` did before its fix: step status=error, empty RecordSet, zero results presented honestly but wrongly.
4. **Approved corrections can silently fail to apply** (SEAM-04, scripts/metadata/feedback_loop.py:394-395) — DB error returns 0, indistinguishable from "no rows matched"; undermines the curator-approval loop the project memory treats as load-bearing.
5. **Live derived-data violations already in production DB** (SEAM-41/47/50/55) — 26 authority-linked agent_norms unreachable via aliases (fix_29 collision-ordering residue), 3 publisher variants shadowing other authorities' canonicals, 2 orphan network edges, 1 wikidata_id disagreement. None has a test, so all will silently recur on the next rebuild.

---

## 2. THE REGISTER

Format: id | seam | invariant | currently enforced by | status | finding ref.
"nothing" = no test, no deploy gate. Finding refs point to Section 3.

### A. Fallback contracts that encode a real invariant

| id | seam | invariant | currently enforced by | status | finding |
|---|---|---|---|---|---|
| SEAM-01 | scripts/marc/parse.py:769-771 -> pipeline | On MARC parse failure the run logs to data/runs/ and stops; it never writes an empty canonical JSONL | nothing | FINDING | FB-1 |
| SEAM-02 | scripts/query/db_adapter.py:52-53 -> :388-410 | Alias-resolution EXISTS branch is included whenever alias tables exist; a transient error is never cached as "tables absent" | tests/scripts/query/test_db_adapter_agent_alias.py::test_query_fallback_no_alias_tables (absent-tables path only; exception-cache path untested) | FINDING | FB-2 |
| SEAM-03 | scripts/chat/narrator.py:269-271 | Confidence is a measured value or null+reason; meta-extraction failure never yields a fabricated 0.85 | tests/scripts/chat/test_narrator.py::test_streaming_meta_schema_is_confidence_only (schema only, not failure value) | FINDING | FB-3 |
| SEAM-04 | scripts/metadata/feedback_loop.py:394-395 | An approved correction either applies or surfaces a distinct error; DB failure is never reported as "0 rows updated" | nothing | FINDING | FB-4 |
| SEAM-05 | scripts/query/concept_bridge.py:35-45 | Concept-bridge disablement (missing file or missing `concepts` key) emits a signal distinguishing intended-absent from accidental | tests/scripts/query/test_concept_bridge.py (expansion behavior only, not disable-signal) | FINDING | FB-5 |
| SEAM-06 | scripts/query/execute.py:260-297 | Evidence `source` carries real MARC provenance; corrupt source_tags degrade to labeled "unknown", never to wrong provenance | tests/scripts/query/test_execute.py::test_agent_norm_source_* (agent path, #43 fix only) | FINDING | FB-6 |
| SEAM-07 | scripts/query/llm_compiler.py:428-430 | A cached plan that fails schema validation triggers a logged recompile, not a silent one (determinism of plan->CandidateSet) | nothing | FINDING | FB-7 |
| SEAM-08 | scripts/chat/interpreter.py:907-950 | Malformed LLM plan steps are dropped with a warning and surfaced in `dropped_steps` | logged + surfaced by design (interpreter.py:915, 950) | OK | — |
| SEAM-09 | scripts/chat/executor.py:374-388 | A step handler crash becomes StepResult(status="error") with empty RecordSet, never a process crash or silent success | executor design; exercised throughout tests/scripts/chat/test_executor.py | OK | — |
| SEAM-10 | app/api/security.py:113-124 | Moderation fail-open is a deliberate, warning-logged trade-off | logged warning (by design) | OK | — |
| SEAM-11 | scripts/models/config.py:52-54 | Corrupt model config falls back to defaults with a warning (visible degradation) | warning logged | OK | — |
| SEAM-12 | app/api/feedback_routes.py:153-154 | A successful feedback action always leaves an audit-log record, or the failure is surfaced | nothing | FINDING | FB-8 |
| SEAM-13 | scripts/eval/run_eval.py:270-272 | A judge-scoring crash is recorded as an error, never as a real-looking score of 0 | nothing (warning logged but 0 recorded as data) | FINDING | FB-9 |
| SEAM-14 | app/api/auth_service.py:13-24 | JWT_SECRET unset in production fails loudly rather than auto-generating per-restart secrets | partial (stdout warning; <32-char raises) | FINDING | FB-10 |

### B. Field-op matrix (producer: interpreter prompt/coercions; consumer: db_adapter.build_where_clause)

| id | seam | invariant | currently enforced by | status | finding |
|---|---|---|---|---|---|
| SEAM-15 | m3_contract EXPECTED_SCHEMA <-> live bibliographic.db | All 18 contracted tables/columns match the live schema | tests/integration/test_schema_contract.py (3 tests) + scripts/marc/m3_contract.py validate_schema (returned 0 errors) | OK | — |
| SEAM-16 | every `row[...]` reference in scripts/query/, scripts/chat/, scripts/network/, app/api/ | Every consumed column name/position exists in the producing SELECT or schema (Seam A: 0 phantom references) | test_schema_contract.py (schema only); column-reference layer verified by audit, untested | OK | — |
| SEAM-17 | supported matrix cells (cross-layer-seams.md full matrix) | Each supported field x op compiles to correct, deterministic SQL | tests/scripts/query/test_db_adapter.py (per-field EQUALS/CONTAINS/RANGE/IN tests incl. test_physical_desc_equals_raises) | OK | — |
| SEAM-18 | year EQUALS scalar coercion (#44) | year EQUALS with a parseable scalar is coerced to RANGE start=end before execution | tests/scripts/chat/test_interpreter.py::test_year_equals_* (6 tests) | OK | — |
| SEAM-19 | subject EQUALS | Every subject op the prompt permits has an execution arm or coercion | nothing | FINDING | B1 |
| SEAM-20 | year IN | Multi-value year filters (prompt mandates IN) execute as a year-set or range union | nothing | FINDING | B2 |
| SEAM-21 | year EQUALS with `$step_N`/unparseable value | Residual year EQUALS values left by the #44 coercion do not reach the raising year branch | test_interpreter.py::test_year_equals_step_ref_left_alone / _unparseable_left_alone assert the gap exists, not that it is closed | FINDING | B3 |
| SEAM-22 | list->IN promotion (interpreter.py:606-611) vs IN arms | A list value is only promoted to IN for fields with an IN arm or repair (title/subject/physical_desc/agent_norm have neither) | nothing | FINDING | B4 |
| SEAM-23 | negated multi-value place/country/publisher IN | The multi-value repair applies regardless of `negate` (executor.py:809 skips negated filters) | tests/scripts/chat/test_executor.py::test_comma_canonical_names_match_via_normalized_in (non-negated only) | FINDING | B5 |
| SEAM-24 | language/agent_role/agent_type CONTAINS | CONTAINS, offered by the prompt for uncertain terms, has an arm or coercion for every field | nothing | FINDING | B6 |
| SEAM-25 | executor param reconstruction (executor.py:709, 854-857) | Executor's rebuilt param suffixes match db_adapter's naming for every multi-value-capable field (language: `_lang` vs "language") | nothing | FINDING | B7 |
| SEAM-26 | aggregate field alias map (executor.py:1213) | Aggregating by "country" facets `imprints.country_name`, not city/place | nothing | FINDING | B8 |
| SEAM-27 | unknown aggregate field (executor.py:1226-1230) | An unrecognized aggregate field produces an evidenced empty (relaxation/honesty note), matching retrieve's honest-empty contract | nothing | FINDING | B9 |
| SEAM-28 | negate on supported cells | negate wraps the condition in NOT(...) without changing semantics | test_db_adapter.py::test_filter_with_negate, ::test_physical_desc_negate_wraps_not | OK | — |

### C. JSON shapes across modules

| id | seam | invariant | currently enforced by | status | finding |
|---|---|---|---|---|---|
| SEAM-29 | agents.provenance_json (m3_index.py:406 -> execute.py:214-235) | Both provenance shapes (string-source and legacy dict) parse to a real MARC tag | tests/scripts/query/test_execute.py::test_agent_norm_source_from_string_provenance / _from_dict_provenance / _unknown_when_provenance_missing | OK | — |
| SEAM-30 | imprints.source_tags (m3_index.py:276 -> execute.py:256-296) | source_tags is a JSON list of tag strings; first element is the evidence source | nothing (shape verified vs live row; corrupt path is SEAM-06) | OK | — |
| SEAM-31 | authority_enrichment.person_info (enrichment_service.py:209 -> executor.py:1413-1498, build_network_tables.py:276-734) | person_info round-trips PersonInfo: all consumed keys (birth/death_year, occupations, teachers, students) are produced | nothing (verified vs live row) | OK | — |
| SEAM-32 | network_agents.occupations (build_network_tables.py:731 -> app/api/network.py:179,716,1078) | occupations is a JSON list of strings | nothing | OK | — |
| SEAM-33 | wikipedia_cache.categories (batch_wikipedia.py:96-105 -> build_network_tables.py:83-90) | categories is a JSON list of strings | nothing | OK | — |
| SEAM-34 | network_edges.evidence (build_network_tables.py:750-754 -> app/api/network.py:316,503,621) | evidence is plain text on both sides — never parsed as JSON | nothing | OK | — |
| SEAM-35 | publisher/agent_authorities.sources (publisher_authority.py:302, agent_authority.py:302) | sources is a JSON list, round-tripped by `_parse_sources` | unit tests in tests/scripts/metadata/test_publisher_authority.py / test_agent_authority.py (module-level) | OK | — |
| SEAM-36 | chat_messages.query_plan / candidate_set (session_store.py:217-220 <-> :178-179) | Stored plans/candidate-sets round-trip through pydantic — but no production writer populates them (0 of 166 rows) | nothing; UNVERIFIED against data | FINDING | C11 |
| SEAM-37 | chat_sessions.context / metadata (session_store.py:100-101, 266-270 <-> :143-144) | Free-form dict on both sides; no schema to drift | trivially OK (all 78 live rows `{}`) | OK | — |
| SEAM-38 | active_subgroups load path (session_store.py:558-577 -> models.py:68) | The defensive NULL/parse-failure branch constructs a valid ActiveSubgroup — but candidate_set is a required field, so the branch itself raises | nothing (0 rows; latent) | FINDING | C9 |
| SEAM-39 | session.active_subgroup (app/api/main.py:677,1010 <- ChatSession models.py:139-162) | `previous_record_ids` is fed by persisted subgroups — but ChatSession has no `active_subgroup` field and set/get have zero production callers: getattr always None | nothing | FINDING | C10 |
| SEAM-40 | RecordSet.filters_applied (executor.py:1060,1127 vs :1550,1672 -> run_diagnostic_suite.py:87) | filters_applied is homogeneous Filter dumps reconstructible via `Filter(**f)` — sample steps store `{"strategy","n"}`, breaking the M5 evidence audit | nothing (failure caught and mis-reported at run_diagnostic_suite.py:88-89) | FINDING | C12 |

### D. Derived-artifact invariants (all 31, executed against live DBs 2026-06-12)

| id | seam | invariant | currently enforced by | status | finding |
|---|---|---|---|---|---|
| SEAM-41 | I1: agent_aliases <- agents/agent_authorities | Every authority-linked agent_norm has an alias row (fix_29 contract) | nothing | FINDING (n=26) | D1 |
| SEAM-42 | I2: agent_aliases | No primary alias is a comma-fragment of its own authority's norms (fix_29 seeding-bug regression) | nothing (one-time fix script, no test) | OK (n=0) | — |
| SEAM-43 | I3+I4+A1: agent_aliases | Every alias references an existing authority; ASCII alias_form_lower = lower(alias_form); alias_form_lower globally unique (resolution determinism) | nothing | OK (n=0) | — |
| SEAM-44 | I5: agent_authorities | ASCII canonical_name_lower = lower(canonical_name); no duplicate canonical_name_lower | nothing (#54 tracks the adjacent agent_norm dual-claim defect) | OK (n=0) | — |
| SEAM-45 | P1: publisher_variants -> publisher_authorities | Every variant references an existing authority row | tests/integration/test_publisher_authority.py::test_no_orphaned_variants | OK (n=0) | — |
| SEAM-46 | P2: imprints -> publisher authorities | Every publisher_norm on >1 record is a canonical or variant form of some authority | nothing (test_publisher_authority.py checks named cases only) | OK (n=0) | — |
| SEAM-47 | P3: publisher_variants vs publisher_authorities | No variant_form_lower equals another authority's canonical_name_lower (unambiguous resolution) | nothing | FINDING (n=3) | D2 |
| SEAM-48 | P4/P6: publisher_variants | variant_form_lower = lower(variant_form), or when intentionally divergent (u/v orthography) resolves to a real imprints.publisher_norm | nothing | OK (n=0; trailing-apostrophe norms noted) | — |
| SEAM-49 | F1-F4: titles_fts / subjects_fts | FTS row counts and rowid sets exactly match titles/subjects (trigger sync, fix_20) | tests/integration/test_fts_integrity.py (rebuild/desync on a DB copy; not a live-DB battery) | OK (4791=4791, 6226=6226) | — |
| SEAM-50 | N1: network_edges -> network_agents | Both edge endpoints resolve to existing nodes (orphan sweep, build_network_tables.py:880-886) | nothing | FINDING (n=2) | D3 |
| SEAM-51 | N2+N3: network_agents provenance | Person nodes exist in agents.agent_norm; publisher nodes minus `pub:` prefix exist in publisher_authorities.canonical_name_lower | nothing | OK (n=0) | — |
| SEAM-52 | N4+N5: network_agents counts | connection_count = touching edges; person record_count = COUNT(DISTINCT record_id) in agents | nothing | OK (n=0) | — |
| SEAM-53 | N6: network_edges | No self-loops; confidence in [0,1] | nothing | OK (n=0) | — |
| SEAM-54 | W1: wikipedia_connections -> network_edges | Every connection with both endpoints as nodes is projected as an edge with connection_type = source_type | nothing | OK (n=0) | — |
| SEAM-55 | E1: agent_authorities <-> authority_enrichment | When both carry a wikidata_id for the same authority_uri, they agree | nothing | FINDING (n=1) | D4 |
| SEAM-56 | E2+E3+E4: network_agents derived fields | birth_year, has_wikipedia, community are each backed by enrichment rows reachable via agents.authority_uri | nothing | OK (n=0) | — |
| SEAM-57 | S1+S2+S3: subjects.value_he | Coverage >= documented floors (83.6% row / 78.4% unique, docs/current/data-quality.md:261); no U+FFFD mojibake or empty strings (fix_25) | nothing (docs only) | OK (drift 0.0) | — |
| SEAM-58 | M1+M2+M3: imprints | No normalized value without preserved raw (CLAUDE.md reversibility rule); date_start <= date_end; country_name never without country_code | nothing | OK (n=0) | — |
| SEAM-59 | R1+C1: referential integrity | record_scope_flags -> records; chat_messages -> chat_sessions | nothing (PRAGMA foreign_key_check passed) | OK (n=0) | — |

---

## 3. Findings (deduped against open issues #45 #47 #48 #49 #50 #51 #52 #54)

None of the eight listed issues describes these defects directly; one finding is partially covered by #51. Adjacencies are noted so triage can link rather than duplicate.

### Group 1 — Silent fallbacks that violate hard rules (from fallback-inventory)

| ref | defect | evidence | dedup |
|---|---|---|---|
| FB-1 | Whole-file MARC parse failure prints to stdout and proceeds with `records = []`, writing an empty canonical JSONL — violates CLAUDE.md "log to data/runs/ and stop" | scripts/marc/parse.py:769-771, :871-876 | NEW |
| FB-2 | `except Exception: _agent_alias_tables_present = False` caches a transient DB error as "tables absent" for process lifetime, silently dropping alias expansion from all AGENT_NORM filters | scripts/query/db_adapter.py:52-53, :23, :388-410 | NEW |
| FB-3 | Meta-extraction failure returns fabricated confidence 0.85 presented as measured — violates "never invent values" | scripts/chat/narrator.py:269-271 | NEW |
| FB-4 | `_renormalize_records` `except Exception: return 0` makes correction-apply failure indistinguishable from "no rows matched"; nothing logged | scripts/metadata/feedback_loop.py:394-395 | NEW |
| FB-5 | Concept bridge silently disabled by missing file or misspelled `concepts` key — recall shrinks with zero signal | scripts/query/concept_bridge.py:35-45 | NEW (transparency-adjacent to #47, different site/mechanism) |
| FB-6 | Corrupt imprints.source_tags JSON degrades publisher/place/year evidence to `marc:unknown` unlogged (agent path was fixed in #43) | scripts/query/execute.py:260-262, 278-279, 296-297 | partially COVERED-BY-#51 (evidence-quality cluster); the corrupt-JSON swallow itself is NEW |
| FB-7 | Cached-plan validation failure silently recompiles via LLM — plan and CandidateSet may differ between runs with no signal | scripts/query/llm_compiler.py:428-430 | NEW |
| FB-8 | `except Exception: pass` around `audit_log` — feedback action succeeds with silent loss of the accountability record | app/api/feedback_routes.py:153-154 | NEW |
| FB-9 | Judge-scoring crash recorded as a real score of 0, skewing eval rankings | scripts/eval/run_eval.py:270-272 | NEW |
| FB-10 | Empty JWT_SECRET auto-generates a per-restart secret with only a stdout warning — sessions invalidated on every production restart | app/api/auth_service.py:13-24 | NEW |

### Group 2 — Planner-emittable filter combinations that raise (from cross-layer Seam B; same failure class as fixed #44)

| ref | defect | evidence | dedup |
|---|---|---|---|
| B1 | subject EQUALS has no execution arm and no coercion; prompt permits EQUALS | scripts/query/db_adapter.py:342-361; scripts/chat/interpreter.py:234, :319 | NEW |
| B2 | year IN raises; prompt mandates IN for multi-value, and "1525 or 1530" lists become IN | db_adapter.py:290; executor.py:706 (YEAR not in repair set) | NEW |
| B3 | year EQUALS with `$step_N` or unparseable value bypasses the #44 coercion and raises | interpreter.py:625-630 -> db_adapter.py:290 | NEW |
| B4 | Interpreter promotes any EQUALS/CONTAINS list to IN for all fields, but title/subject/physical_desc/agent_norm have no IN arm and no repair | interpreter.py:606-611 -> db_adapter.py:336, :361, :483, :437 | NEW |
| B5 | Multi-value repair for place/country/publisher IN explicitly skips negated filters, which then raise | executor.py:809 -> db_adapter.py:236/:253/:271 | NEW |
| B6 | language/agent_role/agent_type CONTAINS raise; prompt offers CONTAINS for uncertain terms without per-field restriction | db_adapter.py:311, :451, :465 | NEW |

### Group 3 — Silent drift (no crash, wrong or narrowed results)

| ref | defect | evidence | dedup |
|---|---|---|---|
| B7 | Executor rebuilds db_adapter param names with suffix "language" where db_adapter uses `_lang`; multi-valued language via `$step_N` silently keeps only the first value | executor.py:709, 854-857 vs db_adapter.py:299 | NEW |
| B8 | Aggregate alias maps "country" -> "place": country aggregation silently returns city facets despite country being a first-class filter field | executor.py:1213 vs db_adapter.py:259-271 | NEW |
| B9 | Unknown aggregate field returns a silent empty AggregationResult with no relaxation note, unlike retrieve's honest-empty contract | executor.py:1226-1230 | NEW (same transparency family as #47; recommend linking) |

### Group 4 — Dormant/dead seams (from cross-layer Seam C)

| ref | defect | evidence | dedup |
|---|---|---|---|
| C9 | active_subgroups defensive load branch constructs `ActiveSubgroup(candidate_set=None)` but candidate_set is required — the fallback itself raises ValidationError (latent, 0 rows) | session_store.py:558-577 vs scripts/chat/models.py:68 | NEW |
| C10 | app/api reads `session.active_subgroup`, which ChatSession never defines and nothing loads; `previous_record_ids` is always `[]` — the whole subgroup-persistence layer has zero production callers | app/api/main.py:677, :1010, :679-685; executor.py:295-296 | NEW |
| C11 | chat_messages.query_plan/candidate_set round-trip code exists but no production writer populates them (0 of 166 rows) — write-never columns | session_store.py:217-220 vs app/api/main.py:716-719, :784-787, app/cli.py:315-324 | NEW |
| C12 | RecordSet.filters_applied is polymorphic (Filter dumps vs sample's `{"strategy","n"}`); diagnostic-suite `Filter(**f)` reconstruction always errors on sample steps, structurally breaking the M5 evidence audit | executor.py:1550, :1672 vs scripts/eval/run_diagnostic_suite.py:87-89; query_plan.py:45 extra='forbid' | NEW |

### Group 5 — Live data violations (from derived-invariants; counts measured 2026-06-12)

| ref | defect | evidence | dedup |
|---|---|---|---|
| D1 | 26 authority-linked agent_norms (bare mononyms: `adam`, `rené`, `מנשה`, ...) have no alias row — fix_29's collision check ran against pre-deletion state, then the colliding fragment was deleted; the forms now exist nowhere | derived-invariants.md I1; scripts/qa/fixes/fix_29_repair_agent_alias_fragments.py:84-93 | NEW (same fix_29/alias family as #54, distinct defect — #54 is dual-claimed agent_norms, this is vanished aliases) |
| D2 | 3 Hebrew publisher variant forms of authority 229 (Proops Press) shadow the canonical names of placeholder authorities 33/41/78 (unknown_marker, never retired) — same form resolves to two authorities | derived-invariants.md P3 | NEW (distinct from #50, which is substring-fallback matching in resolve_publisher) |
| D3 | 2 `same_place_period` network edges reference `מנשה בן ישראל`, whose node was merged into `manasseh ben israel`; edges were neither remapped nor swept (orphan sweep runs before later additive steps) | derived-invariants.md N1; build_network_tables.py:880-886 | NEW |
| D4 | d'Alembert: agent_authorities.wikidata_id = Q106599741 vs authority_enrichment.wikidata_id = Q153232 for the same authority_uri | derived-invariants.md E1 | NEW |

**Finding count: 22 distinct defects (21 NEW, FB-6 partially covered by #51).**
Explicitly checked and NOT duplicated here: #45 (first-name-token probe), #47 (fan-out relaxation transparency — linked from FB-5/B9), #48 (subject lexical variants), #49 (absence semantics), #50 (substring fallback), #51 (evidence cluster — absorbs part of FB-6), #52 (vague-query gate), #54 (dual-claimed authorities — linked from D1).

---

## 4. Proposed enforcement (prioritized)

### P0 — Invariant battery (live-DB SQL assertions) — effort S

A single pytest module (`tests/integration/test_derived_invariants.py`) running the 31 read-only SQL checks from derived-invariants.md against `data/index/bibliographic.db` + `data/chat/sessions.db`, parametrized one test per invariant, with the four current violations marked `xfail(strict=True)` until repaired (I1 n=26, P3 n=3, N1 n=2, E1 n=1). The SQL is already written and verified — this is transcription. **Prevents recurrence of: D1, D2, D3, D4**, and locks SEAM-42..59 (incl. the CLAUDE.md reversibility rule M1 and value_he coverage floors) permanently. Wire into the marc-ingest skill as a post-build gate (phase 7.5).

### P0 — Field-op matrix contract test — effort S

`tests/scripts/query/test_filter_op_matrix.py`: parametrize all 12 fields x 4 ops; assert each cell either (a) produces SQL, (b) is coerced upstream (feed through `_convert_filter_dict` + `_normalize_multivalue_filters` first), or (c) is documented-unreachable (deprecated `agent`). Initially the six gap cells are `xfail(strict=True)` — the test is the register's source of truth and fails the build the moment a prompt change makes a raising cell reachable. **Prevents: B1, B2, B3, B4, B5, B6** (and regression of #44). Follow-up M-sized fix: either add coercions/arms or constrain the prompt per field — the test forces the decision.

### P1 — Silent-fallback contract tests — effort M

Targeted unit tests, one per HIGH fallback, asserting the loud path:
1. `test_parse_failure_stops_pipeline` — corrupt XML -> raises / writes data/runs/ error artifact, never an empty JSONL (prevents FB-1).
2. `test_alias_table_check_does_not_cache_exceptions` — inject a failing connection; assert no module-global False is cached and a warning is logged (prevents FB-2; extends the existing test_db_adapter_agent_alias.py).
3. `test_meta_extraction_failure_returns_null_confidence` — assert None + reason, never 0.85 (prevents FB-3).
4. `test_renormalize_db_error_is_distinct_from_zero_matches` — locked-DB fixture -> raises/None + log, not 0 (prevents FB-4).
5. `test_concept_bridge_disable_is_logged` — missing file -> info log; present file with no `concepts` key -> warning (prevents FB-5).
6. `test_eval_judge_crash_not_scored_zero` (prevents FB-9); `test_audit_log_failure_surfaces` (prevents FB-8); `test_jwt_secret_required_in_prod` (prevents FB-10); cached-plan validation failure logs a warning (prevents FB-7).

### P1 — JSON-shape contract tests — effort S

`tests/scripts/chat/test_shape_contracts.py`:
- `test_active_subgroup_defensive_branch_constructs_valid_model` — NULL candidate_set row -> loader returns a constructible object or None, not ValidationError (prevents C9).
- `test_filters_applied_reconstructible_for_all_step_types` — retrieve and sample RecordSets both survive the diagnostic suite's reconstruction (prevents C12; fixes the M5 evidence audit).
- Decision tests for dormant seams: either wire `session.active_subgroup` + message plan persistence or delete the dead layer; a test asserting "zero callers" prevents half-revival (C10, C11).

### P2 — Metamorphic recall tests — effort M

Extends the existing tests/integration/test_*_recall.py pattern:
- Alias-expansion metamorphic: for each of the 26 D1 mononyms post-repair, query by alias form and by canonical form -> identical CandidateSets (guards SEAM-02 end-to-end, prevents FB-2/D1 recurrence at the result level).
- Publisher-resolution determinism: every variant_form_lower resolves to exactly one authority regardless of canonical-vs-variant lookup order (prevents D2; complements #50).
- Aggregation faceting: `aggregate(country)` keys are country_name values, not cities (prevents B8); multi-valued language filter via `$step_N` returns the union, not first-value (prevents B7); unknown aggregate field carries an honesty note (prevents B9, supports #47).

### P3 — Evidence-provenance fuzz test — effort S

Corrupt-JSON fixtures for provenance_json/source_tags asserting every degradation path is labeled "unknown" and logged (closes the FB-6 remainder; folds into the #51 evidence-quality work).

Effort legend: S = under half a day, M = 1-2 days, L = multi-day. No L items — every enforcement above reuses SQL or fixtures already produced by the sweeps.

REGISTER-COMPLETE
