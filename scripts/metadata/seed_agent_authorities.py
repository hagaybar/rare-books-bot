"""Seed agent authority records from enrichment data.

Creates ``agent_authorities`` and ``agent_aliases`` rows by:
1. Grouping the ``agents`` table by ``authority_uri``
2. Creating one authority per group with all ``agent_norm`` values as primary aliases
3. Adding enrichment labels (from ``authority_enrichment``) as variant_spelling aliases
4. Adding Hebrew labels (from ``person_info.hebrew_label``) as cross_script aliases
5. Generating word-reorder aliases (``Last, First`` -> ``First Last``)

Idempotent: uses INSERT OR IGNORE so running multiple times is safe.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Dict, List, Optional

from scripts.metadata.agent_authority import (
    AgentAlias,
    AgentAuthorityStore,
    detect_script,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEBREW_RE = re.compile(r"[\u0590-\u05FF]")
_SINGLE_COMMA_RE = re.compile(r"^([^,]+),\s*([^,]+)$")


# ---------------------------------------------------------------------------
# Helper: safe INSERT OR IGNORE for aliases
# ---------------------------------------------------------------------------


def _insert_alias_or_ignore(
    conn: sqlite3.Connection,
    authority_id: int,
    alias: AgentAlias,
) -> bool:
    """Insert an alias row, ignoring duplicates (unique constraint on alias_form_lower).

    Returns True if a row was inserted, False if it was a duplicate.
    """
    from scripts.metadata.agent_authority import _now_iso

    try:
        conn.execute(
            """INSERT OR IGNORE INTO agent_aliases
               (authority_id, alias_form, alias_form_lower, alias_type,
                script, language, is_primary, priority, notes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                authority_id,
                alias.alias_form,
                alias.alias_form.lower(),
                alias.alias_type,
                alias.script,
                alias.language,
                int(alias.is_primary),
                alias.priority,
                alias.notes,
                _now_iso(),
            ),
        )
        return conn.total_changes > 0  # Approximate; fine for statistics
    except sqlite3.IntegrityError:
        return False


def _insert_authority_or_ignore(
    conn: sqlite3.Connection,
    canonical_name: str,
    agent_type: str,
    authority_uri: Optional[str],
    wikidata_id: Optional[str] = None,
    viaf_id: Optional[str] = None,
    nli_id: Optional[str] = None,
    confidence: float = 0.5,
) -> Optional[int]:
    """Insert an authority row, ignoring duplicates.

    Returns the authority ID if inserted, or the existing ID if duplicate.
    """
    from scripts.metadata.agent_authority import _now_iso

    now = _now_iso()
    try:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO agent_authorities
               (canonical_name, canonical_name_lower, agent_type,
                dates_active, date_start, date_end, notes, sources,
                confidence, authority_uri, wikidata_id, viaf_id, nli_id,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                canonical_name,
                canonical_name.lower(),
                agent_type,
                None,  # dates_active
                None,  # date_start
                None,  # date_end
                None,  # notes
                "[]",  # sources
                confidence,
                authority_uri,
                wikidata_id,
                viaf_id,
                nli_id,
                now,
                now,
            ),
        )
        if cursor.rowcount > 0:
            return cursor.lastrowid
    except sqlite3.IntegrityError:
        pass

    # Already exists -- look up by canonical_name_lower
    row = conn.execute(
        "SELECT id FROM agent_authorities WHERE canonical_name_lower = ?",
        (canonical_name.lower(),),
    ).fetchone()
    if row:
        return row["id"] if isinstance(row, sqlite3.Row) else row[0]
    # Fallback: look up by authority_uri
    if authority_uri:
        row = conn.execute(
            "SELECT id FROM agent_authorities WHERE authority_uri = ?",
            (authority_uri,),
        ).fetchone()
        if row:
            return row["id"] if isinstance(row, sqlite3.Row) else row[0]
    return None


# ---------------------------------------------------------------------------
# Public: generate_word_reorder_aliases
# ---------------------------------------------------------------------------


