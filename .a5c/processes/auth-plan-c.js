/**
 * @process auth-plan-c
 * @description Auth Plan C: Security hardening — token tracking, quota, moderation, kill switch. 3 tasks.
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;
  const plan = 'docs/superpowers/plans/2026-03-28-auth-plan-c-hardening.md';

  ctx.log('info', 'Auth Plan C: Security hardening (3 tasks)');

  const task1 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 1: Security module',
    description: `Read ${plan} — Task 1. Create app/api/security.py with ALL functions from the plan:
- record_token_usage(user_id, tokens): write to token_usage table using INSERT ON CONFLICT UPDATE
- check_quota(user_id): check if user has remaining monthly quota, return (allowed, used, limit)
- is_chat_enabled() / set_chat_enabled(): read/write chat_enabled setting
- check_moderation(text): async call to OpenAI Moderation API, return (safe, category)
- mask_pii(text): regex-based email and phone masking
- validate_output(text): check for leaked API keys or secrets in LLM output
- validate_input(text): check length, strip control chars

Use the EXACT code from the plan.
Verify: poetry run python -c "from app.api.security import record_token_usage, check_quota, is_chat_enabled, mask_pii; print('OK')"
Commit: git add app/api/security.py && git commit -m "feat: security module — token tracking, quota, moderation, PII, kill switch"`,
    testCommand: `cd ${projectRoot} && poetry run python -c "from app.api.security import record_token_usage, check_quota, is_chat_enabled, mask_pii, validate_output; print('OK')"`,
  });

  const task2 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 2: Wire security into chat endpoint',
    description: `Read ${plan} — Task 2. Modify app/api/main.py to add security checks to the /chat POST endpoint.

Before query processing, add IN ORDER:
1. Kill switch: if not is_chat_enabled() → return 503
2. Input validation: validate_input(message) → return 400 if invalid
3. Quota check: check_quota(user["user_id"]) → return 429 if exceeded, include used/limit in response
4. PII masking: message = mask_pii(message)
5. Moderation: await check_moderation(message) → return 400 if flagged

After response:
6. Output validation: validate_output on response text
7. Token recording: record_token_usage with tokens from OpenAI response
8. Audit log: record the chat query

IMPORTANT: The chat endpoint is in app/api/main.py. Read it first to understand the current flow. The security checks should wrap the existing logic, not replace it.

Also add rate limiting with slowapi (already in dependencies). Apply 30/minute limit to /chat.

For the WebSocket /ws/chat, add the same pre-checks (kill switch, quota, moderation) at the message handling level.

Commit: git add app/api/main.py && git commit -m "feat: wire security into chat — quota, moderation, PII, kill switch, rate limit"`,
    testCommand: `cd ${projectRoot} && poetry run python -c "from app.api.main import app; print('App OK')"`,
  });

  const task3 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 3: Admin kill switch + audit purge + frontend',
    description: `Read ${plan} — Task 3. Three parts:

1. In app/api/auth_routes.py: add GET /settings/chat-status and POST /settings/chat-toggle endpoints (admin only). Uses is_chat_enabled/set_chat_enabled from security.py.

2. In app/api/auth_db.py: add purge_audit_log(days) function. In app/cli.py: add purge-audit command.

3. In frontend/src/pages/admin/Users.tsx: add a kill switch section above the users table. Shows current chat status, toggle button (red "Disable Chat" / green "Enable Chat"). Use React Query for fetching status, useMutation for toggling. Add toast notification.

Verify: cd frontend && npx tsc --noEmit && npm run build
Commit and push: git add app/api/ app/cli.py frontend/src/ && git commit -m "feat: kill switch UI, audit purge, complete security hardening" && git push origin feature/auth-security`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -5`,
  });

  ctx.log('info', 'Auth Plan C complete');
  return { success: true };
}

const agentTask = defineTask('authc-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior security engineer implementing production hardening',
      task: args.taskName,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        'Branch: feature/auth-security',
        args.description,
        `Verification: ${args.testCommand}`,
        'Return JSON: { taskName, status, filesChanged }',
      ],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
