"""Live interaction logger for the Metadata Co-pilot Workbench.

Logs every user interaction to a JSONL file for analytics, debugging,
and understanding how librarians use the workbench.

Each log entry captures: timestamp, action type, field, parameters,
result summary, and duration.

Log file: logs/workbench_interactions.jsonl
"""

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_LOG_PATH = Path("logs/workbench_interactions.jsonl")


class InteractionLogger:
    """Append-only JSONL logger for workbench user interactions."""

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or DEFAULT_LOG_PATH
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        action: str,
        *,
        field: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        result_summary: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Append a single interaction entry to the log.

        Args:
            action: The interaction type (e.g., "view_coverage", "submit_correction",
                    "agent_chat", "approve_proposal", "export_csv").
            field: The metadata field being acted on (place, date, publisher, agent).
            params: Request parameters (query filters, pagination, etc.).
            result_summary: Brief summary of what was returned (counts, IDs, etc.).
            duration_ms: How long the operation took.
            error: Error message if the operation failed.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
        }
        if field is not None:
            entry["field"] = field
        if params:
            entry["params"] = params
        if result_summary:
            entry["result"] = result_summary
        if duration_ms is not None:
            entry["duration_ms"] = round(duration_ms, 1)
        if error is not None:
            entry["error"] = error

        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass  # Never let logging break the request

    @contextmanager
    def timed(self, action: str, **kwargs):
        """Context manager that logs the action with its duration.

        Usage:
            with logger.timed("view_coverage", field="place"):
                result = do_work()
                # optionally set result_summary on the context
        """
        start = time.monotonic()
        ctx = {"result_summary": None, "error": None}
        try:
            yield ctx
        except Exception as exc:
            ctx["error"] = str(exc)
            raise
        finally:
            elapsed = (time.monotonic() - start) * 1000
            self.log(
                action,
                result_summary=ctx.get("result_summary"),
                error=ctx.get("error"),
                duration_ms=elapsed,
                **kwargs,
            )


# Module-level singleton
interaction_logger = InteractionLogger()
