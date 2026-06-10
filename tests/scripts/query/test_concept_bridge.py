"""Tests for the concept→vocabulary bridge (issue #2, item B5).

The bridge maps user concepts (e.g. "cartography", "מפות") to catalog
vocabulary that actually exists in this collection. Deterministic, no LLM.
"""
import sqlite3
from pathlib import Path

import pytest

from scripts.query.concept_bridge import Expansion, expand_concept, load_concept_map

DB_PATH = Path("data/index/bibliographic.db")


def test_expand_known_english_concept():
    expansions = expand_concept("cartography")
    assert Expansion(field="subject", value="geography") in expansions
    assert Expansion(field="physical_desc", value="map") in expansions


def test_expand_hebrew_alias():
    assert expand_concept("מפות") == expand_concept("cartography")


def test_expand_is_case_insensitive():
    assert expand_concept("Cartography") == expand_concept("cartography")


def test_unknown_term_returns_empty():
    assert expand_concept("astronomy-of-the-incas") == []


def test_expansion_fields_are_valid_filter_fields():
    from scripts.schemas.query_plan import FilterField
    valid = {f.value for f in FilterField}
    for expansions in load_concept_map().values():
        for exp in expansions:
            assert exp.field in valid


@pytest.mark.integration
def test_every_expansion_term_hits_the_db():
    """Issue requirement: expansions must be validated against headings
    that actually exist in the DB. A zero-hit term is vocabulary drift."""
    if not DB_PATH.exists():
        pytest.skip("Bibliographic database not available")
    conn = sqlite3.connect(str(DB_PATH))
    try:
        seen: set[tuple[str, str]] = set()
        for expansions in load_concept_map().values():
            for exp in expansions:
                key = (exp.field, exp.value)
                if key in seen:
                    continue
                seen.add(key)
                if exp.field == "subject":
                    n = conn.execute(
                        "SELECT COUNT(*) FROM subjects_fts WHERE subjects_fts MATCH ?",
                        (f'"{exp.value}"',),
                    ).fetchone()[0]
                elif exp.field == "title":
                    n = conn.execute(
                        "SELECT COUNT(*) FROM titles_fts WHERE titles_fts MATCH ?",
                        (f'"{exp.value}"',),
                    ).fetchone()[0]
                else:  # physical_desc
                    n = conn.execute(
                        "SELECT COUNT(*) FROM physical_descriptions "
                        "WHERE LOWER(value) LIKE LOWER(?)",
                        (f"%{exp.value}%",),
                    ).fetchone()[0]
                assert n >= 1, f"zero-hit expansion {key} — remove or fix it"
    finally:
        conn.close()


def test_expand_printing_concept_hebrew_aliases():
    """Printing-houses regression: בתי דפוס must bridge to catalog vocabulary."""
    expansions = expand_concept("בתי דפוס")
    assert expansions, "no printing concept in map"
    assert expansions == expand_concept("printing")
    assert Expansion(field="subject", value="printing") in expansions


def test_expand_jewish_concept():
    expansions = expand_concept("יהודיים")
    assert Expansion(field="subject", value="jews") in expansions
