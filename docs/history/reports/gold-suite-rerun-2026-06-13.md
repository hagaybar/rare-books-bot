# Diagnostic Suite Re-Run — Before/After (2026-06-12 → 2026-06-13)

36 queries, same harness, after fixes #43/#44/#46/#49/#53/#56 + fix_27/28/29/30.
Interpreter is gpt-4.1 (not seeded) — some shifts are nondeterminism, noted below.

## Deterministic wins (tie directly to fixes)
- **Agent evidence provenance (#43)** — AUTH-01/02/03/06, NORM-01, FTS-02 went from
  10–24 `marc:unknown` evidence objects each to ZERO. Provenance now carries real
  MARC tags (e.g. `marc:100[0]$a`, `marc:700[1]$a`). 6 tests cleaned.
- **Year-EQUALS crash gone (#44)** — TEST-DATE-04 (gematria תקס"ה): error-step/0 →
  executed/20. TEST-NORM-02: error-step/0 → executed/0 (clean). No execution errors
  anywhere in the re-run (was 6 lines of "Unsupported operation").
- **Bragadin Hebrew variants (#46)** — TEST-STRESS-01: 0 → 3 records; TEST-PUB-01: 15 → 22.
- **"Limited editions" recall hole closed** — TEST-SUBJ-05: 0 → 103 (exact ground truth).

## Partial — still needs work
- **AUTH-04 (ibn Habib over-broad, #45)** — 234 → 119. Alias fixes (#53) roughly halved
  it, but it's still far over the ≤3 expected. The selectivity cap (#45) is still needed.

## The three count-drops — investigated, NONE are regressions
- **AUTH-05 (4→0)** — identical plan; the LLM included an `agent_role` filter and
  Manuzio's role_norm didn't match → the role-zeroing trap the test targets, firing.
  Pre-existing; maps to role-normalization follow-up.
- **PUB-03 (1→0)** — routing IMPROVED: "Daniel Bomberg" now correctly routes to
  resolve_publisher (was wrongly resolve_agent). The 0 is an honest empty (Bomberg's
  Talmud editions lack a 'talmud' subject heading). The old "1" was a wrong-routing fluke.
- **DATE-03 (38→71)** — LLM nondeterminism: "around 1650" compiled ±5 before, ±10 now.
  Both defensible.

## Noise (LLM nondeterminism)
- AMBIG-02/03 (clarify vs execute on vague queries), SUBJ-01 (31→36), PHYS-01 (134→131).

## Net read
Every deterministic fix landed and is visible in the real queries. No regressions.
Remaining real targets for batch 2: #45 (AUTH-04 selectivity), role-zeroing (AUTH-05),
subject-coverage/relaxation transparency (PUB-03, SUBJ-04 → #47/#48), and the evidence
cosmetics (#51/#57 — subfield labels, marc:008 vs 041 language source).
