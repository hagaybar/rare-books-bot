# Model Evaluation & Cost Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build infrastructure to choose LLM models per pipeline stage and compare quality/cost/latency, using LiteLLM as the provider abstraction.

**Architecture:** LiteLLM replaces direct OpenAI client calls. A JSON config maps pipeline stages to models. A batch evaluation CLI scores models via LLM-as-judge. A frontend compare mode shows side-by-side results.

**Tech Stack:** Python 3.12, LiteLLM, FastAPI, React/TypeScript, SQLite

**Spec:** `docs/superpowers/specs/2026-04-03-model-evaluation-design.md`

**Branch:** `feature/model-evaluation`

---

## File Map

### New Files
| File | Purpose |
|------|---------|
| `scripts/models/__init__.py` | Package init |
| `scripts/models/config.py` | Stage → model config loader |
| `scripts/models/llm_client.py` | Thin litellm wrapper with structured output + logging |
| `scripts/eval/__init__.py` | Package init |
| `scripts/eval/query_set.py` | Load/validate curated test queries |
| `scripts/eval/judge.py` | LLM-as-judge scoring for interpreter + narrator |
| `scripts/eval/report.py` | Generate comparison report + summary.md |
| `scripts/eval/run_eval.py` | Batch evaluation CLI entry point |
| `data/eval/model-config.json` | Active model configuration |
| `data/eval/queries.json` | Curated benchmark query set |
| `app/api/compare.py` | POST /chat/compare endpoint |
| `frontend/src/components/CompareMode.tsx` | Side-by-side comparison UI |
| `frontend/src/components/ModelSelector.tsx` | Model picker checkboxes |
| `tests/test_models_config.py` | Tests for config module |
| `tests/test_llm_client.py` | Tests for LLM client wrapper |
| `tests/test_eval_judge.py` | Tests for judge scoring |
| `tests/test_eval_query_set.py` | Tests for query set loader |

### Modified Files
| File | What Changes |
|------|-------------|
| `pyproject.toml` | Update litellm pin to ≥1.81.9 |
| `scripts/chat/interpreter.py` | Replace OpenAI client with llm_client calls |
| `scripts/chat/narrator.py` | Replace OpenAI client with llm_client calls (sync, stream, meta) |
| `scripts/utils/llm_logger.py` | Replace PRICING_PER_1M_TOKENS with litellm.completion_cost() |
| `scripts/query/llm_compiler.py` | Replace OpenAI client with llm_client calls |
| `scripts/metadata/agent_harness.py` | Replace OpenAI client with llm_client calls |
| `app/api/main.py` | Wire compare endpoint, pass model config to pipeline |
| `app/api/models.py` | Add CompareRequest/CompareResponse models |
| `frontend/src/types/chat.ts` | Add CompareResponse type |
| `frontend/src/App.tsx` | Wire CompareMode toggle |

---

## Phase 1: Infrastructure

### Task 1: Update LiteLLM Dependency & Create Config Module

**Files:**
- Modify: `pyproject.toml`
- Create: `scripts/models/__init__.py`
- Create: `scripts/models/config.py`
- Create: `data/eval/model-config.json`
- Test: `tests/test_models_config.py`

- [ ] **Step 1: Write config test**

```python
# tests/test_models_config.py
import json
import tempfile
from pathlib import Path

import pytest

from scripts.models.config import ModelConfig, load_config, get_model


def test_load_config_from_file(tmp_path):
    """Config loads from JSON file."""
    config_file = tmp_path / "model-config.json"
    config_file.write_text(json.dumps({
        "interpreter": {"model": "gpt-4.1-mini"},
        "narrator": {"model": "gpt-5-mini"},
        "meta_extraction": {"model": "gpt-4.1-nano"},
        "judge": {"model": "gpt-4.1"},
    }))
    cfg = load_config(config_file)
    assert cfg.interpreter.model == "gpt-4.1-mini"
    assert cfg.narrator.model == "gpt-5-mini"
    assert cfg.meta_extraction.model == "gpt-4.1-nano"
    assert cfg.judge.model == "gpt-4.1"


def test_load_config_defaults_when_missing():
    """Config returns defaults when file doesn't exist."""
    cfg = load_config(Path("/nonexistent/config.json"))
    assert cfg.interpreter.model == "gpt-4.1"
    assert cfg.narrator.model == "gpt-4.1"
    assert cfg.meta_extraction.model == "gpt-4.1-nano"
    assert cfg.judge.model == "gpt-4.1"


def test_get_model_returns_stage_model(tmp_path):
    """get_model() returns the model string for a stage."""
    config_file = tmp_path / "model-config.json"
    config_file.write_text(json.dumps({
        "interpreter": {"model": "gpt-5-mini"},
        "narrator": {"model": "gpt-4.1"},
        "meta_extraction": {"model": "gpt-4.1-nano"},
        "judge": {"model": "gpt-4.1"},
    }))
    cfg = load_config(config_file)
    assert get_model(cfg, "interpreter") == "gpt-5-mini"
    assert get_model(cfg, "narrator") == "gpt-4.1"


def test_get_model_unknown_stage_raises():
    """get_model() raises for unknown stage."""
    cfg = load_config(Path("/nonexistent"))
    with pytest.raises(KeyError):
        get_model(cfg, "nonexistent_stage")
```

- [ ] **Step 2: Run test — verify it fails**

Run: `pytest tests/test_models_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.models'`

- [ ] **Step 3: Create config module**

```python
# scripts/models/__init__.py
"""Model configuration and LLM client abstractions."""
```

```python
# scripts/models/config.py
"""Stage-to-model configuration.

Loads model assignments from a JSON config file. Falls back to defaults
if the file is missing. Each pipeline stage (interpreter, narrator, etc.)
maps to a model string compatible with litellm (e.g., "gpt-4.1",
"anthropic/claude-sonnet-4-6", "ollama/llama3").
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("data/eval/model-config.json")


@dataclass
class StageConfig:
    """Configuration for a single pipeline stage."""
    model: str


@dataclass
class ModelConfig:
    """Full model configuration across all pipeline stages."""
    interpreter: StageConfig = field(default_factory=lambda: StageConfig(model="gpt-4.1"))
    narrator: StageConfig = field(default_factory=lambda: StageConfig(model="gpt-4.1"))
    meta_extraction: StageConfig = field(default_factory=lambda: StageConfig(model="gpt-4.1-nano"))
    judge: StageConfig = field(default_factory=lambda: StageConfig(model="gpt-4.1"))


def load_config(path: Optional[Path] = None) -> ModelConfig:
    """Load model config from JSON file, falling back to defaults."""
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        logger.info("Model config not found at %s — using defaults", config_path)
        return ModelConfig()

    try:
        raw = json.loads(config_path.read_text())
        return ModelConfig(
            interpreter=StageConfig(model=raw.get("interpreter", {}).get("model", "gpt-4.1")),
            narrator=StageConfig(model=raw.get("narrator", {}).get("model", "gpt-4.1")),
            meta_extraction=StageConfig(model=raw.get("meta_extraction", {}).get("model", "gpt-4.1-nano")),
            judge=StageConfig(model=raw.get("judge", {}).get("model", "gpt-4.1")),
        )
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to parse model config at %s: %s — using defaults", config_path, e)
        return ModelConfig()


def get_model(config: ModelConfig, stage: str) -> str:
    """Get the model string for a pipeline stage.

    Raises KeyError if stage is not a known field of ModelConfig.
    """
    stage_config: StageConfig = getattr(config, stage)
    return stage_config.model
```

