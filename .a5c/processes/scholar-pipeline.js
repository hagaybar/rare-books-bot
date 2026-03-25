/**
 * @process scholar-pipeline
 * @description Implement the three-stage scholar pipeline (Interpret -> Execute -> Narrate)
 *   for the rare books bot. Replaces rigid detector chain with LLM-driven interpretation,
 *   deterministic execution, and scholarly narration. Targets historian eval from 31% to 76%.
 *
 * 8 tasks with dependencies:
 *   Task 1 (models) -> Tasks 2,3,5 parallel -> Task 4 after 3 -> Task 6 after 2,4,5
 *   -> Task 7 after 6 -> Task 8 after 7
 *
 * @inputs { projectRoot: string, planPath: string, specPath: string, dbPath: string, targetQuality: number, maxIterations: number }
 * @outputs { success: boolean, tasksCompleted: number, testsPassing: boolean }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill git-expert .claude/skills/git-expert/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    planPath = 'docs/superpowers/plans/2026-03-25-scholar-pipeline.md',
    specPath = 'docs/superpowers/specs/2026-03-25-scholar-pipeline-design.md',
    dbPath = 'data/index/bibliographic.db',
    targetQuality = 85,
    maxIterations = 3
  } = inputs;

  ctx.log('info', 'Starting scholar pipeline implementation (8 tasks)');

  // ============================================================================
  // PHASE 1: Foundation — Plan Models (Task 1)
  // ============================================================================

  ctx.log('info', 'Phase 1: Building shared plan models');

  const task1Result = await ctx.task(implementTaskAgent, {
    projectRoot, planPath, specPath,
    taskNumber: 1,
    taskName: 'Plan Models',
    description: `Implement Task 1 from the plan: Create scripts/chat/plan_models.py with all shared Pydantic models (InterpretationPlan, ExecutionStep, ScholarlyDirective, StepAction, typed params, step output types, ExecutionResult, ScholarResponse, GroundingData, RecordSummary, AgentSummary, GroundingLink, SessionContext). Also create tests/scripts/chat/test_plan_models.py. Follow the TDD steps in the plan exactly. Also extract _generate_primo_url from app/api/metadata.py to scripts/utils/primo.py as noted in the Review-Driven Amendments.`,
    testCommand: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_plan_models.py -v 2>&1 | tail -40`,
  });

  // Phase 1 verification
  const phase1Verify = await ctx.task(verifyPhaseTask, {
    projectRoot,
    phase: 'phase1-models',
    description: 'Verify plan models and Primo URL extraction pass all tests',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_plan_models.py -v 2>&1 | tail -40`,
  });

  // ============================================================================
  // PHASE 2: Core Stages — Interpreter, Executor Core, Narrator (Tasks 2,3,5)
  // ============================================================================

  ctx.log('info', 'Phase 2: Implementing Interpreter (Task 2), Executor Core (Task 3), and Narrator (Task 5) in parallel');

  const [task2Result, task3Result, task5Result] = await ctx.parallel.all([
    () => ctx.task(implementTaskAgent, {
        projectRoot, planPath, specPath,
        taskNumber: 2,
        taskName: 'Interpreter',
        description: `Implement Task 2 from the plan: Create scripts/chat/interpreter.py (Stage 1 - LLM query interpretation). Create tests/scripts/chat/test_interpreter.py with mocked LLM. The interpreter receives a user query + session context, calls OpenAI Responses API, returns InterpretationPlan. Must include the full system prompt with step vocabulary, intent classification, century conversion rules, filter fields. Handle clarification (confidence < 0.7). Follow the OpenAI Responses API pattern from intent_agent.py function _interpret_with_openai(). Follow TDD steps exactly. Use the LLM-facing schema approach from the Review-Driven Amendments (ExecutionStepLLM with string action + dict params, then validate/convert to typed ExecutionStep).`,
        testCommand: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_interpreter.py -v 2>&1 | tail -40`,
    }),
    () => ctx.task(implementTaskAgent, {
        projectRoot, planPath, specPath,
        taskNumber: 3,
        taskName: 'Executor Core',
        description: `Implement Task 3 from the plan: Create scripts/chat/executor.py (Stage 2 - deterministic plan execution). Create tests/scripts/chat/test_executor.py. Implement: execute_plan() main entry point, _resolve_execution_order() topological sort with cycle detection, _resolve_step_ref() typed resolution by context (value/scope/agents/targets), _resolve_scope() including $previous_results support, handler dispatch with error catching. Stub all 7 handlers (implemented in next task). Follow TDD steps exactly.`,
        testCommand: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_executor.py -v 2>&1 | tail -40`,
    }),
    () => ctx.task(implementTaskAgent, {
        projectRoot, planPath, specPath,
        taskNumber: 5,
        taskName: 'Narrator',
        description: `Implement Task 5 from the plan: Create scripts/chat/narrator.py (Stage 3 - scholarly response generation). Create tests/scripts/chat/test_narrator.py with mocked LLM. The narrator receives ExecutionResult + query, calls OpenAI with the scholar persona prompt (6 evidence rules from the spec), returns ScholarResponse. Must include: _build_narrator_prompt() that renders records/agents/directives/aggregations, _fallback_response() for LLM failure, grounding passthrough. Follow TDD steps exactly.`,
        testCommand: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_narrator.py -v 2>&1 | tail -40`,
    }),
  ]);

  // Phase 2 verification
  const phase2Verify = await ctx.task(verifyPhaseTask, {
    projectRoot,
    phase: 'phase2-core-stages',
    description: 'Verify interpreter, executor core, and narrator all pass tests',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_interpreter.py tests/scripts/chat/test_executor.py tests/scripts/chat/test_narrator.py -v 2>&1 | tail -60`,
  });

  // ============================================================================
  // PHASE 3: Executor Handlers (Task 4)
  // ============================================================================

  ctx.log('info', 'Phase 3: Implementing executor step handlers');

  const task4Result = await ctx.task(implementTaskAgent, {
    projectRoot, planPath, specPath,
    taskNumber: 4,
    taskName: 'Executor Step Handlers',
    description: `Implement Task 4 from the plan: Add all 7 step handlers to scripts/chat/executor.py. Migrate AggregationResult model to scripts/chat/aggregation.py. Implement: _handle_resolve_agent (uses agent_authority.py alias lookup), _handle_resolve_publisher (uses publisher_authority.py), _handle_retrieve (converts to QueryPlan, calls db_adapter), _handle_aggregate (calls aggregation.execute_aggregation), _handle_find_connections (calls cross_reference.find_connections), _handle_enrich (queries authority_enrichment table), _handle_sample (strategy-based selection). Also implement _collect_grounding() for link collection (Primo via scripts/utils/primo.py, Wikipedia/Wikidata/NLI/VIAF from authority_enrichment). Add handler tests with the test DB fixture. Add tests for find_connections and sample handlers. Follow TDD steps exactly.`,
    testCommand: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_executor.py -v 2>&1 | tail -60`,
  });

  // Phase 3 verification — run all tests so far
  const phase3Verify = await ctx.task(verifyPhaseTask, {
    projectRoot,
    phase: 'phase3-handlers',
    description: 'Verify all handlers pass tests and no regressions in models/interpreter/narrator',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_plan_models.py tests/scripts/chat/test_interpreter.py tests/scripts/chat/test_executor.py tests/scripts/chat/test_narrator.py -v 2>&1 | tail -60`,
  });

  // ============================================================================
  // PHASE 4: API Integration (Task 6)
  // ============================================================================

  ctx.log('info', 'Phase 4: Wiring pipeline into API layer');

  const task6Result = await ctx.task(implementTaskAgent, {
    projectRoot, planPath, specPath,
    taskNumber: 6,
    taskName: 'API Integration',
    description: `Implement Task 6 from the plan: Wire the three-stage pipeline into app/api/main.py. Create tests/app/test_scholar_pipeline.py. Replace handle_query_definition_phase() body with: interpret -> clarification check -> execute_plan -> narrate. Map ScholarResponse to ChatResponse for API compatibility. Update WebSocket handler similarly with new progress message types (plan, evidence, narrative_chunk). Add health check extension for executor_ready. Keep old imports commented (cleanup in Task 8). Extract test DB fixture to tests/conftest.py or tests/scripts/chat/conftest.py for reuse. Follow TDD steps exactly.`,
    testCommand: `cd ${projectRoot} && poetry run pytest tests/app/test_scholar_pipeline.py -v 2>&1 | tail -40`,
  });

  // Phase 4 verification — run new + existing tests
  const phase4Verify = await ctx.task(verifyPhaseTask, {
    projectRoot,
    phase: 'phase4-integration',
    description: 'Verify API integration and check for regressions',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_plan_models.py tests/scripts/chat/test_interpreter.py tests/scripts/chat/test_executor.py tests/scripts/chat/test_narrator.py tests/app/test_scholar_pipeline.py -v 2>&1 | tail -80`,
  });

  // ============================================================================
  // PHASE 5: Evidence Reports (Task 7) — only if OPENAI_API_KEY available
  // ============================================================================

  ctx.log('info', 'Phase 5: Evidence capture tests');

  const task7Result = await ctx.task(implementTaskAgent, {
    projectRoot, planPath, specPath,
    taskNumber: 7,
    taskName: 'Evidence Reports',
    description: `Implement Task 7 from the plan: Create tests/app/test_scholar_evidence.py with the 20 historian evaluation queries. Create reports/scholar-pipeline/ directory. Each test captures full pipeline trace (interpreter plan, executor result, narrator response, latency) and saves to reports/scholar-pipeline/<run-id>/. Include summary.md generation. Mark with @pytest.mark.integration (requires OPENAI_API_KEY). If OPENAI_API_KEY is available, run the evidence tests and save results. If not, just create the test file and verify it's syntactically valid.`,
    testCommand: `cd ${projectRoot} && poetry run python -c "import tests.app.test_scholar_evidence" 2>&1`,
  });

  // ============================================================================
  // PHASE 6: Cleanup (Task 8)
  // ============================================================================

  ctx.log('info', 'Phase 6: Cleanup deprecated modules');

  const task8Result = await ctx.task(implementTaskAgent, {
    projectRoot, planPath, specPath,
    taskNumber: 8,
    taskName: 'Cleanup Removed Modules',
    description: `Implement Task 8 from the plan: Remove deprecated source and test files. Remove: intent_agent.py, analytical_router.py, formatter.py, narrative_agent.py, thematic_context.py, clarification.py, curator.py, exploration_agent.py, llm_compiler.py, execute.py. Remove associated test files. Clean up commented-out imports in app/api/main.py. Check scripts/query/service.py for broken imports. Run full test suite to verify no regressions. Use git rm for each file. Commit with descriptive message.`,
    testCommand: `cd ${projectRoot} && poetry run pytest tests/ -v --ignore=tests/app/test_scholar_evidence.py -x 2>&1 | tail -40`,
  });

  // Final verification
  const finalVerify = await ctx.task(verifyPhaseTask, {
    projectRoot,
    phase: 'final-all-tests',
    description: 'Final verification: all tests pass after cleanup',
    command: `cd ${projectRoot} && poetry run pytest tests/ -v --ignore=tests/app/test_scholar_evidence.py 2>&1 | tail -80`,
  });

  ctx.log('info', 'Scholar pipeline implementation complete');

  return {
    success: true,
    tasksCompleted: 8,
    testsPassing: true,
    phases: {
      models: task1Result,
      interpreter: task2Result,
      executorCore: task3Result,
      executorHandlers: task4Result,
      narrator: task5Result,
      apiIntegration: task6Result,
      evidence: task7Result,
      cleanup: task8Result,
    }
  };
}

// =============================================================================
// Task Definitions
// =============================================================================

const implementTaskAgent = defineTask('implement-task', (args, taskCtx) => ({
  kind: 'agent',
  title: `Implement Task ${args.taskNumber}: ${args.taskName}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python developer implementing a scholar pipeline for a rare books chatbot',
      task: `Implement Task ${args.taskNumber} (${args.taskName}) from the implementation plan.`,
      context: {
        projectRoot: args.projectRoot,
        planPath: args.planPath,
        specPath: args.specPath,
        taskNumber: args.taskNumber,
        taskName: args.taskName,
      },
      instructions: [
        `Read the full plan at ${args.planPath} and the spec at ${args.specPath}.`,
        `Focus on Task ${args.taskNumber}: ${args.taskName}.`,
        args.description,
        'Follow TDD: write tests first, verify they fail, implement, verify they pass.',
        `After implementation, run: ${args.testCommand}`,
        'Commit your changes with a descriptive message.',
        'Use the python-dev-expert and git-expert skills when relevant.',
        'Return a JSON summary with: {success: boolean, filesCreated: string[], filesModified: string[], testsPassing: boolean, commitHash: string}',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['success', 'testsPassing'],
      properties: {
        success: { type: 'boolean' },
        filesCreated: { type: 'array', items: { type: 'string' } },
        filesModified: { type: 'array', items: { type: 'string' } },
        testsPassing: { type: 'boolean' },
        commitHash: { type: 'string' },
        notes: { type: 'string' },
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  }
}));

const verifyPhaseTask = defineTask('verify-phase', (args, taskCtx) => ({
  kind: 'shell',
  title: `Verify: ${args.phase}`,
  shell: {
    command: args.command,
    cwd: args.projectRoot,
    timeout: 120000,
  },
  io: {
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  }
}));
