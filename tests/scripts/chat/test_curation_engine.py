"""Tests for the E2 curation engine (TDD - written before implementation).

Tests for scripts.chat.curation_engine which provides deterministic heuristic
scoring, diversity-aware selection, and exhibit formatting for CandidateSet
subsets.

Scoring weights (from spec):
  - temporal_score: 0.3  (older/rarer items score higher)
  - enrichment_score: 0.3  (items with more metadata score higher)
  - diversity_bonus: 0.2  (items that add new dimension values score higher)
  - subject_richness: 0.2  (items with more subject headings score higher)

These tests address report failure Q20 (Curated exhibit: 1/25 -> 12/25).
All tests should FAIL initially with ModuleNotFoundError since the module
does not yet exist.
"""

import pytest

from scripts.chat.curation_engine import (
    CurationScorer,
    score_for_curation,
    select_curated_items,
    format_curation_response,
)


# =============================================================================
# Helpers: build lightweight candidate dicts for testing
# =============================================================================

def _make_candidate(
    record_id: str,
    date_start: int | None = 1600,
    date_end: int | None = None,
    place_norm: str | None = "venice",
    subjects: list[str] | None = None,
    publisher: str | None = None,
    title: str | None = "A rare book",
    author: str | None = None,
    description: str | None = None,
) -> dict:
    """Return a minimal candidate dict matching the fields curation_engine expects.

    Uses a plain dict so tests do not depend on Candidate Pydantic import.
    The curation engine should accept dicts with these keys.
    """
    return {
        "record_id": record_id,
        "date_start": date_start,
        "date_end": date_end or date_start,
        "place_norm": place_norm,
        "subjects": subjects or [],
        "publisher": publisher,
        "title": title,
        "author": author,
        "description": description,
    }


# =============================================================================
# 1. score_for_curation returns a float in [0.0, 1.0]
# =============================================================================


class TestScoreForCuration:
    """Verify score_for_curation returns a bounded float."""

    def test_score_for_curation_returns_float(self):
        """score_for_curation must return a float between 0.0 and 1.0 inclusive."""
        candidate = _make_candidate("rec001", date_start=1550, place_norm="paris")
        score = score_for_curation(candidate)

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


# =============================================================================
# 2. Temporal weight: older items score higher
# =============================================================================


class TestTemporalWeight:
    """Older items (pre-1500) should receive a higher temporal factor."""

    def test_score_temporal_weight(self):
        """A 1450 item should score higher on the temporal factor than a 1750 item.

        The temporal_score component (weight 0.3) rewards antiquity.
        Pre-1500 (incunabula era) items are rarer and more significant.
        """
        old_candidate = _make_candidate(
            "rec_old", date_start=1450, place_norm="venice", subjects=["History"]
        )
        new_candidate = _make_candidate(
            "rec_new", date_start=1750, place_norm="venice", subjects=["History"]
        )

        score_old = score_for_curation(old_candidate)
        score_new = score_for_curation(new_candidate)

        assert score_old > score_new, (
            f"Older item (1450) scored {score_old} should beat newer item (1750) "
            f"scored {score_new} due to temporal weight"
        )


# =============================================================================
# 3. Enrichment weight: items with more metadata score higher
# =============================================================================


class TestEnrichmentWeight:
    """Items with richer metadata should score higher on the enrichment factor."""

    def test_score_enrichment_weight(self):
        """A candidate with subjects, description, author, and publisher should
        score higher than one with minimal metadata.

        The enrichment_score component (weight 0.3) rewards metadata completeness.
        """
        rich_candidate = _make_candidate(
            "rec_rich",
            date_start=1600,
            place_norm="amsterdam",
            subjects=["Theology", "Philosophy", "History"],
            publisher="Elsevier",
            author="Spinoza",
            description="A treatise on ethics",
        )
        sparse_candidate = _make_candidate(
            "rec_sparse",
            date_start=1600,
            place_norm="amsterdam",
            subjects=[],
            publisher=None,
            author=None,
            description=None,
        )

        score_rich = score_for_curation(rich_candidate)
        score_sparse = score_for_curation(sparse_candidate)

        assert score_rich > score_sparse, (
            f"Enriched item scored {score_rich} should beat sparse item "
            f"scored {score_sparse} due to enrichment weight"
        )


