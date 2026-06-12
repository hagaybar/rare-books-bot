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
