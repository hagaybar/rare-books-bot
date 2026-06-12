"""Tests for the feedback report store (spec 2026-06-12-mark-as-problematic)."""
import sqlite3

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
