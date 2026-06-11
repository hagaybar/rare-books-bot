"""FTS parity check (issue #9): verify the search index matches its source.

Contentless FTS cannot be content-audited, so this checks what CAN be
checked deterministically:
1. Row-count parity: COUNT(subjects) == COUNT(subjects_fts) and
   COUNT(titles) == titles_fts row count.
2. Round-trip sampling: for a stratified sample of source rows (including
   Hebrew value_he rows), an exact-phrase MATCH on the row's own text must
   return that rowid.

Run after every QA fix script and before every deploy.sh --update-db.
Exit code 0 = in sync; 1 = desync detected (each problem printed).

Usage:
    poetry run python scripts/qa/fts_parity_check.py [--db PATH] [--sample N]
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def _phrase(text: str) -> str:
    """First few tokens of ``text`` as a quoted FTS5 phrase."""
    tokens = [t for t in text.replace('"', " ").split() if t][:3]
    return '"' + " ".join(tokens) + '"' if tokens else ""


def check_parity(db_path: Path, sample: int = 200) -> list[str]:
    """Return a list of problem descriptions (empty list = in sync)."""
    problems: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        n_subjects = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        n_subjects_fts = conn.execute("SELECT COUNT(*) FROM subjects_fts").fetchone()[0]
        if n_subjects != n_subjects_fts:
            problems.append(
                f"count mismatch: subjects={n_subjects} subjects_fts={n_subjects_fts}"
            )

        n_titles = conn.execute("SELECT COUNT(*) FROM titles").fetchone()[0]
        n_titles_fts = conn.execute("SELECT COUNT(*) FROM titles_fts").fetchone()[0]
        if n_titles != n_titles_fts:
            problems.append(
                f"count mismatch: titles={n_titles} titles_fts={n_titles_fts}"
            )

        # Round-trip samples: half plain, half with Hebrew value_he
        half = max(sample // 2, 1)
        rows = conn.execute(
            "SELECT id, value, value_he FROM subjects "
            "WHERE value_he IS NOT NULL AND value_he != '' "
            f"ORDER BY id % 97, id LIMIT {half}"
        ).fetchall()
        rows += conn.execute(
            "SELECT id, value, NULL FROM subjects "
            f"ORDER BY id % 89, id LIMIT {half}"
        ).fetchall()
        for sid, value, value_he in rows:
            probe = _phrase(value_he or value)
            if not probe:
                continue
            hit = conn.execute(
                "SELECT 1 FROM subjects_fts WHERE subjects_fts MATCH ? AND rowid = ?",
                (probe, sid),
            ).fetchone()
            if hit is None:
                problems.append(f"subjects row {sid} not findable via {probe!r}")

        rows = conn.execute(
            f"SELECT id, value FROM titles ORDER BY id % 83, id LIMIT {half}"
        ).fetchall()
        for tid, value in rows:
            probe = _phrase(value)
            if not probe:
                continue
            hit = conn.execute(
                "SELECT 1 FROM titles_fts WHERE titles_fts MATCH ? AND rowid = ?",
                (probe, tid),
            ).fetchone()
            if hit is None:
                problems.append(f"titles row {tid} not findable via {probe!r}")
    finally:
        conn.close()
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--sample", type=int, default=200)
    args = parser.parse_args()
    problems = check_parity(args.db, args.sample)
    if problems:
        for p in problems[:20]:
            print(f"DESYNC: {p}", file=sys.stderr)
        print(f"FTS parity check FAILED ({len(problems)} problems)", file=sys.stderr)
        raise SystemExit(1)
    print("FTS parity check OK")


if __name__ == "__main__":
    main()
