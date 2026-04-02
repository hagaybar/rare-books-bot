import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.eval.judge import (
    InterpreterScore,
    NarratorScore,
    score_interpreter,
    score_narrator,
    _compute_filter_overlap,
)
from scripts.eval.query_set import EvalQuery


def test_compute_filter_overlap_exact_match():
    """Perfect filter overlap scores 1.0."""
    expected = {"publisher": "daniel bomberg", "place": "venice"}
    actual = {"publisher": "daniel bomberg", "imprint_place": "venice"}
    # Map field names: imprint_place -> place for comparison
    score = _compute_filter_overlap(expected, actual)
    assert score == 1.0


def test_compute_filter_overlap_partial():
    """Partial overlap scores proportionally."""
    expected = {"publisher": "daniel bomberg", "place": "venice"}
    actual = {"publisher": "daniel bomberg"}
    score = _compute_filter_overlap(expected, actual)
    assert 0.4 <= score <= 0.6  # ~50% overlap


def test_compute_filter_overlap_empty():
    """Empty expected filters scores 1.0 (nothing to match)."""
    score = _compute_filter_overlap({}, {"publisher": "anything"})
    assert score == 1.0


@pytest.mark.asyncio
async def test_score_interpreter_deterministic_checks():
    """Deterministic checks: intent match + filter overlap."""
    query = EvalQuery(
        id="q01", query="test", intent="retrieval", difficulty="simple",
        expected_filters={"publisher": "bomberg"},
    )
    # Simulated interpreter output
    plan_dict = {
        "intents": ["retrieval"],
        "execution_steps": [{"action": "retrieve", "params": {}, "label": "get"}],
        "filters_produced": {"publisher": "bomberg"},
    }

    with patch("scripts.eval.judge.structured_completion") as mock_llm:
        mock_result = MagicMock()
        mock_result.parsed = MagicMock(
            step_quality=4, justification="Good steps"
        )
        mock_llm.return_value = mock_result

        score = await score_interpreter(query, plan_dict, judge_model="gpt-4.1")

    assert isinstance(score, InterpreterScore)
    assert score.intent_match is True
    assert score.filter_overlap == 1.0
    assert score.step_quality == 4
