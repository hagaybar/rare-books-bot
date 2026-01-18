"""SQLite-backed storage for chat sessions.

Provides persistent storage for multi-turn conversations with:
- CRUD operations for sessions and messages
- Context tracking for carry-forward state
- Session expiration and lifecycle management
- Atomic operations with foreign key constraints

Two-Phase Conversation Support:
- Phase tracking (query_definition → corpus_exploration)
- Active subgroup storage for corpus exploration
- User goal tracking for need elicitation
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.chat.models import (
    ChatSession,
    Message,
    ConversationPhase,
    ActiveSubgroup,
    UserGoal,
)
from scripts.schemas import CandidateSet
from scripts.utils.logger import LoggerManager


class SessionStore:
    """SQLite-backed storage for chat sessions.

    Handles CRUD operations for sessions and messages with atomic operations.

    Attributes:
        db_path: Path to SQLite database file
        _conn: SQLite connection (lazy-loaded)
    """

    def __init__(self, db_path: Path):
        """Initialize session store.

        Args:
            db_path: Path to SQLite database (created if not exists)
        """
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self.logger = LoggerManager.get_logger(__name__)
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection with foreign keys enabled.

        Returns:
            SQLite connection with foreign keys enabled
        """
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path) as f:
            schema = f.read()

        conn = self._get_connection()
        conn.executescript(schema)
        conn.commit()
        self.logger.info(
            "Session database schema initialized", extra={"db_path": str(self.db_path)}
        )

    def create_session(self, user_id: Optional[str] = None) -> ChatSession:
        """Create new chat session.

        Args:
            user_id: Optional user identifier

        Returns:
            ChatSession: New session object
        """
        session = ChatSession(user_id=user_id)

        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO chat_sessions
            (session_id, user_id, created_at, updated_at, context, metadata, expired_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_id,
                session.user_id,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                json.dumps(session.context),
                json.dumps(session.metadata),
                None,
            ),
        )
        conn.commit()

        self.logger.info(
            "Created chat session",
            extra={"session_id": session.session_id, "user_id": user_id},
        )
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Retrieve session by ID.

        Args:
            session_id: Session identifier

        Returns:
            ChatSession if found, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT session_id, user_id, created_at, updated_at, context, metadata
            FROM chat_sessions
            WHERE session_id = ? AND expired_at IS NULL
            """,
            (session_id,),
        )
        row = cursor.fetchone()

        if not row:
            self.logger.warning("Session not found", extra={"session_id": session_id})
            return None

        # Reconstruct ChatSession
        session = ChatSession(
            session_id=row[0],
            user_id=row[1],
            created_at=datetime.fromisoformat(row[2]),
            updated_at=datetime.fromisoformat(row[3]),
            context=json.loads(row[4]) if row[4] else {},
            metadata=json.loads(row[5]) if row[5] else {},
        )

        # Load messages
        messages = self._get_messages(session_id)
        session.messages = messages

        return session

    def _get_messages(self, session_id: str) -> List[Message]:
        """Retrieve all messages for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of Message objects ordered by timestamp
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT role, content, query_plan, candidate_set, timestamp
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY timestamp ASC
            """,
            (session_id,),
        )

        messages = []
        for row in cursor.fetchall():
            msg = Message(
                role=row[0],
                content=row[1],
                query_plan=json.loads(row[2]) if row[2] else None,
                candidate_set=json.loads(row[3]) if row[3] else None,
                timestamp=datetime.fromisoformat(row[4]),
            )
            messages.append(msg)

        return messages

    def add_message(self, session_id: str, message: Message) -> None:
        """Add message to session.

        Args:
            session_id: Session identifier
            message: Message to add

        Raises:
            ValueError: If session doesn't exist
        """
        # Verify session exists
        if not self.get_session(session_id):
            raise ValueError(f"Session {session_id} not found")

        conn = self._get_connection()

        # Insert message
        conn.execute(
            """
            INSERT INTO chat_messages
            (session_id, role, content, query_plan, candidate_set, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                message.role,
                message.content,
                json.dumps(message.query_plan.model_dump()) if message.query_plan else None,
                (
                    json.dumps(message.candidate_set.model_dump())
                    if message.candidate_set
                    else None
                ),
                message.timestamp.isoformat(),
            ),
        )

        # Update session timestamp
        conn.execute(
            """
            UPDATE chat_sessions
            SET updated_at = ?
            WHERE session_id = ?
            """,
            (datetime.now(timezone.utc).isoformat(), session_id),
        )

        conn.commit()

        self.logger.info(
            "Added message to session",
            extra={"session_id": session_id, "role": message.role},
        )

    def update_context(self, session_id: str, context: Dict[str, Any]) -> None:
        """Update session context.

        Args:
            session_id: Session identifier
            context: Context dictionary to merge with existing

        Raises:
            ValueError: If session doesn't exist
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Merge contexts
        merged_context = {**session.context, **context}

        conn = self._get_connection()
        conn.execute(
            """
            UPDATE chat_sessions
            SET context = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (json.dumps(merged_context), datetime.now(timezone.utc).isoformat(), session_id),
        )
        conn.commit()

        self.logger.info(
            "Updated session context",
            extra={"session_id": session_id, "context_keys": list(context.keys())},
        )

    def expire_session(self, session_id: str) -> None:
        """Mark session as expired.

        Args:
            session_id: Session identifier
        """
        conn = self._get_connection()
        conn.execute(
            """
            UPDATE chat_sessions
            SET expired_at = ?
            WHERE session_id = ?
            """,
            (datetime.now(timezone.utc).isoformat(), session_id),
        )
        conn.commit()

        self.logger.info("Expired session", extra={"session_id": session_id})

    def expire_old_sessions(self, max_age_hours: int = 24) -> int:
        """Expire sessions older than max_age_hours.

        Args:
            max_age_hours: Sessions inactive for this long are expired

        Returns:
            Number of sessions expired
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        conn = self._get_connection()
        cursor = conn.execute(
            """
            UPDATE chat_sessions
            SET expired_at = ?
            WHERE updated_at < ? AND expired_at IS NULL
            """,
            (datetime.now(timezone.utc).isoformat(), cutoff.isoformat()),
        )
        count = cursor.rowcount
        conn.commit()

        self.logger.info(
            "Expired old sessions", extra={"count": count, "max_age_hours": max_age_hours}
        )
        return count

    def list_user_sessions(
        self, user_id: str, include_expired: bool = False
    ) -> List[str]:
        """List all sessions for a user.

        Args:
            user_id: User identifier
            include_expired: Include expired sessions

        Returns:
            List of session IDs ordered by updated_at (most recent first)
        """
        conn = self._get_connection()

        if include_expired:
            query = "SELECT session_id FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC"
            params = (user_id,)
        else:
            query = "SELECT session_id FROM chat_sessions WHERE user_id = ? AND expired_at IS NULL ORDER BY updated_at DESC"
            params = (user_id,)

        cursor = conn.execute(query, params)
        return [row[0] for row in cursor.fetchall()]

    # =========================================================================
    # Two-Phase Conversation Support Methods
    # =========================================================================

    def get_phase(self, session_id: str) -> Optional[ConversationPhase]:
        """Get current conversation phase for a session.

        Args:
            session_id: Session identifier

        Returns:
            ConversationPhase if session exists, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT phase FROM chat_sessions WHERE session_id = ? AND expired_at IS NULL",
            (session_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        phase_str = row[0] or "query_definition"
        return ConversationPhase(phase_str)

    def update_phase(self, session_id: str, phase: ConversationPhase) -> None:
        """Update session conversation phase.

        Args:
            session_id: Session identifier
            phase: New conversation phase

        Raises:
            ValueError: If session doesn't exist
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        conn = self._get_connection()
        conn.execute(
            """
            UPDATE chat_sessions
            SET phase = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (phase.value, datetime.now(timezone.utc).isoformat(), session_id),
        )
        conn.commit()

        self.logger.info(
            "Updated session phase",
            extra={"session_id": session_id, "phase": phase.value},
        )

    def set_active_subgroup(
        self,
        session_id: str,
        subgroup: Optional[ActiveSubgroup]
    ) -> None:
        """Set or clear the active subgroup for a session.

        Called when transitioning to corpus exploration phase. Pass None
        to clear the subgroup (e.g., when starting a new query).

        Args:
            session_id: Session identifier
            subgroup: ActiveSubgroup to set, or None to clear

        Raises:
            ValueError: If session doesn't exist
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        conn = self._get_connection()

        if subgroup is None:
            # Clear existing subgroup
            conn.execute(
                "DELETE FROM active_subgroups WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            self.logger.info(
                "Cleared active subgroup", extra={"session_id": session_id}
            )
            return

        # Prepare record IDs JSON
        record_ids_json = json.dumps(subgroup.record_ids)

        # Store full CandidateSet if available (may be large)
        candidate_set_json = None
        if subgroup.candidate_set:
            candidate_set_json = json.dumps(subgroup.candidate_set.model_dump())

        # Upsert (insert or replace)
        conn.execute(
            """
            INSERT INTO active_subgroups
            (session_id, defining_query, filter_summary, record_ids,
             candidate_count, candidate_set, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                defining_query = excluded.defining_query,
                filter_summary = excluded.filter_summary,
                record_ids = excluded.record_ids,
                candidate_count = excluded.candidate_count,
                candidate_set = excluded.candidate_set,
                created_at = excluded.created_at
            """,
            (
                session_id,
                subgroup.defining_query,
                subgroup.filter_summary,
                record_ids_json,
                len(subgroup.record_ids),
                candidate_set_json,
                subgroup.created_at.isoformat(),
            ),
        )
        conn.commit()

        self.logger.info(
            "Set active subgroup",
            extra={
                "session_id": session_id,
                "candidate_count": len(subgroup.record_ids),
            },
        )

    def get_active_subgroup(self, session_id: str) -> Optional[ActiveSubgroup]:
        """Get the current active subgroup for a session.

        Args:
            session_id: Session identifier

        Returns:
            ActiveSubgroup if exists, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT defining_query, filter_summary, record_ids,
                   candidate_count, candidate_set, created_at
            FROM active_subgroups
            WHERE session_id = ?
            """,
            (session_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        # Parse record IDs
        record_ids = json.loads(row[2]) if row[2] else []

        # Parse CandidateSet if stored
        candidate_set = None
        if row[4]:
            try:
                candidate_set = CandidateSet(**json.loads(row[4]))
            except Exception as e:
                self.logger.warning(
                    "Failed to parse stored CandidateSet",
                    extra={"session_id": session_id, "error": str(e)},
                )

        return ActiveSubgroup(
            candidate_set=candidate_set,
            defining_query=row[0],
            filter_summary=row[1],
            record_ids=record_ids,
            created_at=datetime.fromisoformat(row[5]),
        )

    def add_user_goal(self, session_id: str, goal: UserGoal) -> None:
        """Record an elicited user goal.

        Args:
            session_id: Session identifier
            goal: UserGoal to record

        Raises:
            ValueError: If session doesn't exist
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO user_goals (session_id, goal_type, description, elicited_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                session_id,
                goal.goal_type,
                goal.description,
                goal.elicited_at.isoformat(),
            ),
        )
        conn.commit()

        self.logger.info(
            "Added user goal",
            extra={"session_id": session_id, "goal_type": goal.goal_type},
        )

    def get_user_goals(self, session_id: str) -> List[UserGoal]:
        """Get all elicited goals for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of UserGoal objects
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT goal_type, description, elicited_at
            FROM user_goals
            WHERE session_id = ?
            ORDER BY elicited_at ASC
            """,
            (session_id,),
        )

        goals = []
        for row in cursor.fetchall():
            goals.append(
                UserGoal(
                    goal_type=row[0],
                    description=row[1],
                    elicited_at=datetime.fromisoformat(row[2]),
                )
            )

        return goals

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
