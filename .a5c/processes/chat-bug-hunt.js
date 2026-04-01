/**
 * @process chat-bug-hunt
 * @description Systematic bug hunt across the chat pipeline — WebSocket, streaming, session, UI rendering
 * @inputs { projectRoot: string }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill frontend-design .claude/skills/frontend-design/SKILL.md
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
  } = inputs;

  // ============================================================================
  // PHASE 1: Audit WebSocket + streaming pipeline for bugs
  // ============================================================================

  ctx.log('info', 'Phase 1: Audit backend WebSocket pipeline');

  const backendAudit = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Audit WebSocket chat pipeline for bugs',
    description: `Systematically audit the WebSocket chat pipeline for bugs. The user reports queries appearing "stuck" — the backend completes but the frontend doesn't show results.

INVESTIGATE AND FIX:

1. Read app/api/main.py — the WebSocket /ws/chat handler. Check:
   - Are all exceptions caught and sent as error messages to the client?
   - Is the WebSocket connection kept alive during the entire pipeline?
   - After narrate_streaming completes, is the "complete" message sent correctly?
   - Is the session message saved BEFORE the complete message is sent?
   - Are there any code paths where the pipeline finishes without sending "complete"?

2. Read scripts/chat/narrator.py — narrate_streaming and _stream_llm. Check:
   - Does _stream_llm properly handle the case where the OpenAI stream ends without a response.completed event?
   - If log_llm_call() throws an error (e.g. in the metadata computation), does the narrative still get returned?
   - Move the log_llm_call in _stream_llm into a try/except so logging failures don't crash the narrator
   - Check that the fallback_response in narrate_streaming sends the full grounding data back

3. Read the executor to check the validation error seen in logs:
   "Skipping step 1 (action='retrieve'): 1 validation error for Filter - Value error, IN operation requires value to be a list"
   - Find where this validation happens and check if it causes downstream issues
   - This might cause empty grounding data which affects the narrator

4. Check if there's a race condition: WebSocket closes before "complete" is sent
   - Look for any await calls between the last stream chunk and the "complete" message

For each bug found: FIX IT. Don't just report — write the fix.

Verification: source .venv/bin/activate && python3 -c "from app.api.main import app; print('OK')"`,
    testCommand: `source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.main import app; print('OK')"`,
  });

  ctx.log('info', `Backend audit: ${JSON.stringify(backendAudit)}`);

  // ============================================================================
  // PHASE 2: Audit frontend WebSocket + streaming rendering
  // ============================================================================

  ctx.log('info', 'Phase 2: Audit frontend streaming rendering');

  const frontendAudit = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Audit frontend chat WebSocket and streaming rendering for bugs',
    description: `Systematically audit the Chat frontend for bugs that cause the UI to appear "stuck" after a query.

INVESTIGATE AND FIX in frontend/src/pages/Chat.tsx:

1. WebSocket message handling:
   - Check ALL message type handlers (thinking, progress, stream_start, stream_delta, batch, complete, error, session_created)
   - Does the "complete" handler properly update the message's streamingState to 'complete'?
   - If the WebSocket closes unexpectedly, does the UI recover (show what was streamed so far)?
   - Is there a timeout for WebSocket responses? What happens if the backend takes >30 seconds?

2. streamingState transitions:
   - Trace the full lifecycle: thinking → streaming → complete
   - Are there any states where the message stays in "thinking" or "streaming" forever?
   - What happens if "complete" arrives but the streaming message ref is null?
   - Check: does onclose handler finalize the streaming message?

3. Session restoration bugs:
   - When the page refreshes and loads a previous session, does it correctly display old messages?
   - The fallback response (raw record dump) was shown on refresh — check how session messages are restored and rendered
   - Are restored messages given the correct streamingState ('complete')?

4. HTTP fallback:
   - When WebSocket fails and falls back to HTTP, does the loading state clear properly?
   - Does the HTTP response get displayed as a proper message?

5. Auth token expiry during streaming:
   - If /auth/me returns 401 during a stream, does the WebSocket handler catch it gracefully?

For each bug found: FIX IT. Don't just report.

Verification: cd ${projectRoot}/frontend && npx tsc --noEmit`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit`,
  });

  ctx.log('info', `Frontend audit: ${JSON.stringify(frontendAudit)}`);

  // ============================================================================
  // PHASE 3: Build verification
  // ============================================================================

  ctx.log('info', 'Phase 3: Build verification');

  const buildCheck = await ctx.task(shellTask, {
    projectRoot,
    phase: 'full build check',
    command: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build`,
    timeout: 120000,
  });

  ctx.log('info', `Build: ${JSON.stringify(buildCheck)}`);

  // ============================================================================
  // PHASE 4: Deploy
  // ============================================================================

  const deployApproval = await ctx.task(breakpointTask, {
    question: 'Bug fixes implemented and build passes. Deploy to production?',
    options: ['Approve - deploy', 'Reject - review first'],
  });

  if (!deployApproval?.approved) {
    return { success: true, deployed: false };
  }

  const deploy = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Commit bug fixes and deploy',
    description: `Commit all bug fixes and deploy:

1. Stage all changed files
2. Commit with message:
   fix: harden WebSocket streaming pipeline and chat UI resilience

   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

3. Push to origin main
4. Run ./deploy.sh
5. Verify health check`,
    testCommand: `cd ${projectRoot} && git log --oneline -1`,
  });

  ctx.log('info', `Deploy: ${JSON.stringify(deploy)}`);

  return { success: true, deployed: true, feature: 'chat-bug-fixes' };
}

// ============================================================================
// Task Definitions
// ============================================================================

const agentTask = defineTask('agent-impl', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior full-stack developer debugging a WebSocket streaming chat pipeline',
      task: args.taskName,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        args.description,
        'Read the relevant files thoroughly before making changes.',
        'For each bug: explain the root cause briefly, then write the fix.',
        'Make minimal, targeted changes — do not refactor unrelated code.',
        `Verification: ${args.testCommand}`,
        'Return JSON summary: { taskName, status, bugsFound, bugsFixed, filesChanged, details }',
      ],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const shellTask = defineTask('shell-cmd', (args, taskCtx) => ({
  kind: 'shell',
  title: args.phase,
  shell: {
    command: args.command,
    cwd: args.projectRoot,
    timeout: args.timeout || 60000,
  },
  io: {
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const breakpointTask = defineTask('breakpoint-gate', (args, taskCtx) => ({
  kind: 'breakpoint',
  title: args.question,
  breakpoint: {
    question: args.question,
    options: args.options,
  },
}));
