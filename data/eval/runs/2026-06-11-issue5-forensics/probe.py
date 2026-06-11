"""Issue #5 forensics: are empty plans LLM emission or conversion drops?"""
import asyncio, json, logging
from pathlib import Path

from scripts.chat.interpreter import (
    INTERPRETER_SYSTEM_PROMPT, InterpretationPlanLLM, _build_user_prompt,
    _convert_llm_plan,
)
from scripts.models.llm_client import structured_completion

QUERIES = {
    "q14": "Books related to Napoleon",
    "q27": "What Italian language books are in the collection?",
    "q29": "What Yiddish texts are in the collection?",
    "q30": "Books printed in Jerusalem",
}
ATTEMPTS = 3
OUT = Path("data/eval/runs/2026-06-11-issue5-forensics/evidence.json")


class WarnCatcher(logging.Handler):
    def __init__(self): super().__init__(); self.records = []
    def emit(self, r): self.records.append(r.getMessage())


async def main():
    logger = logging.getLogger("scripts.chat.interpreter")
    evidence = []
    for qid, q in QUERIES.items():
        for attempt in range(1, ATTEMPTS + 1):
            user_prompt = _build_user_prompt(q, None)
            result = await structured_completion(
                model="gpt-4.1-mini", system=INTERPRETER_SYSTEM_PROMPT,
                user=user_prompt, response_schema=InterpretationPlanLLM,
                call_type="issue5_forensics", extra_metadata={"query_text": q},
            )
            raw: InterpretationPlanLLM = result.parsed
            catcher = WarnCatcher(); logger.addHandler(catcher)
            try:
                converted = _convert_llm_plan(raw)
            finally:
                logger.removeHandler(catcher)
            evidence.append({
                "query_id": qid, "attempt": attempt,
                "raw_steps": len(raw.execution_steps),
                "raw_actions": [s.action for s in raw.execution_steps],
                "raw_params": [s.params for s in raw.execution_steps],
                "raw_intents": list(raw.intents),
                "raw_confidence": raw.confidence,
                "raw_clarification": getattr(raw, "clarification", None),
                "converted_steps": len(converted.execution_steps),
                "drop_warnings": catcher.records,
            })
            verdict = ("EMITTED-EMPTY" if not raw.execution_steps
                       else "DROPPED" if len(converted.execution_steps) < len(raw.execution_steps)
                       else "OK")
            print(f"{qid} #{attempt}: raw={len(raw.execution_steps)} converted={len(converted.execution_steps)} -> {verdict}", flush=True)
            await asyncio.sleep(3)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=1))
    print(f"wrote {OUT}")

asyncio.run(main())