- [ ] **Step 4: Create default config file**

```json
// data/eval/model-config.json
{
  "interpreter": {"model": "gpt-4.1"},
  "narrator": {"model": "gpt-4.1"},
  "meta_extraction": {"model": "gpt-4.1-nano"},
  "judge": {"model": "gpt-4.1"}
}
```

- [ ] **Step 5: Update litellm pin in pyproject.toml**

Change line in `pyproject.toml`:
```
"litellm>=1.73.0,<2.0.0",
```
to:
```
"litellm>=1.81.9,<2.0.0",
```

- [ ] **Step 6: Run tests — verify they pass**

Run: `pytest tests/test_models_config.py -v`
Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add scripts/models/ tests/test_models_config.py data/eval/model-config.json pyproject.toml
git commit -m "feat: add model config module and update litellm pin"
```

---

### Task 2: Build LLM Client Wrapper

**Files:**
- Create: `scripts/models/llm_client.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: Write LLM client test**

```python
# tests/test_llm_client.py
"""Tests for the LLM client wrapper.

These test the wrapper logic (schema conversion, response parsing)
without making actual API calls — litellm.acompletion is mocked.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from scripts.models.llm_client import (
    LLMResult,
    structured_completion,
    streaming_completion,
    pydantic_to_response_format,
)


class SampleSchema(BaseModel):
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)


def test_pydantic_to_response_format():
    """Converts Pydantic model to JSON schema dict for response_format."""
    fmt = pydantic_to_response_format(SampleSchema)
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "SampleSchema"
    assert "properties" in fmt["json_schema"]["schema"]
    assert "answer" in fmt["json_schema"]["schema"]["properties"]


@pytest.mark.asyncio
async def test_structured_completion_parses_response():
    """structured_completion() calls litellm and parses the Pydantic model."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"answer": "hello", "confidence": 0.9})

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.model = "gpt-4.1"

    with patch("scripts.models.llm_client.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)
        mock_litellm.completion_cost.return_value = 0.001

        result = await structured_completion(
            model="gpt-4.1",
            system="You are helpful.",
            user="Say hello.",
            response_schema=SampleSchema,
        )

    assert isinstance(result, LLMResult)
    assert isinstance(result.parsed, SampleSchema)
    assert result.parsed.answer == "hello"
    assert result.parsed.confidence == 0.9
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.cost_usd == 0.001


@pytest.mark.asyncio
async def test_structured_completion_passes_model_to_litellm():
    """The model string is passed through to litellm.acompletion()."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"answer": "hi", "confidence": 0.5})

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5
    mock_response.model = "anthropic/claude-sonnet-4-6"

    with patch("scripts.models.llm_client.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)
        mock_litellm.completion_cost.return_value = 0.002

        await structured_completion(
            model="anthropic/claude-sonnet-4-6",
            system="sys",
            user="usr",
            response_schema=SampleSchema,
        )

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-sonnet-4-6"
```

- [ ] **Step 2: Run test — verify it fails**

Run: `pytest tests/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.models.llm_client'`

- [ ] **Step 3: Implement LLM client wrapper**

```python
# scripts/models/llm_client.py
"""Thin async wrapper around litellm for structured and streaming completions.

Replaces direct OpenAI client calls throughout the codebase. All LLM calls
go through this module, making model switching a config change.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, Type, TypeVar

import litellm
from pydantic import BaseModel

from scripts.utils.llm_logger import log_llm_call

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult:
    """Result from a structured LLM completion."""
    parsed: Any  # The parsed Pydantic model instance
    raw_content: str  # Raw JSON string from the LLM
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    response: Any  # The raw litellm response object


def pydantic_to_response_format(schema: Type[BaseModel]) -> dict:
    """Convert a Pydantic model to a JSON schema dict for litellm response_format.

    This explicit conversion is more reliable across providers than passing
    the Pydantic class directly.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "schema": schema.model_json_schema(),
            "name": schema.__name__,
            "strict": True,
        },
    }


async def structured_completion(
    model: str,
    system: str,
    user: str,
    response_schema: Type[T],
    call_type: str = "unknown",
    extra_metadata: Optional[dict] = None,
) -> LLMResult:
    """Run a structured completion via litellm, returning a parsed Pydantic model.

    Args:
        model: LiteLLM model string (e.g., "gpt-4.1", "anthropic/claude-sonnet-4-6")
        system: System prompt
        user: User prompt
        response_schema: Pydantic model class for structured output
        call_type: Label for logging (e.g., "scholar_interpreter", "narrator")
        extra_metadata: Additional metadata for the log entry

    Returns:
        LLMResult with the parsed model, token usage, cost, and latency.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    start = time.monotonic()
    resp = await litellm.acompletion(
        model=model,
        messages=messages,
        response_format=pydantic_to_response_format(response_schema),
    )
    latency_ms = (time.monotonic() - start) * 1000

    raw_content = resp.choices[0].message.content
    parsed = response_schema.model_validate_json(raw_content)

    input_tokens = resp.usage.prompt_tokens
    output_tokens = resp.usage.completion_tokens
    try:
        cost = litellm.completion_cost(completion_response=resp)
    except Exception:
        cost = 0.0
        logger.debug("litellm.completion_cost() failed for model %s", model)

    log_llm_call(
        call_type=call_type,
        model=model,
        system_prompt=system,
        user_prompt=user,
        response=resp,
        extra_metadata=extra_metadata,
    )

    return LLMResult(
        parsed=parsed,
        raw_content=raw_content,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        latency_ms=latency_ms,
        response=resp,
    )


async def streaming_completion(
    model: str,
    system: str,
    user: str,
    call_type: str = "unknown",
    extra_metadata: Optional[dict] = None,
) -> AsyncIterator[str]:
    """Stream a plain-text completion via litellm.

    Yields text chunks as they arrive. Does not support structured output
    (streaming and structured parsing are incompatible).

    Usage:
        async for chunk in streaming_completion(model, system, user):
            await send_to_client(chunk)
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        stream=True,
    )

    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `pytest tests/test_llm_client.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/models/llm_client.py tests/test_llm_client.py
