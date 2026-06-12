# "Mark as Problematic" Chat Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Testers can flag any assistant chat message (or send general feedback) and the system packs the whole session's debug data into a server-side report + a slim public GitHub issue.

**Architecture:** Save-first pipeline: `POST /feedback` persists a `feedback_reports` row + full-session JSON payload under `data/feedback/`, then best-effort opens a slim GitHub issue via REST (`GITHUB_TOKEN` env). Two frontend entry points (per-message flag button, header feedback button) share one dialog.

**Tech Stack:** FastAPI + sqlite3 (existing `sessions.db`), httpx (already a dep), React 19 + TypeScript + Tailwind + Radix Dialog + sonner (existing conventions).

**Spec:** `docs/superpowers/specs/2026-06-12-mark-as-problematic-design.md` — read it first.

**Branch:** create `feature/mark-as-problematic` off `dev`; all commits there.

**Conventions that bind every task:**
- TDD: write the failing test, watch it fail, implement, watch it pass, commit.
- Run tests with `PYTHONPATH=. poetry run pytest <path> -q`.
- Lint touched files with `poetry run ruff check <files>` before each commit.
- Never log or echo `GITHUB_TOKEN` (user-level secret rules apply).

---

### Task 1: `feedback_reports` schema

**Files:**
- Modify: `scripts/chat/schema.sql` (append)
- Test: `tests/scripts/feedback/test_report_store.py` (create, with `tests/scripts/feedback/__init__.py`)

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/feedback/test_report_store.py
"""Tests for the feedback report store (spec 2026-06-12-mark-as-problematic)."""
import sqlite3
from pathlib import Path

import pytest

from scripts.chat.session_store import SessionStore


@pytest.fixture
def store_db(tmp_path):
    """SessionStore-initialized DB (runs schema.sql, incl. feedback_reports)."""
    db_path = tmp_path / "sessions.db"
    SessionStore(db_path)  # _ensure_schema executes schema.sql
    return db_path


