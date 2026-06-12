"""Test factory for LLM execution steps (issue #14).

``ExecutionStepLLM`` became a discriminated union of per-action step types,
so it is no longer directly constructible with ``params`` as a JSON string.
This factory keeps the old ergonomic test signature: it accepts params as a
dict or JSON string, fills the union's required keys with the same neutral
defaults the prompt documents, and validates through the union — i.e., tests
construct steps exactly the way constrained decoding would emit them.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from pydantic import TypeAdapter

from scripts.chat.plan_models import ExecutionStepLLM

_STEP_ADAPTER: TypeAdapter = TypeAdapter(ExecutionStepLLM)

_REQUIRED_DEFAULTS: dict[str, dict] = {
    "resolve_agent": {"variants": []},
    "resolve_publisher": {"variants": []},
    "retrieve": {"scope": "full_collection"},
    "aggregate": {"scope": "full_collection", "limit": 20},
    "find_connections": {"depth": 1},
    "enrich": {"fields": ["bio", "links"]},
    "sample": {"n": 10, "strategy": "diverse"},
}


class _LooseStep(SimpleNamespace):
    """Un-validated step stand-in: what a NON-strict provider might emit.

    The discriminated union makes unknown actions unrepresentable under
    strict decoding, but ``_convert_llm_plan``'s skip/drop machinery is kept
    as belt-and-suspenders for providers without schema enforcement — tests
    exercise that path with these.
    """


def make_step_llm(action: str, params, label: str = "", depends_on: list[int] | None = None):
    """Build a validated LLM step (union member) from loose test inputs.

    Unknown actions return an un-validated ``_LooseStep`` so conversion-layer
    tests can still exercise the drop/remap machinery.
    """
    if isinstance(params, str):
        params = json.loads(params)
    params = dict(params)
    if action not in _REQUIRED_DEFAULTS:
        return _LooseStep(action=action, params=params, label=label, depends_on=depends_on or [])
    for key, default in _REQUIRED_DEFAULTS[action].items():
        params.setdefault(key, default)
    return _STEP_ADAPTER.validate_python({
        "action": action,
        "params": params,
        "label": label,
        "depends_on": depends_on or [],
    })
