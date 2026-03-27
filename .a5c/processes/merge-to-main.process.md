# Merge Plan: feature/network-map-explorer → main

**Date**: 2026-03-27
**Goal**: Merge all work into main, preserving ALL data from all branches.

---

## Branch Topology

```
main (dd2e258) ──────────────────────────────────────────────────────
  │
  └─ beta-bot-ui (+38 commits = c1e53ff)
       │  Wikipedia enrichment, connection discovery,
       │  narrator integration, specs, plans, babysitter runs
       │
       └─ feature/network-map-explorer (+31 commits = abf4f13)
            Network Map UI, ingestion pipeline, QA audit,
            DB rebuild, bug fixes, LOD XML, enrichment scripts
```

- **main → feature**: 69 commits ahead, 0 behind. **Fast-forward merge possible.**
- **beta-bot-ui → feature**: 31 commits ahead, 0 behind.
- No merge conflicts expected (feature contains all of main's history).

## Key Finding: This Is a Simple Fast-Forward

Since `feature/network-map-explorer` includes ALL commits from `main` (via `beta-bot-ui`), merging feature into main is a **clean fast-forward**. No conflicts, no data loss.

### Files Analysis

| Category | Count | Risk |
|----------|-------|------|
| Files only on feature (new) | 338 | None — all additions |
| Files modified on feature vs main | 359 | None — feature has latest versions |
| Files only on main (deleted on beta-bot-ui) | 24 | **Low** — old Streamlit UIs, archived on beta-bot-ui |

The 24 files only on main are old Streamlit UI files (`app/ui_chat/`, `app/ui_qa/`, etc.) that were deliberately deleted when the unified React UI was built on beta-bot-ui. They're archived at `archive/retired_streamlit/`. The fast-forward merge will delete them, which is correct.

---

## Merge Strategy: Fast-Forward

### Why Fast-Forward (not merge commit)
- Feature includes ALL of main's history — no divergence
- Clean linear history
- No conflicts possible
- No data loss risk

### Pre-Merge Checklist

1. **Verify feature branch is clean**
   ```bash
   git status  # should show clean working tree
   ```

2. **Verify all tests pass**
   ```bash
   cd frontend && npx tsc --noEmit && npm run build
   poetry run pytest tests/ -v --ignore=tests/legacy
   ```

3. **Verify no tracked files are missing**
   ```bash
   # Compare feature vs beta-bot-ui — should show 0 files only on beta-bot-ui
   git diff --name-status feature/network-map-explorer beta-bot-ui | grep "^A" | wc -l
   ```

4. **Verify data files are present**
   ```bash
   git ls-files data/marc_source/  # MARC XML files
   git ls-files data/normalization/  # Alias maps, geocodes
   git ls-files .claude/skills/  # All skills
   ```

### Merge Execution

```bash
# 1. Switch to main
git checkout main

# 2. Fast-forward merge
git merge feature/network-map-explorer --ff-only

# 3. Verify
git log --oneline -5  # Should show feature's latest commits
git diff feature/network-map-explorer  # Should be empty

# 4. Push
git push origin main

# 5. Update beta-bot-ui to match (it's now behind)
git checkout beta-bot-ui
git merge main --ff-only
git push origin beta-bot-ui

# 6. Create release tag on main
git checkout main
git tag -a v1.0.0 -m "v1.0.0: Network Map Explorer + Full Ingestion Pipeline"
git push origin v1.0.0
```

### Post-Merge Verification

```bash
# Verify all data present on main
git checkout main
git ls-files | wc -l  # Should match feature branch file count
git ls-files data/marc_source/  # MARC XMLs tracked
git ls-files .claude/skills/  # All skills present
git ls-files data/normalization/  # Alias maps present

# Verify the 24 old Streamlit files are gone (intentional)
ls app/ui_chat/ 2>/dev/null && echo "OLD FILES STILL EXIST" || echo "Old Streamlit files correctly removed"
```

---

## Risk Assessment

| Risk | Probability | Mitigation |
|------|-------------|------------|
| Data loss from merge | **Zero** | Fast-forward = pointer move only |
| Conflicts | **Zero** | No divergent commits |
| Old Streamlit files lost | **Intentional** | Archived in `archive/retired_streamlit/` |
| DB data loss | **N/A** | DB is gitignored, unaffected by merge |

## What Gets Added to Main (Summary)

- **Network Map Explorer**: MapLibre GL + deck.gl map with 2,757 agents, 32K connections
- **Full Ingestion Pipeline**: `/marc-ingest` command, 7 phases, QA audit
- **Wikipedia Enrichment**: 3-pass pipeline, connection discovery engine
- **DB Safety**: Backup mechanism, seed script protection
- **LOD MARC XML**: Source data with $0 authority URIs in git
- **QA Fixes**: 8 frontend bugs fixed, SPA routing, coverage dashboard
- **21 Babysitter Runs**: Full orchestration history
- **Date Normalization**: Century/decade partials, Roman numerals, Hebrew chronograms
- **Physical Descriptions**: Tag 300 extraction
- **Enrichment Scripts**: Name-based + fast batch Wikidata enrichment
