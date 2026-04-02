import json
from pathlib import Path

import pytest

from scripts.eval.query_set import EvalQuery, load_query_set, validate_query_set


def test_load_query_set(tmp_path):
    """Loads queries from JSON file."""
    queries_file = tmp_path / "queries.json"
    queries_file.write_text(json.dumps([
        {
            "id": "q01",
            "query": "Books by Bomberg",
            "intent": "retrieval",
            "difficulty": "simple",
            "expected_filters": {"publisher": "daniel bomberg"},
            "notes": "test query",
        }
    ]))
    queries = load_query_set(queries_file)
    assert len(queries) == 1
    assert queries[0].id == "q01"
    assert queries[0].intent == "retrieval"
    assert queries[0].expected_filters == {"publisher": "daniel bomberg"}


def test_validate_query_set_catches_duplicate_ids(tmp_path):
    """Rejects query sets with duplicate IDs."""
    queries_file = tmp_path / "queries.json"
    queries_file.write_text(json.dumps([
        {"id": "q01", "query": "A", "intent": "retrieval", "difficulty": "simple",
         "expected_filters": {}, "notes": ""},
        {"id": "q01", "query": "B", "intent": "retrieval", "difficulty": "simple",
         "expected_filters": {}, "notes": ""},
    ]))
    queries = load_query_set(queries_file)
    errors = validate_query_set(queries)
    assert any("duplicate" in e.lower() for e in errors)


def test_validate_query_set_checks_intent_coverage(tmp_path):
    """Warns if not all intent types are covered."""
    queries_file = tmp_path / "queries.json"
    queries_file.write_text(json.dumps([
        {"id": "q01", "query": "A", "intent": "retrieval", "difficulty": "simple",
         "expected_filters": {}, "notes": ""},
    ]))
    queries = load_query_set(queries_file)
    errors = validate_query_set(queries)
    assert any("intent" in e.lower() for e in errors)
