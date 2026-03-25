"""Cross-reference engine for discovering agent relationships (E3).

Builds an in-memory graph from authority_enrichment data and discovers
connections between agents: teacher/student, co-publication, same_place_period.

Key functions:
- build_agent_graph: Load enrichment data into AgentNode graph
- find_connections: Discover pairwise relationships between agents
- find_network_neighbors: Find agents 1-hop away via teacher/student links

Spec: reports/historian-enhancement-plan.md lines 400-565
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from scripts.chat.models import AgentNode, Connection

logger = logging.getLogger(__name__)

# Module-level lazy singleton for the agent graph
_agent_graph_cache: Optional[Dict[str, AgentNode]] = None
_agent_graph_db_id: Optional[int] = None


def _reset_graph_cache() -> None:
    """Reset the module-level graph cache (for testing)."""
    global _agent_graph_cache, _agent_graph_db_id
    _agent_graph_cache = None
    _agent_graph_db_id = None


def _get_connection(db: sqlite3.Connection | Path) -> sqlite3.Connection:
    """Get a sqlite3.Connection from a Path or pass through existing connection."""
    if isinstance(db, sqlite3.Connection):
        return db
    return sqlite3.connect(str(db))


def build_agent_graph(db: sqlite3.Connection | Path) -> Dict[str, AgentNode]:
    """Build agent graph from authority_enrichment data.

    Queries the authority_enrichment table and builds a dict of AgentNode
    objects keyed by agent_norm. Each node contains biographical data
    and teacher/student relationships from person_info JSON.

    Args:
        db: SQLite connection or path to database file.

    Returns:
        Dict mapping agent_norm to AgentNode.
    """
    global _agent_graph_cache, _agent_graph_db_id

    conn = _get_connection(db)

    # Use the connection's id for cache invalidation
    db_id = id(conn)
    if _agent_graph_cache is not None and _agent_graph_db_id == db_id:
        return _agent_graph_cache

    graph: Dict[str, AgentNode] = {}

    try:
        rows = conn.execute("""
            SELECT
                a.agent_norm,
                ae.authority_uri,
                ae.wikidata_id,
                ae.label,
                ae.person_info,
                COUNT(DISTINCT a.record_id) as record_count
            FROM authority_enrichment ae
            JOIN agents a ON a.authority_uri = ae.authority_uri
            WHERE ae.person_info IS NOT NULL
            GROUP BY a.agent_norm, ae.authority_uri
        """).fetchall()
    except sqlite3.OperationalError:
        logger.warning("Could not query authority_enrichment; returning empty graph")
        return graph

    for row in rows:
        agent_norm = row[0]
        authority_uri = row[1]
        wikidata_id = row[2]
        label = row[3]
        person_info_raw = row[4]
        record_count = row[5]

        try:
            person_info = json.loads(person_info_raw) if person_info_raw else {}
        except (json.JSONDecodeError, TypeError):
            person_info = {}

        node = AgentNode(
            label=label or agent_norm,
            agent_norm=agent_norm,
            authority_uri=authority_uri,
            wikidata_id=wikidata_id,
            birth_year=person_info.get("birth_year"),
            death_year=person_info.get("death_year"),
            birth_place=person_info.get("birth_place"),
            occupations=person_info.get("occupations", []),
            teachers=person_info.get("teachers", []),
            students=person_info.get("students", []),
            notable_works=person_info.get("notable_works", []),
            record_count=record_count,
        )
        graph[agent_norm] = node

    _agent_graph_cache = graph
    _agent_graph_db_id = db_id
    return graph


def _match_name_in_graph(
    name: str, graph: Dict[str, AgentNode]
) -> Optional[str]:
    """Find an agent_norm in the graph that matches a display name.

    Performs exact match first, then case-insensitive substring matching.

    Args:
        name: Display name to match (e.g., "Abraham Scultetus").
        graph: Agent graph to search.

    Returns:
        Matching agent_norm or None.
    """
    name_lower = name.lower()

    # Exact match on agent_norm
    if name_lower in graph:
        return name_lower

    # Match by label
    for agent_norm, node in graph.items():
        if node.label.lower() == name_lower:
            return agent_norm

    # Substring match: name parts appear in agent_norm
    name_parts = name_lower.split()
    for agent_norm in graph:
        if all(part in agent_norm for part in name_parts):
            return agent_norm

    # Substring match: agent_norm parts appear in name
    for agent_norm in graph:
        norm_parts = agent_norm.split(", ")
        # Check if the surname (first part of "surname, firstname") is in the name
        if norm_parts and norm_parts[0].lower() in name_lower:
            return agent_norm

    return None


def _find_teacher_student_connections(
    agent_norms: List[str],
    graph: Dict[str, AgentNode],
    visited_pairs: Set[Tuple[str, str]],
) -> List[Connection]:
    """Find teacher/student connections between agents using graph data.

    For each agent in the list, check if any of their teachers/students
    match another agent in the list.

    Args:
        agent_norms: List of agent_norm values to check pairwise.
        graph: Agent graph with teacher/student data.
        visited_pairs: Set of already-visited (sorted) pairs.

    Returns:
        List of Connection objects for teacher_of relationships.
    """
    connections: List[Connection] = []
    agent_set = set(agent_norms)

    for agent_norm in agent_norms:
        node = graph.get(agent_norm)
        if node is None:
            continue

        # Check teachers
        for teacher_name in node.teachers:
            teacher_norm = _match_name_in_graph(teacher_name, graph)
            if teacher_norm is None or teacher_norm not in agent_set:
                continue
            if teacher_norm == agent_norm:
                continue  # Skip self-loops

            pair = tuple(sorted([agent_norm, teacher_norm]))
            if pair in visited_pairs:
                continue
            visited_pairs.add(pair)

            teacher_node = graph[teacher_norm]
            connections.append(Connection(
                agent_a=teacher_node.label,
                agent_b=node.label,
                relationship_type="teacher_of",
                evidence=(
                    f"{teacher_node.label} was teacher of {node.label} "
                    f"(source: Wikidata {node.wikidata_id or 'enrichment'})"
                ),
                confidence=0.90,
                agent_a_wikidata_id=teacher_node.wikidata_id,
                agent_b_wikidata_id=node.wikidata_id,
            ))

        # Check students
        for student_name in node.students:
            student_norm = _match_name_in_graph(student_name, graph)
            if student_norm is None or student_norm not in agent_set:
                continue
            if student_norm == agent_norm:
                continue  # Skip self-loops

            pair = tuple(sorted([agent_norm, student_norm]))
            if pair in visited_pairs:
                continue
            visited_pairs.add(pair)

            student_node = graph[student_norm]
            connections.append(Connection(
                agent_a=node.label,
                agent_b=student_node.label,
                relationship_type="teacher_of",
                evidence=(
                    f"{node.label} was teacher of {student_node.label} "
                    f"(source: Wikidata {node.wikidata_id or 'enrichment'})"
                ),
                confidence=0.90,
                agent_a_wikidata_id=node.wikidata_id,
                agent_b_wikidata_id=student_node.wikidata_id,
            ))

    return connections


def _find_co_publication_connections(
    agent_norms: List[str],
    conn: sqlite3.Connection,
    graph: Dict[str, AgentNode],
    visited_pairs: Set[Tuple[str, str]],
) -> List[Connection]:
    """Find co-publication connections between agents.

    Two agents have a co-publication connection when they appear on the
    same record(s) with different roles (e.g., author + printer).

    Args:
        agent_norms: List of agent_norm values to check.
        conn: SQLite database connection.
        graph: Agent graph for label lookups.
        visited_pairs: Set of already-visited (sorted) pairs.

    Returns:
        List of Connection objects for co_publication relationships.
    """
    if len(agent_norms) < 2:
        return []

    connections: List[Connection] = []
    placeholders = ",".join("?" for _ in agent_norms)

    try:
        # Find pairs of agents sharing records with different roles
        sql = f"""
            SELECT
                a1.agent_norm,
                a2.agent_norm,
                a1.role_norm,
                a2.role_norm,
                COUNT(DISTINCT a1.record_id) as shared_count
            FROM agents a1
            JOIN agents a2 ON a1.record_id = a2.record_id
            WHERE a1.agent_norm IN ({placeholders})
              AND a2.agent_norm IN ({placeholders})
              AND a1.agent_norm < a2.agent_norm
              AND a1.role_norm != a2.role_norm
            GROUP BY a1.agent_norm, a2.agent_norm
            HAVING shared_count >= 2
        """
        rows = conn.execute(sql, agent_norms + agent_norms).fetchall()
    except sqlite3.OperationalError:
        logger.warning("Could not query agents for co-publication")
        return connections

    for row in rows:
        norm_a, norm_b = row[0], row[1]
        role_a, role_b = row[2], row[3]
        shared_count = row[4]

        pair = tuple(sorted([norm_a, norm_b]))
        if pair in visited_pairs:
            continue
        visited_pairs.add(pair)

        node_a = graph.get(norm_a)
        node_b = graph.get(norm_b)
        label_a = node_a.label if node_a else norm_a
        label_b = node_b.label if node_b else norm_b

        connections.append(Connection(
            agent_a=label_a,
            agent_b=label_b,
            relationship_type="co_publication",
            evidence=(
                f"{label_a} ({role_a}) and {label_b} ({role_b}) "
                f"appear together on {shared_count} records"
            ),
            confidence=0.85,
            agent_a_wikidata_id=node_a.wikidata_id if node_a else None,
            agent_b_wikidata_id=node_b.wikidata_id if node_b else None,
        ))

    return connections


def _find_same_place_period_connections(
    agent_norms: List[str],
    graph: Dict[str, AgentNode],
    visited_pairs: Set[Tuple[str, str]],
) -> List[Connection]:
    """Find same_place_period connections between agents.

    Two agents are connected if they share a birth_place and have
    overlapping lifespans.

    Args:
        agent_norms: List of agent_norm values to check pairwise.
        graph: Agent graph with birth_place and dates.
        visited_pairs: Set of already-visited (sorted) pairs.

    Returns:
        List of Connection objects for same_place_period relationships.
    """
    connections: List[Connection] = []

    # Get agents with place and date data
    agents_with_place = []
    for norm in agent_norms:
        node = graph.get(norm)
        if node and node.birth_place and node.birth_year and node.death_year:
            agents_with_place.append(node)

    # Check pairwise
    for i, node_a in enumerate(agents_with_place):
        for node_b in agents_with_place[i + 1:]:
            if node_a.agent_norm == node_b.agent_norm:
                continue  # Skip self-loops

            pair = tuple(sorted([node_a.agent_norm, node_b.agent_norm]))
            if pair in visited_pairs:
                continue

            # Same birth_place (case-insensitive)
            if node_a.birth_place.lower() != node_b.birth_place.lower():
                continue

            # Overlapping lifespans
            if node_a.birth_year > node_b.death_year or node_b.birth_year > node_a.death_year:
                continue

            visited_pairs.add(pair)

            overlap_start = max(node_a.birth_year, node_b.birth_year)
            overlap_end = min(node_a.death_year, node_b.death_year)

            connections.append(Connection(
                agent_a=node_a.label,
                agent_b=node_b.label,
                relationship_type="same_place_period",
                evidence=(
                    f"Both active in {node_a.birth_place}, "
                    f"overlapping period {overlap_start}-{overlap_end}"
                ),
                confidence=0.70,
                agent_a_wikidata_id=node_a.wikidata_id,
                agent_b_wikidata_id=node_b.wikidata_id,
            ))

    return connections


def _find_wikipedia_connections(
    agent_norms: List[str],
    conn: sqlite3.Connection,
    visited_pairs: Set[Tuple[str, str]],
) -> List[Connection]:
    """Find Wikipedia-derived connections between agents.

    Queries wikipedia_connections table for pairs where both agents
    are in the current agent_norms list.

    Args:
        agent_norms: List of agent_norm values to check.
        conn: SQLite database connection.
        visited_pairs: Set of already-visited (sorted) pairs.

    Returns:
        List of Connection objects for wikipedia_mention relationships.
    """
    if len(agent_norms) < 2:
        return []

    connections: List[Connection] = []

    # Check if wikipedia_connections table exists
    try:
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='wikipedia_connections'"
        ).fetchone()
        if not table_check:
            return connections
    except sqlite3.OperationalError:
        return connections

    placeholders = ",".join("?" for _ in agent_norms)

    try:
        sql = f"""
            SELECT
                source_agent_norm,
                target_agent_norm,
                source_wikidata_id,
                target_wikidata_id,
                relationship,
                confidence,
                evidence
            FROM wikipedia_connections
            WHERE source_agent_norm IN ({placeholders})
              AND target_agent_norm IN ({placeholders})
        """
        rows = conn.execute(sql, agent_norms + agent_norms).fetchall()
    except sqlite3.OperationalError:
        logger.warning("Could not query wikipedia_connections table")
        return connections

    for row in rows:
        source_norm = row[0]
        target_norm = row[1]
        source_wikidata_id = row[2]
        target_wikidata_id = row[3]
        relationship = row[4]
        confidence = row[5]
        evidence_text = row[6]

        pair = tuple(sorted([source_norm, target_norm]))
        if pair in visited_pairs:
            continue
        visited_pairs.add(pair)

        connections.append(Connection(
            agent_a=source_norm,
            agent_b=target_norm,
            relationship_type="wikipedia_mention",
            evidence=evidence_text or relationship or "Wikipedia connection",
            confidence=confidence,
            agent_a_wikidata_id=source_wikidata_id,
            agent_b_wikidata_id=target_wikidata_id,
        ))

    return connections


def find_connections(
    db: sqlite3.Connection | Path,
    agent_norms: List[str],
    max_results: int = 20,
) -> List[Connection]:
    """Discover connections between agents in a result set.

    Checks four relationship types:
    1. teacher/student (from graph person_info)
    2. co-publication (shared records with different roles)
    3. same_place_period (same birth_place, overlapping dates)
    4. wikipedia_mention (from wikipedia_connections table)

    Performance guard: skips if >50 agents.

    Args:
        db: SQLite connection or path to database.
        agent_norms: List of normalized agent names to check.
        max_results: Maximum connections to return (default 20).

    Returns:
        List of Connection objects sorted by confidence descending,
        capped at max_results.
    """
    if not agent_norms:
        return []

    # Performance guard
    if len(agent_norms) > 50:
        logger.warning(
            "Skipping cross-reference: %d agents exceeds limit of 50",
            len(agent_norms),
        )
        return []

    conn = _get_connection(db)

    # Always rebuild graph for the given connection to avoid stale cache
    # in test scenarios with different in-memory DBs
    _reset_graph_cache()
    graph = build_agent_graph(conn)

    if not graph:
        return []

    visited_pairs: Set[Tuple[str, str]] = set()
    all_connections: List[Connection] = []

    # 1. Teacher/student from graph
    all_connections.extend(
        _find_teacher_student_connections(agent_norms, graph, visited_pairs)
    )

    # 2. Co-publication from SQL
    all_connections.extend(
        _find_co_publication_connections(agent_norms, conn, graph, visited_pairs)
    )

    # 3. Same place and period from graph
    all_connections.extend(
        _find_same_place_period_connections(agent_norms, graph, visited_pairs)
    )

    # 4. Wikipedia-derived connections
    try:
        wiki_conns = _find_wikipedia_connections(agent_norms, conn, visited_pairs)
        all_connections.extend(wiki_conns)
    except Exception:
        pass  # Table may not exist

    # Sort by confidence descending, cap at max_results
    all_connections.sort(key=lambda c: c.confidence, reverse=True)
    return all_connections[:max_results]


def find_network_neighbors(
    db: sqlite3.Connection | Path,
    agent_norm: str,
    max_hops: int = 1,
) -> List[Connection]:
    """Find agents connected to a starting agent via teacher/student links.

    Traverses the teacher/student graph up to max_hops away from the
    starting agent. Returns Connection objects (network_neighbor type)
    for each discovered link.

    Args:
        db: SQLite connection or path to database.
        agent_norm: Normalized name of the starting agent.
        max_hops: Maximum hops in the graph (default 1).

    Returns:
        List of Connection objects for discovered neighbors.
    """
    conn = _get_connection(db)

    _reset_graph_cache()
    graph = build_agent_graph(conn)

    if agent_norm not in graph:
        return []

    connections: List[Connection] = []
    visited: Set[str] = {agent_norm}
    current_level = [agent_norm]

    for _hop in range(max_hops):
        next_level: List[str] = []

        for current_norm in current_level:
            current_node = graph.get(current_norm)
            if current_node is None:
                continue

            # Find teachers
            for teacher_name in current_node.teachers:
                teacher_norm = _match_name_in_graph(teacher_name, graph)
                if teacher_norm is None or teacher_norm in visited:
                    continue
                visited.add(teacher_norm)
                next_level.append(teacher_norm)

                teacher_node = graph[teacher_norm]
                connections.append(Connection(
                    agent_a=teacher_node.label,
                    agent_b=current_node.label,
                    relationship_type="network_neighbor",
                    evidence=(
                        f"{teacher_node.label} was teacher of "
                        f"{current_node.label} (1-hop neighbor)"
                    ),
                    confidence=0.90,
                    agent_a_wikidata_id=teacher_node.wikidata_id,
                    agent_b_wikidata_id=current_node.wikidata_id,
                ))

            # Find students
            for student_name in current_node.students:
                student_norm = _match_name_in_graph(student_name, graph)
                if student_norm is None or student_norm in visited:
                    continue
                visited.add(student_norm)
                next_level.append(student_norm)

                student_node = graph[student_norm]
                connections.append(Connection(
                    agent_a=current_node.label,
                    agent_b=student_node.label,
                    relationship_type="network_neighbor",
                    evidence=(
                        f"{current_node.label} was teacher of "
                        f"{student_node.label} (1-hop neighbor)"
                    ),
                    confidence=0.90,
                    agent_a_wikidata_id=current_node.wikidata_id,
                    agent_b_wikidata_id=student_node.wikidata_id,
                ))

        current_level = next_level

    return connections
