# Next Audit Checklist

## Pre-Audit Data Collection
```bash
# Git activity since last audit
git log --since="2026-04-01" --oneline | wc -l
git log --since="2026-04-01" --pretty=format: --name-only | sort | uniq -c | sort -rg | head -20

# File sizes (watch for growth)
wc -l app/api/metadata.py app/api/main.py scripts/chat/executor.py scripts/chat/narrator.py

# Test count
pytest --co -q 2>&1 | tail -1

# Dependency versions
pip list --outdated 2>/dev/null | head -20
cd frontend && npm outdated 2>/dev/null | head -20

# Production logs (errors since last audit)
ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 'docker logs rare-books 2>&1 | grep -i "error\|traceback\|exception" | wc -l'
```

## Security Checks
- [ ] SQL injection scan: `rg "f['\"].*SELECT|f['\"].*WHERE" scripts/ app/` — zero hits with user values
- [ ] Path traversal test: `curl https://cenlib-rare-books.nurdillo.com/../../etc/passwd`
- [ ] JWT secret is set (not auto-generated) in production
- [ ] CORS config — no wildcards
- [ ] CSP header — no unsafe-eval
- [ ] WebSocket session ownership validated
- [ ] Rate limiting on all mutation endpoints

## Performance Checks
- [ ] Connection leak scan: all `sqlite3.connect()` have `try/finally`
- [ ] N+1 query patterns in executor grounding
- [ ] Frontend bundle size < 2MB gzipped
- [ ] Health endpoint response time < 100ms

## Metrics to Compare
| Metric | 2026-04-01 | Next Audit |
|--------|------------|------------|
| Python files | 80+ | |
| TypeScript files | 40+ | |
| Tests | 1,433 | |
| metadata.py lines | 2,186 | |
| main.py lines | 1,060 | |
| Frontend bundle (gzip) | ~490KB JS + 272KB MapLibre | |
| SQL injection patterns | 2 found | |
| Connection leak instances | 21 | |
