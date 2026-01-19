"""LLM call logging with cost tracking and prompt capture.

This module provides centralized logging for all OpenAI API calls, capturing:
- Full prompts (system + user) with optional truncation for previews
- Token usage (input/output/total)
- Cost estimates based on current pricing
- Call metadata (model, timestamp, call type, session info)

Logs are written as structured JSON to enable analysis and debugging.

Usage:
    from scripts.utils.llm_logger import LLMLogger

    llm_logger = LLMLogger()

    # After making an OpenAI call:
    llm_logger.log_call(
        call_type="intent_interpretation",
        model="gpt-4o",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response=resp,
        session_id=session_id,  # optional
    )
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.utils.logger import LoggerManager


# Pricing per 1M tokens (as of January 2025)
# Update these when OpenAI changes pricing
PRICING_PER_1M_TOKENS = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}

# Default log file path
DEFAULT_LLM_LOG_PATH = Path("logs/llm_calls.jsonl")


class LLMLogger:
    """Centralized logger for LLM API calls.

    Captures prompts, token usage, and cost estimates for all OpenAI calls.
    Logs are written as JSON lines for easy parsing and analysis.

    Attributes:
        log_path: Path to the JSONL log file
        logger: Python logger instance for structured logging
        log_full_prompts: Whether to log full prompts or just previews
    """

    def __init__(
        self,
        log_path: Optional[Path] = None,
        log_full_prompts: bool = True,
        preview_length: int = 500,
    ):
        """Initialize LLM logger.

        Args:
            log_path: Path to JSONL log file. Defaults to logs/llm_calls.jsonl
            log_full_prompts: If True, log complete prompts. If False, log previews only.
            preview_length: Max characters for prompt previews when log_full_prompts=False
        """
        self.log_path = log_path or DEFAULT_LLM_LOG_PATH
        self.log_full_prompts = log_full_prompts
        self.preview_length = preview_length

        # Ensure log directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Get a logger for console output
        self.logger = LoggerManager.get_logger(
            name="llm_logger",
            level="INFO",
            use_json=False,
        )

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate estimated cost in USD.

        Args:
            model: Model name (e.g., "gpt-4o")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD
        """
        pricing = PRICING_PER_1M_TOKENS.get(model, {"input": 0, "output": 0})
        cost = (
            (input_tokens * pricing["input"] / 1_000_000) +
            (output_tokens * pricing["output"] / 1_000_000)
        )
        return round(cost, 6)

    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text with ellipsis if too long.

        Args:
            text: Text to truncate
            max_length: Maximum length

        Returns:
            Truncated text with "..." suffix if truncated
        """
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."

    def log_call(
        self,
        call_type: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response: Any,
        session_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Log an LLM API call with full details.

        Args:
            call_type: Type of call (e.g., "intent_interpretation", "query_compilation")
            model: Model name (e.g., "gpt-4o")
            system_prompt: The system prompt sent
            user_prompt: The user prompt sent
            response: The OpenAI API response object
            session_id: Optional session ID for tracking conversations
            extra_metadata: Optional additional metadata to include

        Returns:
            The log entry dict that was written
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # Extract usage from response
        usage = getattr(response, 'usage', None)
        input_tokens = getattr(usage, 'input_tokens', 0) if usage else 0
        output_tokens = getattr(usage, 'output_tokens', 0) if usage else 0
        total_tokens = input_tokens + output_tokens

        # Calculate cost
        cost_usd = self._calculate_cost(model, input_tokens, output_tokens)

        # Build log entry
        log_entry = {
            "timestamp": timestamp,
            "call_type": call_type,
            "model": model,
            "session_id": session_id,
            "prompts": {
                "system_length": len(system_prompt),
                "user_length": len(user_prompt),
            },
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            "cost_usd": cost_usd,
        }

        # Add full prompts or previews
        if self.log_full_prompts:
            log_entry["prompts"]["system"] = system_prompt
            log_entry["prompts"]["user"] = user_prompt
        else:
            log_entry["prompts"]["system_preview"] = self._truncate(
                system_prompt, self.preview_length
            )
            log_entry["prompts"]["user_preview"] = self._truncate(
                user_prompt, self.preview_length
            )

        # Add extra metadata if provided
        if extra_metadata:
            log_entry["metadata"] = extra_metadata

        # Write to JSONL file
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            self.logger.warning(f"Failed to write LLM log: {e}")

        # Also log summary to console
        self.logger.info(
            f"LLM call: {call_type} | model={model} | "
            f"tokens={total_tokens} (in={input_tokens}, out={output_tokens}) | "
            f"cost=${cost_usd:.6f}"
        )

        return log_entry

    def get_session_costs(self, session_id: str) -> Dict[str, Any]:
        """Get total costs for a session.

        Args:
            session_id: Session ID to filter by

        Returns:
            Dict with total_cost, total_tokens, and call_count
        """
        if not self.log_path.exists():
            return {"total_cost": 0, "total_tokens": 0, "call_count": 0}

        total_cost = 0.0
        total_tokens = 0
        call_count = 0

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if entry.get("session_id") == session_id:
                            total_cost += entry.get("cost_usd", 0)
                            total_tokens += entry.get("usage", {}).get("total_tokens", 0)
                            call_count += 1
                    except json.JSONDecodeError:
                        continue

        return {
            "session_id": session_id,
            "total_cost": round(total_cost, 6),
            "total_tokens": total_tokens,
            "call_count": call_count,
        }

    def get_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get summary of LLM calls in the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            Dict with total_cost, total_tokens, call_count, and by_type breakdown
        """
        if not self.log_path.exists():
            return {
                "total_cost": 0,
                "total_tokens": 0,
                "call_count": 0,
                "by_type": {},
            }

        cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
        total_cost = 0.0
        total_tokens = 0
        call_count = 0
        by_type: Dict[str, Dict[str, Any]] = {}

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        # Parse timestamp
                        ts = datetime.fromisoformat(
                            entry.get("timestamp", "").replace("Z", "+00:00")
                        ).timestamp()

                        if ts >= cutoff:
                            cost = entry.get("cost_usd", 0)
                            tokens = entry.get("usage", {}).get("total_tokens", 0)
                            call_type = entry.get("call_type", "unknown")

                            total_cost += cost
                            total_tokens += tokens
                            call_count += 1

                            if call_type not in by_type:
                                by_type[call_type] = {
                                    "cost": 0,
                                    "tokens": 0,
                                    "count": 0,
                                }
                            by_type[call_type]["cost"] += cost
                            by_type[call_type]["tokens"] += tokens
                            by_type[call_type]["count"] += 1

                    except (json.JSONDecodeError, ValueError):
                        continue

        # Round costs
        for call_type in by_type:
            by_type[call_type]["cost"] = round(by_type[call_type]["cost"], 6)

        return {
            "period_hours": hours,
            "total_cost": round(total_cost, 6),
            "total_tokens": total_tokens,
            "call_count": call_count,
            "by_type": by_type,
        }


# Global instance for convenience
_llm_logger: Optional[LLMLogger] = None


def get_llm_logger() -> LLMLogger:
    """Get or create the global LLM logger instance.

    Returns:
        LLMLogger instance
    """
    global _llm_logger
    if _llm_logger is None:
        _llm_logger = LLMLogger()
    return _llm_logger


def log_llm_call(
    call_type: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response: Any,
    session_id: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience function to log an LLM call using the global logger.

    Args:
        call_type: Type of call (e.g., "intent_interpretation")
        model: Model name (e.g., "gpt-4o")
        system_prompt: The system prompt sent
        user_prompt: The user prompt sent
        response: The OpenAI API response object
        session_id: Optional session ID
        extra_metadata: Optional additional metadata

    Returns:
        The log entry dict that was written
    """
    return get_llm_logger().log_call(
        call_type=call_type,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response=response,
        session_id=session_id,
        extra_metadata=extra_metadata,
    )
