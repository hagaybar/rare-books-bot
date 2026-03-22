"""Normalization coverage audit for M3 bibliographic database.

Queries the SQLite database and produces a structured report showing
confidence distributions, normalization method breakdowns, and flagged
low-confidence values ranked by frequency.
"""

import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Confidence bands used for grouping
CONFIDENCE_BANDS: List[float] = [0.0, 0.5, 0.8, 0.95, 0.99]


@dataclass
class ConfidenceBand:
    """Count of records falling into a confidence band."""

    band_label: str  # e.g., "0.00", "0.50", "0.80", "0.95", "0.99"
    lower: float     # inclusive lower bound
    upper: float     # exclusive upper bound (except last band)
    count: int


@dataclass
class MethodBreakdown:
    """Count of records by normalization method."""

    method: str
    count: int


@dataclass
class LowConfidenceItem:
    """A single low-confidence value with its frequency."""

    raw_value: str
    norm_value: Optional[str]
    confidence: float
    method: Optional[str]
    frequency: int


@dataclass
class FieldCoverage:
    """Coverage stats for a single normalized field."""

    total_records: int
    non_null_count: int
    null_count: int
    confidence_distribution: List[ConfidenceBand]
    method_distribution: List[MethodBreakdown]
    flagged_items: List[LowConfidenceItem]


