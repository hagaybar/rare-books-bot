# Next Audit Checklist
**Created**: 2026-03-22
**Use after**: Action plan items from this audit are addressed

---

## Pre-Audit Commands

```bash
# Test health
poetry run pytest --tb=short -q

# Lint status
ruff check . 2>&1 | tail -5

# Normalization coverage
sqlite3 data/index/bibliographic.db "
  SELECT
    COUNT(*) as total,
    SUM(CASE WHEN place_confidence >= 0.90 THEN 1 ELSE 0 END) as place_high,
    SUM(CASE WHEN publisher_confidence >= 0.90 THEN 1 ELSE 0 END) as pub_high,
    SUM(CASE WHEN date_confidence >= 0.90 THEN 1 ELSE 0 END) as date_high
  FROM imprints;
"

# Recent git activity
git log --oneline -20

# File sizes (complexity check)
wc -l app/api/main.py app/api/metadata.py scripts/query/execute.py scripts/marc/parse.py
```

## Metrics to Compare Against This Audit

| Metric | 2026-03-22 Baseline | Target |
|--------|---------------------|--------|
| Tests passing | 1,063 / 1,076 (98.8%) | 100% |
| Ruff errors | 590 | 0 |
| Place high-conf | 99.3% | >= 99% |
| Publisher high-conf | 98.8% | >= 99% |
| Date high-conf | 68.2% | >= 90% |
| Deprecation warnings | 3 | 0 |
| Largest file (lines) | 1,484 | < 800 |

## Focus Areas for Next Audit

1. Were all 13 failing tests fixed?
2. Is evidence extraction now fail-closed?
3. Has date normalization coverage improved?
4. Were large API files split?
5. Are there new failing tests or regressions?
6. Has the frontend gained any test coverage?
