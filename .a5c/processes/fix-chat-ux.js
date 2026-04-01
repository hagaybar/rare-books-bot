/**
 * @process fix-chat-ux
 * @description Fix chat streaming/thinking visibility and session persistence across page refreshes
 * @inputs { projectRoot: string }
 *
 * @skill frontend-design .claude/skills/frontend-design/SKILL.md
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
  } = inputs;

  // ============================================================================
  // PHASE 1: Fix streaming/thinking visibility in MessageBubble
  // ============================================================================

  ctx.log('info', 'Phase 1: Fix thinking/streaming visibility');

  const fixStreaming = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Fix thinking process and streaming typing visibility',
    description: `The chat UI no longer shows the "thinking" progress steps or streaming text animation.

ROOT CAUSE: In frontend/src/components/chat/MessageBubble.tsx, the conditional rendering
at line ~162 filters out messages during the thinking phase because content is empty:
  {!message.clarificationNeeded && (isStreaming || (isStreamComplete && message.content)) && (...)}

When streamingState === 'thinking' and content === '', this condition is false, hiding the bubble.

FIX NEEDED:
1. In MessageBubble.tsx, update the conditional so the message bubble renders during the thinking phase too.
   The thinking steps (ThinkingBlock) should be visible with pulsing animation while the query is being processed.
   Once streaming starts, the text should appear with the blinking cursor animation.

2. Make sure the ThinkingBlock component at line ~126 is always visible when there are thinking steps,
   regardless of the streaming state.

3. Test by checking that:
   - When streamingState is 'thinking', the ThinkingBlock shows with its pulsing dots
   - When streamingState is 'streaming', text appears progressively with a cursor
   - When streamingState is 'complete', the final message renders normally

DO NOT change the WebSocket backend or the Chat.tsx message handling — those are correct.
Only fix the rendering logic in MessageBubble.tsx.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit`,
  });

  ctx.log('info', `Streaming fix: ${JSON.stringify(fixStreaming)}`);

  // ============================================================================
  // PHASE 2: Fix session persistence across page refreshes
  // ============================================================================

  ctx.log('info', 'Phase 2: Fix session persistence');

  const fixSessions = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Persist chat session ID across page refreshes',
    description: `Chat history is lost on page refresh because the session ID is only stored in-memory (Zustand store).

ROOT CAUSE: The sessionId in appStore.ts is not persisted to localStorage. When the page refreshes,
sessionId resets to null, and the previous conversation is lost.

FIX NEEDED:

1. In frontend/src/pages/Chat.tsx:
   - On mount, check localStorage for a saved session ID (key: 'rare-books-session-id')
   - If found, set it as the current sessionId and load the session history from GET /sessions/{id}
   - Whenever sessionId changes (from WebSocket session_created or HTTP response), save to localStorage
   - When user explicitly starts a new conversation (if there's such a button), clear localStorage

2. Make sure the session restoration flow works:
   - Page loads → check localStorage → find session ID → call GET /sessions/{id}
   - Parse messages from response → display in chat as historical messages
   - New messages append to the existing conversation

3. The URL parameter ?session=xxx should take priority over localStorage if present.

4. Handle edge cases:
   - Expired/deleted session: if GET /sessions/{id} returns 404, clear localStorage and start fresh
   - Different user: if the session belongs to a different user (403), clear and start fresh

DO NOT change the backend session endpoints — they already support GET /sessions/{id} with message history.
Only modify frontend files.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit`,
  });

  ctx.log('info', `Session fix: ${JSON.stringify(fixSessions)}`);

  // ============================================================================
  // PHASE 3: TypeScript check + build verification
  // ============================================================================

  ctx.log('info', 'Phase 3: Build verification');

  const buildCheck = await ctx.task(shellTask, {
    projectRoot,
    phase: 'frontend build check',
    command: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build`,
    timeout: 120000,
  });

  ctx.log('info', `Build check: ${JSON.stringify(buildCheck)}`);

  // ============================================================================
  // PHASE 4: Deploy breakpoint
  // ============================================================================

  const deployApproval = await ctx.task(breakpointTask, {
    question: 'Both fixes are implemented and build passes. Ready to commit, push, and deploy?',
    options: ['Approve - commit and deploy', 'Reject - review first'],
  });

  if (!deployApproval?.approved) {
    ctx.log('info', 'Deployment rejected');
    return { success: true, deployed: false, reason: 'User rejected deployment' };
  }

  // ============================================================================
  // PHASE 5: Commit, push, deploy
  // ============================================================================

  ctx.log('info', 'Phase 5: Commit, push, deploy');

  const commitAndDeploy = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Commit changes and deploy',
    description: `Commit the chat UX fixes and deploy to production:

1. Stage the changed files (only frontend files that were modified)
2. Create a commit with message:
   fix: restore thinking/streaming UI and persist chat sessions

   - Fix MessageBubble conditional rendering to show thinking steps
   - Persist session ID to localStorage for cross-refresh continuity

   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

3. Push to origin main
4. Run ./deploy.sh to deploy to production
5. Verify with health check: ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 "curl -sf http://127.0.0.1:8001/health"

Return the deploy result.`,
    testCommand: `cd ${projectRoot} && git log --oneline -1`,
  });

  ctx.log('info', `Deploy: ${JSON.stringify(commitAndDeploy)}`);

  return {
    success: true,
    deployed: true,
    fixes: ['streaming-thinking-visibility', 'session-persistence'],
  };
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
      role: 'Senior frontend developer fixing chat UX issues in a React + FastAPI app',
      task: args.taskName,
      context: {
        projectRoot: args.projectRoot,
      },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        args.description,
        'Read the relevant files before making changes.',
        'Make minimal, targeted changes — do not refactor unrelated code.',
        `Verification: ${args.testCommand}`,
        'Return a JSON summary with: { taskName, status, filesChanged, details }',
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
