/**
 * @process auth-plan-b
 * @description Auth Plan B: Frontend — login page, auth store, route guards, sidebar. 3 tasks.
 * @skill frontend-design specializations/web-development/skills/frontend-design/SKILL.md
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;
  const plan = 'docs/superpowers/plans/2026-03-28-auth-plan-b-frontend.md';

  ctx.log('info', 'Auth Plan B: Frontend (3 tasks)');

  const task1 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 1: Vite proxy + auth API client + auth store',
    description: `Read ${plan} — Task 1 completely.

1. In frontend/vite.config.ts: add '/auth' proxy entry to backend.
2. Create frontend/src/api/auth.ts: loginApi, guestApi, fetchMe, refreshToken, logoutApi functions. All use credentials: 'include'. AuthUser interface.
3. Create frontend/src/stores/authStore.ts: Zustand store with user, loading, error state. initialize() tries fetchMe, falls back to refreshToken+fetchMe. logout() calls logoutApi and clears user.

Use the EXACT code from the plan.
Verify: cd frontend && npx tsc --noEmit
Commit: git add frontend/vite.config.ts frontend/src/api/auth.ts frontend/src/stores/authStore.ts && git commit -m "feat: add auth API client, Zustand store, and Vite proxy"`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -3`,
  });

  const task2 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 2: Login page',
    description: `Read ${plan} — Task 2. Create frontend/src/pages/Login.tsx — login form (username + password + Login button) + "or" divider + "Continue as Guest" button. On login success, call fetchMe and navigate to /. On guest, navigate to /network. Show error messages. Use EXACT code from plan.

Verify: cd frontend && npx tsc --noEmit
Commit: git add frontend/src/pages/Login.tsx && git commit -m "feat: add Login page with username/password and guest option"`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -3`,
  });

  const task3 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 3: AuthGuard + routing + sidebar + chat + credentials',
    description: `Read ${plan} — Task 3 completely. This is the biggest task — read ALL steps.

1. Create frontend/src/components/AuthGuard.tsx — checks auth on mount via initialize(), redirects to /login if no user, checks page-level role access. Use code from plan.

2. Update frontend/src/App.tsx:
   - Import Login and AuthGuard
   - Add <Route path="/login" element={<Login />} /> OUTSIDE the Layout
   - Wrap the Layout route in AuthGuard: <Route element={<AuthGuard><Layout /></AuthGuard>}>
   - Add redirect: if user is guest and path is /, redirect to /network

3. Update frontend/src/components/Sidebar.tsx:
   - Import useAuthStore
   - Add minRole to each nav item
   - Filter items by user role level
   - Add user info at bottom: username, role badge, logout button
   - When sidebar is collapsed, just show logout icon

4. Update frontend/src/pages/Chat.tsx:
   - Import useAuthStore
   - If user.role === 'guest': show "Login to use chat" message + link to /login instead of input
   - If user.role === 'limited': show remaining quota badge if available

5. CRITICAL: Add credentials: 'include' to ALL fetch() calls in:
   - frontend/src/api/chat.ts (every fetch call)
   - frontend/src/api/metadata.ts (every fetch call)
   - frontend/src/api/network.ts (every fetch call)
   Without this, cookies won't be sent and all API calls will return 401.

Verify: cd frontend && npx tsc --noEmit && npm run build
Commit and push: git add frontend/src/ && git commit -m "feat: AuthGuard, routing, sidebar role filtering, chat gating, credentials" && git push origin feature/auth-security`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -5`,
  });

  ctx.log('info', 'Auth Plan B complete');
  return { success: true };
}

const agentTask = defineTask('authb-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior React developer implementing authentication frontend',
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
