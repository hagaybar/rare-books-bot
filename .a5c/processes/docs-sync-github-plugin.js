/**
 * @process docs-sync-github-plugin
 * @description Migrate docs-sync plugin from broken local marketplace to a proper GitHub-hosted plugin repo,
 * then clean up leftover files from the project repo.
 *
 * @skill git-expert
 * @agent general-purpose
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    githubRepo,
    localMarketplacePath,
    projectRoot,
    knownMarketplacesPath,
  } = inputs;

  const startTime = ctx.now();
  ctx.log('info', `Starting docs-sync GitHub plugin migration to ${githubRepo}`);

  // Phase 1: Clone the empty GitHub repo and populate it with plugin files
  const setupResult = await ctx.task(setupGithubRepoTask, {
    githubRepo,
    localMarketplacePath,
    projectRoot,
  });

  // Phase 2: Verify the repo structure is correct
  const verifyResult = await ctx.task(verifyRepoStructureTask, {
    githubRepo,
    projectRoot,
  });

  // Breakpoint: Ask user to confirm before pushing and registering
  await ctx.breakpoint({
    question: 'The plugin repo is set up locally and verified. Ready to push to GitHub, register it in known_marketplaces.json, and clean up leftover files?',
    options: ['Yes, push and register', 'Stop here'],
    expert: 'owner',
    tags: ['approval-gate'],
  });

  // Phase 3: Push to GitHub
  const pushResult = await ctx.task(pushToGithubTask, {
    githubRepo,
    projectRoot,
  });

  // Phase 4: Register in known_marketplaces.json
  const registerResult = await ctx.task(registerMarketplaceTask, {
    githubRepo,
    knownMarketplacesPath,
    localMarketplacePath,
  });

  // Phase 5: Clean up leftover files from the project repo
  const cleanupResult = await ctx.task(cleanupLeftoversTask, {
    projectRoot,
    localMarketplacePath,
  });

  // Phase 6: Final verification
  const finalVerify = await ctx.task(finalVerificationTask, {
    githubRepo,
    knownMarketplacesPath,
    projectRoot,
  });

  return {
    success: true,
    githubRepo,
    phases: {
      setup: setupResult,
      verify: verifyResult,
      push: pushResult,
      register: registerResult,
      cleanup: cleanupResult,
      finalVerify: finalVerify,
    },
    duration: ctx.now() - startTime,
  };
}

const setupGithubRepoTask = defineTask('setup-github-repo', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Clone empty GitHub repo and populate with plugin files',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Plugin setup engineer',
      task: `Set up the docs-sync plugin in a freshly cloned GitHub repo.

Steps:
1. Clone ${args.githubRepo} to a temp directory: /tmp/docs-sync-plugin-setup
2. Copy the plugin files from ${args.localMarketplacePath} into the cloned repo with this structure:

   repo-root/
     .claude-plugin/
       marketplace.json    (from ${args.localMarketplacePath}/.claude-plugin/marketplace.json — but FIX the source field)
     plugins/
       docs-sync/
         .claude-plugin/
           plugin.json
         hooks/
           hooks.json
         scripts/
           docs_sync_hook.py
         skills/
           update-docs/
             SKILL.md
         templates/
           topic-map-template.json
         README.md

3. IMPORTANT: The marketplace.json at the repo root must NOT have "source" fields inside individual plugin entries when using relative paths. Use this format:
   {
     "name": "docs-sync",
     "description": "Local marketplace for docs-sync plugin",
     "owner": { "name": "hagaybar" },
     "plugins": [
       {
         "name": "docs-sync",
         "description": "Tracks code changes and notifies when documentation in docs/current/ may need updating",
         "source": "./plugins/docs-sync",
         "category": "development"
       }
     ]
   }

4. Also copy the project-level files that belong with the plugin:
   - Copy ${args.projectRoot}/docs-sync/TEST-FLOW.md to the repo as docs/TEST-FLOW.md (if it exists)

5. Create a proper root-level README.md for the repo explaining what the plugin does.

6. Do NOT run git add/commit yet — just set up the file structure.

Return a JSON summary of what files were created.`,
      context: {
        githubRepo: args.githubRepo,
        localMarketplacePath: args.localMarketplacePath,
        projectRoot: args.projectRoot,
      },
      instructions: [
        'Clone the repo to /tmp/docs-sync-plugin-setup (remove if exists)',
        'Copy files preserving the directory structure',
        'Fix the marketplace.json to not use "local" source type',
        'Do NOT commit yet',
        'Return JSON with list of files created',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['filesCreated', 'repoPath'],
      properties: {
        filesCreated: { type: 'array', items: { type: 'string' } },
        repoPath: { type: 'string' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const verifyRepoStructureTask = defineTask('verify-repo-structure', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Verify plugin repo structure',
  shell: {
    command: `cd /tmp/docs-sync-plugin-setup && echo "=== Directory structure ===" && find . -not -path './.git/*' -not -name '.git' | sort && echo "=== marketplace.json ===" && cat .claude-plugin/marketplace.json && echo "=== plugin.json ===" && cat plugins/docs-sync/.claude-plugin/plugin.json && echo "=== hooks.json ===" && cat plugins/docs-sync/hooks/hooks.json && echo "=== VERIFY COMPLETE ==="`,
  },
  io: {
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const pushToGithubTask = defineTask('push-to-github', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Commit and push plugin files to GitHub',
  shell: {
    command: `cd /tmp/docs-sync-plugin-setup && git add -A && git commit -m "feat: initial docs-sync plugin structure

Migrated from local marketplace to proper GitHub-hosted plugin.
Includes post-commit hook, update-docs skill, topic-map template.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>" && git push -u origin HEAD`,
  },
  io: {
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const registerMarketplaceTask = defineTask('register-marketplace', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Register GitHub plugin in known_marketplaces.json',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Plugin configuration engineer',
      task: `Update the known_marketplaces.json file to register the docs-sync plugin from GitHub.

1. Read ${args.knownMarketplacesPath}
2. Add a "docs-sync" entry (replacing any existing "docs-sync-local" entry) with:
   {
     "source": {
       "source": "github",
       "repo": "${args.githubRepo}"
     },
     "installLocation": "${args.localMarketplacePath}",
     "lastUpdated": "<current ISO timestamp>"
   }
3. Write the updated file back.
4. Verify the JSON is valid.

Return JSON with the updated marketplace entry.`,
      context: {
        githubRepo: args.githubRepo,
        knownMarketplacesPath: args.knownMarketplacesPath,
        localMarketplacePath: args.localMarketplacePath,
      },
      instructions: [
        'Read the current known_marketplaces.json',
        'Remove any docs-sync-local entry if present',
        'Add a docs-sync entry with github source',
        'Write the file and verify JSON validity',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['success', 'entry'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const cleanupLeftoversTask = defineTask('cleanup-leftovers', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Clean up leftover docs-sync files from project repo',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Cleanup engineer',
      task: `Clean up leftover files from the failed babysitter docs-sync runs in the project repo at ${args.projectRoot}.

Files/directories to remove:
1. ${args.projectRoot}/.a5c/processes/fix-docs-sync-plugin.js (leftover process file)
2. ${args.projectRoot}/.a5c/processes/fix-docs-sync-plugin-inputs.json (leftover inputs file)
3. ${args.projectRoot}/docs-sync/TEST-FLOW.md (test file that belongs in the plugin repo)

Files to KEEP (they are valid project files):
- ${args.projectRoot}/.a5c/processes/docs-sync-*.js (other valid process files)
- ${args.projectRoot}/docs-sync/topic-map.json (project-specific config)
- ${args.projectRoot}/docs-sync/artifacts/ (runtime artifacts)
- ${args.projectRoot}/docs/superpowers/specs/2026-04-13-docs-sync-hook-design.md
- ${args.projectRoot}/docs/superpowers/plans/2026-04-13-docs-sync-implementation.md

Also clean up the old local marketplace directory:
- Remove ${args.localMarketplacePath} entirely (its content is now in the GitHub repo)

Return JSON with list of files removed and files kept.`,
      context: {
        projectRoot: args.projectRoot,
        localMarketplacePath: args.localMarketplacePath,
      },
      instructions: [
        'Remove only the specific leftover files listed',
        'Do NOT remove valid project files',
        'Remove the old local marketplace directory',
        'Return JSON summary',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['removed', 'kept'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const finalVerificationTask = defineTask('final-verification', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Final verification of plugin setup',
  shell: {
    command: `echo "=== GitHub repo check ===" && gh repo view ${args.githubRepo} --json name,defaultBranchRef 2>&1 | head -n 5 && echo "=== known_marketplaces.json check ===" && cat ${args.knownMarketplacesPath} | python3 -m json.tool 2>&1 | head -n 50 && echo "=== Leftover check ===" && ls ${args.projectRoot}/.a5c/processes/fix-docs-sync-plugin* 2>&1; ls ${args.projectRoot}/docs-sync/TEST-FLOW.md 2>&1; echo "=== DONE ==="`,
  },
  io: {
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
