"""Tests for M3 SQLite indexing and queries.

Tests the full M3 pipeline: schema creation, indexing, and query functions.
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from scripts.marc.m3_index import create_database, index_record, build_index
from scripts.marc.m3_query import (
    query_by_publisher_and_date_range,
    query_by_place_and_date_range,
    query_by_subject,
    query_by_agent,
    query_by_title,
    get_record_by_mms_id
)


@pytest.fixture
def test_db(tmp_path):
    """Create temporary test database with schema."""
    db_path = tmp_path / "test.db"
    schema_path = Path(__file__).parent.parent.parent.parent / "scripts" / "marc" / "m3_schema.sql"

    conn = create_database(db_path, schema_path)
    conn.close()

    return db_path


@pytest.fixture
def reference_record_m1m2():
    """Load reference record (M1+M2) from full dataset."""
    m1m2_path = Path(__file__).parent.parent.parent.parent / "data" / "m2" / "records_m1m2.jsonl"

    if not m1m2_path.exists():
        pytest.skip("M1+M2 JSONL not found - run m2_normalize.py first")

    # Find reference record
    with open(m1m2_path, 'r', encoding='utf-8') as f:
        for line in f:
            record = json.loads(line.strip())
            if record['source']['control_number']['value'] == '990011964120204146':
                return record

    pytest.skip("Reference record not found in M1+M2 JSONL")


class TestSchemaCreation:
    """Test database schema creation."""

    def test_schema_creates_all_tables(self, test_db):
        """Test that schema creates all expected tables."""
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()

        # Get table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = [
            'records',
            'titles',
            'imprints',
            'subjects',
            'agents',
            'languages',
            'notes',
            'physical_descriptions'
        ]

        for table in expected_tables:
            assert table in tables, f"Table {table} not found"

        conn.close()

    def test_schema_creates_fts_tables(self, test_db):
        """Test that schema creates FTS5 virtual tables."""
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()

        # Get virtual table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts' ORDER BY name")
        fts_tables = [row[0] for row in cursor.fetchall()]

        assert 'titles_fts' in fts_tables
        assert 'subjects_fts' in fts_tables

        conn.close()

    def test_schema_creates_indexes(self, test_db):
        """Test that schema creates expected indexes."""
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()

        # Get index names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        indexes = [row[0] for row in cursor.fetchall()]

        # Check for key indexes
        assert any('idx_records_mms_id' in idx for idx in indexes)
        assert any('idx_imprints_date_range' in idx for idx in indexes)
        assert any('idx_imprints_place_norm' in idx for idx in indexes)
        assert any('idx_imprints_publisher_norm' in idx for idx in indexes)

        conn.close()


class TestIndexing:
    """Test record indexing."""

    def test_index_reference_record(self, test_db, reference_record_m1m2):
        """Test indexing reference record (MMS 990011964120204146)."""
        conn = sqlite3.connect(str(test_db))

        # Index record
        stats = index_record(conn, reference_record_m1m2, "test.jsonl", 1)
        conn.commit()

        # Verify stats
        assert stats['titles'] >= 1  # At least main title
        assert stats['imprints'] >= 1
        assert stats['subjects'] >= 1
        assert stats['agents'] >= 1

        # Verify record was inserted
        cursor = conn.cursor()
        cursor.execute("SELECT mms_id FROM records WHERE mms_id = ?", ('990011964120204146',))
        assert cursor.fetchone() is not None

        conn.close()

    def test_index_imprints_with_m2_normalization(self, test_db, reference_record_m1m2):
        """Test that M2 normalized values are indexed correctly."""
        conn = sqlite3.connect(str(test_db))

        # Index record
        index_record(conn, reference_record_m1m2, "test.jsonl", 1)
        conn.commit()

        # Query imprints
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                date_raw, date_start, date_end, date_confidence, date_method,
                place_raw, place_norm, place_display, place_confidence, place_method,
                publisher_raw, publisher_norm, publisher_display, publisher_confidence, publisher_method
            FROM imprints i
            JOIN records r ON i.record_id = r.id
            WHERE r.mms_id = ?
        """, ('990011964120204146',))

        row = cursor.fetchone()
        assert row is not None

        # Verify M1 raw values
        assert row[0] == "[1680]"  # date_raw
        assert row[5] == "Paris :"  # place_raw
        assert row[10] is not None  # publisher_raw

        # Verify M2 normalized values
        assert row[1] == 1680  # date_start
        assert row[2] == 1680  # date_end
        assert row[3] == 0.95  # date_confidence (bracketed year)
        assert row[4] == "year_bracketed"  # date_method

        assert row[6] == "paris"  # place_norm
        assert row[7] == "Paris"  # place_display
        assert row[8] >= 0.8  # place_confidence

        assert row[11] is not None  # publisher_norm
        assert row[12] is not None  # publisher_display
        assert row[13] >= 0.8  # publisher_confidence

        conn.close()

    def test_index_subjects_with_scheme(self, test_db, reference_record_m1m2):
        """Test that subjects with scheme ($2) are indexed correctly."""
        conn = sqlite3.connect(str(test_db))

        # Index record
        index_record(conn, reference_record_m1m2, "test.jsonl", 1)
        conn.commit()

        # Query subjects
        cursor = conn.cursor()
        cursor.execute("""
            SELECT scheme, heading_lang, parts
            FROM subjects s
            JOIN records r ON s.record_id = r.id
            WHERE r.mms_id = ? AND s.source_tag = '610'
        """, ('990011964120204146',))

        row = cursor.fetchone()
        assert row is not None

        # Verify scheme and heading_lang
        assert row[0] == "nli"  # scheme from $2
        assert row[1] == "lat"  # heading_lang from $9

        # Verify parts is JSON
        parts = json.loads(row[2])
        assert isinstance(parts, dict)
        assert isinstance(parts.get('v'), list)  # Subdivision should be array

        conn.close()