git commit -m "feat: add LLM client wrapper around litellm"
```

---

## Phase 2: Migration

### Task 3: Migrate Interpreter to LiteLLM

**Files:**
- Modify: `scripts/chat/interpreter.py`

- [ ] **Step 1: Update imports**

In `scripts/chat/interpreter.py`, replace:
```python
from openai import OpenAI
```
with:
```python
from scripts.models.llm_client import structured_completion
from scripts.models.config import load_config, get_model
```

- [ ] **Step 2: Rewrite `_call_llm()` function**

Replace the entire `_call_llm()` function (lines ~376-425) with:

```python
async def _call_llm(
    query: str,
    session_context: Optional[SessionContext],
    model: str,
    api_key: Optional[str],
) -> InterpretationPlan:
    """Call LLM via litellm and convert to typed InterpretationPlan."""
    user_prompt = _build_user_prompt(query, session_context)

    result = await structured_completion(
        model=model,
        system=INTERPRETER_SYSTEM_PROMPT,
        user=user_prompt,
        response_schema=InterpretationPlanLLM,
        call_type="scholar_interpreter",
        extra_metadata={"query_text": query},
    )

    llm_plan: InterpretationPlanLLM = result.parsed
    return _convert_llm_plan(llm_plan)
```

- [ ] **Step 3: Update `interpret()` to use config**

Replace the `interpret()` function signature (lines ~859-886) with:

```python
async def interpret(
    query: str,
    session_context: Optional[SessionContext] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> InterpretationPlan:
    """Interpret a user query into an execution plan.

    Args:
        query: Natural language query
        session_context: Optional session context for follow-up queries
        model: LLM model string (defaults to config value)
        api_key: Optional API key override
    """
    if model is None:
        config = load_config()
        model = get_model(config, "interpreter")

    plan = await _call_llm(query, session_context, model, api_key)
    _validate_step_refs(plan)
    return plan
```

- [ ] **Step 4: Remove unused `from openai import OpenAI` import and `os` import if no longer used**

Check if `os` is still used elsewhere in the file (likely yes for `os.getenv` in other places). Only remove the `openai` import.

- [ ] **Step 5: Run existing tests to verify no regression**

Run: `pytest tests/ -k "interpret" -v --timeout=30`
Expected: Existing interpreter tests still pass (they should mock LLM calls)

- [ ] **Step 6: Commit**

```bash
git add scripts/chat/interpreter.py
git commit -m "refactor: migrate interpreter from OpenAI Responses API to litellm"
```

---

### Task 4: Migrate Narrator to LiteLLM

**Files:**
- Modify: `scripts/chat/narrator.py`

- [ ] **Step 1: Update imports**

In `scripts/chat/narrator.py`, replace:
```python
from openai import OpenAI
```
with:
```python
from scripts.models.llm_client import structured_completion, streaming_completion
from scripts.models.config import load_config, get_model
```

- [ ] **Step 2: Rewrite `_call_llm()` (sync narration)**

Replace the `_call_llm()` function (lines ~262-305) with:

```python
async def _call_llm(
    query: str,
    execution_result: ExecutionResult,
    model: str = "gpt-4.1",
    api_key: Optional[str] = None,
    token_saving: bool = True,
) -> ScholarResponse:
    """Call LLM via litellm with the narrator persona and verified data."""
    if token_saving:
        user_prompt = build_lean_narrator_prompt(query, execution_result)
    else:
        user_prompt = _build_narrator_prompt(query, execution_result)

    result = await structured_completion(
        model=model,
        system=NARRATOR_SYSTEM_PROMPT,
        user=user_prompt,
        response_schema=NarratorResponseLLM,
        call_type="narrator",
        extra_metadata={
            "query_text": query,
            "token_saving": token_saving,
        },
    )

    llm_resp: NarratorResponseLLM = result.parsed
    return ScholarResponse(
        narrative=llm_resp.narrative,
        suggested_followups=llm_resp.suggested_followups,
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        confidence=llm_resp.confidence,
        metadata={"model": model},
    )
```

- [ ] **Step 3: Rewrite `_stream_llm()` (streaming narration)**

Replace the `_stream_llm()` function (lines ~338-433) with:

```python
async def _stream_llm(
    query: str,
    execution_result: ExecutionResult,
    chunk_callback: Callable[[str], Awaitable[None]],
    model: str = "gpt-4.1",
    api_key: Optional[str] = None,
    token_saving: bool = True,
) -> str:
    """Stream the narrator LLM response via litellm, forwarding text chunks."""
    if token_saving:
        user_prompt = build_lean_narrator_prompt(query, execution_result)
    else:
        user_prompt = _build_narrator_prompt(query, execution_result)

    streaming_system = (
        NARRATOR_SYSTEM_PROMPT
        + "\n\nRespond with ONLY the scholarly narrative in markdown. "
        "Do not wrap in JSON or add metadata fields."
    )

    full_text: list[str] = []
    async for chunk in streaming_completion(
        model=model,
        system=streaming_system,
        user=user_prompt,
        call_type="narrator_streaming",
        extra_metadata={"query_text": query, "token_saving": token_saving},
    ):
        full_text.append(chunk)
        await chunk_callback(chunk)

    return "".join(full_text)
```

- [ ] **Step 4: Rewrite `_extract_streaming_meta()` (post-streaming metadata)**

Replace the `_extract_streaming_meta()` function (lines ~218-254) with:

```python
async def _extract_streaming_meta(
    query: str,
    narrative: str,
    api_key: Optional[str] = None,
) -> tuple[list[str], float]:
    """Extract followups and confidence after streaming completes."""
    try:
        config = load_config()
        meta_model = get_model(config, "meta_extraction")

        result = await structured_completion(
            model=meta_model,
            system=(
                "Given a user query and the scholarly response that was generated, "
                "suggest 2-4 follow-up questions the user might ask next, and "
                "rate the response quality from 0.0 to 1.0."
            ),
            user=f"Query: {query}\n\nResponse (first 500 chars): {narrative[:500]}",
            response_schema=StreamingMetaLLM,
            call_type="narrator_meta",
        )
        meta: StreamingMetaLLM = result.parsed
        return meta.suggested_followups, meta.confidence
    except Exception:
        logger.debug("Post-streaming meta extraction failed; using defaults")
        return [], 0.85
```

Note: This function was previously synchronous. It now becomes `async` — check all callers and add `await` where needed. The caller in `narrate_streaming()` already uses `await` or should be updated to do so.

- [ ] **Step 5: Update `narrate()` to use config for default model**

In the `narrate()` function (lines ~124-161), change the signature:

```python
async def narrate(
    query: str,
    execution_result: ExecutionResult,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    token_saving: bool = True,
) -> ScholarResponse:
```

And at the top of the function body, add:
```python
    if model is None:
        config = load_config()
        model = get_model(config, "narrator")
```

- [ ] **Step 6: Update `narrate_streaming()` similarly**

Apply the same config-based default model pattern to `narrate_streaming()`.

- [ ] **Step 7: Run existing narrator tests**

Run: `pytest tests/ -k "narrat" -v --timeout=30`
Expected: Existing narrator tests still pass

- [ ] **Step 8: Commit**

```bash
git add scripts/chat/narrator.py
git commit -m "refactor: migrate narrator from OpenAI Responses API to litellm"
```

---

### Task 5: Migrate Cost Tracking in llm_logger.py

**Files:**
- Modify: `scripts/utils/llm_logger.py`

- [ ] **Step 1: Replace PRICING_PER_1M_TOKENS with litellm.completion_cost()**

In `scripts/utils/llm_logger.py`, update the `_calculate_cost` method (lines ~92-108):

```python
def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int,
                    response: Any = None) -> float:
    """Calculate estimated cost in USD using litellm's pricing data.

    Falls back to zero if litellm doesn't have pricing for the model.
    """
    if response is not None:
        try:
            import litellm
            return round(litellm.completion_cost(completion_response=response), 6)
        except Exception:
            pass

    # Fallback: try litellm's per-token cost
    try:
        import litellm
        input_cost, output_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        return round(input_cost + output_cost, 6)
    except Exception:
        return 0.0
