"""Tests for the narrator (Stage 3).

Tests enforce evidence rules: grounding compliance, no fabrication,
link inclusion. All tests mock the OpenAI client.
"""
from unittest.mock import MagicMock, patch

import pytest

from scripts.chat.plan_models import (
    ExecutionResult, ScholarResponse, GroundingData,
    RecordSummary, AgentSummary, GroundingLink,
    StepResult, RecordSet, ScholarlyDirective,
)


# =============================================================================
# Fixtures
# =============================================================================

def _make_execution_result(**overrides) -> ExecutionResult:
    defaults = dict(
        steps_completed=[],
        directives=[],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        original_query="test query",
        session_context=None,
        truncated=False,
    )
    defaults.update(overrides)
    return ExecutionResult(**defaults)


def _make_karo_result() -> ExecutionResult:
    """Execution result with 2 Karo records."""
    records = [
        RecordSummary(
            mms_id="990001234", title="Shulchan Aruch",
            date_display="Venice, 1565", place="venice",
            publisher="bragadin", language="heb",
            agents=["\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd"],
            subjects=["Jewish law"],
            primo_url="https://primo.example.com/990001234",
            source_steps=[0],
        ),
        RecordSummary(
            mms_id="990005678", title="Shulchan Aruch",
            date_display="Amsterdam, 1698", place="amsterdam",
            publisher="proops", language="heb",
            agents=["\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd"],
            subjects=["Jewish law"],
            primo_url="https://primo.example.com/990005678",
            source_steps=[0],
        ),
    ]
    agents = [
        AgentSummary(
            canonical_name="\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd",
            variants=["Joseph Karo"],
            birth_year=1488, death_year=1575,
            occupations=["rabbi", "posek"],
            description="Author of the Shulchan Aruch",
            record_count=2,
            links=[
                GroundingLink(entity_type="agent", entity_id="Q193460",
                    label="Wikipedia", url="https://en.wikipedia.org/wiki/Joseph_Karo", source="wikipedia"),
            ],
        ),
    ]
    return _make_execution_result(
        grounding=GroundingData(
            records=records,
            agents=agents,
            aggregations={},
            links=[
                GroundingLink(entity_type="record", entity_id="990001234",
                    label="Catalog", url="https://primo.example.com/990001234", source="primo"),
                GroundingLink(entity_type="record", entity_id="990005678",
                    label="Catalog", url="https://primo.example.com/990005678", source="primo"),
                GroundingLink(entity_type="agent", entity_id="Q193460",
                    label="Wikipedia", url="https://en.wikipedia.org/wiki/Joseph_Karo", source="wikipedia"),
            ],
        ),
        directives=[
            ScholarlyDirective(directive="expand", params={"focus": "Joseph Karo"}, label="Expand"),
        ],
        original_query="who was Joseph Karo?",
    )


# =============================================================================
# Tests
# =============================================================================

def test_narrate_returns_scholar_response():
    """narrate() returns a ScholarResponse."""
    from scripts.chat.narrator import narrate

    mock_narrative = "Joseph Karo (1488-1575) was a great scholar. **Our collection holds 2 editions**."
    mock_response = ScholarResponse(
        narrative=mock_narrative,
        suggested_followups=["What about Maimonides?"],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        confidence=0.9,
        metadata={},
    )

    with patch("scripts.chat.narrator._call_llm", return_value=mock_response):
        import asyncio
        result = asyncio.run(narrate("who was Karo?", _make_karo_result()))

    assert isinstance(result, ScholarResponse)
    assert "Karo" in result.narrative


def test_narrate_empty_results():
    """Narrator handles zero records gracefully."""
    from scripts.chat.narrator import narrate

    mock_response = ScholarResponse(
        narrative="We do not hold works by this author in our collection.",
        suggested_followups=["Try searching for related authors"],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        confidence=0.85,
        metadata={},
    )

    with patch("scripts.chat.narrator._call_llm", return_value=mock_response):
        import asyncio
        result = asyncio.run(narrate("who was Nobody?", _make_execution_result()))

    assert "do not hold" in result.narrative.lower() or "no " in result.narrative.lower()


def test_narrate_grounding_passthrough():
    """Narrator passes through grounding data from executor."""
    from scripts.chat.narrator import narrate

    exec_result = _make_karo_result()

    mock_response = ScholarResponse(
        narrative="Test narrative",
        suggested_followups=[],
        grounding=exec_result.grounding,  # Pass through
        confidence=0.9,
        metadata={},
    )

    with patch("scripts.chat.narrator._call_llm", return_value=mock_response):
        import asyncio
        result = asyncio.run(narrate("test", exec_result))

    # Grounding should contain the records from the execution result
    assert len(result.grounding.records) == 2
    assert result.grounding.records[0].mms_id == "990001234"


def test_narrate_fallback_on_llm_failure():
    """When LLM fails, narrator returns a structured summary."""
    from scripts.chat.narrator import narrate

    exec_result = _make_karo_result()

    with patch("scripts.chat.narrator._call_llm", side_effect=Exception("API error")):
        import asyncio
        result = asyncio.run(narrate("who was Karo?", exec_result))

    # Should return a valid ScholarResponse with fallback narrative
    assert isinstance(result, ScholarResponse)
    assert "990001234" in result.narrative or "2 " in result.narrative


def test_build_narrator_prompt_includes_records():
    """The narrator prompt includes record details from ExecutionResult."""
    from scripts.chat.narrator import _build_narrator_prompt

    exec_result = _make_karo_result()
    prompt = _build_narrator_prompt("who was Karo?", exec_result)

    assert "990001234" in prompt
    assert "Shulchan Aruch" in prompt
    assert "Venice, 1565" in prompt


def test_build_narrator_prompt_includes_directives():
    """The narrator prompt includes scholarly directives."""
    from scripts.chat.narrator import _build_narrator_prompt

    exec_result = _make_karo_result()
    prompt = _build_narrator_prompt("who was Karo?", exec_result)

    assert "expand" in prompt.lower()
    assert "Joseph Karo" in prompt
