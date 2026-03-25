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
7. LLM-assisted relationship extraction (Pass 3): use gpt-4.1-nano to
   extract structured relationships from Wikipedia summaries

Usage
-----
    from scripts.enrichment.wikipedia_connections import discover_connections
    conns = discover_connections(Path("data/index/bibliographic.db"), store=True)

    # Pass 3: LLM extraction
    from scripts.enrichment.wikipedia_connections import extract_relationships_llm
    import asyncio
    conns = asyncio.run(extract_relationships_llm(
        agent_name="Joseph Karo",
        summary_text="Joseph ben Ephraim Karo was...",
        known_linked_agents=[{"name": "Moses Isserles", "qid": "Q440285"}],
    ))
"""

import csv
import difflib
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field

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


# =============================================================================
# LLM-assisted relationship extraction (Pass 3)
# =============================================================================

# Tag vocabulary for the LLM prompt
_TAG_VOCABULARY = [
    "teacher_of",
    "student_of",
    "collaborator",
    "commentator",
    "co_publication",
    "patron",
    "rival",
    "translator",
    "publisher_of",
    "same_school",
    "family",
    "influenced_by",
]


class ExtractedRelationship(BaseModel):
    """A single relationship extracted by the LLM from a Wikipedia summary."""

    target_name: str = Field(description="Name of the related person")
    target_wikidata_id: str | None = Field(
        default=None,
        description="Wikidata QID if known from provided list, e.g. Q440285",
    )
    relationship: str = Field(description="Free-text description of the relationship")
    tags: list[str] = Field(
        default_factory=list,
        description="Relationship tags from the vocabulary, or new tags if none fit",
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score for this relationship"
    )


class _LLMExtractionResponse(BaseModel):
    """Schema for the complete LLM response."""

    relationships: list[ExtractedRelationship] = Field(default_factory=list)


_EXTRACTION_SYSTEM_PROMPT = """\
You are a bibliographic relationship extraction expert specializing in early \
modern print culture, Jewish intellectual history, and rare book networks.

Your task: Given a person's Wikipedia summary and a list of known linked \
persons (with their Wikidata QIDs), extract structured relationships between \
the subject and other people mentioned.

RULES:
1. Extract ONLY relationships explicitly stated or clearly implied in the text.
2. For each relationship, provide a free-text description AND one or more tags.
3. Tag vocabulary: {tags}
   If none of the above tags fit, create a new descriptive tag (e.g. "successor", "opponent").
4. If a target person appears in the known_linked_agents list, use their exact \
   Wikidata QID in target_wikidata_id. Otherwise, set target_wikidata_id to null.
5. Confidence scoring:
   - 0.9-1.0: Explicitly stated relationship ("X was the teacher of Y")
   - 0.7-0.89: Strongly implied ("studied under X", "worked in X's workshop")
   - 0.5-0.69: Plausibly implied from context
   - Below 0.5: Do not include
6. Only include people, not places, institutions, or works.

Return EXACTLY this JSON structure:
{{
  "relationships": [
    {{
      "target_name": "Name of the related person",
      "target_wikidata_id": "Q12345 or null if unknown",
      "relationship": "Free-text description of the relationship",
      "tags": ["tag1", "tag2"],
      "confidence": 0.85
    }}
  ]
}}