def generate_word_reorder_aliases(name: str) -> List[AgentAlias]:
    """Generate word-reorder alias for a ``Last, First`` name.

    Only processes names with exactly one comma and Latin script.
    Returns a list of AgentAlias (empty if not applicable).

    Parameters
    ----------
    name : str
        The agent name to process (e.g. ``"Buxtorf, Johann"``).

    Returns
    -------
    list[AgentAlias]
        Zero or one alias with ``alias_type='word_reorder'``.
    """
    # Skip Hebrew/non-Latin names
    if _HEBREW_RE.search(name):
        return []

    # Must have exactly one comma
    match = _SINGLE_COMMA_RE.match(name.strip())
    if not match:
        return []

    last_part = match.group(1).strip()
    first_part = match.group(2).strip()

    if not last_part or not first_part:
        return []

    reordered = f"{first_part} {last_part}"

    return [
        AgentAlias(
            alias_form=reordered,
            alias_type="word_reorder",
            script="latin",
            is_primary=False,
            priority=0,
        )
    ]


# ---------------------------------------------------------------------------
# Public: generate_cross_script_aliases
# ---------------------------------------------------------------------------


def generate_cross_script_aliases(
    person_info: Optional[Dict] = None,
    enrichment_label: Optional[str] = None,
) -> List[AgentAlias]:
    """Generate cross-script and variant-spelling aliases from enrichment data.

    Parameters
    ----------
    person_info : dict or None
        Parsed ``person_info`` JSON from ``authority_enrichment``.
        May contain ``hebrew_label``.
    enrichment_label : str or None
        The ``label`` field from ``authority_enrichment``.

    Returns
    -------
    list[AgentAlias]
        Cross-script aliases (Hebrew labels) and variant-spelling aliases
        (enrichment labels).
    """
    aliases: List[AgentAlias] = []

    # Hebrew label from person_info
    if person_info and isinstance(person_info, dict):
        hebrew_label = person_info.get("hebrew_label")
        if hebrew_label and isinstance(hebrew_label, str) and hebrew_label.strip():
            aliases.append(
                AgentAlias(
                    alias_form=hebrew_label.strip(),
                    alias_type="cross_script",
                    script="hebrew",
                    is_primary=False,
                    priority=0,
                )
            )

    # Enrichment label as variant_spelling
    if enrichment_label and isinstance(enrichment_label, str) and enrichment_label.strip():
        script = detect_script(enrichment_label)
        aliases.append(
            AgentAlias(
                alias_form=enrichment_label.strip(),
                alias_type="variant_spelling",
                script=script,
                is_primary=False,
                priority=0,
            )
        )

    return aliases


# ---------------------------------------------------------------------------
# Public: seed_from_enrichment
# ---------------------------------------------------------------------------


def seed_from_enrichment(conn: sqlite3.Connection) -> Dict:
    """Seed agent authorities from enrichment data.

    Groups the ``agents`` table by ``authority_uri``, creates one authority
    per group, and adds all ``agent_norm`` values as primary aliases.  Also
    pulls in enrichment labels and Hebrew labels from
    ``authority_enrichment``.

    Parameters
    ----------
    conn : sqlite3.Connection
        Database connection (must have ``agents``, ``authority_enrichment``,
        ``agent_authorities``, and ``agent_aliases`` tables).

    Returns
    -------
    dict
        Statistics with keys: ``authorities_created``, ``primary_aliases``,
        ``variant_aliases``, ``cross_script_aliases``.
    """
    stats = {
        "authorities_created": 0,
        "primary_aliases": 0,
        "variant_aliases": 0,
        "cross_script_aliases": 0,
    }

    # 1. Group agents by authority_uri
    rows = conn.execute(
        """SELECT authority_uri, agent_type,
                  GROUP_CONCAT(DISTINCT agent_norm) as agent_norms
           FROM agents
           WHERE authority_uri IS NOT NULL AND authority_uri != ''
           GROUP BY authority_uri"""
    ).fetchall()

    for row in rows:
        authority_uri = row["authority_uri"] if isinstance(row, sqlite3.Row) else row[0]
        agent_type = row["agent_type"] if isinstance(row, sqlite3.Row) else row[1]
        agent_norms_str = row["agent_norms"] if isinstance(row, sqlite3.Row) else row[2]

        if not authority_uri:
            continue

        # Collect distinct agent_norm values for this authority_uri
        agent_norms = [
            n.strip() for n in agent_norms_str.split(",") if n.strip()
        ] if agent_norms_str else []

        if not agent_norms:
            continue

        # Use first agent_norm as canonical name
        canonical_name = agent_norms[0]

        # Look up enrichment data
        enrichment = conn.execute(
            "SELECT * FROM authority_enrichment WHERE authority_uri = ?",
            (authority_uri,),
        ).fetchone()

        wikidata_id = None
        viaf_id = None
        nli_id = None
        enrichment_label = None
        person_info = None

        if enrichment:
            wikidata_id = enrichment["wikidata_id"] if isinstance(enrichment, sqlite3.Row) else enrichment[3]
            enrichment_label = enrichment["label"] if isinstance(enrichment, sqlite3.Row) else enrichment[7]
            person_info_raw = enrichment["person_info"] if isinstance(enrichment, sqlite3.Row) else enrichment[9]
            if person_info_raw:
                try:
                    person_info = json.loads(person_info_raw)
                except (json.JSONDecodeError, TypeError):
                    person_info = None

            # Use enrichment label as canonical if available (usually better formatted)
            if enrichment_label and enrichment_label.strip():
                canonical_name = enrichment_label.strip()

        # Create authority
        auth_id = _insert_authority_or_ignore(
            conn,
            canonical_name=canonical_name,
            agent_type=agent_type,
            authority_uri=authority_uri,
            wikidata_id=wikidata_id,
            viaf_id=viaf_id,
            nli_id=nli_id,
        )

        if auth_id is None:
            continue

        stats["authorities_created"] += 1

        # Add all agent_norm values as primary aliases
        for norm in agent_norms:
            alias = AgentAlias(
                alias_form=norm,
                alias_type="primary",
                script=detect_script(norm),
                is_primary=True,
                priority=10,
            )
            _insert_alias_or_ignore(conn, auth_id, alias)
            stats["primary_aliases"] += 1

        # Add enrichment-based aliases
        cross_script = generate_cross_script_aliases(
            person_info=person_info,
            enrichment_label=enrichment_label,
        )
        for alias in cross_script:
            _insert_alias_or_ignore(conn, auth_id, alias)
            if alias.alias_type == "cross_script":
                stats["cross_script_aliases"] += 1
            else:
                stats["variant_aliases"] += 1

    conn.commit()
    return stats


