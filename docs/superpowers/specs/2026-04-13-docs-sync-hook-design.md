# Docs-Sync: Post-Commit Documentation Maintenance

**Date:** 2026-04-13
**Status:** Design approved, pending implementation
**Scope:** User-scoped hook + project-level skill, active across all projects

---

## Problem

Documentation in `docs/current/` drifts from the codebase because updates depend on manual discipline. Code changes land without corresponding doc updates, and no automated check exists to catch the gap.

## Solution

A two-component system:

1. **PostCommit Hook** (user-scoped) — lightweight analysis after every commit. Produces a structured artifact describing which docs are affected. Never modifies files.
2. **`/update-docs` Skill** — user-triggered, reads the artifact + real git diff + real doc files to make targeted updates. Can also be invoked manually without the hook.

## Design Principles

- **Hook is a sensor, skill is an actuator** — decoupled, independently evolvable.
- **No auto-commits** — the hook never writes to the repo. This prevents commit loops.
- **Project-agnostic** — the hook runs for all projects but gracefully skips those without docs-sync config.
- **Evidence-based** — the skill works from the real git diff and real doc files on disk, never from memory or conversation context.

---

## Component 1: PostCommit Hook

### Configuration

User-scoped in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PostCommit": [
      {
        "command": "python3 ~/.claude/hooks/docs-sync-hook.py",
        "timeout": 10000
      }
    ]
  }
}
```

### Flow

```
Commit made
  -> Hook runs
    -> Step 0: Project detection
       Does topic-map.json exist in this project?
       No  -> exit silently (project not configured)
       Yes -> continue
    -> Step 1: Commit prefix filter
       Prefix is docs:/chore:/style:/test: ?
       Yes -> write artifact with skip_reason, exit
       No  -> continue
    -> Step 2: Get changed files
       git diff-tree --no-commit-id --name-only -r HEAD
    -> Step 3: Match against topic map
       For each changed file, find matching doc(s)
       -> affected_docs list
    -> Step 4: Detect unmapped code files
       Changed .py/.ts/.tsx/.js files not in any mapping
       -> unmapped_files list
    -> Step 5: Write artifact
       docs-sync/artifacts/<commit-sha>.json
    -> Step 6: Print summary to user
       List affected docs and unmapped files
       Offer: "Run /update-docs to sync documentation"
```

### Project Detection

The hook checks for the project-level config file. Location within each project:

```
<project-root>/docs-sync/topic-map.json
```

If this file does not exist, the hook exits with no output. This makes the hook safe to install globally — it only activates for configured projects.

### Topic Map Format

A JSON file mapping each documentation file to the code paths it covers. Supports glob patterns.

```json
{
  "config": {
    "docs_root": "docs/current",
    "code_extensions": [".py", ".ts", ".tsx", ".js", ".jsx"],
    "skip_prefixes": ["docs:", "chore:", "style:", "test:"]
  },
  "mappings": {
    "chatbot-api.md": [
      "app/api/main.py",
      "scripts/chat/**"
    ],
    "streaming.md": [
      "app/api/main.py",
      "frontend/src/pages/Chat.tsx",
      "frontend/src/types/chat.ts"
    ],
    "query-engine.md": [
      "scripts/chat/interpreter.py",
      "scripts/chat/executor.py",
      "scripts/chat/plan_models.py"
    ],
    "normalization-pipeline.md": [
      "scripts/marc/m2_*",
      "data/normalization/**"
    ],
    "architecture.md": [
      "app/**",
      "scripts/**",
      "frontend/src/**"
    ],
    "deployment.md": [
      "deploy.sh",
      "Dockerfile",
      "docker/**"
    ],
    "data-model.md": [
      "scripts/marc/m3_schema.sql",
      "scripts/marc/m1_*",
      "scripts/marc/m2_*"
    ],
    "data-quality.md": [
      "scripts/qa/**",
      "data/qa/**"
    ],
    "metadata-workbench.md": [
      "app/api/main.py",
      "scripts/metadata/**",
      "frontend/src/pages/Workbench.tsx"
    ],
    "ingestion-pipeline.md": [
      "scripts/marc/**"
    ],
    "qa-framework.md": [
      "scripts/qa/**",
      "tests/**"
    ]
  }
}
```

Notes:
- `architecture.md` has broad patterns because structural changes are always relevant to it.
- A file can match multiple docs (e.g., `app/api/main.py` maps to both `chatbot-api.md` and `streaming.md`).
- The `config.code_extensions` list determines which unmapped files get flagged. Non-code files (`.json`, `.md`, `.yml`) are ignored in the unmapped check.

### Artifact Schema

Written to `docs-sync/artifacts/<commit-sha>.json`:

```json
{
  "commit": "dbd5ee0",
  "message": "fix: define agents variable in build_lean_narrator_prompt()",
  "timestamp": "2026-04-13T09:00:00Z",
  "changed_code_files": ["scripts/chat/narrator.py"],
  "affected_docs": ["docs/current/chatbot-api.md", "docs/current/query-engine.md"],
  "unmapped_files": [],
  "skip_reason": null
}
```

When skipped:

```json
{
  "commit": "35960b5",
  "message": "docs: add hard rules for codebase research",
  "timestamp": "2026-04-13T09:05:00Z",
  "changed_code_files": [],
  "affected_docs": [],
  "unmapped_files": [],
  "skip_reason": "commit prefix: docs:"
}
```

### Hook Output (printed to user)

When docs are affected:

```
[docs-sync] Commit dbd5ee0 may affect documentation:
  Affected: chatbot-api.md, query-engine.md
  Run /update-docs to sync.
