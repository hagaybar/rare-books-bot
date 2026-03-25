"""Wikipedia connection discovery engine.

Cross-references Wikipedia wikilinks and categories against the agent
collection to discover relationships invisible to Wikidata and MARC data.

Algorithm
---------
1. Build lookup tables: wikipedia_title -> wikidata_id -> agent_norm
2. For each agent's wikilinks, match titles via QID (not name)
3. Score: see_also=0.85, body_link=0.75, category=0.65, bidirectional=0.90
4. Canonical ordering: source_agent_norm < target_agent_norm (alphabetically)
5. Detect bidirectional mentions and boost confidence
6. Optionally store to wikipedia_connections table

Usage
-----
    from scripts.enrichment.wikipedia_connections import discover_connections
    conns = discover_connections(Path("data/index/bibliographic.db"), store=True)
"""

import csv
import difflib
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Category patterns to filter out (maintenance categories, not substantive)
_BROAD_CATEGORY_RE = re.compile(
    r"^("
    r"Articles|All |CS1|Pages|Webarchive|Use |Short description|"
    r"Living people|AC with|Wikipedia|Wikidata|Commons|Harv and Sfn|"
    r"Stub|Good articles|Featured articles|Spoken articles"
    r")",
    re.IGNORECASE,
)


# =============================================================================
# Data classes
# =============================================================================


@dataclass
class AgentLookup:
    """Lookup tables for matching Wikipedia titles to collection agents."""

    title_to_qid: dict[str, str]  # wikipedia_title_lower -> wikidata_id
    qid_to_agent: dict[str, str]  # wikidata_id -> agent_norm
    all_agent_norms: set[str]  # All agent_norms including un-enriched


@dataclass
class DiscoveredConnection:
    """A discovered connection between two agents via Wikipedia data."""

    source_agent_norm: str
    target_agent_norm: str
    source_wikidata_id: str | None
    target_wikidata_id: str | None
    relationship: str | None
    tags: list[str]
    confidence: float
    source_type: str  # "wikilink", "see_also", "category"
    evidence: str | None
    bidirectional: bool = False


@dataclass
class CandidateLinkage:
    """A potential link between a Wikipedia title and an un-enriched agent."""

    wikipedia_title: str
    mentioned_in_agent: str
    possible_agent_norm: str | None
    match_score: float


# =============================================================================
# Lookup builder
# =============================================================================


def build_agent_lookup(db_path: Path) -> AgentLookup:
    """Build lookup tables from authority_enrichment + wikipedia_cache + agents.

    Returns AgentLookup with:
    - title_to_qid: lowercase wikipedia_title -> wikidata_id (from wikipedia_cache)
    - qid_to_agent: wikidata_id -> agent_norm (from authority_enrichment + agents)
    - all_agent_norms: all distinct agent_norm values (including un-enriched)
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # 1. wikipedia_title -> wikidata_id from wikipedia_cache
    title_to_qid: dict[str, str] = {}
    rows = conn.execute(
        "SELECT wikipedia_title, wikidata_id FROM wikipedia_cache "
        "WHERE wikipedia_title IS NOT NULL"
    ).fetchall()
    for row in rows:
        title_lower = row["wikipedia_title"].lower()
        title_to_qid[title_lower] = row["wikidata_id"]

    # 2. wikidata_id -> agent_norm via authority_enrichment + agents
    #    Use DISTINCT agent_norm; when multiple exist per QID, pick first alphabetically
    qid_to_agent: dict[str, str] = {}
    rows = conn.execute(
        """
        SELECT ae.wikidata_id, MIN(a.agent_norm) as agent_norm
        FROM authority_enrichment ae
        JOIN agents a ON a.authority_uri = ae.authority_uri
        WHERE ae.wikidata_id IS NOT NULL AND a.agent_norm IS NOT NULL
        GROUP BY ae.wikidata_id
        """
    ).fetchall()
    for row in rows:
        qid_to_agent[row["wikidata_id"]] = row["agent_norm"]

    # 3. All distinct agent_norms (including un-enriched)
    all_norms_rows = conn.execute(
        "SELECT DISTINCT agent_norm FROM agents WHERE agent_norm IS NOT NULL"
    ).fetchall()
    all_agent_norms = {row["agent_norm"] for row in all_norms_rows}

    conn.close()

    logger.info(
        "Agent lookup built: %d title->qid, %d qid->agent, %d total agent_norms",
        len(title_to_qid),
        len(qid_to_agent),
        len(all_agent_norms),
    )

    return AgentLookup(
        title_to_qid=title_to_qid,
        qid_to_agent=qid_to_agent,
        all_agent_norms=all_agent_norms,
    )


# =============================================================================
# Connection discovery
# =============================================================================


def _parse_json_array(raw: str | None) -> list[str]:
    """Safely parse a JSON array string, returning empty list on failure."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def _is_substantive_category(category: str) -> bool:
    """Return True if a category is substantive (not a maintenance category)."""
    return not _BROAD_CATEGORY_RE.match(category)


