"""Concept→vocabulary bridge for query relaxation (issue #2, item B5).

Maps user concepts ("cartography", "מפות") to catalog vocabulary that
actually exists in this collection ("Geography", "description and travel",
physical_desc "map"). The map is a curated, deterministic JSON file —
data/normalization/concept_maps/concept_map.json — validated against the
DB by tests. No LLM involvement.
"""
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MAP_PATH = Path("data/normalization/concept_maps/concept_map.json")

# Module-level guard: warn at most once per map path so a disabled bridge
# (missing/malformed map) is visible without flooding the logs (issue #55).
_warned_paths: set[str] = set()


def _warn_once(path: Path, reason: str) -> None:
    """Emit a single warning per map path explaining why the bridge is off."""
    key = str(path)
    if key in _warned_paths:
        return
    _warned_paths.add(key)
    logger.warning(
        "Concept bridge disabled — %s (map: %s). Concept expansion will "
        "not run; queries relying on it may return fewer candidates.",
        reason,
        path,
    )


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
    Returns {} if the map file is missing or malformed — the bridge is
    disabled, but a warning is logged once per path so an accidentally
    absent/broken map is visible (it is never silently swallowed).
    """
    if not path.exists():
        _warn_once(path, "concept map file is missing")
        return {}
    try:
        raw = _load_raw(str(path))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        _warn_once(path, f"concept map is unreadable or malformed: {exc}")
        return {}
    if not isinstance(raw, dict) or "concepts" not in raw:
        _warn_once(path, "concept map JSON lacks a top-level 'concepts' key")
        return {}
    try:
        result: dict[str, list[Expansion]] = {}
        for concept in raw["concepts"]:
            expansions = [
                Expansion(field=e["field"], value=e["value"])
                for e in concept.get("expansions", [])
            ]
            for term in [concept["canonical"], *concept.get("aliases", [])]:
                result[term.casefold()] = expansions
        return result
    except (KeyError, TypeError, AttributeError) as exc:
        _warn_once(path, f"concept map entry is malformed: {exc!r}")
        return {}


def expand_concept(term: str, path: Path = DEFAULT_MAP_PATH) -> list[Expansion]:
    """Return the catalog-vocabulary expansions for a user concept.

    Unknown terms return [] — the caller falls back to the literal term.
    """
    return load_concept_map(path).get(term.casefold(), [])
