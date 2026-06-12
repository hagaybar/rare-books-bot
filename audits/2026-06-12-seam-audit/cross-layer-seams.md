# Cross-Layer Seam Audit — Producer/Consumer Contract Verification

Date: 2026-06-12
Branch: dev (read-only audit; no code changes)
Databases inspected (SELECT/PRAGMA only): `data/index/bibliographic.db`, `data/chat/sessions.db`

Method: every cross-module reference (DB column, op enum, JSON shape) was checked
against the actual producer — `PRAGMA table_info` on both live DBs,
`scripts/marc/m3_contract.py`, the `raise ValueError` sites in
`scripts/query/db_adapter.py`, and one real stored row per JSON column where rows exist.
Claims that could not be verified against data are marked UNVERIFIED.

---

## Seam Class A — DB column references

Baseline: `scripts.marc.m3_contract.validate_schema(data/index/bibliographic.db)`
was executed and returned `[]` (zero errors) — the contract module
(scripts/marc/m3_contract.py:373-394 EXPECTED_SCHEMA) matches the live schema for all
18 contracted tables.

`PRAGMA table_info` was run on every table of both DBs; every `row["..."]`,
positional `row[N]`, SELECT list, and INSERT column list in the in-scope files was
checked against it.

| Seam | Producer (schema) | Consumer (reference) | Status | Evidence |
|---|---|---|---|---|
| `agents.provenance_json AS agent_provenance` | agents table (PRAGMA: `provenance_json`) | scripts/query/execute.py:222-225 reads `row["agent_provenance"]` | OK (intentional alias, #43) | Alias produced at scripts/query/db_adapter.py:549 |
| Hydration aliases `language_code/language_source/title_value/subject_value/subject_source/agent_raw/agent_norm/agent_confidence/agent_role_norm/agent_role_confidence/agent_type/agent_authority_uri` | scripts/query/db_adapter.py:493-554 `build_select_columns` | scripts/query/execute.py:265-463 (all guarded with `in row.keys()`) | OK | every alias present in the SELECT builder |
| execute.py positional rows (titles/agents/imprints/subjects/notes) | SELECT lists at scripts/query/execute.py:71-72, 93-94, 114, 140-141, 170-171 | index access at scripts/query/execute.py:82-184 | OK | column order matches index order (e.g. line 114 `mms_id,date_start,date_end,place_norm,place_raw,publisher_raw` ↔ lines 124-132) |
| `imprints` columns (`date_start/date_end/date_label/place_norm/place_display/publisher_norm/publisher_display/*_confidence/occurrence`) | PRAGMA imprints (23 cols, all present) | scripts/chat/executor.py:1786-1904 | OK | column names verified against PRAGMA |
| `subjects.value_he` | PRAGMA subjects (`value_he` present; fix_19) | scripts/chat/executor.py:1837-1838 | OK | |
| `authority_enrichment.*` + joined `aa.canonical_name/date_start/date_end` | SELECT `ae.*, aa.canonical_name, ...` at scripts/chat/executor.py:1396-1400 (LEFT JOIN agent_authorities) | `enrich_row["canonical_name"]`, `["person_info"]`, `["wikipedia_url"]`, `["wikidata_id"]`, `["viaf_id"]`, `["nli_id"]`, `["description"]`, `["image_url"]` at executor.py:1413-1498 | OK | `canonical_name` is NOT a column of authority_enrichment (PRAGMA) — it resolves only because of the JOIN; LEFT JOIN NULL is handled at executor.py:1475 (`or agent_name`). No name collision: the three aa columns are absent from ae |
| second enrichment query, alias `aa_name` | scripts/chat/executor.py:1967 `aa.canonical_name AS aa_name` | executor.py:1980 `enrich_row["aa_name"]` | OK | |
| `publisher_authorities` lookup (`canonical_name,type,dates_active,date_start,date_end,location,wikidata_id,cerl_id`) | PRAGMA publisher_authorities (all present) | scripts/chat/executor.py:2064-2088 | OK | |
| `publisher_variants.variant_form_lower`, alias `auth_id` (`pa.id AS auth_id`) | executor.py:615-617 SELECT | executor.py:621-627 | OK | |
| `agent_aliases.alias_form/alias_form_lower/script` | PRAGMA agent_aliases | executor.py:502-509, 1421-1430, 1477-1487 | OK | |
| `wikipedia_cache.summary_extract/wikidata_id/language` | PRAGMA wikipedia_cache | executor.py:1505-1516 | OK | |
| session_store positional rows | SELECT lists at scripts/chat/session_store.py:124 (6 cols), 162-168 (6 cols), 344-350 (4 cols), 413 (1 col), 545-548 (6 cols), 625-629 (3 cols) | index access at session_store.py:139-144, 176-181, 360-367, 422, 558-576, 637-639 | OK | every index maps to the matching SELECT position; all columns exist in sessions.db PRAGMA (chat_sessions: session_id,user_id,created_at,updated_at,context,metadata,expired_at,phase; chat_messages: id,session_id,role,content,query_plan,candidate_set,timestamp; active_subgroups: id,session_id,defining_query,filter_summary,record_ids,candidate_count,candidate_set,created_at; user_goals: id,session_id,goal_type,description,elicited_at) |
| `network_edges` 7-column shape | created by scripts/network/build_network_tables.py:199-210 (matches live PRAGMA exactly) | INSERTs at build_network_tables.py:216-221, 281-286, 298-303, 422-428, 507; API reads at app/api/network.py:300-316, 489-503, 608-621 | OK | |
| `wikipedia_connections.source_type` → `network_edges.connection_type` | PRAGMA wikipedia_connections (`source_type` present) | build_network_tables.py:219 maps `source_type` into the `connection_type` column | OK (intentional re-labeling: wikilink/llm_extraction/category) | |
| `network_agents` 14 columns incl. `node_type`, `community` | created at build_network_tables.py:656-671; `node_type` backfill ALTER at :546-549 | INSERTs at :565-573 (13 explicit cols; `community` defaulted NULL, set later by :114-116), :770; reads at app/api/network.py:179, 716, 1076-1078 | OK | |
| `imprints.place_norm` | PRAGMA imprints | scripts/network/generate_place_geocodes.py:502-507 | OK | |

**Seam A result: no reference to a non-existent or differently-named column was found.**
The only "phantom" column names (`agent_provenance`, `language_code`, `title_value`,
`subject_value`, `agent_role_norm`, `aa_name`, `auth_id`, `decade`, `cnt`, `value`,
`count`, `subjects_concat`, `record_id`, `d`) are all SQL aliases produced in the same
query that consumes them (verified at each site listed above).

---

## Seam Class B — FilterField × FilterOp support matrix

Producer side (what can be emitted):
- Interpreter prompt declares all 4 ops for 11 fields (scripts/chat/interpreter.py:108-110)
  and explicitly mandates `op IN` for multi-value place filters (interpreter.py:224-227).
  `agent` (deprecated) is NOT in the prompt's field list (interpreter.py:108) — never emitted.
- Conversion coercions in `_convert_filter_dict` (interpreter.py:574-648):
  - IN + single string → wrapped in list (interpreter.py:596-602), `$step_N` kept as string
  - EQUALS/CONTAINS + list value → promoted to IN (interpreter.py:606-611) — **any field**
  - year EQUALS + parseable scalar → RANGE start=end (#44 fix, interpreter.py:620-637);
    `$step_N` refs and unparseable values left as EQUALS (interpreter.py:625, 629-630)
- Executor repair `_normalize_multivalue_filters` (scripts/chat/executor.py:791-836):
  IN-lists and comma-joined EQUALS are repaired **only** for
  `{IMPRINT_PLACE, COUNTRY, PUBLISHER}` (executor.py:706) and **only when not negated**
  (executor.py:809 `and not f.negate`).
- Pydantic Filter validator (scripts/schemas/query_plan.py:56-91): RANGE requires
  start+end; EQUALS/CONTAINS require str value; IN requires list (or `$step_N` string).

Consumer side: `build_where_clause` raise sites (scripts/query/db_adapter.py) —
publisher :236, imprint_place :253, country :271, year :290, language :311,
title :336, subject :361, agent :374, agent_norm :437, agent_role :451,
agent_type :465, physical_desc :483.

A RAISES cell does not crash the pipeline: `_execute_step` catches all exceptions and
returns a step with `status="error"` and an empty RecordSet
(scripts/chat/executor.py:379-389).

### Full matrix

| field \ op | EQUALS | CONTAINS | RANGE | IN |
|---|---|---|---|---|
| publisher | supported (db_adapter.py:227-230) | supported (:231-234) | **RAISES** (:236) | **coerced** → EQUALS + multi-value SQL IN (executor.py:806-830, 850-878); **RAISES if negated** (repair skipped, executor.py:809 → db_adapter.py:236) |
| imprint_place | supported (:244-247) | supported (:248-252) | **RAISES** (:253) | **coerced** (same path); **RAISES if negated** (:253) |
| country | supported (:261-265) | supported (:266-270) | **RAISES** (:271) | **coerced** (same path); **RAISES if negated** (:271) |
| year | **coerced** → RANGE start=end (#44, interpreter.py:620-637); **RAISES** when value is `$step_N` or unparseable (interpreter.py:625-630 leaves EQUALS → db_adapter.py:290) | **RAISES** (:290) | supported, overlap semantics (:279-289) | **RAISES** (:290) — no coercion exists for a year list |
| language | supported (:298-301) | **RAISES** (:311) | **RAISES** (:311) | supported (:302-309) |
| title | supported (:318-322) | supported, FTS5 (:323-334) | **RAISES** (:336) | **RAISES** (:336) — list values are promoted to IN by interpreter.py:606-611 and title is not repaired (executor.py:706) |
| subject | **RAISES** (:361) — only CONTAINS has a branch | supported, FTS5 (:343-359) | **RAISES** (:361) | **RAISES** (:361) — same promotion gap as title |
| physical_desc | **RAISES** (:483) | supported (:474-481) | **RAISES** (:483) | **RAISES** (:483) |
| agent (deprecated) | **RAISES** (:374) | supported (:369-372) | **RAISES** (:374) | **RAISES** (:374) — never-emitted: absent from prompt field list (interpreter.py:108) |
| agent_norm | supported + alias EXISTS branch (:392-412) | supported (:414-435) | **RAISES** (:437) | **RAISES** (:437) — not in `_MULTIVALUE_FIELDS` (executor.py:706); multi-value agent_norm survives only via the `$step_N`-resolution path (executor.py:1012-1019 → multi_value_map) |
| agent_role | supported (:446-449) | **RAISES** (:451) | **RAISES** (:451) | **RAISES** (:451) |
| agent_type | supported (:457-463) | **RAISES** (:465) | **RAISES** (:465) | **RAISES** (:465) |

`negate` interaction: for every *supported* cell, negate wraps the condition in
`NOT (...)` and is safe (e.g. db_adapter.py:238-240, 293-295). The only negate-specific
gap is the skipped multi-value repair noted above.

### Seam B findings

| # | Seam | Producer | Consumer | Status | Evidence |
|---|---|---|---|---|---|
| B1 | subject EQUALS | prompt lists EQUALS as a general op (interpreter.py:234) and only *prefers* CONTAINS (interpreter.py:319); no coercion exists | build_where_clause subject branch has no EQUALS arm | **RAISES** | db_adapter.py:342-361 — same failure class #44 fixed for year |
| B2 | year IN | prompt mandates `op IN` for multi-value filters (interpreter.py:224-227); "1525 or 1530"-style lists become IN via interpreter.py:606-611 | year branch supports only RANGE | **RAISES** | db_adapter.py:290; `_normalize_multivalue_filters` does not cover YEAR (executor.py:706) |
| B3 | year EQUALS with `$step_N` / unparseable value | #44 coercion deliberately skips step refs and non-ints (interpreter.py:625-630) | year branch | **RAISES** | db_adapter.py:290 — residual hole left by #44 |
| B4 | title/subject/physical_desc/agent_norm IN | interpreter promotes any EQUALS/CONTAINS list to IN regardless of field (interpreter.py:606-611) | no IN arm for these fields; repair limited to place/country/publisher (executor.py:706) | **RAISES** | db_adapter.py:336, :361, :483, :437 |
| B5 | negated imprint_place/country/publisher IN | prompt multi-value rule + negate flag | repair explicitly skips negated filters | **RAISES** | executor.py:809 `and not f.negate` → db_adapter.py:236/:253/:271 |
| B6 | language CONTAINS; agent_role/agent_type CONTAINS | prompt presents CONTAINS for "uncertain terms" (interpreter.py:235) without per-field restriction | EQUALS/IN only (language), EQUALS only (agent_role/agent_type) | **RAISES** | db_adapter.py:311, :451, :465 |
| B7 | multi-value SQL param-name reconstruction | executor rebuilds db_adapter's internal param naming `filter_{idx}_{suffix}` with `_PARAM_SUFFIX` covering only imprint_place→"place" (executor.py:709, 854-856) | db_adapter names the language param `filter_{idx}_lang` (db_adapter.py:299), not `filter_{idx}_language` | DRIFT (low) | a multi-valued language filter arriving via the `$step_N` path would silently keep only the first value (`if param_key in sql_params` guard, executor.py:857) — no crash, silent narrowing. All other suffixes match (publisher :228, country :263, title :321, subject :347, agent_norm :393, agent_role :447, agent_type :459) |
| B8 | aggregate field "country" | prompt offers aggregate fields incl. place-like names (interpreter.py:117-118) | alias map sends `"country" → "place"` (executor.py:1213) | DRIFT (low) | country aggregation silently returns city facets, not `imprints.country_name` facets, although country is a first-class filter field (db_adapter.py:259-271) |
| B9 | aggregate unknown field | LLM free-form `field` | unknown fields return a silent empty AggregationResult | OK-by-design but unevidenced | executor.py:1226-1230 — no relaxation note recorded, unlike retrieve's honest-empty contract |

---

## Seam Class C — JSON shapes across modules

Each row verified against one real stored row via sqlite3 where rows exist.

| Seam | Producer | Consumer | Status | Evidence |
|---|---|---|---|---|
| `agents.provenance_json` | scripts/marc/m3_index.py:406 `[{"source": src}]`, dumped at :453 | scripts/query/execute.py:214-235 — accepts both string-`source` and legacy dict shape (#43) | OK | real row: `[{"source": "100[0]$a"}]` — matches the primary branch (execute.py:226-228) |
| `imprints.source_tags` | m3_index.py:276 `json.dumps(imprint.get('source_tags', []))` | execute.py:256-261, 274-279, 292-296 `json.loads(...)[0]` with except | OK | real row: `["264"]` |
| `authority_enrichment.person_info` | scripts/enrichment/enrichment_service.py:209 `json.dumps(PersonInfo.model_dump())` (model from scripts/enrichment/models.py) | (1) executor.py:1413-1419 + 1492-1495 reads `birth_year/death_year/occupations`; (2) build_network_tables.py:726-734 reads same keys; (3) build_network_tables.py:276, 293 reads `teachers`/`students` lists; (4) enrichment_service.py:178 round-trips `PersonInfo(**json.loads(...))` | OK | real row contains exactly `birth_year, death_year, birth_place, death_place, nationality, occupations, description, teachers, students, notable_works, languages_spoken, hebrew_label` — all consumed keys present |
| `network_agents.occupations` | build_network_tables.py:731-732 `json.dumps(list)`; publisher nodes hardcode `'["printing house"]'` (:571) | app/api/network.py:179, 716, 1078 `json.loads` with try/except | OK | real row: `["art collector", "bibliophile"]` |
| `wikipedia_cache.categories` | scripts/enrichment/batch_wikipedia.py:96-105 `json.dumps(links.categories)` (column/value alignment verified) | build_network_tables.py:83-90 `json.loads` → list of str | OK | real row: `["1654 births", "1725 deaths", ...]` |
| `network_edges.evidence` | plain text strings, NOT JSON (build_network_tables.py:750-754; wikipedia_connections passthrough :219-221) | app/api/network.py:316, 503, 621, 702 reads as plain string, never parses | OK | real row: `LLM-extracted from Wikipedia summary: ...` — both sides agree it is text |
| `publisher_authorities.sources` / `agent_authorities.sources` | scripts/metadata/publisher_authority.py:302, agent_authority.py:302 `json.dumps(list)` | same modules `_parse_sources(row["sources"])` (:190 in each) | OK | real rows: `[]`, `["https://en.wikipedia.org/wiki/House_of_Elzevir"]` |
| `chat_messages.query_plan` / `candidate_set` | session_store.py:217-220 `json.dumps(model_dump())` of QueryPlan / CandidateSet (scripts/schemas/candidate_set.py:63-75) | session_store.py:178-179 `json.loads` → pydantic-coerced into Message fields (scripts/chat/models.py:127-128) | OK in code / **DORMANT in data** | sqlite3: 166 chat_messages rows, **0** with query_plan, **0** with candidate_set — every production writer stores content only (app/api/main.py:716-719, 784-787, app/cli.py:315-324). Shape-vs-data verification impossible: UNVERIFIED against data (no rows exist); the columns are currently write-never |
| `chat_sessions.context` / `metadata` | session_store.py:100-101 (create), :266-270 (update_context merge, called from app/api/main.py:594) | session_store.py:143-144 `json.loads` → free-form dicts | OK (trivially) | all 78 live rows store `{}`/`{}`; non-empty shape UNVERIFIED against data (none stored). Free-form dict on both sides — no schema to drift |
| `active_subgroups.candidate_set` / `record_ids` | session_store.py:491-520 `json.dumps(subgroup.candidate_set.model_dump())`, guarded `if subgroup.candidate_set` (:495) | session_store.py:558-577: `record_ids` json.loads OK; `CandidateSet(**json.loads(row[4]))` in try/except, **then constructs `ActiveSubgroup(candidate_set=None, ...)` on NULL/parse failure** | **DRIFT (latent)** | `ActiveSubgroup.candidate_set` is a *required* field (scripts/chat/models.py:68 `candidate_set: CandidateSet`, no Optional/default) — the consumer's defensive NULL path at session_store.py:560-573 would itself raise pydantic ValidationError. Table currently has 0 rows (sqlite3 count), so unexercised |
| `session.active_subgroup` attribute | nothing — ChatSession (scripts/chat/models.py:139-162) has no `active_subgroup` field, `get_session` never loads the active_subgroups table, and `set_active_subgroup`/`get_active_subgroup` have **zero callers** outside session_store (rg over scripts/ + app/) | app/api/main.py:677 and :1010 `getattr(session, "active_subgroup", None)` → feeds `SessionContext.previous_record_ids` (app/api/main.py:679-685) | **DRIFT (dormant feature)** | the getattr always returns None, so `previous_record_ids` is always `[]`; the executor's `previous_results` scope (executor.py:295-296) can therefore never receive persisted subgroup IDs. The persistence layer (table + 2 methods) is connected to nothing |
| `RecordSet.filters_applied` | retrieve: Filter dumps (executor.py:1060, 1127); **sample: `[{"strategy": ..., "n": ...}]`** (executor.py:1550, 1672) | (1) app/api/main.py:97-116 — retrieve steps only, `.get()` access: safe; (2) scripts/eval/run_diagnostic_suite.py:87 `Filter(**f)` over *every* RecordSet step incl. sample (:156) | **DRIFT (low, eval-only)** | a sample step's `{"strategy","n"}` dict fails `Filter(**f)` (extra='forbid', scripts/schemas/query_plan.py:45) — caught at run_diagnostic_suite.py:88-89 and reported as `"filter reconstruction failed"`, so the M5 evidence audit is structurally broken for sample steps rather than crashing |

---

## Findings summary

| # | Class | Finding | Status |
|---|---|---|---|
| 1 | B | subject EQUALS raises with no coercion (prompt permits EQUALS) | RAISES |
| 2 | B | year IN raises with no coercion (prompt mandates IN for multi-value) | RAISES |
| 3 | B | year EQUALS with `$step_N`/unparseable value bypasses #44 coercion and raises | RAISES |
| 4 | B | interpreter list→IN promotion (any field) feeds IN to title/subject/physical_desc/agent_norm, all of which raise | RAISES |
| 5 | B | negated place/country/publisher IN skips the multi-value repair and raises | RAISES |
| 6 | B | language/agent_role/agent_type CONTAINS raise (prompt offers CONTAINS for uncertain terms) | RAISES |
| 7 | B | executor's multi-value param reconstruction uses suffix "language" where db_adapter names the param "_lang" — silent first-value narrowing on the step-ref path | DRIFT |
| 8 | B | aggregate alias maps "country" → "place": country aggregation silently returns city facets | DRIFT |
| 9 | C | ActiveSubgroup.candidate_set is required but the load path constructs it with None on NULL/bad rows → ValidationError in the defensive branch (latent, 0 rows) | DRIFT |
| 10 | C | app/api reads `session.active_subgroup` which ChatSession never defines and nothing loads; persisted subgroups (table + set/get methods) have zero production callers → previous_record_ids always empty | DRIFT |
| 11 | C | chat_messages.query_plan/candidate_set round-trip code exists but no production writer populates them (0 of 166 rows) — write-never columns | DRIFT (dormant) |
| 12 | C | RecordSet.filters_applied is polymorphic (Filter dumps vs sample's strategy dict); diagnostic-suite evidence audit reconstructs `Filter(**f)` and always errors on sample steps | DRIFT |

Seam A: **0 findings** — all column references in scripts/query/execute.py,
scripts/query/db_adapter.py, scripts/chat/executor.py, scripts/chat/session_store.py,
and scripts/network/ resolve against the live schemas; `validate_schema` returned 0
errors; the `agent_provenance` alias (db_adapter.py:549) is the intentional #43 fix.

All RAISES findings degrade to a step-level `status="error"` with an empty RecordSet
(executor.py:379-389) rather than a process crash — but each is a planner-emittable
combination that dies exactly the way issue #44's `year EQUALS` did before its fix.

SWEEP-COMPLETE
