# Docs-Sync Hook & Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a PostCommit hook that detects which docs need updating, plus an `/update-docs` skill that applies the updates.

**Architecture:** User-scoped Python hook at `~/.claude/hooks/docs-sync-hook.py` reads a per-project `docs-sync/topic-map.json`, matches committed files against glob patterns, writes a JSON artifact, and prints a summary. A separate Claude Code skill at `~/.claude/skills/update-docs/SKILL.md` reads the artifact and real git diffs to update documentation. The rare-books-bot project is bootstrapped as the first configured project.

**Tech Stack:** Python 3.12 (hook script), JSON (config/artifacts), Claude Code hooks API, Claude Code skills.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `~/.claude/hooks/docs-sync-hook.py` | PostCommit hook — filter, match, write artifact, print summary |
| `~/.claude/hooks/tests/test_docs_sync_hook.py` | Unit tests for the hook's matching and filtering logic |
| `~/.claude/skills/update-docs/SKILL.md` | Skill definition — instructions for Claude to update docs from artifacts |
| `docs-sync/topic-map.json` | rare-books-bot topic map (committed) |
| `.gitignore` | Add `docs-sync/artifacts/` entry |

---

### Task 1: Hook Script — Core Matching Logic

**Files:**
- Create: `~/.claude/hooks/docs-sync-hook.py`
- Create: `~/.claude/hooks/tests/test_docs_sync_hook.py`

- [ ] **Step 1: Write failing tests for glob matching**

Create the test file with tests for the core matching function:

```python
# ~/.claude/hooks/tests/test_docs_sync_hook.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from docs_sync_hook import match_files_to_docs, detect_unmapped_files

TOPIC_MAP = {
    "config": {
        "docs_root": "docs/current",
        "code_extensions": [".py", ".ts", ".tsx", ".js", ".jsx"],
        "skip_prefixes": ["docs:", "chore:", "style:", "test:"]
    },
    "mappings": {
        "chatbot-api.md": ["app/api/main.py", "scripts/chat/**"],
        "streaming.md": ["app/api/main.py", "frontend/src/pages/Chat.tsx"],
        "deployment.md": ["deploy.sh", "Dockerfile", "docker/**"],
    }
}


def test_exact_match():
    result = match_files_to_docs(["app/api/main.py"], TOPIC_MAP)
    assert sorted(result) == ["chatbot-api.md", "streaming.md"]


def test_glob_match():
    result = match_files_to_docs(["scripts/chat/narrator.py"], TOPIC_MAP)
    assert result == ["chatbot-api.md"]


def test_no_match():
    result = match_files_to_docs(["README.md"], TOPIC_MAP)
    assert result == []


def test_multiple_files():
    result = match_files_to_docs(["deploy.sh", "scripts/chat/executor.py"], TOPIC_MAP)
    assert sorted(result) == ["chatbot-api.md", "deployment.md"]


def test_unmapped_code_files():
    changed = ["scripts/chat/narrator.py", "scripts/new_module.py"]
    mapped = match_files_to_docs(changed, TOPIC_MAP)
    unmapped = detect_unmapped_files(changed, TOPIC_MAP)
    assert "scripts/new_module.py" in unmapped
    assert "scripts/chat/narrator.py" not in unmapped


def test_unmapped_ignores_non_code():
    unmapped = detect_unmapped_files(["data/config.json", ".gitignore"], TOPIC_MAP)
    assert unmapped == []


def test_skip_prefix():
    from docs_sync_hook import should_skip_commit
    assert should_skip_commit("docs: update readme", TOPIC_MAP) == "commit prefix: docs:"
    assert should_skip_commit("chore: bump version", TOPIC_MAP) == "commit prefix: chore:"
    assert should_skip_commit("feat: add feature", TOPIC_MAP) is None
    assert should_skip_commit("fix: bug fix", TOPIC_MAP) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/.claude/hooks && python3 -m pytest tests/test_docs_sync_hook.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'docs_sync_hook'`

- [ ] **Step 3: Implement the matching logic**

Create the hook script with the core functions (no git/IO yet):

