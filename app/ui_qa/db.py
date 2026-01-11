"""QA database operations for query testing and labeling."""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import json

from app.ui_qa.config import QA_DB_PATH


def init_db() -> None:
    """Initialize QA database with schema."""
    QA_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.executescript("""
        -- qa_queries table
        CREATE TABLE IF NOT EXISTS qa_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            query_text TEXT NOT NULL,
            db_path TEXT NOT NULL,
            query_limit INTEGER NULL,
            out_dir TEXT NULL,
            plan_json TEXT NOT NULL,
            sql_text TEXT NOT NULL,
            parser_debug TEXT NULL,
            status TEXT NOT NULL CHECK(status IN ('OK', 'ERROR')),
            error_message TEXT NULL,
            total_candidates INTEGER NOT NULL DEFAULT 0
        );

        -- qa_candidate_labels table
        CREATE TABLE IF NOT EXISTS qa_candidate_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id INTEGER NOT NULL,
            record_id TEXT NOT NULL,
            label TEXT NOT NULL CHECK(label IN ('TP', 'FP', 'FN', 'UNK')) DEFAULT 'UNK',
            issue_tags TEXT NULL,
            note TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (query_id) REFERENCES qa_queries(id) ON DELETE CASCADE,
            UNIQUE(query_id, record_id)
        );

        -- qa_query_gold table
        CREATE TABLE IF NOT EXISTS qa_query_gold (
            query_id INTEGER PRIMARY KEY,
            expected_includes TEXT NOT NULL,
            expected_excludes TEXT NOT NULL,
            min_expected INTEGER NULL,
            FOREIGN KEY (query_id) REFERENCES qa_queries(id) ON DELETE CASCADE
        );

        -- qa_sessions table (NEW)
        CREATE TABLE IF NOT EXISTS qa_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            session_type TEXT NOT NULL CHECK(session_type IN ('SMOKE', 'RECALL')),
            status TEXT NOT NULL CHECK(status IN ('IN_PROGRESS', 'DONE', 'ABORTED')) DEFAULT 'IN_PROGRESS',
            current_step INTEGER NOT NULL DEFAULT 1,
            instructions_version TEXT NOT NULL DEFAULT 'v1',
            query_id INTEGER NULL,
            session_config_json TEXT NOT NULL,
            summary_json TEXT NULL,
            verdict TEXT NULL CHECK(verdict IN ('PASS', 'NEEDS_WORK', 'INCONCLUSIVE')),
            note TEXT NULL,
            FOREIGN KEY (query_id) REFERENCES qa_queries(id) ON DELETE SET NULL
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_qa_queries_created_at ON qa_queries(created_at);
        CREATE INDEX IF NOT EXISTS idx_labels_query_id ON qa_candidate_labels(query_id);
        CREATE INDEX IF NOT EXISTS idx_labels_label ON qa_candidate_labels(label);
        CREATE INDEX IF NOT EXISTS idx_qa_sessions_status ON qa_sessions(status);
        CREATE INDEX IF NOT EXISTS idx_qa_sessions_created_at ON qa_sessions(created_at);
    """)

    # Migration: Add session_id columns to existing tables if they don't exist
    cursor = conn.cursor()

    # Check if session_id exists in qa_queries
    cursor.execute("PRAGMA table_info(qa_queries)")
    qa_queries_columns = [row[1] for row in cursor.fetchall()]
    if 'session_id' not in qa_queries_columns:
        conn.execute("ALTER TABLE qa_queries ADD COLUMN session_id INTEGER NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qa_queries_session_id ON qa_queries(session_id)")

    # Check if session_id exists in qa_candidate_labels
    cursor.execute("PRAGMA table_info(qa_candidate_labels)")
    qa_labels_columns = [row[1] for row in cursor.fetchall()]
    if 'session_id' not in qa_labels_columns:
        conn.execute("ALTER TABLE qa_candidate_labels ADD COLUMN session_id INTEGER NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qa_candidate_labels_session_id ON qa_candidate_labels(session_id)")

    conn.commit()
    conn.close()


