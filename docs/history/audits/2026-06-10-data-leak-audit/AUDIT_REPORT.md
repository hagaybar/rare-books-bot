# Sensitive-Data Leak Audit — Findings Report

**Date:** 2026-06-10
**Tracks:** GitHub issue #1 ("Security audit: sensitive-data leaks — logs, run artifacts, frontend, deployment")
**Scope:** Repo-wide secret/PII leakage across backend, LLM logging, on-disk artifacts, SQLite DBs, React/Vite frontend, deployment/container, config/fixtures/docs, and git history (sections A–H of the issue).
**Method:** Read-only static audit (bounded grep + targeted code reads). No secret value was printed, echoed, or pasted; findings report file + line + variable **name** only, per repo secret-handling rules.
**Auditor:** Claude Code (Opus 4.8)
**Status:** RESOLVED — all four findings fixed 2026-06-10; full suite green (1443 passed, 21 skipped).

> Audit was performed read-only first (no changes during discovery). Fixes below were
> applied after review, each test-driven (failing test first, then minimal fix).

---

## Executive Summary

The repository is **substantially clean**. The most important result: **no real credential
was ever committed to git history**, and **no logging/output path prints a secret value**.
Existing PII masking and output redaction are wired into the chat paths.

Four actionable findings remain — none is an active secret leak, all are hardening/hygiene:

| ID | Severity | Surface | One-line |
|----|----------|---------|----------|
| **DL-1** | MEDIUM | Deployment | `ADMIN_PASSWORD` passed as a **CLI arg** (visible in container `ps`) |
| **DL-2** | MEDIUM (privacy) | LLM logging | Full system+user prompts persisted to disk **by default**, unredacted |
| **DL-3** | LOW | Redaction | Output redaction is narrow (only `sk-` keys) and not applied before persistence |
| **DL-4** | LOW (hygiene) | Git artifacts | `logs/runs/demo_step1/*` tracked despite `logs/` gitignore — **content verified clean** |

Plus one informational carryover from the auth re-audit (N4: `str(exc)` in admin-only diagnostics).

**Recommendation:** Fix DL-1 and DL-2 (small, contained), optionally DL-3/DL-4, then close issue #1
with the summary comment its acceptance criteria require.

---

## Findings

### DL-1 — `ADMIN_PASSWORD` passed as CLI argument (MEDIUM)

- **Surface:** Deployment / container
- **Location:** `docker/entrypoint.sh:36`
- **What:** `python -m app.cli create-user "$ADMIN_EMAIL" "$ADMIN_PASSWORD" --role admin`
- **Why sensitive:** Command-line arguments are visible to any process via the process list
  (`ps -ef`) inside the container for the lifetime of the call. This is exactly the argv-exposure
  vector the global secret-handling rules call out.
- **Severity rationale:** MEDIUM — requires in-container access to exploit, but the password is a
  real admin credential and the exposure is avoidable.
- **Proposed fix:** Add a `--password-stdin` path to `app.cli create-user` and pipe the value
  (`printf '%s' "$ADMIN_PASSWORD" | python -m app.cli create-user "$ADMIN_EMAIL" --role admin --password-stdin`),
  or read `ADMIN_PASSWORD` from the environment directly inside the CLI rather than from argv.

### DL-2 — LLM logger persists full prompts by default (MEDIUM, privacy)

- **Surface:** LLM logging (flagged by the issue as the highest-risk surface)
- **Location:** `scripts/utils/llm_logger.py:69` (`log_full_prompts: bool = True`),
  persisted at lines 202–204 to `logs/llm_calls.jsonl`; singleton constructed with defaults at line 348.
- **What:** When `log_full_prompts=True` (the default, never overridden anywhere in `app/` or
  `scripts/`), the complete system prompt and user prompt are written verbatim to
  `logs/llm_calls.jsonl`. The **console** summary (lines 224–227) logs only lengths/tokens — good —
  but the on-disk JSONL gets full text.
- **Why sensitive:** Persists full user queries + system context (MARC data) to disk. Email/phone are
  masked upstream (`app/api/main.py:554`, `mask_pii`) before prompt construction, so those are covered;
  but names, free-text queries, and any other content are stored in the clear. This is a privacy/PII
  exposure, not a credential leak (prompts do not carry API keys).
- **Severity rationale:** MEDIUM-privacy — high volume, persistent, on by default; low credential risk.
- **Proposed fix:** Flip the default to `log_full_prompts=False` (preview-only is already supported at
  lines 70/206–211) and make full-prompt logging an explicit opt-in for debugging. `logs/` is gitignored
  and rsync-excluded, so this is about data-at-rest on the host, not shipping.

### DL-3 — Output redaction is narrow and not applied before persistence (LOW)

- **Surface:** Existing redaction (section D verification)
- **Location:** `app/api/security.py:142–144`; applied at `app/api/main.py:604, 1087`.
- **What:** `validate_output()` redacts only `sk-[a-zA-Z0-9]{20,}` (OpenAI/Anthropic key shape),
  literal `JWT_SECRET`, and `password_hash`. It does **not** cover bearer tokens, generic
  `Authorization:` headers, or DB connection strings. It is applied only to **user-facing** output —
  not before prompts are persisted by the LLM logger (DL-2) or before writes to `sessions.db`.
- **Why sensitive:** Defense-in-depth gap. In practice low risk because the inputs being persisted
  are user queries + MARC data, which should not contain keys; but the redaction does not hold on the
  persistence path the issue specifically asked about.
- **Proposed fix:** Broaden the redaction pattern set (bearer tokens, connection strings) and apply
  `validate_output()` (or a shared redactor) in the logger write path, not just on user-facing output.

