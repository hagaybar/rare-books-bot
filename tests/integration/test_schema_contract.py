"""Issue #9 / committee §B2: m3_contract.py must describe the database that
actually runs — drift (value_he, network/wikipedia tables) becomes a failing
test instead of a latent contract lie.
"""
import sqlite3
from pathlib import Path

import pytest

from scripts.marc.m3_contract import M3Tables, EXPECTED_SCHEMA as TABLE_COLUMNS

DB_PATH = Path("data/index/bibliographic.db")

pytestmark = pytest.mark.integration

_IGNORED_DB_TABLES = {"sqlite_sequence"}


@pytest.fixture()
def conn():
    if not DB_PATH.exists():
        pytest.skip("Bibliographic database not available")
    c = sqlite3.connect(str(DB_PATH))
    yield c
    c.close()


def _db_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {
        r[0] for r in rows
        if r[0] not in _IGNORED_DB_TABLES
        and "_fts" not in r[0]  # FTS virtual + shadow tables checked separately
    }


def _contract_tables():
    return {
        v for k, v in vars(M3Tables).items()
        if not k.startswith("_") and isinstance(v, str) and "_fts" not in v
    }


def test_every_contract_table_exists_in_db(conn):
    missing = _contract_tables() - _db_tables(conn)
    assert not missing, f"contract names tables absent from DB: {sorted(missing)}"


def test_every_db_table_is_in_contract(conn):
    undocumented = _db_tables(conn) - _contract_tables()
    assert not undocumented, (
        f"DB tables missing from m3_contract.py: {sorted(undocumented)}"
    )


def test_contract_columns_match_db(conn):
    mismatches = []
    for table, cols in TABLE_COLUMNS.items():
        if "_fts" in table:
            continue
        actual = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if not actual:
            continue  # covered by the table-existence test
        missing = set(cols) - actual
        undocumented = actual - set(cols)
        if missing or undocumented:
            mismatches.append((table, sorted(missing), sorted(undocumented)))
    assert not mismatches, f"column drift (table, contract-only, db-only): {mismatches}"
