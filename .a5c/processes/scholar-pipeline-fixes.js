/**
 * @process scholar-pipeline-fixes
 * @description Fix 6 issues found in scholar pipeline evaluation: JSON parsing, index shifting,
 *   narrator prompt, link visibility, agent links, grounding UI. Verify with Playwright.
 *
 * @inputs { projectRoot: string }
 * @outputs { success: boolean, issuesFixed: number }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill git-expert .claude/skills/git-expert/SKILL.md
 * @skill frontend-design specializations/web-development/skills/frontend-design/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
  } = inputs;

  ctx.log('info', 'Starting scholar pipeline fixes (6 issues)');

  // ============================================================================
  // PHASE 1: Backend Critical Fixes (Issues 1, 2, 5)
  // ============================================================================

  ctx.log('info', 'Phase 1: Backend critical fixes — JSON parsing, index remapping, agent links');

  const backendFixes = await ctx.task(backendFixAgent, {
    projectRoot,
  });

  const backendVerify = await ctx.task(verifyShell, {
    projectRoot,
    phase: 'backend-fixes',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_interpreter.py tests/scripts/chat/test_executor.py tests/scripts/chat/test_narrator.py -v 2>&1 | tail -30`,
  });

  // ============================================================================
  // PHASE 2: Narrator Prompt Fix (Issue 3)
  // ============================================================================

  ctx.log('info', 'Phase 2: Fix narrator prompt — no followups/confidence in narrative');

  const narratorFix = await ctx.task(narratorFixAgent, {
    projectRoot,
  });

  const narratorVerify = await ctx.task(verifyShell, {
    projectRoot,
    phase: 'narrator-fix',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_narrator.py -v 2>&1 | tail -20`,
  });

  // ============================================================================
  // PHASE 3: Frontend Fixes (Issues 3b, 4, 6)
  // ============================================================================

  ctx.log('info', 'Phase 3: Frontend — link styling, grounding UI, followup rendering');

  const frontendFixes = await ctx.task(frontendFixAgent, {
    projectRoot,
  });

  const frontendVerify = await ctx.task(verifyShell, {
    projectRoot,
    phase: 'frontend-build',
    command: `cd ${projectRoot}/frontend && npm run build 2>&1 | tail -10`,
  });

  // ============================================================================
  // PHASE 4: End-to-end Verification with Playwright
  // ============================================================================

  ctx.log('info', 'Phase 4: E2E verification — restart server, test both queries with Playwright');

  const e2eVerify = await ctx.task(e2eVerifyAgent, {
    projectRoot,
  });

  // ============================================================================
  // PHASE 5: Commit all fixes
  // ============================================================================

  const commitResult = await ctx.task(commitShell, {
    projectRoot,
    command: `cd ${projectRoot} && git add -A && git commit -m "fix: resolve 6 scholar pipeline issues (JSON parsing, narrator prompt, grounding UI, link visibility)"`,
  });

  ctx.log('info', 'All 6 issues fixed and verified');

  return {
    success: true,
    issuesFixed: 6,
    phases: { backendFixes, narratorFix, frontendFixes, e2eVerify },
  };
}

// =============================================================================
// Task Definitions
// =============================================================================

const backendFixAgent = defineTask('backend-fixes', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Fix backend issues: JSON parsing, index remapping, agent links',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python developer fixing bugs in a scholar pipeline',
      task: 'Fix 3 backend issues in the scholar pipeline interpreter and executor',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Fix all 3 issues below. Read the relevant files first, then make targeted edits.',

        'ISSUE 1 - Hebrew gershayim breaks JSON parsing:',
        'File: scripts/chat/interpreter.py, function _convert_llm_step()',
        'The LLM returns params as JSON strings. Hebrew abbreviations like רמב"ם contain literal double-quotes that break json.loads().',
        'Fix: In _convert_llm_step(), before json.loads(llm_step.params), add a JSON repair step.',
        'Strategy: Try json.loads first. On JSONDecodeError, attempt repair:',
        '  - Use regex to find unescaped quotes inside string values: pattern like matching quotes within [...] arrays that are not at array/object boundaries',
        '  - Or use a try/fallback: try the json_repair library if available, else strip problematic chars',
        '  - Simplest robust approach: iterate through the string tracking if we are inside a JSON string (after opening quote, before closing quote), and escape any interior double-quotes that are not already escaped',
        'Add a test: test_convert_step_with_hebrew_gershayim that uses params containing רמב"ם',

        'ISSUE 2 - Step index shifting after skip:',
        'File: scripts/chat/interpreter.py, function _convert_llm_plan()',
        'When invalid steps are skipped, depends_on references in remaining steps still point to the ORIGINAL indices. After filtering, step 1 becomes step 0, but its depends_on:[0] now self-references.',
        'Fix: After filtering, build an old-to-new index map. Remap depends_on in all surviving steps. If a depends_on reference points to a skipped step, remove that reference.',
        'Add a test: test_convert_plan_remaps_depends_on_after_skip',

        'ISSUE 5 - No Wikipedia/Wikidata agent links in grounding:',
        'File: scripts/chat/executor.py, function _collect_grounding()',
        'The grounding collection builds RecordSummary and Primo links but may not be building AgentSummary with external links from authority_enrichment.',
        'Check: Does _collect_grounding() query authority_enrichment for agents found in retrieve results? Does it create GroundingLink entries for wikipedia_url, wikidata_id, viaf_id, nli_id?',
        'Fix if missing: After collecting records, gather unique agent authority_uris from the agents table, join to authority_enrichment, and build AgentSummary + GroundingLink entries.',
        'Add a test if the existing test_grounding_link_collection doesnt already cover agent links.',

        'After all fixes, run: cd ' + args.projectRoot + ' && poetry run pytest tests/scripts/chat/test_interpreter.py tests/scripts/chat/test_executor.py -v',
        'Return JSON: {"success": true/false, "issuesFixed": [...], "testsPassing": true/false}',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['success'],
      properties: {
        success: { type: 'boolean' },
        issuesFixed: { type: 'array', items: { type: 'string' } },
        testsPassing: { type: 'boolean' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
}));

const narratorFixAgent = defineTask('narrator-fix', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Fix narrator prompt: no followups/confidence in narrative text',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python developer fixing narrator LLM prompt',
      task: 'Fix the narrator to NOT include suggested followups or confidence score in the narrative text',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read scripts/chat/narrator.py — find NARRATOR_SYSTEM_PROMPT.',
        'The problem: The LLM includes "Suggested Followups" and "Confidence: 0.95" as headings at the end of the narrative text. These should NOT be in the narrative — they are separate fields in ScholarResponse.',
        'Fix: Add explicit instruction to the system prompt:',
        '"IMPORTANT: Do NOT include suggested follow-up questions or confidence scores in your narrative. These are handled separately by the system. Your narrative should end with the scholarly content — do not add sections like Suggested Followups or Confidence."',
        'Also check _build_narrator_prompt() — make sure the user prompt does NOT ask the LLM to generate followups in the narrative.',
        'The LLM should still generate suggested_followups and confidence as part of NarratorResponseLLM — just not embedded in the narrative text.',
        'Update the test if needed to verify followups are NOT in the narrative.',
        'Run: cd ' + args.projectRoot + ' && poetry run pytest tests/scripts/chat/test_narrator.py -v',
        'Return JSON: {"success": true/false, "testsPassing": true/false}',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['success'],
      properties: { success: { type: 'boolean' }, testsPassing: { type: 'boolean' } },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
}));

const frontendFixAgent = defineTask('frontend-fixes', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Fix frontend: link styling, grounding UI, followup rendering',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior React/TypeScript developer fixing chat UI for a rare books discovery system',
      task: 'Fix 3 frontend issues in the chat interface',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read the frontend chat components in frontend/src/ to understand the structure.',
        'The chat page is at frontend/src/pages/Chat.tsx.',
        'The app uses a dark theme.',

        'ISSUE 3b - Followups rendered as raw text:',
        'The API response has suggested_followups in response.suggested_followups (array of strings).',
        'But the frontend is probably just rendering response.message as raw markdown, which now includes the followups as text.',
        'Check how Chat.tsx renders the response. Make sure it renders suggested_followups as clickable buttons BELOW the message, not inside the message text.',
        'The response structure from the API is: {success, response: {message, suggested_followups, clarification_needed, session_id, phase, confidence, metadata}}.',

        'ISSUE 4 - Links nearly invisible in dark theme:',
        'The chat message renders markdown including [text](url) links. But on the dark background, links have no visual distinction.',
        'Fix: Add CSS for links inside chat messages — use a visible color (e.g., #60a5fa or similar blue), add underline on hover, ensure good contrast ratio.',
        'Look for where markdown is rendered in the chat component and add appropriate link styles.',

        'ISSUE 6 - No structured grounding UI:',
        'The API returns grounding data in response.metadata.grounding with {records: [...], agents: [...], links: [...]}.',
        'Add a collapsible "Sources & References" section below the narrative that shows:',
        '  - Record cards with title, date, place, and a Primo catalog link button',
        '  - Agent profiles with name, dates, and Wikipedia/Wikidata links',
        'Keep it clean and minimal — a collapsible accordion that defaults to collapsed.',
        'Use existing UI patterns from the frontend (check what component library is used).',

        'After all fixes, run: cd ' + args.projectRoot + '/frontend && npm run build',
        'Return JSON: {"success": true/false, "issuesFixed": [...], "buildPassing": true/false}',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['success'],
      properties: {
        success: { type: 'boolean' },
        issuesFixed: { type: 'array', items: { type: 'string' } },
        buildPassing: { type: 'boolean' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
}));

const e2eVerifyAgent = defineTask('e2e-verify', (args, taskCtx) => ({
  kind: 'agent',
  title: 'E2E verification: test both queries with Playwright',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer verifying scholar pipeline fixes in the browser',
      task: 'Verify all 6 fixes work correctly using Playwright browser automation',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'The API server should be running at http://localhost:8000 and frontend at http://localhost:5173.',
        'If they are not running, start them:',
        '  poetry run uvicorn app.api.main:app --reload --port 8000 &',
        '  cd frontend && npm run dev &',
        'Wait for both to be ready.',

        'TEST 1: Navigate to http://localhost:5173, enter "Who was Joseph Karo?" in the chat.',
        'Wait for response. Take a screenshot. Verify:',
        '  - Response has scholarly narrative (not an error)',
        '  - Links are VISIBLE (colored, distinguishable from text)',
        '  - No "Suggested Followups" or "Confidence" headings inside the narrative text',
        '  - Followup buttons appear BELOW the narrative as separate clickable elements',
        '  - Sources/References section exists (may be collapsed)',

        'TEST 2: Enter the Hebrew query: מה לגבי הרמב"ם מי הוא היה? האם יש בקטלוג חומרים שלו?',
        'Wait for response. Take a screenshot. Verify:',
        '  - Response does NOT show an error',
        '  - Response has scholarly content about Maimonides/Rambam',
        '  - Links and grounding work',

        'Use mcp__playwright__browser_navigate, browser_fill_form, browser_press_key, browser_take_screenshot, browser_snapshot tools.',
        'Take screenshots at key points and report what you see.',

        'Return JSON: {"success": true/false, "test1_passed": true/false, "test2_passed": true/false, "screenshots": [...], "issues_remaining": [...]}',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['success'],
      properties: {
        success: { type: 'boolean' },
        test1_passed: { type: 'boolean' },
        test2_passed: { type: 'boolean' },
        screenshots: { type: 'array', items: { type: 'string' } },
        issues_remaining: { type: 'array', items: { type: 'string' } },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
}));

const verifyShell = defineTask('verify', (args, taskCtx) => ({
  kind: 'shell',
  title: `Verify: ${args.phase}`,
  shell: { command: args.command, cwd: args.projectRoot, timeout: 120000 },
  io: { outputJsonPath: `tasks/${taskCtx.effectId}/result.json` },
}));

const commitShell = defineTask('commit', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Commit all fixes',
  shell: { command: args.command, cwd: args.projectRoot, timeout: 30000 },
  io: { outputJsonPath: `tasks/${taskCtx.effectId}/result.json` },
}));