def _canonical_pair(
    agent_a: str, agent_b: str
) -> tuple[str, str]:
    """Return (source, target) in canonical alphabetical order."""
    if agent_a <= agent_b:
        return agent_a, agent_b
    return agent_b, agent_a


def discover_connections(
    db_path: Path,
    store: bool = False,
) -> list[DiscoveredConnection]:
    """Discover connections by cross-referencing wikilinks with agents.

    Algorithm:
    1. Build title->QID->agent lookup from wikipedia_cache + authority_enrichment
    2. For each agent's wikilinks, match against lookup (by QID, not name)
    3. Score: see_also=0.85, body_link=0.75, category=0.65, bidirectional=0.90
    4. Canonical row: source_agent_norm < target_agent_norm (alphabetically)
    5. Optionally store to wikipedia_connections table

    Parameters
    ----------
    db_path : Path
        Path to bibliographic.db
    store : bool
        If True, INSERT OR REPLACE results into wikipedia_connections table

    Returns
    -------
    list[DiscoveredConnection]
        Deduplicated list of discovered connections
    """
    lookup = build_agent_lookup(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Fetch all wikipedia_cache rows
    cache_rows = conn.execute(
        """
        SELECT wc.wikidata_id, wc.wikipedia_title, wc.article_wikilinks,
               wc.see_also_titles, wc.categories
        FROM wikipedia_cache wc
        WHERE wc.wikipedia_title IS NOT NULL
        """
    ).fetchall()

    # Phase 1: Collect raw directed connections
    # Key: (source_agent_norm, target_agent_norm, source_type) -> connection data
    raw_connections: dict[tuple[str, str, str], dict] = {}

    # Track directed pairs for bidirectional detection
    # Key: (agent_a, agent_b) -> set of source_types where a->b was found
    directed_pairs: dict[tuple[str, str], set[str]] = {}

    # Build category->agents map for shared category discovery
    agent_categories: dict[str, set[str]] = {}  # agent_norm -> set of categories

    for row in cache_rows:
        source_qid = row["wikidata_id"]
        source_agent = lookup.qid_to_agent.get(source_qid)
        if not source_agent:
            continue

        # --- Process article wikilinks ---
        wikilinks = _parse_json_array(row["article_wikilinks"])
        for link_title in wikilinks:
            target_qid = lookup.title_to_qid.get(link_title.lower())
            if not target_qid or target_qid == source_qid:
                continue
            target_agent = lookup.qid_to_agent.get(target_qid)
            if not target_agent or target_agent == source_agent:
                continue

            # Record directed pair
            directed_pairs.setdefault((source_agent, target_agent), set()).add(
                "wikilink"
            )

            # Canonical ordering
            src, tgt = _canonical_pair(source_agent, target_agent)
            src_qid = source_qid if src == source_agent else target_qid
            tgt_qid = target_qid if tgt == target_agent else source_qid

            key = (src, tgt, "wikilink")
            if key not in raw_connections:
                raw_connections[key] = {
                    "source_wikidata_id": src_qid,
                    "target_wikidata_id": tgt_qid,
                    "confidence": 0.75,
                    "evidence": f"Wikilink from '{row['wikipedia_title']}' to '{link_title}'",
                }

        # --- Process see_also titles ---
        see_also = _parse_json_array(row["see_also_titles"])
        for title in see_also:
            target_qid = lookup.title_to_qid.get(title.lower())
            if not target_qid or target_qid == source_qid:
                continue
            target_agent = lookup.qid_to_agent.get(target_qid)
            if not target_agent or target_agent == source_agent:
                continue

            directed_pairs.setdefault((source_agent, target_agent), set()).add(
                "see_also"
            )

            src, tgt = _canonical_pair(source_agent, target_agent)
            src_qid = source_qid if src == source_agent else target_qid
            tgt_qid = target_qid if tgt == target_agent else source_qid

            key = (src, tgt, "see_also")
            if key not in raw_connections:
                raw_connections[key] = {
                    "source_wikidata_id": src_qid,
                    "target_wikidata_id": tgt_qid,
                    "confidence": 0.85,
                    "evidence": f"See also link from '{row['wikipedia_title']}' to '{title}'",
                }

        # --- Collect categories for shared-category analysis ---
        categories = _parse_json_array(row["categories"])
        substantive = [c for c in categories if _is_substantive_category(c)]
        if substantive:
            agent_categories[source_agent] = agent_categories.get(
                source_agent, set()
            ) | set(substantive)

    # --- Phase 2: Shared category connections ---
    # Build category -> set of agents
    category_to_agents: dict[str, set[str]] = {}
    for agent, cats in agent_categories.items():
        for cat in cats:
            category_to_agents.setdefault(cat, set()).add(agent)

    # Find pairs sharing categories (skip overly broad categories with >50 agents)
    for cat, agents_in_cat in category_to_agents.items():
        if len(agents_in_cat) > 50 or len(agents_in_cat) < 2:
            continue
        agent_list = sorted(agents_in_cat)
        for i, agent_a in enumerate(agent_list):
            for agent_b in agent_list[i + 1 :]:
                src, tgt = _canonical_pair(agent_a, agent_b)
                key = (src, tgt, "category")
                if key not in raw_connections:
                    # Look up QIDs
                    src_qid = _find_qid_for_agent(src, lookup)
                    tgt_qid = _find_qid_for_agent(tgt, lookup)
                    raw_connections[key] = {
                        "source_wikidata_id": src_qid,
                        "target_wikidata_id": tgt_qid,
                        "confidence": 0.65,
                        "evidence": f"Shared category: '{cat}'",
                    }

    # --- Phase 3: Detect bidirectional and build final connections ---
    connections: list[DiscoveredConnection] = []

    for (src, tgt, source_type), data in raw_connections.items():
        # Check bidirectional: does the reverse directed pair exist?
        bidirectional = False
        if source_type in ("wikilink", "see_also"):
            # Agent A->B and B->A both found?
            forward_exists = False
            reverse_exists = False
            for stype in ("wikilink", "see_also"):
                if (src, tgt) in directed_pairs and stype in directed_pairs.get(
                    (src, tgt), set()
                ):
                    forward_exists = True
                if (tgt, src) in directed_pairs and stype in directed_pairs.get(
                    (tgt, src), set()
                ):
                    reverse_exists = True
            bidirectional = forward_exists and reverse_exists

        confidence = 0.90 if bidirectional else data["confidence"]

        connection = DiscoveredConnection(
            source_agent_norm=src,
            target_agent_norm=tgt,
            source_wikidata_id=data["source_wikidata_id"],
            target_wikidata_id=data["target_wikidata_id"],
            relationship=None,
            tags=[],
            confidence=confidence,
            source_type=source_type,
            evidence=data["evidence"],
            bidirectional=bidirectional,
        )
        connections.append(connection)

    conn.close()

    logger.info(
        "Discovered %d connections (%d bidirectional)",
        len(connections),
        sum(1 for c in connections if c.bidirectional),
    )

    if store:
        _store_connections(db_path, connections)

    return connections


def _find_qid_for_agent(agent_norm: str, lookup: AgentLookup) -> str | None:
    """Find wikidata_id for an agent_norm via reverse lookup."""
    for qid, norm in lookup.qid_to_agent.items():
        if norm == agent_norm:
            return qid
    return None


def _store_connections(
    db_path: Path, connections: list[DiscoveredConnection]
) -> None:
    """Store connections to wikipedia_connections table via INSERT OR REPLACE."""
    conn = sqlite3.connect(str(db_path))
    now = datetime.now(timezone.utc).isoformat()

    inserted = 0
    for c in connections:
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO wikipedia_connections
                    (source_agent_norm, target_agent_norm, source_wikidata_id,
                     target_wikidata_id, relationship, tags, confidence,
                     source_type, evidence, bidirectional, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c.source_agent_norm,
                    c.target_agent_norm,
                    c.source_wikidata_id,
                    c.target_wikidata_id,
                    c.relationship,
                    json.dumps(c.tags, ensure_ascii=False),
                    c.confidence,
                    c.source_type,
                    c.evidence,
                    1 if c.bidirectional else 0,
                    now,
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            logger.warning(
                "Duplicate connection: %s -> %s (%s)",
                c.source_agent_norm,
                c.target_agent_norm,
                c.source_type,
            )

    conn.commit()
    conn.close()
    logger.info("Stored %d connections to wikipedia_connections table", inserted)


# =============================================================================
# Candidate linkage report
# =============================================================================


def generate_candidate_linkage_report(
    db_path: Path,
    fuzzy_threshold: float = 0.80,
    output_path: Path | None = None,
) -> list[CandidateLinkage]:
    """Generate report of wikilinks that might match un-enriched agents.

    For each wikilink title that does NOT match an enriched agent via the
    title->QID->agent chain, fuzzy-match against all agent_norms using
    difflib.SequenceMatcher.  Uses token-based pre-filtering to avoid
    O(N*M) full comparisons (149k titles x 3k norms).

    Parameters
    ----------
    db_path : Path
        Path to bibliographic.db
    fuzzy_threshold : float
        Minimum SequenceMatcher ratio to consider a match (default 0.80)
    output_path : Path or None
        If provided, write CSV report to this path

    Returns
    -------
    list[CandidateLinkage]
        Candidate linkages sorted by match_score descending
    """
    lookup = build_agent_lookup(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    cache_rows = conn.execute(
        """
        SELECT wc.wikidata_id, wc.wikipedia_title, wc.article_wikilinks
        FROM wikipedia_cache wc
        WHERE wc.wikipedia_title IS NOT NULL AND wc.article_wikilinks IS NOT NULL
        """
    ).fetchall()

    # Collect all wikilink titles that did NOT match an enriched agent
    unmatched_titles: dict[str, tuple[str, str]] = {}  # title_lower -> (original_title, mentioned_in)

    for row in cache_rows:
        source_qid = row["wikidata_id"]
        source_agent = lookup.qid_to_agent.get(source_qid, row["wikipedia_title"])

        wikilinks = _parse_json_array(row["article_wikilinks"])
        for link_title in wikilinks:
            title_lower = link_title.lower()
            # Skip if this title matches an enriched agent
            if title_lower in lookup.title_to_qid:
                continue
            # Only record once per unique title (keep first mentioning agent)
            if title_lower not in unmatched_titles:
                unmatched_titles[title_lower] = (link_title, source_agent)

    conn.close()

    logger.info(
        "Found %d unmatched wikilink titles to fuzzy-match against %d agent_norms",
        len(unmatched_titles),
        len(lookup.all_agent_norms),
    )

    # Build token-based inverted index for agent_norms to pre-filter candidates.
    # This reduces from O(N*M) to O(N * small_set) comparisons.
    agent_norms_list = sorted(lookup.all_agent_norms)
    token_to_norms: dict[str, list[str]] = {}
    for norm in agent_norms_list:
        for token in _tokenize(norm):
            token_to_norms.setdefault(token, []).append(norm)

    candidates: list[CandidateLinkage] = []
    checked = 0

    for title_lower, (original_title, mentioned_in) in unmatched_titles.items():
        # Generate multiple normalized forms for matching
        forms = _normalize_forms_for_fuzzy(title_lower)

        # Pre-filter: find agent_norms sharing at least one token with any form
        candidate_norms: set[str] = set()
        for form in forms:
            for token in _tokenize(form):
                if token in token_to_norms:
                    candidate_norms.update(token_to_norms[token])

        if not candidate_norms:
            continue

        best_match: str | None = None
        best_score: float = 0.0

        for norm in candidate_norms:
            # Try all normalized forms and take the best score
            for form in forms:
                score = difflib.SequenceMatcher(None, form, norm).ratio()
                if score > best_score:
                    best_score = score
                    best_match = norm

        checked += 1
        if best_score >= fuzzy_threshold:
            candidates.append(
                CandidateLinkage(
                    wikipedia_title=original_title,
                    mentioned_in_agent=mentioned_in,
                    possible_agent_norm=best_match,
                    match_score=round(best_score, 4),
                )
            )

    # Sort by score descending
    candidates.sort(key=lambda c: c.match_score, reverse=True)

    logger.info(
        "Found %d candidate linkages above threshold %.2f (checked %d titles with token overlap)",
        len(candidates),
        fuzzy_threshold,
        checked,
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["wikipedia_title", "mentioned_in_agent", "possible_agent_norm", "match_score"]
            )
            for c in candidates:
                writer.writerow(
                    [c.wikipedia_title, c.mentioned_in_agent, c.possible_agent_norm, c.match_score]
                )
        logger.info("Wrote candidate linkage report to %s", output_path)

    return candidates


def _tokenize(text: str) -> set[str]:
    """Extract meaningful tokens from a name string for pre-filtering.

    Splits on whitespace/commas/punctuation. Returns tokens with length >= 3
    to avoid matching on trivial fragments.
    """
    tokens = set()
    for part in re.split(r"[\s,;:()\[\]]+", text.lower()):
        cleaned = part.strip(".-'\"")
        if len(cleaned) >= 3:
            tokens.add(cleaned)
    return tokens


def _normalize_forms_for_fuzzy(title: str) -> list[str]:
    """Generate multiple normalized forms of a Wikipedia title for fuzzy matching.

    Wikipedia titles: "Johann Buxtorf" -> try both "johann buxtorf" and "buxtorf, johann"
    Agent norms are typically "surname, given" lowercase.

    Returns list of forms to try (original + inverted if 2 words).
    """
    title = title.strip()
    forms = [title]
    # Try "First Last" -> "last, first"
    parts = title.split()
    if len(parts) == 2:
        forms.append(f"{parts[1]}, {parts[0]}")
    elif len(parts) == 3:
        # "First Middle Last" -> "last, first middle"
        forms.append(f"{parts[2]}, {parts[0]} {parts[1]}")
        # Also try "Last, First" -> "first last" (reverse)
        forms.append(f"{parts[0]}, {parts[1]} {parts[2]}")
    return forms
