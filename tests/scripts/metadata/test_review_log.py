"""Tests for the review log persistence module.

Covers: append/read, convenience methods, filtering, pagination,
rejected-signal queries, aggregation counters, empty-log edge case,
malformed-line resilience, and interleaved multi-entry scenarios.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.metadata.review_log import ReviewEntry, ReviewLog


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def log_path(tmp_path: Path) -> Path:
    """Return a fresh JSONL path inside a temporary directory."""
    return tmp_path / "review_log.jsonl"


@pytest.fixture()
def review_log(log_path: Path) -> ReviewLog:
    """Return a ReviewLog backed by a temp file."""
    return ReviewLog(log_path)


def _make_entry(
    field: str = "place",
    raw_value: str = "Lugduni Batavorum",
    canonical_value: str = "leiden",
    action: str = "approved",
    source: str = "human",
    evidence: str = "",
    records_affected: int = 0,
) -> ReviewEntry:
    """Helper factory for test entries."""
    return ReviewEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        field=field,
        raw_value=raw_value,
        canonical_value=canonical_value,
        evidence=evidence,
        source=source,
        action=action,
        records_affected=records_affected,
    )


# ---------------------------------------------------------------------------
# Basic append / read
# ---------------------------------------------------------------------------


class TestAppendAndRead:
    def test_append_and_read_back(self, review_log: ReviewLog) -> None:
        entry = _make_entry()
        review_log.append(entry)

        entries, total = review_log.get_history()
        assert total == 1
        assert len(entries) == 1
        assert entries[0].field == "place"
        assert entries[0].raw_value == "Lugduni Batavorum"
        assert entries[0].canonical_value == "leiden"
        assert entries[0].action == "approved"

    def test_append_multiple(self, review_log: ReviewLog) -> None:
        for i in range(5):
            review_log.append(_make_entry(raw_value=f"val_{i}"))

        entries, total = review_log.get_history()
        assert total == 5
        assert [e.raw_value for e in entries] == [f"val_{i}" for i in range(5)]


# ---------------------------------------------------------------------------
# Convenience methods
# ---------------------------------------------------------------------------


class TestConvenienceMethods:
    def test_append_approved(self, review_log: ReviewLog) -> None:
        review_log.append_approved(
            field="place",
            raw_value="Parisiis",
            canonical_value="paris",
            evidence="country_code=fr",
            source="agent",
            records_affected=12,
        )

        entries, total = review_log.get_history()
        assert total == 1
        e = entries[0]
        assert e.action == "approved"
        assert e.source == "agent"
        assert e.records_affected == 12
        assert e.evidence == "country_code=fr"

    def test_append_rejected(self, review_log: ReviewLog) -> None:
        review_log.append_rejected(
            field="publisher",
            raw_value="C. Fosset,",
            canonical_value="fosset",
            evidence="uncertain mapping",
            source="human",
        )

        entries, total = review_log.get_history()
        assert total == 1
        e = entries[0]
        assert e.action == "rejected"
        assert e.records_affected == 0  # always 0 for rejections
        assert e.field == "publisher"


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


class TestGetHistoryFilters:
    def _populate(self, review_log: ReviewLog) -> None:
        """Populate log with mixed entries for filter tests."""
        review_log.append_approved(field="place", raw_value="Parisiis", canonical_value="paris", source="human", records_affected=5)
        review_log.append_rejected(field="place", raw_value="Amstel.", canonical_value="amsterdam", source="agent")
        review_log.append_approved(field="publisher", raw_value="Elsevier:", canonical_value="elsevier", source="agent", records_affected=3)
        review_log.append(_make_entry(field="place", action="edited", source="human", raw_value="Berolini", canonical_value="berlin"))
        review_log.append(_make_entry(field="publisher", action="skipped", source="human", raw_value="Unknown", canonical_value=""))

    def test_filter_by_field(self, review_log: ReviewLog) -> None:
        self._populate(review_log)
        entries, total = review_log.get_history(field="place")
        assert total == 3
        assert all(e.field == "place" for e in entries)

    def test_filter_by_action(self, review_log: ReviewLog) -> None:
        self._populate(review_log)
        entries, total = review_log.get_history(action="approved")
        assert total == 2
        assert all(e.action == "approved" for e in entries)

    def test_filter_by_source(self, review_log: ReviewLog) -> None:
        self._populate(review_log)
        entries, total = review_log.get_history(source="agent")
        assert total == 2
        assert all(e.source == "agent" for e in entries)

    def test_combined_filters(self, review_log: ReviewLog) -> None:
        self._populate(review_log)
        entries, total = review_log.get_history(field="place", action="approved", source="human")
        assert total == 1
        assert entries[0].raw_value == "Parisiis"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    def test_limit(self, review_log: ReviewLog) -> None:
        for i in range(10):
            review_log.append(_make_entry(raw_value=f"val_{i}"))

        entries, total = review_log.get_history(limit=3)
        assert total == 10
        assert len(entries) == 3
        assert entries[0].raw_value == "val_0"

    def test_offset(self, review_log: ReviewLog) -> None:
        for i in range(10):
            review_log.append(_make_entry(raw_value=f"val_{i}"))

        entries, total = review_log.get_history(limit=3, offset=5)
        assert total == 10
        assert len(entries) == 3
        assert entries[0].raw_value == "val_5"
        assert entries[2].raw_value == "val_7"

    def test_offset_past_end(self, review_log: ReviewLog) -> None:
        for i in range(5):
            review_log.append(_make_entry(raw_value=f"val_{i}"))

        entries, total = review_log.get_history(limit=10, offset=100)
        assert total == 5
        assert len(entries) == 0

    def test_pagination_with_filter(self, review_log: ReviewLog) -> None:
        for i in range(8):
            action = "approved" if i % 2 == 0 else "rejected"
            review_log.append(_make_entry(raw_value=f"val_{i}", action=action))

        entries, total = review_log.get_history(action="approved", limit=2, offset=1)
        assert total == 4  # 4 approved entries total
        assert len(entries) == 2
        assert entries[0].raw_value == "val_2"  # second approved entry


# ---------------------------------------------------------------------------
# Rejected-signal queries
# ---------------------------------------------------------------------------


class TestRejectedSignal:
    def test_get_rejected_returns_only_rejected(self, review_log: ReviewLog) -> None:
        review_log.append_approved(field="place", raw_value="Parisiis", canonical_value="paris")
        review_log.append_rejected(field="place", raw_value="Amstel.", canonical_value="amsterdam")
        review_log.append_rejected(field="publisher", raw_value="Unknown", canonical_value="unknown_pub")

        rejected = review_log.get_rejected()
        assert len(rejected) == 2
        assert all(e.action == "rejected" for e in rejected)

    def test_get_rejected_filtered_by_field(self, review_log: ReviewLog) -> None:
        review_log.append_rejected(field="place", raw_value="Amstel.", canonical_value="amsterdam")
        review_log.append_rejected(field="publisher", raw_value="Unknown", canonical_value="unknown_pub")

        rejected = review_log.get_rejected(field="place")
        assert len(rejected) == 1
        assert rejected[0].field == "place"

    def test_is_rejected_true(self, review_log: ReviewLog) -> None:
        review_log.append_rejected(field="place", raw_value="Amstel.", canonical_value="amsterdam")

        assert review_log.is_rejected("place", "Amstel.") is True

    def test_is_rejected_false_for_approved(self, review_log: ReviewLog) -> None:
        review_log.append_approved(field="place", raw_value="Parisiis", canonical_value="paris")

        assert review_log.is_rejected("place", "Parisiis") is False

    def test_is_rejected_false_for_missing(self, review_log: ReviewLog) -> None:
        assert review_log.is_rejected("place", "never_seen") is False

    def test_is_rejected_field_specific(self, review_log: ReviewLog) -> None:
        """Rejection in one field does not affect another field."""
        review_log.append_rejected(field="place", raw_value="Amstel.", canonical_value="amsterdam")

        assert review_log.is_rejected("place", "Amstel.") is True
        assert review_log.is_rejected("publisher", "Amstel.") is False


# ---------------------------------------------------------------------------
# Aggregation counters
# ---------------------------------------------------------------------------


class TestAggregation:
    def _populate(self, review_log: ReviewLog) -> None:
        review_log.append_approved(field="place", raw_value="Parisiis", canonical_value="paris", source="human")
        review_log.append_rejected(field="place", raw_value="Amstel.", canonical_value="amsterdam", source="agent")
        review_log.append_approved(field="publisher", raw_value="Elsevier:", canonical_value="elsevier", source="agent")
        review_log.append(_make_entry(field="place", action="edited", source="human"))
        review_log.append(_make_entry(field="publisher", action="skipped", source="human"))

    def test_count_by_action(self, review_log: ReviewLog) -> None:
        self._populate(review_log)
        counts = review_log.count_by_action()
        assert counts == {"approved": 2, "rejected": 1, "edited": 1, "skipped": 1}

    def test_count_by_field(self, review_log: ReviewLog) -> None:
        self._populate(review_log)
        counts = review_log.count_by_field()
        assert counts == {"place": 3, "publisher": 2}

    def test_count_by_source(self, review_log: ReviewLog) -> None:
        self._populate(review_log)
        counts = review_log.count_by_source()
        assert counts == {"human": 3, "agent": 2}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_log_no_file(self, log_path: Path) -> None:
        """ReviewLog gracefully handles a non-existent file."""
        rl = ReviewLog(log_path)
        entries, total = rl.get_history()
        assert total == 0
        assert entries == []
        assert rl.get_rejected() == []
        assert rl.is_rejected("place", "anything") is False
        assert rl.count_by_action() == {}
        assert rl.count_by_field() == {}
        assert rl.count_by_source() == {}

    def test_empty_log_empty_file(self, log_path: Path) -> None:
        """ReviewLog handles an existing but empty file."""
        log_path.touch()
        rl = ReviewLog(log_path)
        entries, total = rl.get_history()
        assert total == 0
        assert entries == []

    def test_malformed_line_skipped(self, log_path: Path) -> None:
        """Malformed JSON lines are skipped; valid lines still parsed."""
        good_entry = _make_entry()
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": good_entry.timestamp, "field": "place",
                                "raw_value": "ok", "canonical_value": "ok",
                                "evidence": "", "source": "human",
                                "action": "approved", "records_affected": 0}) + "\n")
            f.write("NOT VALID JSON\n")
            f.write('{"incomplete": true}\n')  # missing required fields
            f.write(json.dumps({"timestamp": good_entry.timestamp, "field": "publisher",
                                "raw_value": "also_ok", "canonical_value": "also_ok",
                                "evidence": "", "source": "agent",
                                "action": "rejected", "records_affected": 0}) + "\n")

        rl = ReviewLog(log_path)
        entries, total = rl.get_history()
        assert total == 2
        assert entries[0].raw_value == "ok"
        assert entries[1].raw_value == "also_ok"

    def test_parent_directory_created(self, tmp_path: Path) -> None:
        """ReviewLog creates parent dirs if they don't exist."""
        deep_path = tmp_path / "a" / "b" / "c" / "log.jsonl"
        rl = ReviewLog(deep_path)
        rl.append_approved(field="place", raw_value="test", canonical_value="test")
        assert deep_path.exists()


