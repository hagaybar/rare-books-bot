# Gold-Standard Diagnostic Suite — Phase 2 Report

**Run**: `data/runs/diagnostic_suite_20260612/` · 2026-06-12 · interpreter model `gpt-4.1` · 36 queries (18 he / 18 en) · ~$0.22 LLM cost
**Suite**: `data/eval/gold_standard_diagnostic_suite.json` v1.1
**Harness**: `scripts/eval/run_diagnostic_suite.py` (interpret → chat executor → deterministic M5 evidence audit), triage by `scripts/eval/diagnose_suite_run.py` (`_triage.json`)

## Adjudicated scoreboard

Raw triage: 1 PASS / 2 CLARIFIED / 33 DEVIATION. After root-cause tracing, the 33 deviations collapse into **8 real defect clusters**, **2 gold-suite calibration errors** (system was right), and **1 cosmetic cluster** affecting nearly every test.

| Adjudication | Tests |
|---|---|
| Correct behavior (intent + count), only evidence cosmetics | AUTH-01, AUTH-02, AUTH-03, AUTH-05, PLACE-01, PLACE-02, PLACE-04, DATE-01, DATE-02, DATE-03, SUBJ-01, SUBJ-02, SUBJ-04, LANG-01, LANG-02, NEG-01, PHYS-01, FTS-01, PUB-03 |
| Correct clarification | AMBIG-01, AMBIG-03 |
| System right, gold wrong | PUB-02 (26 is the true Proops count), STRESS-02 (2 real Romm/Vilna records exist) |
| Real failure | DATE-04, NORM-02 (D2) · AUTH-04 (D3) · STRESS-01 + PUB-01 partial (D4) · SUBJ-03 (D5) · SUBJ-05 (D6) · PLACE-03 (D7) · AUTH-06 (D8-adjacent, see below) |
| Systemic (all tests) | D1 agent evidence provenance, D9 evidence cosmetics |
| Policy question | AMBIG-02 (sampled "notable" instead of clarifying) |

### Notable wins (the hard stuff worked)