# ---------------------------------------------------------------------------
# Public: seed_all
# ---------------------------------------------------------------------------


def seed_all(conn: sqlite3.Connection) -> Dict:
    """Orchestrate all seeding steps.

    Idempotent: uses INSERT OR IGNORE via unique constraints so running
    multiple times produces the same result.

    Parameters
    ----------
    conn : sqlite3.Connection
        Database connection with all required tables.

    Returns
    -------
    dict
        Combined statistics from all seeding steps.
    """
    # Ensure schema exists
    store = AgentAuthorityStore(":memory:")
    store.init_schema(conn=conn)

    # Step 1: Seed from enrichment (authorities + primary + enrichment aliases)
    enrichment_stats = seed_from_enrichment(conn)

    # Step 2: Generate word-reorder aliases for all primary aliases
    word_reorder_count = 0
    primary_aliases = conn.execute(
        """SELECT al.authority_id, al.alias_form
           FROM agent_aliases al
           WHERE al.alias_type = 'primary'"""
    ).fetchall()

    for alias_row in primary_aliases:
        auth_id = alias_row["authority_id"] if isinstance(alias_row, sqlite3.Row) else alias_row[0]
        alias_form = alias_row["alias_form"] if isinstance(alias_row, sqlite3.Row) else alias_row[1]

        reorder_aliases = generate_word_reorder_aliases(alias_form)
        for ra in reorder_aliases:
            _insert_alias_or_ignore(conn, auth_id, ra)
            word_reorder_count += 1

    conn.commit()

    # Step 3: Generate cross-script aliases from enrichment
    # (already done in seed_from_enrichment, but we count separately
    #  for the statistics breakdown)

    # Build combined statistics
    total_aliases = (
        enrichment_stats["primary_aliases"]
        + enrichment_stats["variant_aliases"]
        + enrichment_stats["cross_script_aliases"]
        + word_reorder_count
    )

    return {
        "authorities_created": enrichment_stats["authorities_created"],
        "aliases_created": total_aliases,
        "primary_aliases": enrichment_stats["primary_aliases"],
        "variant_aliases": enrichment_stats["variant_aliases"],
        "cross_script_aliases": enrichment_stats["cross_script_aliases"],
        "word_reorder_aliases": word_reorder_count,
        "aliases_by_type": {
            "primary": enrichment_stats["primary_aliases"],
            "variant_spelling": enrichment_stats["variant_aliases"],
            "cross_script": enrichment_stats["cross_script_aliases"],
            "word_reorder": word_reorder_count,
        },
    }
