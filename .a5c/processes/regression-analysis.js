/**
 * @process regression-analysis
 * @description Analyze chat pipeline regression between main (d1ecb1b) and dev (26bc311) — evidence-based root cause analysis
 * @inputs { projectRoot: string, mainCommit: string, devCommit: string, testQuery: string, serverHost: string, sshKey: string, serverLogsPath: string, changedFiles: string[], symptom: string }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill systematic-debugging .superpowers/skills/systematic-debugging/SKILL.md
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    mainCommit = 'd1ecb1b',
    devCommit = '26bc311',
    testQuery = 'ספרים בשפה העברית שהודפסו באמסטרדם',
    serverHost = 'rarebooks@151.145.90.19',
    sshKey = '~/.ssh/rarebooks_a1',
    serverLogsPath = '~/rare-books-data/logs/llm_calls.jsonl',
    changedFiles = [],
    symptom = '',
  } = inputs;

  // ============================================================================
  // PHASE 1: Gather all evidence from server logs
  // ============================================================================

  ctx.log('info', 'Phase 1: Gather complete server log evidence');

  const logEvidence = await ctx.task(gatherLogsTask, {
    projectRoot,
    serverHost,
    sshKey,
    serverLogsPath,
    testQuery,
  });

  ctx.log('info', `Log evidence gathered: ${JSON.stringify(logEvidence).slice(0, 500)}`);

  // ============================================================================
  // PHASE 2: Analyze code diff — trace every change path
  // ============================================================================

  ctx.log('info', 'Phase 2: Analyze code diff between main and dev');

  const diffAnalysis = await ctx.task(analyzeDiffTask, {
    projectRoot,
    mainCommit,
    devCommit,
    changedFiles,
    symptom,
    logEvidence: JSON.stringify(logEvidence).slice(0, 2000),
  });

  ctx.log('info', `Diff analysis: ${JSON.stringify(diffAnalysis).slice(0, 500)}`);

  // ============================================================================
  // PHASE 3: Trace the execution path — what happens when interpreter returns {}
  // ============================================================================

  ctx.log('info', 'Phase 3: Trace execution path for empty interpreter response');

  const pathTrace = await ctx.task(traceExecutionPathTask, {
    projectRoot,
    devCommit,
    symptom,
    logEvidence: JSON.stringify(logEvidence).slice(0, 2000),
    diffAnalysis: JSON.stringify(diffAnalysis).slice(0, 2000),
  });

  ctx.log('info', `Path trace: ${JSON.stringify(pathTrace).slice(0, 500)}`);

  // ============================================================================
  // PHASE 4: Synthesize findings into evidence-based report
  // ============================================================================

  ctx.log('info', 'Phase 4: Synthesize evidence-based regression report');

  const report = await ctx.task(synthesizeReportTask, {
    projectRoot,
    mainCommit,
    devCommit,
    testQuery,
    symptom,
    logEvidence: JSON.stringify(logEvidence).slice(0, 3000),
    diffAnalysis: JSON.stringify(diffAnalysis).slice(0, 3000),
    pathTrace: JSON.stringify(pathTrace).slice(0, 3000),
  });

  ctx.log('info', `Report synthesized`);

  // ============================================================================
  // BREAKPOINT: Present report for user review
  // ============================================================================

  await ctx.breakpoint({
    question: 'Regression analysis report is ready. Review the report at .a5c/runs/*/artifacts/regression-report.md. Approve to finalize?',
    title: 'Regression Analysis Report Review',
    options: ['Approve report', 'Request deeper investigation'],
  });

  return {
    success: true,
    reportPath: 'artifacts/regression-report.md',
    logEvidence,
    diffAnalysis,
    pathTrace,
    report,
  };
}

// ============================================================================
// Task: Gather complete server log evidence
// ============================================================================