# =============================================================================
# 4. select_curated_items returns top N sorted by score
# =============================================================================


class TestSelectCuratedItems:
    """Verify select_curated_items returns top-N in descending score order."""

    def test_select_curated_items_returns_top_n(self):
        """Given 5 candidates, selecting top 3 should return the 3 highest-scoring
        items in descending score order.
        """
        candidates = [
            _make_candidate("rec_a", date_start=1750),  # least old
            _make_candidate("rec_b", date_start=1450, subjects=["History", "Art"]),  # oldest + subjects
            _make_candidate("rec_c", date_start=1550, subjects=["Theology"]),
            _make_candidate("rec_d", date_start=1500, subjects=["History", "Science", "Math"]),
            _make_candidate("rec_e", date_start=1650),
        ]

        result = select_curated_items(candidates, n=3)

        assert len(result) == 3
        # Results should be sorted by score descending
        scores = [item["score"] for item in result]
        assert scores == sorted(scores, reverse=True), (
            f"Results should be sorted by score descending, got {scores}"
        )
        # Each result must have a record_id and score
        for item in result:
            assert "record_id" in item
            assert "score" in item
            assert isinstance(item["score"], float)


# =============================================================================
# 5. Diversity: selected items should span multiple decades/places
# =============================================================================


class TestDiversity:
    """Diversity bonus should promote items from different decades and places."""

    def test_select_curated_items_diversity(self):
        """When many candidates share the same place but a few have different places,
        diversity-aware selection should include items from multiple places
        even if they have slightly lower individual scores.

        Diversity bonus (weight 0.2) rewards new dimension values (decade, place, etc.).
        """
        # 6 candidates from Venice (dominant place), 2 from other places
        candidates = [
            _make_candidate("ven_1", date_start=1500, place_norm="venice", subjects=["History"]),
            _make_candidate("ven_2", date_start=1510, place_norm="venice", subjects=["History"]),
            _make_candidate("ven_3", date_start=1520, place_norm="venice", subjects=["History"]),
            _make_candidate("ven_4", date_start=1530, place_norm="venice", subjects=["History"]),
            _make_candidate("ven_5", date_start=1540, place_norm="venice", subjects=["History"]),
            _make_candidate("ven_6", date_start=1550, place_norm="venice", subjects=["History"]),
            _make_candidate("par_1", date_start=1500, place_norm="paris", subjects=["History"]),
            _make_candidate("ams_1", date_start=1500, place_norm="amsterdam", subjects=["History"]),
        ]

        result = select_curated_items(candidates, n=5)

        places = {item["record_id"].split("_")[0] for item in result}
        assert len(places) >= 2, (
            f"Selection of 5 from 3 places should span at least 2 places, "
            f"got places from: {[item['record_id'] for item in result]}"
        )

        # Also check decade diversity: items span multiple decades
        decades = set()
        for item in result:
            candidate = next(c for c in candidates if c["record_id"] == item["record_id"])
            if candidate["date_start"]:
                decades.add(candidate["date_start"] // 10 * 10)
        assert len(decades) >= 2, (
            f"Selection should span at least 2 decades, got {decades}"
        )


# =============================================================================
# 6. Format curation response includes rationale
# =============================================================================


class TestFormatCurationResponse:
    """Each curated item in the formatted response must have a significance note."""

    def test_format_curation_response_includes_rationale(self):
        """format_curation_response should produce a structured response where
        each item includes a human-readable significance/rationale string.

        This is critical for exhibit-quality output (Q20 requirement).
        """
        scored_items = [
            {
                "record_id": "rec001",
                "score": 0.85,
                "title": "Tractatus Theologico-Politicus",
                "date_start": 1470,
                "place_norm": "venice",
            },
            {
                "record_id": "rec002",
                "score": 0.72,
                "title": "De Revolutionibus",
                "date_start": 1543,
                "place_norm": "nuremberg",
            },
        ]

        response = format_curation_response(scored_items)

        assert "items" in response
        assert len(response["items"]) == 2

        for item in response["items"]:
            assert "significance" in item or "rationale" in item, (
                f"Each item must have a significance/rationale note, got keys: {list(item.keys())}"
            )
            # The rationale should be a non-empty string
            note = item.get("significance") or item.get("rationale")
            assert isinstance(note, str)
            assert len(note) > 0, "Significance note must be non-empty"


# =============================================================================
# 7. Empty input returns empty result
# =============================================================================


class TestEdgeCaseEmpty:
    """Empty input must produce empty output without errors."""

    def test_empty_input_returns_empty(self):
        """Passing an empty list of candidates should return an empty list,
        not raise an exception.
        """
        result = select_curated_items([], n=5)

        assert isinstance(result, list)
        assert len(result) == 0


# =============================================================================
# 8. Single item returns that item
# =============================================================================


class TestEdgeCaseSingle:
    """A single candidate should be returned as-is."""

    def test_single_item_returns_item(self):
        """When only one candidate is provided and n >= 1, it should be returned."""
        candidates = [
            _make_candidate("sole_item", date_start=1480, place_norm="mainz"),
        ]

        result = select_curated_items(candidates, n=5)

        assert len(result) == 1
        assert result[0]["record_id"] == "sole_item"
        assert "score" in result[0]


# =============================================================================
# 9. All identical scores handled gracefully
# =============================================================================


class TestEdgeCaseIdenticalScores:
    """When all candidates have identical metadata, scoring should not crash."""

    def test_all_identical_scores(self):
        """Candidates with identical metadata should all receive the same score.
        select_curated_items should still return n items without errors.

        Per spec: degrades to pure top-N-by-score with selection_method='top_n_fallback'.
        """
        candidates = [
            _make_candidate(f"twin_{i}", date_start=1600, place_norm="london", subjects=["History"])
            for i in range(10)
        ]

        result = select_curated_items(candidates, n=5)

        assert len(result) == 5
        # All scores should be equal (or very close due to floating point)
        scores = [item["score"] for item in result]
        assert max(scores) - min(scores) < 0.01, (
            f"Identical candidates should have near-identical scores, got {scores}"
        )
        # Should not crash, and all record_ids should be unique
        record_ids = [item["record_id"] for item in result]
        assert len(set(record_ids)) == 5


# =============================================================================
# 10. CurationScorer class orchestrates scoring
# =============================================================================


class TestCurationScorerClass:
    """CurationScorer is the orchestrator class that combines scoring + selection."""

    def test_curation_scorer_class(self):
        """CurationScorer should:
        1. Accept candidates and configuration (weights, n)
        2. Score all candidates
        3. Select top-N with diversity
        4. Return a structured result with metadata

        Weights from spec: temporal=0.3, enrichment=0.3, diversity=0.2, subject=0.2
        """
        candidates = [
            _make_candidate("rec_a", date_start=1460, place_norm="mainz", subjects=["Bible"]),
            _make_candidate("rec_b", date_start=1550, place_norm="venice", subjects=["Philosophy", "Art"]),
            _make_candidate("rec_c", date_start=1650, place_norm="amsterdam", subjects=["Science"]),
            _make_candidate("rec_d", date_start=1520, place_norm="paris", subjects=["Theology"]),
            _make_candidate("rec_e", date_start=1700, place_norm="london"),
        ]

        scorer = CurationScorer(
            weights={
                "temporal": 0.3,
                "enrichment": 0.3,
                "diversity": 0.2,
                "subject_richness": 0.2,
            }
        )

        result = scorer.curate(candidates, n=3)

        # Result should have structured metadata
        assert "selected" in result
        assert "total_scored" in result
        assert result["total_scored"] == 5
        assert len(result["selected"]) == 3

        # Each selected item should have score and record_id
        for item in result["selected"]:
            assert "record_id" in item
            assert "score" in item
            assert isinstance(item["score"], float)
            assert 0.0 <= item["score"] <= 1.0

        # Dimension coverage should be tracked
        assert "dimension_coverage" in result
        assert isinstance(result["dimension_coverage"], dict)
