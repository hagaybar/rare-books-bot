/**
 * @process auth-plan-a
 * @description Auth Plan A: Core backend — DB, JWT, routes, role deps, CLI. 7 tasks.
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;
  const plan = 'docs/superpowers/plans/2026-03-28-auth-plan-a-core.md';

  ctx.log('info', 'Auth Plan A: Core backend (7 tasks)');

  // Task 1+2: Dependencies + DB + Service (combined — foundational, no deps between them)
  const foundation = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Tasks 1+2: Dependencies, auth DB, auth models, auth service',
    description: `Read ${plan} — Tasks 1 and 2 completely.

1. Install dependencies: poetry add PyJWT "passlib[bcrypt]"
2. Create app/api/auth_db.py — auth database schema (users, refresh_tokens, token_usage, settings, audit_log). Use EXACT code from plan.
3. Create app/api/auth_models.py — Pydantic models (LoginRequest, TokenResponse, UserInfo, CreateUserRequest, UpdateUserRequest, UserListItem). Use EXACT code from plan.
4. Create app/api/auth_service.py — password hashing, JWT create/validate, authenticate_user, create_user, audit_log, refresh token management. Use EXACT code from plan. Auto-generate JWT_SECRET if not set (dev mode).

Verify:
  poetry run python -c "from app.api.auth_db import init_auth_db; init_auth_db(); print('DB OK')"
  poetry run python -c "from app.api.auth_service import hash_password, create_access_token; print('Service OK')"

Commit: git add pyproject.toml poetry.lock app/api/auth_db.py app/api/auth_models.py app/api/auth_service.py && git commit -m "feat: add auth database, models, and service (JWT + bcrypt)"`,
    testCommand: `cd ${projectRoot} && poetry run python -c "from app.api.auth_service import hash_password, verify_password; h = hash_password('test'); assert verify_password('test', h); print('OK')"`,
  });

  // Task 3: Auth dependencies
  const deps = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 3: Auth dependencies (role enforcement)',
    description: `Read ${plan} — Task 3. Create app/api/auth_deps.py with get_current_user (extracts JWT from cookie) and require_role factory (returns dependency requiring minimum role level). ROLE_HIERARCHY: admin=4, full=3, limited=2, guest=1. Use EXACT code from plan.

Verify: poetry run python -c "from app.api.auth_deps import require_role, get_current_user; print('OK')"
Commit: git add app/api/auth_deps.py && git commit -m "feat: add auth dependencies — get_current_user, require_role"`,
    testCommand: `cd ${projectRoot} && poetry run python -c "from app.api.auth_deps import require_role; print('OK')"`,
  });

  // Task 4: Auth routes
  const routes = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 4: Auth routes (login, guest, refresh, me, user CRUD)',
    description: `Read ${plan} — Task 4. Create app/api/auth_routes.py with FastAPI router at /auth prefix. Endpoints: POST /login, POST /guest, POST /refresh, POST /logout, GET /me, GET /users (admin), POST /users (admin), PUT /users/{id} (admin). Use httpOnly cookies for JWT. Use EXACT code from plan.

Verify: poetry run python -c "from app.api.auth_routes import router; print(f'Routes: {len(router.routes)}')"
Commit: git add app/api/auth_routes.py && git commit -m "feat: add auth routes — login, guest, refresh, me, user CRUD"`,
    testCommand: `cd ${projectRoot} && poetry run python -c "from app.api.auth_routes import router; print(f'Routes: {len(router.routes)}')"`,
  });

  // Task 5: Mount + protect existing routes
  const mount = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 5: Mount auth router + protect existing endpoints',
    description: `Read ${plan} — Task 5.

In app/api/main.py:
1. Import and mount auth router: from app.api.auth_routes import router as auth_router; app.include_router(auth_router)
2. Import init_auth_db and call on startup: add @app.on_event("startup") handler that calls init_auth_db()
3. Update CORS: read CORS_ORIGIN from env var, default to ["*"] for dev

For protecting existing endpoints, add Depends(require_role(...)) to the key endpoints:
- The /chat POST endpoint needs Depends(require_role("limited"))
- The /ws/chat WebSocket needs JWT validation from cookies at connection
- The /network/* endpoints need Depends(require_role("guest"))
- The /metadata/enrichment/* public endpoints need Depends(require_role("guest"))
- The /metadata/coverage, /metadata/issues, /metadata/corrections, /metadata/agent/chat endpoints need Depends(require_role("full"))
- The /diagnostics/* endpoints need Depends(require_role("full"))
- The /health endpoint stays public (no auth)

IMPORTANT: Be careful not to break existing functionality. Add the dependencies as additional parameters to existing endpoint functions. If an endpoint is in a separate router file (metadata.py, network.py, diagnostics.py), import require_role there and add to the specific endpoints.

Test: Start the server (poetry run uvicorn app.api.main:app --port 8765) and verify:
  curl -s http://localhost:8765/health — should return 200 (public)
  curl -s http://localhost:8765/auth/guest -X POST — should return 200 with cookie
  curl -s http://localhost:8765/network/map?connection_types=none&limit=1 — should return 401 (no cookie)

Kill the server after testing.

Commit: git add app/api/ && git commit -m "feat: mount auth router, protect existing endpoints with role deps"`,
    testCommand: `cd ${projectRoot} && poetry run python -c "from app.api.main import app; print(f'App routes: {len(app.routes)}')"`,
  });

  // Task 6: CLI create-user
  const cli = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 6: CLI create-user command',
    description: `Read ${plan} — Task 6. Add create-user command to app/cli.py using Typer. Takes username and password as arguments, --role as option (default admin). Calls init_auth_db() then create_user().

Test: poetry run python -m app.cli create-user testadmin testpass123 --role admin
Verify: poetry run python -c "from app.api.auth_db import get_auth_db; c=get_auth_db(); print([dict(r)['username'] for r in c.execute('SELECT username FROM users').fetchall()])"

Commit: git add app/cli.py && git commit -m "feat: add create-user CLI command for admin bootstrapping"`,
    testCommand: `cd ${projectRoot} && poetry run python -m app.cli create-user clitest clipass12345 --role full 2>&1 | head -3`,
  });

  // Task 7: Tests
  const tests = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 7: Auth endpoint tests',
    description: `Read ${plan} — Task 7. Create tests/app/test_auth.py with tests for: login success, login wrong password, guest session, /me endpoint, /me without auth, admin list users, non-admin cannot list users. Use tmp_path + monkeypatch to isolate auth DB. Use EXACT test code from plan.

Run: poetry run pytest tests/app/test_auth.py -v
All tests must pass.

Commit and push: git add tests/app/test_auth.py && git commit -m "feat: add auth endpoint tests" && git push origin feature/auth-security`,
    testCommand: `cd ${projectRoot} && poetry run pytest tests/app/test_auth.py -v 2>&1 | tail -15`,
  });

  ctx.log('info', 'Auth Plan A complete');
  return { success: true };
}

const agentTask = defineTask('auth-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior backend developer implementing authentication system',
      task: args.taskName,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        'Branch: feature/auth-security (already checked out)',
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
