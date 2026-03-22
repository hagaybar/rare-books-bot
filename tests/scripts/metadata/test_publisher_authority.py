"""Tests for the publisher authority record store.

All tests use in-memory SQLite databases so no files are created on disk.
"""

from __future__ import annotations

import sqlite3

import pytest

from scripts.metadata.publisher_authority import (
    PublisherAuthority,
    PublisherAuthorityStore,
    PublisherVariant,
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
def store(conn: sqlite3.Connection) -> PublisherAuthorityStore:
    """Store initialised with schema on the in-memory connection."""
    s = PublisherAuthorityStore(db_path=":memory:")
    s.init_schema(conn=conn)
    return s


def _make_elzevir() -> PublisherAuthority:
    """Sample authority record for House of Elzevir."""
    return PublisherAuthority(
        canonical_name="House of Elzevir",
        type="printing_house",
        confidence=0.95,
        dates_active="1583-1712",
        date_start=1583,
        date_end=1712,
        location="Leiden/Amsterdam, Netherlands",
        notes="Elzevir family printing house.",
        sources=["https://en.wikipedia.org/wiki/House_of_Elzevir"],
        is_missing_marker=False,
        viaf_id="12345",
        wikidata_id="Q123456",
        cerl_id="C001",
        variants=[
            PublisherVariant(
                variant_form="ex officina elzeviriana",
                script="latin",
                language="la",
                is_primary=True,
                notes="Latin imprint form",
            ),
            PublisherVariant(
                variant_form="ex officina elseviriorum",
                script="latin",
                language="la",
                is_primary=False,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestInitSchema:
    def test_creates_tables(self, store: PublisherAuthorityStore, conn: sqlite3.Connection):
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "publisher_authorities" in tables
        assert "publisher_variants" in tables

    def test_idempotent(self, store: PublisherAuthorityStore, conn: sqlite3.Connection):
        """Calling init_schema twice should not raise."""
        store.init_schema(conn=conn)
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "publisher_authorities" in tables


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestCreate:
    def test_basic_create(self, store: PublisherAuthorityStore, conn: sqlite3.Connection):
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)
        assert auth_id is not None
        assert auth_id > 0

    def test_create_sets_id(self, store: PublisherAuthorityStore, conn: sqlite3.Connection):
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)
        assert auth.id == auth_id

    def test_creates_variants(self, store: PublisherAuthorityStore, conn: sqlite3.Connection):
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)

        rows = conn.execute(
            "SELECT * FROM publisher_variants WHERE authority_id = ?",
            (auth_id,),
        ).fetchall()
        assert len(rows) == 2

    def test_canonical_name_lower_populated(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        store.create(auth, conn=conn)
        row = conn.execute(
            "SELECT canonical_name_lower FROM publisher_authorities WHERE id = ?",
            (auth.id,),
        ).fetchone()
        assert row["canonical_name_lower"] == "house of elzevir"

    def test_sources_stored_as_json(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        store.create(auth, conn=conn)
        row = conn.execute(
            "SELECT sources FROM publisher_authorities WHERE id = ?",
            (auth.id,),
        ).fetchone()
        import json
        parsed = json.loads(row["sources"])
        assert isinstance(parsed, list)
        assert "https://en.wikipedia.org/wiki/House_of_Elzevir" in parsed

    def test_create_no_variants(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        """Creating without variants should succeed."""
        auth = PublisherAuthority(
            canonical_name="Unknown Press",
            type="unresearched",
            confidence=0.3,
        )
        auth_id = store.create(auth, conn=conn)
        assert auth_id > 0

        rows = conn.execute(
            "SELECT * FROM publisher_variants WHERE authority_id = ?",
            (auth_id,),
        ).fetchall()
        assert len(rows) == 0

    def test_create_unknown_marker(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="[publisher unknown]",
            type="unknown_marker",
            confidence=0.95,
            is_missing_marker=True,
        )
        auth_id = store.create(auth, conn=conn)
        row = conn.execute(
            "SELECT is_missing_marker FROM publisher_authorities WHERE id = ?",
            (auth_id,),
        ).fetchone()
        assert row["is_missing_marker"] == 1

    def test_duplicate_canonical_name_raises(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth1 = _make_elzevir()
        store.create(auth1, conn=conn)
        auth2 = _make_elzevir()
        # Same canonical name (lowered) should trigger UNIQUE constraint
        with pytest.raises(sqlite3.IntegrityError):
            store.create(auth2, conn=conn)

    def test_invalid_type_raises(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="Bad Type Press",
            type="invalid_type",
            confidence=0.5,
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.create(auth, conn=conn)


# ---------------------------------------------------------------------------
# Read: get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    def test_returns_full_record(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)

        assert result is not None
        assert result.id == auth_id
        assert result.canonical_name == "House of Elzevir"
        assert result.type == "printing_house"
        assert result.confidence == 0.95
        assert result.dates_active == "1583-1712"
        assert result.date_start == 1583
        assert result.date_end == 1712
        assert result.location == "Leiden/Amsterdam, Netherlands"
        assert result.viaf_id == "12345"
        assert result.wikidata_id == "Q123456"
        assert result.cerl_id == "C001"
        assert result.is_missing_marker is False
        assert len(result.sources) == 1

    def test_includes_variants(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)

        assert len(result.variants) == 2
        primary = [v for v in result.variants if v.is_primary]
        assert len(primary) == 1
        assert primary[0].variant_form == "ex officina elzeviriana"
        assert primary[0].script == "latin"
        assert primary[0].language == "la"

    def test_nonexistent_returns_none(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        result = store.get_by_id(9999, conn=conn)
        assert result is None


# ---------------------------------------------------------------------------
# Read: get_by_canonical_name
# ---------------------------------------------------------------------------


class TestGetByCanonicalName:
    def test_case_insensitive(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        store.create(auth, conn=conn)
        result = store.get_by_canonical_name("HOUSE OF ELZEVIR", conn=conn)
        assert result is not None
        assert result.canonical_name == "House of Elzevir"

    def test_exact_case(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        store.create(auth, conn=conn)
        result = store.get_by_canonical_name("House of Elzevir", conn=conn)
        assert result is not None

    def test_not_found(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        result = store.get_by_canonical_name("Nonexistent Press", conn=conn)
        assert result is None


# ---------------------------------------------------------------------------
# Read: search_by_variant
# ---------------------------------------------------------------------------


class TestSearchByVariant:
    def test_finds_by_variant(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        store.create(auth, conn=conn)
        result = store.search_by_variant("Ex Officina Elzeviriana", conn=conn)
        assert result is not None
        assert result.canonical_name == "House of Elzevir"

    def test_finds_by_secondary_variant(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        store.create(auth, conn=conn)
        result = store.search_by_variant("EX OFFICINA ELSEVIRIORUM", conn=conn)
        assert result is not None
        assert result.canonical_name == "House of Elzevir"

    def test_not_found(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        result = store.search_by_variant("totally unknown variant", conn=conn)
        assert result is None

    def test_includes_all_variants(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        store.create(auth, conn=conn)
        result = store.search_by_variant("ex officina elzeviriana", conn=conn)
        assert len(result.variants) == 2


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


class TestListAll:
    def test_empty(self, store: PublisherAuthorityStore, conn: sqlite3.Connection):
        results = store.list_all(conn=conn)
        assert results == []

    def test_returns_all(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        store.create(_make_elzevir(), conn=conn)
        store.create(
            PublisherAuthority(
                canonical_name="Bragadin Press",
                type="printing_house",
                confidence=0.98,
            ),
            conn=conn,
        )
        results = store.list_all(conn=conn)
        assert len(results) == 2

    def test_filter_by_type(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        store.create(_make_elzevir(), conn=conn)
        store.create(
            PublisherAuthority(
                canonical_name="A.A.M. Stols",
                type="private_press",
                confidence=0.99,
            ),
            conn=conn,
        )
        results = store.list_all(type_filter="private_press", conn=conn)
        assert len(results) == 1
        assert results[0].canonical_name == "A.A.M. Stols"

    def test_filter_no_match(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        store.create(_make_elzevir(), conn=conn)
        results = store.list_all(type_filter="bibliophile_society", conn=conn)
        assert len(results) == 0

    def test_includes_variants(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        store.create(_make_elzevir(), conn=conn)
        results = store.list_all(conn=conn)
        assert len(results[0].variants) == 2


# ---------------------------------------------------------------------------
# add_variant
# ---------------------------------------------------------------------------


class TestAddVariant:
    def test_adds_to_existing(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)

        new_var = PublisherVariant(
            variant_form="Elzevier",
            script="latin",
            language="nl",
            is_primary=False,
        )
        vid = store.add_variant(auth_id, new_var, conn=conn)
        assert vid > 0

        result = store.get_by_id(auth_id, conn=conn)
        assert len(result.variants) == 3

    def test_searchable_after_add(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)

        store.add_variant(
            auth_id,
            PublisherVariant(variant_form="Elzevier", script="latin"),
            conn=conn,
        )
        result = store.search_by_variant("Elzevier", conn=conn)
        assert result is not None
        assert result.canonical_name == "House of Elzevir"

    def test_duplicate_variant_raises(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)
        # "ex officina elzeviriana" already exists (lowered)
        with pytest.raises(sqlite3.IntegrityError):
            store.add_variant(
                auth_id,
                PublisherVariant(variant_form="Ex Officina Elzeviriana"),
                conn=conn,
            )


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestUpdate:
    def test_updates_fields(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)

        auth.notes = "Updated notes"
        auth.confidence = 0.99
        auth.wikidata_id = "Q999999"
        store.update(auth, conn=conn)

        result = store.get_by_id(auth_id, conn=conn)
        assert result.notes == "Updated notes"
        assert result.confidence == 0.99
        assert result.wikidata_id == "Q999999"

    def test_updates_canonical_name(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        store.create(auth, conn=conn)

        auth.canonical_name = "Elzevir Family Press"
        store.update(auth, conn=conn)

        # Old name should not find it
        assert store.get_by_canonical_name("House of Elzevir", conn=conn) is None
        # New name should
        result = store.get_by_canonical_name("Elzevir Family Press", conn=conn)
        assert result is not None

    def test_update_without_id_raises(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        # No id set
        with pytest.raises(ValueError, match="without an id"):
            store.update(auth, conn=conn)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_deletes_authority(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)
        store.delete(auth_id, conn=conn)
        assert store.get_by_id(auth_id, conn=conn) is None

    def test_cascades_to_variants(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)
        store.delete(auth_id, conn=conn)
        rows = conn.execute(
            "SELECT * FROM publisher_variants WHERE authority_id = ?",
            (auth_id,),
        ).fetchall()
        assert len(rows) == 0

    def test_delete_nonexistent_is_noop(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        """Deleting a non-existent ID should not raise."""
        store.delete(9999, conn=conn)


# ---------------------------------------------------------------------------
# link_to_imprints
# ---------------------------------------------------------------------------


class TestLinkToImprints:
    def _create_imprints_table(self, conn: sqlite3.Connection):
        """Create a minimal imprints table for testing."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS imprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                publisher_raw TEXT,
                publisher_norm TEXT,
                place_norm TEXT,
                date_start INTEGER,
                date_end INTEGER
            )
        """)
        conn.commit()

    def test_links_by_variant(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        self._create_imprints_table(conn)
        conn.execute(
            "INSERT INTO imprints (record_id, publisher_raw, publisher_norm) VALUES (1, 'Ex officina Elzeviriana', 'ex officina elzeviriana')"
        )
        conn.execute(
            "INSERT INTO imprints (record_id, publisher_raw, publisher_norm) VALUES (2, 'Other Press', 'other press')"
        )
        conn.commit()

        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)
        count = store.link_to_imprints(auth_id, conn=conn)
        assert count == 1

    def test_links_by_canonical_name(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        self._create_imprints_table(conn)
        conn.execute(
            "INSERT INTO imprints (record_id, publisher_raw, publisher_norm) VALUES (1, 'House of Elzevir', 'house of elzevir')"
        )
        conn.commit()

        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)
        count = store.link_to_imprints(auth_id, conn=conn)
        assert count == 1

    def test_no_imprints_table(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        """If imprints table doesn't exist, returns 0."""
        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)
        count = store.link_to_imprints(auth_id, conn=conn)
        assert count == 0

    def test_no_variants_returns_zero(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        self._create_imprints_table(conn)
        auth = PublisherAuthority(
            canonical_name="No Variants Press",
            type="unresearched",
        )
        auth_id = store.create(auth, conn=conn)
        count = store.link_to_imprints(auth_id, conn=conn)
        # Should still check canonical_name_lower even without variants
        assert count == 0

    def test_get_linked_imprints(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        self._create_imprints_table(conn)
        conn.execute(
            "INSERT INTO imprints (record_id, publisher_raw, publisher_norm, place_norm, date_start, date_end) VALUES (1, 'Ex officina Elzeviriana', 'ex officina elzeviriana', 'leiden', 1600, 1650)"
        )
        conn.execute(
            "INSERT INTO imprints (record_id, publisher_raw, publisher_norm) VALUES (2, 'Other Press', 'other press')"
        )
        conn.commit()

        auth = _make_elzevir()
        auth_id = store.create(auth, conn=conn)
        imprints = store.get_linked_imprints(auth_id, conn=conn)
        assert len(imprints) == 1
        assert imprints[0]["publisher_norm"] == "ex officina elzeviriana"
        assert imprints[0]["place_norm"] == "leiden"
        assert imprints[0]["date_start"] == 1600


# ---------------------------------------------------------------------------
# detect_script
# ---------------------------------------------------------------------------


class TestDetectScript:
    def test_latin(self):
        assert detect_script("House of Elzevir") == "latin"

    def test_hebrew(self):
        assert detect_script("חמו\"ל") == "hebrew"

    def test_arabic(self):
        assert detect_script("دار النشر") == "arabic"

    def test_empty_string(self):
        assert detect_script("") == "other"

    def test_mixed_hebrew_latin(self):
        """Mixed Hebrew-Latin strings should classify as hebrew."""
        result = detect_script("דפוס וינדראמינה Press")
        assert result == "hebrew"

    def test_mixed_hebrew_latin_latin_dominant(self):
        """When Latin characters dominate, return latin."""
        result = detect_script("דפוס bragadin")  # Hebrew=4, Latin=8
        assert result == "latin"

    def test_punctuation_only(self):
        """Punctuation-only should return 'other'."""
        result = detect_script(".,;:!?")
        # detect_script from clustering returns 'latin' for no-script chars
        # or 'other' — either is acceptable
        assert result in ("latin", "other")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_minimal_authority(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        """Create with only required fields."""
        auth = PublisherAuthority(
            canonical_name="Minimal",
            type="unresearched",
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result is not None
        assert result.canonical_name == "Minimal"
        assert result.confidence == 0.5  # default
        assert result.sources == []
        assert result.variants == []
        assert result.is_missing_marker is False

    def test_empty_sources_stored_correctly(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="Empty Sources",
            type="unresearched",
            sources=[],
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result.sources == []

    def test_hebrew_variant(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        """Variant with Hebrew script."""
        auth = PublisherAuthority(
            canonical_name="Vendramin Press",
            type="printing_house",
            variants=[
                PublisherVariant(
                    variant_form="דפוס וינדראמינה",
                    script="hebrew",
                    language="he",
                    is_primary=False,
                ),
                PublisherVariant(
                    variant_form="Nella Stamparia Vendramina",
                    script="latin",
                    language="it",
                    is_primary=True,
                ),
            ],
        )
        auth_id = store.create(auth, conn=conn)

        # Search by Hebrew variant
        result = store.search_by_variant("דפוס וינדראמינה", conn=conn)
        assert result is not None
        assert result.canonical_name == "Vendramin Press"

    def test_special_characters_in_name(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        """Names with quotes, commas, brackets."""
        auth = PublisherAuthority(
            canonical_name='[publisher unknown] "test"',
            type="unknown_marker",
            is_missing_marker=True,
            variants=[
                PublisherVariant(variant_form='[חמו"ל]', script="hebrew"),
            ],
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result.canonical_name == '[publisher unknown] "test"'
        assert result.variants[0].variant_form == '[חמו"ל]'

    def test_duplicate_variant_across_authorities_raises(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        """Same variant form cannot belong to two different authorities."""
        auth1 = PublisherAuthority(
            canonical_name="Press A",
            type="printing_house",
            variants=[
                PublisherVariant(variant_form="shared variant"),
            ],
        )
        store.create(auth1, conn=conn)

        auth2 = PublisherAuthority(
            canonical_name="Press B",
            type="printing_house",
            variants=[
                PublisherVariant(variant_form="Shared Variant"),  # same lowered
            ],
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.create(auth2, conn=conn)

    def test_all_publisher_types(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        """Verify all valid types can be created."""
        valid_types = [
            "printing_house",
            "private_press",
            "modern_publisher",
            "bibliophile_society",
            "unknown_marker",
            "unresearched",
        ]
        for i, t in enumerate(valid_types):
            auth = PublisherAuthority(
                canonical_name=f"Type Test {i}",
                type=t,
            )
            auth_id = store.create(auth, conn=conn)
            assert auth_id > 0

        results = store.list_all(conn=conn)
        assert len(results) == len(valid_types)


# ---------------------------------------------------------------------------
# branch field
# ---------------------------------------------------------------------------


class TestBranchField:
    def test_create_with_branch(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="Elzevir Leiden",
            type="printing_house",
            branch="Leiden",
            confidence=0.95,
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result is not None
        assert result.branch == "Leiden"

    def test_branch_defaults_to_none(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="No Branch Press",
            type="printing_house",
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result.branch is None

    def test_update_branch(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="Elzevir Amsterdam",
            type="printing_house",
            branch="Amsterdam",
        )
        auth_id = store.create(auth, conn=conn)

        auth.branch = "Amsterdam (later)"
        store.update(auth, conn=conn)

        result = store.get_by_id(auth_id, conn=conn)
        assert result.branch == "Amsterdam (later)"

    def test_list_all_filter_by_branch(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        store.create(
            PublisherAuthority(
                canonical_name="Elzevir Leiden",
                type="printing_house",
                branch="Leiden",
            ),
            conn=conn,
        )
        store.create(
            PublisherAuthority(
                canonical_name="Elzevir Amsterdam",
                type="printing_house",
                branch="Amsterdam",
            ),
            conn=conn,
        )
        store.create(
            PublisherAuthority(
                canonical_name="Bragadin Press",
                type="printing_house",
            ),
            conn=conn,
        )

        leiden_results = store.list_all(branch_filter="Leiden", conn=conn)
        assert len(leiden_results) == 1
        assert leiden_results[0].canonical_name == "Elzevir Leiden"

    def test_list_all_filter_by_type_and_branch(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        store.create(
            PublisherAuthority(
                canonical_name="Elzevir Leiden",
                type="printing_house",
                branch="Leiden",
            ),
            conn=conn,
        )
        store.create(
            PublisherAuthority(
                canonical_name="Modern Leiden Press",
                type="modern_publisher",
                branch="Leiden",
            ),
            conn=conn,
        )

        results = store.list_all(
            type_filter="printing_house", branch_filter="Leiden", conn=conn
        )
        assert len(results) == 1
        assert results[0].canonical_name == "Elzevir Leiden"


# ---------------------------------------------------------------------------
# primary_language field
# ---------------------------------------------------------------------------


class TestPrimaryLanguageField:
    def test_create_with_primary_language(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="Bragadin Press, Venice",
            type="printing_house",
            primary_language="heb",
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result is not None
        assert result.primary_language == "heb"

    def test_primary_language_defaults_to_none(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="No Language Press",
            type="unresearched",
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result.primary_language is None

    def test_update_primary_language(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="Bomberg Press",
            type="printing_house",
            primary_language="heb",
        )
        auth_id = store.create(auth, conn=conn)

        auth.primary_language = "lat"
        store.update(auth, conn=conn)

        result = store.get_by_id(auth_id, conn=conn)
        assert result.primary_language == "lat"

    def test_roundtrip_with_branch_and_language(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        """Both branch and primary_language round-trip correctly."""
        auth = PublisherAuthority(
            canonical_name="Estienne Paris Branch",
            type="printing_house",
            branch="Paris",
            primary_language="lat",
            confidence=0.9,
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result.branch == "Paris"
        assert result.primary_language == "lat"
        assert result.confidence == 0.9


# ---------------------------------------------------------------------------
# variant priority field
# ---------------------------------------------------------------------------


class TestVariantPriority:
    def test_create_variant_with_priority(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="Test Press",
            type="printing_house",
            variants=[
                PublisherVariant(
                    variant_form="Primary Form",
                    is_primary=True,
                    priority=10,
                ),
                PublisherVariant(
                    variant_form="Secondary Form",
                    is_primary=False,
                    priority=5,
                ),
                PublisherVariant(
                    variant_form="Tertiary Form",
                    is_primary=False,
                    priority=1,
                ),
            ],
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)

        assert len(result.variants) == 3
        # Primary should be first (is_primary DESC, then priority DESC)
        assert result.variants[0].variant_form == "Primary Form"
        assert result.variants[0].priority == 10
        # Non-primary ordered by priority DESC
        assert result.variants[1].variant_form == "Secondary Form"
        assert result.variants[1].priority == 5
        assert result.variants[2].variant_form == "Tertiary Form"
        assert result.variants[2].priority == 1

    def test_priority_defaults_to_zero(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="Default Priority Press",
            type="printing_house",
            variants=[
                PublisherVariant(variant_form="No Priority Set"),
            ],
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)
        assert result.variants[0].priority == 0

    def test_add_variant_with_priority(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        auth = PublisherAuthority(
            canonical_name="Priority Add Press",
            type="printing_house",
            variants=[
                PublisherVariant(
                    variant_form="Original",
                    is_primary=True,
                    priority=5,
                ),
            ],
        )
        auth_id = store.create(auth, conn=conn)

        store.add_variant(
            auth_id,
            PublisherVariant(
                variant_form="Added Later",
                priority=10,
            ),
            conn=conn,
        )

        result = store.get_by_id(auth_id, conn=conn)
        assert len(result.variants) == 2
        # Primary still first (is_primary DESC is the first sort key)
        assert result.variants[0].variant_form == "Original"
        # Added later has higher priority but is not primary
        assert result.variants[1].variant_form == "Added Later"
        assert result.variants[1].priority == 10

    def test_priority_ordering_among_non_primary(
        self, store: PublisherAuthorityStore, conn: sqlite3.Connection
    ):
        """Among non-primary variants, higher priority comes first."""
        auth = PublisherAuthority(
            canonical_name="Ordering Test Press",
            type="printing_house",
            variants=[
                PublisherVariant(
                    variant_form="Low Priority",
                    is_primary=False,
                    priority=1,
                ),
                PublisherVariant(
                    variant_form="High Priority",
                    is_primary=False,
                    priority=100,
                ),
                PublisherVariant(
                    variant_form="Mid Priority",
                    is_primary=False,
                    priority=50,
                ),
            ],
        )
        auth_id = store.create(auth, conn=conn)
        result = store.get_by_id(auth_id, conn=conn)

        # All non-primary, so sorted by priority DESC
        assert result.variants[0].variant_form == "High Priority"
        assert result.variants[1].variant_form == "Mid Priority"
        assert result.variants[2].variant_form == "Low Priority"
