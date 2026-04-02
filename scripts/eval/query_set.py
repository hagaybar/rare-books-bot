"""Load and validate curated evaluation query sets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXPECTED_INTENTS = {
    "retrieval", "entity_exploration", "analytical", "comparison",
    "curation", "topical", "follow_up", "overview",
}

EXPECTED_DIFFICULTIES = {"simple", "moderate", "complex"}


@dataclass
class EvalQuery:
    """A single evaluation query with expected outcomes."""
    id: str
    query: str
    intent: str
    difficulty: str
    expected_filters: dict[str, Any]
    notes: str = ""


def load_query_set(path: Path) -> list[EvalQuery]:
    """Load evaluation queries from a JSON file."""
    raw = json.loads(path.read_text())
    return [
        EvalQuery(
            id=q["id"],
            query=q["query"],
            intent=q["intent"],
            difficulty=q["difficulty"],
            expected_filters=q.get("expected_filters", {}),
            notes=q.get("notes", ""),
        )
        for q in raw
    ]


def validate_query_set(queries: list[EvalQuery]) -> list[str]:
    """Validate a query set, returning a list of warnings/errors."""
    errors: list[str] = []

    # Check duplicate IDs
    ids = [q.id for q in queries]
    if len(ids) != len(set(ids)):
        dupes = [qid for qid in ids if ids.count(qid) > 1]
        errors.append(f"Duplicate query IDs: {set(dupes)}")

    # Check intent coverage
    covered = {q.intent for q in queries}
    missing = EXPECTED_INTENTS - covered
    if missing:
        errors.append(f"Missing intent coverage: {missing}")

    # Check difficulty coverage
    covered_diff = {q.difficulty for q in queries}
    missing_diff = EXPECTED_DIFFICULTIES - covered_diff
    if missing_diff:
        errors.append(f"Missing difficulty coverage: {missing_diff}")

    return errors
