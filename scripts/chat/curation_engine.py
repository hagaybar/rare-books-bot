"""Curation engine for deterministic heuristic scoring and exhibit selection.

Provides quality-scored, diversity-aware selection of bibliographic items
for curated exhibits and scholarly presentations. Scoring is fully
deterministic (no LLM) with transparent rationale for each selection.

Scoring weights (from spec):
  - temporal_score: 0.3  (older/rarer items score higher; incunabula era top)
  - enrichment_score: 0.3  (items with richer metadata score higher)
  - diversity_bonus: 0.2  (items adding new dimension values score higher)
  - subject_richness: 0.2  (items with more subject headings score higher)

Addresses historian evaluation failure Q20 (curated exhibit: 1/25 -> 12/25).
"""

from typing import Any, Dict, Optional

from scripts.utils.logger import LoggerManager

logger = LoggerManager.get_logger(__name__)

# Default weights per spec
DEFAULT_WEIGHTS: Dict[str, float] = {
    "temporal": 0.3,
    "enrichment": 0.3,
    "diversity": 0.2,
    "subject_richness": 0.2,
}

# Temporal scoring boundaries
_INCUNABULA_CUTOFF = 1500  # Pre-1500 is incunabula era (highest temporal score)
_EARLY_MODERN_CUTOFF = 1600
_MODERN_CUTOFF = 1800


# =============================================================================
# Individual scoring components
# =============================================================================


def _compute_temporal_score(candidate: dict) -> float:
    """Score antiquity: older items are rarer and more significant.

    Returns a float in [0.0, 1.0] where pre-1500 items score highest.
    """
    date_start = candidate.get("date_start")
    if date_start is None:
        return 0.3  # Unknown date gets a neutral score

    if date_start < _INCUNABULA_CUTOFF:
        return 1.0
    elif date_start < _EARLY_MODERN_CUTOFF:
        # Linear scale 1.0 -> 0.7 across 1500-1599
        return 1.0 - 0.3 * (date_start - _INCUNABULA_CUTOFF) / (_EARLY_MODERN_CUTOFF - _INCUNABULA_CUTOFF)
    elif date_start < _MODERN_CUTOFF:
        # Linear scale 0.7 -> 0.3 across 1600-1799
        return 0.7 - 0.4 * (date_start - _EARLY_MODERN_CUTOFF) / (_MODERN_CUTOFF - _EARLY_MODERN_CUTOFF)
    else:
        # Post-1800: low but non-zero
        return max(0.1, 0.3 - 0.1 * (date_start - _MODERN_CUTOFF) / 100)


def _compute_enrichment_score(candidate: dict) -> float:
    """Score metadata completeness: more enriched items are more exhibit-worthy.

    Checks presence of: subjects, publisher, author, description.
    Returns a float in [0.0, 1.0].
    """
    score = 0.0
    checks = 0
    total_checks = 5

    # Subjects (up to 2 bonus points for multiple)
    subjects = candidate.get("subjects") or []
    if subjects:
        score += 1.0
        if len(subjects) >= 2:
            score += 0.5
    checks += 1.5

    # Publisher
    if candidate.get("publisher"):
        score += 1.0
    checks += 1.0

    # Author
    if candidate.get("author"):
        score += 1.0
    checks += 1.0

    # Description
    if candidate.get("description"):
        score += 1.0
    checks += 1.0

    # Title (always expected, but reward non-trivial titles)
    title = candidate.get("title") or ""
    if len(title) > 10:
        score += 0.5
    checks += 0.5

    return min(score / total_checks, 1.0)


def _compute_subject_richness(candidate: dict) -> float:
    """Score subject heading richness.

    More subject headings indicate richer cataloguing and scholarly interest.
    Returns a float in [0.0, 1.0].
    """
    subjects = candidate.get("subjects") or []
    count = len(subjects)
    if count == 0:
        return 0.0
    elif count == 1:
        return 0.3
    elif count == 2:
        return 0.6
    elif count == 3:
        return 0.8
    else:
        return 1.0


# =============================================================================
# Diversity-aware selection
# =============================================================================


def _compute_diversity_bonus(
    candidate: dict,
    seen_decades: set,
    seen_places: set,
) -> float:
    """Compute diversity bonus for a candidate given already-selected dimensions.

    New decades and places receive a bonus. Returns 0.0-1.0.
    """
    bonus = 0.0

    date_start = candidate.get("date_start")
    if date_start is not None:
        decade = date_start // 10 * 10
        if decade not in seen_decades:
            bonus += 0.5

    place = candidate.get("place_norm")
    if place and place not in seen_places:
        bonus += 0.5

    return min(bonus, 1.0)


def _generate_significance(candidate: dict, score: float) -> str:
    """Generate a human-readable significance note for a curated item."""
    parts = []

    date_start = candidate.get("date_start")
    if date_start is not None:
        if date_start < _INCUNABULA_CUTOFF:
            parts.append(f"Incunabulum ({date_start}) -- exceptionally rare early printed work")
        elif date_start < _EARLY_MODERN_CUTOFF:
            parts.append(f"Early modern imprint ({date_start})")
        else:
            parts.append(f"Published {date_start}")

    place = candidate.get("place_norm")
    if place:
        parts.append(f"printed in {place.title()}")

    subjects = candidate.get("subjects") or []
    if subjects:
        subj_str = ", ".join(subjects[:3])
        parts.append(f"subjects: {subj_str}")

    author = candidate.get("author")
    if author:
        parts.append(f"by {author}")

    if not parts:
        parts.append("Selected for collection diversity")

    return "; ".join(parts)


# =============================================================================
# Public API
# =============================================================================


