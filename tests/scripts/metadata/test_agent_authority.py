"""Tests for the agent authority record store (TDD -- written before implementation).

All tests use in-memory SQLite databases so no files are created on disk.
These tests import from ``scripts.metadata.agent_authority`` which does not
yet exist -- running them will produce ImportError until the module is created.

Mirrors the pattern established in ``test_publisher_authority.py``.
"""

from __future__ import annotations

import sqlite3

import pytest

from scripts.metadata.agent_authority import (
    AgentAlias,
    AgentAuthority,
    AgentAuthorityStore,
    detect_script,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def conn() -> sqlite3.Connection:
    """In-memory SQLite connection with row_factory and FK enforcement."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


@pytest.fixture()
def store(conn: sqlite3.Connection) -> AgentAuthorityStore:
    """Store initialised with schema on the in-memory connection."""
    s = AgentAuthorityStore(db_path=":memory:")
    s.init_schema(conn=conn)
    return s


# ---------------------------------------------------------------------------
# Sample data factories
# ---------------------------------------------------------------------------


def _make_maimonides() -> AgentAuthority:
    """Maimonides: Latin canonical name, Hebrew patronymic, acronym forms.

    authority_uri mirrors a real NLI URI.  Three aliases cover the core
    cross-script scenario:
      - Latin primary: 'Maimonides, Moses'
      - Hebrew patronymic: 'משה בן מימון'
      - Hebrew acronym: 'רמב"ם'
    """
    return AgentAuthority(
        canonical_name="Maimonides, Moses",
        agent_type="personal",
        confidence=0.95,
        dates_active="1138-1204",
        date_start=1138,
        date_end=1204,
        notes="Philosopher, rabbi, physician.",
        sources=["https://viaf.org/viaf/100185495"],
        authority_uri="987007265654005171",
        wikidata_id="Q9200",
        viaf_id="100185495",
        nli_id="987007265654005171",
        aliases=[
            AgentAlias(
                alias_form="Maimonides, Moses",
                alias_type="primary",
                script="latin",
                language="la",
                is_primary=True,
                priority=10,
            ),
            AgentAlias(
                alias_form="משה בן מימון",
                alias_type="patronymic",
                script="hebrew",
                language="he",
                is_primary=False,
                priority=5,
            ),
            AgentAlias(
                alias_form='רמב"ם',
                alias_type="acronym",
                script="hebrew",
                language="he",
                is_primary=False,
                priority=3,
            ),
        ],
    )


def _make_buxtorf() -> AgentAuthority:
    """Johann Buxtorf the Elder: word-reorder scenario.

    DB has ``'buxtorf, johann'`` (surname-first).  The word-reorder alias
    ``'johann buxtorf'`` must also match.
    """
    return AgentAuthority(
        canonical_name="Buxtorf, Johann",
        agent_type="personal",
        confidence=0.90,
        dates_active="1564-1629",
        date_start=1564,
        date_end=1629,
        authority_uri="987007258658505171",
        viaf_id="54152415",
        aliases=[
            AgentAlias(
                alias_form="Buxtorf, Johann",
                alias_type="primary",
                script="latin",
                language="la",
                is_primary=True,
                priority=10,
            ),
            AgentAlias(
                alias_form="Johann Buxtorf",
                alias_type="word_reorder",
                script="latin",
                language="la",
                is_primary=False,
                priority=5,
            ),
        ],
    )


def _make_mendelssohn() -> AgentAuthority:
    """Moses Mendelssohn: cross-script scenario.

    Both Latin and Hebrew forms must resolve to the same authority.
    """
    return AgentAuthority(
        canonical_name="Mendelssohn, Moses",
        agent_type="personal",
        confidence=0.90,
        dates_active="1729-1786",
        date_start=1729,
        date_end=1786,
        authority_uri="987007265098305171",
        aliases=[
            AgentAlias(
                alias_form="Mendelssohn, Moses",
                alias_type="primary",
                script="latin",
                language="de",
                is_primary=True,
                priority=10,
            ),
            AgentAlias(
                alias_form="מנדלסון, משה",
                alias_type="cross_script",
                script="hebrew",
                language="he",
                is_primary=False,
                priority=5,
            ),
            AgentAlias(
                alias_form="Moses Mendelssohn",
                alias_type="word_reorder",
                script="latin",
                language="de",
                is_primary=False,
                priority=4,
            ),
            AgentAlias(
                alias_form="משה מנדלסון",
                alias_type="cross_script",
                script="hebrew",
                language="he",
                is_primary=False,
                priority=3,
            ),
        ],
    )


def _make_karo() -> AgentAuthority:
    """Joseph Karo: Latin-to-Hebrew scenario.

    DB only has Hebrew form. Latin aliases seeded from enrichment so that
    a query for 'Joseph Karo' resolves to Hebrew records.
    """
    return AgentAuthority(
        canonical_name="קארו, יוסף בן אפרים",
        agent_type="personal",
        confidence=0.85,
        dates_active="1488-1575",
        date_start=1488,
        date_end=1575,
        authority_uri="987007260372005171",
        aliases=[
            AgentAlias(
                alias_form="קארו, יוסף בן אפרים",
                alias_type="primary",
                script="hebrew",
                language="he",
                is_primary=True,
                priority=10,
            ),
            AgentAlias(
                alias_form="Joseph ben Ephraim Karo",
                alias_type="cross_script",
                script="latin",
                language="en",
                is_primary=False,
                priority=5,
            ),
            AgentAlias(
                alias_form="Joseph Karo",
                alias_type="variant_spelling",
                script="latin",
                language="en",
                is_primary=False,
                priority=4,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestInitSchema:
    def test_creates_tables(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Both agent_authorities and agent_aliases tables must exist."""
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "agent_authorities" in tables
        assert "agent_aliases" in tables

    def test_creates_indexes(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Key indexes must be created for performance."""
        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        # Authorities indexes
        assert "idx_agent_auth_canonical_lower" in indexes
        assert "idx_agent_auth_type" in indexes
        assert "idx_agent_auth_authority_uri" in indexes
        assert "idx_agent_auth_wikidata" in indexes
        # Aliases indexes
        assert "idx_agent_alias_authority" in indexes
        assert "idx_agent_alias_form_lower" in indexes
        assert "idx_agent_alias_type" in indexes
        assert "idx_agent_alias_script" in indexes

    def test_authorities_columns(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Verify agent_authorities has all expected columns from the schema."""
        cols = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(agent_authorities)"
            ).fetchall()
        }
        expected = {
            "id",
            "canonical_name",
            "canonical_name_lower",
            "agent_type",
            "dates_active",
            "date_start",
            "date_end",
            "notes",
            "sources",
            "confidence",
            "authority_uri",
            "wikidata_id",
            "viaf_id",
            "nli_id",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_aliases_columns(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Verify agent_aliases has all expected columns from the schema."""
        cols = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(agent_aliases)"
            ).fetchall()
        }
        expected = {
            "id",
            "authority_id",
            "alias_form",
            "alias_form_lower",
            "alias_type",
            "script",
            "language",
            "is_primary",
            "priority",
            "notes",
            "created_at",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_idempotent(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Calling init_schema twice should not raise."""
        store.init_schema(conn=conn)
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "agent_authorities" in tables

    def test_agent_type_check_constraint(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Invalid agent_type must be rejected by CHECK constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO agent_authorities
                   (canonical_name, canonical_name_lower, agent_type,
                    confidence, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("Test", "test", "invalid_type", 0.5, "now", "now"),
            )

    def test_alias_type_check_constraint(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Invalid alias_type must be rejected by CHECK constraint."""
        # First create a valid authority to reference
        conn.execute(
            """INSERT INTO agent_authorities
               (canonical_name, canonical_name_lower, agent_type,
                confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("Test", "test", "personal", 0.5, "now", "now"),
        )
        auth_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO agent_aliases
                   (authority_id, alias_form, alias_form_lower, alias_type,
                    is_primary, priority, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (auth_id, "Test", "test", "bogus_type", 0, 0, "now"),
            )


# ---------------------------------------------------------------------------
# Create and retrieve
# ---------------------------------------------------------------------------


class TestCreateAndRetrieve:
    def test_create_authority_and_retrieve(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Create Maimonides with 3 aliases, verify all fields round-trip."""
        auth = _make_maimonides()
        auth_id = store.create(auth, conn=conn)

        assert auth_id is not None
        assert auth_id > 0
        assert auth.id == auth_id

        result = store.get_by_id(auth_id, conn=conn)
        assert result is not None
        assert result.canonical_name == "Maimonides, Moses"
        assert result.agent_type == "personal"
        assert result.confidence == 0.95
        assert result.dates_active == "1138-1204"
        assert result.date_start == 1138
        assert result.date_end == 1204
        assert result.notes == "Philosopher, rabbi, physician."
        assert result.authority_uri == "987007265654005171"
        assert result.wikidata_id == "Q9200"
        assert result.viaf_id == "100185495"
        assert result.nli_id == "987007265654005171"
        assert "https://viaf.org/viaf/100185495" in result.sources
        assert len(result.aliases) == 3

    def test_canonical_name_lower_populated(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_maimonides()
        store.create(auth, conn=conn)
        row = conn.execute(
            "SELECT canonical_name_lower FROM agent_authorities WHERE id = ?",
            (auth.id,),
        ).fetchone()
        assert row["canonical_name_lower"] == "maimonides, moses"

    def test_alias_form_lower_populated(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_buxtorf()
        store.create(auth, conn=conn)
        rows = conn.execute(
            "SELECT alias_form, alias_form_lower FROM agent_aliases WHERE authority_id = ?",
            (auth.id,),
        ).fetchall()
        for row in rows:
            assert row["alias_form_lower"] == row["alias_form"].lower()

    def test_sources_stored_as_json(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        import json

        auth = _make_maimonides()
        store.create(auth, conn=conn)
        row = conn.execute(
            "SELECT sources FROM agent_authorities WHERE id = ?",
            (auth.id,),
        ).fetchone()
        parsed = json.loads(row["sources"])
        assert isinstance(parsed, list)
        assert "https://viaf.org/viaf/100185495" in parsed

    def test_create_no_aliases(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Creating without aliases should succeed."""
        auth = AgentAuthority(
            canonical_name="Unknown Agent",
            agent_type="personal",
            confidence=0.3,
        )
        auth_id = store.create(auth, conn=conn)
        assert auth_id > 0

        result = store.get_by_id(auth_id, conn=conn)
        assert result.aliases == []

    def test_create_sets_timestamps(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_buxtorf()
        store.create(auth, conn=conn)
        row = conn.execute(
            "SELECT created_at, updated_at FROM agent_authorities WHERE id = ?",
            (auth.id,),
        ).fetchone()
        assert row["created_at"] is not None
        assert row["updated_at"] is not None

    def test_nonexistent_returns_none(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        result = store.get_by_id(9999, conn=conn)
        assert result is None


# ---------------------------------------------------------------------------
# Search by alias
# ---------------------------------------------------------------------------


class TestSearchByAlias:
    def test_search_by_alias_case_insensitive(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Search 'moshe ben maimon' (all lowercase) must match Maimonides
        whose alias is stored as 'משה בן מימון'.

        Actually, the case-insensitive test is about Latin forms.
        Search 'maimonides, moses' in varied casing must match.
        """
        auth = _make_maimonides()
        store.create(auth, conn=conn)

        # Search with different casing
        result = store.search_by_alias("MAIMONIDES, MOSES", conn=conn)
        assert result is not None
        assert result.canonical_name == "Maimonides, Moses"

        # Mixed case
        result2 = store.search_by_alias("Maimonides, Moses", conn=conn)
        assert result2 is not None
        assert result2.canonical_name == "Maimonides, Moses"

    def test_search_by_alias_cross_script(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Search Hebrew acronym 'רמב"ם' must match Maimonides."""
        auth = _make_maimonides()
        store.create(auth, conn=conn)

        result = store.search_by_alias('רמב"ם', conn=conn)
        assert result is not None
        assert result.canonical_name == "Maimonides, Moses"
        assert result.authority_uri == "987007265654005171"

    def test_search_by_alias_hebrew_patronymic(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Search Hebrew patronymic 'משה בן מימון' must match Maimonides."""
        auth = _make_maimonides()
        store.create(auth, conn=conn)

        result = store.search_by_alias("משה בן מימון", conn=conn)
        assert result is not None
        assert result.canonical_name == "Maimonides, Moses"

    def test_search_by_alias_word_reorder(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Search 'johann buxtorf' (first-last) must match 'Buxtorf, Johann'."""
        auth = _make_buxtorf()
        store.create(auth, conn=conn)

        result = store.search_by_alias("johann buxtorf", conn=conn)
        assert result is not None
        assert result.canonical_name == "Buxtorf, Johann"

    def test_search_by_alias_mendelssohn_hebrew(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Search Hebrew form of Mendelssohn must match Latin authority."""
        auth = _make_mendelssohn()
        store.create(auth, conn=conn)

        result = store.search_by_alias("מנדלסון, משה", conn=conn)
        assert result is not None
        assert result.canonical_name == "Mendelssohn, Moses"

    def test_search_by_alias_karo_latin_to_hebrew(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Search Latin 'Joseph Karo' must match Hebrew-canonical authority."""
        auth = _make_karo()
        store.create(auth, conn=conn)

        result = store.search_by_alias("Joseph Karo", conn=conn)
        assert result is not None
        assert result.canonical_name == "קארו, יוסף בן אפרים"

    def test_search_by_alias_karo_full_latin(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Search Latin full form 'Joseph ben Ephraim Karo' must match."""
        auth = _make_karo()
        store.create(auth, conn=conn)

        result = store.search_by_alias("Joseph ben Ephraim Karo", conn=conn)
        assert result is not None
        assert result.canonical_name == "קארו, יוסף בן אפרים"

    def test_search_not_found(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        result = store.search_by_alias("totally unknown name", conn=conn)
        assert result is None

    def test_search_returns_all_aliases(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Searching by one alias returns the full authority with all aliases."""
        auth = _make_maimonides()
        store.create(auth, conn=conn)

        result = store.search_by_alias('רמב"ם', conn=conn)
        assert len(result.aliases) == 3


# ---------------------------------------------------------------------------
# Unique alias constraint
# ---------------------------------------------------------------------------


class TestUniqueAliasConstraint:
    def test_duplicate_alias_same_authority_raises(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Duplicate alias_form_lower within the same authority raises IntegrityError."""
        auth = AgentAuthority(
            canonical_name="Test Agent",
            agent_type="personal",
            aliases=[
                AgentAlias(
                    alias_form="Duplicate Name",
                    alias_type="primary",
                    is_primary=True,
                ),
                AgentAlias(
                    alias_form="duplicate name",  # same lowered
                    alias_type="variant_spelling",
                    is_primary=False,
                ),
            ],
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.create(auth, conn=conn)

    def test_duplicate_alias_cross_authority_raises(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Same alias_form_lower across two different authorities raises IntegrityError."""
        auth1 = AgentAuthority(
            canonical_name="Agent One",
            agent_type="personal",
            aliases=[
                AgentAlias(
                    alias_form="Shared Name Form",
                    alias_type="primary",
                    is_primary=True,
                ),
            ],
        )
        store.create(auth1, conn=conn)

        auth2 = AgentAuthority(
            canonical_name="Agent Two",
            agent_type="personal",
            aliases=[
                AgentAlias(
                    alias_form="shared name form",  # same lowered
                    alias_type="primary",
                    is_primary=True,
                ),
            ],
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.create(auth2, conn=conn)


# ---------------------------------------------------------------------------
# Delete and cascade
# ---------------------------------------------------------------------------


class TestDeleteCascadesAliases:
    def test_delete_removes_authority(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_maimonides()
        auth_id = store.create(auth, conn=conn)
        store.delete(auth_id, conn=conn)
        assert store.get_by_id(auth_id, conn=conn) is None

    def test_delete_cascades_aliases(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Deleting an authority must cascade-delete all its aliases (FK)."""
        auth = _make_maimonides()
        auth_id = store.create(auth, conn=conn)

        # Verify aliases exist before delete
        alias_count_before = conn.execute(
            "SELECT COUNT(*) as cnt FROM agent_aliases WHERE authority_id = ?",
            (auth_id,),
        ).fetchone()["cnt"]
        assert alias_count_before == 3

        store.delete(auth_id, conn=conn)

        alias_count_after = conn.execute(
            "SELECT COUNT(*) as cnt FROM agent_aliases WHERE authority_id = ?",
            (auth_id,),
        ).fetchone()["cnt"]
        assert alias_count_after == 0

    def test_delete_nonexistent_is_noop(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Deleting a non-existent ID should not raise."""
        store.delete(9999, conn=conn)


# ---------------------------------------------------------------------------
# Script detection
# ---------------------------------------------------------------------------


class TestDetectScript:
    def test_detect_script_latin(self):
        assert detect_script("Maimonides, Moses") == "latin"

    def test_detect_script_hebrew(self):
        assert detect_script("משה בן מימון") == "hebrew"

    def test_detect_script_hebrew_acronym(self):
        assert detect_script('רמב"ם') == "hebrew"

    def test_detect_script_mixed_hebrew_dominant(self):
        """Mixed text with Hebrew majority should return 'hebrew'."""
        result = detect_script("קארו, יוסף בן אפרים Joseph")
        assert result == "hebrew"

    def test_detect_script_empty(self):
        assert detect_script("") == "other"

    def test_detect_script_arabic(self):
        assert detect_script("ابن ميمون") == "arabic"


# ---------------------------------------------------------------------------
# List all with type filter
# ---------------------------------------------------------------------------


class TestListAllWithTypeFilter:
    def test_list_all_empty(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        results = store.list_all(conn=conn)
        assert results == []

    def test_list_all_returns_all(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        store.create(_make_maimonides(), conn=conn)
        store.create(_make_buxtorf(), conn=conn)
        store.create(_make_karo(), conn=conn)
        results = store.list_all(conn=conn)
        assert len(results) == 3

    def test_list_all_filter_by_agent_type(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Filter by agent_type='personal' returns only personal agents."""
        store.create(_make_maimonides(), conn=conn)
        # Create a corporate agent
        corp = AgentAuthority(
            canonical_name="Aldine Press",
            agent_type="corporate",
            confidence=0.80,
            aliases=[
                AgentAlias(
                    alias_form="Aldine Press",
                    alias_type="primary",
                    script="latin",
                    is_primary=True,
                ),
            ],
        )
        store.create(corp, conn=conn)

        personal = store.list_all(type_filter="personal", conn=conn)
        assert len(personal) == 1
        assert personal[0].canonical_name == "Maimonides, Moses"

        corporate = store.list_all(type_filter="corporate", conn=conn)
        assert len(corporate) == 1
        assert corporate[0].canonical_name == "Aldine Press"

    def test_list_all_filter_no_match(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        store.create(_make_maimonides(), conn=conn)
        results = store.list_all(type_filter="meeting", conn=conn)
        assert len(results) == 0

    def test_list_all_includes_aliases(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Listing must include aliases for each authority."""
        store.create(_make_maimonides(), conn=conn)
        results = store.list_all(conn=conn)
        assert len(results) == 1
        assert len(results[0].aliases) == 3


# ---------------------------------------------------------------------------
# Add alias to existing authority
# ---------------------------------------------------------------------------


class TestAddAliasToExisting:
    def test_add_alias_to_existing_authority(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Dynamically adding a new alias to an existing authority."""
        auth = _make_buxtorf()
        auth_id = store.create(auth, conn=conn)

        new_alias = AgentAlias(
            alias_form="Buxtorfius",
            alias_type="historical",
            script="latin",
            language="la",
            is_primary=False,
            priority=2,
        )
        alias_id = store.add_alias(auth_id, new_alias, conn=conn)
        assert alias_id > 0

        result = store.get_by_id(auth_id, conn=conn)
        assert len(result.aliases) == 3  # 2 original + 1 added

    def test_added_alias_is_searchable(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Newly added alias must be immediately searchable."""
        auth = _make_buxtorf()
        auth_id = store.create(auth, conn=conn)

        store.add_alias(
            auth_id,
            AgentAlias(
                alias_form="Buxtorfius",
                alias_type="historical",
                script="latin",
            ),
            conn=conn,
        )
        result = store.search_by_alias("Buxtorfius", conn=conn)
        assert result is not None
        assert result.canonical_name == "Buxtorf, Johann"

    def test_add_duplicate_alias_raises(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Adding an alias whose lowered form already exists must raise."""
        auth = _make_buxtorf()
        auth_id = store.create(auth, conn=conn)

        with pytest.raises(sqlite3.IntegrityError):
            store.add_alias(
                auth_id,
                AgentAlias(
                    alias_form="buxtorf, johann",  # already exists lowered
                    alias_type="variant_spelling",
                ),
                conn=conn,
            )


# ---------------------------------------------------------------------------
# Get by canonical name
# ---------------------------------------------------------------------------


class TestGetByCanonicalName:
    def test_case_insensitive_lookup(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_maimonides()
        store.create(auth, conn=conn)
        result = store.get_by_canonical_name("MAIMONIDES, MOSES", conn=conn)
        assert result is not None
        assert result.canonical_name == "Maimonides, Moses"

    def test_hebrew_canonical_name(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Hebrew canonical name must be retrievable."""
        auth = _make_karo()
        store.create(auth, conn=conn)
        result = store.get_by_canonical_name("קארו, יוסף בן אפרים", conn=conn)
        assert result is not None

    def test_not_found(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        result = store.get_by_canonical_name("Nonexistent", conn=conn)
        assert result is None


# ---------------------------------------------------------------------------
# Valid agent types
# ---------------------------------------------------------------------------


class TestValidAgentTypes:
    def test_personal_type(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        auth = AgentAuthority(
            canonical_name="Personal Agent", agent_type="personal"
        )
        auth_id = store.create(auth, conn=conn)
        assert auth_id > 0

    def test_corporate_type(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        auth = AgentAuthority(
            canonical_name="Corporate Agent", agent_type="corporate"
        )
        auth_id = store.create(auth, conn=conn)
        assert auth_id > 0

    def test_meeting_type(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        auth = AgentAuthority(
            canonical_name="Meeting Agent", agent_type="meeting"
        )
        auth_id = store.create(auth, conn=conn)
        assert auth_id > 0

    def test_invalid_type_raises(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        auth = AgentAuthority(
            canonical_name="Bad Type", agent_type="invalid_type"
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.create(auth, conn=conn)


# ---------------------------------------------------------------------------
# Valid alias types
# ---------------------------------------------------------------------------


class TestValidAliasTypes:
    @pytest.mark.parametrize(
        "alias_type",
        [
            "primary",
            "variant_spelling",
            "cross_script",
            "patronymic",
            "acronym",
            "word_reorder",
            "historical",
        ],
    )
    def test_valid_alias_types(
        self,
        store: AgentAuthorityStore,
        conn: sqlite3.Connection,
        alias_type: str,
    ):
        """All 7 defined alias types must be accepted."""
        auth = AgentAuthority(
            canonical_name=f"Agent for {alias_type}",
            agent_type="personal",
            aliases=[
                AgentAlias(
                    alias_form=f"Alias for {alias_type}",
                    alias_type=alias_type,
                    is_primary=(alias_type == "primary"),
                ),
            ],
        )
        auth_id = store.create(auth, conn=conn)
        assert auth_id > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_minimal_authority(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Create with only required fields."""
        auth = AgentAuthority(
            canonical_name="Minimal Agent",
            agent_type="personal",
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result is not None
        assert result.canonical_name == "Minimal Agent"
        assert result.confidence == 0.5  # default
        assert result.sources == []
        assert result.aliases == []
        assert result.authority_uri is None
        assert result.wikidata_id is None
        assert result.viaf_id is None
        assert result.nli_id is None

    def test_special_characters_in_name(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Names with quotes, commas, brackets, Hebrew quotation marks."""
        auth = AgentAuthority(
            canonical_name='רמב"ם (Maimonides)',
            agent_type="personal",
            aliases=[
                AgentAlias(
                    alias_form='רמב"ם',
                    alias_type="acronym",
                    script="hebrew",
                ),
            ],
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result.canonical_name == 'רמב"ם (Maimonides)'
        assert result.aliases[0].alias_form == 'רמב"ם'

    def test_duplicate_canonical_name_raises(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Same canonical_name_lower should trigger UNIQUE constraint."""
        auth1 = AgentAuthority(
            canonical_name="Unique Agent",
            agent_type="personal",
            aliases=[
                AgentAlias(
                    alias_form="alias one",
                    alias_type="primary",
                    is_primary=True,
                ),
            ],
        )
        store.create(auth1, conn=conn)

        auth2 = AgentAuthority(
            canonical_name="unique agent",  # same lowered
            agent_type="personal",
            aliases=[
                AgentAlias(
                    alias_form="alias two",
                    alias_type="primary",
                    is_primary=True,
                ),
            ],
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.create(auth2, conn=conn)

    def test_empty_sources_stored_correctly(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        auth = AgentAuthority(
            canonical_name="Empty Sources Agent",
            agent_type="personal",
            sources=[],
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result.sources == []

    def test_alias_priority_ordering(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Aliases should be ordered: is_primary DESC, priority DESC."""
        auth = _make_maimonides()
        store.create(auth, conn=conn)
        result = store.get_by_id(auth.id, conn=conn)

        # Primary alias (priority=10) should be first
        assert result.aliases[0].is_primary is True
        assert result.aliases[0].alias_form == "Maimonides, Moses"
        # Then by priority descending
        assert result.aliases[1].priority >= result.aliases[2].priority


# ---------------------------------------------------------------------------
# Resolve agent_norm to authority IDs
# ---------------------------------------------------------------------------


class TestResolveAgentNorm:
    """Tests for resolve_agent_norm_to_authority_ids if the method exists.

    This is a query-support method that takes an agent_norm search string
    and returns matching authority IDs via alias lookup.
    """

    def test_resolve_returns_authority_ids(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Given a search string, resolve to the set of matching authority IDs."""
        auth = _make_maimonides()
        auth_id = store.create(auth, conn=conn)

        ids = store.resolve_agent_norm_to_authority_ids(
            "maimonides, moses", conn=conn
        )
        assert auth_id in ids

    def test_resolve_cross_script(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """Hebrew alias resolves to authority ID."""
        auth = _make_maimonides()
        auth_id = store.create(auth, conn=conn)

        ids = store.resolve_agent_norm_to_authority_ids(
            'רמב"ם', conn=conn
        )
        assert auth_id in ids

    def test_resolve_no_match(
        self, store: AgentAuthorityStore, conn: sqlite3.Connection
    ):
        """No match returns empty set/list."""
        ids = store.resolve_agent_norm_to_authority_ids(
            "nonexistent person", conn=conn
        )
        assert len(ids) == 0