IMPORTANT: Each relationship object MUST have these exact keys: \
target_name, target_wikidata_id, relationship, tags, confidence. \
Do NOT use "source", "target", or any other key names.
"""


def _build_extraction_user_prompt(
    agent_name: str,
    summary_text: str,
    known_linked_agents: list[dict],
) -> str:
    """Build the user prompt for LLM relationship extraction."""
    known_section = ""
    if known_linked_agents:
        lines = []
        for a in known_linked_agents[:100]:  # Cap at 100 to stay within context
            qid = a.get("qid", "unknown")
            name = a.get("name", "unknown")
            lines.append(f"  - {name} ({qid})")
        known_section = (
            "Known linked persons (use their QIDs if they appear in relationships):\n"
            + "\n".join(lines)
        )
    else:
        known_section = "No known linked persons from previous passes."

    return (
        f"Subject: {agent_name}\n\n"
        f"Wikipedia summary:\n{summary_text}\n\n"
        f"{known_section}\n\n"
        "Extract all interpersonal relationships from this summary."
    )


# Field-name remapping for common LLM output variations
_FIELD_ALIASES = {
    # target_name aliases
    "target": "target_name",
    "name": "target_name",
    "person": "target_name",
    "person_name": "target_name",
    # target_wikidata_id aliases
    "wikidata_id": "target_wikidata_id",
    "qid": "target_wikidata_id",
    "wikidata_qid": "target_wikidata_id",
    # relationship aliases
    "description": "relationship",
    "relation": "relationship",
    "relation_type": "relationship",
    "relationship_description": "relationship",
    # tags aliases
    "tag": "tags",
    "labels": "tags",
    "relationship_tags": "tags",
    "relationship_type": "tags",
}

# Keys the LLM might include that should be ignored (not mapped)
_IGNORED_KEYS = {"source", "source_name", "source_wikidata_id"}


def _normalize_relationship_dict(raw: dict) -> dict:
    """Remap common LLM field-name variants to the expected schema.

    The LLM sometimes uses alternative key names like "target" instead of
    "target_name" or "source" + "target" instead of just "target_name".
    This function normalizes the dict to match ExtractedRelationship fields.
    """
    normalized: dict = {}

    for key, value in raw.items():
        if key in _IGNORED_KEYS:
            continue

        canonical = _FIELD_ALIASES.get(key, key)

        # Don't overwrite if canonical key already set from a more specific alias
        if canonical not in normalized:
            normalized[canonical] = value
        # Special case: if "tags" was set as a string, wrap in a list
        if canonical == "tags" and isinstance(value, str):
            normalized[canonical] = [value]

    return normalized


async def extract_relationships_llm(
    agent_name: str,
    summary_text: str,
    known_linked_agents: list[dict],
    model: str = "gpt-4.1-nano",
    api_key: str | None = None,
) -> list[DiscoveredConnection]:
    """Use LLM to extract structured relationships from a Wikipedia summary.

    The LLM receives the agent's summary text and a list of known linked
    agents with their Wikidata QIDs (from Pass 1 connections). It returns
    structured relationships with free-text descriptions and pre-tagged labels.

    Matching strategy:
    - If target_wikidata_id is provided: match directly via authority_enrichment
    - If not: look up target_name in wikipedia_cache.wikipedia_title
    - Fallback: skip (no fuzzy matching to avoid false positives)

    Parameters
    ----------
    agent_name : str
        Display name of the source agent.
    summary_text : str
        Wikipedia summary extract for the agent.
    known_linked_agents : list[dict]
        Known linked agents from Pass 1, each with "name" and "qid" keys.
    model : str
        OpenAI model to use (default: gpt-4.1-nano).
    api_key : str or None
        OpenAI API key override (falls back to OPENAI_API_KEY env var).

    Returns
    -------
    list[DiscoveredConnection]
        Extracted connections with source_type="llm_extraction".

    Raises
    ------
    ValueError
        If no API key is available.
    """
    from openai import OpenAI

    resolved_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_key:
        raise ValueError("OPENAI_API_KEY not set and no api_key provided")

    client = OpenAI(api_key=resolved_key)

    system_prompt = _EXTRACTION_SYSTEM_PROMPT.format(
        tags=", ".join(_TAG_VOCABULARY)
    )
    user_prompt = _build_extraction_user_prompt(
        agent_name, summary_text, known_linked_agents
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            logger.warning("Empty LLM response for agent %s", agent_name)
            return []

        parsed = json.loads(content)

        # Normalize LLM output: remap common field-name variants to our schema
        if "relationships" in parsed and isinstance(parsed["relationships"], list):
            parsed["relationships"] = [
                _normalize_relationship_dict(r)
                for r in parsed["relationships"]
            ]

        llm_result = _LLMExtractionResponse.model_validate(parsed)

    except json.JSONDecodeError as exc:
        logger.error("JSON parse error for agent %s: %s", agent_name, exc)
        return []
    except Exception as exc:
        logger.error("LLM extraction failed for agent %s: %s", agent_name, exc)
        return []

    # Log the LLM call (best-effort, don't fail if logger unavailable)
    try:
        from scripts.utils.llm_logger import log_llm_call

        log_llm_call(
            call_type="wikipedia_relationship_extraction",
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=response,
            extra_metadata={"agent_name": agent_name},
        )
    except Exception:
        pass  # Logging is optional

    # Build known-agent lookup for QID resolution
    qid_lookup: dict[str, dict] = {}
    for a in known_linked_agents:
        qid = a.get("qid")
        if qid:
            qid_lookup[qid] = a

    connections: list[DiscoveredConnection] = []
    for rel in llm_result.relationships:
        if rel.confidence < 0.5:
            continue

        # We don't resolve to agent_norm here -- that's done at storage time
        # by the batch script, which has access to the DB. Here we just
        # validate that the target has a resolvable identifier.
        target_qid = rel.target_wikidata_id
        target_name = rel.target_name

        # Build a placeholder connection -- the batch script resolves
        # agent_norms and applies canonical ordering before storing.
        conn_obj = DiscoveredConnection(
            source_agent_norm=agent_name,  # Placeholder; batch resolves
            target_agent_norm=target_name,  # Placeholder; batch resolves
            source_wikidata_id=None,  # Filled by batch
            target_wikidata_id=target_qid,
            relationship=rel.relationship,
            tags=rel.tags,
            confidence=rel.confidence,
            source_type="llm_extraction",
            evidence=f"LLM-extracted from Wikipedia summary: {rel.relationship}",
            bidirectional=False,
        )
        connections.append(conn_obj)

    logger.info(
        "LLM extracted %d relationships for %s (from %d raw)",
        len(connections),
        agent_name,
        len(llm_result.relationships),
    )

    return connections


def resolve_and_store_llm_connections(
    db_path: Path,
    source_qid: str,
    source_agent_norm: str,
    raw_connections: list[DiscoveredConnection],
) -> int:
    """Resolve LLM-extracted connections to agent_norms and store them.

    Matching strategy:
    1. If target_wikidata_id is set: look up via authority_enrichment -> agents
    2. Else: look up target_agent_norm (as wikipedia_title) in wikipedia_cache
    3. Fallback: skip the connection

    Uses canonical ordering (source < target alphabetically) and INSERT OR
    REPLACE to avoid duplicates.

    Parameters
    ----------
    db_path : Path
        Path to bibliographic.db.
    source_qid : str
        Wikidata QID of the source agent.
    source_agent_norm : str
        Normalized name of the source agent.
    raw_connections : list[DiscoveredConnection]
        Connections from extract_relationships_llm() with placeholder names.

    Returns
    -------
    int
        Number of connections successfully stored.
    """
    if not raw_connections:
        return 0

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat()

    stored = 0
    for rc in raw_connections:
        target_agent_norm: str | None = None
        target_qid = rc.target_wikidata_id

        # Strategy 1: Resolve via QID -> authority_enrichment -> agents
        if target_qid:
            row = conn.execute(
                """
                SELECT MIN(a.agent_norm) as agent_norm
                FROM authority_enrichment ae
                JOIN agents a ON a.authority_uri = ae.authority_uri
                WHERE ae.wikidata_id = ? AND a.agent_norm IS NOT NULL
                """,
                (target_qid,),
            ).fetchone()
            if row and row["agent_norm"]:
                target_agent_norm = row["agent_norm"]

        # Strategy 2: Look up target name as wikipedia_title
        if not target_agent_norm:
            target_title = rc.target_agent_norm  # This is the placeholder name
            row = conn.execute(
                """
                SELECT wc.wikidata_id
                FROM wikipedia_cache wc
                WHERE LOWER(wc.wikipedia_title) = LOWER(?)
                """,
                (target_title,),
            ).fetchone()
            if row and row["wikidata_id"]:
                target_qid = row["wikidata_id"]
                # Now resolve QID -> agent_norm
                row2 = conn.execute(
                    """
                    SELECT MIN(a.agent_norm) as agent_norm
                    FROM authority_enrichment ae
                    JOIN agents a ON a.authority_uri = ae.authority_uri
                    WHERE ae.wikidata_id = ? AND a.agent_norm IS NOT NULL
                    """,
                    (target_qid,),
                ).fetchone()
                if row2 and row2["agent_norm"]:
                    target_agent_norm = row2["agent_norm"]

        # Fallback: skip if we can't resolve to an agent in our collection
        if not target_agent_norm:
            logger.debug(
                "Skipping LLM connection: could not resolve target '%s' (QID=%s)",
                rc.target_agent_norm,
                target_qid,
            )
            continue

        # Skip self-references
        if target_agent_norm == source_agent_norm:
            continue

        # Canonical ordering
        src, tgt = _canonical_pair(source_agent_norm, target_agent_norm)
        src_qid = source_qid if src == source_agent_norm else target_qid
        tgt_qid = target_qid if tgt == target_agent_norm else source_qid

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
                    src,
                    tgt,
                    src_qid,
                    tgt_qid,
                    rc.relationship,
                    json.dumps(rc.tags, ensure_ascii=False),
                    rc.confidence,
                    "llm_extraction",
                    rc.evidence,
                    0,
                    now,
                ),
            )
            stored += 1
        except sqlite3.IntegrityError:
            logger.warning(
                "Duplicate LLM connection: %s -> %s", src, tgt
            )

    conn.commit()
    conn.close()

    logger.info(
        "Stored %d/%d LLM-extracted connections for %s",
        stored,
        len(raw_connections),
        source_agent_norm,
    )
    return stored