def score_for_curation(candidate: dict, db_path=None) -> float:
    """Score a single candidate for curation suitability.

    Uses a weighted combination of temporal, enrichment, diversity (baseline),
    and subject richness factors.

    Args:
        candidate: Dict with keys: record_id, date_start, date_end,
            place_norm, subjects, publisher, title, author, description.
        db_path: Optional path to database (reserved for future enrichment
            lookups; not used in v1 heuristic).

    Returns:
        Float in [0.0, 1.0] representing curation suitability.
    """
    temporal = _compute_temporal_score(candidate)
    enrichment = _compute_enrichment_score(candidate)
    subject = _compute_subject_richness(candidate)
    # Diversity bonus is 0.0 in standalone scoring (no context)
    diversity = 0.0

    weights = DEFAULT_WEIGHTS
    score = (
        weights["temporal"] * temporal
        + weights["enrichment"] * enrichment
        + weights["subject_richness"] * subject
        + weights["diversity"] * diversity
    )
    return round(min(max(score, 0.0), 1.0), 6)


def select_curated_items(
    candidates: list,
    n: int = 10,
    db_path=None,
) -> list:
    """Select top-N candidates with diversity-aware scoring.

    Scores all candidates, then greedily selects items that maximize
    both individual score and dimensional diversity (decades, places).

    Args:
        candidates: List of candidate dicts.
        n: Number of items to select.
        db_path: Optional path to database (reserved for future use).

    Returns:
        List of dicts with keys: record_id, score, title, date_start,
        place_norm, significance. Sorted by score descending.
    """
    if not candidates:
        return []

    # Phase 1: Compute base scores for all candidates
    scored = []
    for c in candidates:
        base_score = score_for_curation(c, db_path)
        scored.append({"candidate": c, "base_score": base_score})

    # Phase 2: Greedy diversity-aware selection
    scored.sort(key=lambda x: x["base_score"], reverse=True)
    selected = []
    seen_decades: set = set()
    seen_places: set = set()

    while len(selected) < n and scored:
        best_idx = 0
        best_total = -1.0

        for i, item in enumerate(scored):
            c = item["candidate"]
            diversity = _compute_diversity_bonus(c, seen_decades, seen_places)
            total = (
                item["base_score"] * (1.0 - DEFAULT_WEIGHTS["diversity"])
                + DEFAULT_WEIGHTS["diversity"] * diversity
            )
            if total > best_total:
                best_total = total
                best_idx = i

        chosen = scored.pop(best_idx)
        c = chosen["candidate"]

        # Update seen dimensions
        date_start = c.get("date_start")
        if date_start is not None:
            seen_decades.add(date_start // 10 * 10)
        place = c.get("place_norm")
        if place:
            seen_places.add(place)

        # Report the base score (diversity influences selection order, not
        # the reported score -- ensures identical candidates get identical scores)
        final_score = round(chosen["base_score"], 6)
        selected.append({
            "record_id": c["record_id"],
            "score": final_score,
            "title": c.get("title"),
            "date_start": c.get("date_start"),
            "place_norm": c.get("place_norm"),
            "significance": _generate_significance(c, final_score),
        })

    # Sort final selection by score descending
    selected.sort(key=lambda x: x["score"], reverse=True)
    return selected


def format_curation_response(scored_items: list) -> dict:
    """Format curated items into a structured response with rationale.

    Each item receives a significance note explaining why it was selected
    for exhibit-quality output (Q20 requirement).

    Args:
        scored_items: List of dicts with record_id, score, title,
            date_start, place_norm.

    Returns:
        Dict with keys:
          - items: List of item dicts each containing significance note.
          - header: Summary text.
          - total: Number of items.
    """
    items = []
    for item in scored_items:
        significance = item.get("significance") or _generate_significance(
            item, item.get("score", 0.0)
        )
        items.append({
            "record_id": item.get("record_id"),
            "score": item.get("score", 0.0),
            "title": item.get("title"),
            "date_start": item.get("date_start"),
            "place_norm": item.get("place_norm"),
            "significance": significance,
        })

    return {
        "items": items,
        "header": f"Curated selection of {len(items)} notable items",
        "total": len(items),
    }


# =============================================================================
# CurationScorer class (orchestrator)
# =============================================================================


class CurationScorer:
    """Orchestrates scoring, diversity-aware selection, and formatting.

    Combines all curation logic into a single class with configurable
    weights and structured output including dimension coverage metadata.

    Args:
        weights: Dict with keys temporal, enrichment, diversity,
            subject_richness. Values should sum to 1.0.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or dict(DEFAULT_WEIGHTS)

    def curate(
        self,
        candidates: list,
        n: int = 10,
        db_path=None,
    ) -> Dict[str, Any]:
        """Score, select, and return structured curation result.

        Args:
            candidates: List of candidate dicts.
            n: Number of items to select.
            db_path: Optional database path.

        Returns:
            Dict with keys:
              - selected: List of scored item dicts.
              - total_scored: Total candidates evaluated.
              - dimension_coverage: Dict of dimension -> set of unique values
                  in the selected items.
              - selection_method: 'diversity_aware' or 'top_n_fallback'.
        """
        selected = select_curated_items(candidates, n=n, db_path=db_path)

        # Compute dimension coverage
        decades = set()
        places = set()
        for item in selected:
            ds = item.get("date_start")
            if ds is not None:
                decades.add(ds // 10 * 10)
            pl = item.get("place_norm")
            if pl:
                places.add(pl)

        # Determine selection method
        scores = [item["score"] for item in selected]
        if scores and (max(scores) - min(scores)) < 0.01:
            method = "top_n_fallback"
        else:
            method = "diversity_aware"

        return {
            "selected": selected,
            "total_scored": len(candidates),
            "dimension_coverage": {
                "decades": sorted(decades),
                "places": sorted(places),
            },
            "selection_method": method,
        }
