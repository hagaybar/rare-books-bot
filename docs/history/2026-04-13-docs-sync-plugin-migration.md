# docs-sync Plugin Migration to GitHub

**Date:** 2026-04-13  
**Status:** Complete

## What Happened

A babysitter run attempted to create a local marketplace for the docs-sync plugin. It added a `docs-sync-local` entry to `~/.claude/plugins/known_marketplaces.json` with `"source": "local"` — a source type that the Claude Code plugin system doesn't support. This corrupted the config file and caused **all** plugin operations to fail with: `"Marketplace configuration file is corrupted: docs-sync-local.source.source: Invalid input"`.

## What Was Done

### 1. Removed the corrupted entry from known_marketplaces.json
- Removed the `docs-sync-local` entry with `"source": "local"` that was causing the parser to reject the entire file.

### 2. Created proper GitHub repo (hagaybar/docs-sync-plugin)
- User created the empty repo on GitHub
- A babysitter run (`01KP3B428C9PEECJ1ZNHH65AMH`) was used to populate it
- All plugin files were copied from the broken local marketplace at `~/.claude/plugins/marketplaces/docs-sync-local/` into the repo with proper structure:

```
hagaybar/docs-sync-plugin/
  .claude-plugin/
    marketplace.json          # marketplace definition (name: "docs-sync")
  plugins/
    docs-sync/
      .claude-plugin/
        plugin.json           # plugin metadata (v1.0.0)
      hooks/
        hooks.json            # PreToolUse hook for pending notifications
      scripts/
        docs_sync_hook.py     # post-commit hook: matches changed files to topic map
      skills/
        update-docs/
          SKILL.md            # /update-docs skill definition
      templates/
        topic-map-template.json  # template for new project setup
      README.md
  docs/
    TEST-FLOW.md              # testing guide
  README.md                   # repo-level README with install instructions
```

- Pushed as commit `238df04` to `main` branch

### 3. Registered the new marketplace
- Added `docs-sync` entry to `~/.claude/plugins/known_marketplaces.json` with:
  ```json
  "docs-sync": {
    "source": { "source": "github", "repo": "hagaybar/docs-sync-plugin" },
    "installLocation": "~/.claude/plugins/marketplaces/docs-sync"
  }
  ```
- Claude Code automatically cloned the repo to `~/.claude/plugins/marketplaces/docs-sync/`

### 4. Updated installed_plugins.json
- Changed plugin key from `docs-sync@docs-sync-local` to `docs-sync@docs-sync`
- Updated `installPath` from `cache/docs-sync-local/...` to `cache/docs-sync/...`
- Moved the cache directory to match

### 6. Fixed settings.json enabledPlugins

The `enabledPlugins` section in `~/.claude/settings.json` still had the old key `"docs-sync@docs-sync-local": true`. This was the actual root cause of the persistent plugin error — not session caching as originally suspected. Changed it to `"docs-sync@docs-sync": true`.

This was missed in the original migration because `installed_plugins.json` and `known_marketplaces.json` were updated, but `settings.json` was not checked.

### 5. Cleaned up leftovers
**Removed:**
- `~/.claude/plugins/marketplaces/docs-sync-local/` — old broken local marketplace
- `~/.claude/plugins/local/docs-sync/` — another leftover local plugin directory
- `.a5c/processes/fix-docs-sync-plugin.js` and `.a5c/processes/fix-docs-sync-plugin-inputs.json` — leftover babysitter process files
- `docs-sync/TEST-FLOW.md` — moved to the plugin repo

**Kept (valid project files):**
- `.a5c/processes/docs-sync-implement.js`, `docs-sync-plugin.js`, `docs-sync-consolidate.js` — valid process definitions
- `docs-sync/topic-map.json` — project-specific topic map config
- `docs-sync/artifacts/` — runtime artifacts directory
- `docs/superpowers/specs/2026-04-13-docs-sync-hook-design.md`
- `docs/superpowers/plans/2026-04-13-docs-sync-implementation.md`

## Open Item — Resolved

The persistent error `Plugin "docs-sync" not found in marketplace "docs-sync-local"` was **not** caused by session caching — it was caused by a stale key in `~/.claude/settings.json` `enabledPlugins`. The key `"docs-sync@docs-sync-local"` was changed to `"docs-sync@docs-sync"` (see step 6 above). A restart of Claude Code after this fix resolves the error completely.

## Key Lessons

1. **Claude Code plugin marketplaces only support `"source": "github"`** — the `"source": "local"` type is not recognized and corrupts the entire config
2. **Plugin registration spans 4 files** that must stay in sync: `known_marketplaces.json`, `installed_plugins.json`, `settings.json` (`enabledPlugins`), and the `cache/` directory structure
3. **Running Claude Code sessions cache plugin state in memory** — external file changes aren't picked up until restart

## File Locations

| What | Where |
|------|-------|
| Plugin source repo | `https://github.com/hagaybar/docs-sync-plugin` |
| Marketplace config | `~/.claude/plugins/known_marketplaces.json` (key: `docs-sync`) |
| Install registry | `~/.claude/plugins/installed_plugins.json` (key: `docs-sync@docs-sync`) |
| Cloned marketplace | `~/.claude/plugins/marketplaces/docs-sync/` |
| Plugin cache | `~/.claude/plugins/cache/docs-sync/docs-sync/1.0.0/` |
| Project topic map | `rare-books-bot/docs-sync/topic-map.json` |
