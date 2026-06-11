"""Free offline re-score of the 2026-06-10-postfix run (issues #10/#11).

Replays each stored plan deterministically (no LLM): recomputes
filter_overlap with the RANGE fix, intent_match with the clarification
rule, recall with intent-awareness — against today's executor.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.chat.plan_models import (
    AggregateParams, EnrichParams, ExecutionStep, FindConnectionsParams,
    InterpretationPlan, ResolveAgentParams, ResolvePublisherParams,
    RetrieveParams, SampleParams, StepAction,
)
from scripts.eval.judge import InterpreterScore, deterministic_checks
from scripts.eval.query_set import load_query_set
from scripts.eval.run_eval import compute_recall, extract_filters

PARAMS = {"resolve_agent": ResolveAgentParams, "resolve_publisher": ResolvePublisherParams,
          "retrieve": RetrieveParams, "aggregate": AggregateParams,
          "find_connections": FindConnectionsParams, "enrich": EnrichParams,
          "sample": SampleParams}
DB = "data/index/bibliographic.db"

queries = {q.id: q for q in load_query_set(Path("data/eval/queries.json"))}
stored = json.loads(Path("data/eval/runs/2026-06-10-postfix/results.json").read_text())

out, changed, zero_now = [], 0, []
old_avg, new_avg = [], []
for e in stored:
    q = queries.get(e["query_id"])
    if not q or not e.get("success"):
        continue
    steps = []
    rebuilt = True
    for s in e["plan"]["execution_steps"]:
        try:
            steps.append(ExecutionStep(action=StepAction(s["action"]),
                                       params=PARAMS[s["action"]](**s["params"]),
                                       label=s["label"], depends_on=[]))
        except Exception:
            rebuilt = False
            break
    if not rebuilt:
        continue
    plan = InterpretationPlan(intents=e["plan"]["intents"], reasoning="rescore",
                              confidence=e["plan"].get("confidence", 0.9), directives=[],
                              clarification=e["plan"].get("clarification"),
                              execution_steps=steps)
    fp = extract_filters(plan)
    plan_dict = {"intents": plan.intents, "clarification": plan.clarification,
                 "filters_produced": fp}
    intent_match, overlap = deterministic_checks(q, plan_dict)
    step_quality = (e.get("score_detail") or {}).get("step_quality", 3)
    score = InterpreterScore(intent_match=intent_match, filter_overlap=overlap,
                             step_quality=step_quality, justification="rescored")
    recall = compute_recall(plan, DB, expected_intent=q.intent)
    old = e.get("score_combined")
    new = round(score.combined, 2)
    if old is not None:
        old_avg.append(old); new_avg.append(new)
        if abs(new - old) >= 0.05:
            changed += 1
    if recall["zero_result"]:
        zero_now.append(e["query_id"])
    out.append({"query_id": e["query_id"], "old_score": old, "new_score": new,
                "old_zero": (e.get("recall") or {}).get("zero_result"),
                "new_zero": recall["zero_result"], "recall": recall})

Path(__file__).parent.joinpath("results.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1))
print(f"rescored {len(out)} | score changed >=0.05: {changed}")
print(f"avg: {sum(old_avg)/len(old_avg):.3f} -> {sum(new_avg)/len(new_avg):.3f}")
print(f"TRUE zero-result queries now: {len(zero_now)} -> {zero_now}")