const gatherLogsTask = defineTask('gather-logs', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Gather server log evidence for regression analysis',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Log forensics analyst',
      task: `Gather ALL relevant log evidence from the production server for the chat pipeline regression.

The server has logs at ${args.serverHost}:${args.serverLogsPath}
SSH key: ${args.sshKey}

DO THE FOLLOWING (execute commands, don't just plan):

1. Fetch the COMPLETE last 10 entries from llm_calls.jsonl (not just last 3). For each entry extract:
   - timestamp, call_type, model
   - The FULL user prompt (not truncated)
   - The FULL response content (not truncated)
   - Any error fields

2. Fetch the app.api.main.log — look for errors, warnings, tracebacks around the same timestamps

3. Fetch the llm_logger.log — look for any parsing errors or validation failures

4. Fetch workbench_interactions.jsonl — check if there were other interactions that worked/failed

5. Check the sessions.db for the session that produced the regression query:
   ssh -i ${args.sshKey} ${args.serverHost} "docker exec rare-books python3 -c \\"
   import sqlite3; conn = sqlite3.connect('/app/data/chat/sessions.db');
   rows = conn.execute('SELECT * FROM messages ORDER BY created_at DESC LIMIT 5').fetchall();
   print([dict(zip([d[0] for d in conn.execute(\\\"SELECT * FROM messages LIMIT 0\\\").description], r)) for r in rows])
   \\""

IMPORTANT: Actually execute SSH commands and return the real data. Do NOT make up or assume log contents.

Return a structured JSON with all findings.`,
      context: {
        serverHost: args.serverHost,
        sshKey: args.sshKey,
        serverLogsPath: args.serverLogsPath,
        testQuery: args.testQuery,
      },
      instructions: [
        'Execute all SSH commands to gather real log data',
        'Do not truncate responses — capture full content',
        'Return structured JSON with all evidence',
        'If a command fails, report the error and try alternative approaches',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['llmCalls', 'appLog', 'llmLoggerLog'],
      properties: {
        llmCalls: { type: 'array', description: 'All LLM call log entries' },
        appLog: { type: 'string', description: 'Relevant app log entries' },
        llmLoggerLog: { type: 'string', description: 'LLM logger entries' },
        workbenchInteractions: { type: 'array', description: 'Workbench interaction entries' },
        sessionMessages: { type: 'array', description: 'Recent session messages' },
        errors: { type: 'array', description: 'Any errors encountered during gathering' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task: Analyze code diff between main and dev
// ============================================================================

const analyzeDiffTask = defineTask('analyze-diff', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Analyze code differences that could cause regression',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Code forensics analyst specializing in Python backend pipelines',
      task: `Analyze the code differences between main (${args.mainCommit}) and dev (${args.devCommit}) to identify what caused this regression:

SYMPTOM: ${args.symptom}

LOG EVIDENCE: ${args.logEvidence}

DO THE FOLLOWING (execute commands and read files, don't just plan):

1. Run: git diff ${args.mainCommit} ${args.devCommit} -- scripts/chat/executor.py scripts/chat/narrator.py scripts/chat/plan_models.py app/api/main.py

2. For EACH changed file, read BOTH the main and dev versions of the critical functions:
   - git show ${args.mainCommit}:scripts/chat/narrator.py | focus on build_lean_narrator_prompt and _build_narrator_prompt
   - git show ${args.devCommit}:scripts/chat/narrator.py | same functions
   - git show ${args.mainCommit}:scripts/chat/executor.py | focus on _collect_grounding and execute_plan
   - git show ${args.devCommit}:scripts/chat/executor.py | same functions
   - git show ${args.mainCommit}:app/api/main.py | focus on websocket_chat handler
   - git show ${args.devCommit}:app/api/main.py | same handler

3. For each change, classify it:
   - SAFE: purely additive, cannot break existing paths
   - RISKY: modifies existing logic, could alter behavior
   - BREAKING: changes function signatures, return types, or control flow

4. Pay special attention to:
   - The interpreter call and response parsing — does any dev change affect how {} is handled?
   - The narrator call — is narrator_meta (gpt-4.1-nano) a new code path in dev?
   - The WebSocket message flow — do the new "stage" fields affect anything?
   - Error handling differences — are exceptions swallowed differently?

5. Check if narrator_meta is a NEW call type that only exists in dev:
   git show ${args.mainCommit}:scripts/chat/narrator.py | grep -n "narrator_meta"
   git show ${args.devCommit}:scripts/chat/narrator.py | grep -n "narrator_meta"

Return structured findings with evidence (file:line references).`,
      context: {
        projectRoot: args.projectRoot,
        mainCommit: args.mainCommit,
        devCommit: args.devCommit,
        changedFiles: args.changedFiles,
      },
      instructions: [
        'Read actual code from both branches — do not guess',
        'Classify each change as SAFE, RISKY, or BREAKING',
        'Focus on changes that could cause empty interpreter response or lost narration',
        'Return file:line references for every finding',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['changes', 'riskAssessment', 'suspectedCauses'],
      properties: {
        changes: { type: 'array', description: 'List of classified changes' },
        riskAssessment: { type: 'object', description: 'Overall risk per file' },
        suspectedCauses: { type: 'array', description: 'Ranked list of suspected root causes with evidence' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task: Trace execution path for empty interpreter response
// ============================================================================

const traceExecutionPathTask = defineTask('trace-execution-path', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Trace what happens when interpreter returns empty JSON',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python execution path tracer',
      task: `Trace the EXACT execution path when the interpreter returns {} on the dev branch (${args.devCommit}).

SYMPTOM: ${args.symptom}
LOG EVIDENCE: ${args.logEvidence}
DIFF ANALYSIS: ${args.diffAnalysis}

DO THE FOLLOWING (read actual code, trace every function call):

1. Read the WebSocket handler on dev branch:
   git show ${args.devCommit}:app/api/main.py | look at websocket_chat function

2. Trace what happens after interpret() returns a plan parsed from {}:
   - How does InterpretationPlan.model_validate({}) behave? What are the defaults?
   - Read git show ${args.devCommit}:scripts/chat/plan_models.py — what does InterpretationPlan look like? What are its required fields?
   - If validation fails, where is the exception caught?
   - If validation succeeds with defaults, what does execute_scholar_plan receive?

3. Trace the executor path with an empty/default plan:
   - git show ${args.devCommit}:scripts/chat/executor.py — execute_plan function
   - With no execution_steps, what does _collect_grounding return?
   - How do the 30 records appear if the interpreter returned {}?

4. Trace the narrator path:
   - After execution, how is narrate called?
   - Read the full narrate_streaming / narrate function chain
   - Is narrator_meta a DIFFERENT function from the regular narrator?
   - What triggers narrator_meta vs the regular narrator?
   - With what data is the narrator called?

5. Trace the WebSocket response assembly:
   - After narration, how are the results + links sent to the client?
   - Is there a code path where results are sent but narration is skipped?
   - Check if the "complete" message includes different data on dev vs main

6. KEY QUESTION: Is there a fallback/default query that runs when the plan is empty?
   Look for any code that says "if no steps" or "if plan is empty" or default retrieval.

Return the complete trace with file:line references for every step.`,
      context: {
        projectRoot: args.projectRoot,
        devCommit: args.devCommit,
      },
      instructions: [
        'Read actual code using git show — do not guess or assume',
        'Trace every function call in the path',
        'Include file:line references',
        'Answer the 6 specific questions above with evidence',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['executionTrace', 'emptyPlanBehavior', 'narratorPath', 'rootCauseEvidence'],
      properties: {
        executionTrace: { type: 'array', description: 'Step-by-step execution trace' },
        emptyPlanBehavior: { type: 'object', description: 'What happens with empty interpreter response' },
        narratorPath: { type: 'object', description: 'How narrator is invoked and what data it receives' },
        rootCauseEvidence: { type: 'object', description: 'Evidence pointing to root cause' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task: Synthesize evidence-based regression report
// ============================================================================

const synthesizeReportTask = defineTask('synthesize-report', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Synthesize evidence-based regression report',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior software engineer writing an incident report',
      task: `Synthesize all gathered evidence into a definitive regression report.

INPUTS:
- Main commit: ${args.mainCommit}
- Dev commit: ${args.devCommit}
- Test query: ${args.testQuery}
- Symptom: ${args.symptom}
- Log evidence: ${args.logEvidence}
- Diff analysis: ${args.diffAnalysis}
- Execution path trace: ${args.pathTrace}

WRITE a markdown report to ${args.projectRoot}/.a5c/runs/regression-analysis/artifacts/regression-report.md

The report MUST follow this structure:

# Regression Analysis Report

## Summary
One paragraph: what broke, confirmed root cause, impact.

## Timeline
- When was the broken version deployed
- When was the regression detected
- When was rollback performed

## Evidence

### Server Logs
- Exact log entries that show the failure
- What each log entry proves

### Code Analysis
- Specific code changes that caused the regression (file:line)
- Why these changes cause the observed behavior

### Execution Path Trace
- The exact path from query → interpreter → executor → narrator → UI
- Where the path diverges between main and dev

## Root Cause
- THE confirmed root cause with evidence chain
- Distinguish between primary cause and contributing factors
- If multiple factors, rank by impact

## What Worked vs What Broke
- Which parts of the dev enhancement are safe
- Which parts caused the regression

## Recommendations
- How to fix the regression on dev branch
- What tests would catch this in future
- Whether any of the dev changes can be safely cherry-picked to main

IMPORTANT: Every claim must cite evidence (log entry, code line, or test result). Mark any remaining uncertainty explicitly with [UNCONFIRMED].`,
      context: {
        projectRoot: args.projectRoot,
      },
      instructions: [
        'Write the report as a markdown file',
        'Every claim must have a citation',
        'Mark uncertainty explicitly',
        'Be concise — no filler',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['reportPath', 'rootCause', 'confidence'],
      properties: {
        reportPath: { type: 'string', description: 'Path to the written report' },
        rootCause: { type: 'string', description: 'One-line root cause summary' },
        confidence: { type: 'string', enum: ['confirmed', 'high', 'medium', 'low'], description: 'Confidence in root cause' },
        safeChanges: { type: 'array', description: 'Dev changes that are safe to keep' },
        breakingChanges: { type: 'array', description: 'Dev changes that caused the regression' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
