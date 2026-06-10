"""Verify externally-claimed citations against bibliographic.db (issue #2 D10).

External tools (ChatGPT etc.) may cite real titles with fabricated MMS IDs.
This harness cross-checks each claimed (title, mms_id) pair:

  verified                 — the mms_id exists AND one of its titles matches
  id_fabricated_title_real — the title exists in the collection but under
                             different mms_id(s); the claimed id does not
                             match it (fabricated or wrong)
  id_real_title_mismatch   — the mms_id exists but none of its titles match
  not_found                — neither the id nor the title is in the collection

Usage:
    python scripts/qa/verify_external_citations.py \
        --claims data/qa/external_claims/2026-06-10-chatgpt-cartography.json \
        --db data/index/bibliographic.db [--out report.json]

Claims file format: [{"title": "...", "mms_id": "..."}, ...]
"""
import argparse
import json
import sqlite3
from pathlib import Path

_TITLE_PROBE_LEN = 40


def _norm_title(title: str) -> str:
    """Whitespace-collapsed, LIKE-escaped probe prefix of a claimed title."""
    collapsed = " ".join(title.split())
    probe = collapsed[:_TITLE_PROBE_LEN]
    return probe.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _title_match_ids(conn: sqlite3.Connection, title: str) -> list:
    probe = _norm_title(title)
    rows = conn.execute(
        "SELECT DISTINCT r.mms_id FROM records r "
        "JOIN titles t ON t.record_id = r.id "
        "WHERE LOWER(t.value) LIKE '%' || LOWER(?) || '%' ESCAPE '\\' "
        "ORDER BY r.mms_id",
        (probe,),
    ).fetchall()
    return [row[0] for row in rows]


def verify_claim(title: str, mms_id: str, db_path: Path) -> dict:
    """Verify a single (title, mms_id) claim. Returns a result dict."""
    conn = sqlite3.connect(str(db_path))
    try:
        id_exists = (
            conn.execute(
                "SELECT 1 FROM records WHERE mms_id = ?", (mms_id,)
            ).fetchone()
            is not None
        )
        title_ids = _title_match_ids(conn, title)

        if id_exists and mms_id in title_ids:
            status = "verified"
        elif title_ids:
            status = "id_fabricated_title_real"
        elif id_exists:
            status = "id_real_title_mismatch"
        else:
            status = "not_found"

        return {
            "claimed_title": title,
            "claimed_mms_id": mms_id,
            "status": status,
            "id_exists": id_exists,
            "real_mms_ids": title_ids,
        }
    finally:
        conn.close()


def verify_claims(claims: list, db_path: Path) -> dict:
    """Verify a batch of claims; returns {results: [...], summary: {...}}."""
    results = [verify_claim(c["title"], c["mms_id"], db_path) for c in claims]
    summary: dict = {"total": len(results)}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    return {"results": results, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    claims = json.loads(args.claims.read_text(encoding="utf-8"))
    report = verify_claims(claims, args.db)

    for r in report["results"]:
        print(f"[{r['status']:>26}] {r['claimed_mms_id']}  {r['claimed_title'][:60]}")
        if r["status"] == "id_fabricated_title_real":
            print(f"{'':>30}real id(s): {', '.join(r['real_mms_ids'])}")
    print(f"\nSummary: {json.dumps(report['summary'], ensure_ascii=False)}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
