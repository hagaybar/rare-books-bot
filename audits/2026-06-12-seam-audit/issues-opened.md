# Issues Opened — Seam Audit Triage

Date: 2026-06-12 | Source: `audits/2026-06-12-seam-audit/contract-register.md` (22 distinct defects: 21 NEW, 1 partially COVERED-BY-#51) | Label: `seam-audit-2026-06-12`

## Created issues (6)

| issue | covers | summary |
|---|---|---|
| [#55](https://github.com/hagaybar/rare-books-bot/issues/55) | FB-1..FB-5, FB-7..FB-10 | Silent-fallback cluster: 9 swallowed exceptions returning plausible success values (parse-failure proceeds with empty JSONL, alias expansion cached off for process lifetime, fabricated 0.85 confidence, correction-apply failure reported as 0 rows, + 5 medium). Enforcement: P1 silent-fallback contract tests. `bug` |
| [#56](https://github.com/hagaybar/rare-books-bot/issues/56) | B1–B6 | Six planner-emittable filter combinations always raise in db_adapter (subject EQUALS, year IN, residual year EQUALS, list→IN promotion to 4 armless fields, negated multi-value IN, language/agent_role/agent_type CONTAINS) — same failure class as fixed #44. Enforcement: P0 field-op matrix contract test with `xfail(strict=True)` gap cells. `bug` |
| [#57](https://github.com/hagaybar/rare-books-bot/issues/57) | B7–B9 | Silent drift in executor: language param-suffix mismatch (`language` vs `_lang`) keeps first value only; aggregate `country` silently facets cities; unknown aggregate field returns silent empty with no honesty note. Enforcement: P2 metamorphic recall tests. `bug` |
| [#58](https://github.com/hagaybar/rare-books-bot/issues/58) | D1–D4 | 4 live data-invariant violations in production DB: 26 vanished agent aliases (fix_29 collision-order regression, I1 SQL n=26), 3 publisher variant/canonical shadows (P3 n=3), 2 orphan network edges (N1 n=2), 1 wikidata_id disagreement (E1 n=1). Enforcement: P0 invariant battery `tests/integration/test_derived_invariants.py` + marc-ingest phase 7.5 gate. `bug` |
| [#59](https://github.com/hagaybar/rare-books-bot/issues/59) | C9, C12 | Shape-contract defects: active_subgroups defensive load branch constructs `ActiveSubgroup(candidate_set=None)` and raises ValidationError by construction (latent); polymorphic `filters_applied` (`Filter` dumps vs sample `{"strategy","n"}`) structurally breaks the M5 evidence audit. Enforcement: P1 JSON-shape contract tests. `bug` |
| [#60](https://github.com/hagaybar/rare-books-bot/issues/60) | C10, C11 | Design decision: chat persistence layer is dead code — `query_plan`/`candidate_set` columns write-never (0 of 166 rows), `session.active_subgroup` never defined or loaded so `previous_record_ids` is always `[]`. Wire it or delete it; decision test either way. `question` |

## Updated existing issues (4)

| issue | comment added |
|---|---|
| [#51](https://github.com/hagaybar/rare-books-bot/issues/51#issuecomment-4695300333) | FB-6 evidence: corrupt `imprints.source_tags` JSON silently degrades publisher/place/year evidence to `marc:unknown` unlogged (`scripts/query/execute.py:260-262, 278-279, 296-297`; agent path was fixed in #43). Proposed P3 evidence-provenance fuzz test folded into this issue's scope. |
| [#47](https://github.com/hagaybar/rare-books-bot/issues/47#issuecomment-4695301598) | Two new members of the relaxation-transparency family cross-linked: FB-5 concept-bridge silent disablement (`scripts/query/concept_bridge.py:35-45`, filed in #55) and B9 unknown-aggregate silent empty (`scripts/chat/executor.py:1226-1230`, filed in #57). |
| [#54](https://github.com/hagaybar/rare-books-bot/issues/54#issuecomment-4695305033) | D1 cross-reference: same fix_29 run also left 26 authority-linked mononym norms with no alias row at all (I1 SQL, n=26; mechanism at `fix_29_repair_agent_alias_fragments.py:84-93` — collision check ran pre-deletion). Distinct defect filed in #58; shared root cause, separate invariant tests. |
| [#50](https://github.com/hagaybar/rare-books-bot/issues/50#issuecomment-4695306097) | D2 cross-reference: data-side resolution ambiguity — 3 Hebrew variants of authority 229 shadow placeholder authorities 33/41/78 canonicals (P3 SQL, n=3). Filed in #58; shared determinism test proposed (variant resolves to exactly one authority regardless of lookup order). |

No comment added to #45, #48, #49, #52: the register explicitly checked these and carried no new evidence or adjacent finding for them.

## Not filed (unverified)

Per rule 5, UNVERIFIED items were not turned into issues:

1. **chat_messages.query_plan/candidate_set shape-vs-data round-trip fidelity** (SEAM-36, cross-layer-seams.md:130) — unverifiable against data because 0 of 166 rows populate the columns. The verified write-never gap itself IS filed (#60); only the round-trip shape claim remains unverified.
2. **chat_sessions.context/metadata non-empty shape** (cross-layer-seams.md:131) — all 78 live rows store `{}`; non-empty shape behavior unverified. Free-form dict on both sides, no schema to drift; not filed.
3. **titles_fts token-level content parity with titles** (derived-invariants.md:47) — FTS5 `'integrity-check'` is an INSERT and was not run under the read-only constraint. Rowcount + rowid-set parity (F1–F4) verified at 0 violations instead; not filed.

## Totals

- 22 distinct defects in register → 21 filed across 6 new issues (#55–#60), 1 (FB-6) routed as evidence to #51.
- 4 existing issues received consolidated evidence/cross-link comments (#51, #47, #54, #50).
- 3 unverified items excluded from filing.

ISSUES-COMPLETE