```

- [ ] **Step 2: Keep PRICING_PER_1M_TOKENS as a comment block for reference, but mark as deprecated**

```python
# DEPRECATED: Previously used for manual cost calculation.
# Now using litellm.completion_cost() which maintains its own pricing database.
# Kept as reference for models litellm may not yet support.
# PRICING_PER_1M_TOKENS = {
#     "gpt-4.1": {"input": 2.00, "output": 8.00},
#     ...
# }
```

- [ ] **Step 3: Update `log_llm_call()` to pass response object to `_calculate_cost()`**

Find where `_calculate_cost` is called and pass the response object through for more accurate pricing:

```python
cost = self._calculate_cost(model, input_tokens, output_tokens, response=response)
```

- [ ] **Step 4: Run existing logger tests**

Run: `pytest tests/ -k "logger" -v --timeout=30`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/utils/llm_logger.py
git commit -m "refactor: replace manual pricing table with litellm.completion_cost()"
```

---

### Task 6: Migrate Legacy Compiler & Agent Harness

**Files:**
- Modify: `scripts/query/llm_compiler.py`
- Modify: `scripts/metadata/agent_harness.py`

- [ ] **Step 1: Migrate llm_compiler.py**

In `scripts/query/llm_compiler.py`, update `call_model()` (lines ~217-260):

Replace `from openai import OpenAI` with:
```python
from scripts.models.llm_client import structured_completion
```

Rewrite `call_model()`:
```python
async def call_model(model: str, query_text: str) -> QueryPlan:
    """Call LLM via litellm with structured output."""
    user_prompt = build_user_prompt(query_text)

    result = await structured_completion(
        model=model,
        system=SYSTEM_PROMPT,
        user=user_prompt,
        response_schema=QueryPlanLLM,
        call_type="query_compilation",
        extra_metadata={"query_text": query_text},
    )

    llm_plan = result.parsed
    return QueryPlan(
        version=llm_plan.version,
        query_text=llm_plan.query_text,
        filters=llm_plan.filters,
        soft_filters=llm_plan.soft_filters,
        limit=llm_plan.limit,
        debug={},
    )
```

Note: This changes `call_model` from sync to async. Update any callers to use `await`. Check `compile_query()` which calls it.

- [ ] **Step 2: Migrate agent_harness.py**

In `scripts/metadata/agent_harness.py`, replace the lazy `_get_client()` pattern (lines ~329-360):

Replace lazy OpenAI client init with litellm calls. The harness class should store the model string and call `structured_completion()` instead of `self.client.responses.parse()`. Since agent_harness has multiple LLM call sites, update each one to use `structured_completion()`.

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v --timeout=60`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/query/llm_compiler.py scripts/metadata/agent_harness.py
git commit -m "refactor: migrate legacy compiler and agent harness to litellm"
```

---

## Phase 3: Batch Evaluation Framework

### Task 7: Build Query Set Module

**Files:**
- Create: `scripts/eval/__init__.py`
- Create: `scripts/eval/query_set.py`
- Create: `data/eval/queries.json`
- Test: `tests/test_eval_query_set.py`

- [ ] **Step 1: Write query set test**

```python
# tests/test_eval_query_set.py
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
```

- [ ] **Step 2: Run test — verify it fails**

Run: `pytest tests/test_eval_query_set.py -v`
Expected: FAIL

- [ ] **Step 3: Implement query set module**

```python
# scripts/eval/__init__.py
"""Evaluation framework for model comparison."""
```

```python
# scripts/eval/query_set.py
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
```

- [ ] **Step 4: Create initial curated query set**

Create `data/eval/queries.json` with 20+ queries covering all intent types and difficulty levels. Research the actual data in bibliographic.db to craft realistic queries. Include queries involving:
- Known publishers (Bomberg, Plantin, Aldine)
- Known agents (Elijah Levita, Maimonides)
- Date ranges (15th-16th century Venice)
- Languages (Hebrew, Latin, French)
- Subject searches
- Network/connection queries
- Analytical queries (distribution by place/century)
- Comparison queries
- Follow-up queries

- [ ] **Step 5: Run tests — verify they pass**

Run: `pytest tests/test_eval_query_set.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/eval/ tests/test_eval_query_set.py data/eval/queries.json
git commit -m "feat: add evaluation query set module with curated benchmarks"
```

---

### Task 8: Build LLM-as-Judge Module

**Files:**
- Create: `scripts/eval/judge.py`
- Test: `tests/test_eval_judge.py`

- [ ] **Step 1: Write judge test**

```python
# tests/test_eval_judge.py
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
    # Map field names: imprint_place → place for comparison
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
```

- [ ] **Step 2: Run test — verify it fails**

Run: `pytest tests/test_eval_judge.py -v`
Expected: FAIL

- [ ] **Step 3: Implement judge module**

