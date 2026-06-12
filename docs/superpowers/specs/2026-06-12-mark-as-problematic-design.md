# "Mark as Problematic" — Chat Feedback to GitHub Issues

**Date**: 2026-06-12
**Status**: Approved (user, 2026-06-12; design dialogue in-session)
**Issue tracker target**: `hagaybar/rare-books-bot` (public repo)

## Purpose

Testers using the chat notice wrong or odd results. They need a one-click way to
send everything a debugger needs — packaged as a GitHub issue — with an optional
comment. Two entry points:

1. **Per-message**: a "Report" action on every completed assistant chat message.
2. **General**: a "Report a problem" button (header), for errors not tied to a
   specific message; comment required there.

## Key decisions (user-approved)

| Decision | Choice |
|---|---|
| Privacy (repo is PUBLIC) | **Slim issue + server file**: the GitHub issue carries only a summary; the full debug payload is stored server-side at `data/feedback/<report_id>.json` and referenced by Report ID. |
| Access | Anyone who can chat (`limited` role+, same gate as `POST /chat`), plus session-ownership check. |
| Payload scope | **Whole session** up to and including the flagged message — every turn with its persisted `query_plan` + `candidate_set` (already stored in `chat_messages`). |
| Resilience | **Save first, sync later**: report is persisted before any GitHub call; issue creation is best-effort; pending reports are retried (piggyback on next report + admin sync endpoint). |
| Integration | **Backend-native** (approach A): `httpx` call to the GitHub REST API with a server-side `GITHUB_TOKEN`. |

## Architecture

```
MessageBubble [flag btn] ─┐
Header [report btn] ──────┤→ FeedbackDialog → POST /feedback (api/feedback.ts)
                                                  │
                              app/api/feedback_routes.py
                              │  auth (limited+) · ownership · rate limit (5/min/user) · audit log
                              ▼
                scripts/feedback/report_store.py
                │  assemble_session_payload() ← sessions.db (chat_messages.query_plan/candidate_set)
                │  create_report() → feedback_reports row + data/feedback/<id>.json
                ▼
                scripts/feedback/github_client.py  (best-effort)
                   create_issue() → github.com REST · GITHUB_TOKEN env
                   success → mark_synced(issue_url) · failure → sync_status='pending'
```

### Backend units

**`scripts/feedback/report_store.py`** — pure/SQLite logic, no network:
- `assemble_session_payload(session_id, message_id | None) -> dict` — all session
  turns up to & incl. the flagged message (role, content, query_plan,
  candidate_set, timestamps), session metadata, app git SHA, assembled_at.
- `create_report(...) -> Report` — inserts `feedback_reports` row, writes payload
  JSON to `data/feedback/<report_id>.json`. Report ID format: `fb_<utc-ts>_<6hex>`.
- `list_pending()`, `mark_synced(report_id, issue_url, issue_number)`.
- Payload assembly failure must NOT lose the report: save the row + comment with
  whatever payload parts succeeded, note the error in the JSON.

**`scripts/feedback/github_client.py`**:
- `create_issue(title, body, labels) -> (url, number)` via `httpx` POST
  `/repos/{FEEDBACK_REPO}/issues`.
- `GITHUB_TOKEN` read from env at call time; **never logged, never echoed in
  errors**. Missing token → `FeedbackSyncDisabled` (report stays `pending`).
- `FEEDBACK_REPO` env, default `hagaybar/rare-books-bot`.

**`app/api/feedback_routes.py`**:
- `POST /feedback` (role `limited`+): body `{kind: 'message'|'general',
  session_id?: str, message_id?: int, comment?: str}` (`message_id` is the
  backend `chat_messages.id`).
  - `kind='message'`: `session_id` + `message_id` required; comment optional.
  - `kind='general'`: comment required; `session_id` optional (attach current
    session for context when present).
  - Ownership: non-admin users may only report their own sessions (reuse the
    GET /sessions ownership rule).
  - Rate limit: 5 reports/min/user. Audit-log each report.
  - Flow: persist → try GitHub (also retry up to 3 oldest pending reports,
    piggyback) → respond `{report_id, github_issue_url | null}`.
- `GET /feedback` (admin): list reports incl. sync_status.
- `POST /feedback/sync` (admin): retry all pending GitHub syncs.