### DL-4 — Committed run artifacts despite gitignore (LOW, hygiene)

- **Surface:** Git artifacts (the issue's "known lead")
- **Location (tracked in git):** `logs/runs/demo_step1/llm_prompt.txt`,
  `logs/runs/demo_step1/llm_response.txt`, `logs/runs/demo_step1/run_metadata.json`
- **What:** These three files are tracked even though `logs/` is gitignored (`.gitignore:155`).
- **Content — VERIFIED CLEAN:** `llm_prompt.txt` = `"Hello from Step 1"` (17 B),
  `llm_response.txt` = `"World from Step 1"` (17 B), `run_metadata.json` = `{"ok":…,"note":…}` (41 B).
  No key, token, URL, or identifiable data. Secret-pattern scan: 0 hits per file.
- **Why it matters:** No leak today, but tracking files under a gitignored `logs/` path normalizes
  committing run artifacts — a future real run could be committed by habit.
- **Proposed fix:** `git rm --cached logs/runs/demo_step1/*` and regenerate the demo on demand, so the
  gitignore is the single source of truth for `logs/`.

### INFO — Diagnostics `str(exc)` in error responses (carryover, accepted)

- **Location:** `app/api/diagnostics.py:131, 149, 438`
- **What:** Exception text is passed into HTTP error details / regression results.
- **Status:** All diagnostics endpoints require `role=full` (operator-only); already documented as
  accepted in `docs/history/reports/security-reaudit.md` (finding N4). No action unless the diagnostics
  API is exposed to lower-privilege users. The same pattern exists in `interaction_logger`'s `error`
  field (`scripts/metadata/interaction_logger.py:64`) — operational metadata, no credentials.

---

## Verified Clean (per section)

| Section | Result |
|---------|--------|
| **A — Python logging/output** | No call prints a secret value. Warnings reference variable **names** only (`auth_service.py:24`, `security.py:100`). `print()`s are stats/progress; `traceback.print_exc()` in `cli.py:272`/`marc/parse.py:866` is local CLI only. |
| **B — LLM logging** | Console summary logs lengths/tokens only. On-disk full-prompt persistence → **DL-2**. `llm_client.py` logs no key/config/raw error object (only `logger.debug` model name at line 135). |
| **C — On-disk artifacts/DBs** | Writers persist MARC/QA/eval/normalization data (alias maps, geocodes, candidate sets `execute.py:670`, query plans `compile.py:25`) — record IDs and bibliographic data, not credentials. Prompt/response persistence is centralized in the LLM logger (DL-2). |
| **D — Existing redaction** | `mask_pii` + `validate_output` wired into chat paths (`main.py:554, 604, 960, 1087`). Coverage gaps → **DL-3**. |
| **E — Frontend** | No `VITE_*` secret, no frontend `.env`. `localStorage` holds only a session id (`appStore.ts:16/25`). One `console.warn` (`Chat.tsx:558`) logs a WebSocket error message, not tokens/responses. Passwords live in form state only. JWT is in an httponly cookie (per auth audit), not JS-readable storage. |
| **F — Deployment/container** | `deploy.sh` rsync excludes `.env`, `.env.*`, `*.env`, `logs/`, `data/` (lines 85–89) — secrets/artifacts not shipped. `Dockerfile` bakes no secret. `docker/nginx.conf` mounts cert paths (40–41), sets HSTS (48). Admin-password argv → **DL-1**. |
| **G — Config/fixtures/docs** | `data/eval/model-config.json` holds model names only. No `.env.example`. `tests/app/conftest.py` generates JWTs dynamically via `create_access_token` — no hardcoded secret. README `sk-...` is a literal placeholder (`README.md:77`, `app/api/README.md:161`). |
| **H — Git history** | **0 commits** ever introduced a real 20+ char key shape. The only `sk-` literal in the tree is a false positive: `ta`**`sk-s`**`pecific` inside a docstring (`scripts/utils/logger.py:39`). `OPENAI_API_KEY`/`JWT_SECRET` history hits are env-var **name** references in code/docs, not values. Known-lead artifacts → **DL-4** (clean). |

---

## Resolution (2026-06-10)

All four findings fixed, test-driven (RED → GREEN), full suite green afterward.

| ID | Fix | Code | Tests |
|----|-----|------|-------|
| DL-1 | `create-user` accepts `--password-stdin`; entrypoint pipes the password via stdin, not argv | `app/cli.py`, `docker/entrypoint.sh:36` | `tests/app/test_cli_create_user.py` |
| DL-2 | `log_full_prompts` now defaults to `False` (preview-only) | `scripts/utils/llm_logger.py:69` | `tests/scripts/utils/test_llm_logger.py::TestLLMLoggerPrivacyDefaults` |
| DL-3 | Shared `redact_secrets` (API keys, bearer tokens, JWT secret, password_hash, conn-string creds); applied before LLM-log persistence and via `validate_output` | `scripts/utils/redaction.py`, `app/api/security.py`, `scripts/utils/llm_logger.py` | `tests/scripts/utils/test_redaction.py`, `tests/app/test_security_redaction.py` |
| DL-4 | `logs/runs/demo_step1/*` untracked (`git rm --cached`); still gitignored | `.gitignore` (already covered `logs/`) | n/a (verified clean) |

## Acceptance-criteria status (issue #1)

- [x] Every section A–H worked through
- [x] All findings documented (surface, path, line, category, severity, proposed fix)
- [x] "Known lead" `logs/runs/demo_step1/*` inspected and resolved (clean; untracked)
- [x] Proposed fixes applied (all four), test-driven; full suite green
- [x] Summary comment added to issue #1; issue closed