```python
# scripts/eval/judge.py
"""LLM-as-judge scoring for interpreter and narrator outputs.

Combines deterministic checks (intent match, filter overlap) with
LLM-based quality assessment (step quality, narrative criteria).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from scripts.eval.query_set import EvalQuery
from scripts.models.llm_client import structured_completion

logger = logging.getLogger(__name__)


# -- Judge schemas (what the LLM returns) --

class InterpreterJudgment(BaseModel):
    """LLM judge output for interpreter step quality."""
    step_quality: int = Field(ge=1, le=5, description="Quality of execution steps (1-5)")
    justification: str = Field(description="Brief justification for the score")


class NarratorJudgment(BaseModel):
    """LLM judge output for narrator quality."""
    accuracy: int = Field(ge=1, le=5, description="Does narrative reflect grounding data?")
    completeness: int = Field(ge=1, le=5, description="Are all relevant records/agents mentioned?")
    scholarly_tone: int = Field(ge=1, le=5, description="Appropriate for bibliographic discovery?")
    conciseness: int = Field(ge=1, le=5, description="No filler or hallucination?")
    justification: str = Field(description="Brief justification")


# -- Score dataclasses --

@dataclass
class InterpreterScore:
    """Combined score for an interpreter output."""
    intent_match: bool
    filter_overlap: float  # 0.0 - 1.0
    step_quality: int  # 1-5 from LLM judge
    justification: str

    @property
    def combined(self) -> float:
        """Weighted combined score (0.0 - 5.0 scale)."""
        intent_score = 5.0 if self.intent_match else 1.0
        filter_score = self.filter_overlap * 5.0
        return (intent_score * 0.3 + filter_score * 0.3 + self.step_quality * 0.4)


@dataclass
class NarratorScore:
    """Combined score for a narrator output."""
    accuracy: int
    completeness: int
    scholarly_tone: int
    conciseness: int
    justification: str

    @property
    def combined(self) -> float:
        """Average of all criteria (1.0 - 5.0 scale)."""
        return (self.accuracy + self.completeness + self.scholarly_tone + self.conciseness) / 4.0


# -- Filter overlap computation --

# Map expected_filters keys to actual filter field names
_FILTER_KEY_MAP = {
    "place": {"place", "imprint_place"},
    "publisher": {"publisher"},
    "agent": {"agent", "agent_norm"},
    "year": {"year"},
    "language": {"language"},
    "subject": {"subject"},
    "title": {"title"},
}


def _compute_filter_overlap(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> float:
    """Compute overlap between expected and actual filters.

    Returns 1.0 if all expected filters have a matching key (with mapped names)
    and matching value in actual. Returns proportional score for partial matches.
    Returns 1.0 if expected is empty (nothing to match).
    """
    if not expected:
        return 1.0

    matches = 0
    for key, expected_val in expected.items():
        # Get all possible field names for this key
        possible_keys = _FILTER_KEY_MAP.get(key, {key})
        matched = False
        for possible_key in possible_keys:
            if possible_key in actual:
                actual_val = actual[possible_key]
                if str(expected_val).lower() in str(actual_val).lower():
                    matched = True
                    break
        if matched:
            matches += 1

    return matches / len(expected)


# -- Scoring functions --

INTERPRETER_JUDGE_PROMPT = """You are evaluating the quality of a bibliographic query interpretation.

Given a user's query and the execution plan produced by the interpreter, rate the quality of the execution steps on a 1-5 scale:

1 = Steps are completely wrong or irrelevant
2 = Steps address the query but with significant errors
3 = Steps are reasonable but miss important aspects
4 = Steps are good with minor improvements possible
5 = Steps are excellent and comprehensive

Respond with your rating and a brief justification."""


async def score_interpreter(
    query: EvalQuery,
    plan_dict: dict[str, Any],
    judge_model: str = "gpt-4.1",
) -> InterpreterScore:
    """Score an interpreter output using deterministic checks + LLM judge."""
    # Deterministic: intent match
    plan_intents = plan_dict.get("intents", [])
    intent_match = query.intent in plan_intents

    # Deterministic: filter overlap
    filters_produced = plan_dict.get("filters_produced", {})
    filter_overlap = _compute_filter_overlap(query.expected_filters, filters_produced)

    # LLM judge: step quality
    user_prompt = (
        f"Query: {query.query}\n"
        f"Expected intent: {query.intent}\n"
        f"Execution steps: {plan_dict.get('execution_steps', [])}\n"
    )
    result = await structured_completion(
        model=judge_model,
        system=INTERPRETER_JUDGE_PROMPT,
        user=user_prompt,
        response_schema=InterpreterJudgment,
        call_type="eval_judge_interpreter",
    )
    judgment: InterpreterJudgment = result.parsed

    return InterpreterScore(
        intent_match=intent_match,
        filter_overlap=filter_overlap,
        step_quality=judgment.step_quality,
        justification=judgment.justification,
    )


NARRATOR_JUDGE_PROMPT = """You are evaluating the quality of a scholarly bibliographic narrative.

Given a user's query, the grounding data (records, agents), and the narrative produced, rate on a 1-5 scale:

- Accuracy: Does the narrative correctly reflect the grounding data?
- Completeness: Are all relevant records and agents mentioned?
- Scholarly tone: Is it appropriate for a bibliographic discovery tool?
- Conciseness: No filler, no hallucination, no unsupported claims?

Respond with ratings for each criterion and a brief justification."""


async def score_narrator(
    query: EvalQuery,
    narrative: str,
    grounding_summary: str,
    judge_model: str = "gpt-4.1",
) -> NarratorScore:
    """Score a narrator output using LLM judge."""
    user_prompt = (
        f"Query: {query.query}\n\n"
        f"Grounding data:\n{grounding_summary}\n\n"
        f"Narrative produced:\n{narrative}\n"
    )
    result = await structured_completion(
        model=judge_model,
        system=NARRATOR_JUDGE_PROMPT,
        user=user_prompt,
        response_schema=NarratorJudgment,
        call_type="eval_judge_narrator",
    )
    judgment: NarratorJudgment = result.parsed

    return NarratorScore(
        accuracy=judgment.accuracy,
        completeness=judgment.completeness,
        scholarly_tone=judgment.scholarly_tone,
        conciseness=judgment.conciseness,
        justification=judgment.justification,
    )
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `pytest tests/test_eval_judge.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/judge.py tests/test_eval_judge.py
git commit -m "feat: add LLM-as-judge scoring module for interpreter and narrator"
```

---

### Task 9: Build Report Generator & Batch Evaluation CLI

**Files:**
- Create: `scripts/eval/report.py`
- Create: `scripts/eval/run_eval.py`

- [ ] **Step 1: Implement report generator**

```python
# scripts/eval/report.py
"""Generate comparison reports from evaluation results."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def generate_report(
    results: list[dict[str, Any]],
    output_dir: Path,
) -> Path:
    """Generate evaluation report artifacts in output_dir.

    Creates:
      - results.json (raw results)
      - scores.json (aggregated scores per model × stage)
      - human_review.csv (template for human calibration)
      - summary.md (readable comparison table)

    Returns the output directory path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Raw results
    (output_dir / "results.json").write_text(
        json.dumps(results, indent=2, default=str)
    )

    # 2. Aggregated scores
    scores = _aggregate_scores(results)
    (output_dir / "scores.json").write_text(
        json.dumps(scores, indent=2, default=str)
    )

    # 3. Human review CSV
    _write_human_review_csv(results, output_dir / "human_review.csv")

    # 4. Summary markdown
    _write_summary_md(scores, output_dir / "summary.md")

    return output_dir


