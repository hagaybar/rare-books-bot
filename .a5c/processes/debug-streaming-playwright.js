/**
 * @process debug-streaming-playwright
 * @description Debug chat streaming issues on live site using Playwright browser automation
 * @inputs { liveUrl: string, projectRoot: string }
 *
 * @skill systematic-debugging superpowers:systematic-debugging
 * @skill frontend-design .claude/skills/frontend-design/SKILL.md
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

export async function process(inputs, ctx) {
  const {
    liveUrl = 'https://cenlib-rare-books.nurdillo.com',
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
  } = inputs;

  // ============================================================================
  // PHASE 1: Playwright analysis of live site streaming behavior
  // ============================================================================

  ctx.log('info', 'Phase 1: Playwright browser analysis of streaming on live site');

  const playwrightAnalysis = await ctx.task(playwrightAnalysisTask, {
    liveUrl,
    projectRoot,
  });

  ctx.log('info', `Playwright analysis result: ${JSON.stringify(playwrightAnalysis)}`);

  // ============================================================================
  // PHASE 2: Root cause analysis from Playwright findings + code review
  // ============================================================================

  ctx.log('info', 'Phase 2: Root cause analysis');

  const rootCause = await ctx.task(rootCauseAnalysisTask, {
    liveUrl,
    projectRoot,
    playwrightFindings: playwrightAnalysis,
  });

  ctx.log('info', `Root cause analysis: ${JSON.stringify(rootCause)}`);

  // ============================================================================
  // PHASE 3: Fix the identified issues
  // ============================================================================

  ctx.log('info', 'Phase 3: Implement fixes');

  const fix = await ctx.task(implementFixTask, {
    projectRoot,
    rootCause,
  });

  ctx.log('info', `Fix result: ${JSON.stringify(fix)}`);

  // ============================================================================
  // PHASE 4: Deploy and verify on live site
  // ============================================================================

  ctx.log('info', 'Phase 4: Deploy fix');

  await ctx.breakpoint({
    question: `Root cause identified and fix implemented. Deploy to ${liveUrl}?`,
    title: 'Deploy Fix',
    context: { rootCause, fix },
  });

  const deploy = await ctx.task(deployAndVerifyTask, {
    liveUrl,
    projectRoot,
  });

  ctx.log('info', `Deploy result: ${JSON.stringify(deploy)}`);

  return {
    success: true,
    playwrightAnalysis,
    rootCause,
    fix,
    deploy,
  };
}

// ---------------------------------------------------------------------------
// TASK DEFINITIONS
// ---------------------------------------------------------------------------

export const playwrightAnalysisTask = defineTask('playwright-analysis', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Playwright: Analyze streaming on live site',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Browser automation QA engineer',
      task: `Use Playwright MCP tools to analyze the chat streaming behavior on the live website at ${args.liveUrl}. The user reports streaming is not working and no answer is shown.`,
      context: {
        liveUrl: args.liveUrl,
        projectRoot: args.projectRoot,
      },
      instructions: [
        `1. Navigate to ${args.liveUrl} using mcp__playwright__browser_navigate`,
        '2. Take a screenshot of the initial page state',
        '3. AUTHENTICATION: The chat page requires "limited" role. Create a test user on the production server via SSH:',
        '   ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 "docker exec rare-books python -m app.cli create-user playwright_test test1234 --role limited" (ignore error if user exists)',
        `4. Navigate to ${args.liveUrl}/login — login with username "playwright_test" and password "test1234" using Playwright form fill and click`,
        '5. After login, navigate to the Chat page',
        '6. Take a screenshot of the Chat page',
        '7. Check browser console messages using mcp__playwright__browser_console_messages for any errors',
        '8. Check network requests using mcp__playwright__browser_network_requests to see WebSocket and API calls',
        '9. Try to interact with the chat - find the input field, type a test query like "books published in Paris", and submit it',
        '10. Wait 15-20 seconds for the response using mcp__playwright__browser_wait_for or just wait',
        '11. Take a screenshot showing the result (or lack thereof)',
        '12. Check console messages again for any errors during the query',
        '13. Check network requests to see if WebSocket connection was established and what messages were exchanged',
        '14. Take a final screenshot',
        '15. Summarize ALL findings: what worked, what failed, any error messages, network activity, WebSocket status',
        'IMPORTANT: Use the Playwright MCP tools (mcp__playwright__*). Do NOT try to run playwright via code or npm.',
        'IMPORTANT: If you encounter authentication, note what type it is and whether it blocks the chat page.',
        'IMPORTANT: Capture ALL console errors and network failures in your summary.',
      ],
      outputFormat: 'JSON with fields: { screenshots: string[], consoleErrors: string[], networkIssues: string[], wsStatus: string, chatBehavior: string, summary: string }',
    },
    outputSchema: {
      type: 'object',
      required: ['summary'],
      properties: {
        summary: { type: 'string' },
        consoleErrors: { type: 'array', items: { type: 'string' } },
        networkIssues: { type: 'array', items: { type: 'string' } },
        wsStatus: { type: 'string' },
        chatBehavior: { type: 'string' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['playwright', 'debugging', 'streaming'],
}));

export const rootCauseAnalysisTask = defineTask('root-cause-analysis', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Root cause analysis from Playwright findings + code',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior full-stack debugger',
      task: 'Analyze the Playwright findings and source code to identify the root cause of the streaming failure.',
      context: {
        liveUrl: args.liveUrl,
        projectRoot: args.projectRoot,
        playwrightFindings: args.playwrightFindings,
      },
      instructions: [
        '1. Review the Playwright findings passed in context — console errors, network issues, WebSocket status, chat behavior',
        '2. Based on the findings, investigate the relevant source code:',
        '   - If WebSocket failed to connect: check app/api/main.py WebSocket handler, docker/cenlib-rare-books.conf nginx proxy config',
        '   - If WebSocket connected but no messages: check the chat pipeline in app/api/main.py ws_chat handler',
        '   - If auth blocked access: check app/api/auth.py and frontend auth flow',
        '   - If frontend JS errors: check frontend/src/pages/Chat.tsx',
        '   - If network errors: check CORS, nginx config, SSL config',
        '3. Read the specific files implicated by the findings (use Read tool with offset/limit)',
        '4. Cross-reference with the deployed Docker configuration: Dockerfile, docker/entrypoint.sh, docker/cenlib-rare-books.conf',
        '5. Identify the EXACT root cause — not guesses, evidence-based',
        '6. Propose a specific fix with file paths and code changes',
        'IMPORTANT: Ground your analysis in the Playwright evidence. Do not speculate without evidence.',
        'IMPORTANT: Check if the issue is frontend (React), backend (FastAPI), infrastructure (nginx/Docker), or a combination.',
      ],
      outputFormat: 'JSON with fields: { rootCause: string, evidence: string[], affectedFiles: string[], proposedFix: string, confidence: number }',
    },
    outputSchema: {
      type: 'object',
      required: ['rootCause', 'proposedFix'],
      properties: {
        rootCause: { type: 'string' },
        evidence: { type: 'array', items: { type: 'string' } },
        affectedFiles: { type: 'array', items: { type: 'string' } },
        proposedFix: { type: 'string' },
        confidence: { type: 'number' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['debugging', 'root-cause', 'analysis'],
}));

export const implementFixTask = defineTask('implement-fix', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Implement the fix for streaming issue',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior full-stack developer',
      task: 'Implement the proposed fix for the streaming issue based on root cause analysis.',
      context: {
        projectRoot: args.projectRoot,
        rootCause: args.rootCause,
      },
      instructions: [
        '1. Review the root cause analysis and proposed fix from context',
        '2. Read the affected files identified in the analysis',
        '3. Implement the fix — make the actual code changes using Edit tool',
        '4. If the fix involves nginx config (docker/cenlib-rare-books.conf), make those changes too',
        '5. If the fix involves frontend code, make changes and verify the build works: cd frontend && npm run build',
        '6. If the fix involves backend code, verify imports work: cd /home/hagaybar/projects/rare-books-bot && source .venv/bin/activate && python3 -c "from app.api.main import app; print(\'OK\')"',
        '7. Run any relevant tests to verify the fix does not break existing functionality',
        '8. Summarize what was changed and why',
        'IMPORTANT: Make ONLY the changes needed to fix the identified issue. Do not refactor or improve other code.',
        'IMPORTANT: Actually write the code changes using Edit/Write tools. Do not just describe what to change.',
      ],
      outputFormat: 'JSON with fields: { changedFiles: string[], changes: string, testsRun: string, testsPassed: boolean }',
    },
    outputSchema: {
      type: 'object',
      required: ['changedFiles', 'changes'],
      properties: {
        changedFiles: { type: 'array', items: { type: 'string' } },
        changes: { type: 'string' },
        testsRun: { type: 'string' },
        testsPassed: { type: 'boolean' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['implementation', 'fix', 'streaming'],
}));

export const deployAndVerifyTask = defineTask('deploy-and-verify', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Deploy fix and verify streaming works on live site',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'DevOps engineer and QA tester',
      task: `Deploy the fix to the live site at ${args.liveUrl} and verify streaming works using Playwright.`,
      context: {
        liveUrl: args.liveUrl,
        projectRoot: args.projectRoot,
      },
      instructions: [
        `1. Deploy using the deploy script: cd ${args.projectRoot} && ./deploy.sh`,
        '2. Wait for deployment to complete and health check to pass',
        '3. Check server health: ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 "curl -sf http://127.0.0.1:8000/health"',
        '4. Check server logs for errors: ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 "docker logs rare-books --tail 30"',
        `5. Use Playwright to navigate to ${args.liveUrl}`,
        '6. Navigate to Chat page',
        '7. Send a test query like "books published in Paris"',
        '8. Wait for response and observe streaming behavior',
        '9. Take screenshots showing the result',
        '10. Check console for errors',
        '11. Report whether the fix resolved the streaming issue',
        'IMPORTANT: Use Playwright MCP tools (mcp__playwright__*) for browser verification.',
        'IMPORTANT: If deployment fails, report the error and do not proceed with verification.',
      ],
      outputFormat: 'JSON with fields: { deployed: boolean, healthCheck: string, streamingWorks: boolean, screenshots: string[], summary: string }',
    },
    outputSchema: {
      type: 'object',
      required: ['deployed', 'streamingWorks', 'summary'],
      properties: {
        deployed: { type: 'boolean' },
        healthCheck: { type: 'string' },
        streamingWorks: { type: 'boolean' },
        summary: { type: 'string' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['deploy', 'verify', 'playwright'],
}));
