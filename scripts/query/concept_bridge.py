"""Concept→vocabulary bridge for query relaxation (issue #2, item B5).

Maps user concepts ("cartography", "מפות") to catalog vocabulary that
actually exists in this collection ("Geography", "description and travel",
physical_desc "map"). The map is a curated, deterministic JSON file —
data/normalization/concept_maps/concept_map.json — validated against the
DB by tests. No LLM involvement.
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_MAP_PATH = Path("data/normalization/concept_maps/concept_map.json")


@dataclass(frozen=True)
class Expansion:
    """One concept expansion: a (filter field, value) probe."""

    field: str  # "subject" | "title" | "physical_desc"
    value: str


@lru_cache(maxsize=1)
def _load_raw(path_str: str) -> dict:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def load_concept_map(path: Path = DEFAULT_MAP_PATH) -> dict[str, list[Expansion]]:
    """Load the concept map as {casefolded term -> expansions}.

    Canonical names and all aliases map to the same expansion list.
    Returns {} if the map file is missing (bridge disabled, not an error).
    """
    if not path.exists():
        return {}
    raw = _load_raw(str(path))
    result: dict[str, list[Expansion]] = {}
    for concept in raw.get("concepts", []):
        expansions = [
            Expansion(field=e["field"], value=e["value"])
            for e in concept.get("expansions", [])
        ]
        for term in [concept["canonical"], *concept.get("aliases", [])]:
            result[term.casefold()] = expansions
    return result


def expand_concept(term: str, path: Path = DEFAULT_MAP_PATH) -> list[Expansion]:
    """Return the catalog-vocabulary expansions for a user concept.

    Unknown terms return [] — the caller falls back to the literal term.
    """
    return load_concept_map(path).get(term.casefold(), [])