def _aggregate_scores(results: list[dict]) -> list[dict]:
    """Aggregate scores by model × stage."""
    buckets: dict[tuple[str, str], list[float]] = {}
    latencies: dict[tuple[str, str], list[float]] = {}
    costs: dict[tuple[str, str], list[float]] = {}
    tokens: dict[tuple[str, str], list[int]] = {}

    for r in results:
        key = (r["model"], r["stage"])
        buckets.setdefault(key, []).append(r.get("score_combined", 0))
        latencies.setdefault(key, []).append(r.get("latency_ms", 0))
        costs.setdefault(key, []).append(r.get("cost_usd", 0))
        tokens.setdefault(key, []).append(r.get("total_tokens", 0))

    aggregated = []
    for (model, stage), score_list in sorted(buckets.items()):
        n = len(score_list)
        aggregated.append({
            "model": model,
            "stage": stage,
            "avg_score": round(sum(score_list) / n, 2) if n else 0,
            "avg_latency_ms": round(sum(latencies[model, stage]) / n) if n else 0,
            "avg_cost_usd": round(sum(costs[model, stage]) / n, 4) if n else 0,
            "avg_tokens": round(sum(tokens[model, stage]) / n) if n else 0,
            "n_queries": n,
        })
    return aggregated


def _write_human_review_csv(results: list[dict], path: Path) -> None:
    """Write human review template CSV."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["query_id", "model", "stage", "auto_score", "human_score", "notes"])
        for r in results:
            writer.writerow([
                r.get("query_id", ""),
                r.get("model", ""),
                r.get("stage", ""),
                round(r.get("score_combined", 0), 2),
                "",  # Human fills this in
                "",  # Human fills this in
            ])


def _write_summary_md(scores: list[dict], path: Path) -> None:
    """Write readable summary markdown table."""
    lines = [
        f"# Evaluation Summary — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "| Model | Stage | Avg Score | Avg Latency | Avg Cost | Avg Tokens | N |",
        "|-------|-------|-----------|-------------|----------|------------|---|",
    ]
    for s in scores:
        lines.append(
            f"| {s['model']} | {s['stage']} | {s['avg_score']} "
            f"| {s['avg_latency_ms']}ms | ${s['avg_cost_usd']:.4f} "
            f"| {s['avg_tokens']} | {s['n_queries']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines))
```

- [ ] **Step 2: Implement batch evaluation CLI**

```python
# scripts/eval/run_eval.py
"""Batch evaluation CLI — run queries through multiple models and score results.

Usage:
    python3 scripts/eval/run_eval.py \
        --models gpt-4.1,gpt-4.1-mini,gpt-5-mini \
        --stages interpreter,narrator \
        --queries data/eval/queries.json \
        --judge-model gpt-4.1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.eval.query_set import load_query_set, validate_query_set, EvalQuery
from scripts.eval.judge import score_interpreter, score_narrator
from scripts.eval.report import generate_report
from scripts.models.llm_client import structured_completion
from scripts.models.config import load_config

logger = logging.getLogger(__name__)


async def evaluate_interpreter(
    query: EvalQuery,
    model: str,
    db_path: str,
) -> dict[str, Any]:
    """Run interpreter for a single query × model and return raw result."""
    from scripts.chat.interpreter import interpret

    start = time.monotonic()
    try:
        plan = await interpret(query.query, model=model)
        latency_ms = (time.monotonic() - start) * 1000

        # Extract filters from plan for scoring
        filters_produced = {}
        for step in plan.execution_steps:
            if hasattr(step.params, 'filters'):
                for f in step.params.filters:
                    filters_produced[f.field.value if hasattr(f.field, 'value') else str(f.field)] = f.value

        return {
            "query_id": query.id,
            "model": model,
            "stage": "interpreter",
            "success": True,
            "latency_ms": round(latency_ms),
            "plan": {
                "intents": plan.intents,
                "execution_steps": [
                    {"action": s.action.value if hasattr(s.action, 'value') else str(s.action),
                     "label": s.label}
                    for s in plan.execution_steps
                ],
                "filters_produced": filters_produced,
                "confidence": plan.confidence,
            },
        }
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "query_id": query.id,
            "model": model,
            "stage": "interpreter",
            "success": False,
            "latency_ms": round(latency_ms),
            "error": str(e),
        }


async def evaluate_narrator(
    query: EvalQuery,
    model: str,
    db_path: str,
) -> dict[str, Any]:
    """Run full pipeline (interpret + execute + narrate) for a query × narrator model."""
    from scripts.chat.interpreter import interpret
    from scripts.chat.executor import execute
    from scripts.chat.narrator import narrate

    start = time.monotonic()
    try:
        # Use default interpreter model, only vary narrator
        plan = await interpret(query.query)
        exec_result = await execute(plan, db_path=db_path)
        scholar_resp = await narrate(query.query, exec_result, model=model)
        latency_ms = (time.monotonic() - start) * 1000

        # Summarize grounding for judge
        grounding_summary = ""
        if exec_result.grounding:
            records = exec_result.grounding.records[:10]
            grounding_summary = "\n".join(
                f"- {r.title} ({r.date_display}, {r.place})" for r in records
            )

        return {
            "query_id": query.id,
            "model": model,
            "stage": "narrator",
            "success": True,
            "latency_ms": round(latency_ms),
            "narrative": scholar_resp.narrative,
            "grounding_summary": grounding_summary,
            "confidence": scholar_resp.confidence,
            "followups": scholar_resp.suggested_followups,
        }
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "query_id": query.id,
            "model": model,
            "stage": "narrator",
            "success": False,
            "latency_ms": round(latency_ms),
            "error": str(e),
        }


