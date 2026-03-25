"""Agent authority record store.

CRUD operations for a two-table normalized authority system:
- ``agent_authorities`` -- one row per canonical agent identity
- ``agent_aliases`` -- one row per name variant, FK to authorities

Designed for the rare-books bibliographic database so that agent
names (authors, printers, etc.) can be linked to canonical identities
with external-authority IDs (VIAF, Wikidata, NLI).  Enables
cross-script, word-reorder, and patronymic alias resolution.

Mirrors the pattern established by ``publisher_authority.py``.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from scripts.metadata.clustering import detect_script as _detect_script

# ---------------------------------------------------------------------------
# Schema SQL (embedded so we don't depend on the .sql file at runtime)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_authorities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,
    canonical_name_lower TEXT NOT NULL,
    agent_type TEXT NOT NULL CHECK(agent_type IN ('personal', 'corporate', 'meeting')),
    dates_active TEXT,
    date_start INTEGER,
    date_end INTEGER,
    notes TEXT,
    sources TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    authority_uri TEXT,
    wikidata_id TEXT,
    viaf_id TEXT,
    nli_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_auth_canonical_lower
    ON agent_authorities(canonical_name_lower);
CREATE INDEX IF NOT EXISTS idx_agent_auth_type
    ON agent_authorities(agent_type);
CREATE INDEX IF NOT EXISTS idx_agent_auth_authority_uri
    ON agent_authorities(authority_uri);
CREATE INDEX IF NOT EXISTS idx_agent_auth_wikidata
    ON agent_authorities(wikidata_id);

CREATE TABLE IF NOT EXISTS agent_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    authority_id INTEGER NOT NULL REFERENCES agent_authorities(id) ON DELETE CASCADE,
    alias_form TEXT NOT NULL,
    alias_form_lower TEXT NOT NULL,
    alias_type TEXT NOT NULL CHECK(alias_type IN (
        'primary', 'variant_spelling', 'cross_script',
        'patronymic', 'acronym', 'word_reorder', 'historical'
    )),
    script TEXT DEFAULT 'latin',
    language TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_alias_authority
    ON agent_aliases(authority_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_alias_form_lower
    ON agent_aliases(alias_form_lower);
CREATE INDEX IF NOT EXISTS idx_agent_alias_type
    ON agent_aliases(alias_type);
CREATE INDEX IF NOT EXISTS idx_agent_alias_script
    ON agent_aliases(script);
"""

# ---------------------------------------------------------------------------
# Valid types
# ---------------------------------------------------------------------------

VALID_AGENT_TYPES = frozenset({"personal", "corporate", "meeting"})

VALID_ALIAS_TYPES = frozenset({
    "primary",
    "variant_spelling",
    "cross_script",
    "patronymic",
    "acronym",
    "word_reorder",
    "historical",
})

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AgentAlias:
    """A single name alias for an agent authority."""

    alias_form: str
    alias_type: str = "primary"
    script: str = "latin"
    language: Optional[str] = None
    is_primary: bool = False
    priority: int = 0
    notes: Optional[str] = None
    id: Optional[int] = None
    authority_id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class AgentAuthority:
    """A canonical agent identity with metadata and aliases."""

    canonical_name: str
    agent_type: str = "personal"
    confidence: float = 0.5
    dates_active: Optional[str] = None
    date_start: Optional[int] = None
    date_end: Optional[int] = None
    notes: Optional[str] = None
    sources: List[str] = field(default_factory=list)
    authority_uri: Optional[str] = None
    wikidata_id: Optional[str] = None
    viaf_id: Optional[str] = None
    nli_id: Optional[str] = None
    aliases: List[AgentAlias] = field(default_factory=list)
    id: Optional[int] = None


# ---------------------------------------------------------------------------
# Helper: detect script (delegates to clustering module)
# ---------------------------------------------------------------------------


