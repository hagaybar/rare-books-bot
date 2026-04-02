# Model Evaluation & Cost Optimization Infrastructure

> Design spec for multi-model comparison framework using LiteLLM
> Created: 2026-04-03
> Status: Approved
> Branch: feature/model-evaluation

## 1. Goal

Build infrastructure to choose LLM models per pipeline stage and compare their quality/cost/latency, enabling data-driven model selection for the best cost-effectiveness ratio.

**Primary success criterion**: Given a curated query set, produce a scored comparison report showing quality vs. cost for each model × stage combination, enabling confident model selection.

## 2. Approach: LiteLLM as Provider Layer

Use [LiteLLM](https://docs.litellm.ai/) as the unified provider abstraction instead of building a custom one. LiteLLM provides:
- Unified API across 100+ providers (OpenAI, Anthropic, Ollama, etc.)
- Built-in cost tracking (`completion_cost()`)
- Async streaming
- Structured output with `response_format` (Pydantic models)
- Fallback/retry via Router

### Migration: OpenAI Responses API → LiteLLM Chat Completions API

Current code uses OpenAI's `client.responses.parse()` (Responses API), which is OpenAI-specific. LiteLLM uses the Chat Completions API pattern:

```python
# Before (OpenAI-only):
resp = client.responses.parse(model=model, input=messages, text_format=MyModel)
result = resp.output_parsed

# After (LiteLLM, any provider):
resp = await litellm.acompletion(model=model, messages=messages, response_format=MyModel)
result = MyModel.model_validate_json(resp.choices[0].message.content)
```

### Files requiring migration

| File | Current API | Change |
|------|------------|--------|
| `scripts/chat/interpreter.py` | `client.responses.parse()` | → `litellm.acompletion()` + Pydantic parse |
| `scripts/chat/narrator.py` (sync) | `client.responses.parse()` | → `litellm.acompletion()` + Pydantic parse |
| `scripts/chat/narrator.py` (stream) | `client.responses.create(stream=True)` | → `litellm.acompletion(stream=True)` |
| `scripts/chat/narrator.py` (meta) | `client.responses.parse()` | → `litellm.acompletion()` + Pydantic parse |
| `scripts/query/llm_compiler.py` | `client.responses.parse()` | → `litellm.acompletion()` (legacy, low priority) |
| `scripts/metadata/agent_harness.py` | `openai.Client` direct calls | → `litellm.acompletion()` |

### Streaming migration

Current streaming listens for `event.type == "response.output_text.delta"` (Responses API). LiteLLM streaming uses `chunk.choices[0].delta.content`. The callback logic in `_stream_llm()` needs updating.

### Known Pydantic constraint issue

`NarratorResponseLLM` and `StreamingMetaLLM` use `ge=0.0, le=1.0` on confidence fields. Anthropic rejects schemas with `minimum`/`maximum`. Fixed in LiteLLM ≥ v1.81.9 (strips unsupported constraints automatically). Pin to a compatible version.

### Recommended: explicit JSON schema conversion

For reliability across providers, convert Pydantic to explicit JSON schema rather than passing models directly:

```python
def pydantic_to_response_format(model: type[BaseModel]) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "schema": model.model_json_schema(),
            "name": model.__name__,
            "strict": True,
        }
    }
```

## 3. Model Configuration

### Config file: `data/eval/model-config.json`

```json
{
  "interpreter": {"model": "gpt-4.1"},
  "narrator": {"model": "gpt-4.1"},
  "meta_extraction": {"model": "gpt-4.1-nano"},
  "judge": {"model": "gpt-4.1"}
}
```

Switching a stage to a different provider is a single string change:
- OpenAI: `"gpt-4.1"`, `"gpt-4.1-mini"`, `"gpt-5-mini"`, `"gpt-5.4"`
- Anthropic: `"anthropic/claude-sonnet-4-6"`, `"anthropic/claude-haiku-4-5"`
- Ollama: `"ollama/llama3"`

### Config module: `scripts/models/config.py`

Loads the JSON config and provides `get_model(stage: str) -> str`. Falls back to defaults if config file missing.

### LLM client: `scripts/models/llm_client.py`

Thin async wrapper: reads stage config → calls `litellm.acompletion()` → feeds results into existing `llm_logger`. Replaces direct `openai.Client` calls in interpreter/narrator.

### Cost tracking simplification

Replace the manual `PRICING_PER_1M_TOKENS` dict in `scripts/utils/llm_logger.py` with `litellm.completion_cost()`. Keep the JSONL logging and token accumulator — just change the cost source.

## 4. Batch Evaluation Framework

### File structure

```
scripts/eval/
  run_eval.py        # CLI entry point
  query_set.py       # Load/manage curated test queries
  judge.py           # LLM-as-judge scoring
  report.py          # Generate comparison report
data/eval/
  queries.json       # Curated test query set (20-30 queries)
  runs/              # One directory per evaluation run
```

### Query set: `data/eval/queries.json`

20-30 hand-curated queries covering all intent types:

```json
[
  {
    "id": "q01",
    "query": "Books printed by Daniel Bomberg in Venice",
    "intent": "retrieval",
    "difficulty": "simple",
    "expected_filters": {"publisher": "daniel bomberg", "place": "venice"},
    "notes": "Well-known Hebrew printer, should produce clear results"
  },
  {
    "id": "q12",
    "query": "What connections exist between Elijah Levita and other scholars?",
    "intent": "entity_exploration",
    "difficulty": "complex",
    "expected_filters": {"agent": "levita, elijah"},
    "notes": "Tests agent resolution + network connections"
  }
]
```

Intent coverage: retrieval, entity_exploration, analytical, comparison, curation, topical, follow_up, overview. Difficulty levels: simple, moderate, complex.

### CLI usage

```bash
python3 scripts/eval/run_eval.py \
  --models gpt-4.1,gpt-4.1-mini,gpt-5-mini,gpt-5.4 \
  --stages interpreter,narrator \
  --queries data/eval/queries.json
```

For each query × model × stage:
1. Run the pipeline stage with that model
2. Record: output, latency, token usage, cost
3. Score with LLM-as-judge
4. Save to `data/eval/runs/YYYY-MM-DD-HHMMSS/`

### Default evaluation model set

| Stage | Candidates |
|-------|-----------|
| Interpreter | gpt-4.1, gpt-4.1-mini, gpt-5-mini, gpt-5.4 |
| Narrator | gpt-4.1, gpt-4.1-mini, gpt-5-mini, gpt-5.4 |
| Meta extraction | gpt-4.1-nano, gpt-5-nano |

Model list is a CLI argument — add or remove per run.

### LLM-as-Judge scoring (`scripts/eval/judge.py`)

**Interpreter scoring** (deterministic + judge):
- Correct intent classification (exact match, automated)
- Expected filter overlap (automated score)
- Execution step quality (LLM judge, 1-5 scale)

**Narrator scoring** (judge only):
- **Accuracy**: Does narrative correctly reflect grounding data? (1-5)
- **Completeness**: Are all relevant records/agents mentioned? (1-5)
- **Scholarly tone**: Appropriate for bibliographic discovery? (1-5)
- **Conciseness**: No filler or hallucination? (1-5)

Judge uses a strong model (configurable via `judge` key in model-config.json) with structured rubric prompt. Each criterion scored 1-5 with brief justification.

### Human review layer

After automated run, report includes `human_review.csv`:
`query_id, model, stage, auto_score, human_score, notes`

Fill in `human_score` for a calibration subset (~10 queries × top 2-3 models) to validate the LLM judge.

### Output artifacts

```
data/eval/runs/YYYY-MM-DD-HHMMSS/
  results.json        # Raw results per query × model × stage
  scores.json         # Aggregated scores per model × stage
  human_review.csv    # Template for human calibration
  summary.md          # Readable comparison table
```

Summary table format:

```
| Model         | Stage       | Avg Score | Avg Latency | Avg Cost | Tokens |
|---------------|-------------|-----------|-------------|----------|--------|
| gpt-4.1       | interpreter | 4.8       | 2.1s        | $0.032   | 6,200  |
| gpt-4.1-mini  | interpreter | 4.5       | 1.4s        | $0.004   | 5,800  |
| gpt-5-mini    | interpreter | 4.7       | 1.2s        | $0.003   | 5,600  |
| gpt-5.4       | interpreter | 4.9       | 2.8s        | $0.045   | 6,400  |
```

## 5. UI Comparison Mode

### API endpoint: `POST /chat/compare`

```json
// Request
{
  "message": "Books printed in Venice before 1550",
  "models": {
    "interpreter": ["gpt-4.1", "gpt-5-mini"],
    "narrator": ["gpt-4.1", "gpt-5-mini"]
  },
  "session_id": "optional"
}

// Response
{
  "comparisons": [
    {
      "config": {"interpreter": "gpt-4.1", "narrator": "gpt-4.1"},
      "response": { /* standard ChatResponse */ },
      "metrics": {"latency_ms": 3200, "cost_usd": 0.064, "tokens": {"input": 5800, "output": 1200}}
    },
    {
      "config": {"interpreter": "gpt-5-mini", "narrator": "gpt-5-mini"},
      "response": { /* standard ChatResponse */ },
      "metrics": {"latency_ms": 1800, "cost_usd": 0.008, "tokens": {"input": 5500, "output": 1100}}
    }
  ]
}
```

Runs full pipeline N times in parallel (`asyncio.gather()`). Each combination pairs one interpreter model with one narrator model. The frontend sends explicit config pairs (not a cartesian product) — the user picks which combinations to compare (max 3).

### Frontend components

- **CompareMode toggle**: Button next to chat input. When active, switches to comparison layout.
- **ModelSelector**: Checkboxes for which models to include in comparison.
- **Side-by-side cards**: Each card shows narrative response, latency, cost, token count.
- **Rating widget**: 1-5 star rating on each card. Ratings saved to `data/eval/ui-ratings.jsonl`.

### Constraints

- **Admin-only**: Behind existing auth — only admin/full role users can access compare mode.
- **Max 3 models per comparison**: Hard limit to bound costs.
- **No streaming**: Synchronous responses only in compare mode (need complete results side-by-side). Regular chat keeps streaming.
- **Normal chat unchanged**: Compare mode is additive — the default flow is untouched unless you flip the toggle.

## 6. New File Structure

```
scripts/models/
  config.py              # Stage → model config loader
  llm_client.py          # Thin litellm wrapper with logging

scripts/eval/
  run_eval.py            # Batch evaluation CLI
  query_set.py           # Query set loader/validator
  judge.py               # LLM-as-judge scoring
  report.py              # Summary report generator

data/eval/
  model-config.json      # Active model configuration
  queries.json           # Curated benchmark queries
  runs/                  # Evaluation run outputs

app/api/
  compare.py             # /chat/compare endpoint

frontend/src/components/
  CompareMode.tsx         # Side-by-side comparison UI
  ModelSelector.tsx       # Model picker
```

## 7. What Stays the Same

- All Pydantic schemas (`InterpretationPlanLLM`, `NarratorResponseLLM`, etc.)
- System prompts
- Pipeline flow (interpret → execute → narrate)
- Token accumulator and quota system (fed by litellm costs instead of manual calc)
- Existing `/chat` endpoint behavior (reads model from config instead of hardcoded default)
- Existing `/ws/chat` WebSocket endpoint

## 8. Dependencies

- `litellm` — add to pyproject.toml (pin to ≥ 1.81.9 for Pydantic constraint fix)
- No other new dependencies