async def run_evaluation(
    queries: list[EvalQuery],
    models: list[str],
    stages: list[str],
    judge_model: str,
    db_path: str,
) -> list[dict[str, Any]]:
    """Run full evaluation: all queries × models × stages, then score."""
    results: list[dict[str, Any]] = []

    total = len(queries) * len(models) * len(stages)
    done = 0

    for query in queries:
        for model in models:
            for stage in stages:
                done += 1
                print(f"  [{done}/{total}] {query.id} × {model} × {stage}")

                if stage == "interpreter":
                    result = await evaluate_interpreter(query, model, db_path)
                elif stage == "narrator":
                    result = await evaluate_narrator(query, model, db_path)
                else:
                    continue

                # Score successful results
                if result.get("success"):
                    try:
                        if stage == "interpreter":
                            score = await score_interpreter(
                                query, result["plan"], judge_model=judge_model,
                            )
                            result["score_combined"] = score.combined
                            result["score_detail"] = {
                                "intent_match": score.intent_match,
                                "filter_overlap": score.filter_overlap,
                                "step_quality": score.step_quality,
                                "justification": score.justification,
                            }
                        elif stage == "narrator":
                            score = await score_narrator(
                                query,
                                result["narrative"],
                                result.get("grounding_summary", ""),
                                judge_model=judge_model,
                            )
                            result["score_combined"] = score.combined
                            result["score_detail"] = {
                                "accuracy": score.accuracy,
                                "completeness": score.completeness,
                                "scholarly_tone": score.scholarly_tone,
                                "conciseness": score.conciseness,
                                "justification": score.justification,
                            }
                    except Exception as e:
                        logger.warning("Scoring failed for %s × %s: %s", query.id, model, e)
                        result["score_combined"] = 0
                        result["score_error"] = str(e)

                results.append(result)

    return results