```python
#!/usr/bin/env python3
"""PostCommit hook: detect which docs need updating after a commit.

Reads docs-sync/topic-map.json from the project root, matches committed files
against glob patterns, writes a JSON artifact, and prints a summary.
Never modifies repo files. Safe to install globally — exits silently if no
topic-map.json is found.
"""

import fnmatch
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def find_project_root() -> str | None:
    """Find git repo root via git rev-parse."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def load_topic_map(project_root: str) -> dict | None:
    """Load topic-map.json from the project. Returns None if not found."""
    path = os.path.join(project_root, "docs-sync", "topic-map.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def should_skip_commit(message: str, topic_map: dict) -> str | None:
    """Return skip reason if commit should be skipped, None otherwise."""
    prefixes = topic_map.get("config", {}).get(
        "skip_prefixes", ["docs:", "chore:", "style:", "test:"]
    )
    msg = message.strip().lower()
    for prefix in prefixes:
        if msg.startswith(prefix.lower()):
            return f"commit prefix: {prefix}"
    return None


def match_files_to_docs(changed_files: list[str], topic_map: dict) -> list[str]:
    """Match changed files against topic map, return affected doc names."""
    mappings = topic_map.get("mappings", {})
    affected = set()
    for doc_name, patterns in mappings.items():
        for pattern in patterns:
            for changed in changed_files:
                if fnmatch.fnmatch(changed, pattern):
                    affected.add(doc_name)
    return sorted(affected)


def detect_unmapped_files(changed_files: list[str], topic_map: dict) -> list[str]:
    """Find code files not covered by any mapping pattern."""
    extensions = topic_map.get("config", {}).get(
        "code_extensions", [".py", ".ts", ".tsx", ".js", ".jsx"]
    )
    mappings = topic_map.get("mappings", {})
    all_patterns = [p for patterns in mappings.values() for p in patterns]

    unmapped = []
    for f in changed_files:
        ext = os.path.splitext(f)[1]
        if ext not in extensions:
            continue
        covered = any(fnmatch.fnmatch(f, pat) for pat in all_patterns)
        if not covered:
            unmapped.append(f)
    return sorted(unmapped)


def get_commit_info() -> tuple[str, str]:
    """Get HEAD commit SHA and message."""
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    message = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return sha, message


def get_changed_files() -> list[str]:
    """Get list of files changed in HEAD commit."""
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return [f for f in result.stdout.strip().split("\n") if f]


def write_artifact(project_root: str, artifact: dict) -> str:
    """Write artifact JSON to docs-sync/artifacts/<sha>.json."""
    artifacts_dir = os.path.join(project_root, "docs-sync", "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)
    path = os.path.join(artifacts_dir, f"{artifact['commit']}.json")
    with open(path, "w") as f:
        json.dump(artifact, f, indent=2)
    return path


def print_summary(artifact: dict, docs_root: str) -> None:
    """Print human-readable summary to stdout."""
    if artifact.get("skip_reason"):
        print(f"[docs-sync] Skipped ({artifact['skip_reason']}).")
        return

    affected = artifact.get("affected_docs", [])
    unmapped = artifact.get("unmapped_files", [])

    if not affected and not unmapped:
        return

    sha = artifact["commit"]
    if affected:
        names = ", ".join(os.path.basename(d) for d in affected)
        print(f"[docs-sync] Commit {sha} may affect documentation:")
        print(f"  Affected: {names}")
        print("  Run /update-docs to sync.")

    if unmapped:
        files = ", ".join(unmapped)
        print(f"[docs-sync] Commit {sha} has unmapped code files:")
        print(f"  Unmapped: {files}")
        print(f"  These files aren't covered by any doc in {docs_root}/.")
        print("  Run /update-docs to review and update the topic map.")


def main() -> None:
    project_root = find_project_root()
    if not project_root:
        return

    topic_map = load_topic_map(project_root)
    if topic_map is None:
        return

    sha, message = get_commit_info()
    docs_root = topic_map.get("config", {}).get("docs_root", "docs/current")

    skip_reason = should_skip_commit(message, topic_map)
    if skip_reason:
        artifact = {
            "commit": sha,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "changed_code_files": [],
            "affected_docs": [],
            "unmapped_files": [],
            "skip_reason": skip_reason,
        }
        write_artifact(project_root, artifact)
        print_summary(artifact, docs_root)
        return

    changed_files = get_changed_files()
    affected_docs = match_files_to_docs(changed_files, topic_map)
    unmapped_files = detect_unmapped_files(changed_files, topic_map)

    # Prepend docs_root to affected doc names for full paths
    affected_full = [f"{docs_root}/{d}" for d in affected_docs]

    artifact = {
        "commit": sha,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "changed_code_files": changed_files,
        "affected_docs": affected_full,
        "unmapped_files": unmapped_files,
        "skip_reason": None,
    }
    write_artifact(project_root, artifact)
    print_summary(artifact, docs_root)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/.claude/hooks && python3 -m pytest tests/test_docs_sync_hook.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/hooks
git init  # if not already a repo — these are user-scoped files, not in the project repo
```

