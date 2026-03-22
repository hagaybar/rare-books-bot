"""Publisher authority record store.

CRUD operations for a two-table normalized authority system:
- ``publisher_authorities`` -- one row per canonical publisher identity
- ``publisher_variants`` -- one row per name variant, FK to authorities

Designed for the rare-books bibliographic database so that publisher
names can be linked to canonical identities with external-authority IDs
(VIAF, Wikidata, CERL).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from scripts.metadata.clustering import detect_script as _detect_script

# ---------------------------------------------------------------------------
# Schema SQL (embedded so we don't depend on the .sql file at runtime)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS publisher_authorities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,
    canonical_name_lower TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN (
        'printing_house', 'private_press', 'modern_publisher',
        'bibliophile_society', 'unknown_marker', 'unresearched'
    )),
    dates_active TEXT,
    date_start INTEGER,
    date_end INTEGER,
    location TEXT,
    notes TEXT,
    sources TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    is_missing_marker INTEGER NOT NULL DEFAULT 0,
    viaf_id TEXT,
    wikidata_id TEXT,
    cerl_id TEXT,
    branch TEXT,
    primary_language TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pub_auth_canonical_lower
    ON publisher_authorities(canonical_name_lower);
CREATE INDEX IF NOT EXISTS idx_pub_auth_type
    ON publisher_authorities(type);
CREATE INDEX IF NOT EXISTS idx_pub_auth_location
    ON publisher_authorities(location);
CREATE INDEX IF NOT EXISTS idx_pub_auth_branch
    ON publisher_authorities(branch);
CREATE INDEX IF NOT EXISTS idx_pub_auth_primary_language
    ON publisher_authorities(primary_language);

CREATE TABLE IF NOT EXISTS publisher_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    authority_id INTEGER NOT NULL REFERENCES publisher_authorities(id) ON DELETE CASCADE,
    variant_form TEXT NOT NULL,
    variant_form_lower TEXT NOT NULL,
    script TEXT DEFAULT 'latin',
    language TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pub_var_authority
    ON publisher_variants(authority_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pub_var_form_lower
    ON publisher_variants(variant_form_lower);
CREATE INDEX IF NOT EXISTS idx_pub_var_script
    ON publisher_variants(script);
"""

# ---------------------------------------------------------------------------
# Valid publisher types
# ---------------------------------------------------------------------------

VALID_TYPES = frozenset({
    "printing_house",
    "private_press",
    "modern_publisher",
    "bibliophile_society",
    "unknown_marker",
    "unresearched",
})

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PublisherVariant:
    """A single name variant for a publisher authority."""

    variant_form: str
    script: str = "latin"  # latin, hebrew, arabic, other
    language: Optional[str] = None
    is_primary: bool = False
    priority: int = 0  # Higher = preferred for display ordering
    notes: Optional[str] = None
    id: Optional[int] = None
    authority_id: Optional[int] = None


@dataclass
class PublisherAuthority:
    """A canonical publisher identity with metadata and variants."""

    canonical_name: str
    type: str  # one of VALID_TYPES
    confidence: float = 0.5
    dates_active: Optional[str] = None
    date_start: Optional[int] = None
    date_end: Optional[int] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    sources: List[str] = field(default_factory=list)
    is_missing_marker: bool = False
    viaf_id: Optional[str] = None
    wikidata_id: Optional[str] = None
    cerl_id: Optional[str] = None
    branch: Optional[str] = None  # Branch for printing dynasties (e.g., "Leiden")
    primary_language: Optional[str] = None  # Dominant language/script (ISO 639: "lat", "heb")
    variants: List[PublisherVariant] = field(default_factory=list)
    id: Optional[int] = None


# ---------------------------------------------------------------------------
# Helper: detect script (delegates to clustering module)
# ---------------------------------------------------------------------------


