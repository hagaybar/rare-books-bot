/**
 * @process fix-deprecated-apis
 * @description Migrate deprecated Pydantic Config and FastAPI on_event APIs
 *
 * @inputs { projectRoot: string }
 * @outputs { success: boolean, filesModified: array }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;

  ctx.log('info', 'Fixing deprecated APIs');

  // Two independent fixes in parallel
  const [pydanticFix, fastapiFix] = await ctx.parallel.all([
    () => ctx.task(fixPydanticConfigTask, { projectRoot }),
    () => ctx.task(fixFastapiLifespanTask, { projectRoot }),
  ]);

  // Verify
  const verify = await ctx.task(verifyTask, { projectRoot });

  return {
    success: true,
    pydanticFix,
    fastapiFix,
    verify,
  };
}

export const fixPydanticConfigTask = defineTask('fix-pydantic-config', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Migrate Pydantic class Config to ConfigDict',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer migrating Pydantic v1 patterns to v2',
      task: `Migrate class-based Config to model_config = ConfigDict() in scripts/marc/models.py.

Steps:
1. Read scripts/marc/models.py
2. Find all classes using "class Config:" inside Pydantic models (around lines 100 and 246)
3. Replace each with model_config = ConfigDict(...) using the equivalent settings
4. Add "from pydantic import ConfigDict" to imports if not present
5. Remove the old class Config blocks
6. Run: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/scripts/marc/ -v --tb=short 2>&1 | tail -15
7. Verify no PydanticDeprecatedSince20 warnings about class Config remain

Common migrations:
- class Config: json_encoders = {...} → model_config = ConfigDict(json_encoders={...})  [note: json_encoders is also deprecated, but handle one thing at a time]
- class Config: arbitrary_types_allowed = True → model_config = ConfigDict(arbitrary_types_allowed=True)

Return JSON: {"filesModified": [...], "summary": "..."}`,
      context: { projectRoot: args.projectRoot },
      instructions: ['Read file first', 'Migrate Config to ConfigDict', 'Run tests', 'Return summary'],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
}));

export const fixFastapiLifespanTask = defineTask('fix-fastapi-lifespan', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Migrate FastAPI on_event to lifespan handler',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer migrating FastAPI deprecated patterns',
      task: `Migrate @app.on_event("startup") and @app.on_event("shutdown") to a lifespan context manager in app/api/main.py.

Steps:
1. Read app/api/main.py, find all @app.on_event decorators
2. Create a lifespan async context manager that replaces them:
   - Code before "yield" runs on startup
   - Code after "yield" runs on shutdown
3. Pass the lifespan to the FastAPI constructor: app = FastAPI(..., lifespan=lifespan)
4. Remove the old @app.on_event decorated functions
5. Add "from contextlib import asynccontextmanager" if not present
6. Run: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/app/test_api.py -v --tb=short 2>&1 | tail -15
7. Verify no DeprecationWarning about on_event remains

Example pattern:
  from contextlib import asynccontextmanager

  @asynccontextmanager
  async def lifespan(app):
      # startup code here
      yield
      # shutdown code here

  app = FastAPI(lifespan=lifespan)

Return JSON: {"filesModified": [...], "summary": "..."}`,
      context: { projectRoot: args.projectRoot },
      instructions: ['Read file first', 'Migrate on_event to lifespan', 'Run tests', 'Return summary'],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
}));

export const verifyTask = defineTask('verify-no-deprecations', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Verify no deprecation warnings remain',
  shell: {
    command: 'cd /home/hagaybar/projects/rare-books-bot && poetry run pytest --tb=short -q 2>&1 | tail -10',
  },
}));