```

When unmapped files detected:

```
[docs-sync] Commit abc1234 has unmapped code files:
  Unmapped: scripts/chat/new_feature.py
  These files aren't covered by any doc in docs/current/.
  Run /update-docs to review and update the topic map.
```

When skipped:

```
[docs-sync] Skipped (docs: commit).
```

---

## Component 2: `/update-docs` Skill

### Trigger

- Automatically offered by the hook after relevant commits
- Manually invocable at any time by the user

### Modes

**1. Artifact-driven (after hook):**
- Reads the latest artifact from `docs-sync/artifacts/`
- Scoped to the specific commit's changes

**2. Manual (no artifact):**
- Reads recent git log to find commits since the last doc update
- Or accepts a commit range: `/update-docs --since abc1234`
- Scoped to the specified range

### Flow

```
Skill invoked
  -> Read artifact (or compute scope from git log)
  -> For each doc in affected_docs:
     1. Read the actual git diff (git show <commit> -- <files>)
     2. Read the doc file
     3. Determine what changed semantically:
        - New function/endpoint/parameter?
        - Changed behavior?
        - Removed feature?
     4. Make targeted edits to the doc
     5. Update "Last verified: YYYY-MM-DD" header
  -> For unmapped files:
     1. Read the file to understand its purpose
     2. Propose: extend an existing doc OR create a new topic file
     3. If new doc created: update topic-map.json and CLAUDE.md registry
  -> Report changes made
```

### Guardrails

- The skill reads the **real git diff** and **real doc file** for every edit. No working from memory.
- Changes are made as unstaged edits. The user reviews and commits them.
- The skill never auto-commits.

---

## Component 3: Project Bootstrapping

### `/update-docs --init`

Run once per project to set up docs-sync:

1. Scan the project for existing markdown documentation directories
2. Scan the codebase structure (directories, key files)
3. Propose a topic map linking docs to code areas
4. Write `docs-sync/topic-map.json`
5. Create `docs-sync/artifacts/` directory

For projects without existing docs, the init can optionally scaffold a `docs/current/` structure based on the codebase.

### Topic Map Evolution

The topic map is not static. It evolves when:
- The `/update-docs` skill creates a new topic doc (adds mapping)
- Code is reorganized (paths change, skill updates mappings)
- The user manually edits the map

The map is committed to the repo so all collaborators share it.

---

## File Locations

| Component | Location | Scope |
|-----------|----------|-------|
| Hook script | `~/.claude/hooks/docs-sync-hook.py` | User (all projects) |
| Hook config | `~/.claude/settings.json` | User (all projects) |
| Skill definition | `~/.claude/skills/update-docs/SKILL.md` | User (all projects) |
| Topic map | `<project>/docs-sync/topic-map.json` | Per project (committed) |
| Artifacts | `<project>/docs-sync/artifacts/<sha>.json` | Per project (gitignored via `docs-sync/artifacts/`) |

---

## Edge Cases

**Multiple commits before running skill:** Artifacts accumulate. The skill reads all pending artifacts and merges their affected docs into a single update pass.

**Commit touches only test files:** Tests are typically not in any doc mapping and `test:` prefix commits are skipped. If tests are committed with a `feat:` prefix, the file-path matching handles it — test files won't match doc mappings, so they'll be ignored or flagged as unmapped (depending on extension config).

**Large refactors:** A commit touching 20+ files may match many docs. The skill handles this by processing each affected doc independently. The user can also run `/update-docs` with a specific doc: `/update-docs --doc chatbot-api.md`.

**Merge commits:** The hook runs on merge commits too. The diff may be large, but the same filtering applies. The prefix filter catches `Merge branch...` messages (no matching prefix = proceeds to file matching).

---

## What This Does NOT Do

- Does not auto-commit documentation changes (prevents loops)
- Does not read or modify code (only reads diffs for context)
- Does not run on projects without `topic-map.json` (safe global install)
- Does not replace human judgment on doc quality (it updates, user reviews)
