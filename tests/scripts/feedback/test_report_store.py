"""Tests for the feedback report store (spec 2026-06-12-mark-as-problematic)."""
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.chat.models import Message
from scripts.chat.session_store import SessionStore
from scripts.feedback.report_store import FeedbackStore


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


@pytest.fixture
def seeded(store_db, tmp_path):
    """Session with 2 turns; returns (FeedbackStore, session_id, assistant_msg_db_id)."""
    ss = SessionStore(store_db)
    session = ss.create_session(user_id="tester1")
    ss.add_message(session.session_id, Message(role="user", content="books by Maimonides"))
    # NOTE: query_plan/candidate_set are typed Pydantic models on Message;
    # dicts below carry their required fields (query_text, op/value, plan_hash, sql).
    ss.add_message(session.session_id, Message(
        role="assistant", content="Found 20 records.",
        query_plan={"query_text": "books by Maimonides",
                    "filters": [{"field": "agent_norm", "op": "CONTAINS",
                                 "value": "maimonides"}]},
        candidate_set={"query_text": "books by Maimonides", "plan_hash": "ph",
                       "sql": "SELECT 1", "total_count": 20},
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
