/**
 * @process fix-token-display
 * @description Fix admin token usage showing 0 and add input/output/cost columns to user management table
 * @inputs { projectRoot: string }
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

// ============================================================================
// Task: Fix backend to aggregate all months + Fix frontend to show breakdown
// ============================================================================

const fixTokenTracking = defineTask('fix-token-tracking', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Fix token usage display: backend aggregation + frontend columns',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Full-stack developer',
      task: 'Fix two bugs in the user management token usage display',
      context: {
        projectRoot: args.projectRoot,
        bug1_description: 'Admin token use shows 0 despite having used tokens. The GET /auth/users endpoint in app/api/auth_routes.py filters token_usage by current month only. When the month rolls over, all users show 0. Fix: aggregate across ALL months (SUM) instead of filtering by current month.',
        bug2_description: 'The Users.tsx admin page only shows a single "Tokens Used" column but the API already returns input_tokens_this_month, output_tokens_this_month, and cost_usd_this_month. Add these to the table display.',
        backend_file: 'app/api/auth_routes.py',
        backend_model_file: 'app/api/auth_models.py',
        frontend_file: 'frontend/src/pages/admin/Users.tsx',
        frontend_types_file: 'frontend/src/api/auth.ts',
      },
      instructions: [
        'Read all 4 files mentioned in context first.',
        '',
        '## Backend fix (app/api/auth_routes.py):',
        'In the list_users function (GET /auth/users endpoint):',
        '1. Remove the current-month-only filter from the SQL query',
        '2. Change the LEFT JOIN to aggregate across ALL months using SUM:',
        '   SELECT u.*, COALESCE(SUM(tu.tokens_used), 0) as tokens_used_this_month, COALESCE(SUM(tu.input_tokens), 0) as input_tokens_this_month, COALESCE(SUM(tu.output_tokens), 0) as output_tokens_this_month, COALESCE(SUM(tu.cost_usd), 0.0) as cost_usd_this_month FROM users u LEFT JOIN token_usage tu ON tu.user_id = u.id GROUP BY u.id ORDER BY u.id',
        '3. Remove the month parameter since we no longer filter by month',
        '4. The column aliases should remain the same (_this_month names) so the frontend doesnt need model changes, even though they now represent all-time totals',
        '',
        '## Frontend fix (frontend/src/pages/admin/Users.tsx):',
        '1. Replace the single "Tokens Used" column with three columns: "Input Tokens", "Output Tokens", and "Cost (USD)"',
        '2. In the table header (thead), add the three new column headers replacing the old "Tokens Used" header',
        '3. In the UserRow view mode, replace the single tokens_used_this_month cell with:',
        '   - Input tokens cell showing user.input_tokens_this_month formatted with toLocaleString()',
        '   - Output tokens cell showing user.output_tokens_this_month formatted with toLocaleString()',
        '   - Cost cell showing "$" + user.cost_usd_this_month.toFixed(4)',
        '4. In the UserRow edit mode, make the same column changes',
        '5. Update the colSpan on the password reset row from 7 to 9 (since we added 2 new columns)',
        '6. Update the empty state colSpan from 7 to 9',
        '',
        '## Do NOT change:',
        '- auth_models.py (the UserListItem model already has all needed fields)',
        '- auth.ts (the UserListItem interface already has all needed fields)',
        '- Any other files',
        '',
        'After making changes, run: cd frontend && npx tsc --noEmit to verify TypeScript compiles.',
      ],
      outputFormat: 'JSON with fields: { summary: string, filesChanged: string[], backendFixed: boolean, frontendFixed: boolean, typecheckPassed: boolean }',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Task: Verify the fix
// ============================================================================

const verifyFix = defineTask('verify-fix', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Verify token display fix',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer',
      task: 'Verify the token display fix is correct',
      context: {
        projectRoot: args.projectRoot,
      },
      instructions: [
        'Verify the fix by checking:',
        '',
        '1. Read app/api/auth_routes.py - confirm the list_users SQL aggregates across ALL months (no month filter, uses SUM + GROUP BY)',
        '2. Read frontend/src/pages/admin/Users.tsx - confirm the table has Input Tokens, Output Tokens, and Cost columns',
        '3. Run: cd frontend && npx tsc --noEmit - confirm no TypeScript errors',
        '4. Check that the SQL query is valid SQLite syntax',
        '5. Check colSpan values are consistent with the number of columns',
        '',
        'Report any issues found.',
      ],
      outputFormat: 'JSON with fields: { passed: boolean, issues: string[], details: string }',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

// ============================================================================
// Process definition
// ============================================================================

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
  } = inputs;

  ctx.log('info', 'Phase 1: Fix token usage backend and frontend display');

  const fixResult = await ctx.task(fixTokenTracking, {
    projectRoot,
  });

  ctx.log('info', `Phase 1 result: ${JSON.stringify(fixResult)}`);

  ctx.log('info', 'Phase 2: Verify the fix');

  const verifyResult = await ctx.task(verifyFix, {
    projectRoot,
  });

  ctx.log('info', `Phase 2 result: ${JSON.stringify(verifyResult)}`);

  return { fixResult, verifyResult };
}