# ---------------------------------------------------------------------------
# Interleaved multi-entry scenarios
# ---------------------------------------------------------------------------


class TestInterleaved:
    def test_interleaved_approved_rejected(self, review_log: ReviewLog) -> None:
        """Mixed approved/rejected entries for the same field, different raw values."""
        review_log.append_approved(field="place", raw_value="Parisiis", canonical_value="paris")
        review_log.append_rejected(field="place", raw_value="Amstel.", canonical_value="amsterdam")
        review_log.append_approved(field="place", raw_value="Londini", canonical_value="london")
        review_log.append_rejected(field="place", raw_value="Berl.", canonical_value="berlin")

        # Approved entries
        approved, total_a = review_log.get_history(field="place", action="approved")
        assert total_a == 2
        assert {e.raw_value for e in approved} == {"Parisiis", "Londini"}

        # Rejected entries
        rejected = review_log.get_rejected(field="place")
        assert len(rejected) == 2
        assert {e.raw_value for e in rejected} == {"Amstel.", "Berl."}

        # is_rejected checks
        assert review_log.is_rejected("place", "Amstel.") is True
        assert review_log.is_rejected("place", "Parisiis") is False

    def test_same_raw_value_approved_then_rejected(self, review_log: ReviewLog) -> None:
        """A value approved first, then rejected later -- is_rejected returns True."""
        review_log.append_approved(field="place", raw_value="Amstel.", canonical_value="amsterdam")
        review_log.append_rejected(field="place", raw_value="Amstel.", canonical_value="amsterdam")

        assert review_log.is_rejected("place", "Amstel.") is True

    def test_multi_field_multi_source(self, review_log: ReviewLog) -> None:
        """Entries across multiple fields and sources aggregate correctly."""
        review_log.append_approved(field="place", raw_value="Parisiis", canonical_value="paris", source="human", records_affected=10)
        review_log.append_approved(field="publisher", raw_value="Elsevier:", canonical_value="elsevier", source="agent", records_affected=5)
        review_log.append_rejected(field="place", raw_value="Amstel.", canonical_value="amsterdam", source="agent")
        review_log.append(_make_entry(field="agent", action="edited", source="human"))
        review_log.append(_make_entry(field="publisher", action="skipped", source="human"))

        assert review_log.count_by_action() == {"approved": 2, "rejected": 1, "edited": 1, "skipped": 1}
        assert review_log.count_by_field() == {"place": 2, "publisher": 2, "agent": 1}
        assert review_log.count_by_source() == {"human": 3, "agent": 2}