class TestFeedbackSchema:
    def test_feedback_reports_table_exists(self, store_db):
        conn = sqlite3.connect(store_db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(feedback_reports)")}
        conn.close()
        assert {"id", "session_id", "message_id", "kind", "user_id", "comment",
                "payload_path", "github_issue_url", "github_issue_number",
                "sync_status", "created_at"} <= cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. poetry run pytest tests/scripts/feedback/test_report_store.py -q`
Expected: FAIL — `feedback_reports` has no columns (table missing).

- [ ] **Step 3: Append the table to `scripts/chat/schema.sql`**

```sql
-- Feedback reports: "Mark as problematic" (spec 2026-06-12)
CREATE TABLE IF NOT EXISTS feedback_reports (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    message_id INTEGER,
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

NOTE: verify how `SessionStore._ensure_schema` (scripts/chat/session_store.py:64)
executes schema.sql — if it uses `executescript` on the whole file this just works;
if it checks table existence first, mirror how earlier tables (e.g. `user_goals`)
were added.

- [ ] **Step 4: Run test to verify it passes** — same command, expected PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/schema.sql tests/scripts/feedback/
git commit -m "feat: feedback_reports table for mark-as-problematic (#spec 2026-06-12)"
```

---

### Task 2: Report store — payload assembly + persistence

**Files:**
- Create: `scripts/feedback/__init__.py` (empty), `scripts/feedback/report_store.py`
- Test: `tests/scripts/feedback/test_report_store.py` (extend)

- [ ] **Step 1: Write the failing tests** (append to the test file)

```python
import json
from scripts.chat.models import Message  # verify exact import in session_store.py
from scripts.feedback.report_store import FeedbackStore


@pytest.fixture
def seeded(store_db, tmp_path):
    """Session with 2 turns; returns (FeedbackStore, session_id, assistant_msg_db_id)."""
    ss = SessionStore(store_db)
    session = ss.create_session(user_id="tester1")
    ss.add_message(session.session_id, Message(role="user", content="books by Maimonides"))
    ss.add_message(session.session_id, Message(
        role="assistant", content="Found 20 records.",
        query_plan={"filters": [{"field": "agent_norm"}]},
        candidate_set={"total_count": 20},
    ))
    conn = sqlite3.connect(store_db)
    msg_id = conn.execute(
        "SELECT MAX(id) FROM chat_messages WHERE session_id = ?",
        (session.session_id,)).fetchone()[0]
    conn.close()
    fs = FeedbackStore(store_db, payload_dir=tmp_path / "feedback")
    return fs, session.session_id, msg_id


class TestAssemblePayload:
    def test_includes_all_turns_with_plan_and_candidates(self, seeded):
        fs, sid, msg_id = seeded
        payload = fs.assemble_session_payload(sid, msg_id)
        assert payload["session_id"] == sid
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["content"] == "books by Maimonides"
        assert payload["messages"][1]["query_plan"]["filters"][0]["field"] == "agent_norm"
        assert payload["messages"][1]["candidate_set"]["total_count"] == 20

    def test_message_id_cutoff(self, seeded):
        fs, sid, msg_id = seeded
        payload = fs.assemble_session_payload(sid, msg_id - 1)
        assert len(payload["messages"]) == 1  # only the user turn

    def test_unknown_session_raises(self, seeded):
        fs, _, _ = seeded
        with pytest.raises(KeyError):
            fs.assemble_session_payload("no-such-session", None)


class TestCreateReport:
    def test_creates_row_and_payload_file(self, seeded):
        fs, sid, msg_id = seeded
        report = fs.create_report(kind="message", session_id=sid, message_id=msg_id,
                                  user_id="tester1", comment="result looks wrong")
        assert report.id.startswith("fb_")
        assert report.sync_status == "pending"
        data = json.loads(Path(report.payload_path).read_text(encoding="utf-8"))
        assert len(data["messages"]) == 2
        assert data["report"]["comment"] == "result looks wrong"

    def test_general_report_without_session(self, seeded):
        fs, _, _ = seeded
        report = fs.create_report(kind="general", session_id=None, message_id=None,
                                  user_id="tester1", comment="map button broken")
        data = json.loads(Path(report.payload_path).read_text(encoding="utf-8"))
        assert data["messages"] == []

    def test_assembly_failure_still_saves_report(self, seeded):
        fs, _, _ = seeded
        # message kind pointing at a nonexistent session: row + file must still exist
        report = fs.create_report(kind="message", session_id="ghost", message_id=1,
                                  user_id="t", comment="c")
        data = json.loads(Path(report.payload_path).read_text(encoding="utf-8"))
        assert "assembly_error" in data

    def test_pending_and_mark_synced_roundtrip(self, seeded):
        fs, sid, msg_id = seeded
        r = fs.create_report(kind="message", session_id=sid, message_id=msg_id,
                             user_id="t", comment=None)
        assert [p.id for p in fs.list_pending()] == [r.id]
        fs.mark_synced(r.id, "https://github.com/x/y/issues/9", 9)
        assert fs.list_pending() == []
        got = fs.get_report(r.id)
        assert got.github_issue_url.endswith("/9")
        assert got.sync_status == "synced"
```

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError: scripts.feedback`.

- [ ] **Step 3: Implement `scripts/feedback/report_store.py`**

```python
"""Feedback report store: save-first persistence for mark-as-problematic.

Spec: docs/superpowers/specs/2026-06-12-mark-as-problematic-design.md
A report is ALWAYS persisted (row + payload JSON) before any GitHub sync.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEFAULT_PAYLOAD_DIR = Path("data/feedback")


@dataclass
class Report:
    id: str
    session_id: Optional[str]
    message_id: Optional[int]
    kind: str
    user_id: Optional[str]
    comment: Optional[str]
    payload_path: str
    github_issue_url: Optional[str]
    github_issue_number: Optional[int]
    sync_status: str
    created_at: str


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


class FeedbackStore:
    def __init__(self, db_path: Path, payload_dir: Path = DEFAULT_PAYLOAD_DIR):
        self.db_path = Path(db_path)
        self.payload_dir = Path(payload_dir)
        self.payload_dir.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def assemble_session_payload(self, session_id: str,
                                 message_id: Optional[int]) -> dict:
        """All session turns up to & incl. message_id, with plan/candidates."""
        conn = self._conn()
        try:
            sess = conn.execute(
                "SELECT session_id, user_id, created_at, phase FROM chat_sessions "
                "WHERE session_id = ?", (session_id,)).fetchone()
            if not sess:
                raise KeyError(f"session not found: {session_id}")
            sql = ("SELECT id, role, content, query_plan, candidate_set, timestamp "
                   "FROM chat_messages WHERE session_id = ?")
            params: list = [session_id]
            if message_id is not None:
                sql += " AND id <= ?"
                params.append(message_id)
            sql += " ORDER BY id"
            messages = []
            for row in conn.execute(sql, params):
                messages.append({
                    "db_id": row["id"],
                    "role": row["role"],
                    "content": row["content"],
                    "query_plan": json.loads(row["query_plan"]) if row["query_plan"] else None,
                    "candidate_set": json.loads(row["candidate_set"]) if row["candidate_set"] else None,
                    "timestamp": row["timestamp"],
                })
            return {
                "session_id": session_id,
                "session": dict(sess),
                "messages": messages,
                "app_git_sha": _git_sha(),
                "assembled_at": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            conn.close()

    def create_report(self, *, kind: str, session_id: Optional[str],
                      message_id: Optional[int], user_id: Optional[str],
                      comment: Optional[str]) -> Report:
        now = datetime.now(timezone.utc)
        report_id = f"fb_{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
        if kind == "message" or (kind == "general" and session_id):
            try:
                payload = self.assemble_session_payload(session_id, message_id)
            except Exception as e:  # save-first: never lose the report
                payload = {"session_id": session_id, "messages": [],
                           "assembly_error": f"{type(e).__name__}: {e}"}
        else:
            payload = {"session_id": None, "messages": []}
        payload["report"] = {
            "id": report_id, "kind": kind, "message_id": message_id,
            "user_id": user_id, "comment": comment,
            "created_at": now.isoformat(),
        }
        payload_path = self.payload_dir / f"{report_id}.json"
        payload_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO feedback_reports
                   (id, session_id, message_id, kind, user_id, comment,
                    payload_path, sync_status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (report_id, session_id, message_id, kind, user_id, comment,
                 str(payload_path), now.isoformat()))
            conn.commit()
        finally:
            conn.close()
        return self.get_report(report_id)

    def get_report(self, report_id: str) -> Report:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM feedback_reports WHERE id = ?", (report_id,)).fetchone()
            if not row:
                raise KeyError(f"report not found: {report_id}")
            return Report(**{k: row[k] for k in Report.__dataclass_fields__})
        finally:
            conn.close()

    def list_pending(self, limit: int = 50) -> list[Report]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM feedback_reports WHERE sync_status = 'pending' "
                "ORDER BY created_at LIMIT ?", (limit,)).fetchall()
            return [Report(**{k: r[k] for k in Report.__dataclass_fields__}) for r in rows]
        finally:
            conn.close()

    def list_reports(self, limit: int = 100) -> list[Report]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM feedback_reports ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()
            return [Report(**{k: r[k] for k in Report.__dataclass_fields__}) for r in rows]
        finally:
            conn.close()

    def mark_synced(self, report_id: str, issue_url: str, issue_number: int) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE feedback_reports SET sync_status='synced', "
                "github_issue_url=?, github_issue_number=? WHERE id=?",
                (issue_url, issue_number, report_id))
            conn.commit()
        finally:
            conn.close()
```

NOTE: verify the `Message` import + constructor kwargs against
`scripts/chat/session_store.py` / `scripts/chat/models.py` (the test seeds via
`SessionStore.add_message`); adjust the TEST, not the store, if field names differ.

- [ ] **Step 4: Run to verify pass** — full test file green.
- [ ] **Step 5: `poetry run ruff check scripts/feedback tests/scripts/feedback` then commit**

```bash
git add scripts/feedback/ tests/scripts/feedback/
git commit -m "feat: FeedbackStore - save-first report persistence + session payload assembly"
```

---

### Task 3: GitHub client

**Files:**
- Create: `scripts/feedback/github_client.py`
- Test: `tests/scripts/feedback/test_github_client.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/scripts/feedback/test_github_client.py
import httpx
import pytest

from scripts.feedback.github_client import (
    FeedbackSyncDisabled, FeedbackSyncError, create_issue,
)


def test_missing_token_raises_disabled(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(FeedbackSyncDisabled):
        create_issue("t", "b", ["user-reported"])


def test_create_issue_success(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_dummy_token_for_test")

    def fake_post(url, **kwargs):
        assert url.endswith("/repos/owner/repo/issues")
        assert kwargs["json"]["labels"] == ["user-reported"]
        return httpx.Response(201, json={"html_url": "https://github.com/owner/repo/issues/7",
                                         "number": 7},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    url, number = create_issue("title", "body", ["user-reported"], repo="owner/repo")
    assert number == 7 and url.endswith("/7")


def test_http_error_raises_without_token_leak(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_supersecret123")

    def fake_post(url, **kwargs):
        return httpx.Response(401, json={"message": "Bad credentials"},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(FeedbackSyncError) as exc:
        create_issue("t", "b", [], repo="owner/repo")
    assert "ghp_supersecret123" not in str(exc.value)
```

- [ ] **Step 2: Run to verify failure** — import error.

- [ ] **Step 3: Implement `scripts/feedback/github_client.py`**

```python
"""Minimal GitHub issue creation for feedback sync.

GITHUB_TOKEN is read from the environment at call time and must never be
logged, echoed, or included in exception text.
"""
from __future__ import annotations

import os

import httpx

DEFAULT_REPO = "hagaybar/rare-books-bot"


class FeedbackSyncDisabled(Exception):
    """GITHUB_TOKEN not configured — reports stay pending."""


class FeedbackSyncError(Exception):
    """GitHub API call failed — reports stay pending."""


def create_issue(title: str, body: str, labels: list[str],
                 repo: str | None = None, timeout: float = 10.0) -> tuple[str, int]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise FeedbackSyncDisabled("GITHUB_TOKEN not set")
    repo = repo or os.environ.get("FEEDBACK_REPO", DEFAULT_REPO)
    resp = httpx.post(
        f"https://api.github.com/repos/{repo}/issues",
        json={"title": title, "body": body, "labels": labels},
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"},
        timeout=timeout,
    )
    if resp.status_code != 201:
        raise FeedbackSyncError(
            f"GitHub issue creation failed: HTTP {resp.status_code}")
    data = resp.json()
    return data["html_url"], data["number"]
```

- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Lint + commit** — `git commit -m "feat: GitHub issue client for feedback sync (token never logged)"`

---

### Task 4: Expose backend message id to the frontend

**Files:**
- Modify: `scripts/chat/session_store.py:186` (`add_message` returns the row id)
- Modify: `app/api/main.py` — POST /chat response `metadata["message_db_id"]`; WS `complete` event gains `message_db_id`
- Test: extend an existing test in `tests/app/test_api.py` (POST /chat path) + a store-level test in `tests/scripts/feedback/test_report_store.py`

- [ ] **Step 1: Failing store test** — `add_message` returns the integer row id:

```python
class TestAddMessageReturnsId:
    def test_add_message_returns_db_id(self, store_db):
        ss = SessionStore(store_db)
        s = ss.create_session(user_id="t")
        first = ss.add_message(s.session_id, Message(role="user", content="a"))
        second = ss.add_message(s.session_id, Message(role="assistant", content="b"))
        assert isinstance(first, int) and second == first + 1
```

- [ ] **Step 2: Run; expect FAIL (`add_message` returns None).**

- [ ] **Step 3: Modify `SessionStore.add_message`** to `return cursor.lastrowid`
(change the return type hint to `int`; read the existing body first — keep all
current behavior, just capture the INSERT cursor and return its lastrowid).

- [ ] **Step 4: Wire into the API.** In `app/api/main.py`:
  - POST /chat handler (`main.py:493-592`): where the assistant message is added
    to the session store, capture `msg_db_id = store.add_message(...)` and set
    `response.metadata["message_db_id"] = msg_db_id` before returning.
  - WS handler (`main.py:887-1168`): same capture; add `"message_db_id": msg_db_id`
    to the `{"type": "complete", ...}` payload.
  Read the surrounding code to find the exact persistence call sites — there is
  one per handler. If the chat service (not the route) persists messages,
  thread the id back through the service return value instead.

- [ ] **Step 5: API test** (append to `tests/app/test_api.py`, reusing its `client` fixture):

```python
def test_chat_response_metadata_has_message_db_id(client):
    resp = client.post("/chat", json={"message": "books printed in Livorno"})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["response"]["metadata"].get("message_db_id"), int)
```

NOTE: mirror how existing tests in this file mock the chat pipeline (they may
stub the LLM); follow the file's established fixtures exactly.

- [ ] **Step 6: Run both test files; expect PASS. Run full `pytest tests/app tests/scripts/feedback -q`.**
- [ ] **Step 7: Lint + commit** — `git commit -m "feat: expose chat message db id to frontend (REST metadata + WS complete)"`

---

### Task 5: POST /feedback route

**Files:**
- Create: `app/api/feedback_routes.py`
- Modify: `app/api/main.py` (include router; near `main.py:344-356`)
- Test: `tests/app/test_feedback_routes.py`

- [ ] **Step 1: Failing tests**

```python
# tests/app/test_feedback_routes.py
"""POST /feedback: auth, ownership, save-first, best-effort GitHub sync."""
import pytest
from fastapi.testclient import TestClient

# Reuse the auth/test-DB fixtures pattern from tests/app/test_api.py:
# import make_test_token + app the same way that file does.


class TestPostFeedback:
    def test_requires_auth(self, anon_client):
        assert anon_client.post("/feedback", json={"kind": "general", "comment": "x"}).status_code in (401, 403)

    def test_general_requires_comment(self, client):
        resp = client.post("/feedback", json={"kind": "general"})
        assert resp.status_code == 422

    def test_message_kind_requires_session_and_message(self, client):
        assert client.post("/feedback", json={"kind": "message"}).status_code == 422

    def test_unknown_session_404(self, client):
        resp = client.post("/feedback", json={"kind": "message",
                                              "session_id": "ghost", "message_id": 1})
        assert resp.status_code == 404

    def test_other_users_session_403(self, client, other_user_session):
        resp = client.post("/feedback", json={"kind": "message",
                                              "session_id": other_user_session,
                                              "message_id": 1})
        assert resp.status_code == 403

    def test_saves_report_and_returns_pending_when_github_disabled(
            self, client, own_session_with_message, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        sid, mid = own_session_with_message
        resp = client.post("/feedback", json={"kind": "message", "session_id": sid,
                                              "message_id": mid, "comment": "broken"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["report_id"].startswith("fb_")
        assert body["github_issue_url"] is None

    def test_synced_when_github_succeeds(self, client, own_session_with_message, monkeypatch):
        import scripts.feedback.github_client as gc
        monkeypatch.setattr(gc, "create_issue",
                            lambda *a, **k: ("https://github.com/o/r/issues/12", 12))
        sid, mid = own_session_with_message
        resp = client.post("/feedback", json={"kind": "message", "session_id": sid,
                                              "message_id": mid})
        assert resp.json()["github_issue_url"].endswith("/12")
```

Build the fixtures (`anon_client`, `own_session_with_message`, `other_user_session`)
by copying the patterns in `tests/app/test_api.py` (TestClient with/without
`make_test_token()` cookie; seed sessions via `SessionStore` pointing at the
test sessions DB the app uses — see that file's `test_sessions_db` fixture).

- [ ] **Step 2: Run; expect failures (404 route).**

- [ ] **Step 3: Implement `app/api/feedback_routes.py`**

```python
"""Feedback endpoints: mark-as-problematic reports -> GitHub issues.

Save-first: the report row + payload JSON are persisted before any GitHub
call; sync is best-effort and retried opportunistically.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator

from app.api.auth_deps import get_current_user, require_role
from scripts.feedback import github_client
from scripts.feedback.report_store import FeedbackStore, Report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])

RATE_LIMIT = 5          # reports
RATE_WINDOW = 60.0      # seconds
_recent: dict[str, list[float]] = defaultdict(list)


def _check_rate(user: str) -> bool:
    now = time.time()
    _recent[user] = [t for t in _recent[user] if now - t < RATE_WINDOW]
    if len(_recent[user]) >= RATE_LIMIT:
        return False
    _recent[user].append(now)
    return True


def _get_store() -> FeedbackStore:
    # Reuse the same sessions DB path the chat endpoints use (see app/api/main.py
    # session-store construction) — import that constant rather than hardcoding.
    from app.api.main import SESSIONS_DB_PATH  # adjust to the actual constant name
    return FeedbackStore(SESSIONS_DB_PATH)


class FeedbackRequest(BaseModel):
    kind: Literal["message", "general"]
    session_id: Optional[str] = None
    message_id: Optional[int] = None
    comment: Optional[str] = None

    @model_validator(mode="after")
    def _validate_kind(self):
        if self.kind == "general" and not (self.comment and self.comment.strip()):
            raise ValueError("comment is required for general feedback")
        if self.kind == "message" and (not self.session_id or self.message_id is None):
            raise ValueError("session_id and message_id are required for message reports")
        return self


class FeedbackResponse(BaseModel):
    report_id: str
    github_issue_url: Optional[str] = None


def _issue_text(report: Report, payload: dict) -> tuple[str, str]:
    """Slim public issue: query + answer excerpt + comment only (public repo)."""
    msgs = payload.get("messages", [])
    flagged_q = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
    answer = next((m["content"] for m in reversed(msgs) if m["role"] == "assistant"), "")
    counts = next((m["candidate_set"].get("total_count") for m in reversed(msgs)
                   if m.get("candidate_set")), None)
    if report.kind == "message":
        title = f'[chat-report] "{flagged_q[:60]}"'
    else:
        title = f"[feedback] {(report.comment or '')[:60]}"
    lines = [
        f"**Reporter**: {report.user_id} · **When**: {report.created_at} · **Kind**: {report.kind}",
        "",
    ]
    if flagged_q:
        lines += [f"**Query**: {flagged_q}", ""]
    if answer:
        lines += [f"**Answer excerpt**: {answer[:300]}", ""]
    if counts is not None:
        lines += [f"**Result count**: {counts}", ""]
    if report.comment:
        lines += [f"**Tester comment**: {report.comment}", ""]
    lines += ["---", f"Report ID: `{report.id}` — full payload on the server at "
              f"`{report.payload_path}` (not published; repo is public)."]
    return title, "\n".join(lines)


def _try_sync(store: FeedbackStore, report: Report) -> Optional[str]:
    import json
    from pathlib import Path
    try:
        payload = json.loads(Path(report.payload_path).read_text(encoding="utf-8"))
        title, body = _issue_text(report, payload)
        url, number = github_client.create_issue(title, body, ["user-reported"])
        store.mark_synced(report.id, url, number)
        return url
    except github_client.FeedbackSyncDisabled:
        logger.info("feedback sync disabled (no token); report %s pending", report.id)
    except Exception as e:
        logger.warning("feedback sync failed for %s: %s", report.id, type(e).__name__)
    return None


@router.post("", response_model=FeedbackResponse)
def post_feedback(req: FeedbackRequest,
                  user: dict = Depends(require_role("limited"))):
    username = user.get("username") or user.get("sub") or "unknown"
    if not _check_rate(username):
        raise HTTPException(status_code=429, detail="Too many reports; wait a minute")

    store = _get_store()
    if req.session_id:
        # Ownership: mirror GET /sessions/{id} (app/api/main.py:814-847)
        from scripts.chat.session_store import SessionStore
        from app.api.main import SESSIONS_DB_PATH
        sess = SessionStore(SESSIONS_DB_PATH).get_session(req.session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if user.get("role") != "admin" and sess.user_id not in (None, username):
            raise HTTPException(status_code=403, detail="Not your session")

    report = store.create_report(kind=req.kind, session_id=req.session_id,
                                 message_id=req.message_id, user_id=username,
                                 comment=req.comment)
    issue_url = _try_sync(store, report)

    # Piggyback: retry up to 3 oldest other pending reports
    for pending in store.list_pending(limit=4):
        if pending.id != report.id:
            _try_sync(store, pending)

    # Audit log — match the signature at app/api/auth_service.py:190
    try:
        from app.api.auth_service import audit_log
        audit_log("feedback_report", username=username,
                  detail=f"report={report.id} kind={req.kind}")
    except Exception:
        pass
    return FeedbackResponse(report_id=report.id, github_issue_url=issue_url)
```

NOTES for the implementer:
- `SESSIONS_DB_PATH`: find the real constant/way main.py builds its SessionStore
  and reuse it (grep `SessionStore(` in app/api/main.py). Adjust both usages.
- `require_role("limited")` returns the user claims dict — verify against
  `app/api/auth_deps.py:20` and how other routes consume it.
- `audit_log` kwargs: match the real signature at auth_service.py:190.
- Ownership semantics: copy the exact comparison used by GET /sessions/{id}.

- [ ] **Step 4: Register the router in `app/api/main.py`** next to the other
`include_router` calls (~line 356): `from app.api.feedback_routes import router as feedback_router` + `app.include_router(feedback_router)`.

- [ ] **Step 5: Run the new test file until green; then the full app tests:**
`PYTHONPATH=. poetry run pytest tests/app -q`

- [ ] **Step 6: Lint + commit** — `git commit -m "feat: POST /feedback - save-first report + best-effort GitHub issue"`

---

### Task 6: Admin endpoints — list + sync

**Files:**
- Modify: `app/api/feedback_routes.py`
- Test: `tests/app/test_feedback_routes.py` (extend)

- [ ] **Step 1: Failing tests**

```python
class TestAdminEndpoints:
    def test_list_requires_admin(self, client):  # client = limited role
        assert client.get("/feedback").status_code == 403

    def test_admin_lists_reports(self, admin_client, own_session_with_message, client, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        sid, mid = own_session_with_message
        client.post("/feedback", json={"kind": "message", "session_id": sid, "message_id": mid})
        resp = admin_client.get("/feedback")
        assert resp.status_code == 200
        assert resp.json()[0]["sync_status"] == "pending"

    def test_admin_sync_retries_pending(self, admin_client, client,
                                        own_session_with_message, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        sid, mid = own_session_with_message
        client.post("/feedback", json={"kind": "message", "session_id": sid, "message_id": mid})
        import scripts.feedback.github_client as gc
        monkeypatch.setattr(gc, "create_issue",
                            lambda *a, **k: ("https://github.com/o/r/issues/1", 1))
        resp = admin_client.post("/feedback/sync")
        assert resp.json()["synced"] >= 1
```

(`admin_client`: TestClient with an admin-role token — copy how admin-gated
endpoints are tested elsewhere in tests/app, e.g. test_auth.py.)

- [ ] **Step 2: Run; expect 404/403 failures.**

- [ ] **Step 3: Implement** (append to feedback_routes.py):

```python
@router.get("")
def list_feedback(user: dict = Depends(require_role("admin"))):
    store = _get_store()
    return [vars(r) for r in store.list_reports()]


@router.post("/sync")
def sync_feedback(user: dict = Depends(require_role("admin"))):
    store = _get_store()
    synced = 0
    for pending in store.list_pending():
        if _try_sync(store, pending):
            synced += 1
    return {"synced": synced, "remaining": len(store.list_pending())}
```

- [ ] **Step 4: Run until green; lint; commit** — `git commit -m "feat: admin feedback list + sync endpoints"`

---

### Task 7: Frontend — API client + FeedbackDialog

**Files:**
- Create: `frontend/src/api/feedback.ts`, `frontend/src/components/chat/FeedbackDialog.tsx`

- [ ] **Step 1: `frontend/src/api/feedback.ts`** (mirror the URL convention of
`frontend/src/api/chat.ts:46-71` — same base path handling):

```typescript
import { authenticatedFetch } from './auth';

export interface FeedbackRequest {
  kind: 'message' | 'general';
  session_id?: string;
  message_id?: number;
  comment?: string;
}

export interface FeedbackResponse {
  report_id: string;
  github_issue_url: string | null;
}

export async function submitFeedback(req: FeedbackRequest): Promise<FeedbackResponse> {
  const resp = await authenticatedFetch('/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Feedback failed (${resp.status})`);
  }
  return resp.json();
}
```

- [ ] **Step 2: `FeedbackDialog.tsx`** — Radix Dialog (the repo already uses
`@radix-ui/react-dialog`; mirror an existing dialog's styling if one exists,
else use this structure):

```tsx
import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { toast } from 'sonner';
import { submitFeedback } from '../../api/feedback';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: 'message' | 'general';
  sessionId?: string;
  messageDbId?: number;
}

