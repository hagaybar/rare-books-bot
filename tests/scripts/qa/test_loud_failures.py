"""Issue #55 HIGH cluster: five silent fallbacks become loud, honest failures.

One test class per fix:
1. MARC whole-file parse failure -> error log in data/runs/ + raise (never 0 records)
2. db_adapter alias-availability probe -> transient errors are not cached as 'disabled'
3. narrator meta extraction -> None + explicit reason, never a fabricated 0.85
4. feedback_loop correction apply -> DB errors surface, never collapse into "0 rows"
5. concept_bridge missing/malformed map -> logger.warning once (visible disablement)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


# =========================================================================
# Fix 1: MARC whole-file parse failure is loud
# =========================================================================


class TestMarcParseFailureIsLoud:
    """parse_marc_xml_file must log to data/runs/ AND raise on total parse failure."""

    def _write_bad_xml(self, tmp_path: Path) -> Path:
        bad_xml = tmp_path / "bad.xml"
        bad_xml.write_text("this is not <xml at all", encoding="utf-8")
        return bad_xml

    def test_parse_failure_raises_marc_parse_error(self, tmp_path: Path):
        from scripts.marc.parse import MarcParseError, parse_marc_xml_file

        bad_xml = self._write_bad_xml(tmp_path)
        out = tmp_path / "records.jsonl"
        runs_dir = tmp_path / "runs"

        with pytest.raises(MarcParseError):
            parse_marc_xml_file(bad_xml, out, runs_dir=runs_dir)

        # Must NOT proceed: no empty canonical JSONL written
        assert not out.exists()

    def test_parse_failure_writes_timestamped_error_log(self, tmp_path: Path):
        from scripts.marc.parse import MarcParseError, parse_marc_xml_file

        bad_xml = self._write_bad_xml(tmp_path)
        runs_dir = tmp_path / "runs"

        with pytest.raises(MarcParseError):
            parse_marc_xml_file(bad_xml, tmp_path / "out.jsonl", runs_dir=runs_dir)

        logs = list(runs_dir.glob("marc_parse_failure_*.json"))
        assert len(logs) == 1, "expected exactly one timestamped error log in runs dir"
        payload = json.loads(logs[0].read_text(encoding="utf-8"))
        assert payload["source_file"] == "bad.xml"
        assert payload["error"]  # non-empty error description
        assert payload["traceback"]

    def test_rebuild_pipeline_m1_surfaces_failure(self, tmp_path: Path, monkeypatch, capsys):
        from scripts.marc.rebuild_pipeline import run_m1_parse

        monkeypatch.chdir(tmp_path)  # default runs dir (data/runs) lands in tmp
        bad_xml = self._write_bad_xml(tmp_path)

        ok = run_m1_parse(bad_xml, tmp_path / "out.jsonl", tmp_path / "report.json")

        assert ok is False
        captured = capsys.readouterr()
        assert "ERROR" in captured.out or "ERROR" in captured.err

    def test_cli_parse_marc_exits_with_error(self, tmp_path: Path, monkeypatch):
        from typer.testing import CliRunner

        from app.cli import app

        monkeypatch.chdir(tmp_path)
        bad_xml = self._write_bad_xml(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "parse-marc",
                str(bad_xml),
                "-o",
                str(tmp_path / "out.jsonl"),
                "-r",
                str(tmp_path / "report.json"),
            ],
        )

        assert result.exit_code == 1
        assert "error" in result.output.lower()


# =========================================================================
# Fix 2: alias-expansion availability probe re-probes after transient errors
# =========================================================================


class _FailingConn:
    """Connection stub whose execute always raises (simulates transient DB error)."""

    def execute(self, *args, **kwargs):
        raise sqlite3.OperationalError("database is locked")


class TestAliasProbeNotCachedOnError:
    """A transient probe error must not cache 'disabled' for process lifetime."""

    @pytest.fixture(autouse=True)
    def _fresh_cache(self):
        from scripts.query.db_adapter import reset_agent_alias_cache

        reset_agent_alias_cache()
        yield
        reset_agent_alias_cache()

    def test_transient_error_returns_false_but_does_not_cache(self, caplog):
        from scripts.query import db_adapter
        from scripts.query.db_adapter import _agent_alias_tables_exist

        with caplog.at_level(logging.WARNING, logger="scripts.query.db_adapter"):
            assert _agent_alias_tables_exist(_FailingConn()) is False

        # The error must NOT be cached as a definitive negative
        assert db_adapter._agent_alias_tables_present is None
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "transient probe failure must log a warning"
        assert "alias" in warnings[0].getMessage().lower()

    def test_reprobe_after_transient_error_detects_tables(self):
        from scripts.query import db_adapter
        from scripts.query.db_adapter import _agent_alias_tables_exist

        assert _agent_alias_tables_exist(_FailingConn()) is False

        good = sqlite3.connect(":memory:")
        good.execute("CREATE TABLE agent_aliases (id INTEGER)")
        good.execute("CREATE TABLE agent_authorities (id INTEGER)")

        assert _agent_alias_tables_exist(good) is True
        assert db_adapter._agent_alias_tables_present is True
        good.close()

    def test_only_positive_detection_is_cached(self):
        from scripts.query import db_adapter
        from scripts.query.db_adapter import _agent_alias_tables_exist

        empty = sqlite3.connect(":memory:")  # probe succeeds, tables absent
        assert _agent_alias_tables_exist(empty) is False
        # Honest negative is re-probed on next call too (cache only positives)
        assert db_adapter._agent_alias_tables_present is None
        empty.close()


# =========================================================================
# Fix 3: narrator meta extraction never fabricates confidence
# =========================================================================


class TestNarratorMetaHonesty:
    """Meta-extraction failure must yield None + explicit reason, not 0.85."""

    def test_meta_extraction_failure_returns_none_with_reason(self):
        from scripts.chat.narrator import _extract_streaming_meta

        with patch(
            "scripts.chat.narrator.structured_completion",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            confidence, reason = asyncio.run(_extract_streaming_meta("a query", "a narrative"))

        assert confidence is None
        assert reason is not None and "meta_extraction_failed" in reason

    def test_meta_extraction_success_returns_value_and_no_reason(self):
        from scripts.chat.narrator import StreamingMetaLLM, _extract_streaming_meta

        fake_result = type("R", (), {"parsed": StreamingMetaLLM(confidence=0.7)})()
        with patch(
            "scripts.chat.narrator.structured_completion",
            new=AsyncMock(return_value=fake_result),
        ):
            confidence, reason = asyncio.run(_extract_streaming_meta("a query", "a narrative"))

        assert confidence == 0.7
        assert reason is None

    def test_scholar_response_accepts_none_confidence(self):
        from scripts.chat.plan_models import GroundingData, ScholarResponse

        resp = ScholarResponse(narrative="x", grounding=GroundingData(), confidence=None)
        assert resp.confidence is None

    def test_streaming_response_carries_none_and_reason(self):
        from scripts.chat.narrator import narrate_streaming
        from scripts.chat.plan_models import ExecutionResult, GroundingData

        exec_result = ExecutionResult(
            steps_completed=[],
            directives=[],
            grounding=GroundingData(),
            original_query="q",
        )

        async def noop_cb(chunk: str) -> None:
            pass

        with (
            patch(
                "scripts.chat.narrator._stream_llm",
                new=AsyncMock(return_value="narrative text"),
            ),
            patch(
                "scripts.chat.narrator.structured_completion",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            resp = asyncio.run(narrate_streaming("q", exec_result, noop_cb, model="test-model"))

        assert resp.confidence is None
        assert "meta_extraction_failed" in resp.metadata.get("confidence_reason", "")


# =========================================================================
# Fix 4: correction apply surfaces DB errors (never collapsed into 0 rows)
# =========================================================================


class TestCorrectionApplyLoud:
    """A DB exception during re-normalization must surface, not return 0."""

    def _make_loop(self, tmp_path: Path):
        from scripts.metadata.feedback_loop import FeedbackLoop

        return FeedbackLoop(
            db_path=tmp_path / "missing_dir" / "db.sqlite",  # unopenable
            alias_map_dir=tmp_path / "aliases",
            review_log_path=tmp_path / "review_log.jsonl",
        )

    def test_renormalize_raises_distinct_error_on_db_failure(self, tmp_path: Path):
        from scripts.metadata.feedback_loop import CorrectionApplyError

        loop = self._make_loop(tmp_path)
        with pytest.raises(CorrectionApplyError):
            loop._renormalize_records("place", "Paris :", "paris")

    def test_apply_correction_returns_failure_not_zero_rows(self, tmp_path: Path):
        loop = self._make_loop(tmp_path)
        result = loop.apply_correction("place", "lugduni batavorum", "leiden")

        assert result.success is False
        assert result.error, "DB failure must carry an explicit error message"
        # A failed apply must not be logged to the review log as approved
        review_log = tmp_path / "review_log.jsonl"
        if review_log.exists():
            entries = [json.loads(line) for line in review_log.read_text(encoding="utf-8").splitlines() if line.strip()]
            assert not any(e.get("action") == "approved" for e in entries)

    def test_apply_batch_surfaces_db_error_per_correction(self, tmp_path: Path):
        loop = self._make_loop(tmp_path)
        results = loop.apply_batch([{"field": "place", "raw_value": "Parisiis", "canonical_value": "paris"}])

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error


# =========================================================================
# Fix 5: concept bridge warns once when the map is missing/malformed
# =========================================================================


class TestConceptBridgeWarnsOnce:
    """Disabled concept expansion must be visible via a single warning."""

    @pytest.fixture(autouse=True)
    def _fresh_guard(self):
        from scripts.query import concept_bridge

        concept_bridge._warned_paths.clear()
        concept_bridge._load_raw.cache_clear()
        yield
        concept_bridge._warned_paths.clear()
        concept_bridge._load_raw.cache_clear()

    def test_missing_map_warns_once(self, tmp_path: Path, caplog):
        from scripts.query import concept_bridge

        missing = tmp_path / "no_such_map.json"
        with caplog.at_level(logging.WARNING, logger="scripts.query.concept_bridge"):
            assert concept_bridge.load_concept_map(missing) == {}
            assert concept_bridge.load_concept_map(missing) == {}
            assert concept_bridge.expand_concept("maps", missing) == []

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1, "must warn exactly once per map path"
        assert "concept" in warnings[0].getMessage().lower()

    def test_malformed_json_warns_once_and_disables(self, tmp_path: Path, caplog):
        from scripts.query import concept_bridge

        bad = tmp_path / "concept_map.json"
        bad.write_text("{this is not valid json", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="scripts.query.concept_bridge"):
            assert concept_bridge.load_concept_map(bad) == {}
            assert concept_bridge.expand_concept("maps", bad) == []

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1

    def test_missing_concepts_key_warns_once(self, tmp_path: Path, caplog):
        from scripts.query import concept_bridge

        bad = tmp_path / "concept_map.json"
        bad.write_text(json.dumps({"concpets": []}), encoding="utf-8")  # typo'd key

        with caplog.at_level(logging.WARNING, logger="scripts.query.concept_bridge"):
            assert concept_bridge.load_concept_map(bad) == {}
            assert concept_bridge.load_concept_map(bad) == {}

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1

    def test_valid_map_does_not_warn(self, tmp_path: Path, caplog):
        from scripts.query import concept_bridge

        good = tmp_path / "concept_map.json"
        good.write_text(
            json.dumps(
                {
                    "concepts": [
                        {
                            "canonical": "cartography",
                            "aliases": ["maps"],
                            "expansions": [{"field": "subject", "value": "Geography"}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="scripts.query.concept_bridge"):
            result = concept_bridge.load_concept_map(good)

        assert "maps" in result
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert not warnings