class TestQueries:
    """Test query functions."""

    @pytest.fixture(autouse=True)
    def indexed_db(self, test_db, reference_record_m1m2):
        """Create database with indexed reference record."""
        conn = sqlite3.connect(str(test_db))
        index_record(conn, reference_record_m1m2, "test.jsonl", 1)
        conn.commit()
        conn.close()
        return test_db

    def test_query_by_place_and_date_range(self, indexed_db):
        """Test querying by place and date range."""
        # Query: Books printed in Paris in 17th century (1600-1699)
        result = query_by_place_and_date_range(
            indexed_db,
            place_norm="paris",
            start_year=1600,
            end_year=1699
        )

        # Should find reference record
        assert result.total_count >= 1
        assert '990011964120204146' in result.mms_ids

        # Check evidence
        place_evidence = [e for e in result.evidence if e.field == 'imprints.place_norm']
        assert len(place_evidence) >= 1
        assert place_evidence[0].value == "paris"
        assert place_evidence[0].confidence >= 0.8

    def test_query_by_publisher_and_date_range(self, indexed_db):
        """Test querying by publisher and date range."""
        # Query: Books published by C. Fosset in 17th century
        result = query_by_publisher_and_date_range(
            indexed_db,
            publisher_norm="c. fosset",
            start_year=1600,
            end_year=1699
        )

        # Should find reference record
        assert result.total_count >= 1
        assert '990011964120204146' in result.mms_ids

        # Check evidence
        publisher_evidence = [e for e in result.evidence if e.field == 'imprints.publisher_norm']
        assert len(publisher_evidence) >= 1
        assert publisher_evidence[0].value == "c. fosset"

    def test_query_by_subject_exact(self, indexed_db):
        """Test exact subject query."""
        # Reference record has subject "Catholic Church -- Prayers and devotions -- French."
        result = query_by_subject(
            indexed_db,
            subject_query="Catholic Church -- Prayers and devotions -- French.",
            use_fts=False
        )

        # Should find reference record
        assert result.total_count >= 1
        assert '990011964120204146' in result.mms_ids

        # Check evidence
        assert len(result.evidence) >= 1
        assert result.evidence[0].field == 'subjects.value'

    def test_query_by_subject_fts(self, indexed_db):
        """Test full-text subject query."""
        # FTS query with wildcards
        result = query_by_subject(
            indexed_db,
            subject_query="Catholic Church",
            use_fts=True
        )

        # Should find reference record
        assert result.total_count >= 1
        assert '990011964120204146' in result.mms_ids

    def test_query_by_title_fts(self, indexed_db):
        """Test full-text title query."""
        # Reference record has uniform title "[Office, Holy Week]"
        result = query_by_title(
            indexed_db,
            title_query="Holy Week",
            use_fts=True
        )

        # Should find reference record
        assert result.total_count >= 1
        assert '990011964120204146' in result.mms_ids

        # Check evidence
        assert len(result.evidence) >= 1
        assert 'titles.' in result.evidence[0].field

    def test_get_record_by_mms_id(self, indexed_db):
        """Test retrieving full record by MMS ID."""
        record = get_record_by_mms_id(indexed_db, '990011964120204146')

        assert record is not None
        assert record['mms_id'] == '990011964120204146'
        assert len(record['titles']) >= 1
        assert len(record['imprints']) >= 1
        assert len(record['subjects']) >= 1

    def test_query_with_confidence_filter(self, indexed_db):
        """Test querying with minimum confidence filter."""
        # Query with high confidence requirement
        result = query_by_place_and_date_range(
            indexed_db,
            place_norm="paris",
            start_year=1600,
            end_year=1699,
            min_confidence=0.8
        )

        # Should still find reference record (paris has confidence >= 0.8)
        assert result.total_count >= 1
        assert '990011964120204146' in result.mms_ids

    def test_query_empty_result(self, indexed_db):
        """Test query that returns no results."""
        result = query_by_place_and_date_range(
            indexed_db,
            place_norm="nonexistent_place",
            start_year=1600,
            end_year=1699
        )

        assert result.total_count == 0
        assert len(result.mms_ids) == 0
        assert len(result.evidence) == 0


class TestFullDatasetIndexing:
    """Test indexing full dataset."""

    def test_build_index_from_full_dataset(self, tmp_path):
        """Test building index from full M1+M2 JSONL dataset."""
        m1m2_path = Path(__file__).parent.parent.parent.parent / "data" / "m2" / "records_m1m2.jsonl"
        schema_path = Path(__file__).parent.parent.parent.parent / "scripts" / "marc" / "m3_schema.sql"

        if not m1m2_path.exists():
            pytest.skip("M1+M2 JSONL not found - run m2_normalize.py first")

        db_path = tmp_path / "full_test.db"

        # Build index
        stats = build_index(m1m2_path, db_path, schema_path)

        # Verify stats
        assert stats['total_records'] > 0
        assert stats['titles'] > 0
        assert stats['imprints'] > 0
        assert stats['subjects'] > 0
        assert len(stats['errors']) == 0

        # Verify database exists and has data
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM records")
        record_count = cursor.fetchone()[0]
        assert record_count == stats['total_records']
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