@dataclass
class CoverageReport:
    """Full normalization coverage report across all fields."""

    date_coverage: FieldCoverage
    place_coverage: FieldCoverage
    publisher_coverage: FieldCoverage
    agent_name_coverage: FieldCoverage
    agent_role_coverage: FieldCoverage
    total_imprint_rows: int
    total_agent_rows: int

    def to_dict(self) -> dict:
        """Serialize report to a plain dict."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _band_label(value: float) -> str:
    """Return the band label for a confidence value."""
    return f"{value:.2f}"


def _assign_band(confidence: float) -> str:
    """Assign a confidence value to its band label.

    Bands: [0.0, 0.5), [0.5, 0.8), [0.8, 0.95), [0.95, 0.99), [0.99, 1.0]
    """
    if confidence < 0.5:
        return _band_label(0.0)
    if confidence < 0.8:
        return _band_label(0.5)
    if confidence < 0.95:
        return _band_label(0.8)
    if confidence < 0.99:
        return _band_label(0.95)
    return _band_label(0.99)


def _build_confidence_distribution(
    rows: List[Tuple[Optional[float],]],
) -> List[ConfidenceBand]:
    """Build confidence distribution from raw confidence values.

    Args:
        rows: List of single-element tuples containing confidence values.
              None values are counted in the 0.0 band.

    Returns:
        List of ConfidenceBand in ascending order.
    """
    band_ranges = [
        ("0.00", 0.0, 0.5),
        ("0.50", 0.5, 0.8),
        ("0.80", 0.8, 0.95),
        ("0.95", 0.95, 0.99),
        ("0.99", 0.99, 1.01),  # inclusive upper for 1.0
    ]
    counts: Dict[str, int] = {label: 0 for label, _, _ in band_ranges}

    for (conf,) in rows:
        label = _assign_band(conf if conf is not None else 0.0)
        counts[label] += 1

    return [
        ConfidenceBand(band_label=label, lower=lo, upper=hi, count=counts[label])
        for label, lo, hi in band_ranges
    ]


def _query_method_distribution(
    conn: sqlite3.Connection,
    table: str,
    method_col: str,
) -> List[MethodBreakdown]:
    """Query method distribution from a table.

    Args:
        conn: SQLite connection.
        table: Table name (must be a known safe name).
        method_col: Method column name (must be a known safe name).

    Returns:
        List of MethodBreakdown sorted descending by count.
    """
    # Using allowlist instead of parameterized names because
    # SQLite does not support parameterized table/column names.
    _ALLOWED_TABLES = {"imprints", "agents"}
    _ALLOWED_COLS = {
        "date_method", "place_method", "publisher_method",
        "agent_method", "role_method",
    }
    if table not in _ALLOWED_TABLES or method_col not in _ALLOWED_COLS:
        raise ValueError(f"Invalid table/column: {table}.{method_col}")

    sql = f"SELECT {method_col}, COUNT(*) FROM {table} GROUP BY {method_col} ORDER BY COUNT(*) DESC"
    cursor = conn.execute(sql)
    return [
        MethodBreakdown(method=method or "NULL", count=cnt)
        for method, cnt in cursor.fetchall()
    ]


def _query_flagged_items(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
    limit: int = 100,
) -> List[LowConfidenceItem]:
    """Run a flagging query and return low-confidence items sorted by frequency.

    Args:
        conn: SQLite connection.
        sql: SQL query that returns (raw_value, norm_value, confidence, method, frequency).
        params: Query parameters.
        limit: Maximum number of items to return.

    Returns:
        List of LowConfidenceItem sorted by descending frequency.
    """
    cursor = conn.execute(sql, params)
    items = [
        LowConfidenceItem(
            raw_value=row[0] or "",
            norm_value=row[1],
            confidence=row[2] if row[2] is not None else 0.0,
            method=row[3],
            frequency=row[4],
        )
        for row in cursor.fetchall()
    ]
    items.sort(key=lambda x: x.frequency, reverse=True)
    return items[:limit]


# ---------------------------------------------------------------------------
# Per-field coverage builders
# ---------------------------------------------------------------------------

def build_date_coverage(conn: sqlite3.Connection) -> FieldCoverage:
    """Build coverage report for date normalization."""
    total = conn.execute("SELECT COUNT(*) FROM imprints").fetchone()[0]
    non_null = conn.execute(
        "SELECT COUNT(*) FROM imprints WHERE date_confidence IS NOT NULL"
    ).fetchone()[0]

    conf_rows = conn.execute(
        "SELECT date_confidence FROM imprints"
    ).fetchall()

    methods = _query_method_distribution(conn, "imprints", "date_method")

    flagged = _query_flagged_items(
        conn,
        """SELECT date_raw, CAST(date_start AS TEXT), date_confidence,
                  date_method, COUNT(*) AS freq
           FROM imprints
           WHERE date_method = 'unparsed' OR date_method = 'missing'
                 OR date_confidence IS NULL OR date_confidence <= 0.0
           GROUP BY date_raw
           ORDER BY freq DESC
           LIMIT 100""",
    )

    return FieldCoverage(
        total_records=total,
        non_null_count=non_null,
        null_count=total - non_null,
        confidence_distribution=_build_confidence_distribution(conf_rows),
        method_distribution=methods,
        flagged_items=flagged,
    )


def build_place_coverage(conn: sqlite3.Connection) -> FieldCoverage:
    """Build coverage report for place normalization."""
    total = conn.execute("SELECT COUNT(*) FROM imprints").fetchone()[0]
    non_null = conn.execute(
        "SELECT COUNT(*) FROM imprints WHERE place_confidence IS NOT NULL"
    ).fetchone()[0]

    conf_rows = conn.execute(
        "SELECT place_confidence FROM imprints"
    ).fetchall()

    methods = _query_method_distribution(conn, "imprints", "place_method")

    flagged = _query_flagged_items(
        conn,
        """SELECT place_raw, place_norm, place_confidence,
                  place_method, COUNT(*) AS freq
           FROM imprints
           WHERE place_confidence IS NULL OR place_confidence <= 0.80
           GROUP BY place_raw
           ORDER BY freq DESC
           LIMIT 100""",
    )

    return FieldCoverage(
        total_records=total,
        non_null_count=non_null,
        null_count=total - non_null,
        confidence_distribution=_build_confidence_distribution(conf_rows),
        method_distribution=methods,
        flagged_items=flagged,
    )


def build_publisher_coverage(conn: sqlite3.Connection) -> FieldCoverage:
    """Build coverage report for publisher normalization."""
    total = conn.execute("SELECT COUNT(*) FROM imprints").fetchone()[0]
    non_null = conn.execute(
        "SELECT COUNT(*) FROM imprints WHERE publisher_confidence IS NOT NULL"
    ).fetchone()[0]

    conf_rows = conn.execute(
        "SELECT publisher_confidence FROM imprints"
    ).fetchall()

    methods = _query_method_distribution(conn, "imprints", "publisher_method")

    flagged = _query_flagged_items(
        conn,
        """SELECT publisher_raw, publisher_norm, publisher_confidence,
                  publisher_method, COUNT(*) AS freq
           FROM imprints
           WHERE publisher_confidence IS NULL OR publisher_confidence <= 0.80
           GROUP BY publisher_raw
           ORDER BY freq DESC
           LIMIT 100""",
    )

    return FieldCoverage(
        total_records=total,
        non_null_count=non_null,
        null_count=total - non_null,
        confidence_distribution=_build_confidence_distribution(conf_rows),
        method_distribution=methods,
        flagged_items=flagged,
    )


def build_agent_name_coverage(conn: sqlite3.Connection) -> FieldCoverage:
    """Build coverage report for agent name normalization."""
    total = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    non_null = total  # agent_confidence is NOT NULL per schema

    conf_rows = conn.execute(
        "SELECT agent_confidence FROM agents"
    ).fetchall()

    methods = _query_method_distribution(conn, "agents", "agent_method")

    flagged = _query_flagged_items(
        conn,
        """SELECT agent_raw, agent_norm, agent_confidence,
                  agent_method, COUNT(*) AS freq
           FROM agents
           WHERE agent_method = 'ambiguous' OR agent_confidence <= 0.80
           GROUP BY agent_raw
           ORDER BY freq DESC
           LIMIT 100""",
    )

    return FieldCoverage(
        total_records=total,
        non_null_count=non_null,
        null_count=0,
        confidence_distribution=_build_confidence_distribution(conf_rows),
        method_distribution=methods,
        flagged_items=flagged,
    )


def build_agent_role_coverage(conn: sqlite3.Connection) -> FieldCoverage:
    """Build coverage report for agent role normalization."""
    total = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    non_null = total  # role_confidence is NOT NULL per schema

    conf_rows = conn.execute(
        "SELECT role_confidence FROM agents"
    ).fetchall()

    methods = _query_method_distribution(conn, "agents", "role_method")

    flagged = _query_flagged_items(
        conn,
        """SELECT role_raw, role_norm, role_confidence,
                  role_method, COUNT(*) AS freq
           FROM agents
           WHERE role_confidence < 0.80
           GROUP BY role_raw
           ORDER BY freq DESC
           LIMIT 100""",
    )

    return FieldCoverage(
        total_records=total,
        non_null_count=non_null,
        null_count=0,
        confidence_distribution=_build_confidence_distribution(conf_rows),
        method_distribution=methods,
        flagged_items=flagged,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_coverage_report(db_path: Path) -> CoverageReport:
    """Generate a full normalization coverage report from an M3 database.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        CoverageReport with per-field breakdowns.

    Raises:
        FileNotFoundError: If db_path does not exist.
        sqlite3.OperationalError: If required tables are missing.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        total_imprints = conn.execute("SELECT COUNT(*) FROM imprints").fetchone()[0]
        total_agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]

        return CoverageReport(
            date_coverage=build_date_coverage(conn),
            place_coverage=build_place_coverage(conn),
            publisher_coverage=build_publisher_coverage(conn),
            agent_name_coverage=build_agent_name_coverage(conn),
            agent_role_coverage=build_agent_role_coverage(conn),
            total_imprint_rows=total_imprints,
            total_agent_rows=total_agents,
        )
    finally:
        conn.close()