### Schema (added to `scripts/chat/schema.sql`)

```sql
CREATE TABLE IF NOT EXISTS feedback_reports (
  id TEXT PRIMARY KEY,                 -- fb_<utc-ts>_<6hex>
  session_id TEXT,                     -- nullable for general feedback
  message_id INTEGER,                  -- chat_messages.id; null for general
  kind TEXT NOT NULL CHECK(kind IN ('message','general')),
  user_id TEXT,
  comment TEXT,
  payload_path TEXT NOT NULL,
  github_issue_url TEXT,
  github_issue_number INTEGER,
  sync_status TEXT NOT NULL DEFAULT 'pending'
    CHECK(sync_status IN ('pending','synced')),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_sync ON feedback_reports(sync_status);
```

### Frontend units (conventions: function components, Tailwind, Zustand, Radix, sonner)

- **`FlagMessageButton`** — flag icon + "Report" in `MessageBubble`'s existing
  action row; assistant messages only; rendered only when
  `streamingState === 'complete'` (or undefined for non-streamed).
- **Header "Report a problem"** button — opens the same dialog in `general` mode.
- **`FeedbackDialog`** (shared, Radix Dialog):
  - Explains what gets sent: "your conversation in this session plus technical
    traces; the issue text (your query, the answer excerpt, your comment) will be
    publicly visible on GitHub".
  - Optional comment textarea (required in general mode).
  - Submit → toast: success "Report sent — thanks!" (+ issue link when synced) /
    "Report saved — will sync to GitHub later" / error toast on failure.
- **`frontend/src/api/feedback.ts`** — `submitFeedback(...)` via
  `authenticatedFetch`.
- Frontend needs the backend `chat_messages.id` per assistant message to report
  precisely. The chat response/metadata must expose it (add `message_db_id` to
  response metadata in POST /chat and WS complete event); fallback: report by
  session + latest assistant message when id is absent.

### GitHub issue format (slim — nothing sensitive)

- Title: `[chat-report] "<first 60 chars of flagged user query>"` or
  `[feedback] <first 60 chars of comment>`.
- Body: reporter username, UTC timestamp, kind, flagged user query, assistant
  answer excerpt (≤300 chars), result count + relaxations (when present),
  tester comment, `Report ID: fb_…` + note that the full payload lives at
  `data/feedback/<id>.json` on the server.
- Label: `user-reported` (create label if missing — once, idempotent).

### Error handling

| Case | Behavior |
|---|---|
| Session/message not found | 404 |
| Reporting someone else's session (non-admin) | 403 |
| GitHub call fails / token missing | report saved; `sync_status='pending'`; response has `github_issue_url: null`; informative toast |
| Payload assembly fails | report row + comment still saved; error noted in payload JSON |
| Rate limit exceeded | 429 |

### Security & privacy

- Public-issue content limited to: query text, answer excerpt, comment, counts.
  The dialog warns testers about public visibility.
- `GITHUB_TOKEN`: fine-grained PAT, `issues:write` on the single repo; provided
  via server env (document in `docs/current/deployment.md`); never logged.
- Existing PII masking applies to chat content before it is ever stored.

### Testing

- `tests/scripts/feedback/test_report_store.py` — tmp-SQLite store tests:
  payload assembly (session turns, plan/candidate JSON round-trip), report
  persistence, pending/synced transitions, assembly-failure still saves.
- `tests/scripts/feedback/test_github_client.py` — mocked httpx: success,
  HTTP error, missing token; assert token never appears in exception text.
- `tests/app/test_feedback_routes.py` — FastAPI TestClient: auth gates,
  ownership 403, 404s, rate limit, piggyback retry, github mocked.
- Manual frontend checklist appended to `docs/testing/` guide (no FE test infra).

### Documentation updates (per CLAUDE.md protocol)

- `docs/current/chatbot-api.md` — new /feedback endpoints.
- `docs/current/deployment.md` — `GITHUB_TOKEN` + `FEEDBACK_REPO` env setup.
- `docs/current/architecture.md` — `scripts/feedback/` module.

## Out of scope (YAGNI)

- Screenshots/attachments; issue de-duplication; in-app report management UI
  beyond the admin list endpoint; email notifications; editing reports.
