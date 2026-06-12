"""Feedback endpoints: mark-as-problematic reports -> GitHub issues.

Save-first: the report row + payload JSON are persisted before any GitHub
call; sync is best-effort and retried opportunistically.

Spec: docs/superpowers/specs/2026-06-12-mark-as-problematic-design.md
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator

from app.api.auth_deps import require_role
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
    # Reuse the same sessions DB the chat endpoints use: main.py builds its
    # SessionStore from the SESSIONS_DB_PATH env var inside lifespan(); the
    # live store's db_path is the authoritative location.
    from app.api.main import get_session_store

    payload_dir = Path(os.getenv("FEEDBACK_DIR", "data/feedback"))
    return FeedbackStore(get_session_store().db_path, payload_dir=payload_dir)


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
async def post_feedback(req: FeedbackRequest,
                        user: dict = Depends(require_role("limited"))):
    # async so the shared SessionStore sqlite connection stays on the event-loop
    # thread (same pattern as the /sessions endpoints in app/api/main.py).
    username = user.get("username") or "unknown"
    if not _check_rate(username):
        raise HTTPException(status_code=429, detail="Too many reports; wait a minute")

    store = _get_store()
    if req.session_id:
        # Ownership: mirror GET /sessions/{session_id} in app/api/main.py
        from app.api.main import get_session_store

        session = get_session_store().get_session(req.session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {req.session_id} not found",
            )
        if str(session.user_id) != str(user["user_id"]) and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Access denied")

    report = store.create_report(kind=req.kind, session_id=req.session_id,
                                 message_id=req.message_id, user_id=username,
                                 comment=req.comment)
    issue_url = _try_sync(store, report)

    # Piggyback: retry up to 3 oldest other pending reports
    for pending in store.list_pending(limit=4):
        if pending.id != report.id:
            _try_sync(store, pending)

    # Audit log (signature: app/api/auth_service.py audit_log)
    try:
        from app.api.auth_service import audit_log

        audit_log("feedback_report", user_id=user.get("user_id"), username=username,
                  details=f"report={report.id} kind={req.kind}")
    except Exception:
        pass
    return FeedbackResponse(report_id=report.id, github_issue_url=issue_url)