def main():
    parser = argparse.ArgumentParser(description="Batch model evaluation")
    parser.add_argument("--models", required=True, help="Comma-separated model list")
    parser.add_argument("--stages", default="interpreter,narrator", help="Comma-separated stages")
    parser.add_argument("--queries", default="data/eval/queries.json", help="Query set JSON file")
    parser.add_argument("--judge-model", default=None, help="Model for LLM judge (default: from config)")
    parser.add_argument("--db-path", default="data/index/bibliographic.db", help="Database path")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: auto-generated)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    models = [m.strip() for m in args.models.split(",")]
    stages = [s.strip() for s in args.stages.split(",")]
    queries = load_query_set(Path(args.queries))

    # Validate query set
    warnings = validate_query_set(queries)
    for w in warnings:
        print(f"  WARNING: {w}")

    judge_model = args.judge_model
    if judge_model is None:
        config = load_config()
        judge_model = config.judge.model

    output_dir = Path(args.output_dir) if args.output_dir else Path(
        f"data/eval/runs/{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M%S')}"
    )

    print(f"\nEvaluation: {len(queries)} queries × {len(models)} models × {len(stages)} stages")
    print(f"Judge model: {judge_model}")
    print(f"Output: {output_dir}\n")

    results = asyncio.run(run_evaluation(queries, models, stages, judge_model, args.db_path))

    report_dir = generate_report(results, output_dir)
    print(f"\nReport saved to {report_dir}/")
    print(f"  - results.json ({len(results)} entries)")
    print(f"  - scores.json (aggregated)")
    print(f"  - human_review.csv (fill in human_score column)")
    print(f"  - summary.md (readable table)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify CLI runs with `--help`**

Run: `python3 scripts/eval/run_eval.py --help`
Expected: Help text with all arguments listed

- [ ] **Step 4: Commit**

```bash
git add scripts/eval/report.py scripts/eval/run_eval.py
git commit -m "feat: add batch evaluation CLI with report generation"
```

---

## Phase 4: UI Comparison Mode

### Task 10: Build Compare API Endpoint

**Files:**
- Create: `app/api/compare.py`
- Modify: `app/api/models.py`
- Modify: `app/api/main.py`

- [ ] **Step 1: Add request/response models to app/api/models.py**

Add to the end of `app/api/models.py`:

```python
class ModelPair(BaseModel):
    """A specific interpreter + narrator model configuration."""
    interpreter: str = Field(..., description="Model for interpreter stage")
    narrator: str = Field(..., description="Model for narrator stage")


class CompareRequest(BaseModel):
    """Request to /chat/compare endpoint."""
    message: str = Field(..., min_length=1, description="User's query")
    configs: list[ModelPair] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="Model configurations to compare (max 3)",
    )
    session_id: Optional[str] = Field(None, description="Optional session ID")
    token_saving: bool = Field(True, description="Use lean prompt builder")


class ComparisonMetrics(BaseModel):
    """Metrics for a single comparison result."""
    latency_ms: int
    cost_usd: float
    tokens: Dict[str, int]  # {"input": N, "output": N}


class ComparisonResult(BaseModel):
    """One model configuration's result."""
    config: ModelPair
    response: Optional[ChatResponse]
    metrics: ComparisonMetrics
    error: Optional[str] = None


class CompareResponse(BaseModel):
    """Response from /chat/compare endpoint."""
    comparisons: list[ComparisonResult]
```

- [ ] **Step 2: Implement compare endpoint**

```python
# app/api/compare.py
"""POST /chat/compare — run same query through multiple model configs side-by-side."""

from __future__ import annotations

import asyncio
import logging
import time

from app.api.models import (
    CompareRequest,
    CompareResponse,
    ComparisonResult,
    ComparisonMetrics,
    ModelPair,
)
from scripts.chat.interpreter import interpret
from scripts.chat.executor import execute
from scripts.chat.narrator import narrate
from scripts.chat.models import ChatResponse
from scripts.chat.plan_models import ConversationPhase
from scripts.utils.llm_logger import token_accumulator

logger = logging.getLogger(__name__)


async def _run_pipeline_with_config(
    message: str,
    config: ModelPair,
    db_path: str,
    token_saving: bool,
) -> ComparisonResult:
    """Run the full scholar pipeline with a specific model configuration."""
    start = time.monotonic()
    token_accumulator.reset()

    try:
        plan = await interpret(message, model=config.interpreter)
        exec_result = await execute(plan, db_path=db_path)
        scholar_resp = await narrate(
            message, exec_result,
            model=config.narrator,
            token_saving=token_saving,
        )

        latency_ms = int((time.monotonic() - start) * 1000)
        breakdown = token_accumulator.get_breakdown()

        response = ChatResponse(
            message=scholar_resp.narrative,
            candidate_set=None,
            suggested_followups=scholar_resp.suggested_followups,
            clarification_needed=None,
            session_id="compare",
            phase=ConversationPhase.QUERY_DEFINITION,
            confidence=scholar_resp.confidence,
            metadata={"model_config": {"interpreter": config.interpreter, "narrator": config.narrator}},
        )

        return ComparisonResult(
            config=config,
            response=response,
            metrics=ComparisonMetrics(
                latency_ms=latency_ms,
                cost_usd=round(breakdown.get("cost_usd", 0), 4),
                tokens={
                    "input": breakdown.get("input_tokens", 0),
                    "output": breakdown.get("output_tokens", 0),
                },
            ),
        )
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.exception("Compare pipeline failed for config %s", config)
        return ComparisonResult(
            config=config,
            response=None,
            metrics=ComparisonMetrics(latency_ms=latency_ms, cost_usd=0, tokens={"input": 0, "output": 0}),
            error=str(e),
        )


async def run_comparison(
    request: CompareRequest,
    db_path: str,
) -> CompareResponse:
    """Run the comparison — all configs in parallel."""
    tasks = [
        _run_pipeline_with_config(request.message, cfg, db_path, request.token_saving)
        for cfg in request.configs
    ]
    results = await asyncio.gather(*tasks)
    return CompareResponse(comparisons=list(results))
```

- [ ] **Step 3: Wire the endpoint into main.py**

In `app/api/main.py`, add the import and route:

```python
from app.api.compare import run_comparison
from app.api.models import CompareRequest, CompareResponse
```

Add the endpoint (after the `/chat` endpoint):

```python
@app.post("/chat/compare", response_model=CompareResponse)
@limiter.limit("10/minute")
async def chat_compare(
    request: Request,
    compare_request: CompareRequest,
    _user=Depends(require_role("full")),  # Admin/full only
):
    """Compare multiple model configurations side-by-side."""
    bib_db = get_db_path()
    return await run_comparison(compare_request, bib_db)
```

- [ ] **Step 4: Commit**

```bash
git add app/api/compare.py app/api/models.py app/api/main.py
git commit -m "feat: add /chat/compare endpoint for side-by-side model comparison"
```

---

### Task 11: Build Frontend Compare Mode

**Files:**
- Modify: `frontend/src/types/chat.ts`
- Create: `frontend/src/components/ModelSelector.tsx`
- Create: `frontend/src/components/CompareMode.tsx`
- Modify: `frontend/src/App.tsx` (or main chat component)

- [ ] **Step 1: Add TypeScript types**

Add to `frontend/src/types/chat.ts`:

```typescript
// ---------------------------------------------------------------------------
// Compare Mode Types
// ---------------------------------------------------------------------------

export interface ModelPair {
  interpreter: string;
  narrator: string;
}

export interface CompareRequest {
  message: string;
  configs: ModelPair[];
  session_id?: string;
  token_saving: boolean;
}

export interface ComparisonMetrics {
  latency_ms: number;
  cost_usd: number;
  tokens: { input: number; output: number };
}

export interface ComparisonResult {
  config: ModelPair;
  response: ChatMessage | null;
  metrics: ComparisonMetrics;
  error: string | null;
}

export interface CompareResponse {
  comparisons: ComparisonResult[];
}

// Available models for selection
export const AVAILABLE_MODELS = [
  'gpt-4.1',
  'gpt-4.1-mini',
  'gpt-4.1-nano',
  'gpt-5-mini',
  'gpt-5.4',
] as const;
```

- [ ] **Step 2: Build ModelSelector component**

Create `frontend/src/components/ModelSelector.tsx`: A checkbox-based model picker that lets the user select up to 3 model configurations (interpreter + narrator pairs). Each row has two dropdowns (interpreter model, narrator model). An "Add Configuration" button adds rows (max 3). The component calls back with the selected `ModelPair[]`.

- [ ] **Step 3: Build CompareMode component**

Create `frontend/src/components/CompareMode.tsx`: The side-by-side comparison view. Includes:
- ModelSelector at the top
- A query input field
- A "Compare" button that POSTs to `/chat/compare`
- Results displayed as cards (one per config) showing: narrative, latency, cost, tokens
- A 1-5 star rating widget on each card
- Ratings saved via a POST to a simple `/chat/compare/rate` endpoint (or appended to a local state for now)

- [ ] **Step 4: Wire CompareMode into the app**

In the main chat component (likely `frontend/src/App.tsx` or the chat page), add a toggle button "Compare Mode" that switches between normal chat and the CompareMode component. The toggle is only visible to admin/full role users (check the user's role from the auth context).

- [ ] **Step 5: Build and verify frontend compiles**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/chat.ts frontend/src/components/ModelSelector.tsx frontend/src/components/CompareMode.tsx frontend/src/App.tsx
git commit -m "feat: add frontend compare mode with model selector and side-by-side results"
```

---

## Phase 5: Integration & Verification

### Task 12: End-to-End Verification

**Files:** None new — verification only

- [ ] **Step 1: Verify default config works (no behavior change)**

Run the existing chat endpoint with default config:
```bash
python3 -c "
import asyncio
from scripts.chat.interpreter import interpret
plan = asyncio.run(interpret('Books printed in Venice'))
print(f'Intents: {plan.intents}')
print(f'Steps: {len(plan.execution_steps)}')
print(f'Confidence: {plan.confidence}')
"
```
Expected: Works exactly as before — same model (gpt-4.1), same output format.

- [ ] **Step 2: Verify config override works**

Create a test config with a different model:
```bash
echo '{"interpreter":{"model":"gpt-4.1-mini"},"narrator":{"model":"gpt-4.1-mini"},"meta_extraction":{"model":"gpt-4.1-nano"},"judge":{"model":"gpt-4.1"}}' > /tmp/test-config.json
```
Then verify it's picked up (this would need the config path to be overridden — verify the config loading works).

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests pass

- [ ] **Step 4: Verify evaluation CLI runs with a small query set**

Create a minimal 2-query test set and run:
```bash
python3 scripts/eval/run_eval.py \
  --models gpt-4.1-mini \
  --stages interpreter \
  --queries data/eval/queries.json \
  --output-dir /tmp/eval-test
```
Expected: Report generated in `/tmp/eval-test/` with results.json, scores.json, human_review.csv, summary.md

- [ ] **Step 5: Commit any fixes from verification**

```bash
git add -A
git commit -m "fix: integration fixes from end-to-end verification"
```

- [ ] **Step 6: Final commit — update documentation**

Update `docs/current/architecture.md` to mention the model config system. Add `data/eval/model-config.json` to the directory conventions in CLAUDE.md. Update the Common Commands section:

```bash
python3 scripts/eval/run_eval.py --models gpt-4.1,gpt-4.1-mini --stages interpreter,narrator --queries data/eval/queries.json
```

```bash
git add docs/ CLAUDE.md
git commit -m "docs: add model evaluation to architecture docs and CLAUDE.md"
```