def detect_script(text: str) -> str:
    """Detect script type: latin, hebrew, arabic, other.

    Delegates to ``scripts.metadata.clustering.detect_script`` and maps
    the ``"empty"`` return value to ``"other"`` for consistency.
    """
    result = _detect_script(text)
    if result == "empty":
        return "other"
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _parse_sources(raw: Optional[str]) -> List[str]:
    """Parse a JSON-encoded sources string into a list."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def _row_to_authority(row: sqlite3.Row) -> AgentAuthority:
    """Convert a DB row (without aliases) to an AgentAuthority."""
    return AgentAuthority(
        id=row["id"],
        canonical_name=row["canonical_name"],
        agent_type=row["agent_type"],
        confidence=row["confidence"],
        dates_active=row["dates_active"],
        date_start=row["date_start"],
        date_end=row["date_end"],
        notes=row["notes"],
        sources=_parse_sources(row["sources"]),
        authority_uri=row["authority_uri"],
        wikidata_id=row["wikidata_id"],
        viaf_id=row["viaf_id"],
        nli_id=row["nli_id"],
        aliases=[],
    )


def _row_to_alias(row: sqlite3.Row) -> AgentAlias:
    """Convert a DB row to an AgentAlias."""
    return AgentAlias(
        id=row["id"],
        authority_id=row["authority_id"],
        alias_form=row["alias_form"],
        alias_type=row["alias_type"],
        script=row["script"],
        language=row["language"],
        is_primary=bool(row["is_primary"]),
        priority=row["priority"],
        notes=row["notes"],
        created_at=row["created_at"],
    )


def _attach_aliases(
    conn: sqlite3.Connection, authority: AgentAuthority
) -> AgentAuthority:
    """Load and attach aliases to an authority record."""
    rows = conn.execute(
        "SELECT * FROM agent_aliases WHERE authority_id = ? "
        "ORDER BY is_primary DESC, priority DESC, id",
        (authority.id,),
    ).fetchall()
    authority.aliases = [_row_to_alias(r) for r in rows]
    return authority


# ---------------------------------------------------------------------------
# Store class
# ---------------------------------------------------------------------------


class AgentAuthorityStore:
    """CRUD operations for agent authority records.

    Every public method accepts an optional ``conn`` parameter.  When
    provided (e.g. an in-memory ``sqlite3.Connection`` for testing), that
    connection is used directly.  Otherwise a new connection is created
    from ``self.db_path``.
    """

    def __init__(self, db_path: Path | str):
        self.db_path = db_path

    # -- connection helper --------------------------------------------------

    def _conn(self, conn: Optional[sqlite3.Connection] = None) -> sqlite3.Connection:
        """Return the given connection or open a new one."""
        if conn is not None:
            return conn
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    def _should_close(self, conn: Optional[sqlite3.Connection]) -> bool:
        """Whether the caller did *not* pass a connection (we opened one)."""
        return conn is None

    # -- schema -------------------------------------------------------------

    def init_schema(self, conn: Optional[sqlite3.Connection] = None) -> None:
        """Create tables and indexes if they don't exist."""
        c = self._conn(conn)
        try:
            c.executescript(_SCHEMA_SQL)
            c.commit()
        finally:
            if self._should_close(conn):
                c.close()

    # -- create -------------------------------------------------------------

    def create(
        self,
        authority: AgentAuthority,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Insert a new agent authority record with aliases.

        Returns the auto-generated authority ID.
        """
        c = self._conn(conn)
        try:
            now = _now_iso()
            cursor = c.execute(
                """INSERT INTO agent_authorities
                   (canonical_name, canonical_name_lower, agent_type,
                    dates_active, date_start, date_end, notes, sources,
                    confidence, authority_uri, wikidata_id, viaf_id, nli_id,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    authority.canonical_name,
                    authority.canonical_name.lower(),
                    authority.agent_type,
                    authority.dates_active,
                    authority.date_start,
                    authority.date_end,
                    authority.notes,
                    json.dumps(authority.sources) if authority.sources else "[]",
                    authority.confidence,
                    authority.authority_uri,
                    authority.wikidata_id,
                    authority.viaf_id,
                    authority.nli_id,
                    now,
                    now,
                ),
            )
            auth_id = cursor.lastrowid
            authority.id = auth_id

            for alias in authority.aliases:
                self._insert_alias(c, auth_id, alias)

            c.commit()
            return auth_id
        finally:
            if self._should_close(conn):
                c.close()

    def _insert_alias(
        self,
        conn: sqlite3.Connection,
        authority_id: int,
        alias: AgentAlias,
    ) -> int:
        """Insert a single alias row (no commit)."""
        now = _now_iso()
        cursor = conn.execute(
            """INSERT INTO agent_aliases
               (authority_id, alias_form, alias_form_lower, alias_type,
                script, language, is_primary, priority, notes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                authority_id,
                alias.alias_form,
                alias.alias_form.lower(),
                alias.alias_type,
                alias.script,
                alias.language,
                int(alias.is_primary),
                alias.priority,
                alias.notes,
                now,
            ),
        )
        alias.id = cursor.lastrowid
        alias.authority_id = authority_id
        return cursor.lastrowid

    # -- read ---------------------------------------------------------------

    def get_by_id(
        self,
        authority_id: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[AgentAuthority]:
        """Get an agent authority by ID, including aliases."""
        c = self._conn(conn)
        try:
            row = c.execute(
                "SELECT * FROM agent_authorities WHERE id = ?",
                (authority_id,),
            ).fetchone()
            if row is None:
                return None
            auth = _row_to_authority(row)
            return _attach_aliases(c, auth)
        finally:
            if self._should_close(conn):
                c.close()

    def get_by_canonical_name(
        self,
        name: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[AgentAuthority]:
        """Look up by canonical name (case-insensitive)."""
        c = self._conn(conn)
        try:
            row = c.execute(
                "SELECT * FROM agent_authorities WHERE canonical_name_lower = ?",
                (name.lower(),),
            ).fetchone()
            if row is None:
                return None
            auth = _row_to_authority(row)
            return _attach_aliases(c, auth)
        finally:
            if self._should_close(conn):
                c.close()

    def search_by_alias(
        self,
        query: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[AgentAuthority]:
        """Look up agent by any known alias form (case-insensitive)."""
        c = self._conn(conn)
        try:
            row = c.execute(
                """SELECT aa.* FROM agent_authorities aa
                   JOIN agent_aliases al ON al.authority_id = aa.id
                   WHERE al.alias_form_lower = ?""",
                (query.lower(),),
            ).fetchone()
            if row is None:
                return None
            auth = _row_to_authority(row)
            return _attach_aliases(c, auth)
        finally:
            if self._should_close(conn):
                c.close()

    def resolve_agent_norm_to_authority_ids(
        self,
        agent_norm: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[int]:
        """Find authority IDs matching a given agent_norm value via alias lookup.

        Returns a list of authority IDs whose aliases match the query string
        (case-insensitive).
        """
        c = self._conn(conn)
        try:
            rows = c.execute(
                """SELECT DISTINCT al.authority_id
                   FROM agent_aliases al
                   WHERE al.alias_form_lower = ?""",
                (agent_norm.lower(),),
            ).fetchall()
            return [row["authority_id"] for row in rows]
        finally:
            if self._should_close(conn):
                c.close()

    def list_all(
        self,
        type_filter: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[AgentAuthority]:
        """List all authorities, optionally filtered by agent_type."""
        c = self._conn(conn)
        try:
            if type_filter:
                rows = c.execute(
                    "SELECT * FROM agent_authorities WHERE agent_type = ? "
                    "ORDER BY canonical_name",
                    (type_filter,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM agent_authorities ORDER BY canonical_name"
                ).fetchall()

            results = []
            for row in rows:
                auth = _row_to_authority(row)
                _attach_aliases(c, auth)
                results.append(auth)
            return results
        finally:
            if self._should_close(conn):
                c.close()

    # -- add alias ----------------------------------------------------------

    def add_alias(
        self,
        authority_id: int,
        alias: AgentAlias,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Add an alias to an existing authority. Returns alias ID."""
        c = self._conn(conn)
        try:
            alias_id = self._insert_alias(c, authority_id, alias)
            c.commit()
            return alias_id
        finally:
            if self._should_close(conn):
                c.close()

    # -- delete -------------------------------------------------------------

    def delete(
        self,
        authority_id: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Delete an authority and its aliases (cascade)."""
        c = self._conn(conn)
        try:
            c.execute("PRAGMA foreign_keys = ON")
            c.execute(
                "DELETE FROM agent_authorities WHERE id = ?",
                (authority_id,),
            )
            c.commit()
        finally:
            if self._should_close(conn):
                c.close()
