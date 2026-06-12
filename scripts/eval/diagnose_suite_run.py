"""Deterministic triage of a diagnostic-suite run against the gold suite.

Compares each test's actual artifacts (from run_diagnostic_suite.py) with
the gold expectations and emits a per-test triage verdict with machine-
checkable flags. Qualitative root-cause analysis happens downstream; this
script only surfaces deviations.

Usage:
    python3 scripts/eval/diagnose_suite_run.py data/runs/diagnostic_suite_20260612
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

GOLD_PATH = Path("data/eval/gold_standard_diagnostic_suite.json")


def check(test: dict, actual: dict) -> dict:
    flags: list[str] = []
    exp_plan = test["expected_m3_plan"]
    exp_ev = test["expected_m4_evidence"]
    outcome = actual.get("outcome")

    # --- errors first
    if "interpreter_error" in actual:
        return {"verdict": "ERROR", "flags": [f"interpreter_error: {actual['interpreter_error']}"]}
    if "executor_error" in actual:
        return {"verdict": "ERROR", "flags": [f"executor_error: {actual['executor_error']}"]}

    # --- clarification expectations
    exp_clar = exp_plan.get("clarification_expected", False)
    if exp_clar and outcome != "clarification":
        flags.append(
            f"INTENT-GAP: expected clarification, got outcome={outcome} "
            f"(count={actual.get('total_record_count')})"
        )
    if not exp_clar and outcome == "clarification":
        # only a deviation if no acceptable_alternative allows execution
        flags.append(
            "INTENT-GAP?: clarified instead of executing: "
            + str(actual.get("clarification_text"))[:160]
        )
    if outcome == "clarification":
        return {"verdict": "CLARIFIED", "flags": flags,
                "clarification": actual.get("clarification_text")}

    # --- gather actual filters across retrieve steps
    actual_filters = []
    relaxations = []
    for s in actual.get("steps", []):
        d = s.get("data", {})
        if d.get("type") == "RecordSet":
            actual_filters.extend(d.get("filters_applied") or [])
            relaxations.extend(d.get("relaxations") or [])
    actual_filters = [f for f in actual_filters if isinstance(f, dict) and "field" in f]
    actual_fields = {f["field"] for f in actual_filters}

    # --- expected filters present?
    for ef in exp_plan.get("filters", []):
        if ef["field"] not in actual_fields:
            flags.append(f"INTENT-GAP: expected filter on '{ef['field']}' missing "
                         f"(actual fields: {sorted(actual_fields) or 'none'})")
    # negation preserved?
    for ef in exp_plan.get("filters", []):
        if ef.get("negate"):
            neg_ok = any(f["field"] == ef["field"] and f.get("negate")
                         for f in actual_filters)
            if not neg_ok:
                flags.append(f"INTENT-GAP: negation on '{ef['field']}' dropped")

    # --- count window
    total = actual.get("total_record_count")
    ec = exp_ev.get("expected_count", {})
    lo = ec.get("min", ec.get("exact", ec.get("approx")))
    hi = ec.get("max", ec.get("exact"))
    if ec.get("approx") is not None:
        tol = ec.get("tolerance", 0)
        lo, hi = ec["approx"] - tol, ec["approx"] + tol
    if total is not None:
        if lo is not None and total < lo:
            flags.append(f"COUNT: {total} below expected min {lo}")
        if hi is not None and total > hi:
            flags.append(f"COUNT: {total} above expected max {hi}")

    # --- evidence audit
    audits = actual.get("actual_m4_evidence", [])
    all_sources: list[str] = []
    null_value_evidence = 0
    extraction_failures = 0
    confidence_anomalies = []
    for audit in audits:
        for cand in audit.get("evidence_sample", []):
            for ev in cand.get("evidence", []):
                src = ev.get("source", "")
                all_sources.append(src)
                if ev.get("value") is None and not ev.get("extraction_error"):
                    null_value_evidence += 1
                if ev.get("extraction_error") or src == "extraction_failed":
                    extraction_failures += 1
                # false-high audit: agents are uniformly 0.8/base_clean in this DB
                if (ev.get("field", "").startswith("agent")
                        and ev.get("confidence") is not None
                        and ev["confidence"] >= 0.90):
                    confidence_anomalies.append(
                        f"{ev['field']}={ev['confidence']}")

    for forbidden in exp_ev.get("forbidden_sources", []):
        hits = [s for s in all_sources if forbidden in s]
        if hits:
            flags.append(f"EVIDENCE-GAP: forbidden source '{forbidden}' present ({len(hits)}x)")
    for req in exp_ev.get("required_sources", []):
        if all_sources and not any(req in s for s in all_sources):
            flags.append(f"EVIDENCE-GAP: required source '{req}' absent "
                         f"(saw: {sorted(set(all_sources))[:4]})")
    if null_value_evidence:
        flags.append(f"SILENT-NULL: {null_value_evidence} evidence objects with value=null and no error")
    if extraction_failures:
        flags.append(f"EVIDENCE-GAP: {extraction_failures} evidence extraction failures")
    if confidence_anomalies:
        flags.append(f"FALSE-HIGH: agent confidence >=0.90: {confidence_anomalies[:3]}")

    # --- relaxation honesty: relaxations recorded but expectation says none
    if relaxations and "none" in str(exp_ev.get("relaxations", "")):
        flags.append(f"RELAXATION: ladder fired on hard-only query: {relaxations[:2]}")

    verdict = "PASS" if not flags else "DEVIATION"
    return {"verdict": verdict, "flags": flags,
            "total": total, "relaxations": relaxations,
            "actual_fields": sorted(actual_fields)}


def main() -> None:
    run_dir = Path(sys.argv[1])
    gold = {t["test_id"]: t
            for t in json.loads(GOLD_PATH.read_text(encoding="utf-8"))["test_cases"]}
    combined = json.loads((run_dir / "_combined.json").read_text(encoding="utf-8"))

    report = {}
    for actual in combined:
        tid = actual["test_id"]
        report[tid] = check(gold[tid], actual)

    out = run_dir / "_triage.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for tid, r in report.items():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        marker = {"PASS": " ", "CLARIFIED": "C", "DEVIATION": "!", "ERROR": "X"}[r["verdict"]]
        print(f"[{marker}] {tid}: {r['verdict']}"
              + (f" | total={r.get('total')}" if r.get("total") is not None else ""))
        for fl in r["flags"]:
            print(f"      - {fl}")
    print(f"\nSummary: {counts}")
    print(f"Triage written to {out}")


if __name__ == "__main__":
    main()
