"""
Fix 15: Expand Wikidata Role Inference

For agents with role_method='missing_role' (706 agents), check if they have an
authority_uri linking to authority_enrichment with person_info containing
occupations. Map those occupations to bibliographic roles.

Follows the same pattern as existing wikidata_occupation_direct and
wikidata_occupation_semantic role methods, but uses a broader mapping to
capture more occupation terms.

Raw values (role_raw) are preserved as-is.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("data/index/bibliographic.db")
ARCHIVE_DIR = Path("data/archive/data-quality-2026-04-02")
FIX_LOG = Path("data/qa/fix-log.jsonl")
FIX_ID = "fix_15_expand_wikidata_role_inference"

# Occupation keywords -> bibliographic role mapping.
# Each key is a substring to match (case-insensitive) in occupation strings.
# Order matters: first match wins.
OCCUPATION_TO_ROLE: list[tuple[list[str], str]] = [
    # printer / typographer / publisher
    (["printer", "typographer", "publisher", "printing", "type designer",
      "book publisher", "type_designer"], "printer"),
    # author / writer / poet
    (["author", "writer", "poet", "novelist", "playwright", "essayist",
      "lyricist", "screenwriter", "dramatist", "librettist",
      "literary critic", "biographer"], "author"),
    # translator
    (["translator", "dragoman", "interpreter"], "translator"),
    # editor / lexicographer
    (["editor", "lexicographer", "redactor", "compiler",
      "encyclopedist"], "editor"),
    # illustrator / engraver / artist
    (["illustrator", "engraver", "etcher", "lithographer", "wood engraver",
      "wood_engraver", "printmaker", "graphic artist",
      "calligrapher", "miniaturist"], "illustrator"),
    # bookseller / book dealer
    (["bookseller", "book dealer", "book_dealer", "bookman",
      "book trader", "antiquarian"], "bookseller"),
]

# Broader/weaker mappings for semantic inference (lower confidence)
SEMANTIC_OCCUPATION_TO_ROLE: list[tuple[list[str], str]] = [
    (["artist", "painter", "sculptor", "draftsman", "draughtsman",
      "designer", "goldsmith", "silversmith"], "illustrator"),
    (["scholar", "philosopher", "theologian", "rabbi", "historian",
      "professor", "academic", "teacher", "researcher", "scientist",
      "mathematician", "physician", "jurist", "lawyer", "clergyman",
      "cleric", "monk", "preacher"], "author"),
    (["curator", "archivist", "librarian", "bibliographer",
      "collector", "patron"], "editor"),
    (["cartographer", "map maker", "geographer",
      "surveyor", "photographer"], "illustrator"),
]


def find_candidates(conn: sqlite3.Connection) -> list[dict]:
    """Find agents with missing_role that have enrichment data."""
    cur = conn.execute(
        """
        SELECT a.id, a.record_id, a.agent_raw, a.agent_norm, a.authority_uri,
               a.role_raw, a.role_norm, a.role_method, a.role_confidence,
               r.mms_id
        FROM agents a
        JOIN records r ON r.id = a.record_id
        WHERE a.role_method = 'missing_role'
        ORDER BY a.id
        """
    )
    return [
        {
            "agent_id": row[0],
            "record_id": row[1],
            "agent_raw": row[2],
            "agent_norm": row[3],
            "authority_uri": row[4],
            "role_raw": row[5],
            "role_norm_old": row[6],
            "role_method_old": row[7],
            "role_confidence_old": row[8],
            "mms_id": row[9],
        }
        for row in cur.fetchall()
    ]


def get_enrichment_occupations(conn: sqlite3.Connection, authority_uri: str) -> list[str]:
    """Get occupations from authority_enrichment person_info for a URI."""
    if not authority_uri:
        return []
    cur = conn.execute(
        "SELECT person_info FROM authority_enrichment WHERE authority_uri = ?",
        (authority_uri,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return []
    try:
        info = json.loads(row[0])
        occupations = info.get("occupations", [])
        return [str(o).lower() for o in occupations if o]
    except (json.JSONDecodeError, TypeError):
        return []


def match_occupation_to_role(
    occupations: list[str],
    mapping: list[tuple[list[str], str]],
) -> str | None:
    """Map a list of occupations to a bibliographic role using keyword matching."""
    for occ in occupations:
        occ_lower = occ.lower()
        for keywords, role in mapping:
            for kw in keywords:
                if kw in occ_lower:
                    return role
    return None


def analyze_candidates(
    conn: sqlite3.Connection, candidates: list[dict]
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Classify candidates into:
    - direct_matches: occupation directly maps to role (high confidence)
    - semantic_matches: occupation semantically maps (lower confidence)
    - no_match: no enrichment or no occupation match
    """
    direct = []
    semantic = []
    no_match = []

    for cand in candidates:
        occupations = get_enrichment_occupations(conn, cand["authority_uri"])
        if not occupations:
            no_match.append(cand)
            continue

        # Try direct mapping first
        role = match_occupation_to_role(occupations, OCCUPATION_TO_ROLE)
        if role:
            direct.append({
                **cand,
                "new_role": role,
                "method": "wikidata_occupation_expanded",
                "confidence": 0.75,
                "occupations": occupations,
            })
            continue

        # Try semantic mapping
        role = match_occupation_to_role(occupations, SEMANTIC_OCCUPATION_TO_ROLE)
        if role:
            semantic.append({
                **cand,
                "new_role": role,
                "method": "wikidata_occupation_expanded",
                "confidence": 0.55,
                "occupations": occupations,
            })
            continue

        no_match.append({**cand, "occupations": occupations})

    return direct, semantic, no_match


