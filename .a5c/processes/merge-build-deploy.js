/**
 * @process merge-build-deploy
 * @description Merge mobile branch to main, rebuild Docker, deploy to server
 * @inputs { branch: string, target: string, deployScript: string }
 *
 * @skill git-expert .claude/skills/git-expert/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    branch = 'claude/improve-mobile-navigation-rXthV',
    target = 'main',
    deployScript = './deploy.sh',
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
  } = inputs;

  // ============================================================================
  // PHASE 1: Merge branch into main
  // ============================================================================

  ctx.log('info', 'Phase 1: Merge mobile branch into main');

  const mergeTask = await ctx.task(shellTask, {
    projectRoot,
    phase: 'merge',
    command: [
      'git fetch origin',
      `git checkout ${target}`,
      `git merge origin/${branch} --no-edit`,
      `git push origin ${target}`,
      'echo "Merge complete. HEAD is now $(git rev-parse --short HEAD)"',
    ].join(' && '),
  });

  ctx.log('info', `Merge result: ${JSON.stringify(mergeTask)}`);

  // Verify merge
  const verifyMerge = await ctx.task(shellTask, {
    projectRoot,
    phase: 'merge verification',
    command: [
      'git log --oneline -3',
      'test -f frontend/src/components/MobileTabBar.tsx && echo "MobileTabBar.tsx present - OK" || (echo "FAIL: MobileTabBar.tsx missing" && exit 1)',
      'echo "Merge verification passed"',
    ].join(' && '),
  });

  ctx.log('info', `Merge verification: ${JSON.stringify(verifyMerge)}`);

  // ============================================================================
  // PHASE 2: Deploy (breakpoint + deploy.sh + health check)
  // ============================================================================

  ctx.log('info', 'Phase 2: Deploy to production server');

  const deployApproval = await ctx.task(breakpointTask, {
    question: 'Merge is complete and verified. Ready to rebuild Docker and deploy to the production server (cenlib-rare-books.nurdillo.com)?',
    options: ['Approve - deploy now', 'Reject - stop here'],
  });

  if (!deployApproval?.approved) {
    ctx.log('info', 'Deployment rejected by user');
    return {
      success: true,
      mergeCompleted: true,
      deployCompleted: false,
      reason: 'User rejected deployment',
    };
  }

  const deployResult = await ctx.task(shellTask, {
    projectRoot,
    phase: 'deployment',
    command: deployScript,
    timeout: 300000,
  });

  ctx.log('info', `Deploy result: ${JSON.stringify(deployResult)}`);

  // Verify deployment health
  const healthCheck = await ctx.task(shellTask, {
    projectRoot,
    phase: 'remote health check',
    command: 'ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 "curl -sf http://127.0.0.1:8000/health" && echo "Remote health check PASSED"',
    timeout: 30000,
  });

  ctx.log('info', `Health check: ${JSON.stringify(healthCheck)}`);

  return {
    success: true,
    mergeCompleted: true,
    deployCompleted: true,
  };
}

// ============================================================================
// Task Definitions
// ============================================================================

const shellTask = defineTask('shell-cmd', (args, taskCtx) => ({
  kind: 'shell',
  title: `${args.phase}`,
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
