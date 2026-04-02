"""
Data Quality Checks for bibliographic.db

Runs all Tier 1 (zero-error target) and Tier 2 (gap analysis) checks,
outputs a JSON report and a formatted summary to stdout.

Usage:
    python -m scripts.qa.data_quality_checks
    python -m scripts.qa.data_quality_checks --db-path data/index/bibliographic.db --output-dir data/qa
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Known place -> country_code mappings (MARC country codes)
# Covers the most common places in the collection for cross-validation.
# ---------------------------------------------------------------------------
PLACE_COUNTRY_MAP: dict[str, set[str]] = {
    "amsterdam": {"ne"},
    "antwerp": {"be"},
    "augsburg": {"gw"},
    "basel": {"sz"},
    "berlin": {"gw"},
    "bologna": {"it"},
    "bordeaux": {"fr"},
    "breslau": {"gw", "pl"},
    "brussels": {"be"},
    "cambridge": {"enk", "mau"},
    "cologne": {"gw"},
    "constantinople": {"tu"},
    "copenhagen": {"dk"},
    "cracow": {"pl"},
    "dresden": {"gw"},
    "edinburgh": {"stk"},
    "ferrara": {"it"},
    "florence": {"it"},
    "frankfurt": {"gw"},
    "frankfurt am main": {"gw"},
    "frankfurt an der oder": {"gw"},
    "freiburg": {"gw"},
    "geneva": {"sz"},
    "genoa": {"it"},
    "hague": {"ne"},
    "the hague": {"ne"},
    "hamburg": {"gw"},
    "hanover": {"gw"},
    "heidelberg": {"gw"},
    "istanbul": {"tu"},
    "jerusalem": {"is"},
    "krakow": {"pl"},
    "leiden": {"ne"},
    "leipzig": {"gw"},
    "lisbon": {"po"},
    "livorno": {"it"},
    "london": {"enk"},
    "lublin": {"pl"},
    "lyon": {"fr"},
    "madrid": {"sp"},
    "mainz": {"gw"},
    "mantua": {"it"},
    "marseille": {"fr"},
    "milan": {"it"},
    "moscow": {"ru"},
    "munich": {"gw"},
    "naples": {"it"},
    "new york": {"nyu"},
    "nuremberg": {"gw"},
    "offenbach": {"gw"},
    "oxford": {"enk"},
    "padua": {"it"},
    "paris": {"fr"},
    "parma": {"it"},
    "philadelphia": {"pau"},
    "prague": {"xr"},
    "rome": {"it"},
    "rotterdam": {"ne"},
    "safed": {"is"},
    "salonika": {"gr"},
    "st. petersburg": {"ru"},
    "strasbourg": {"fr"},
    "stuttgart": {"gw"},
    "thessaloniki": {"gr"},
    "tiberias": {"is"},
    "tubingen": {"gw"},
    "turin": {"it"},
    "utrecht": {"ne"},
    "venice": {"it"},
    "verona": {"it"},
    "vienna": {"au"},
    "vilna": {"li", "ru"},
    "warsaw": {"pl"},
    "wittenberg": {"gw"},
    "worms": {"gw"},
    "zurich": {"sz"},
}

# Country names that should not appear as place_norm (place should be a city)
COUNTRY_NAMES: set[str] = {
    "afghanistan", "albania", "algeria", "argentina", "armenia", "australia",
    "austria", "azerbaijan", "bahrain", "bangladesh", "belarus", "belgium",
    "bolivia", "bosnia", "brazil", "bulgaria", "cambodia", "canada", "chile",
    "china", "colombia", "croatia", "cuba", "cyprus", "czech republic",
    "denmark", "egypt", "england", "estonia", "ethiopia", "finland", "france",
    "georgia", "germany", "greece", "holland", "hungary", "iceland", "india",
    "indonesia", "iran", "iraq", "ireland", "israel", "italy", "japan",
    "jordan", "kazakhstan", "kenya", "korea", "kuwait", "latvia", "lebanon",
    "libya", "lithuania", "luxembourg", "malaysia", "mexico", "moldova",
    "mongolia", "morocco", "nepal", "netherlands", "new zealand", "nigeria",
    "norway", "oman", "pakistan", "palestine", "peru", "philippines", "poland",
    "portugal", "qatar", "romania", "russia", "saudi arabia", "scotland",
    "serbia", "singapore", "slovakia", "slovenia", "south africa", "spain",
    "sudan", "sweden", "switzerland", "syria", "taiwan", "thailand",
    "tunisia", "turkey", "turkmenistan", "ukraine", "united kingdom",
    "united states", "uruguay", "uzbekistan", "venezuela", "vietnam", "wales",
    "yemen",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CheckError:
    """A single error found by a data quality check."""
    check: str
    mms_id: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"check": self.check, "mms_id": self.mms_id, "detail": self.detail}


@dataclass
class DimensionResult:
    """Result for a single Tier 1 dimension."""
    score: float = 1.0
    weight: float = 0.0
    errors: list[CheckError] = field(default_factory=list)
    total_checked: int = 0
    error_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 6),
            "weight": self.weight,
            "errors": [e.to_dict() for e in self.errors],
            "total_checked": self.total_checked,
            "error_count": self.error_count,
        }


def _has_hebrew(text: str) -> bool:
    """Return True if text contains Hebrew unicode characters."""
    return any("\u0590" <= ch <= "\u05FF" or "\uFB1D" <= ch <= "\uFB4F" for ch in text)


# ---------------------------------------------------------------------------
# Tier 1 checks
# ---------------------------------------------------------------------------

def check_date_accuracy(conn: sqlite3.Connection) -> DimensionResult:
    """Run all date accuracy checks."""
    cur = conn.cursor()
    result = DimensionResult(weight=0.20)
    errors: list[CheckError] = []

    # Total records with any imprint date data
    total = cur.execute(
        "SELECT COUNT(DISTINCT i.record_id) FROM imprints i"
    ).fetchone()[0]
    result.total_checked = total

    # 1. Impossible inversions: date_end < date_start
    rows = cur.execute("""
        SELECT r.mms_id, i.date_start, i.date_end
        FROM imprints i
        JOIN records r ON r.id = i.record_id
        WHERE i.date_end IS NOT NULL
          AND i.date_start IS NOT NULL
          AND i.date_end < i.date_start
    """).fetchall()
    for mms_id, ds, de in rows:
        errors.append(CheckError(
            check="impossible_inversion",
            mms_id=mms_id,
            detail=f"date_end ({de}) < date_start ({ds})",
        ))

    # 2. Out-of-scope dates
    rows = cur.execute("""
        SELECT r.mms_id, i.date_start
        FROM imprints i
        JOIN records r ON r.id = i.record_id
        WHERE i.date_start IS NOT NULL
          AND (i.date_start < 1400 OR i.date_start > 1950)
    """).fetchall()
    for mms_id, ds in rows:
        errors.append(CheckError(
            check="out_of_scope_date",
            mms_id=mms_id,
            detail=f"date_start = {ds}",
        ))

    # 3. Suspiciously wide ranges
    rows = cur.execute("""
        SELECT r.mms_id, i.date_start, i.date_end
        FROM imprints i
        JOIN records r ON r.id = i.record_id
        WHERE i.date_start IS NOT NULL
          AND i.date_end IS NOT NULL
          AND (i.date_end - i.date_start) > 100
    """).fetchall()
    for mms_id, ds, de in rows:
        errors.append(CheckError(
            check="wide_date_range",
            mms_id=mms_id,
            detail=f"range = {de - ds} years ({ds}-{de})",
        ))

    # 4. Hebrew gematria cross-validation
    # Same record has gematria and non-gematria imprints that disagree > 5 years
    rows = cur.execute("""
        SELECT r.mms_id,
               g.date_start AS gematria_start,
               n.date_start AS other_start,
               g.date_method AS g_method,
               n.date_method AS n_method
        FROM imprints g
        JOIN imprints n ON g.record_id = n.record_id
        JOIN records r ON r.id = g.record_id
        WHERE g.date_method LIKE '%gematria%'
          AND n.date_method NOT LIKE '%gematria%'
          AND n.date_method != 'missing'
          AND g.date_start IS NOT NULL
          AND n.date_start IS NOT NULL
          AND ABS(g.date_start - n.date_start) > 5
    """).fetchall()
    seen_gematria: set[str] = set()
    for mms_id, gs, ns, gm, nm in rows:
        if mms_id not in seen_gematria:
            seen_gematria.add(mms_id)
            errors.append(CheckError(
                check="gematria_disagreement",
                mms_id=mms_id,
                detail=f"gematria={gs} ({gm}) vs other={ns} ({nm}), diff={abs(gs - ns)}yr",
            ))

    # 5. Failed parses
    rows = cur.execute("""
        SELECT r.mms_id, i.date_raw
        FROM imprints i
        JOIN records r ON r.id = i.record_id
        WHERE i.date_raw IS NOT NULL
          AND i.date_raw != ''
          AND i.date_start IS NULL
    """).fetchall()
    for mms_id, dr in rows:
        errors.append(CheckError(
            check="failed_date_parse",
            mms_id=mms_id,
            detail=f"date_raw={dr!r}, date_start=NULL",
        ))

    # 6. Agent lifespan vs publication date
    # Find agents with enrichment birth/death years that conflict with imprint dates.
    # In a rare-books collection, posthumous reprints centuries later are normal
    # (e.g., Aristotle reprinted in 1600). We flag two truly suspicious patterns:
    #   a) Agent born after publication date (impossible link)
    #   b) Agent who died in the modern era (post-1700) linked to a publication
    #      more than 100 years after death (likely a misattribution, not a reprint
    #      of an ancient author)
    rows = cur.execute("""
        SELECT DISTINCT r.mms_id, a.agent_norm,
               ae.person_info, i.date_start
        FROM agents a
        JOIN records r ON r.id = a.record_id
        JOIN imprints i ON i.record_id = a.record_id
        JOIN authority_enrichment ae ON ae.authority_uri = a.authority_uri
        WHERE ae.person_info IS NOT NULL
          AND i.date_start IS NOT NULL
          AND a.authority_uri IS NOT NULL
    """).fetchall()
    seen_lifespan: set[tuple[str, str]] = set()
    for mms_id, agent_norm, person_info_str, pub_date in rows:
        try:
            pi = json.loads(person_info_str)
        except (json.JSONDecodeError, TypeError):
            continue
        death_year = pi.get("death_year")
        birth_year = pi.get("birth_year")
        key = (mms_id, agent_norm)
        if key in seen_lifespan:
            continue
        # Agent born after publication (with 5yr grace for date imprecision)
        if birth_year and isinstance(birth_year, (int, float)):
            if int(birth_year) > pub_date + 5:
                seen_lifespan.add(key)
                errors.append(CheckError(
                    check="agent_born_after_publication",
                    mms_id=mms_id,
                    detail=(
                        f"agent={agent_norm}, birth={int(birth_year)}, "
                        f"pub_date={pub_date}, born {int(birth_year) - pub_date}yr after publication"
                    ),
                ))
        # Modern agent died >100yr before publication (suspicious misattribution)
        if death_year and isinstance(death_year, (int, float)):
            dy = int(death_year)
            gap = pub_date - dy
            if dy >= 1700 and gap > 100:
                seen_lifespan.add(key)
                errors.append(CheckError(
                    check="agent_lifespan_conflict",
                    mms_id=mms_id,
                    detail=(
                        f"agent={agent_norm}, death={dy}, "
                        f"pub_date={pub_date}, gap={gap}yr (modern agent, suspicious)"
                    ),
                ))

    result.errors = errors
    result.error_count = len(errors)
    if total > 0:
        result.score = max(0.0, 1.0 - (len(errors) / total))
    return result


def check_place_accuracy(conn: sqlite3.Connection) -> DimensionResult:
    """Run all place accuracy checks."""
    cur = conn.cursor()
    result = DimensionResult(weight=0.20)
    errors: list[CheckError] = []

    total = cur.execute(
        "SELECT COUNT(*) FROM imprints WHERE place_norm IS NOT NULL AND place_norm != ''"
    ).fetchone()[0]
    result.total_checked = total

    # 1. place_norm vs country_code cross-validation
    rows = cur.execute("""
        SELECT r.mms_id, i.place_norm, i.country_code
        FROM imprints i
        JOIN records r ON r.id = i.record_id
        WHERE i.place_norm IS NOT NULL
          AND i.country_code IS NOT NULL
          AND i.place_norm != ''
          AND i.country_code != ''
    """).fetchall()
    for mms_id, place_norm, country_code in rows:
        pn_lower = place_norm.lower().strip()
        cc_lower = country_code.lower().strip()
        if pn_lower in PLACE_COUNTRY_MAP:
            expected = PLACE_COUNTRY_MAP[pn_lower]
            if cc_lower not in expected:
                errors.append(CheckError(
                    check="place_country_mismatch",
                    mms_id=mms_id,
                    detail=(
                        f"place_norm={place_norm!r}, country_code={country_code!r}, "
                        f"expected one of {expected}"
                    ),
                ))

    # 2. Country-name-as-place detection
    rows = cur.execute("""
        SELECT r.mms_id, i.place_norm
        FROM imprints i
        JOIN records r ON r.id = i.record_id
        WHERE i.place_norm IS NOT NULL AND i.place_norm != ''
    """).fetchall()
    for mms_id, place_norm in rows:
        if place_norm.lower().strip() in COUNTRY_NAMES:
            errors.append(CheckError(
                check="country_name_as_place",
                mms_id=mms_id,
                detail=f"place_norm={place_norm!r} is a country name, not a city",
            ))

    # 3. country_name column population
    populated = cur.execute(
        "SELECT COUNT(*) FROM imprints WHERE country_name IS NOT NULL AND country_name != ''"
    ).fetchone()[0]
    total_with_cc = cur.execute(
        "SELECT COUNT(*) FROM imprints WHERE country_code IS NOT NULL AND country_code != ''"
    ).fetchone()[0]
    if total_with_cc > 0 and populated == 0:
        errors.append(CheckError(
            check="country_name_unpopulated",
            mms_id="ALL",
            detail=f"0 of {total_with_cc} imprints with country_code have country_name populated",
        ))

    result.errors = errors
    result.error_count = len(errors)
    if total > 0:
        result.score = max(0.0, 1.0 - (len(errors) / total))
    return result


def check_agent_identity(conn: sqlite3.Connection) -> DimensionResult:
    """Run all agent identity checks."""
    cur = conn.cursor()
    result = DimensionResult(weight=0.25)
    errors: list[CheckError] = []

    total = cur.execute("SELECT COUNT(DISTINCT agent_norm) FROM agents").fetchone()[0]
    result.total_checked = total

    # 1. Multi-script fragmentation: same authority_uri -> multiple agent_norm values
    rows = cur.execute("""
        SELECT a.authority_uri, GROUP_CONCAT(DISTINCT a.agent_norm) AS norms,
               COUNT(DISTINCT a.agent_norm) AS cnt
        FROM agents a
        WHERE a.authority_uri IS NOT NULL AND a.authority_uri != ''
        GROUP BY a.authority_uri
        HAVING COUNT(DISTINCT a.agent_norm) > 1
    """).fetchall()
    for uri, norms, cnt in rows:
        # Get a sample mms_id for this authority_uri
        sample = cur.execute(
            "SELECT r.mms_id FROM agents a JOIN records r ON r.id = a.record_id "
            "WHERE a.authority_uri = ? LIMIT 1", (uri,)
        ).fetchone()
        mms_id = sample[0] if sample else "UNKNOWN"
        norms_list = norms.split(",") if norms else []
        truncated = norms_list[:5]
        errors.append(CheckError(
            check="multi_script_fragmentation",
            mms_id=mms_id,
            detail=(
                f"authority_uri has {cnt} distinct agent_norm values: "
                f"{', '.join(truncated)}"
                + (f" (and {cnt - 5} more)" if cnt > 5 else "")
            ),
        ))

    # 2. Bare first names (no comma, shorter than 6 chars)
    rows = cur.execute("""
        SELECT a.agent_norm, COUNT(*) AS cnt,
               (SELECT r.mms_id FROM records r WHERE r.id = a.record_id LIMIT 1) AS sample_mms
        FROM agents a
        WHERE a.agent_norm NOT LIKE '%,%'
          AND LENGTH(a.agent_norm) < 6
          AND a.agent_type = 'personal'
        GROUP BY a.agent_norm
        ORDER BY cnt DESC
    """).fetchall()
    for agent_norm, cnt, sample_mms in rows:
        errors.append(CheckError(
            check="bare_first_name",
            mms_id=sample_mms or "UNKNOWN",
            detail=f"agent_norm={agent_norm!r} ({cnt} records), no surname separator",
        ))

    # 3. Missing authority linkage: agent_norm not in agent_authorities
    rows = cur.execute("""
        SELECT a.agent_norm, COUNT(*) AS cnt, MIN(a.record_id) AS min_rid
        FROM agents a
        LEFT JOIN agent_authorities aa ON LOWER(a.agent_norm) = aa.canonical_name_lower
        WHERE aa.id IS NULL
        GROUP BY a.agent_norm
        ORDER BY cnt DESC
    """).fetchall()
    for agent_norm, cnt, min_rid in rows:
        sample_mms_row = cur.execute(
            "SELECT mms_id FROM records WHERE id = ?", (min_rid,)
        ).fetchone()
        sample_mms = sample_mms_row[0] if sample_mms_row else "UNKNOWN"
        errors.append(CheckError(
            check="missing_authority_linkage",
            mms_id=sample_mms,
            detail=f"agent_norm={agent_norm!r} ({cnt} agent rows) not in agent_authorities",
        ))

    # 4. Agent type conflicts: same agent_norm with different agent_types
    rows = cur.execute("""
        SELECT a.agent_norm, GROUP_CONCAT(DISTINCT a.agent_type) AS types,
               COUNT(DISTINCT a.agent_type) AS cnt,
               (SELECT r.mms_id FROM records r WHERE r.id = a.record_id LIMIT 1) AS sample_mms
        FROM agents a
        GROUP BY a.agent_norm
        HAVING COUNT(DISTINCT a.agent_type) > 1
    """).fetchall()
    for agent_norm, types, cnt, sample_mms in rows:
        errors.append(CheckError(
            check="agent_type_conflict",
            mms_id=sample_mms or "UNKNOWN",
            detail=f"agent_norm={agent_norm!r} has conflicting types: {types}",
        ))

    result.errors = errors
    result.error_count = len(errors)
    if total > 0:
        result.score = max(0.0, 1.0 - (len(errors) / total))
    return result


def check_publisher_identity(conn: sqlite3.Connection) -> DimensionResult:
    """Run all publisher identity checks."""
    cur = conn.cursor()
    result = DimensionResult(weight=0.15)
    errors: list[CheckError] = []

    # Total distinct normalized publishers with records
    total = cur.execute(
        "SELECT COUNT(DISTINCT publisher_norm) FROM imprints "
        "WHERE publisher_norm IS NOT NULL AND publisher_norm != ''"
    ).fetchone()[0]
    result.total_checked = total

    # 1. High-record-count publishers missing from publisher_authorities
    # A publisher is "in" publisher_authorities if their publisher_norm matches
    # a variant_form_lower in publisher_variants
    rows = cur.execute("""
        SELECT i.publisher_norm, COUNT(DISTINCT i.record_id) AS rec_count,
               (SELECT r.mms_id FROM records r WHERE r.id = i.record_id LIMIT 1) AS sample_mms
        FROM imprints i
        LEFT JOIN publisher_variants pv ON LOWER(i.publisher_norm) = pv.variant_form_lower
        WHERE i.publisher_norm IS NOT NULL
          AND i.publisher_norm != ''
          AND pv.id IS NULL
        GROUP BY i.publisher_norm
        HAVING COUNT(DISTINCT i.record_id) >= 3
        ORDER BY rec_count DESC
    """).fetchall()
    for pub_norm, rec_count, sample_mms in rows:
        errors.append(CheckError(
            check="publisher_missing_authority",
            mms_id=sample_mms or "UNKNOWN",
            detail=f"publisher_norm={pub_norm!r} ({rec_count} records) not in publisher_authorities",
        ))

    # 2. Unresearched authorities with records
    rows = cur.execute("""
        SELECT pa.canonical_name, pa.type,
               COUNT(DISTINCT i.record_id) AS rec_count,
               (SELECT r.mms_id FROM records r
                JOIN imprints i2 ON i2.record_id = r.id
                JOIN publisher_variants pv2 ON LOWER(i2.publisher_norm) = pv2.variant_form_lower
                WHERE pv2.authority_id = pa.id LIMIT 1) AS sample_mms
        FROM publisher_authorities pa
        JOIN publisher_variants pv ON pv.authority_id = pa.id
        JOIN imprints i ON LOWER(i.publisher_norm) = pv.variant_form_lower
        WHERE pa.type = 'unresearched'
        GROUP BY pa.id
        ORDER BY rec_count DESC
    """).fetchall()
    for canonical, ptype, rec_count, sample_mms in rows:
        errors.append(CheckError(
            check="unresearched_authority",
            mms_id=sample_mms or "UNKNOWN",
            detail=f"publisher={canonical!r} (type=unresearched, {rec_count} records)",
        ))

    result.errors = errors
    result.error_count = len(errors)
    if total > 0:
        result.score = max(0.0, 1.0 - (len(errors) / total))
    return result


def check_role_accuracy(conn: sqlite3.Connection) -> DimensionResult:
    """Run all role accuracy checks."""
    cur = conn.cursor()
    result = DimensionResult(weight=0.20)
    errors: list[CheckError] = []

    total = cur.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    result.total_checked = total

    # 1. Unmapped roles with trailing period in role_raw
    rows = cur.execute("""
        SELECT r.mms_id, a.role_raw, a.role_norm, a.role_method
        FROM agents a
        JOIN records r ON r.id = a.record_id
        WHERE a.role_method = 'unmapped'
          AND a.role_raw IS NOT NULL
          AND a.role_raw LIKE '%.'
    """).fetchall()
    for mms_id, role_raw, role_norm, role_method in rows:
        errors.append(CheckError(
            check="trailing_period_unmapped",
            mms_id=mms_id,
            detail=f"role_raw={role_raw!r} has trailing period, role_method=unmapped",
        ))

    # 2. Hebrew role terms in role_raw
    rows = cur.execute("""
        SELECT r.mms_id, a.role_raw, a.role_norm, a.role_method
        FROM agents a
        JOIN records r ON r.id = a.record_id
        WHERE a.role_method = 'unmapped'
          AND a.role_raw IS NOT NULL
    """).fetchall()
    for mms_id, role_raw, role_norm, role_method in rows:
        if _has_hebrew(role_raw):
            errors.append(CheckError(
                check="hebrew_role_unmapped",
                mms_id=mms_id,
                detail=f"role_raw={role_raw!r} contains Hebrew, role_method=unmapped",
            ))

    # 3. Valid MARC relator terms not in map (unmapped, no trailing period, no Hebrew)
    rows = cur.execute("""
        SELECT r.mms_id, a.role_raw, a.role_norm, a.role_method
        FROM agents a
        JOIN records r ON r.id = a.record_id
        WHERE a.role_method = 'unmapped'
          AND a.role_raw IS NOT NULL
          AND a.role_raw NOT LIKE '%.'
    """).fetchall()
    for mms_id, role_raw, role_norm, role_method in rows:
        if not _has_hebrew(role_raw):
            errors.append(CheckError(
                check="unmapped_relator_term",
                mms_id=mms_id,
                detail=f"role_raw={role_raw!r} not in relator map, role_method=unmapped",
            ))

    # 4. Missing roles
    rows = cur.execute("""
        SELECT r.mms_id, a.agent_norm, a.role_method
        FROM agents a
        JOIN records r ON r.id = a.record_id
        WHERE a.role_method = 'missing_role'
    """).fetchall()
    for mms_id, agent_norm, role_method in rows:
        errors.append(CheckError(
            check="missing_role",
            mms_id=mms_id,
            detail=f"agent={agent_norm!r}, role_method=missing_role",
        ))

    result.errors = errors
    result.error_count = len(errors)
    if total > 0:
        result.score = max(0.0, 1.0 - (len(errors) / total))
    return result


# ---------------------------------------------------------------------------
# Tier 2 checks (gap analysis)
# ---------------------------------------------------------------------------

def check_subject_coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    """Tier 2: Subject coverage gap analysis."""
    cur = conn.cursor()
    total_records = cur.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    records_with_subjects = cur.execute("""
        SELECT COUNT(DISTINCT s.record_id) FROM subjects s
    """).fetchone()[0]
    records_without_subjects = total_records - records_with_subjects

    # Scheme consistency
    scheme_counts = cur.execute("""
        SELECT scheme, COUNT(*) AS cnt
        FROM subjects
        WHERE scheme IS NOT NULL
        GROUP BY scheme
        ORDER BY cnt DESC
    """).fetchall()

    # Find NLI vs nli inconsistency
    nli_variants = {
        scheme: cnt for scheme, cnt in scheme_counts
        if scheme and scheme.lower() == "nli"
    }
    scheme_inconsistent = sum(cnt for s, cnt in nli_variants.items() if s != "nli")

    return {
        "total_records": total_records,
        "records_with_subjects": records_with_subjects,
        "records_without_subjects": records_without_subjects,
        "records_with_subjects_pct": round(records_with_subjects / max(total_records, 1), 4),
        "scheme_distribution": {s: c for s, c in scheme_counts},
        "scheme_inconsistent_count": scheme_inconsistent,
        "nli_variants": nli_variants,
    }


def check_record_completeness(conn: sqlite3.Connection) -> dict[str, Any]:
    """Tier 2: Record completeness gap analysis."""
    cur = conn.cursor()
    total = cur.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    missing_imprints = cur.execute("""
        SELECT COUNT(*) FROM records r
        WHERE NOT EXISTS (SELECT 1 FROM imprints i WHERE i.record_id = r.id)
    """).fetchone()[0]

    missing_agents = cur.execute("""
        SELECT COUNT(*) FROM records r
        WHERE NOT EXISTS (SELECT 1 FROM agents a WHERE a.record_id = r.id)
    """).fetchone()[0]

    missing_subjects = cur.execute("""
        SELECT COUNT(*) FROM records r
        WHERE NOT EXISTS (SELECT 1 FROM subjects s WHERE s.record_id = r.id)
    """).fetchone()[0]

    missing_language = cur.execute("""
        SELECT COUNT(*) FROM records r
        WHERE NOT EXISTS (SELECT 1 FROM languages l WHERE l.record_id = r.id)
    """).fetchone()[0]

    missing_physical = cur.execute("""
        SELECT COUNT(*) FROM records r
        WHERE NOT EXISTS (SELECT 1 FROM physical_descriptions pd WHERE pd.record_id = r.id)
    """).fetchone()[0]

    # Records with ALL key fields
    complete_records = cur.execute("""
        SELECT COUNT(*) FROM records r
        WHERE EXISTS (SELECT 1 FROM imprints i WHERE i.record_id = r.id)
          AND EXISTS (SELECT 1 FROM agents a WHERE a.record_id = r.id)
          AND EXISTS (SELECT 1 FROM subjects s WHERE s.record_id = r.id)
          AND EXISTS (SELECT 1 FROM languages l WHERE l.record_id = r.id)
    """).fetchone()[0]

    return {
        "total_records": total,
        "missing_imprints": missing_imprints,
        "missing_imprints_pct": round(missing_imprints / max(total, 1), 4),
        "missing_agents": missing_agents,
        "missing_agents_pct": round(missing_agents / max(total, 1), 4),
        "missing_subjects": missing_subjects,
        "missing_subjects_pct": round(missing_subjects / max(total, 1), 4),
        "missing_language": missing_language,
        "missing_language_pct": round(missing_language / max(total, 1), 4),
        "missing_physical_description": missing_physical,
        "missing_physical_description_pct": round(missing_physical / max(total, 1), 4),
        "complete_records": complete_records,
        "complete_records_pct": round(complete_records / max(total, 1), 4),
    }


def check_authority_enrichment(conn: sqlite3.Connection) -> dict[str, Any]:
    """Tier 2: Authority enrichment gap analysis."""
    cur = conn.cursor()

    # Agent enrichment
    total_unique_uris = cur.execute("""
        SELECT COUNT(DISTINCT authority_uri) FROM agents
        WHERE authority_uri IS NOT NULL AND authority_uri != ''
    """).fetchone()[0]

    enriched_uris = cur.execute("""
        SELECT COUNT(*) FROM authority_enrichment
    """).fetchone()[0]

    # Publisher enrichment
    total_pub_authorities = cur.execute(
        "SELECT COUNT(*) FROM publisher_authorities"
    ).fetchone()[0]

    researched_pub = cur.execute(
        "SELECT COUNT(*) FROM publisher_authorities WHERE type != 'unresearched'"
    ).fetchone()[0]

    unresearched_pub = cur.execute(
        "SELECT COUNT(*) FROM publisher_authorities WHERE type = 'unresearched'"
    ).fetchone()[0]

    return {
        "agent_unique_authority_uris": total_unique_uris,
        "agent_enriched_uris": enriched_uris,
        "agent_enrichment_pct": round(enriched_uris / max(total_unique_uris, 1), 4),
        "publisher_total_authorities": total_pub_authorities,
        "publisher_researched": researched_pub,
        "publisher_unresearched": unresearched_pub,
        "publisher_researched_pct": round(researched_pub / max(total_pub_authorities, 1), 4),
    }


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run_all_checks(db_path: str) -> dict[str, Any]:
    """Run all Tier 1 and Tier 2 checks, return full report dict."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = None
    try:
        record_count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]

        # Tier 1
        date_result = check_date_accuracy(conn)
        place_result = check_place_accuracy(conn)
        agent_result = check_agent_identity(conn)
        publisher_result = check_publisher_identity(conn)
        role_result = check_role_accuracy(conn)

        tier1 = {
            "date_accuracy": date_result,
            "place_accuracy": place_result,
            "agent_identity": agent_result,
            "publisher_identity": publisher_result,
            "role_accuracy": role_result,
        }

        # Weighted overall Tier 1 score
        overall = sum(d.score * d.weight for d in tier1.values())

        # Tier 2
        tier2 = {
            "subject_coverage": check_subject_coverage(conn),
            "record_completeness": check_record_completeness(conn),
            "authority_enrichment": check_authority_enrichment(conn),
        }

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "record_count": record_count,
            "tier1": {k: v.to_dict() for k, v in tier1.items()},
            "tier2": tier2,
            "overall_tier1_score": round(overall, 6),
        }
        return report

    finally:
        conn.close()


