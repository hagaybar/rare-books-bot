/**
 * @process docs-sync-implement
 * @description Execute docs-sync hook implementation with strict quality gates — TDD, verification, E2E testing
 * @inputs { projectRoot: string, planPath: string, specPath: string, hookPath: string, testPath: string, skillPath: string, settingsPath: string, topicMapPath: string }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill update-config .claude/skills/update-config/SKILL.md
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    hookPath = '/home/hagaybar/.claude/hooks/docs-sync-hook.py',
    testPath = '/home/hagaybar/.claude/hooks/tests/test_docs_sync_hook.py',
    skillPath = '/home/hagaybar/.claude/skills/update-docs/SKILL.md',
    settingsPath = '/home/hagaybar/.claude/settings.json',
    topicMapPath = 'docs-sync/topic-map.json',
    planPath = 'docs/superpowers/plans/2026-04-13-docs-sync-implementation.md',
    specPath = 'docs/superpowers/specs/2026-04-13-docs-sync-hook-design.md',
  } = inputs;

  // ============================================================================
  // PHASE 1: Write tests + implement hook script (TDD)
  // ============================================================================

  ctx.log('info', 'Phase 1: TDD — write tests and implement hook script');

  const hookResult = await ctx.task(implementHookTask, {
    projectRoot, hookPath, testPath, planPath, specPath,
  });

  ctx.log('info', `Hook implementation: ${JSON.stringify(hookResult).slice(0, 300)}`);

  // Quality gate: tests must pass
  const testVerify1 = await ctx.task(runTestsTask, {
    testPath, hookPath, gate: 'Phase 1',
  });

  ctx.log('info', `Phase 1 test gate: ${JSON.stringify(testVerify1).slice(0, 200)}`);

  // ============================================================================
  // PHASE 2: Hook config in user settings
  // ============================================================================

  ctx.log('info', 'Phase 2: Configure PostCommit hook in user settings');

  const configResult = await ctx.task(configureHookTask, {
    settingsPath, hookPath,
  });

  ctx.log('info', `Hook config: ${JSON.stringify(configResult).slice(0, 200)}`);

  // ============================================================================
  // PHASE 3: Bootstrap rare-books-bot project
  // ============================================================================

  ctx.log('info', 'Phase 3: Create topic-map.json and gitignore artifacts');

  const bootstrapResult = await ctx.task(bootstrapProjectTask, {
    projectRoot, topicMapPath, specPath,
  });

  ctx.log('info', `Bootstrap: ${JSON.stringify(bootstrapResult).slice(0, 200)}`);

  // ============================================================================
  // PHASE 4: End-to-end verification
  // ============================================================================

  ctx.log('info', 'Phase 4: End-to-end hook verification');

  const e2eResult = await ctx.task(e2eVerifyTask, {
    projectRoot, hookPath, topicMapPath,
  });

  ctx.log('info', `E2E verify: ${JSON.stringify(e2eResult).slice(0, 300)}`);

  // ============================================================================
  // PHASE 5: /update-docs skill definition
  // ============================================================================

  ctx.log('info', 'Phase 5: Write /update-docs skill');

  const skillResult = await ctx.task(writeSkillTask, {
    skillPath, planPath,
  });

  ctx.log('info', `Skill written: ${JSON.stringify(skillResult).slice(0, 200)}`);

  // ============================================================================
  // PHASE 6: Commit to dev + push
  // ============================================================================

  ctx.log('info', 'Phase 6: Commit and push to dev');

  const commitResult = await ctx.task(commitAndPushTask, {
    projectRoot, topicMapPath,
  });

  ctx.log('info', `Commit: ${JSON.stringify(commitResult).slice(0, 200)}`);

  // ============================================================================
  // BREAKPOINT: Review before cherry-picking to main
  // ============================================================================

  await ctx.breakpoint({
    question: 'All phases complete. Hook tests pass, E2E verified, skill written, pushed to dev. Ready to cherry-pick to main?',
    title: 'Pre-main cherry-pick review',
    options: ['Cherry-pick to main', 'Skip — stay on dev only'],
  });

  // ============================================================================
  // PHASE 7: Cherry-pick to main
  // ============================================================================

  ctx.log('info', 'Phase 7: Cherry-pick to main');

  const cherryResult = await ctx.task(cherryPickTask, {
    projectRoot, commitSha: commitResult.commitSha || 'HEAD',
  });

  ctx.log('info', `Cherry-pick: ${JSON.stringify(cherryResult).slice(0, 200)}`);

  // Final test gate
  const testVerifyFinal = await ctx.task(runTestsTask, {
    testPath, hookPath, gate: 'Final',
  });

  ctx.log('info', `Final test gate: ${JSON.stringify(testVerifyFinal).slice(0, 200)}`);

  return {
    success: true,
    hookResult, configResult, bootstrapResult,
    e2eResult, skillResult, commitResult, cherryResult,
  };
}

// ============================================================================
// Task: Implement hook script with TDD
// ============================================================================

const implementHookTask = defineTask('implement-hook', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Write tests and implement docs-sync hook script',
  execution: { timeout: 300000 },
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer following strict TDD',
      task: `Implement the docs-sync PostCommit hook script using TDD.

Read the implementation plan at ${args.projectRoot}/${args.planPath} — Task 1.
Read the spec at ${args.projectRoot}/${args.specPath} for the full design.

EXECUTE THESE STEPS IN ORDER:

1. Create directory: mkdir -p /home/hagaybar/.claude/hooks/tests

2. Write the test file at ${args.testPath} with ALL tests from the plan's Task 1, Step 1.
   Copy the test code EXACTLY from the plan.

3. Run the tests to verify they FAIL:
   cd /home/hagaybar/.claude/hooks && python3 -m pytest tests/test_docs_sync_hook.py -v 2>&1
   Expected: ModuleNotFoundError

4. Write the hook script at ${args.hookPath} with the COMPLETE implementation from Task 1, Step 3.
   Copy the code EXACTLY from the plan. Make sure the file is named docs_sync_hook.py (underscore, not hyphen)
   so it can be imported by tests, BUT the settings.json will reference it as docs-sync-hook.py.

   IMPORTANT: The import in tests uses underscored name. Create TWO files:
   - /home/hagaybar/.claude/hooks/docs_sync_hook.py (the actual module, importable)
   - /home/hagaybar/.claude/hooks/docs-sync-hook.py (symlink or wrapper that imports and runs main)

   Actually, simpler approach: name the file docs_sync_hook.py and update the settings command to reference that name.

5. Run the tests to verify they PASS:
   cd /home/hagaybar/.claude/hooks && python3 -m pytest tests/test_docs_sync_hook.py -v 2>&1
   Expected: All 7 tests PASS

Return the test output and confirmation that both files were created.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Follow TDD strictly: tests first, then implementation',
        'Copy code from the plan exactly',
        'Run tests after each step',
        'Return full test output',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['testsPass', 'hookCreated', 'testOutput'],
      properties: {
        testsPass: { type: 'boolean' },
        hookCreated: { type: 'boolean' },
        testOutput: { type: 'string' },
        filesCreated: { type: 'array' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task: Run tests (quality gate)
// ============================================================================

const runTestsTask = defineTask('run-tests', (args, taskCtx) => ({
  kind: 'shell',
  title: `Quality gate: run hook tests (${args.gate})`,
  shell: {
    command: `cd /home/hagaybar/.claude/hooks && python3 -m pytest tests/test_docs_sync_hook.py -v 2>&1`,
    cwd: '/home/hagaybar/.claude/hooks',
  },
  io: {
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task: Configure hook in user settings
// ============================================================================

const configureHookTask = defineTask('configure-hook', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Add PostCommit hook to ~/.claude/settings.json',
  execution: { timeout: 120000 },
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Configuration specialist',
      task: `Add a PostCommit hook entry to ${args.settingsPath}.

1. Read the current settings.json at ${args.settingsPath}
2. Add a PostCommit entry to the existing hooks object. The hooks object already has a "Stop" key.
   Add this alongside it:

   "PostCommit": [
     {
       "matcher": "",
       "hooks": [
         {
           "type": "command",
           "command": "python3 /home/hagaybar/.claude/hooks/docs_sync_hook.py"
         }
       ]
     }
   ]

3. Write the updated settings.json back, preserving ALL existing content.
4. Verify the JSON is valid by reading it back.

IMPORTANT: Do NOT remove or modify any existing keys. Only ADD the PostCommit entry.`,
      context: { settingsPath: args.settingsPath },
      instructions: [
        'Preserve all existing settings',
        'Only add the PostCommit key',
        'Verify valid JSON after writing',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['configured'],
      properties: {
        configured: { type: 'boolean' },
        settingsKeys: { type: 'array' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task: Bootstrap project with topic-map.json
// ============================================================================

const bootstrapProjectTask = defineTask('bootstrap-project', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Create topic-map.json and gitignore for rare-books-bot',
  execution: { timeout: 120000 },
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Project setup specialist',
      task: `Bootstrap docs-sync for the rare-books-bot project.

Project root: ${args.projectRoot}

1. Read the spec at ${args.projectRoot}/${args.specPath} — specifically the "Topic Map Format" section.

2. Create directory: mkdir -p ${args.projectRoot}/docs-sync/artifacts

3. Write ${args.projectRoot}/${args.topicMapPath} with the EXACT topic map from the spec (the full JSON with config + mappings).

4. Add "docs-sync/artifacts/" to ${args.projectRoot}/.gitignore if not already present.
   Add it under a clear comment: "# Docs-sync artifacts (ephemeral, per-commit analysis)"

5. Verify: cat ${args.projectRoot}/${args.topicMapPath} | python3 -m json.tool
   (must be valid JSON)

Return confirmation of files created.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Use exact topic map from spec',
        'Verify JSON is valid',
        'Do not modify existing gitignore entries',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['topicMapCreated', 'gitignoreUpdated'],
      properties: {
        topicMapCreated: { type: 'boolean' },
        gitignoreUpdated: { type: 'boolean' },
        validJson: { type: 'boolean' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task: End-to-end verification
// ============================================================================

const e2eVerifyTask = defineTask('e2e-verify', (args, taskCtx) => ({
  kind: 'agent',
  title: 'End-to-end hook verification',
  execution: { timeout: 180000 },
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer running E2E tests',
      task: `Run end-to-end tests of the docs-sync hook.

Project root: ${args.projectRoot}
Hook script: ${args.hookPath}
Topic map: ${args.projectRoot}/${args.topicMapPath}

The hook is a standalone Python script. We can test it by simulating what happens after a commit.

TEST 1: Direct invocation in the project directory
  cd ${args.projectRoot} && python3 ${args.hookPath}
  This should run the hook against the current HEAD commit.
  Expected: either a "may affect documentation" message or "Skipped" depending on the last commit.
  Capture the output.

TEST 2: Verify artifact was written
  ls -la ${args.projectRoot}/docs-sync/artifacts/
  Should contain a .json file for the HEAD commit.
  Read the artifact and verify it matches the schema:
  - has commit, message, timestamp, changed_code_files, affected_docs, unmapped_files, skip_reason

TEST 3: Test skip logic
  Create a temp script that mocks the git commands to return a "docs:" prefix message:
  cd ${args.projectRoot} && python3 -c "
  import sys
  sys.path.insert(0, '/home/hagaybar/.claude/hooks')
  from docs_sync_hook import should_skip_commit, match_files_to_docs, detect_unmapped_files, load_topic_map

  tm = load_topic_map('${args.projectRoot}')
  assert tm is not None, 'topic-map.json not found'

  # Test skip
  assert should_skip_commit('docs: update readme', tm) == 'commit prefix: docs:'
  assert should_skip_commit('feat: add feature', tm) is None

  # Test matching
  affected = match_files_to_docs(['scripts/chat/narrator.py'], tm)
  assert 'chatbot-api.md' in affected, f'Expected chatbot-api.md in {affected}'

  # Test unmapped
  unmapped = detect_unmapped_files(['scripts/brand_new.py'], tm)
  assert 'scripts/brand_new.py' in unmapped, f'Expected unmapped: {unmapped}'

  print('ALL E2E CHECKS PASSED')
  "

Return pass/fail for each test with output.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Run all 3 tests',
        'Capture full output',
        'Report pass/fail for each',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['allPassed', 'tests'],
      properties: {
        allPassed: { type: 'boolean' },
        tests: { type: 'array' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task: Write /update-docs skill
// ============================================================================

const writeSkillTask = defineTask('write-skill', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Write /update-docs skill definition',
  execution: { timeout: 120000 },
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Claude Code skill author',
      task: `Create the /update-docs skill.

Read the implementation plan at /home/hagaybar/projects/rare-books-bot/${args.planPath} — Task 5.

1. Create directory: mkdir -p /home/hagaybar/.claude/skills/update-docs

2. Write ${args.skillPath} with the COMPLETE skill definition from the plan's Task 5, Step 1.
   Copy the content EXACTLY from the plan — it has the full SKILL.md with frontmatter,
   description, all modes (init, artifact-driven, manual, single-doc), and guardrails.

3. Verify the file was written: cat ${args.skillPath} | head -5
   Should show the YAML frontmatter.

Return confirmation.`,
      context: {},
      instructions: [
        'Copy skill definition exactly from plan',
        'Include YAML frontmatter',
        'Verify file was written',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['skillCreated'],
      properties: {
        skillCreated: { type: 'boolean' },
        frontmatterValid: { type: 'boolean' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task: Commit and push to dev
// ============================================================================

const commitAndPushTask = defineTask('commit-push', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Commit docs-sync files and push to dev',
  execution: { timeout: 120000 },
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Git workflow specialist',
      task: `Commit and push docs-sync project files to the dev branch.

Project root: ${args.projectRoot}
Current branch should be: dev

1. Verify we're on the dev branch:
   cd ${args.projectRoot} && git branch --show-current

2. Check what's changed:
   git status

3. Stage ONLY the project-level docs-sync files:
   git add docs-sync/topic-map.json .gitignore

   Also stage the spec and plan if they haven't been committed:
   git add docs/superpowers/specs/2026-04-13-docs-sync-hook-design.md
   git add docs/superpowers/plans/2026-04-13-docs-sync-implementation.md

4. Commit:
   git commit -m "feat: add docs-sync hook infrastructure — topic map, spec, and plan

   Adds post-commit hook support for detecting documentation drift:
   - docs-sync/topic-map.json maps 11 topic docs to code paths
   - Design spec and implementation plan in docs/superpowers/
   - Gitignore for ephemeral artifacts

   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"

5. Push:
   git push origin dev

Return the commit SHA.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Verify branch is dev before committing',
        'Only stage docs-sync and spec/plan files',
        'Do not stage .a5c or other unrelated files',
        'Return the commit SHA',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['committed', 'pushed', 'commitSha'],
      properties: {
        committed: { type: 'boolean' },
        pushed: { type: 'boolean' },
        commitSha: { type: 'string' },
        branch: { type: 'string' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task: Cherry-pick to main
// ============================================================================

const cherryPickTask = defineTask('cherry-pick', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Cherry-pick docs-sync commit to main',
  execution: { timeout: 120000 },
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Git workflow specialist',
      task: `Cherry-pick the docs-sync commit to the main branch.

Project root: ${args.projectRoot}
Commit to cherry-pick: the most recent commit on dev that starts with "feat: add docs-sync"

1. Get the exact commit SHA:
   cd ${args.projectRoot} && git log dev --oneline -5

2. Stash any uncommitted changes:
   git stash

3. Switch to main:
   git checkout main

4. Cherry-pick:
   git cherry-pick <sha>

5. Push:
   git push origin main

6. Switch back to dev:
   git checkout dev
   git stash pop (if stash was created)

Return confirmation with commit SHAs.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Identify the correct commit SHA first',
        'Stash before switching branches',
        'Push main after cherry-pick',
        'Return to dev branch',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['cherryPicked', 'mainPushed'],
      properties: {
        cherryPicked: { type: 'boolean' },
        mainPushed: { type: 'boolean' },
        devSha: { type: 'string' },
        mainSha: { type: 'string' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
