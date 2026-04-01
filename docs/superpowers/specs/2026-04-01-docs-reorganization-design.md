# Documentation Reorganization Design
> Date: 2026-04-01
> Status: Approved
> Goal: Claude finds correct, current information fast; maintenance burden is manageable

## Problem

- CLAUDE.md is 834 lines (32KB), loaded into every conversation — most of it irrelevant to any given task
- No separation between current truth and historical record
- Historical docs (reports, audits, plans, specs) scattered across `docs/`, `reports/`, `audits/` with no index
- Claude wastes tokens reading stale/irrelevant context or can't find the right doc

## Design

### 1. CLAUDE.md (~150 lines)

Trim to operating essentials. Keeps:

| Section | Lines (est.) | Content |
|---------|:---:|---------|
| Project Mission & Answer Contract | ~20 | Unchanged — foundational |
| Data Model Rules | ~6 | Unchanged — non-negotiable |
| Code Style | ~6 | Unchanged |
| Directory Conventions | ~15 | Updated for new docs structure |
| Common Commands | ~20 | Trimmed to essentials |
| Topic Registry | ~30 | Table mapping topics to `docs/current/*.md` |
| Documentation Maintenance Protocol | ~20 | Rules for keeping docs current |
| Available Skills | ~10 | Trimmed |
| What's Different from the Template | ~7 | Unchanged |

Everything else moves to `docs/current/` topic files.

### 2. `docs/current/` — 9 Topic Files

Single source of truth per area. Standard header:

```markdown
# Topic Name
> Last verified: YYYY-MM-DD
> Source of truth for: [scope description]
```

| File | Absorbs from CLAUDE.md | Also absorbs |
|------|----------------------|--------------|
| `normalization-pipeline.md` | Data Normalization Pipeline | `docs/pipelines/place_normalization.md`, `docs/utilities/place_alias_mapping.md`, `docs/specs/m2_normalization_spec.md` |
| `query-engine.md` | LLM Usage Rules, Stable Interfaces, Acceptance Tests | — |
| `chatbot-api.md` | API Layer, Session Management, Response Formatting, Clarification Flow | `docs/session_management_usage.md` |
| `streaming.md` | Streaming Responses (WebSocket), Testing the Chatbot | — |
| `qa-framework.md` | QA Tool Architecture | — |
| `metadata-workbench.md` | Metadata Co-pilot Workbench, Specialist Agents, Publisher Authorities | `docs/metadata_workbench.md`, `docs/metadata_workbench_architecture.md` |
| `deployment.md` | Production Deployment | `docs/deployment.md` |
| `ingestion-pipeline.md` | Full Ingestion Pipeline | — |
| `architecture.md` | Key Architecture Notes, Project Structure | `docs/model_index.md` |

### 3. `docs/history/` — Historical Journal

```
docs/history/
├── INDEX.md              # Reverse-chronological, one line per entry
├── audits/               # Moved from audits/
├── reports/              # Moved from reports/
├── plans/                # Moved from docs/superpowers/plans/
├── specs/                # Moved from docs/superpowers/specs/
├── dev-instructions/     # Moved from docs/dev_instructions/
└── misc/                 # salvaged_discussion.txt, chat_tests/, network_tests/, etc.
```

### 4. Skill Output Paths (Preserved)

| Skill | Writes to | Unchanged? |
|-------|-----------|:---:|
| superpowers:brainstorming | `docs/superpowers/specs/` | Yes |
| superpowers:writing-plans | `docs/superpowers/plans/` | Yes |
| project-audit | `audits/YYYY-MM-DD-<name>/` | Yes |

After implementation/resolution, items are swept to `docs/history/`.

### 5. Untouched Areas

- `.a5c/` — all babysitter processes, runs, artifacts
- `.claude/` — skills, memory, project config
- `scripts/README.md`, `frontend/README.md`
- `docs/testing/MANUAL_TESTING_GUIDE.md`

### 6. Loose File Disposition

| File | Action |
|------|--------|
| `IMPLEMENTATION_PLAN.md` (root) | Move to `docs/history/plans/` |
| `TODO_CONVERSATIONAL_AGENT.md` (root) | Move to `docs/history/misc/` |
| `docs/PROJECT_DESCRIPTION.md` | Move to `docs/history/misc/` |
| `docs/qa_wizard_implementation.md` | Move to `docs/history/misc/` |
| `docs/session_management_implementation_plan.md` | Move to `docs/history/plans/` |
| `docs/specs/SCHEMA_VERSIONING.md` | Move to `docs/history/specs/` |
| `docs/specs/place_frequency_spec.md` | Move to `docs/history/specs/` |
| `docs/testing/other_needed_enhancements_190126.txt` | Delete (330 bytes, stale) |
| `docs/salvaged_discussion.txt` | Move to `docs/history/misc/` |
| `docs/chat_tests/` | Move to `docs/history/misc/` |
| `docs/network_tests/` | Move to `docs/history/misc/` |
| `docs/tests/token-saving-evaluation-2026-04-01.md` | Move to `docs/history/reports/` |

### 7. Documentation Maintenance Protocol (in CLAUDE.md)

```markdown
## Documentation Maintenance Protocol

### On Every Code Change
When you modify code that affects behavior documented in `docs/current/`:
1. Update the relevant topic file in `docs/current/`
2. Set `Last verified: YYYY-MM-DD` in the file header
3. If no topic file exists for the area changed, create one and add it
   to the Topic Registry table above

### On Every New Feature or Architectural Change
1. Update `docs/current/architecture.md` if project structure changed
2. Update the Topic Registry in this file if a new topic was added
3. Update `Common Commands` in this file if new CLI commands were added

### After Superpowers Brainstorming/Planning
- New specs land in `docs/superpowers/specs/` (skill default)
- New plans land in `docs/superpowers/plans/` (skill default)
- After implementation is complete: move the spec/plan to
  `docs/history/specs/` or `docs/history/plans/` and add a line
  to `docs/history/INDEX.md`

### After Project Audits
- New audits land in `audits/YYYY-MM-DD-<name>/` (skill default)
- After action items are resolved: move the audit directory to
  `docs/history/audits/` and add a line to `docs/history/INDEX.md`

### Staleness Rule
If you read a `docs/current/` file and notice it contradicts the
code, fix the doc immediately — don't proceed with stale information.
```

## Migration Summary

1. Create `docs/current/` with 9 topic files (content from CLAUDE.md + existing docs)
2. Create `docs/history/` with INDEX.md, move all historical docs
3. Rewrite CLAUDE.md to ~150 lines with topic registry + maintenance protocol
4. Move loose root files to history
5. Delete `docs/testing/other_needed_enhancements_190126.txt`
6. Verify: every `docs/current/` file is accurate against current code
7. Commit and push