def print_summary(report: dict[str, Any]) -> None:
    """Print formatted summary table to stdout."""
    print()
    print("=" * 78)
    print(f"  DATA QUALITY REPORT  |  {report['record_count']} records  "
          f"|  {report['generated_at'][:19]}")
    print("=" * 78)

    # Tier 1
    print()
    print("  TIER 1 — Zero-Error Target")
    print("  " + "-" * 74)
    print(f"  {'Dimension':<25} {'Score':>8} {'Weight':>8} "
          f"{'Errors':>8} {'Checked':>10}")
    print("  " + "-" * 74)

    for dim_name, dim in report["tier1"].items():
        label = dim_name.replace("_", " ").title()
        score_str = f"{dim['score']:.4f}"
        print(f"  {label:<25} {score_str:>8} {dim['weight']:>8.2f} "
              f"{dim['error_count']:>8} {dim['total_checked']:>10}")

    print("  " + "-" * 74)
    print(f"  {'OVERALL TIER 1 SCORE':<25} {report['overall_tier1_score']:>8.4f}")
    print()

    # Tier 2
    print("  TIER 2 — Gap Analysis")
    print("  " + "-" * 74)

    sc = report["tier2"]["subject_coverage"]
    print(f"  Subject Coverage")
    print(f"    Records with subjects:     {sc['records_with_subjects']:>6} / {sc['total_records']}"
          f"  ({sc['records_with_subjects_pct']:.1%})")
    print(f"    Scheme inconsistencies:    {sc['scheme_inconsistent_count']:>6}")

    rc = report["tier2"]["record_completeness"]
    print(f"  Record Completeness")
    print(f"    Missing imprints:          {rc['missing_imprints']:>6}  ({rc['missing_imprints_pct']:.1%})")
    print(f"    Missing agents:            {rc['missing_agents']:>6}  ({rc['missing_agents_pct']:.1%})")
    print(f"    Missing subjects:          {rc['missing_subjects']:>6}  ({rc['missing_subjects_pct']:.1%})")
    print(f"    Missing language:          {rc['missing_language']:>6}  ({rc['missing_language_pct']:.1%})")
    print(f"    Missing phys. desc:        {rc['missing_physical_description']:>6}"
          f"  ({rc['missing_physical_description_pct']:.1%})")
    print(f"    Fully complete records:    {rc['complete_records']:>6}  ({rc['complete_records_pct']:.1%})")

    ae = report["tier2"]["authority_enrichment"]
    print(f"  Authority Enrichment")
    print(f"    Agent URIs enriched:       {ae['agent_enriched_uris']:>6} / {ae['agent_unique_authority_uris']}"
          f"  ({ae['agent_enrichment_pct']:.1%})")
    print(f"    Publishers researched:     {ae['publisher_researched']:>6} / {ae['publisher_total_authorities']}"
          f"  ({ae['publisher_researched_pct']:.1%})")

    print()
    print("  " + "=" * 74)

    # Top errors per dimension (limit 5 per dimension)
    print()
    print("  TOP ERRORS BY DIMENSION (first 5 per dimension)")
    print("  " + "-" * 74)
    for dim_name, dim in report["tier1"].items():
        if dim["error_count"] == 0:
            continue
        label = dim_name.replace("_", " ").title()
        print(f"\n  [{label}] — {dim['error_count']} errors")
        # Group by check type first
        by_check: dict[str, int] = {}
        for e in dim["errors"]:
            by_check[e["check"]] = by_check.get(e["check"], 0) + 1
        for check_name, cnt in sorted(by_check.items(), key=lambda x: -x[1]):
            print(f"    {check_name}: {cnt}")
        # Show first 5 individual errors
        for e in dim["errors"][:5]:
            print(f"      {e['mms_id']}: {e['detail'][:80]}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run data quality checks on bibliographic.db"
    )
    parser.add_argument(
        "--db-path",
        default="data/index/bibliographic.db",
        help="Path to SQLite database (default: data/index/bibliographic.db)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/qa",
        help="Directory for JSON report output (default: data/qa)",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running data quality checks on {db_path} ...")
    report = run_all_checks(str(db_path))

    output_file = output_dir / "data-quality-report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Report written to {output_file}")

    print_summary(report)


if __name__ == "__main__":
    main()
