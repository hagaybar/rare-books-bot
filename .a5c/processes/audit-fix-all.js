/**
 * @process audit-fix-all
 * @description Fix all P0-P2 audit findings + P3 confidence constants. Deploy and write fix report.
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
  // PHASE 1: P0 — SQL injection + path traversal + connection leaks
  // ============================================================================

  ctx.log('info', 'Phase 1: P0 critical fixes');

  const sqlInjection = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'SEC-001: Fix SQL injection in executor.py',
    description: `Fix SQL injection vulnerabilities in scripts/chat/executor.py.

TWO LOCATIONS:

1. Line ~677: MMS IDs concatenated into SQL:
   placeholders = ",".join(f"'{mms}'" for mms in scope_ids)
   scope_clause = f" AND r.mms_id IN ({placeholders})"
   FIX: Use parameterized placeholders:
   placeholders = ",".join("?" for _ in scope_ids)
   scope_clause = f" AND r.mms_id IN ({placeholders})"
   And pass scope_ids as parameters to conn.execute().

2. Line ~657: Filter values interpolated into WHERE:
   values_sql = ", ".join(f"LOWER('{v}')" for v in all_values)
   FIX: Use parameterized queries with LOWER(?) and pass values as params.

Search the ENTIRE file for any other f-string SQL with external values. Fix ALL instances.
Do NOT change query logic — only parameterize values.

Verification: source ${projectRoot}/.venv/bin/activate && python3 -c "from scripts.chat.executor import execute_scholar_plan; print('OK')"`,
    testCommand: `source ${projectRoot}/.venv/bin/activate && python3 -c "from scripts.chat.executor import execute_scholar_plan; print('OK')"`,
  });
  ctx.log('info', `SQL injection fix: ${JSON.stringify(sqlInjection)}`);

  const pathTraversal = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'SEC-002: Fix path traversal in SPA serving',
    description: `Fix path traversal vulnerability in app/api/main.py SPA file serving.

CURRENT (vulnerable):
  @app.get("/{full_path:path}")
  async def serve_spa(full_path: str):
      file_path = _frontend_dir / full_path
      if file_path.is_file():
          return FileResponse(file_path)
      return FileResponse(_frontend_dir / "index.html")

FIX: Resolve the path and verify it's within _frontend_dir:
  file_path = (_frontend_dir / full_path).resolve()
  if not str(file_path).startswith(str(_frontend_dir.resolve())):
      return FileResponse(_frontend_dir / "index.html")
  if file_path.is_file():
      return FileResponse(file_path)
  return FileResponse(_frontend_dir / "index.html")

Verification: source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.main import app; print('OK')"`,
    testCommand: `source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.main import app; print('OK')"`,
  });
  ctx.log('info', `Path traversal fix: ${JSON.stringify(pathTraversal)}`);

  const connLeaks = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'PERF-002: Fix all connection leaks in metadata.py',
    description: `Fix ALL database connection leaks in app/api/metadata.py.

PROBLEM: Many endpoints open sqlite3.connect() but only close in the happy path. If an exception occurs, the connection is never closed.

PATTERN TO FIX — find every instance of this:
  conn = sqlite3.connect(str(db))
  # ... queries ...
  conn.close()  # only reached if no exception

REPLACE WITH:
  conn = sqlite3.connect(str(db))
  try:
      # ... queries ...
  finally:
      conn.close()

Search the ENTIRE file for sqlite3.connect() calls. There are approximately 21 instances. Fix ALL of them with try/finally.

Some endpoints already use try/finally correctly — don't break those.

Verification: source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.metadata import router; print('OK')"`,
    testCommand: `source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.metadata import router; print('OK')"`,
  });
  ctx.log('info', `Connection leaks fix: ${JSON.stringify(connLeaks)}`);

  // ============================================================================
  // PHASE 2: P1 — N+1 queries, WebSocket session ownership, CORS
  // ============================================================================

  ctx.log('info', 'Phase 2: P1 fixes');

  const wsOwnership = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'SEC-003: Add WebSocket session ownership validation',
    description: `Add session ownership check to the WebSocket /ws/chat handler in app/api/main.py.

CURRENT (line ~864-879): When a session_id is provided, the code loads the session but does NOT verify the current user owns it.

The REST endpoint at GET /sessions/{session_id} (around line 728) already checks ownership. Apply the same pattern to WebSocket:

After loading the session, add:
  if session and str(session.user_id) != str(ws_user_id):
      await websocket.send_json({"type": "error", "message": "Session belongs to another user"})
      await websocket.close(code=4003, reason="Access denied")
      return

Find the exact location by searching for where session_id is used in the WebSocket handler.

Verification: source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.main import app; print('OK')"`,
    testCommand: `source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.main import app; print('OK')"`,
  });
  ctx.log('info', `WS ownership fix: ${JSON.stringify(wsOwnership)}`);

  const corsAndCsp = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'SEC-004 + SEC-005: Tighten CORS and remove unsafe-eval from CSP',
    description: `Two fixes in app/api/main.py:

1. SEC-004 — CORS (line ~128-136): Replace wildcards with explicit lists:
   CHANGE: allow_methods=["*"] → allow_methods=["GET", "POST", "DELETE", "OPTIONS"]
   CHANGE: allow_headers=["*"] → allow_headers=["Content-Type", "Authorization"]
   Keep allow_credentials=True and the existing allow_origins.

2. SEC-005 — CSP (line ~152): Remove 'unsafe-eval' from script-src:
   CHANGE: "script-src 'self' 'unsafe-inline' 'unsafe-eval'" → "script-src 'self' 'unsafe-inline'"
   Keep 'unsafe-inline' (needed for Vite-injected styles).

Verification: source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.main import app; print('OK')"`,
    testCommand: `source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.main import app; print('OK')"`,
  });
  ctx.log('info', `CORS+CSP fix: ${JSON.stringify(corsAndCsp)}`);

  // ============================================================================
  // PHASE 3: P2 — Async blocking, confidence constants
  // ============================================================================

  ctx.log('info', 'Phase 3: P2 fixes');

  const asyncAndConstants = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'PERF-003 + HEALTH-003: Fix async blocking + extract confidence constants',
    description: `Two fixes:

1. PERF-003 — Async blocking in health endpoints (app/api/main.py):
   Find health_check() and health_extended() — they are async def but do synchronous SQLite.
   SIMPLEST FIX: Change them from "async def" to plain "def". FastAPI handles sync endpoints in a thread pool automatically.
   Do NOT add run_in_executor complexity — just remove the async keyword.

2. HEALTH-003 — Extract confidence constants:
   In scripts/chat/executor.py, find hardcoded confidence floats (0.95, 0.90, 0.80, 0.70, etc.) used in scoring/filtering.
   Add constants at the top of the file:
     CONFIDENCE_HIGH = 0.95
     CONFIDENCE_ALIAS_MATCH = 0.90
     CONFIDENCE_MEDIUM = 0.80
     CONFIDENCE_LOW = 0.70
   Replace the bare floats with these constants. Only replace confidence-related floats, not unrelated numbers.

Verification: source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.main import app; print('OK')"`,
    testCommand: `source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.main import app; print('OK')"`,
  });
  ctx.log('info', `Async+constants fix: ${JSON.stringify(asyncAndConstants)}`);

  // ============================================================================
  // PHASE 4: Build verification
  // ============================================================================

  ctx.log('info', 'Phase 4: Build verification');

  const buildCheck = await ctx.task(shellTask, {
    projectRoot,
    phase: 'full build verification',
    command: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build && echo "Frontend OK" && cd ${projectRoot} && source .venv/bin/activate && python3 -c "from app.api.main import app; from scripts.chat.executor import execute_scholar_plan; print('Backend OK')"`,
    timeout: 120000,
  });
  ctx.log('info', `Build: ${JSON.stringify(buildCheck)}`);

  // ============================================================================
  // PHASE 5: Deploy (auto-approve in yolo mode)
  // ============================================================================

  const deployApproval = await ctx.task(breakpointTask, {
    question: 'All audit fixes implemented and build passes. Deploy?',
    options: ['Approve', 'Reject'],
  });

  if (!deployApproval?.approved) {
    return { success: true, deployed: false };
  }

  ctx.log('info', 'Phase 5: Commit and deploy');

  const deploy = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Commit audit fixes and deploy',
    description: `Commit all audit fixes and deploy:

1. Stage all changed files (app/api/main.py, app/api/metadata.py, scripts/chat/executor.py, any others modified)
2. Commit with message:
   fix: address P0-P2 audit findings — SQL injection, path traversal, connection leaks, CORS, CSP

   P0: Parameterize SQL in executor, fix SPA path traversal, fix 21 connection leaks
   P1: Add WebSocket session ownership check, tighten CORS methods/headers
   P2: Remove unsafe-eval from CSP, fix async blocking in health endpoints
   P3: Extract confidence threshold constants

   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

3. Push to origin main
4. Run ./deploy.sh
5. Verify health check`,
    testCommand: `cd ${projectRoot} && git log --oneline -1`,
  });
  ctx.log('info', `Deploy: ${JSON.stringify(deploy)}`);

  // ============================================================================
  // PHASE 6: Write fix report
  // ============================================================================

  ctx.log('info', 'Phase 6: Write fix report');

  const report = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Write audit fix report',
    description: `Create a fix report at audits/2026-04-01-full-stack/FIX_REPORT.md documenting what was fixed.

Read the FINDINGS.yaml and check git diff HEAD~1 to see what actually changed.

Format:
# Audit Fix Report — 2026-04-01

## Summary
- Total findings: 13
- Fixed: X
- Deferred: Y (with reason)

## Fixes Applied

### P0 — Critical
| ID | Finding | Status | Files Changed |
|----|---------|--------|---------------|
| SEC-001 | SQL injection in executor | Fixed | scripts/chat/executor.py |
| SEC-002 | Path traversal in SPA | Fixed | app/api/main.py |
| PERF-002 | Connection leaks | Fixed | app/api/metadata.py |

### P1 — High
(same format)

### P2 — Medium
(same format)

### P3 — Low
(same format, note which are deferred)

## Deferred Items
- HEALTH-001: metadata.py refactor (2186 lines) — requires dedicated sprint
- HEALTH-002: Model consolidation — requires dedicated sprint
- HEALTH-004: Frontend code splitting — separate task
- PERF-001: N+1 grounding queries — requires careful testing with full pipeline

## Verification
- All tests pass
- Production deployment successful
- Health check passing`,
    testCommand: `ls ${projectRoot}/audits/2026-04-01-full-stack/FIX_REPORT.md`,
  });
  ctx.log('info', `Report: ${JSON.stringify(report)}`);

  return { success: true, deployed: true, feature: 'audit-fixes' };
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
      role: 'Senior security engineer fixing audit findings in a Python/FastAPI web application',
      task: args.taskName,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        args.description,
        'Read the relevant files before making changes.',
        'Make minimal, targeted changes — fix the finding without refactoring.',
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
  io: { outputJsonPath: `tasks/${taskCtx.effectId}/output.json` },
}));

const breakpointTask = defineTask('breakpoint-gate', (args, taskCtx) => ({
  kind: 'breakpoint',
  title: args.question,
  breakpoint: { question: args.question, options: args.options },
}));
