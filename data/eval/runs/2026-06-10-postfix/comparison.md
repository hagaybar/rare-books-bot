# Eval comparison: 2026-06-10-baseline → 2026-06-10-postfix

- Common queries: 58
- Avg judge score: 4.102 → 4.026
- Regressions (Δ ≤ -1.0): 6 | Improvements (Δ ≥ +1.0): 5
- Zero-result queries: 0 → 22 (recall data may be absent in older runs)

| query | before | after | Δ | zero→ |
|---|---|---|---|---|
| q01 | 4.25 | 4.25 | 0.0 | None→True |
| q02 | 3.5 | 3.5 | 0.0 | None→True |
| q03 | 5.0 | 5.0 | 0.0 | None→False |
| q04 | 3.5 | 3.5 | 0.0 | None→True |
| q05 | 3.5 | 3.5 | 0.0 | None→False |
| q06 | 1.9000000000000001 | 1.5000000000000002 | -0.4 | None→False |
| q07 | 4.2 | 4.6 | 0.4 | None→True |
| q08 | 5.0 | 5.0 | 0.0 | None→False |
| q09 | 4.6 | 4.6 | 0.0 | None→False |
| q10 | 4.2 | 4.6 | 0.4 | None→False |
| q11 | 1.9000000000000001 | 1.5000000000000002 | -0.4 | None→False |
| q12 | 4.6 | 4.6 | 0.0 | None→False |
| q13 | 5.0 | 5.0 | 0.0 | None→False |
| q14 ⚠ | 4.6 | 3.4 | -1.2 | None→True |
| q15 | 4.6 | 4.6 | 0.0 | None→True |
| q16 | 5.0 | 5.0 | 0.0 | None→True |
| q17 | 5.0 | 5.0 | 0.0 | None→True |
| q18 | 5.0 | 5.0 | 0.0 | None→True |
| q19 | 5.0 | 5.0 | 0.0 | None→False |
| q20 | 3.5 | 3.5 | 0.0 | None→False |
| q21 | 5.0 | 4.6 | -0.4 | None→False |
| q22 | 3.5 | 3.5 | 0.0 | None→False |
| q23 | 1.9 | 5.0 | 3.1 | None→False |
| q24 | 5.0 | 5.0 | 0.0 | None→True |
| q25 | 4.6 | 5.0 | 0.4 | None→True |
| q26 | 3.85 | 4.25 | 0.4 | None→False |
| q27 ⚠ | 3.8 | 0.7 | -3.1 | None→True |
| q28 | 5.0 | 5.0 | 0.0 | None→False |
| q29 ⚠ | 5.0 | 1.9 | -3.1 | None→True |
| q30 ⚠ | 5.0 | 1.9 | -3.1 | None→True |
| q31 | 4.25 | 3.85 | -0.4 | None→False |
| q32 | 3.1 | 4.2 | 1.1 | None→False |
| q33 | 5.0 | 4.6 | -0.4 | None→False |
| q34 | 4.25 | 4.25 | 0.0 | None→False |
| q35 | 3.5 | 5.0 | 1.5 | None→False |
| q36 | 4.6 | 4.6 | 0.0 | None→True |
| q37 | 3.8 | 4.6 | 0.8 | None→False |
| q38 ⚠ | 4.6 | 3.1 | -1.5 | None→False |
| q39 | 3.1 | 3.5 | 0.4 | None→False |
| q40 ⚠ | 4.2 | 3.1 | -1.1 | None→True |
| q41 | 5.0 | 5.0 | 0.0 | None→False |
| q42 | 4.6 | 4.6 | 0.0 | None→False |
| q43 | 3.5 | 3.5 | 0.0 | None→False |
| q44 | 2.3 | 2.7 | 0.4 | None→True |
| q45 | 3.1 | 3.5 | 0.4 | None→False |
| q46 | 5.0 | 4.2 | -0.8 | None→False |
| q47 | 4.2 | 5.0 | 0.8 | None→False |
| q48 | 5.0 | 4.6 | -0.4 | None→False |
| q49 | 3.1 | 2.7 | -0.4 | None→True |
| q50 | 3.5 | 3.5 | 0.0 | None→False |
| q51 | 3.5 | 3.5 | 0.0 | None→True |
| q52 | 3.5 | 3.5 | 0.0 | None→False |
| q53 | 5.0 | 5.0 | 0.0 | None→True |
| q54 | 3.5 | 3.5 | 0.0 | None→False |
| q55 | 3.5 | 5.0 | 1.5 | None→True |
| q56 | 5.0 | 4.2 | -0.8 | None→False |
| q57 | 2.7 | 4.2 | 1.5 | None→False |
| q58 | 5.0 | 5.0 | 0.0 | None→True |