No git commit for user-scoped files — they live outside the project repo. Just verify the files are in place.

---

### Task 2: Hook Configuration in User Settings

**Files:**
- Modify: `~/.claude/settings.json`

- [ ] **Step 1: Read current settings.json**

Verify the current content of `~/.claude/settings.json` to understand existing hooks structure (there's an existing `Stop` hook).

- [ ] **Step 2: Add PostCommit hook entry**

Add to the `hooks` object in `~/.claude/settings.json`:

```json
"PostCommit": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "python3 ~/.claude/hooks/docs-sync-hook.py"
      }
    ]
  }
]
```

This sits alongside the existing `Stop` hook. The `matcher: ""` means it runs for all commits. The hook script itself handles project detection (exits silently if no `topic-map.json`).

- [ ] **Step 3: Verify hook fires**

Make a trivial commit in the rare-books-bot project (after Task 3 sets up topic-map.json) and confirm the hook output appears.

---

### Task 3: Project Bootstrapping — rare-books-bot Topic Map

**Files:**
- Create: `docs-sync/topic-map.json`
- Modify: `.gitignore` (add `docs-sync/artifacts/`)

- [ ] **Step 1: Create topic-map.json**

Write the topic map for the rare-books-bot project:

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

- [ ] **Step 2: Create artifacts directory**

```bash
mkdir -p docs-sync/artifacts
```

- [ ] **Step 3: Add gitignore entry for artifacts**

Add to `.gitignore`:

```
# Docs-sync artifacts (ephemeral, per-commit analysis)
docs-sync/artifacts/
```

- [ ] **Step 4: Commit**

```bash
git add docs-sync/topic-map.json .gitignore
git commit -m "feat: bootstrap docs-sync for rare-books-bot project"
```

---

### Task 4: End-to-End Hook Test

**Files:** None (verification only)

- [ ] **Step 1: Test with a code commit**

Make a trivial change to a mapped file (e.g., add a comment to `scripts/chat/narrator.py`), commit with `feat:` prefix, verify hook output:

```
[docs-sync] Commit <sha> may affect documentation:
  Affected: chatbot-api.md, query-engine.md
  Run /update-docs to sync.
```

- [ ] **Step 2: Test with a docs commit**

Commit a doc-only change with `docs:` prefix, verify hook skips:

```
[docs-sync] Skipped (commit prefix: docs:).
```

- [ ] **Step 3: Test with unmapped file**

Create a new Python file outside any mapping (e.g., `scripts/new_experiment.py`), commit it, verify unmapped detection:

```
[docs-sync] Commit <sha> has unmapped code files:
  Unmapped: scripts/new_experiment.py
```

- [ ] **Step 4: Revert test commits**

```bash
git reset --soft HEAD~3  # undo the 3 test commits
git checkout -- .        # restore files
```

---

### Task 5: `/update-docs` Skill Definition

**Files:**
- Create: `~/.claude/skills/update-docs/SKILL.md`

- [ ] **Step 1: Write the skill definition**

```markdown
---
name: update-docs
description: Update project documentation based on recent code changes. Use when the docs-sync hook reports affected docs, when you want to sync docs after a series of commits, or when bootstrapping docs-sync for a new project. Trigger on /update-docs or when the post-commit hook suggests running it.
---

# Update Documentation

Sync project documentation with recent code changes. Works in two modes:
artifact-driven (after the post-commit hook) or manual (from git history).

## Arguments

- `--init` — Bootstrap docs-sync for the current project (create topic-map.json)
- `--since <commit>` — Sync docs for all commits since the given SHA
- `--doc <filename>` — Only update a specific doc file
- (no args) — Read pending artifacts from docs-sync/artifacts/ and process them

## Init Mode (`/update-docs --init`)

When `--init` is passed:

1. Check if `docs-sync/topic-map.json` already exists. If so, report and stop.
2. Scan the project for markdown documentation directories (look for `docs/`,
   `docs/current/`, `documentation/`, `reference/`, or any directory with 3+
   `.md` files).
3. Scan the codebase structure — list top-level directories and key source files.
4. Read any existing CLAUDE.md or similar project config for topic registries.
5. Propose a topic-map.json linking discovered docs to code areas.
6. Present the proposed map to the user for approval.
7. Write `docs-sync/topic-map.json` and create `docs-sync/artifacts/`.
8. Add `docs-sync/artifacts/` to `.gitignore` if not already present.
9. Report: "docs-sync initialized. The post-commit hook will now detect
   documentation changes for this project."

## Artifact-Driven Mode (default)

When invoked without arguments:

1. Look for pending artifacts in `docs-sync/artifacts/`.
2. If no artifacts found, check the last 5 commits for changes that would
   affect docs (run the same matching logic as the hook).
3. For each affected doc:
   a. Read the actual git diff: `git show <commit> -- <matched-files>`
   b. Read the current doc file from disk.
   c. Determine what changed semantically:
      - New function, endpoint, parameter, or config option?
      - Changed behavior or return values?
      - Removed or renamed feature?
      - Changed file paths or module structure?
   d. Make targeted edits to the doc. Only change sections relevant to the
      diff. Do not rewrite unchanged sections.
   e. Update the `Last verified: YYYY-MM-DD` header to today's date.
4. For unmapped files:
   a. Read the file to understand its purpose.
   b. Decide: extend an existing doc OR create a new topic file.
   c. If creating a new doc: write it, add to topic-map.json, and update
      the Topic Registry in CLAUDE.md (if one exists).
5. Report all changes made. Do not commit — leave changes unstaged for user
   review.

## Manual Mode (`--since`)

When `--since <commit>` is passed:

1. Run `git log --oneline <commit>..HEAD` to list commits in range.
2. For each commit, get changed files and match against topic map.
3. Merge all affected docs into a deduplicated set.
4. Process each affected doc as in artifact-driven mode, but read the
   combined diff: `git diff <commit>..HEAD -- <matched-files>`
5. Process unmapped files from the combined diff.
6. Report all changes made.

## Single-Doc Mode (`--doc`)

When `--doc <filename>` is passed:

1. Find the doc in the topic map.
2. Get the code files mapped to it.
3. Read the recent diff for those files (last 10 commits).
4. Update the doc based on the diff.

## Guardrails

- ALWAYS read the real git diff before editing any doc. Never work from memory
  or conversation context.
- ALWAYS read the current doc file from disk before editing.
- NEVER auto-commit. Leave all changes unstaged.
- NEVER modify code files. Only modify documentation and topic-map.json.
- When uncertain whether a change warrants a doc update, err on the side of
  updating — stale docs are worse than verbose docs.
- Keep edits surgical. If a function signature changed, update the doc section
  about that function. Don't rewrite the entire doc.
```

- [ ] **Step 2: Verify skill appears in Claude Code**

Start a new Claude Code session and check that `/update-docs` appears in the skill list. Run `/update-docs --help` or similar to verify it loads.

---

### Task 6: Integration Commit

**Files:**
- Commit all project-level files on the dev branch

- [ ] **Step 1: Commit topic-map and gitignore**

```bash
cd /home/hagaybar/projects/rare-books-bot
git add docs-sync/topic-map.json .gitignore
git commit -m "feat: add docs-sync topic map and gitignore artifacts"
```

- [ ] **Step 2: Verify hook fires on the commit**

The commit from Step 1 modifies `.gitignore` — the hook should run and report no affected docs (`.gitignore` is not in any mapping and has no code extension).

- [ ] **Step 3: Push to dev**

```bash
git push origin dev
```

---

### Task 7: Cherry-pick to main

**Files:** None — git operations only.

Per the user's request, the hook should be active on both branches.

- [ ] **Step 1: Switch to main and cherry-pick**

```bash
git checkout main
git stash  # if needed
git cherry-pick <commit-sha-from-task-6>
```

- [ ] **Step 2: Push main**

```bash
git push origin main
```

- [ ] **Step 3: Switch back to dev**

```bash
git checkout dev
git stash pop  # if needed
```
