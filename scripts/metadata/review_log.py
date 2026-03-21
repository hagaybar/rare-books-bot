"""Queryable review log for tracking correction decisions.

Formalizes the append-only JSONL review log used by the feedback loop into a
queryable interface.  The critical addition is the *negative signal*: rejected
proposals are tracked so that agents can check ``is_rejected`` before
re-proposing a mapping that a human has already declined.

No LLM calls.  All operations are deterministic.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Valid action values (enforced on write, tolerated on read).
_VALID_ACTIONS = frozenset({"approved", "rejected", "edited", "skipped"})


@dataclass
class ReviewEntry:
    """A single review-log entry."""

    timestamp: str
    field: str
    raw_value: str
    canonical_value: str
    evidence: str
    source: str  # "human" or "agent"
    action: str  # "approved", "rejected", "edited", "skipped"
    records_affected: int = 0


class ReviewLog:
    """Append-only JSONL review log for tracking correction decisions.

    Serves two purposes:
    1. Audit trail for all corrections
    2. Negative signal -- rejected proposals tracked so agents don't re-propose
    """

    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def append(self, entry: ReviewEntry) -> None:
        """Append a single entry to the log."""
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def append_approved(
        self,
        field: str,
        raw_value: str,
        canonical_value: str,
        evidence: str = "",
        source: str = "human",
        records_affected: int = 0,
    ) -> None:
        """Convenience method for approved corrections."""
        self.append(
            ReviewEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                field=field,
                raw_value=raw_value,
                canonical_value=canonical_value,
                evidence=evidence,
                source=source,
                action="approved",
                records_affected=records_affected,
            )
        )

    def append_rejected(
        self,
        field: str,
        raw_value: str,
        canonical_value: str,
        evidence: str = "",
        source: str = "human",
    ) -> None:
        """Log a rejected proposal.

        ``records_affected`` is always 0 for rejections since no records are
        modified.
        """
        self.append(
            ReviewEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                field=field,
                raw_value=raw_value,
                canonical_value=canonical_value,
                evidence=evidence,
                source=source,
                action="rejected",
                records_affected=0,
            )
        )

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_history(
        self,
        field: Optional[str] = None,
        action: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[ReviewEntry], int]:
        """Query the review log with optional filters.

        Returns ``(entries, total_count)`` where *total_count* is the number
        of entries matching the filters (before pagination).
        """
        entries = self._read_all()

        # Apply filters
        if field is not None:
            entries = [e for e in entries if e.field == field]
        if action is not None:
            entries = [e for e in entries if e.action == action]
        if source is not None:
            entries = [e for e in entries if e.source == source]

        total_count = len(entries)
        paginated = entries[offset : offset + limit]
        return paginated, total_count

    def get_rejected(self, field: Optional[str] = None) -> List[ReviewEntry]:
        """Get all rejected proposals, optionally filtered by field.

        Used by agents to avoid re-proposing rejected mappings.
        """
        entries, _ = self.get_history(field=field, action="rejected", limit=10_000)
        return entries

    def is_rejected(self, field: str, raw_value: str) -> bool:
        """Check if a specific value has been rejected for a field.

        Fast check used by agents before proposing mappings.  Returns ``True``
        if *any* entry exists where ``(field, raw_value, action=rejected)``.
        """
        for entry in self._read_all():
            if (
                entry.field == field
                and entry.raw_value == raw_value
                and entry.action == "rejected"
            ):
                return True
        return False

    # ------------------------------------------------------------------
    # Aggregate API
    # ------------------------------------------------------------------

    def count_by_action(self) -> Dict[str, int]:
        """Count entries by action type (approved, rejected, edited, skipped)."""
        counts: Dict[str, int] = {}
        for entry in self._read_all():
            counts[entry.action] = counts.get(entry.action, 0) + 1
        return counts

    def count_by_field(self) -> Dict[str, int]:
        """Count entries by field."""
        counts: Dict[str, int] = {}
        for entry in self._read_all():
            counts[entry.field] = counts.get(entry.field, 0) + 1
        return counts

    def count_by_source(self) -> Dict[str, int]:
        """Count entries by source (human, agent)."""
        counts: Dict[str, int] = {}
        for entry in self._read_all():
            counts[entry.source] = counts.get(entry.source, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_all(self) -> List[ReviewEntry]:
        """Read all entries from the log file.

        Malformed lines are skipped with a warning log.
        """
        if not self.log_path.exists():
            return []

        entries: List[ReviewEntry] = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(ReviewEntry(**data))
                except (json.JSONDecodeError, TypeError, KeyError) as exc:
                    logger.warning(
                        "Skipping malformed line %d in %s: %s",
                        line_no,
                        self.log_path,
                        exc,
                    )
                    continue
        return entries
