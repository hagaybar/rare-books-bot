/**
 * @process model-evaluation
 * @description Implement model evaluation & cost optimization infrastructure — LiteLLM migration, config, batch eval, UI compare
 * @inputs { planPath: string, specPath: string, branch: string }
 * @outputs { success: boolean, phases: object, artifacts: array }
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    planPath = 'docs/superpowers/plans/2026-04-03-model-evaluation.md',
    specPath = 'docs/superpowers/specs/2026-04-03-model-evaluation-design.md',
    branch = 'feature/model-evaluation',
  } = inputs;

  const artifacts = [];
  ctx.log('info', 'Starting Model Evaluation implementation — 5 phases, 12 tasks');

  // ============================================================================
  // PHASE 1: INFRASTRUCTURE
  // ============================================================================

  ctx.log('info', 'Phase 1: Infrastructure — config module + LLM client wrapper');

  const configModule = await ctx.task(buildConfigModuleTask, { planPath, specPath });
  artifacts.push('scripts/models/config.py', 'tests/test_models_config.py');

  const llmClient = await ctx.task(buildLlmClientTask, { planPath, specPath });
  artifacts.push('scripts/models/llm_client.py', 'tests/test_llm_client.py');

  const runTestsPhase1 = await ctx.task(runTestsShellTask, {
    label: 'Phase 1 tests',
    command: 'cd /home/hagaybar/projects/rare-books-bot && python3 -m pytest tests/test_models_config.py tests/test_llm_client.py -v --timeout=30 2>&1 | tail -30',
  });

  const commitPhase1 = await ctx.task(commitShellTask, {
    label: 'Commit Phase 1',
    command: 'cd /home/hagaybar/projects/rare-books-bot && git add scripts/models/ tests/test_models_config.py tests/test_llm_client.py data/eval/model-config.json pyproject.toml && git commit -m "feat: add model config module and LLM client wrapper (litellm)"',
  });

  // ============================================================================
  // PHASE 2: MIGRATION
  // ============================================================================

  ctx.log('info', 'Phase 2: Migrate interpreter, narrator, cost tracking, legacy compiler, agent harness');

  const migrateInterpreter = await ctx.task(migrateInterpreterTask, { planPath, specPath });
  const migrateNarrator = await ctx.task(migrateNarratorTask, { planPath, specPath });
  const migrateCostTracking = await ctx.task(migrateCostTrackingTask, { planPath, specPath });
  const migrateLegacy = await ctx.task(migrateLegacyTask, { planPath, specPath });

  const runTestsPhase2 = await ctx.task(runTestsShellTask, {
    label: 'Phase 2 regression tests',
    command: 'cd /home/hagaybar/projects/rare-books-bot && python3 -m pytest tests/ -v --timeout=60 2>&1 | tail -40',
  });

  const commitPhase2 = await ctx.task(commitShellTask, {
    label: 'Commit Phase 2',
    command: 'cd /home/hagaybar/projects/rare-books-bot && git add scripts/chat/interpreter.py scripts/chat/narrator.py scripts/utils/llm_logger.py scripts/query/llm_compiler.py scripts/metadata/agent_harness.py && git commit -m "refactor: migrate all LLM calls from OpenAI Responses API to litellm"',
  });

  // ============================================================================
  // PHASE 3: EVALUATION FRAMEWORK
  // ============================================================================

  ctx.log('info', 'Phase 3: Build evaluation framework — query set, judge, report, CLI');

  const buildEvalFramework = await ctx.task(buildEvalFrameworkTask, { planPath, specPath });
  artifacts.push('scripts/eval/', 'data/eval/queries.json');

  const runTestsPhase3 = await ctx.task(runTestsShellTask, {
    label: 'Phase 3 eval tests',
    command: 'cd /home/hagaybar/projects/rare-books-bot && python3 -m pytest tests/test_eval_query_set.py tests/test_eval_judge.py -v --timeout=30 2>&1 | tail -30',
  });

  const commitPhase3 = await ctx.task(commitShellTask, {
    label: 'Commit Phase 3',
    command: 'cd /home/hagaybar/projects/rare-books-bot && git add scripts/eval/ tests/test_eval_query_set.py tests/test_eval_judge.py data/eval/queries.json && git commit -m "feat: add batch evaluation framework with LLM-as-judge scoring"',
  });

  // ============================================================================
  // PHASE 4: UI COMPARISON MODE
  // ============================================================================

  ctx.log('info', 'Phase 4: Build compare API endpoint and frontend components');

  const buildCompareApi = await ctx.task(buildCompareApiTask, { planPath, specPath });
  artifacts.push('app/api/compare.py');

  const buildFrontend = await ctx.task(buildFrontendCompareTask, { planPath, specPath });
  artifacts.push('frontend/src/components/CompareMode.tsx', 'frontend/src/components/ModelSelector.tsx');

  const buildFrontendShell = await ctx.task(runTestsShellTask, {
    label: 'Frontend build check',
    command: 'cd /home/hagaybar/projects/rare-books-bot/frontend && npm run build 2>&1 | tail -20',
  });

  const commitPhase4 = await ctx.task(commitShellTask, {
    label: 'Commit Phase 4',
    command: 'cd /home/hagaybar/projects/rare-books-bot && git add app/api/compare.py app/api/models.py app/api/main.py frontend/src/ && git commit -m "feat: add /chat/compare endpoint and frontend compare mode"',
  });

  // ============================================================================
  // PHASE 5: INTEGRATION & VERIFICATION
  // ============================================================================

  ctx.log('info', 'Phase 5: End-to-end verification and documentation');

  // Breakpoint: approve running API calls for integration test
  await ctx.breakpoint({
    question: 'All code is written. Ready to run end-to-end verification which will make LLM API calls (costs tokens). Approve?',
    title: 'Approve Integration Test (API Costs)',
    context: { phases_complete: 4, branch },
  });

  const integrationVerify = await ctx.task(integrationVerifyTask, { planPath, specPath });

  const updateDocs = await ctx.task(updateDocsTask, { planPath, specPath });
  artifacts.push('docs/current/architecture.md', 'CLAUDE.md');

  const commitPhase5 = await ctx.task(commitShellTask, {
    label: 'Commit Phase 5',
    command: 'cd /home/hagaybar/projects/rare-books-bot && git add -A && git commit -m "feat: integration verification + documentation updates for model evaluation"',
  });

  // ============================================================================
  // COMPLETION
  // ============================================================================

  ctx.log('info', 'Model Evaluation implementation complete');
  return { success: true, artifacts, metadata: { branch, processId: 'model-evaluation' } };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

const buildConfigModuleTask = defineTask('build-config-module', (args) => ({
  kind: 'agent',
  title: 'Task 1: Create config module + update litellm dependency',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer implementing model configuration',
      task: `Implement Task 1 from the plan at ${args.planPath}. You MUST:

1. Read the plan file first to get the exact code for Task 1
2. Update pyproject.toml: change litellm pin from >=1.73.0 to >=1.81.9
3. Create scripts/models/__init__.py
4. Create scripts/models/config.py with ModelConfig, StageConfig, load_config(), get_model() — exact code is in the plan
5. Create data/eval/model-config.json with the default config
6. Create tests/test_models_config.py with the 4 tests from the plan
7. Run the tests with: python3 -m pytest tests/test_models_config.py -v
8. Fix any issues until all tests pass

Return summary of files created and test results.`,
      instructions: [
        'Read the plan file for exact code',
        'Create all files exactly as specified',
        'Run tests and fix any failures',
        'Return summary only'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const buildLlmClientTask = defineTask('build-llm-client', (args) => ({
  kind: 'agent',
  title: 'Task 2: Build LLM client wrapper around litellm',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer building LLM abstraction layer',
      task: `Implement Task 2 from the plan at ${args.planPath}. You MUST:

1. Read the plan file for the exact code
2. Create scripts/models/llm_client.py with LLMResult, pydantic_to_response_format(), structured_completion(), streaming_completion() — exact code is in the plan
3. Create tests/test_llm_client.py with the 3 tests from the plan
4. Run tests: python3 -m pytest tests/test_llm_client.py -v
5. Fix any issues until all tests pass

Return summary of files created and test results.`,
      instructions: [
        'Read the plan for exact code',
        'Create all files exactly as specified',
        'Run tests and fix failures',
        'Return summary only'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const migrateInterpreterTask = defineTask('migrate-interpreter', (args) => ({
  kind: 'agent',
  title: 'Task 3: Migrate interpreter.py from OpenAI to litellm',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer performing API migration',
      task: `Implement Task 3 from the plan at ${args.planPath}. You MUST:

1. Read the plan for exact changes
2. Read scripts/chat/interpreter.py to understand current code
3. Replace 'from openai import OpenAI' with imports from scripts.models.llm_client and scripts.models.config
4. Rewrite _call_llm() to use structured_completion() — exact code in plan
5. Update interpret() signature to use Optional[str] model with config-based default — exact code in plan
6. Remove unused OpenAI import
7. Run existing tests: python3 -m pytest tests/ -k "interpret" -v --timeout=30
8. Fix any regressions

IMPORTANT: Keep all existing logic (system prompts, _convert_llm_plan, _validate_step_refs) unchanged. Only change the LLM call layer.

Return summary of changes and test results.`,
      instructions: [
        'Read plan and current interpreter.py',
        'Make minimal changes per plan',
        'Preserve all existing logic',
        'Run tests and fix regressions'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const migrateNarratorTask = defineTask('migrate-narrator', (args) => ({
  kind: 'agent',
  title: 'Task 4: Migrate narrator.py from OpenAI to litellm',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer performing API migration',
      task: `Implement Task 4 from the plan at ${args.planPath}. You MUST:

1. Read the plan for exact changes
2. Read scripts/chat/narrator.py to understand all 4 LLM call sites
3. Replace 'from openai import OpenAI' with imports from scripts.models.llm_client and scripts.models.config
4. Rewrite _call_llm() for sync narration — exact code in plan
5. Rewrite _stream_llm() for streaming — use streaming_completion() with async for
6. Rewrite _extract_streaming_meta() — make it async, use structured_completion()
7. Update narrate() and narrate_streaming() to use config-based default model
8. CRITICAL: Check if _extract_streaming_meta becoming async breaks any callers — add await where needed
9. Run tests: python3 -m pytest tests/ -k "narrat" -v --timeout=30
10. Fix any regressions

IMPORTANT: Keep NarratorResponseLLM, StreamingMetaLLM, system prompts, prompt builders unchanged.

Return summary of changes and test results.`,
      instructions: [
        'Read plan and current narrator.py',
        'Migrate all 4 call sites',
        'Handle async change carefully',
        'Run tests and fix regressions'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const migrateCostTrackingTask = defineTask('migrate-cost-tracking', (args) => ({
  kind: 'agent',
  title: 'Task 5: Migrate cost tracking to litellm.completion_cost()',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer updating cost tracking',
      task: `Implement Task 5 from the plan at ${args.planPath}. You MUST:

1. Read the plan for exact changes
2. Read scripts/utils/llm_logger.py
3. Update _calculate_cost() to use litellm.completion_cost() with fallback to litellm.cost_per_token()
4. Comment out PRICING_PER_1M_TOKENS dict with deprecation note
5. Update log_llm_call() to pass response object to _calculate_cost()
6. Run tests: python3 -m pytest tests/ -k "logger" -v --timeout=30

Return summary of changes.`,
      instructions: [
        'Read plan and current llm_logger.py',
        'Make changes per plan',
        'Keep JSONL logging and token accumulator unchanged',
        'Run tests'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const migrateLegacyTask = defineTask('migrate-legacy', (args) => ({
  kind: 'agent',
  title: 'Task 6: Migrate legacy compiler + agent harness',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer performing API migration',
      task: `Implement Task 6 from the plan at ${args.planPath}. You MUST:

1. Read the plan for exact changes
2. Migrate scripts/query/llm_compiler.py: replace OpenAI client with structured_completion(). Note: call_model becomes async — update callers.
3. Migrate scripts/metadata/agent_harness.py: replace lazy OpenAI client with litellm calls via structured_completion()
4. Run full test suite: python3 -m pytest tests/ -v --timeout=60
5. Fix any regressions

These are lower-priority files but must work correctly.

Return summary of changes and test results.`,
      instructions: [
        'Read plan and both files',
        'Migrate both to litellm',
        'Handle sync-to-async changes',
        'Run full test suite'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const buildEvalFrameworkTask = defineTask('build-eval-framework', (args) => ({
  kind: 'agent',
  title: 'Tasks 7-9: Build complete evaluation framework (query set, judge, report, CLI)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer building an evaluation framework for LLM comparison',
      task: `Implement Tasks 7, 8, and 9 from the plan at ${args.planPath}. You MUST:

**Task 7: Query Set Module**
1. Create scripts/eval/__init__.py
2. Create scripts/eval/query_set.py with EvalQuery, load_query_set(), validate_query_set() — exact code in plan
3. Create tests/test_eval_query_set.py with the 3 tests from plan
4. Create data/eval/queries.json with 20-30 curated queries covering all intent types and difficulty levels. Query the database at data/index/bibliographic.db to craft realistic queries using actual publishers, agents, places, and dates in the collection.

**Task 8: Judge Module**
5. Create scripts/eval/judge.py with InterpreterScore, NarratorScore, score_interpreter(), score_narrator(), _compute_filter_overlap() — exact code in plan
6. Create tests/test_eval_judge.py with the 4 tests from plan

**Task 9: Report & CLI**
7. Create scripts/eval/report.py with generate_report(), _aggregate_scores(), etc. — exact code in plan
8. Create scripts/eval/run_eval.py with the batch evaluation CLI — exact code in plan
9. Verify CLI: python3 scripts/eval/run_eval.py --help

10. Run all eval tests: python3 -m pytest tests/test_eval_query_set.py tests/test_eval_judge.py -v
11. Fix any failures

IMPORTANT for queries.json: Query the actual database to find real publishers (daniel bomberg, christophe plantin, etc.), agents (elijah levita, maimonides, etc.), places (venice, amsterdam, etc.), and date ranges. Include queries for all intent types: retrieval, entity_exploration, analytical, comparison, curation, topical, follow_up, overview.

Return summary of all files created and test results.`,
      instructions: [
        'Read plan for all 3 tasks',
        'Query the DB for realistic test queries',
        'Create all files with exact code from plan',
        'Run tests and fix failures'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const buildCompareApiTask = defineTask('build-compare-api', (args) => ({
  kind: 'agent',
  title: 'Task 10: Build /chat/compare API endpoint',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python FastAPI developer',
      task: `Implement Task 10 from the plan at ${args.planPath}. You MUST:

1. Read the plan for exact code
2. Add CompareRequest, CompareResponse, ModelPair, ComparisonResult, ComparisonMetrics models to app/api/models.py — exact code in plan
3. Create app/api/compare.py with run_comparison() and _run_pipeline_with_config() — exact code in plan
4. Wire the /chat/compare endpoint into app/api/main.py:
   - Add imports for run_comparison, CompareRequest, CompareResponse
   - Add the POST /chat/compare route (admin/full role only)
5. Read the current app/api/main.py to understand the import patterns and route structure before adding

Return summary of changes.`,
      instructions: [
        'Read plan and current app/api files',
        'Add models to models.py',
        'Create compare.py',
        'Wire route into main.py',
        'Follow existing patterns'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const buildFrontendCompareTask = defineTask('build-frontend-compare', (args) => ({
  kind: 'agent',
  title: 'Task 11: Build frontend compare mode components',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'React/TypeScript frontend developer',
      task: `Implement Task 11 from the plan at ${args.planPath}. You MUST:

1. Read the plan for TypeScript types and component descriptions
2. Read the existing frontend structure: ls frontend/src/components/ and frontend/src/types/
3. Read frontend/src/types/chat.ts to understand existing types
4. Read the main app component to understand routing and layout

5. Add to frontend/src/types/chat.ts: ModelPair, CompareRequest, ComparisonMetrics, ComparisonResult, CompareResponse, AVAILABLE_MODELS — exact types from plan

6. Create frontend/src/components/ModelSelector.tsx:
   - Dropdown pairs (interpreter model + narrator model)
   - "Add Configuration" button (max 3)
   - Remove button per row
   - Calls back with ModelPair[]

7. Create frontend/src/components/CompareMode.tsx:
   - Uses ModelSelector
   - Query input field
   - "Compare" button that POSTs to /chat/compare
   - Side-by-side result cards showing: narrative (markdown rendered), latency, cost, tokens
   - 1-5 star rating on each card
   - Loading state while comparing

8. Wire into the app: Add a "Compare" toggle button visible only to admin/full users. When active, show CompareMode instead of normal chat.

9. Build: cd frontend && npm run build
10. Fix any TypeScript errors

IMPORTANT: Follow the existing component patterns, styling, and auth patterns in the codebase.

Return summary of components created and build result.`,
      instructions: [
        'Read existing frontend structure first',
        'Follow existing component patterns',
        'Add types, create components, wire into app',
        'Build and fix errors'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const integrationVerifyTask = defineTask('integration-verify', (args) => ({
  kind: 'agent',
  title: 'Task 12: End-to-end integration verification',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer verifying full-stack integration',
      task: `Implement Task 12 from the plan at ${args.planPath}. You MUST:

1. Verify default config works (no behavior change):
   python3 -c "
   import asyncio
   from scripts.chat.interpreter import interpret
   plan = asyncio.run(interpret('Books printed in Venice'))
   print(f'Intents: {plan.intents}')
   print(f'Steps: {len(plan.execution_steps)}')
   print(f'Confidence: {plan.confidence}')
   "

2. Run full test suite: python3 -m pytest tests/ -v --timeout=60

3. Verify eval CLI help works: python3 scripts/eval/run_eval.py --help

4. Fix any failures discovered

Return summary of verification results.`,
      instructions: [
        'Run the verification commands',
        'Fix any issues found',
        'Report all results'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const updateDocsTask = defineTask('update-docs', (args) => ({
  kind: 'agent',
  title: 'Update architecture docs and CLAUDE.md',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical writer updating project documentation',
      task: `Update documentation for the model evaluation feature:

1. Read docs/current/architecture.md and add a section about the model config system (scripts/models/)
2. Read CLAUDE.md and:
   - Add to Common Commands: the eval CLI command
   - Add to Directory Conventions: data/eval/ description
3. Read the spec at ${args.specPath} to ensure docs accurately reflect what was built

Return summary of documentation changes.`,
      instructions: [
        'Read current docs',
        'Add model evaluation sections',
        'Keep changes minimal and accurate'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

// Shell task helpers

const runTestsShellTask = defineTask('run-tests', (args) => ({
  kind: 'shell',
  title: args.label || 'Run tests',
  shell: { command: args.command, timeout: 120000 },
}));

const commitShellTask = defineTask('commit-changes', (args) => ({
  kind: 'shell',
  title: args.label || 'Commit changes',
  shell: { command: args.command, timeout: 30000 },
}));