def insert_query_run(
    query_text: str,
    plan: Optional[Any],  # QueryPlan
    result: Optional[Any],  # CandidateSet
    db_path: str,
    status: str,
    error_message: Optional[str] = None,
    out_dir: Optional[str] = None,
    session_id: Optional[int] = None  # NEW
) -> int:
    """Insert a query run into qa_queries table. Returns query_id."""
    conn = sqlite3.connect(str(QA_DB_PATH))

    plan_json = plan.model_dump_json() if plan else "{}"
    sql_text = result.sql if result else ""
    parser_debug = json.dumps(plan.debug) if plan and plan.debug else None
    total_candidates = result.total_count if result else 0
    limit_val = plan.limit if plan else None

    cursor = conn.execute("""
        INSERT INTO qa_queries (
            created_at, query_text, db_path, query_limit, out_dir,
            plan_json, sql_text, parser_debug, status, error_message, total_candidates, session_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        query_text,
        db_path,
        limit_val,
        out_dir,
        plan_json,
        sql_text,
        parser_debug,
        status,
        error_message,
        total_candidates,
        session_id  # NEW
    ))

    query_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return query_id


def upsert_label(
    query_id: int,
    record_id: str,
    label: str,
    issue_tags: Optional[List[str]] = None,
    note: Optional[str] = None,
    session_id: Optional[int] = None  # NEW
) -> None:
    """Insert or update a label for a candidate."""
    conn = sqlite3.connect(str(QA_DB_PATH))

    issue_tags_json = json.dumps(issue_tags) if issue_tags else None
    now = datetime.now().isoformat()

    conn.execute("""
        INSERT INTO qa_candidate_labels (
            query_id, record_id, label, issue_tags, note, created_at, updated_at, session_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(query_id, record_id) DO UPDATE SET
            label = excluded.label,
            issue_tags = excluded.issue_tags,
            note = excluded.note,
            updated_at = excluded.updated_at,
            session_id = excluded.session_id
    """, (query_id, record_id, label, issue_tags_json, note, now, now, session_id))

    conn.commit()
    conn.close()


def get_query_runs(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent query runs."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT * FROM qa_queries
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_query_by_id(query_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific query by ID."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("SELECT * FROM qa_queries WHERE id = ?", (query_id,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def get_labels_for_query(query_id: int) -> List[Dict[str, Any]]:
    """Get all labels for a query."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT * FROM qa_candidate_labels
        WHERE query_id = ?
    """, (query_id,))

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_label_for_candidate(query_id: int, record_id: str) -> Optional[Dict[str, Any]]:
    """Get label for a specific candidate."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT * FROM qa_candidate_labels
        WHERE query_id = ? AND record_id = ?
    """, (query_id, record_id))

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def get_label_stats(filters: Optional[Dict] = None) -> Dict[str, int]:
    """Get aggregate label statistics."""
    conn = sqlite3.connect(str(QA_DB_PATH))

    # Get counts by label type
    cursor = conn.execute("""
        SELECT label, COUNT(*) as count
        FROM qa_candidate_labels
        GROUP BY label
    """)
    label_counts = {row[0]: row[1] for row in cursor.fetchall()}

    # Get number of queries with labels
    cursor = conn.execute("""
        SELECT COUNT(DISTINCT query_id) as count
        FROM qa_candidate_labels
    """)
    queries_reviewed = cursor.fetchone()[0]

    conn.close()

    return {
        'queries_reviewed': queries_reviewed,
        'tp_count': label_counts.get('TP', 0),
        'fp_count': label_counts.get('FP', 0),
        'fn_count': label_counts.get('FN', 0),
        'unk_count': label_counts.get('UNK', 0)
    }


def get_worst_queries(limit: int = 20, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
    """Get queries with most FP+FN labels."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT
            q.id,
            q.query_text,
            q.created_at,
            SUM(CASE WHEN l.label = 'FP' THEN 1 ELSE 0 END) as fp_count,
            SUM(CASE WHEN l.label = 'FN' THEN 1 ELSE 0 END) as fn_count,
            COUNT(l.id) as total_labels
        FROM qa_queries q
        LEFT JOIN qa_candidate_labels l ON q.id = l.query_id
        WHERE l.label IN ('FP', 'FN')
        GROUP BY q.id
        ORDER BY (fp_count + fn_count) DESC
        LIMIT ?
    """, (limit,))

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def export_gold_set() -> Dict[str, Any]:
    """Export gold set from labeled queries."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row

    # Get all queries with labels
    cursor = conn.execute("""
        SELECT q.id, q.query_text, q.plan_json
        FROM qa_queries q
        WHERE EXISTS (
            SELECT 1 FROM qa_candidate_labels l
            WHERE l.query_id = q.id
        )
    """)

    queries = []
    for row in cursor.fetchall():
        query_id = row['id']
        plan = json.loads(row['plan_json'])

        # Get labels
        labels = get_labels_for_query(query_id)

        # expected_includes = TP + FN
        expected_includes = [l['record_id'] for l in labels if l['label'] in ['TP', 'FN']]

        # expected_excludes = FP
        expected_excludes = [l['record_id'] for l in labels if l['label'] == 'FP']

        # Only include queries that have at least one label
        if expected_includes or expected_excludes:
            queries.append({
                "query_text": row['query_text'],
                "plan_hash": plan.get('plan_hash', ''),
                "expected_includes": expected_includes,
                "expected_excludes": expected_excludes,
                "min_expected": len(expected_includes) if expected_includes else None
            })

    conn.close()

    return {
        "version": "1.0",
        "exported_at": datetime.now().isoformat(),
        "queries": queries
    }


def get_queries_with_labels() -> List[Dict[str, Any]]:
    """Get all queries that have at least one label."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT DISTINCT q.*, COUNT(l.id) as label_count
        FROM qa_queries q
        JOIN qa_candidate_labels l ON q.id = l.query_id
        GROUP BY q.id
        ORDER BY q.created_at DESC
    """)

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def delete_query(query_id: int) -> bool:
    """Delete a query and all associated labels.

    Args:
        query_id: ID of the query to delete

    Returns:
        True if query was deleted, False if query was not found
    """
    conn = sqlite3.connect(str(QA_DB_PATH))

    # Check if query exists
    cursor = conn.execute("SELECT id FROM qa_queries WHERE id = ?", (query_id,))
    if not cursor.fetchone():
        conn.close()
        return False

    # Delete query (labels will cascade delete due to ON DELETE CASCADE)
    conn.execute("DELETE FROM qa_queries WHERE id = ?", (query_id,))
    conn.commit()
    conn.close()
    return True


# ==================== Session Management Functions ====================


def create_session(session_type: str, config: dict) -> int:
    """Create new session. Returns session_id."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    now = datetime.now().isoformat()

    cursor = conn.execute("""
        INSERT INTO qa_sessions (
            created_at, updated_at, session_type, status, current_step,
            instructions_version, session_config_json
        ) VALUES (?, ?, ?, 'IN_PROGRESS', 1, 'v1', ?)
    """, (now, now, session_type, json.dumps(config)))

    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def get_session_by_id(session_id: int) -> Optional[Dict[str, Any]]:
    """Fetch session by ID."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("SELECT * FROM qa_sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def get_session_by_status(status: str) -> Optional[Dict[str, Any]]:
    """Fetch first session with given status."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT * FROM qa_sessions
        WHERE status = ?
        ORDER BY updated_at DESC
        LIMIT 1
    """, (status,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def get_recent_sessions(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent sessions."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT * FROM qa_sessions
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def update_session_step(session_id: int, step: int):
    """Update current step."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    now = datetime.now().isoformat()

    conn.execute("""
        UPDATE qa_sessions
        SET current_step = ?, updated_at = ?
        WHERE id = ?
    """, (step, now, session_id))

    conn.commit()
    conn.close()


def update_session_query_id(session_id: int, query_id: int):
    """Link query to session."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    now = datetime.now().isoformat()

    conn.execute("""
        UPDATE qa_sessions
        SET query_id = ?, updated_at = ?
        WHERE id = ?
    """, (query_id, now, session_id))

    conn.commit()
    conn.close()


def update_session_config(session_id: int, config: dict):
    """Update session configuration."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    now = datetime.now().isoformat()

    conn.execute("""
        UPDATE qa_sessions
        SET session_config_json = ?, updated_at = ?
        WHERE id = ?
    """, (json.dumps(config), now, session_id))

    conn.commit()
    conn.close()


def finish_session(session_id: int, verdict: str, note: str, summary: dict):
    """Mark session as DONE."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    now = datetime.now().isoformat()

    conn.execute("""
        UPDATE qa_sessions
        SET status = 'DONE', verdict = ?, note = ?,
            summary_json = ?, updated_at = ?
        WHERE id = ?
    """, (verdict, note, json.dumps(summary), now, session_id))

    conn.commit()
    conn.close()


def abort_session(session_id: int):
    """Mark session as ABORTED."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    now = datetime.now().isoformat()

    conn.execute("""
        UPDATE qa_sessions
        SET status = 'ABORTED', updated_at = ?
        WHERE id = ?
    """, (now, session_id))

    conn.commit()
    conn.close()


def delete_session(session_id: int) -> bool:
    """Permanently delete a session.

    This will also delete the associated query and labels (if any) via CASCADE.

    Args:
        session_id: ID of the session to delete

    Returns:
        True if session was deleted, False if session was not found
    """
    conn = sqlite3.connect(str(QA_DB_PATH))

    # Check if session exists
    cursor = conn.execute("SELECT id FROM qa_sessions WHERE id = ?", (session_id,))
    if not cursor.fetchone():
        conn.close()
        return False

    # Delete session (will CASCADE to related query and labels via ON DELETE SET NULL/CASCADE)
    conn.execute("DELETE FROM qa_sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return True


def get_session_label_counts(session_id: int) -> Dict[str, int]:
    """Get label counts for a session."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    cursor = conn.execute("""
        SELECT label, COUNT(*) as count
        FROM qa_candidate_labels
        WHERE session_id = ?
        GROUP BY label
    """, (session_id,))

    counts = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return counts


def get_random_labeled_candidates(session_id: int, count: int = 3) -> List[Dict]:
    """Get random labeled candidates for spot check."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT record_id, label
        FROM qa_candidate_labels
        WHERE session_id = ? AND label IN ('TP', 'FP')
        ORDER BY RANDOM()
        LIMIT ?
    """, (session_id, count))

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows
