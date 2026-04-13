/**
 * @process docs-sync-plugin
 * @description Build a docs-sync Claude Code plugin packaging the existing hook+skill.
 * @inputs { pluginDir: string, existingHookPath: string, existingSkillPath: string, exampleTopicMapPath: string }
 * @outputs { success: boolean, pluginPath: string, filesCreated: array, verified: boolean }
 *
 * @skill skill-creator
 * @agent frontend-architect specializations/web-development/agents/frontend-architect/AGENT.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    pluginDir = '/home/hagaybar/.claude/plugins/local/docs-sync',
    existingHookPath = '/home/hagaybar/.claude/hooks/docs_sync_hook.py',
    existingSkillPath = '/home/hagaybar/.claude/skills/update-docs/SKILL.md',
    exampleTopicMapPath = '/home/hagaybar/projects/rare-books-bot/docs-sync/topic-map.json',
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
  } = inputs;
  const startTime = ctx.now();

  ctx.log('info', 'Starting docs-sync plugin build');

  // Phase 1: Research existing assets and Claude Code plugin structure
  const research = await ctx.task(researchPluginStructureTask, {
    pluginDir,
    existingHookPath,
    existingSkillPath,
    exampleTopicMapPath,
  });

  // Phase 2: Build the plugin — create all files
  const build = await ctx.task(buildPluginTask, {
    pluginDir,
    existingHookPath,
    existingSkillPath,
    exampleTopicMapPath,
    research,
  });

  // Phase 3: Register plugin in settings.json and verify
  const registration = await ctx.task(registerAndVerifyTask, {
    pluginDir,
    projectRoot,
  });

  // Phase 4: End-to-end test — make a commit and check the hook fires
  const e2eTest = await ctx.task(e2eTestTask, {
    pluginDir,
    projectRoot,
  });

  // Refinement if e2e fails
  if (!e2eTest.passed) {
    const fix = await ctx.task(fixPluginTask, {
      pluginDir,
      e2eResult: e2eTest,
      projectRoot,
    });

    const retest = await ctx.task(e2eTestTask, {
      pluginDir,
      projectRoot,
    });

    return {
      success: retest.passed,
      pluginPath: pluginDir,
      filesCreated: build.filesCreated || [],
      verified: retest.passed,
      duration: ctx.now() - startTime,
    };
  }

  return {
    success: true,
    pluginPath: pluginDir,
    filesCreated: build.filesCreated || [],
    verified: true,
    duration: ctx.now() - startTime,
  };
}

// ---- Task Definitions ----

export const researchPluginStructureTask = defineTask('research-plugin-structure', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Research Claude Code plugin structure and existing assets',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Claude Code plugin developer',
      task: `Research the Claude Code plugin structure and the existing docs-sync assets to plan the plugin build.

Do these steps:
1. Read the existing hook script at ${args.existingHookPath} — understand its full behavior
2. Read the existing skill at ${args.existingSkillPath} — understand all modes
3. Read the example topic map at ${args.exampleTopicMapPath}
4. Search online or in docs for Claude Code plugin structure requirements:
   - .claude-plugin/plugin.json manifest format
   - hooks/hooks.json format for auto-registering hooks
   - skills/ directory structure
   - How CLAUDE_PLUGIN_ROOT env var works in hooks
   - How plugins reference their own files

Return JSON with:
- hookScript: summary of what the hook does, key functions, dependencies
- skillDefinition: summary of skill modes and behavior
- pluginStructure: the exact directory tree needed
- manifestFormat: the plugin.json schema fields needed
- hooksJsonFormat: the hooks.json format for PostToolUse
- pathRewriting: what paths in the hook/skill need to change to use CLAUDE_PLUGIN_ROOT
- skillNamespacing: how the skill name will change (e.g., docs-sync:update-docs)`,
      context: {
        existingHookPath: args.existingHookPath,
        existingSkillPath: args.existingSkillPath,
        exampleTopicMapPath: args.exampleTopicMapPath,
        pluginDir: args.pluginDir,
      },
      instructions: [
        'Read each existing file fully to understand what needs to be adapted',
        'Pay attention to hardcoded paths that need to become relative to CLAUDE_PLUGIN_ROOT',
        'The hook script must work unchanged from the plugin directory — it auto-detects project root via git',
        'The skill SKILL.md may need minor path adjustments',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['pluginStructure', 'manifestFormat', 'hooksJsonFormat'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

export const buildPluginTask = defineTask('build-plugin', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Build the docs-sync plugin — create all files',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Claude Code plugin builder',
      task: `Build the docs-sync Claude Code plugin by creating all necessary files.

Research results:
${JSON.stringify(args.research, null, 2)}

Create the plugin at: ${args.pluginDir}

You MUST create these files (use Write/Edit tools):

1. **${args.pluginDir}/.claude-plugin/plugin.json** — Plugin manifest:
   \`\`\`json
   {
     "name": "docs-sync",
     "description": "Automatically detect documentation drift after commits and sync docs with code changes",
     "version": "1.0.0",
     "author": { "name": "Hagay Bar" }
   }
   \`\`\`

2. **${args.pluginDir}/hooks/hooks.json** — Hook registration:
   \`\`\`json
   {
     "hooks": {
       "PostToolUse": [
         {
           "matcher": "Bash",
           "hooks": [
             {
               "type": "command",
               "command": "python3 \${CLAUDE_PLUGIN_ROOT}/scripts/docs_sync_hook.py",
               "if": "Bash(git commit*)",
               "timeout": 10
             }
           ]
         }
       ]
     }
   }
   \`\`\`

3. **${args.pluginDir}/scripts/docs_sync_hook.py** — Copy from ${args.existingHookPath}. The script is already project-agnostic (finds project root via git), so it needs NO path changes.

4. **${args.pluginDir}/skills/update-docs/SKILL.md** — Copy from ${args.existingSkillPath}. Review and ensure it doesn't have hardcoded paths.

5. **${args.pluginDir}/templates/topic-map-template.json** — A starter template (not the project-specific one). Create a generic template with placeholder mappings and clear comments.

6. **${args.pluginDir}/README.md** — Brief usage doc explaining:
   - What the plugin does (hook detects doc drift, skill syncs docs)
   - How to install (enable in settings.json or marketplace)
   - How to bootstrap a project (/docs-sync:update-docs --init)
   - How to customize the topic map

After creating all files, verify each one exists by reading it.

Return JSON with:
- filesCreated: array of file paths created
- pluginReady: boolean`,
      context: {
        pluginDir: args.pluginDir,
        existingHookPath: args.existingHookPath,
        existingSkillPath: args.existingSkillPath,
      },
      instructions: [
        'Create directories before writing files',
        'Copy the hook script as-is — it is already project-agnostic',
        'The skill SKILL.md should work without modification',
        'Create a generic topic-map template, NOT a project-specific one',
        'The README should be concise — not a wall of text',
        'Verify all files exist after creation',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['filesCreated', 'pluginReady'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

export const registerAndVerifyTask = defineTask('register-and-verify', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Register plugin in settings.json and verify structure',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Claude Code plugin installer',
      task: `Register the docs-sync plugin in Claude Code settings and verify the structure.

Plugin directory: ${args.pluginDir}

Steps:
1. Read the current ~/.claude/settings.json
2. Add the plugin to extraKnownMarketplaces and enabledPlugins using the local directory source format:
   - In extraKnownMarketplaces, add a "docs-sync-local" entry with source type "directory" pointing to ${args.pluginDir}
   - In enabledPlugins, add "docs-sync@docs-sync-local": true
3. Verify the plugin structure by checking all required files exist:
   - .claude-plugin/plugin.json
   - hooks/hooks.json
   - scripts/docs_sync_hook.py
   - skills/update-docs/SKILL.md
4. Run a basic validation: parse plugin.json and hooks.json as valid JSON

IMPORTANT: Read settings.json BEFORE editing. Make targeted edits only. Do NOT break existing settings.

Return JSON with:
- registered: boolean
- structureValid: boolean
- settingsUpdated: boolean
- issues: array of any problems found`,
      context: {
        pluginDir: args.pluginDir,
        projectRoot: args.projectRoot,
      },
      instructions: [
        'Read settings.json before editing',
        'Use Edit tool for targeted changes',
        'Do not remove or modify existing settings entries',
        'Validate JSON files parse correctly',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['registered', 'structureValid'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

export const e2eTestTask = defineTask('e2e-test', (args, taskCtx) => ({
  kind: 'agent',
  title: 'End-to-end test: verify hook fires on commit',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Plugin QA tester',
      task: `Verify the docs-sync plugin works end-to-end.

Plugin directory: ${args.pluginDir}
Project: ${args.projectRoot}

Verification steps:
1. Verify plugin files exist and are valid:
   - ${args.pluginDir}/.claude-plugin/plugin.json — valid JSON
   - ${args.pluginDir}/hooks/hooks.json — valid JSON with PostToolUse entry
   - ${args.pluginDir}/scripts/docs_sync_hook.py — executable Python
   - ${args.pluginDir}/skills/update-docs/SKILL.md — valid SKILL.md with frontmatter
2. Test the hook script directly by running it from the project directory:
   cd ${args.projectRoot} && python3 ${args.pluginDir}/scripts/docs_sync_hook.py
   (This should detect the most recent commit and output a summary)
3. Verify the topic map exists at ${args.projectRoot}/docs-sync/topic-map.json
4. Check that a new artifact was created in ${args.projectRoot}/docs-sync/artifacts/
5. Verify the skill file has valid frontmatter (name and description in YAML header)
6. Verify the hooks.json matcher pattern "Bash(git commit*)" is correct

Return JSON with:
- passed: boolean
- checks: array of {name, passed, details}
- issues: array of remaining problems`,
      context: {
        pluginDir: args.pluginDir,
        projectRoot: args.projectRoot,
      },
      instructions: [
        'Run the hook script manually to test it works',
        'Check file permissions',
        'Validate JSON/YAML parsing',
        'Report specific failure details',
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

export const fixPluginTask = defineTask('fix-plugin', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Fix plugin issues from e2e test',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Plugin developer fixing issues',
      task: `Fix issues found during e2e testing of the docs-sync plugin.

E2E test results:
${JSON.stringify(args.e2eResult, null, 2)}

Plugin directory: ${args.pluginDir}

Read the failing files, diagnose the problems, and fix them.

Return JSON with:
- fixed: boolean
- changes: array of {file, description}`,
      context: {
        pluginDir: args.pluginDir,
        projectRoot: args.projectRoot,
      },
      instructions: [
        'Read files before editing',
        'Make minimal targeted fixes',
        'Verify fixes by re-reading files',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['fixed', 'changes'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
