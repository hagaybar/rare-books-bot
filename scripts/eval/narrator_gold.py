"""Narrator gold-standard evaluation: fixtures, pricing, batch request builders.

Pure functions only — no network, no LLM calls. The batch I/O lives in
scripts/eval/batch_client.py; orchestration in run_narrator_gold_eval.py.
"""
from __future__ import annotations

# Prices in USD per 1M tokens (input, output). Source: OpenAI price list 2026-06.
# Batch API applies a flat 50% discount to both input and output.
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4.1":      (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-5":        (1.25, 10.00),
    "gpt-5-mini":   (0.25, 2.00),
    "gpt-5-nano":   (0.05, 0.40),
    "gpt-5.1":      (1.25, 10.00),
    "gpt-5.2":      (1.75, 14.00),
    "gpt-5.4":      (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.5":      (5.00, 30.00),
}


def estimate_request_cost(model: str, input_tokens: int, max_output_tokens: int,
                          batch: bool) -> float:
    """Upper-bound cost of one request: full input + output at the cap."""
    in_price, out_price = PRICING[model]
    cost = input_tokens * in_price / 1e6 + max_output_tokens * out_price / 1e6
    return cost * 0.5 if batch else cost


def estimate_batch_cost(requests: list[tuple[str, int, int]], batch: bool) -> float:
    """Sum estimate_request_cost over (model, input_tokens, max_output_tokens) triples."""
    return sum(estimate_request_cost(m, i, o, batch) for (m, i, o) in requests)
