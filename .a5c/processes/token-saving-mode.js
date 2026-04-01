/**
 * @process token-saving-mode
 * @description Implement dual-mode token-saving for narrator LLM calls — lean records by default, full payload as opt-out
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
  // PHASE 1: Implement lean record builder in narrator.py
  // ============================================================================

  ctx.log('info', 'Phase 1: Implement lean record builder');

  const leanBuilder = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Implement lean narrator prompt builder with selective agent inclusion',
    description: `Add a lean prompt-building mode to the narrator in scripts/chat/narrator.py.

CURRENT STATE:
- _build_narrator_prompt() at line ~400 assembles full records into the narrator's user prompt
- It includes: COLLECTION RECORDS, AGENT PROFILES, AGGREGATION RESULTS, AVAILABLE LINKS, SESSION CONTEXT
- The narrator user prompt is ~19,829 chars / ~7,351 input tokens for a typical query

CHANGES NEEDED:

1. Add function build_lean_narrator_prompt(query, result) alongside _build_narrator_prompt().

   COLLECTION RECORDS section — per record include:
   * mms_id, title, date_display, publisher, primo_url (ALWAYS)
   * language: ONLY if the result set has mixed languages
   * agents: up to 2, selected by role relevance — printer/publisher FIRST, then author/editor. NOT the first 2 blindly. Look at the agent's role_raw or role field to pick.
   * subjects: up to 2, ONLY if they help justify why this item belongs (i.e. the query mentions a subject or topic)
   * DROP: full agent lists, full subject lists, source_steps, separate place field

   AGENT PROFILES section — RADICAL REDUCTION:
   * Include 0-3 agent profiles total, NOT all agents
   * Selection logic (deterministic, no LLM):
     a) If a step in execution had action "resolve_agent" or "enrich", include that agent
     b) If an agent appears in 3+ records in the result set, include them
     c) If the query mentions "printer"/"publisher"/"author" and an agent matches, include them
     d) Otherwise include ZERO agent profiles
   * When included, each profile has: canonical_name, birth/death years, description, record_count, ONE link (Wikipedia preferred)
   * Do NOT trim all agents to 200 chars. Just include fewer agents.

   AGGREGATION RESULTS: top 5 per field (not 20). Drop fields with only 1 value.

   AVAILABLE LINKS section: DROP ENTIRELY (redundant — URLs already in records + agent profiles).

   Keep unchanged: USER QUERY, SCHOLARLY DIRECTIVES, SESSION CONTEXT, TRUNCATION NOTICE.

2. Modify narrate() signature: add token_saving: bool = True, pass to _call_llm().

3. Modify _call_llm(): if token_saving, use build_lean_narrator_prompt(); else use _build_narrator_prompt().

4. Do NOT change the system prompt, model, or response parsing.
5. Do NOT change the interpreter or executor.

IMPORTANT: Read the full _build_narrator_prompt() function and the ExecutionResult/GroundingData models before implementing. Match the exact formatting style of the existing function.`,
    testCommand: `cd ${projectRoot} && python3 -c "from scripts.chat.narrator import narrate, build_lean_narrator_prompt; print('OK')"`,
  });

  ctx.log('info', `Lean builder: ${JSON.stringify(leanBuilder)}`);

  const verify1 = await ctx.task(shellTask, {
    projectRoot,
    phase: 'phase 1 import check',
    command: `cd ${projectRoot} && python3 -c "from scripts.chat.narrator import narrate, build_lean_narrator_prompt; print('Both functions importable')"`,
  });

  ctx.log('info', `Verify 1: ${JSON.stringify(verify1)}`);

  // ============================================================================
  // PHASE 2: Add section-size logging
  // ============================================================================

  ctx.log('info', 'Phase 2: Section-size logging');

  const logging = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Add comparison logging with section sizes to narrator and llm_logger',
    description: `Add metadata logging so we can measure and compare lean vs full prompts.

CHANGES:

1. In scripts/chat/narrator.py _call_llm():
   When calling log_llm_call(), pass extra_metadata with:
   - "token_saving_mode": "lean" if token_saving else "full"
   - "prompt_char_count": len(user_prompt)
   - "record_count": len(result.grounding.records) if result.grounding else 0
   - "agent_profile_count": number of agent profiles actually included in the prompt
   This metadata will be written to the JSONL log automatically.

2. In app/api/main.py, both HTTP /chat and WebSocket /ws/chat handlers:
   - Read token_saving from the request (default True)
   - Pass it to narrate(query, execution_result, token_saving=token_saving)
   - For HTTP: read from request body field "token_saving" (bool, default True)
   - For WebSocket: read from the incoming JSON message field "token_saving" (bool, default True)
   - Find the ChatRequest model (in scripts/chat/models.py or app/api/main.py) and add token_saving: bool = True field

3. Do NOT change the log_llm_call function signature — use extra_metadata parameter.`,
    testCommand: `cd ${projectRoot} && python3 -c "from scripts.chat.narrator import narrate; print('OK')"`,
  });

  ctx.log('info', `Logging: ${JSON.stringify(logging)}`);

  // ============================================================================
  // PHASE 3: Build check (before UI, validate backend works)
  // ============================================================================

  ctx.log('info', 'Phase 3: Backend build check');

  const backendCheck = await ctx.task(shellTask, {
    projectRoot,
    phase: 'backend verification',
    command: `cd ${projectRoot} && python3 -c "from scripts.chat.narrator import narrate, build_lean_narrator_prompt; from app.api.main import app; print('All imports OK')"`,
  });

  ctx.log('info', `Backend check: ${JSON.stringify(backendCheck)}`);

  // ============================================================================
  // PHASE 4: UI toggle checkbox
  // ============================================================================

  ctx.log('info', 'Phase 4: UI toggle');

  const uiToggle = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Add "No token saving" checkbox to Chat UI',
    description: `Add a small checkbox toggle to the Chat page.

CHANGES in frontend/src/pages/Chat.tsx:

1. Add state: const [tokenSaving, setTokenSaving] = useState(true)

2. Add a small checkbox near the input area (below the token usage display, above or beside the textarea). Keep it unobtrusive:
   <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer">
     <input type="checkbox" checked={!tokenSaving} onChange={(e) => setTokenSaving(!e.target.checked)} className="w-3 h-3" />
     No token saving
   </label>

3. Pass tokenSaving in the WebSocket message:
   ws.send(JSON.stringify({ message: trimmed, session_id: sessionId, token_saving: tokenSaving }))

4. Pass tokenSaving in the HTTP fallback body:
   body: JSON.stringify({ message: trimmed, session_id: sessionId, token_saving: tokenSaving })

Keep the change minimal. Do NOT change any other UI components.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit`,
  });

  ctx.log('info', `UI toggle: ${JSON.stringify(uiToggle)}`);

  // ============================================================================
  // PHASE 5: Full build verification
  // ============================================================================

  ctx.log('info', 'Phase 5: Full build verification');

  const buildCheck = await ctx.task(shellTask, {
    projectRoot,
    phase: 'full build verification',
    command: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build`,
    timeout: 120000,
  });

  ctx.log('info', `Build: ${JSON.stringify(buildCheck)}`);

  // ============================================================================
  // PHASE 6: Deploy breakpoint
  // ============================================================================

  const deployApproval = await ctx.task(breakpointTask, {
    question: 'Token-saving mode implemented and build passes. Ready to commit, push, and deploy?',
    options: ['Approve - commit and deploy', 'Reject - review first'],
  });

  if (!deployApproval?.approved) {
    ctx.log('info', 'Deployment rejected');
    return { success: true, deployed: false };
  }

  // ============================================================================
  // PHASE 7: Commit, push, deploy
  // ============================================================================

  ctx.log('info', 'Phase 7: Commit and deploy');

  const deploy = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Commit and deploy token-saving mode',
    description: `Commit all changes and deploy:

1. Stage all changed files (scripts/chat/narrator.py, app/api/main.py, scripts/utils/llm_logger.py, frontend/src/pages/Chat.tsx, any model files)

2. Commit with message:
   feat: add token-saving mode for narrator LLM calls

   Lean mode (default) sends compact records with selective agent
   inclusion (0-3 query-relevant agents instead of all). Full mode
   available via "No token saving" checkbox. Comparison logging added.

   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

3. Push to origin main
4. Run ./deploy.sh
5. Verify health check: ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 "curl -sf http://127.0.0.1:8001/health"`,
    testCommand: `cd ${projectRoot} && git log --oneline -1`,
  });

  ctx.log('info', `Deploy: ${JSON.stringify(deploy)}`);

  return {
    success: true,
    deployed: true,
    feature: 'token-saving-mode',
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
      role: 'Senior Python/React developer implementing token optimization for a rare books chatbot',
      task: args.taskName,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        args.description,
        'Read the relevant files before making changes.',
        'Make minimal, targeted changes — do not refactor unrelated code.',
        `Verification: ${args.testCommand}`,
        'Return JSON summary: { taskName, status, filesChanged, details }',
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