def archive_state(
    direct: list[dict], semantic: list[dict], no_match: list[dict],
    archive_dir: Path,
) -> Path:
    """Archive original state before modifications."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{FIX_ID}_archive.json"

    def slim(items: list[dict]) -> list[dict]:
        """Keep only essential fields for archive."""
        return [
            {k: v for k, v in item.items()
             if k in ("agent_id", "agent_norm", "role_norm_old",
                       "role_method_old", "role_confidence_old",
                       "mms_id", "new_role", "method", "confidence",
                       "occupations")}
            for item in items
        ]

    payload = {
        "fix_id": FIX_ID,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "direct_count": len(direct),
        "semantic_count": len(semantic),
        "no_match_count": len(no_match),
        "direct": slim(direct),
        "semantic": slim(semantic),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def apply_fixes(
    conn: sqlite3.Connection,
    matches: list[dict],
) -> int:
    """Update role_norm, role_method, role_confidence for matched agents."""
    count = 0
    for m in matches:
        conn.execute(
            """
            UPDATE agents
            SET role_norm = ?,
                role_method = ?,
                role_confidence = ?
            WHERE id = ? AND role_method = 'missing_role'
            """,
            (m["new_role"], m["method"], m["confidence"], m["agent_id"]),
        )
        count += 1
    conn.commit()
    return count


def append_fix_log(
    direct: list[dict], semantic: list[dict],
    no_match_count: int, applied: int,
) -> None:
    """Append one JSONL entry to the fix log."""
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)

    # Role distribution
    role_dist: dict[str, int] = {}
    for m in direct + semantic:
        r = m["new_role"]
        role_dist[r] = role_dist.get(r, 0) + 1

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Expand role inference for missing_role agents via Wikidata occupations",
        "direct_matches": len(direct),
        "semantic_matches": len(semantic),
        "no_match": no_match_count,
        "agents_updated": applied,
        "role_distribution": role_dist,
        "fields_changed": ["role_norm", "role_method", "role_confidence"],
        "method": "wikidata_occupation_expanded",
    }
    with open(FIX_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report only, no DB changes")
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: Database not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(args.db_path))
    try:
        candidates = find_candidates(conn)
        print(f"[{FIX_ID}] Found {len(candidates)} agents with role_method='missing_role'")

        with_uri = sum(1 for c in candidates if c["authority_uri"])
        print(f"  With authority_uri: {with_uri}")
        print(f"  Without authority_uri: {len(candidates) - with_uri}")

        direct, semantic, no_match = analyze_candidates(conn, candidates)

        print(f"\n[{FIX_ID}] Analysis results:")
        print(f"  Direct occupation match: {len(direct)}")
        print(f"  Semantic occupation match: {len(semantic)}")
        print(f"  No match (no enrichment or unrecognized): {len(no_match)}")

        # Show role distribution
        role_dist: dict[str, int] = {}
        for m in direct + semantic:
            r = m["new_role"]
            role_dist[r] = role_dist.get(r, 0) + 1
        print("\n  Role distribution of matches:")
        for role, cnt in sorted(role_dist.items(), key=lambda x: -x[1]):
            print(f"    {role:<20s} {cnt:>4d}")

        # Show samples
        print("\n  Sample direct matches:")
        for m in direct[:5]:
            occs = ", ".join(m["occupations"][:3])
            print(f"    {m['agent_norm']!r} -> {m['new_role']} "
                  f"(occupations: {occs})")

        print("\n  Sample semantic matches:")
        for m in semantic[:5]:
            occs = ", ".join(m["occupations"][:3])
            print(f"    {m['agent_norm']!r} -> {m['new_role']} "
                  f"(occupations: {occs})")

        all_matches = direct + semantic
        if not all_matches:
            print(f"\n[{FIX_ID}] No matches found. Nothing to update.")
            return

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN -- would update {len(all_matches)} agents.")
            return

        archive_path = archive_state(direct, semantic, no_match, ARCHIVE_DIR)
        print(f"\n[{FIX_ID}] Archived state to {archive_path}")

        applied = apply_fixes(conn, all_matches)
        print(f"[{FIX_ID}] Updated {applied} agent rows.")

        append_fix_log(direct, semantic, len(no_match), applied)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