def _print_summary(report: CoverageReport) -> None:
    """Print a human-readable summary to stderr."""
    import sys

    def _pct(non_null: int, total: int) -> str:
        if total == 0:
            return "N/A"
        return f"{non_null / total * 100:.1f}%"

    def _coverage_line(label: str, fc: FieldCoverage) -> str:
        pct = _pct(fc.non_null_count, fc.total_records)
        return f"  {label:<20s}  {fc.non_null_count:>6d} / {fc.total_records:<6d}  ({pct})"

    w = sys.stderr.write

    w("\n=== Normalization Coverage Audit ===\n\n")
    w(f"Total imprint rows:  {report.total_imprint_rows}\n")
    w(f"Total agent rows:    {report.total_agent_rows}\n\n")

    w("--- Per-Field Coverage (non-null / total) ---\n")
    w(_coverage_line("date", report.date_coverage) + "\n")
    w(_coverage_line("place", report.place_coverage) + "\n")
    w(_coverage_line("publisher", report.publisher_coverage) + "\n")
    w(_coverage_line("agent_name", report.agent_name_coverage) + "\n")
    w(_coverage_line("agent_role", report.agent_role_coverage) + "\n")
    w("\n")

    # Confidence distribution summary
    w("--- Confidence Distribution ---\n")
    for label, fc in [
        ("date", report.date_coverage),
        ("place", report.place_coverage),
        ("publisher", report.publisher_coverage),
        ("agent_name", report.agent_name_coverage),
        ("agent_role", report.agent_role_coverage),
    ]:
        bands_str = "  ".join(
            f"[{b.band_label}]: {b.count}"
            for b in fc.confidence_distribution
        )
        w(f"  {label:<20s}  {bands_str}\n")
    w("\n")

    # Top flagged items per field
    w("--- Top Flagged Items (up to 5 per field) ---\n")
    for label, fc in [
        ("date", report.date_coverage),
        ("place", report.place_coverage),
        ("publisher", report.publisher_coverage),
        ("agent_name", report.agent_name_coverage),
        ("agent_role", report.agent_role_coverage),
    ]:
        if not fc.flagged_items:
            w(f"  {label}: (none)\n")
            continue
        w(f"  {label}:\n")
        for item in fc.flagged_items[:5]:
            w(f"    raw={item.raw_value!r}  norm={item.norm_value!r}  "
              f"conf={item.confidence:.2f}  method={item.method}  freq={item.frequency}\n")
    w("\n")


