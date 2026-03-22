"""Tests for M3 schema contract runtime validation.

Validates that validate_schema() correctly detects missing tables and columns.
"""

import sqlite3
from pathlib import Path

import pytest

from scripts.marc.m3_contract import (
    EXPECTED_SCHEMA,
    M3Tables,
    M3Columns,
    validate_schema,
)


def _create_full_schema(conn: sqlite3.Connection) -> None:
    """Create all tables from EXPECTED_SCHEMA in the given connection."""
    for table_name, columns in EXPECTED_SCHEMA.items():
        col_defs = ", ".join(f"{col} TEXT" for col in columns)
        conn.execute(f"CREATE TABLE {table_name} ({col_defs})")
    conn.commit()


class TestValidateSchemaValid:
    """Tests with a fully valid schema."""

    def test_valid_schema_returns_empty_list(self):
        """A database with all expected tables and columns should pass."""
        conn = sqlite3.connect(":memory:")
        _create_full_schema(conn)

        errors = validate_schema(conn)
        assert errors == []

    def test_valid_schema_with_path(self, tmp_path):
        """validate_schema() should accept a Path argument."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _create_full_schema(conn)
        conn.close()

        errors = validate_schema(db_path)
        assert errors == []

    def test_extra_columns_are_ignored(self):
        """Extra columns in a table should not cause errors."""
        conn = sqlite3.connect(":memory:")
        for table_name, columns in EXPECTED_SCHEMA.items():
            col_defs = ", ".join(f"{col} TEXT" for col in columns)
            col_defs += ", extra_col TEXT"
            conn.execute(f"CREATE TABLE {table_name} ({col_defs})")
        conn.commit()

        errors = validate_schema(conn)
        assert errors == []


class TestValidateSchemaMissingTable:
    """Tests for missing table detection."""

    def test_missing_one_table(self):
        """A missing table should produce exactly one error string."""
        conn = sqlite3.connect(":memory:")
        for table_name, columns in EXPECTED_SCHEMA.items():
            if table_name == M3Tables.IMPRINTS:
                continue  # skip imprints
            col_defs = ", ".join(f"{col} TEXT" for col in columns)
            conn.execute(f"CREATE TABLE {table_name} ({col_defs})")
        conn.commit()

        errors = validate_schema(conn)
        assert len(errors) == 1
        assert "imprints" in errors[0]
        assert "missing table" in errors[0]

    def test_empty_database(self):
        """An empty database should produce one error per expected table."""
        conn = sqlite3.connect(":memory:")

        errors = validate_schema(conn)
        assert len(errors) == len(EXPECTED_SCHEMA)
        for err in errors:
            assert "missing table" in err


class TestValidateSchemaMissingColumn:
    """Tests for missing column detection."""

    def test_missing_one_column(self):
        """A table missing one expected column should produce one error."""
        conn = sqlite3.connect(":memory:")
        for table_name, columns in EXPECTED_SCHEMA.items():
            if table_name == M3Tables.RECORDS:
                # Omit the 'source_file' column
                columns = [c for c in columns if c != M3Columns.Records.SOURCE_FILE]
            col_defs = ", ".join(f"{col} TEXT" for col in columns)
            conn.execute(f"CREATE TABLE {table_name} ({col_defs})")
        conn.commit()

        errors = validate_schema(conn)
        assert len(errors) == 1
        assert "source_file" in errors[0]
        assert "records" in errors[0]
        assert "missing column" in errors[0]

    def test_missing_multiple_columns(self):
        """Missing several columns should produce one error each."""
        conn = sqlite3.connect(":memory:")
        dropped = {"date_start", "date_end", "date_confidence"}
        for table_name, columns in EXPECTED_SCHEMA.items():
            if table_name == M3Tables.IMPRINTS:
                columns = [c for c in columns if c not in dropped]
            col_defs = ", ".join(f"{col} TEXT" for col in columns)
            conn.execute(f"CREATE TABLE {table_name} ({col_defs})")
        conn.commit()

        errors = validate_schema(conn)
        assert len(errors) == len(dropped)
        for err in errors:
            assert "imprints" in err
            assert "missing column" in err


class TestValidateSchemaLogging:
    """Tests that warnings are emitted via logging."""

    def test_missing_table_logs_warning(self, caplog):
        """Missing table should log a warning."""
        conn = sqlite3.connect(":memory:")

        with caplog.at_level("WARNING", logger="scripts.marc.m3_contract"):
            validate_schema(conn)

        assert any("missing table" in record.message for record in caplog.records)

    def test_valid_schema_no_warnings(self, caplog):
        """Valid schema should produce no warnings."""
        conn = sqlite3.connect(":memory:")
        _create_full_schema(conn)

        with caplog.at_level("WARNING", logger="scripts.marc.m3_contract"):
            validate_schema(conn)

        assert len(caplog.records) == 0


class TestExpectedSchemaConsistency:
    """Sanity checks on the EXPECTED_SCHEMA mapping itself."""

    def test_all_regular_tables_present(self):
        """EXPECTED_SCHEMA should cover every non-FTS table in M3Tables."""
        regular_tables = [
            v for k, v in vars(M3Tables).items()
            if not k.startswith("_") and isinstance(v, str) and "fts" not in v
        ]
        for table in regular_tables:
            assert table in EXPECTED_SCHEMA, f"Table {table} not in EXPECTED_SCHEMA"

    def test_each_table_has_columns(self):
        """Every table in EXPECTED_SCHEMA should have at least one column."""
        for table_name, columns in EXPECTED_SCHEMA.items():
            assert len(columns) > 0, f"Table {table_name} has no columns"
