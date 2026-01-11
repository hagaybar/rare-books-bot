"""Query compiler - Natural Language → QueryPlan using LLM.

This module now uses LLM-based query parsing via the llm_compiler module.
The previous heuristic/regex parser has been replaced with OpenAI's Responses API
for more robust and flexible query understanding.
"""

import json
import hashlib
from pathlib import Path
from typing import Optional

from scripts.query.llm_compiler import compile_query_llm as compile_query
from scripts.schemas import QueryPlan


def write_plan_to_file(plan: QueryPlan, output_path: Path) -> None:
    """Write QueryPlan to JSON file.

    Args:
        plan: Validated QueryPlan
        output_path: Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(plan.model_dump(), f, indent=2, ensure_ascii=False)


def compute_plan_hash(plan: QueryPlan) -> str:
    """Compute SHA256 hash of canonicalized plan.

    Args:
        plan: QueryPlan

    Returns:
        Hex digest of SHA256 hash
    """
    # Serialize to JSON with sorted keys for canonical representation
    plan_json = json.dumps(plan.model_dump(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(plan_json.encode('utf-8')).hexdigest()


# Re-export for backward compatibility
__all__ = ['compile_query', 'write_plan_to_file', 'compute_plan_hash']