def generate_coverage_report_from_conn(conn: sqlite3.Connection) -> CoverageReport:
    """Generate a coverage report from an existing SQLite connection.

    Useful for testing with in-memory databases.

    Args:
        conn: Open SQLite connection to an M3 database.

    Returns:
        CoverageReport with per-field breakdowns.
    """
    total_imprints = conn.execute("SELECT COUNT(*) FROM imprints").fetchone()[0]
    total_agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]

    return CoverageReport(
        date_coverage=build_date_coverage(conn),
        place_coverage=build_place_coverage(conn),
        publisher_coverage=build_publisher_coverage(conn),
        agent_name_coverage=build_agent_name_coverage(conn),
        agent_role_coverage=build_agent_role_coverage(conn),
        total_imprint_rows=total_imprints,
        total_agent_rows=total_agents,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Run normalization coverage audit against a bibliographic SQLite database."
    )
    parser.add_argument(
        "db_path",
        type=str,
        help="Path to the SQLite bibliographic database.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path for JSON output file. Defaults to stdout if not specified.",
    )
    args = parser.parse_args()

    report = generate_coverage_report(Path(args.db_path))

    # Print human-readable summary to stderr
    _print_summary(report)

    # Serialize to JSON
    report_json = json.dumps(asdict(report), indent=2, ensure_ascii=False)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_json, encoding="utf-8")
        sys.stderr.write(f"JSON report written to: {out_path}\n")
    else:
        print(report_json)
