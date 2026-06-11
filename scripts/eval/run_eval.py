def extract_filters(plan) -> dict[str, list]:
    """Collect ALL filter values per field across all plan steps.

    The previous implementation kept only the last value per field
    (dict overwrite), so multi-step / multi-filter plans were scored
    on a fraction of what they actually contained.
    """
    filters_produced: dict[str, list] = {}
    for step in plan.execution_steps:
        if hasattr(step.params, "filters"):
            for f in step.params.filters:
                key = f.field.value if hasattr(f.field, "value") else str(f.field)
                if f.type == "RANGE":
                    filters_produced.setdefault(key, []).append(f"{f.start}-{f.end}")
                else:
                    filters_produced.setdefault(key, []).append(f.value)
    return filters_produced


async def evaluate_interpreter(
    query: EvalQuery,
    model: str,
    db_path: str,
) -> dict[str, Any]:
    """Run interpreter for a single query x model and return raw result."""
    from scripts.chat.interpreter import interpret

    start = time.monotonic()
    try:
        plan = await interpret(query.query, model=model)
        latency_ms = (time.monotonic() - start) * 1000

        filters_produced = extract_filters(plan)
        recall = compute_recall(plan, db_path)

        return {
            "query_id": query.id,
            "model": model,
            "stage": "interpreter",
            "success": True,
            "latency_ms": round(latency_ms),
            "recall": recall,
            "plan": {
                "intents": plan.intents,
                "execution_steps": [
                    {"action": s.action.value if hasattr(s.action, 'value') else str(s.action),
                     "label": s.label,
                     "params": s.params.model_dump() if hasattr(s.params, "model_dump") else str(s.params)}
                    for s in plan.execution_steps
                ],
                "filters_produced": filters_produced,
                "confidence": plan.conf,
                "clarification": getattr(plan, "clarification", None)
            },
            "expected_intent": query.expected_intent
        }
    except Exception as e:
        return {
            "query_id": query.id,
            "model": model,
            "stage": "interpreter",
            "success": False,
            "error": str(e)
        }


def score_interpreter(result: dict[str, Any], judge_model: str) -> dict[str, Any]:
    """Score an interpreter result using a judge model."""
    from scripts.models.llm_client import structured_completion

    query_id = result["query_id"]
    model = result["model"]
    plan = result["plan"]
    expected_intent = result["expected_intent"]

    if expected_intent == "clarification":
        intent_match = plan.get("clarification") is not None
    else:
        intent_match = expected_intent in plan["intents"]

    prompt = (
        f"Query {query_id}: {expected_intent}\n"
        "Execution steps:\n"
        + "\n".join(
            f"- {step['action']} {step['label']}: {step['params']}"
            for step in plan["execution_steps"]
        )
        + f"\nFilters: {plan['filters_produced']}\n"
        + f"Confidence: {plan['confidence']}\n"
        + f"Clarification: {plan.get('clarification', 'None')}\n"
        + "Asking for clarification on a garbled/ambiguous query is correct behavior.\n"
        "Score this plan based on its correctness and the quality of the clarification."
    )

    score = structured_completion(judge_model, prompt)
    return {
        "query_id": query_id,
        "model": model,
        "score": score,
        "intent_match": intent_match
    }