/**
 * @process fix-docs-sync-settings
 * @description Fix stale docs-sync-local reference in settings.json enabledPlugins.
 * The docs-sync plugin was migrated from a local marketplace to GitHub, but
 * settings.json still has the old key "docs-sync@docs-sync-local" instead of
 * "docs-sync@docs-sync". This causes Claude Code to show a plugin error on startup.
 *
 * @inputs { settingsPath, oldPluginKey, newPluginKey, installedPluginsPath, knownMarketplacesPath, marketplaceDir, cacheDir }
 * @outputs { success: boolean, changes: array, verified: boolean }
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    settingsPath,
    oldPluginKey,
    newPluginKey,
    installedPluginsPath,
    knownMarketplacesPath,
    marketplaceDir,
    cacheDir,
  } = inputs;

  const startTime = ctx.now();
  ctx.log('info', 'Starting docs-sync settings fix');

  // ── Phase 1: Audit current state ──────────────────────────────────────────
  const audit = await ctx.task(auditStateTask, {
    settingsPath,
    oldPluginKey,
    newPluginKey,
    installedPluginsPath,
    knownMarketplacesPath,
    marketplaceDir,
    cacheDir,
  });

  // ── Phase 2: Fix settings.json ────────────────────────────────────────────
  const fix = await ctx.task(fixSettingsTask, {
    settingsPath,
    oldPluginKey,
    newPluginKey,
    audit,
  });

  // ── Phase 3: Verify all config files are consistent ───────────────────────
  const verification = await ctx.task(verifyConsistencyTask, {
    settingsPath,
    newPluginKey,
    installedPluginsPath,
    knownMarketplacesPath,
    marketplaceDir,
    cacheDir,
  });

  // ── Phase 4: Update migration doc ────────────────────────────────────────
  const docUpdate = await ctx.task(updateMigrationDocTask, {
    fixApplied: fix,
    verification,
  });

  const elapsed = ctx.now() - startTime;
  ctx.log('info', `Settings fix finished in ${elapsed}ms`);

  return {
    success: verification.consistent || false,
    changes: [audit, fix, verification, docUpdate],
    verified: verification.consistent || false,
    duration: elapsed,
  };
}

// ── Task definitions ─────────────────────────────────────────────────────────

const auditStateTask = defineTask('audit-state', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Audit plugin config state across all files',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Configuration auditor',
      task: 'Audit the current state of the docs-sync plugin configuration across all config files',
      context: {
        settingsPath: args.settingsPath,
        oldPluginKey: args.oldPluginKey,
        newPluginKey: args.newPluginKey,
        installedPluginsPath: args.installedPluginsPath,
        knownMarketplacesPath: args.knownMarketplacesPath,
        marketplaceDir: args.marketplaceDir,
        cacheDir: args.cacheDir,
      },
      instructions: [
        `Read ${args.settingsPath} and check enabledPlugins for "${args.oldPluginKey}" (stale) vs "${args.newPluginKey}" (correct)`,
        `Read ${args.installedPluginsPath} and check that the plugin key is "${args.newPluginKey}"`,
        `Read ${args.knownMarketplacesPath} and check for a "docs-sync" entry with github source`,
        `Check if ${args.marketplaceDir} directory exists`,
        `Check if ${args.cacheDir} directory exists`,
        `Return a JSON report of which files have correct vs stale references`,
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['settingsHasStaleKey', 'settingsHasCorrectKey', 'installedPluginsCorrect', 'knownMarketplacesCorrect', 'marketplaceDirExists', 'cacheDirExists', 'summary'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const fixSettingsTask = defineTask('fix-settings', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Fix enabledPlugins key in settings.json',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Configuration fixer',
      task: `Fix the stale plugin key in ${args.settingsPath}`,
      context: {
        settingsPath: args.settingsPath,
        oldPluginKey: args.oldPluginKey,
        newPluginKey: args.newPluginKey,
        auditResult: args.audit,
      },
      instructions: [
        `Read ${args.settingsPath}`,
        `In the "enabledPlugins" object, remove the key "${args.oldPluginKey}"`,
        `Add the key "${args.newPluginKey}" with value true (if not already present)`,
        `Write the file back with the same formatting (2-space indent JSON)`,
        `IMPORTANT: Only modify the enabledPlugins key. Do NOT change any other settings`,
        `Verify the change by reading the file again`,
        `Return JSON: { changed: boolean, oldKey: string, newKey: string, beforeEnabledPlugins: object, afterEnabledPlugins: object }`,
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['changed', 'oldKey', 'newKey'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const verifyConsistencyTask = defineTask('verify-consistency', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Verify all plugin config files are consistent',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Verification specialist',
      task: 'Verify that ALL docs-sync plugin configuration files are now consistent',
      context: {
        settingsPath: args.settingsPath,
        newPluginKey: args.newPluginKey,
        installedPluginsPath: args.installedPluginsPath,
        knownMarketplacesPath: args.knownMarketplacesPath,
        marketplaceDir: args.marketplaceDir,
        cacheDir: args.cacheDir,
      },
      instructions: [
        `Read ${args.settingsPath} - enabledPlugins should have "${args.newPluginKey}": true and NO "docs-sync-local" references`,
        `Read ${args.installedPluginsPath} - should have key "${args.newPluginKey}" with correct installPath`,
        `Read ${args.knownMarketplacesPath} - should have "docs-sync" entry with github source "hagaybar/docs-sync-plugin"`,
        `Check ${args.marketplaceDir} directory exists`,
        `Check ${args.cacheDir} directory exists`,
        `Grep all three JSON files for any remaining "docs-sync-local" references`,
        `Return JSON: { consistent: boolean, settingsCorrect: boolean, installedPluginsCorrect: boolean, knownMarketplacesCorrect: boolean, marketplaceDirExists: boolean, cacheDirExists: boolean, staleReferencesFound: string[], summary: string }`,
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['consistent', 'summary'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const updateMigrationDocTask = defineTask('update-migration-doc', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Update migration doc with settings.json fix',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Documentation updater',
      task: 'Update the migration history document to record the settings.json fix',
      context: {
        docPath: 'docs/history/2026-04-13-docs-sync-plugin-migration.md',
        fixApplied: args.fixApplied,
        verification: args.verification,
      },
      instructions: [
        `Read docs/history/2026-04-13-docs-sync-plugin-migration.md`,
        `Add a new section "### 6. Fixed settings.json enabledPlugins" documenting that the stale "docs-sync@docs-sync-local" key in enabledPlugins was changed to "docs-sync@docs-sync"`,
        `Update the "Open Item" section to mark it as resolved - the root cause was settings.json, not session caching`,
        `Update the Status line at the top from "Mostly complete" to "Complete"`,
        `Update lesson #2 to say "Plugin registration spans 4 files" (add settings.json enabledPlugins to the list)`,
        `Return JSON: { updated: boolean, sectionsModified: string[] }`,
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['updated', 'sectionsModified'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