def detect_script(text: str) -> str:
    """Detect script type: latin, hebrew, arabic, other.

    Delegates to ``scripts.metadata.clustering.detect_script`` and maps
    the ``"empty"`` return value to ``"other"`` for consistency with the
    publisher_variants schema.
    """
    result = _detect_script(text)
    if result == "empty":
        return "other"
    return result


# ---------------------------------------------------------------------------
# Helpers
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


def _row_to_authority(row: sqlite3.Row) -> PublisherAuthority:
    """Convert a DB row (without variants) to a PublisherAuthority."""
    return PublisherAuthority(
        id=row["id"],
        canonical_name=row["canonical_name"],
        type=row["type"],
        confidence=row["confidence"],
        dates_active=row["dates_active"],
        date_start=row["date_start"],
        date_end=row["date_end"],
        location=row["location"],
        notes=row["notes"],
        sources=_parse_sources(row["sources"]),
        is_missing_marker=bool(row["is_missing_marker"]),
        viaf_id=row["viaf_id"],
        wikidata_id=row["wikidata_id"],
        cerl_id=row["cerl_id"],
        branch=row["branch"],
        primary_language=row["primary_language"],
        variants=[],
    )


def _row_to_variant(row: sqlite3.Row) -> PublisherVariant:
    """Convert a DB row to a PublisherVariant."""
    return PublisherVariant(
        id=row["id"],
        authority_id=row["authority_id"],
        variant_form=row["variant_form"],
        script=row["script"],
        language=row["language"],
        is_primary=bool(row["is_primary"]),
        priority=row["priority"],
        notes=row["notes"],
    )


def _attach_variants(
    conn: sqlite3.Connection, authority: PublisherAuthority
) -> PublisherAuthority:
    """Load and attach variants to an authority record."""
    rows = conn.execute(
        "SELECT * FROM publisher_variants WHERE authority_id = ? ORDER BY is_primary DESC, priority DESC, id",
        (authority.id,),
    ).fetchall()
    authority.variants = [_row_to_variant(r) for r in rows]
    return authority


# ---------------------------------------------------------------------------
# Store class
# ---------------------------------------------------------------------------