export function FeedbackDialog({ open, onOpenChange, kind, sessionId, messageDbId }: Props) {
  const [comment, setComment] = useState('');
  const [sending, setSending] = useState(false);
  const commentRequired = kind === 'general';

  const handleSubmit = async () => {
    if (commentRequired && !comment.trim()) return;
    setSending(true);
    try {
      const res = await submitFeedback({
        kind,
        session_id: sessionId,
        message_id: messageDbId,
        comment: comment.trim() || undefined,
      });
      toast.success(
        res.github_issue_url
          ? 'Report sent — thanks! Issue opened.'
          : 'Report saved — it will sync to GitHub later.',
      );
      setComment('');
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to send report');
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 z-50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[28rem] max-w-[92vw] -translate-x-1/2 -translate-y-1/2 rounded-xl bg-white p-5 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-gray-900">
            {kind === 'message' ? 'Report this result as problematic' : 'Report a problem'}
          </Dialog.Title>
          <Dialog.Description className="mt-2 text-xs text-gray-500">
            {kind === 'message'
              ? 'Your conversation in this session plus technical traces will be sent to the developers. The report summary (your query, an answer excerpt, and your comment) will be publicly visible on GitHub.'
              : 'Your message will be publicly visible on GitHub. If a chat session is open, its technical traces are attached for the developers.'}
          </Dialog.Description>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={commentRequired ? 'Describe the problem…' : 'Optional: what looks wrong?'}
            className="mt-3 h-24 w-full rounded-md border border-gray-300 p-2 text-sm focus:border-blue-400 focus:outline-none"
          />
          <div className="mt-4 flex justify-end gap-2">
            <Dialog.Close className="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100">
              Cancel
            </Dialog.Close>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={sending || (commentRequired && !comment.trim())}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {sending ? 'Sending…' : 'Send report'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
```

- [ ] **Step 3: `cd frontend && npx tsc --noEmit && npm run lint`** (fix anything in the new files).
- [ ] **Step 4: Commit** — `git commit -m "feat(frontend): feedback API client + FeedbackDialog"`

---

### Task 8: Frontend — flag button per message + header button

**Files:**
- Modify: `frontend/src/components/chat/MessageBubble.tsx` (action row area, ~:195-264)
- Modify: `frontend/src/types/chat.ts:157-172` (no change needed if metadata is `Record<string, unknown>`; read it)
- Modify: `frontend/src/pages/Chat.tsx` (header area + dialog state)

- [ ] **Step 1: MessageBubble.** Add a "Report" affordance for assistant messages
whose `streamingState` is `'complete'` or `undefined`, next to the existing
query-details toggle (read MessageBubble.tsx:195-264 first; match its button
styling). Extract `messageDbId` from `message.metadata?.message_db_id`:

```tsx
// near other action buttons inside the assistant bubble:
const messageDbId = typeof message.metadata?.message_db_id === 'number'
  ? message.metadata.message_db_id
  : undefined;
const [reportOpen, setReportOpen] = useState(false);
// ...
{message.role === 'assistant' && (message.streamingState === 'complete' || !message.streamingState) && (
  <>
    <button
      type="button"
      onClick={() => setReportOpen(true)}
      className="text-xs text-gray-400 hover:text-red-600 font-medium"
      title="Report this result as problematic"
    >
      ⚑ Report
    </button>
    <FeedbackDialog
      open={reportOpen}
      onOpenChange={setReportOpen}
      kind="message"
      sessionId={sessionId}
      messageDbId={messageDbId}
    />
  </>
)}
```

`sessionId` comes from the Zustand store (`appStore.ts:6`) — import `useAppStore`
the same way Chat.tsx does. If `messageDbId` is undefined (e.g. restored old
session), still allow the report: backend treats missing message_id on kind
'message' as invalid, so in that case fall back to `kind: 'message'` with the
LAST message id is NOT possible — instead disable the button with title
"Reporting unavailable for this message" when `messageDbId` is undefined.

- [ ] **Step 2: Header button.** In `frontend/src/pages/Chat.tsx`, add a small
"⚑ Report a problem" button in the header/top bar (find the existing header
controls), opening `<FeedbackDialog kind="general" sessionId={sessionId ?? undefined} />`.

- [ ] **Step 3: Manual check** — `cd frontend && npm run dev` + backend
`uvicorn app.api.main:app --reload`; flag a message; verify toast and (token
unset locally) a `pending` row in feedback_reports + JSON in data/feedback/.

- [ ] **Step 4: `npx tsc --noEmit && npm run lint && npm run build`** — all clean.
- [ ] **Step 5: Commit** — `git commit -m "feat(frontend): per-message Report button + header feedback entry"`

---

### Task 9: Docs

**Files:**
- Modify: `docs/current/chatbot-api.md` (new /feedback endpoints section + Last verified)
- Modify: `docs/current/deployment.md` (GITHUB_TOKEN + FEEDBACK_REPO env)
- Modify: `docs/current/architecture.md` (scripts/feedback module)
- Modify: `docs/testing/` manual guide (feedback checklist)

- [ ] **Step 1:** chatbot-api.md — document POST /feedback (body, roles, rate
limit, save-first semantics, response), GET /feedback + POST /feedback/sync
(admin). Update `Last verified: 2026-06-12`.
- [ ] **Step 2:** deployment.md — env table addition:

```markdown
| `GITHUB_TOKEN` | Fine-grained PAT, `issues:write` on the feedback repo only. Optional — without it, feedback reports stay `pending` and can be synced later via `POST /feedback/sync`. Never commit or log this value. |
| `FEEDBACK_REPO` | Target repo for feedback issues (default `hagaybar/rare-books-bot`). |
```

- [ ] **Step 3:** architecture.md — add `scripts/feedback/` (report_store, github_client) to the module map.
- [ ] **Step 4:** docs/testing — manual checklist: flag a message (with/without comment), general feedback (comment required), token unset → pending toast, admin sync, public-visibility warning text shown.
- [ ] **Step 5: Commit** — `git commit -m "docs: /feedback endpoints, GITHUB_TOKEN deployment, feedback module"`

---

### Task 10: Final verification + merge readiness

- [ ] **Step 1:** `PYTHONPATH=. poetry run pytest -q` — full suite green (baseline: 1601+ passed / 21 skipped; no new failures).
- [ ] **Step 2:** `poetry run ruff check scripts/feedback app/api/feedback_routes.py tests/scripts/feedback tests/app/test_feedback_routes.py` — clean.
- [ ] **Step 3:** `cd frontend && npm run build` — clean build.
- [ ] **Step 4:** `git log --oneline dev..HEAD` — review commits; do NOT merge; report branch ready.
