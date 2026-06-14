# Narrator Gold-Standard Eval — Report

Judge: gpt-5.4 (reasoning_effort=low) · OpenAI Batch pricing · costs are MEASURED from actual tokens (incl. reasoning).

| Model | Mean composite (0-3) | Fabrications | Cases | $/query (narration) | vs gpt-4.1 |
|-------|----------------------|--------------|-------|---------------------|------------|
| gpt-5-mini | 2.50 | 1 | 11 | $0.00231 | +73% cost |
| gpt-5.4-mini | 2.23 | 3 | 11 | $0.00516 | +40% cost |
| gpt-4.1-mini | 1.83 | 5 | 11 | $0.00134 | +84% cost |
| gpt-4.1 | 1.58 | 7 | 11 | $0.00855 | baseline |

**Total eval spend (this run, batch): $0.6632** (narration + gpt-5.4 judging).

*$/query is the production-relevant narration cost (judge cost is eval-only). The 'vs gpt-4.1' column shows cost reduction, NOT quality — read it alongside the composite score.*