"""End-to-end HITL feedback loop for the metadata quality workbench.

When a librarian approves a correction (e.g., "Lugduni Batavorum" -> "leiden"),
this module:
1. Writes the new mapping to the alias map JSON file (atomically)
2. Re-normalizes affected records in the database (incremental UPDATE)
3. Logs the change to a review log
4. Reports coverage improvement

No LLM calls.  All operations are deterministic and reversible.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CorrectionResult:
    """Outcome of applying a single correction."""

    field: str
    raw_value: str
    canonical_value: str
    records_updated: int
    alias_map_path: str
    success: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Map field name -> alias-map filename relative to alias_map_dir
_ALIAS_FILE_NAMES: Dict[str, str] = {
    "place": "place_aliases/place_alias_map.json",
    "publisher": "publisher_aliases/publisher_alias_map.json",
    "agent": "agent_aliases/agent_alias_map.json",
}

# Map field -> (table, raw_col, norm_col, confidence_col, method_col)
_UPDATE_MAP: Dict[str, tuple] = {
    "place": ("imprints", "place_raw", "place_norm", "place_confidence", "place_method"),
    "publisher": ("imprints", "publisher_raw", "publisher_norm", "publisher_confidence", "publisher_method"),
    "agent": ("agents", "agent_raw", "agent_norm", "agent_confidence", "agent_method"),
}

# Coverage query map: field -> (table, confidence_col)
_COVERAGE_MAP: Dict[str, tuple] = {
    "place": ("imprints", "place_confidence"),
    "publisher": ("imprints", "publisher_confidence"),
    "agent": ("agents", "agent_confidence"),
}


# ---------------------------------------------------------------------------
# FeedbackLoop
# ---------------------------------------------------------------------------

class FeedbackLoop:
    """End-to-end feedback loop: approve -> alias map -> re-normalize -> log."""

    def __init__(
        self,
        db_path: Path,
        alias_map_dir: Path,
        review_log_path: Optional[Path] = None,
    ):
        self.db_path = Path(db_path)
        self.alias_map_dir = Path(alias_map_dir)
        self.review_log_path = (
            Path(review_log_path) if review_log_path else Path("data/metadata/review_log.jsonl")
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_correction(
        self,
        field: str,
        raw_value: str,
        canonical_value: str,
        evidence: str = "",
        source: str = "human",
    ) -> CorrectionResult:
        """Apply a single correction end-to-end.

        1. Validate field name
        2. Write to alias map (atomic)
        3. Re-normalize affected records in DB (incremental UPDATE)
        4. Log to review_log.jsonl
        """
        if field not in _ALIAS_FILE_NAMES:
            return CorrectionResult(
                field=field,
                raw_value=raw_value,
                canonical_value=canonical_value,
                records_updated=0,
                alias_map_path="",
                success=False,
                error=f"Unknown field: {field}. Must be one of: {', '.join(sorted(_ALIAS_FILE_NAMES))}",
            )

        try:
            alias_path = self._write_to_alias_map(field, raw_value, canonical_value)
        except ValueError as exc:
            return CorrectionResult(
                field=field,
                raw_value=raw_value,
                canonical_value=canonical_value,
                records_updated=0,
                alias_map_path="",
                success=False,
                error=str(exc),
            )

        records_updated = self._renormalize_records(field, raw_value, canonical_value)

        self._log_correction(
            field=field,
            raw_value=raw_value,
            canonical_value=canonical_value,
            evidence=evidence,
            source=source,
            records_updated=records_updated,
        )

        return CorrectionResult(
            field=field,
            raw_value=raw_value,
            canonical_value=canonical_value,
            records_updated=records_updated,
            alias_map_path=str(alias_path),
            success=True,
        )

    def apply_batch(self, corrections: List[Dict]) -> List[CorrectionResult]:
        """Apply multiple corrections efficiently.

        Groups by field to minimise alias-map writes: the map is loaded once
        per field, all entries are added, then it is written back atomically.

        Each item in *corrections* must contain at minimum:
            field, raw_value, canonical_value
        Optional: evidence, source
        """
        # Group by field
        by_field: Dict[str, List[Dict]] = {}
        for corr in corrections:
            fld = corr.get("field", "")
            by_field.setdefault(fld, []).append(corr)

        results: List[CorrectionResult] = []

        for fld, group in by_field.items():
            if fld not in _ALIAS_FILE_NAMES:
                for corr in group:
                    results.append(CorrectionResult(
                        field=fld,
                        raw_value=corr.get("raw_value", ""),
                        canonical_value=corr.get("canonical_value", ""),
                        records_updated=0,
                        alias_map_path="",
                        success=False,
                        error=f"Unknown field: {fld}",
                    ))
                continue

            # Load alias map once for the whole group
            alias_path = self._alias_map_path(fld)
            alias_map = self._load_alias_map(alias_path)
            map_modified = False

            for corr in group:
                raw_val = corr.get("raw_value", "")
                canon_val = corr.get("canonical_value", "")
                evidence = corr.get("evidence", "")
                src = corr.get("source", "human")

                # Conflict check
                if raw_val in alias_map and alias_map[raw_val] != canon_val:
                    results.append(CorrectionResult(
                        field=fld,
                        raw_value=raw_val,
                        canonical_value=canon_val,
                        records_updated=0,
                        alias_map_path=str(alias_path),
                        success=False,
                        error=(
                            f"Conflict: '{raw_val}' already maps to "
                            f"'{alias_map[raw_val]}', cannot remap to '{canon_val}'"
                        ),
                    ))
                    continue

                # Duplicate check (already correct)
                if raw_val in alias_map and alias_map[raw_val] == canon_val:
                    updated = self._renormalize_records(fld, raw_val, canon_val)
                    self._log_correction(fld, raw_val, canon_val, evidence, src, updated)
                    results.append(CorrectionResult(
                        field=fld,
                        raw_value=raw_val,
                        canonical_value=canon_val,
                        records_updated=updated,
                        alias_map_path=str(alias_path),
                        success=True,
                    ))
                    continue

                alias_map[raw_val] = canon_val
                map_modified = True

                updated = self._renormalize_records(fld, raw_val, canon_val)
                self._log_correction(fld, raw_val, canon_val, evidence, src, updated)

                results.append(CorrectionResult(
                    field=fld,
                    raw_value=raw_val,
                    canonical_value=canon_val,
                    records_updated=updated,
                    alias_map_path=str(alias_path),
                    success=True,
                ))

            # Single atomic write per field
            if map_modified:
                self._save_alias_map_atomic(alias_path, alias_map)

        return results

    def get_pending_corrections(self) -> List[Dict]:
        """Read pending corrections from a queue file (if any).

        Looks for ``pending_corrections.json`` next to the review log.
        Returns an empty list if the file does not exist.
        """
        pending_path = self.review_log_path.parent / "pending_corrections.json"
        if not pending_path.exists():
            return []
        with open(pending_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    def get_coverage_delta(self, field: str) -> Dict:
        """Calculate coverage by confidence band for *field*.

        Returns a dict with keys:
            field, total, high (>=0.90), medium (0.50-0.89),
            low (0.01-0.49), missing (NULL or 0)
        """
        if field not in _COVERAGE_MAP:
            return {"field": field, "error": f"Unknown field: {field}"}

        table, conf_col = _COVERAGE_MAP[field]

        try:
            conn = sqlite3.connect(str(self.db_path))
            cur = conn.cursor()

            cur.execute(f"SELECT COUNT(*) FROM {table}")
            total = cur.fetchone()[0]

            cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {conf_col} >= 0.90"
            )
            high = cur.fetchone()[0]

            cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {conf_col} >= 0.50 AND {conf_col} < 0.90"
            )
            medium = cur.fetchone()[0]

            cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {conf_col} > 0 AND {conf_col} < 0.50"
            )
            low = cur.fetchone()[0]

            cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {conf_col} IS NULL OR {conf_col} = 0"
            )
            missing = cur.fetchone()[0]

            conn.close()

            return {
                "field": field,
                "total": total,
                "high": high,
                "medium": medium,
                "low": low,
                "missing": missing,
            }
        except Exception as exc:
            return {"field": field, "error": str(exc)}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _alias_map_path(self, field: str) -> Path:
        """Return the alias-map JSON path for *field*."""
        return self.alias_map_dir / _ALIAS_FILE_NAMES[field]

    @staticmethod
    def _load_alias_map(path: Path) -> dict:
        """Load an alias-map JSON file, returning empty dict if missing."""
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _save_alias_map_atomic(path: Path, alias_map: dict) -> None:
        """Write alias map to disk atomically (write .tmp then os.replace)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(alias_map, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)

    def _write_to_alias_map(self, field: str, raw_value: str, canonical_value: str) -> Path:
        """Atomic write of a single entry to the appropriate alias map.

        Returns the path of the alias-map file that was written.
        Raises ValueError on conflict (raw_value already mapped to a
        *different* canonical value).
        """
        alias_path = self._alias_map_path(field)
        alias_map = self._load_alias_map(alias_path)

        if raw_value in alias_map:
            existing = alias_map[raw_value]
            if existing != canonical_value:
                raise ValueError(
                    f"Conflict: '{raw_value}' already maps to '{existing}', "
                    f"cannot remap to '{canonical_value}'"
                )
            # Same mapping already exists - no-op, still return path
            return alias_path

        alias_map[raw_value] = canonical_value
        self._save_alias_map_atomic(alias_path, alias_map)
        return alias_path

    def _renormalize_records(
        self, field: str, raw_value: str, canonical_value: str
    ) -> int:
        """Incrementally update affected records in the M3 database.

        Instead of re-running the full pipeline, directly UPDATE the
        normalised columns for records whose raw value matches.

        For place/publisher the match is on the *raw* column (same column
        the pipeline populates from the MARC source).  For agents the match
        is on ``agent_raw``.

        Returns the count of updated rows.
        """
        if field not in _UPDATE_MAP:
            return 0

        table, raw_col, norm_col, conf_col, method_col = _UPDATE_MAP[field]

        method_value = f"{field}_alias_map_correction"

        try:
            conn = sqlite3.connect(str(self.db_path))
            cur = conn.cursor()
            cur.execute(
                f"UPDATE {table} "
                f"SET {norm_col} = ?, {conf_col} = 0.95, {method_col} = ? "
                f"WHERE {raw_col} = ?",
                (canonical_value, method_value, raw_value),
            )
            updated = cur.rowcount
            conn.commit()
            conn.close()
            return updated
        except Exception:
            return 0

    def _log_correction(
        self,
        field: str,
        raw_value: str,
        canonical_value: str,
        evidence: str,
        source: str,
        records_updated: int,
    ) -> None:
        """Append a structured entry to review_log.jsonl."""
        self.review_log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "field": field,
            "raw_value": raw_value,
            "canonical_value": canonical_value,
            "evidence": evidence,
            "source": source,
            "records_updated": records_updated,
            "action": "approved",
        }
        with open(self.review_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="HITL feedback loop: apply corrections, re-normalise, log.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Apply a single correction
  python -m scripts.metadata.feedback_loop \\
      --field place --raw "Lugduni Batavorum" --canonical leiden \\
      --db data/index/bibliographic.db

  # Apply all pending corrections from a file
  python -m scripts.metadata.feedback_loop \\
      --apply-pending pending_corrections.json \\
      --db data/index/bibliographic.db

  # Show coverage delta for a field
  python -m scripts.metadata.feedback_loop \\
      --coverage-delta place --db data/index/bibliographic.db
""",
    )

    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"),
                        help="Path to the M3 bibliographic SQLite database")
    parser.add_argument("--alias-dir", type=Path, default=Path("data/normalization"),
                        help="Root directory for alias-map JSON files")
    parser.add_argument("--review-log", type=Path, default=None,
                        help="Path to review_log.jsonl (default: data/metadata/review_log.jsonl)")

    # Single correction
    parser.add_argument("--field", type=str, help="Metadata field: place, publisher, agent")
    parser.add_argument("--raw", type=str, help="Raw value to map")
    parser.add_argument("--canonical", type=str, help="Canonical normalised value")
    parser.add_argument("--evidence", type=str, default="", help="Evidence / justification")
    parser.add_argument("--source", type=str, default="human", help="Source: human or agent")

    # Batch
    parser.add_argument("--apply-pending", type=Path, default=None,
                        help="Apply all corrections from a JSON file")

    # Coverage
    parser.add_argument("--coverage-delta", type=str, default=None,
                        help="Show coverage bands for the given field")

    args = parser.parse_args()

    loop = FeedbackLoop(
        db_path=args.db,
        alias_map_dir=args.alias_dir,
        review_log_path=args.review_log,
    )

    if args.coverage_delta:
        delta = loop.get_coverage_delta(args.coverage_delta)
        print(json.dumps(delta, indent=2))
        return

    if args.apply_pending:
        if not args.apply_pending.exists():
            print(f"ERROR: Pending file not found: {args.apply_pending}", file=sys.stderr)
            sys.exit(1)
        with open(args.apply_pending, "r", encoding="utf-8") as f:
            corrections = json.load(f)
        results = loop.apply_batch(corrections)
        for r in results:
            status = "OK" if r.success else f"FAIL: {r.error}"
            print(f"  [{status}] {r.field}: {r.raw_value!r} -> {r.canonical_value!r}  ({r.records_updated} records)")
        succeeded = sum(1 for r in results if r.success)
        print(f"\nApplied {succeeded}/{len(results)} corrections.")
        return

    if args.field and args.raw and args.canonical:
        result = loop.apply_correction(
            field=args.field,
            raw_value=args.raw,
            canonical_value=args.canonical,
            evidence=args.evidence,
            source=args.source,
        )
        if result.success:
            print(f"OK: {result.raw_value!r} -> {result.canonical_value!r}")
            print(f"  Records updated: {result.records_updated}")
            print(f"  Alias map: {result.alias_map_path}")
        else:
            print(f"FAIL: {result.error}", file=sys.stderr)
            sys.exit(1)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
