/**
 * @process docs-sync-consolidate
 * @description Consolidate docs-sync into a single plugin with git post-commit hook
 * and real-time notification to Claude via a lightweight poll mechanism.
 *
 * Issues to resolve:
 * 1. Duplicate files: standalone hook/skill vs plugin copies — plugin should be sole source
 * 2. Hook type: Claude PostToolUse hook only fires for Claude-made commits → switch to git post-commit
 * 3. Message passing: git hook stdout doesn't reach Claude → notification file + PreToolUse poll
 * 4. Archive pruning: standalone hook has prune_archive(), plugin copy doesn't
 *
 * Architecture after consolidation:
 * - Plugin at ~/.claude/plugins/local/docs-sync/ is the ONLY source
 * - Git post-commit hook at .git/hooks/post-commit calls the plugin's script
 * - Plugin script writes artifacts + appends to .pending-notification
 * - Claude PreToolUse hook reads .pending-notification and prints it, then truncates
 * - Standalone copies at ~/.claude/hooks/ and ~/.claude/skills/ are removed
 * - Claude PostToolUse hook in plugin hooks.json is replaced with PreToolUse notification reader
 *
 * @inputs { pluginDir, standaloneHookPath, standaloneSkillDir, settingsPath, projectRoot, topicMapPath, notificationFile, archiveKeep }
 * @outputs { success: boolean, changes: array, verified: boolean }
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    pluginDir,
    standaloneHookPath,
    standaloneSkillDir,
    settingsPath,
    projectRoot,
    topicMapPath,
    notificationFile,
    archiveKeep,
  } = inputs;

  const startTime = ctx.now();
  ctx.log('info', 'Starting docs-sync consolidation');

  // ── Phase 1: Audit current state ──────────────────────────────────────────
  const audit = await ctx.task(auditCurrentStateTask, {
    pluginDir,
    standaloneHookPath,
    standaloneSkillDir,
    settingsPath,
    projectRoot,
  });

  // ── Phase 2: Sync plugin hook script ──────────────────────────────────────
  // Copy the latest standalone hook (with prune_archive) into the plugin,
  // PLUS add the notification-file write logic.
  const syncHook = await ctx.task(syncAndEnhanceHookTask, {
    pluginDir,
    standaloneHookPath,
    notificationFile,
    archiveKeep,
    audit,
  });

  // ── Phase 3: Update plugin hooks.json ─────────────────────────────────────
  // Replace PostToolUse → PreToolUse notification reader
  const updatePluginHooks = await ctx.task(updatePluginHooksConfigTask, {
    pluginDir,
    projectRoot,
    notificationFile,
  });

  // ── Phase 4: Install git post-commit hook ─────────────────────────────────
  const installGitHook = await ctx.task(installGitPostCommitHookTask, {
    pluginDir,
    projectRoot,
  });

  // ── Breakpoint: Review changes before cleanup ─────────────────────────────
  const reviewApproval = await ctx.breakpoint({
    question: 'Review the changes so far. The next step removes standalone copies. Approve to continue?',
    options: ['Approve — remove standalone copies', 'Stop — keep standalone copies for now'],
    expert: 'owner',
    tags: ['cleanup-gate'],
  });

  if (!reviewApproval.approved) {
    ctx.log('info', 'User stopped before cleanup');
    return {
      success: true,
      changes: [audit, syncHook, updatePluginHooks, installGitHook],
      verified: false,
      note: 'Stopped before standalone cleanup per user request',
    };
  }

  // ── Phase 5: Remove standalone copies ─────────────────────────────────────
  const cleanup = await ctx.task(removeStandaloneCopiesTask, {
    standaloneHookPath,
    standaloneSkillDir,
  });

  // ── Phase 6: End-to-end verification ──────────────────────────────────────
  const verify = await ctx.task(e2eVerificationTask, {
    pluginDir,
    projectRoot,
    notificationFile,
  });

  // ── Breakpoint: Final review ──────────────────────────────────────────────
  await ctx.breakpoint({
    question: `Consolidation complete. Verification ${verify.passed ? 'PASSED' : 'FAILED'}. Review the summary and approve to finish.`,
    options: ['Approve — done', 'Request changes'],
    expert: 'owner',
    tags: ['final-review'],
  });

  const elapsed = ctx.now() - startTime;
  ctx.log('info', `Consolidation finished in ${elapsed}ms`);

  return {
    success: verify.passed,
    changes: [audit, syncHook, updatePluginHooks, installGitHook, cleanup, verify],
    verified: verify.passed,
  };
}

// ── Task Definitions ──────────────────────────────────────────────────────────

const auditCurrentStateTask = defineTask('audit-current-state', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Audit docs-sync: inventory all files, find duplicates and drift',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Infrastructure auditor',
      task: 'Audit the current state of the docs-sync plugin and its standalone copies',
      context: {
        pluginDir: args.pluginDir,
        standaloneHookPath: args.standaloneHookPath,
        standaloneSkillDir: args.standaloneSkillDir,
        settingsPath: args.settingsPath,
        projectRoot: args.projectRoot,
      },
      instructions: [
        `Read and diff the hook scripts at two locations:`,
        `  1. Plugin: ${args.pluginDir}/scripts/docs_sync_hook.py`,
        `  2. Standalone: ${args.standaloneHookPath}`,
        `Read and diff the skill files at two locations:`,
        `  1. Plugin: ${args.pluginDir}/skills/update-docs/SKILL.md`,
        `  2. Standalone: ${args.standaloneSkillDir}/SKILL.md`,
        `Check ${args.settingsPath} for any docs-sync hook registrations in the "hooks" section (separate from enabledPlugins)`,
        `Check the plugin hooks config at ${args.pluginDir}/hooks/hooks.json`,
        `Check if ${args.projectRoot}/.git/hooks/post-commit exists`,
        `List all artifacts in ${args.projectRoot}/docs-sync/artifacts/`,
        `Return a JSON report with: { duplicates: [{file1, file2, inSync: bool}], hookRegistrations: [...], gitHookExists: bool, pendingArtifacts: int }`,
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['duplicates', 'hookRegistrations', 'gitHookExists', 'pendingArtifacts'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const syncAndEnhanceHookTask = defineTask('sync-and-enhance-hook', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Sync plugin hook script with standalone (add prune_archive + notification)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer',
      task: 'Update the plugin hook script to be the definitive version with all features',
      context: {
        pluginScriptPath: `${args.pluginDir}/scripts/docs_sync_hook.py`,
        standaloneScriptPath: args.standaloneHookPath,
        notificationFile: args.notificationFile,
        archiveKeep: args.archiveKeep,
      },
      instructions: [
        `Read both hook scripts:`,
        `  1. Standalone: ${args.standaloneHookPath} (has prune_archive function)`,
        `  2. Plugin: ${args.pluginDir}/scripts/docs_sync_hook.py (missing prune_archive)`,
        `Update the PLUGIN copy to include:`,
        `  a. The prune_archive() function from the standalone version`,
        `  b. Both prune_archive() calls in main() (skip path and normal path)`,
        `  c. NEW: After print_summary(), also write a one-line notification to ${args.notificationFile}`,
        `     Format: "[docs-sync] <sha> | <message> | Affected: <docs-list-or-skipped>"`,
        `     Use append mode ("a"). Create parent dirs if needed.`,
        `     Only write if there IS something to report (affected docs, unmapped files, or skip).`,
        `     For the silent case (no affected docs, no unmapped, not skipped): write nothing.`,
        `  d. The notification file path should be relative to project_root`,
        `Do NOT modify the standalone copy — only update the plugin copy.`,
        `Return { updatedFile: string, changesApplied: string[] }`,
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['updatedFile', 'changesApplied'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const updatePluginHooksConfigTask = defineTask('update-plugin-hooks-config', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Replace PostToolUse hook with PreToolUse notification reader in plugin',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Claude Code plugin developer',
      task: 'Update the plugin hooks.json to replace the commit-detection hook with a notification display hook',
      context: {
        pluginDir: args.pluginDir,
        projectRoot: args.projectRoot,
        notificationFile: args.notificationFile,
        hooksConfigPath: `${args.pluginDir}/hooks/hooks.json`,
      },
      instructions: [
        `Read the current hooks config at ${args.pluginDir}/hooks/hooks.json`,
        `The current config has a PostToolUse hook that fires on "Bash(git commit*)" — this is being replaced by a git post-commit hook.`,
        `Replace the entire hooks config with a PreToolUse hook that:`,
        `  1. Fires on ALL tool calls (matcher: "" or no matcher)`,
        `  2. Runs a small shell script that:`,
        `     a. Finds the git repo root (git rev-parse --show-toplevel)`,
        `     b. Checks if <repo-root>/${args.notificationFile} exists and is non-empty`,
        `     c. If yes: cat the file contents and truncate it (> file)`,
        `     d. If no: exit silently (exit 0)`,
        `  3. Has a short timeout (5 seconds max)`,
        `The hook should be a single inline bash command, not a separate script file.`,
        `Write the updated hooks.json file.`,
        `Return { updatedFile: string, previousConfig: object, newConfig: object }`,
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['updatedFile', 'newConfig'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const installGitPostCommitHookTask = defineTask('install-git-post-commit-hook', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Install git post-commit hook that calls the plugin script',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Git hooks developer',
      task: 'Create a git post-commit hook that invokes the docs-sync plugin script',
      context: {
        pluginDir: args.pluginDir,
        projectRoot: args.projectRoot,
        gitHookPath: `${args.projectRoot}/.git/hooks/post-commit`,
        pluginScriptPath: `${args.pluginDir}/scripts/docs_sync_hook.py`,
      },
      instructions: [
        `Check if ${args.projectRoot}/.git/hooks/post-commit already exists.`,
        `If it exists, read it. We need to ADD our hook, not replace existing hooks.`,
        `Create or update the post-commit hook to run: python3 ${args.pluginDir}/scripts/docs_sync_hook.py`,
        `The hook script should:`,
        `  1. Have #!/bin/bash shebang`,
        `  2. Run the python script, capturing exit code but not blocking on failure`,
        `  3. If the file already exists with other hooks, append our command (don't replace)`,
        `  4. Make the file executable (chmod +x)`,
        `Return { hookPath: string, created: bool, appended: bool, content: string }`,
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['hookPath', 'created'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const removeStandaloneCopiesTask = defineTask('remove-standalone-copies', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Remove standalone hook and skill (plugin is now the sole source)',
  shell: {
    command: [
      `echo "Removing standalone copies..."`,
      `rm -v "${args.standaloneHookPath}" 2>/dev/null || echo "Standalone hook already gone"`,
      `rm -rv "${args.standaloneSkillDir}" 2>/dev/null || echo "Standalone skill dir already gone"`,
      `echo "Done. Remaining copies are plugin-only."`,
    ].join(' && '),
  },
  io: {
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const e2eVerificationTask = defineTask('e2e-verification', (args, taskCtx) => ({
  kind: 'agent',
  title: 'End-to-end verification: git commit → artifact + notification → Claude display',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer',
      task: 'Verify the full docs-sync flow works end-to-end after consolidation',
      context: {
        pluginDir: args.pluginDir,
        projectRoot: args.projectRoot,
        notificationFile: args.notificationFile,
      },
      instructions: [
        `Verify the following (read files, don't make commits):`,
        `1. Plugin hook script exists at ${args.pluginDir}/scripts/docs_sync_hook.py and contains prune_archive function`,
        `2. Plugin hook script contains notification-file write logic`,
        `3. Plugin hooks.json has PreToolUse notification reader (not PostToolUse commit detector)`,
        `4. Git post-commit hook exists at ${args.projectRoot}/.git/hooks/post-commit and is executable`,
        `5. Git post-commit hook calls the plugin script`,
        `6. Standalone hook at ~/.claude/hooks/docs_sync_hook.py is GONE`,
        `7. Standalone skill dir at ~/.claude/skills/update-docs/ is GONE`,
        `8. Plugin skill still exists at ${args.pluginDir}/skills/update-docs/SKILL.md`,
        `9. Plugin is still enabled in ~/.claude/settings.json`,
        `10. Topic map exists at ${args.projectRoot}/docs-sync/topic-map.json`,
        `Return { passed: bool, checks: [{name, passed, detail}] }`,
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['passed', 'checks'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const fixIssuesTask = defineTask('fix-issues', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Fix issues found during verification',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Developer',
      task: 'Fix the issues found during E2E verification',
      context: {
        verifyResult: args.verifyResult,
        pluginDir: args.pluginDir,
        projectRoot: args.projectRoot,
      },
      instructions: [
        `The E2E verification found these failing checks:`,
        JSON.stringify(args.verifyResult?.checks?.filter(c => !c.passed) || []),
        `Fix each failing check. Read the relevant files, make corrections, and verify.`,
        `Return { fixed: string[], remaining: string[] }`,
      ],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
