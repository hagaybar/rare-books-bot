/**
 * @process narrator-trace
 * @description End-to-end tracing of narrator failure — instrument code, reproduce, capture exact exception
 * @inputs { projectRoot: string, testQuery: string, confirmedEvidence: object }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill systematic-debugging .superpowers/skills/systematic-debugging/SKILL.md
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    testQuery = 'ספרים בשפה העברית שהודפסו באמסטרדם',
  } = inputs;

  // ============================================================================
  // PHASE 1: Instrument the narrator to capture the exact exception
  // ============================================================================

  ctx.log('info', 'Phase 1: Instrument narrator and reproduce the error');

  const instrumentResult = await ctx.task(instrumentAndReproduceTask, {
    projectRoot,
    testQuery,
  });

  ctx.log('info', `Instrument result: ${JSON.stringify(instrumentResult).slice(0, 500)}`);

  // ============================================================================
  // PHASE 2: Trace the root cause from the captured exception
  // ============================================================================

  ctx.log('info', 'Phase 2: Trace root cause from captured exception');

  const traceResult = await ctx.task(traceRootCauseTask, {
    projectRoot,
    testQuery,
    instrumentResult: JSON.stringify(instrumentResult).slice(0, 5000),
  });

  ctx.log('info', `Trace result: ${JSON.stringify(traceResult).slice(0, 500)}`);

  // ============================================================================
  // PHASE 3: Write definitive report with fix recommendation
  // ============================================================================

  ctx.log('info', 'Phase 3: Write definitive findings');

  const report = await ctx.task(writeReportTask, {
    projectRoot,
    testQuery,
    instrumentResult: JSON.stringify(instrumentResult).slice(0, 5000),
    traceResult: JSON.stringify(traceResult).slice(0, 5000),
  });

  ctx.log('info', 'Report written');

  // ============================================================================
  // BREAKPOINT: Present findings
  // ============================================================================

  await ctx.breakpoint({
    question: 'Root cause analysis complete. Review findings and approve?',
    title: 'Narrator Trace Results',
    options: ['Approve findings', 'Investigate further'],
  });

  return { success: true, instrumentResult, traceResult, report };
}

// ============================================================================
// Task 1: Instrument narrator.py and reproduce the error
// ============================================================================

const instrumentAndReproduceTask = defineTask('instrument-reproduce', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Instrument narrator and reproduce the exact exception',
  execution: {
    timeout: 300000,
  },
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python debugging specialist',
      task: `The narrator in a rare books chat pipeline is failing silently. The exception is caught at scripts/chat/narrator.py:224 and the fallback response is returned. We need to capture the EXACT exception.

Project root: ${args.projectRoot}
Test query: ${args.testQuery}
Branch: dev (currently checked out)
The app is running locally: backend on port 8000, frontend on port 5174.

DO THE FOLLOWING — execute every step:

1. First, read scripts/chat/narrator.py lines 206-230 to understand the try/except block around narrate_streaming.

2. Read scripts/chat/narrator.py to find _stream_llm function — this is what's called inside the try block. Read the FULL function.

3. Read scripts/chat/narrator.py to find build_lean_narrator_prompt — this is called inside _stream_llm. Read the FULL function. Pay attention to every attribute access on execution_result and its sub-objects.

4. Create a standalone test script at ${args.projectRoot}/debug_narrator.py that:
   - Sets up Python path correctly (sys.path.insert)
   - Loads environment from .env using dotenv
   - Imports the pipeline functions
   - Runs interpret() -> execute_plan() -> narrate_streaming()
   - WRAPS the narrate_streaming call to log the EXACT exception with full traceback
   - Does NOT catch the exception — let it propagate with full traceback

   The script should look like:
   \`\`\`python
   import sys, os, asyncio, traceback
   sys.path.insert(0, '${args.projectRoot}')
   from dotenv import load_dotenv
   load_dotenv('${args.projectRoot}/.env')

   from scripts.chat.interpreter import interpret
   from scripts.chat.executor import execute_plan
   from scripts.chat.narrator import _stream_llm, build_lean_narrator_prompt
   from scripts.models.llm_client import load_config, get_model

   async def main():
       print("=== Step 1: Interpret ===")
       plan = await interpret("${args.testQuery}")
       print(f"Plan: {len(plan.execution_steps)} steps, intents={plan.intents}")

       print("\\n=== Step 2: Execute ===")
       result = execute_plan(plan, "${args.projectRoot}/data/index/bibliographic.db")
       print(f"Records: {len(result.grounding.records)}, truncated={result.truncated}")

       print("\\n=== Step 3: Build narrator prompt (this is where it likely fails) ===")
       try:
           prompt = build_lean_narrator_prompt("${args.testQuery}", result)
           print(f"Prompt built OK, length={len(prompt)}")
       except Exception as e:
           print(f"PROMPT BUILD FAILED: {type(e).__name__}: {e}")
           traceback.print_exc()
           return

       print("\\n=== Step 4: Stream LLM (narrator) ===")
       chunks = []
       async def cb(text):
           chunks.append(text)
       try:
           narrative = await _stream_llm("${args.testQuery}", result, cb, model=None, api_key=None, token_saving=True)
           print(f"Narrative OK, length={len(narrative)}")
       except Exception as e:
           print(f"STREAM LLM FAILED: {type(e).__name__}: {e}")
           traceback.print_exc()

   asyncio.run(main())
   \`\`\`

5. Run the script:
   cd ${args.projectRoot} && source .venv/bin/activate && python debug_narrator.py

6. Capture the FULL output including any traceback.

IMPORTANT:
- This script WILL make LLM API calls (interpreter). That is expected and approved for this debugging session.
- DO NOT modify narrator.py or any production code. Only create the debug script.
- Return the EXACT exception type, message, and full traceback.`,
      context: { projectRoot: args.projectRoot, testQuery: args.testQuery },
      instructions: [
        'Create and run the debug script — do not just plan',
        'Capture the full exception traceback',
        'Do NOT modify any production code',
        'Return the exact exception details',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['exceptionType', 'exceptionMessage', 'traceback', 'failingStep'],
      properties: {
        exceptionType: { type: 'string' },
        exceptionMessage: { type: 'string' },
        traceback: { type: 'string' },
        failingStep: { type: 'string', description: 'Which step failed: interpret, execute, build_prompt, or stream_llm' },
        scriptOutput: { type: 'string' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task 2: Trace root cause from the captured exception
// ============================================================================

const traceRootCauseTask = defineTask('trace-root-cause', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Trace root cause from captured exception to code',
  execution: {
    timeout: 180000,
  },
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python code analyst',
      task: `An exception was captured from the narrator pipeline. Trace it to the exact root cause.

Project: ${args.projectRoot}
Exception details from instrumentation: ${args.instrumentResult}

DO THE FOLLOWING:

1. Read the exact file and line mentioned in the traceback.
2. Understand what attribute/field/column is missing or what operation failed.
3. Compare the failing code with the main branch version:
   git show d1ecb1b:<failing-file> — show the same function on main
   git show 26bc311:<failing-file> — show the same function on dev
4. Identify the EXACT change that introduced the failure.
5. Check if it's a missing field, wrong type, missing import, or API change.
6. Determine if the fix is in the narrator code, the model code, or the executor code.

Return:
- The exact root cause with file:line
- The exact diff that introduced it
- The minimal fix needed`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read actual code at the traceback locations',
        'Compare main vs dev at those exact lines',
        'Identify the minimal fix',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['rootCause', 'failingCode', 'introducedBy', 'minimalFix'],
      properties: {
        rootCause: { type: 'string' },
        failingCode: { type: 'object', description: 'file, line, code snippet' },
        introducedBy: { type: 'string', description: 'Which commit/change introduced it' },
        minimalFix: { type: 'string', description: 'The exact code change needed' },
        mainBranchCode: { type: 'string' },
        devBranchCode: { type: 'string' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task 3: Write definitive report
// ============================================================================

const writeReportTask = defineTask('write-report', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Write definitive root cause report',
  execution: {
    timeout: 120000,
  },
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical writer',
      task: `Write a concise, definitive root cause report based on the investigation.

Instrumentation result: ${args.instrumentResult}
Trace result: ${args.traceResult}

Write the report to: ${args.projectRoot}/docs/history/reports/2026-04-13-narrator-trace.md

Structure:
# Narrator Failure — Root Cause (Confirmed)
## Exception
The exact exception type, message, and where it occurs.
## Root Cause
What code change caused it, with file:line references.
## Evidence
The full traceback from the debug script.
## Fix
The minimal code change needed.
## Safe Changes
Which dev branch changes are unrelated and safe.

Keep it under 100 lines. Every statement must cite evidence.`,
      context: { projectRoot: args.projectRoot },
      instructions: ['Write the report file', 'Keep it concise and evidence-based'],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['reportPath', 'rootCause'],
      properties: {
        reportPath: { type: 'string' },
        rootCause: { type: 'string' },
        fix: { type: 'string' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