- **Cross-script agent recall is solved by `resolve_agent`**: both "Maimonides" (en) and "משה בן מימון" (he) returned all **20/20 distinct records** spanning both stored name forms — the headline trap of the suite did not fire.
- **Gematria conversion worked**: תקס"ה → 1805 (then died on D2, see below — the failure is downstream of a correct conversion).
- פיורדא → `furth` (9/9 exact) · Ge'ez → `gez` (58/58 exact) · "בסביבות 1650" → RANGE 1645-1655 · Hebrew ordinal century → RANGE 1500-1599 (74≈73) · fused negation שלא preserved (`negate:true`, 702 records) · gershayim in תנ"ך survived FTS sanitization without crash or noise.
- **Latin→Hebrew publisher bridge worked for Proops**: authority token match resolved 18 Hebrew forms; the 26 records returned are the true full set (gold's max of 9 was an undercount from sampling).
- Executor-level relaxation honesty works where it applies: AUTH-04's fallback probes were all faithfully recorded in `relaxations[]`.

---

## Diagnostic reports (real defects)

### D1 — Agent evidence provenance is never extracted (`marc:unknown` 100%)
- **test_id**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, NORM-01, FTS-02 — every agent evidence object in the run
- **failure_stage**: M5 Evidence Extraction (`scripts/query/execute.py:346-428`)
- **symptom**: every `agent_norm` / `role_norm` / `agent_type` evidence carries `source: "db.agents.agent_norm (marc:unknown)"` despite correct matches. This is verbatim the suite's canonical failure trap.
- **root_cause_hypothesis**: **confirmed, double contract drift.** (1) The extractor reads `row["agent_provenance"]`, but the M3 `agents` table names the column `provenance_json` (`PRAGMA table_info(agents)` col 15) — the guard `"agent_provenance" in row.keys()` is always false. (2) Even after fixing the name, the extractor expects `provenance[0]["source"]` to be a dict with `tag`/`occurrence`; the stored shape is `[{"source": "100[0]$a"}]` — a string. Both layers drifted independently; the exception swallowing (`except ... : marc_source = "unknown"`) made it silent.
- **action_required**: align `db_adapter` SELECT (alias `provenance_json AS agent_provenance` or rename in extractor) **and** parse the string shape (`"100[0]$a"` already encodes tag+occurrence+subfield). Add a regression test: agent evidence must never be `marc:unknown` when `provenance_json` is non-null.

### D2 — `year EQUALS` is emitted by the interpreter but crashes the executor
- **test_id**: DATE-04 (he, gematria), NORM-02 (he) — 2 of 36 queries; 6 error lines in run log
- **failure_stage**: M3 Interpretation → M4 Execution contract (`scripts/chat/interpreter.py` filter conversion vs `scripts/query/db_adapter.py:290`)
- **symptom**: interpreter emits `{"field":"year","op":"EQUALS","value":"1805"}`; `build_where_clause` raises `ValueError: Unsupported operation FilterOp.EQUALS for year`; the step errors and the user receives 0 records. In DATE-04 the gematria→1805 conversion was *correct* — a right answer destroyed by an IR contract gap.
- **root_cause_hypothesis**: the interpreter's prompt/schema permits `EQUALS` on `year`, but the SQL adapter only implements `RANGE` (and the LLM examples never show a single-year query). Nothing repairs or rejects the plan before execution.
- **action_required**: coerce `year EQUALS v` → `RANGE(start=v, end=v)` in `_convert_filter_dict` (cheapest, one site), or support EQUALS in `db_adapter`. Surface step errors to the user as errors, not as an empty result.

### D3 — Unresolved-agent fallback over-broadens by first-name token (234 records)
- **test_id**: AUTH-04 ("Books by Jacob ibn Habib")
- **failure_stage**: M4 Execution — `_unresolved_ref_fallback` / `_fallback_tokens` (`scripts/chat/executor.py`)
- **symptom**: `resolve_agent` correctly found no match for the transliteration (the Hebrew rows 'חביב, יעקב אבן-' have no authority bridge). The fallback then probed `agent_norm CONTAINS 'Jacob'` and returned **234 records** — every Jacob in the collection — as the answer. Relaxations were honestly recorded, but the result is wrong-by-construction (expected: ≤3 or an honest empty set).
- **root_cause_hypothesis**: the token fallback treats all name tokens equally; a given name is maximally non-selective. No selectivity cap rejects a probe that matches ~8% of the collection.
- **action_required**: in the fallback, (a) prefer the rarest token, (b) reject probes whose hit-count exceeds a selectivity ceiling (e.g. >2% of collection), (c) when all probes are non-selective, return the honest empty set with the resolution failure stated. Note the probe on 'חביב' (6) and 'Habib' (2) found the right records — ranking by selectivity would have succeeded.

### D4 — Hebrew publisher variants unlinked: the 16th-century Bragadin records are unreachable (fix_26 class, live)
- **test_id**: STRESS-01 (0 records returned; ≥3 exist), PUB-01 (15 returned; ~23 exist)
- **failure_stage**: M2 Normalization / publisher authority linking (data layer), surfaced through `resolve_publisher`
- **symptom**: "Hebrew books printed in Venice by Bragadin 1550-1600" → 0. Ground truth: imprints dated **1553, 1554, 1574** with `publisher_raw` 'נדפס במצות האדון מסיר אלוויז בראגאדין' etc. exist, but their `publisher_norm` is the identity Hebrew string, not `bragadin press, venice`. The canonical norm covers only the later (1663-1792) records. `resolve_publisher` token-matched 5 forms — none of the pure-Hebrew בראגאדין forms.
- **root_cause_hypothesis**: confirmed data gap — the documented fix_26 pattern (1,851 unmapped Hebrew singleton norms) includes the most historically important records of this press. The resolver's token matching is Latin-biased; Hebrew בראגאדין shares no token with 'bragadin'.
- **action_required**: add the Hebrew Bragadin forms to `publisher_variants` (≥7 raws found by `publisher_raw LIKE '%בראגאדין%'`); audit the unmapped-singleton list against the publisher authority table for other famous presses; consider script-aware (transliteration) token matching in `_handle_resolve_publisher`.

### D5 — Interpreter-level concept fan-out bypasses relaxation transparency
- **test_id**: SUBJ-03 ("Books about cartography" → 158 records)
- **failure_stage**: M3 Interpretation (broadening) + grounding contract
- **symptom**: the interpreter itself emitted 5 probes (subject `cartography`, `geography`, `description and travel`, physical_desc `map`, title `atlas`) plus a diverse sample. Every `relaxations[]` list is **empty** — the broadening evidence mechanism never fired because the broadening happened a layer above it. 158 records are presented with nothing recording that 'cartography' was expanded.
- **root_cause_hypothesis**: `RecordSet.relaxations` only documents *executor*-initiated broadening. When the LLM does semantically identical expansion at plan time, the honesty contract has no carrier. This is the silent-broadening trap relocated, not solved.
- **action_required**: define a plan-level expansion record (e.g. interpreter must declare `expanded_from: "cartography"` per probe, or a directive the narrator must surface). The grounding/narrator layer should state "no direct subject 'cartography'; showing geography/atlas/maps matches."

### D6 — Subject lexical-variant miss: 'limited edition' vs 'Limited editions' → 0/103
- **test_id**: SUBJ-05 ("Show me the limited editions")
- **failure_stage**: M3 Interpretation (singularized the term) + M4 FTS matching (no stemming)
- **symptom**: interpreter emitted `subject CONTAINS "limited edition"` (singular); `subjects_fts` (default tokenizer, no stemming) finds 0; title probe also 0; relaxation ladder had no concept_bridge entry; honest-but-wrong empty set while the single largest subject in the DB (103 records) sits one plural-s away.
- **root_cause_hypothesis**: FTS5 unit tokenizer treats 'edition'≠'editions'; nothing in the ladder tries morphological variants.
- **action_required**: either rebuild FTS with `porter` tokenizer for the Latin field, or add a plural/singular variant probe to the relaxation ladder before declaring empty (cheap: re-probe with `s`-toggled tokens). Add 'limited edition(s)' to concept_bridge as a stopgap.

### D7 — Absence semantics: "no place of publication" compiles to `imprint_place EQUALS ""`
- **test_id**: PLACE-03 (ספרים ללא ציון מקום הוצאה → 0; truth: 41 `[sine loco]` records)
- **failure_stage**: M3 Interpretation + Filter schema validation
- **symptom**: interpreter emitted an **empty-string** place filter; it validated (the schema rejects missing `value` but not `""`), executed, matched nothing, and returned a silent 0.
- **root_cause_hypothesis**: the interpreter doesn't know absence is reified as the sentinel `[sine loco]`; the schema's EQUALS validation accepts empty strings, hiding the planning failure as an ordinary empty result.
- **action_required**: (a) reject empty-string filter values in `Filter` validation (turns silent 0 into a loud plan error); (b) teach the interpreter prompt the `[sine loco]` / ח"מ sentinel mapping.

### D8 — Resolver substring noise: 'rom'/'ram' variants match inside unrelated words
- **test_id**: STRESS-02 (masked), latent elsewhere
- **failure_stage**: M4 `resolve_publisher` substring fallback
- **symptom**: resolving דפוס ראם with variants `Rom/Romm/Ram` substring-matched 15 publisher forms including 'broderna lagerst**rom**s forlag', 'imprimerie de jé**rôme** perret', 'evreilor din **rom**ănia'. The Vilna place filter happened to mask the noise (final result: the 2 correct Romm records — the system actually answered this query *correctly*, and the gold suite was wrong to expect 0).
- **root_cause_hypothesis**: substring matching without word-boundary anchoring or minimum-token-length guard for short Latin variants.
- **action_required**: token/word-boundary anchored matching in the substring fallback; minimum variant length (≥4 chars) for Latin; keep the Hebrew path (it found האלמנה והאחים ראם correctly).

### D9 — Evidence cosmetics: subfield precision, JSON-list leakage, missing extractor branches
- **test_id**: pervasive (every executed test)
- **failure_stage**: M5 Evidence Extraction
- **symptom**: (a) imprint sources cite bare tags (`marc:260`, sometimes `marc:264`) with no subfield ($a/$b/$c) and default to 260 regardless of actual field; (b) language evidence source is `marc:["041$a"]` — a Python/JSON list serialized into the string; (c) `country` and `physical_desc` filters have **no extractor branch** and fall through to the bare `{value:"unknown", source:"unknown"}` fallback (seen in PLACE-04, PHYS-01, SUBJ-03); (d) `subjects_fts` matches produced evidence objects with `value=null` and no `extraction_error` (SUBJ-01: 2, SUBJ-03: 3) — the contentless-index Silent Null, confirmed.
- **action_required**: extend `extract_evidence_for_filter` with country/physical_desc branches; join subfield info from provenance; normalize the language source string; re-read FTS match values from base tables by rowid so `value` is never null on a real match.

### Policy observation (not a bug): AMBIG-02
"What are the most interesting items?" executed `sample(strategy="notable", n=15)` while the two sibling vague queries (AMBIG-01/03) correctly clarified. Sampling is a sanctioned action and arguably good UX, but the clarification policy fires inconsistently across equivalent vagueness. Worth a deliberate product decision, not a patch.

---

## Gold-suite corrections (for v1.2)

| Test | Correction |
|---|---|
| STRESS-02 | 2 Romm/Vilna records DO exist; expected_count → exact 2; reframe trap to resolver substring noise (D8) |
| PUB-02 | True Proops/Amsterdam count is 26, not ≤9; the Latin→Hebrew bridge is a PASS; keep the 0.95-identity-alias confidence audit |
| AUTH-01/02 | "ideal 22" counted agent rows; distinct records = 20; system achieved 20/20 |
| SUBJ-01 | 31 (subject value_he + title probe) is acceptable; exact 30 → min 30 |
| STRESS-01 | expectation stands, but root cause reassigned from executor to D4 data gap; true reachable count ≥3 once variants are linked |
| AUTH-06 | union-by-subject route returns 40 (includes personal-author works); gold should require agent_type evidence per candidate to catch the bleed it almost caught |

## Artifacts
- Per-test: `data/runs/diagnostic_suite_20260612/TEST-*.json` (plan, steps, relaxations, evidence sample)
- Triage: `_triage.json` · Combined: `_combined.json` · Console: `data/runs/diagnostic_suite_20260612_console.log`