class PublisherAuthorityStore:
    """CRUD operations for publisher authority records.

    Every public method accepts an optional ``conn`` parameter.  When
    provided (e.g. an in-memory ``sqlite3.Connection`` for testing), that
    connection is used directly.  Otherwise a new connection is created
    from ``self.db_path``.
    """

    def __init__(self, db_path: Path):
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
        """Create tables if they don't exist."""
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
        authority: PublisherAuthority,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Insert a new publisher authority record with variants.

        Returns the auto-generated authority ID.
        """
        c = self._conn(conn)
        try:
            now = _now_iso()
            cursor = c.execute(
                """INSERT INTO publisher_authorities
                   (canonical_name, canonical_name_lower, type, dates_active,
                    date_start, date_end, location, notes, sources, confidence,
                    is_missing_marker, viaf_id, wikidata_id, cerl_id,
                    branch, primary_language,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    authority.canonical_name,
                    authority.canonical_name.lower(),
                    authority.type,
                    authority.dates_active,
                    authority.date_start,
                    authority.date_end,
                    authority.location,
                    authority.notes,
                    json.dumps(authority.sources) if authority.sources else "[]",
                    authority.confidence,
                    int(authority.is_missing_marker),
                    authority.viaf_id,
                    authority.wikidata_id,
                    authority.cerl_id,
                    authority.branch,
                    authority.primary_language,
                    now,
                    now,
                ),
            )
            auth_id = cursor.lastrowid
            authority.id = auth_id

            for var in authority.variants:
                self._insert_variant(c, auth_id, var)

            c.commit()
            return auth_id
        finally:
            if self._should_close(conn):
                c.close()

    def _insert_variant(
        self,
        conn: sqlite3.Connection,
        authority_id: int,
        variant: PublisherVariant,
    ) -> int:
        """Insert a single variant row (no commit)."""
        now = _now_iso()
        cursor = conn.execute(
            """INSERT INTO publisher_variants
               (authority_id, variant_form, variant_form_lower, script,
                language, is_primary, priority, notes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                authority_id,
                variant.variant_form,
                variant.variant_form.lower(),
                variant.script,
                variant.language,
                int(variant.is_primary),
                variant.priority,
                variant.notes,
                now,
            ),
        )
        variant.id = cursor.lastrowid
        variant.authority_id = authority_id
        return cursor.lastrowid

    # -- read ---------------------------------------------------------------

    def get_by_id(
        self,
        authority_id: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[PublisherAuthority]:
        """Get a publisher authority by ID, including variants."""
        c = self._conn(conn)
        try:
            row = c.execute(
                "SELECT * FROM publisher_authorities WHERE id = ?",
                (authority_id,),
            ).fetchone()
            if row is None:
                return None
            auth = _row_to_authority(row)
            return _attach_variants(c, auth)
        finally:
            if self._should_close(conn):
                c.close()

    def get_by_canonical_name(
        self,
        name: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[PublisherAuthority]:
        """Look up by canonical name (case-insensitive)."""
        c = self._conn(conn)
        try:
            row = c.execute(
                "SELECT * FROM publisher_authorities WHERE canonical_name_lower = ?",
                (name.lower(),),
            ).fetchone()
            if row is None:
                return None
            auth = _row_to_authority(row)
            return _attach_variants(c, auth)
        finally:
            if self._should_close(conn):
                c.close()

    def search_by_variant(
        self,
        variant: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[PublisherAuthority]:
        """Look up publisher by any known variant form (case-insensitive)."""
        c = self._conn(conn)
        try:
            row = c.execute(
                """SELECT pa.* FROM publisher_authorities pa
                   JOIN publisher_variants pv ON pv.authority_id = pa.id
                   WHERE pv.variant_form_lower = ?""",
                (variant.lower(),),
            ).fetchone()
            if row is None:
                return None
            auth = _row_to_authority(row)
            return _attach_variants(c, auth)
        finally:
            if self._should_close(conn):
                c.close()

    def list_all(
        self,
        type_filter: Optional[str] = None,
        branch_filter: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[PublisherAuthority]:
        """List all authorities, optionally filtered by type and/or branch."""
        c = self._conn(conn)
        try:
            conditions = []
            params: list = []
            if type_filter:
                conditions.append("type = ?")
                params.append(type_filter)
            if branch_filter:
                conditions.append("branch = ?")
                params.append(branch_filter)

            where_clause = ""
            if conditions:
                where_clause = " WHERE " + " AND ".join(conditions)

            rows = c.execute(
                f"SELECT * FROM publisher_authorities{where_clause} ORDER BY canonical_name",
                params,
            ).fetchall()
            results = []
            for row in rows:
                auth = _row_to_authority(row)
                _attach_variants(c, auth)
                results.append(auth)
            return results
        finally:
            if self._should_close(conn):
                c.close()

    # -- update -------------------------------------------------------------

    def update(
        self,
        authority: PublisherAuthority,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Update an existing authority record (does not modify variants)."""
        if authority.id is None:
            raise ValueError("Cannot update authority without an id")
        c = self._conn(conn)
        try:
            now = _now_iso()
            c.execute(
                """UPDATE publisher_authorities SET
                   canonical_name = ?, canonical_name_lower = ?, type = ?,
                   dates_active = ?, date_start = ?, date_end = ?,
                   location = ?, notes = ?, sources = ?, confidence = ?,
                   is_missing_marker = ?, viaf_id = ?, wikidata_id = ?,
                   cerl_id = ?, branch = ?, primary_language = ?,
                   updated_at = ?
                   WHERE id = ?""",
                (
                    authority.canonical_name,
                    authority.canonical_name.lower(),
                    authority.type,
                    authority.dates_active,
                    authority.date_start,
                    authority.date_end,
                    authority.location,
                    authority.notes,
                    json.dumps(authority.sources) if authority.sources else "[]",
                    authority.confidence,
                    int(authority.is_missing_marker),
                    authority.viaf_id,
                    authority.wikidata_id,
                    authority.cerl_id,
                    authority.branch,
                    authority.primary_language,
                    now,
                    authority.id,
                ),
            )
            c.commit()
        finally:
            if self._should_close(conn):
                c.close()

    # -- add variant --------------------------------------------------------

    def add_variant(
        self,
        authority_id: int,
        variant: PublisherVariant,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Add a variant to an existing authority. Returns variant ID."""
        c = self._conn(conn)
        try:
            vid = self._insert_variant(c, authority_id, variant)
            c.commit()
            return vid
        finally:
            if self._should_close(conn):
                c.close()

    # -- link to imprints ---------------------------------------------------

    def link_to_imprints(
        self,
        authority_id: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Match authority variants against imprints.publisher_norm.

        Returns count of matched imprint rows. Does **not** alter the
        imprints table (no FK column added).
        """
        c = self._conn(conn)
        try:
            # Get all variant forms (lowered) for this authority
            variant_rows = c.execute(
                "SELECT variant_form_lower FROM publisher_variants WHERE authority_id = ?",
                (authority_id,),
            ).fetchall()
            if not variant_rows:
                return 0

            placeholders = ",".join("?" for _ in variant_rows)
            values = [r["variant_form_lower"] for r in variant_rows]

            # Also include the canonical_name_lower
            auth_row = c.execute(
                "SELECT canonical_name_lower FROM publisher_authorities WHERE id = ?",
                (authority_id,),
            ).fetchone()
            if auth_row:
                placeholders += ",?"
                values.append(auth_row["canonical_name_lower"])

            # Check if imprints table exists before querying
            table_check = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='imprints'"
            ).fetchone()
            if not table_check:
                return 0

            count_row = c.execute(
                f"SELECT COUNT(*) as cnt FROM imprints WHERE publisher_norm IN ({placeholders})",
                values,
            ).fetchone()
            return count_row["cnt"] if count_row else 0
        finally:
            if self._should_close(conn):
                c.close()

    def get_linked_imprints(
        self,
        authority_id: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict]:
        """Get imprints linked to this authority via variant matching."""
        c = self._conn(conn)
        try:
            variant_rows = c.execute(
                "SELECT variant_form_lower FROM publisher_variants WHERE authority_id = ?",
                (authority_id,),
            ).fetchall()
            if not variant_rows:
                return []

            placeholders = ",".join("?" for _ in variant_rows)
            values = [r["variant_form_lower"] for r in variant_rows]

            # Also include canonical_name_lower
            auth_row = c.execute(
                "SELECT canonical_name_lower FROM publisher_authorities WHERE id = ?",
                (authority_id,),
            ).fetchone()
            if auth_row:
                placeholders += ",?"
                values.append(auth_row["canonical_name_lower"])

            # Check if imprints table exists
            table_check = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='imprints'"
            ).fetchone()
            if not table_check:
                return []

            rows = c.execute(
                f"""SELECT id, record_id, publisher_raw, publisher_norm,
                           place_norm, date_start, date_end
                    FROM imprints
                    WHERE publisher_norm IN ({placeholders})""",
                values,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if self._should_close(conn):
                c.close()

    # -- delete -------------------------------------------------------------

    def delete(
        self,
        authority_id: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Delete an authority and its variants (cascade)."""
        c = self._conn(conn)
        try:
            c.execute("PRAGMA foreign_keys = ON")
            c.execute(
                "DELETE FROM publisher_authorities WHERE id = ?",
                (authority_id,),
            )
            c.commit()
        finally:
            if self._should_close(conn):
                c.close()
