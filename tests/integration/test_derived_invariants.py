"""Derived-artifact invariant battery (audits/2026-06-12-seam-audit).

Encodes every derived-artifact invariant from the seam audit as a permanent
regression guard: each invariant is a read-only SELECT against the live DB that
returns a *violation count*, asserted == 0. All four original audit violations
are now repaired and enforce strictly: D1=I1 (vanished aliases) and D3=N1
(orphan network edges) by fix_30, and D2=P3 (Proops placeholder shadows) and
D4=E1 (d'Alembert wikidata disagreement) by fix_31 (both applied 2026-06-13).

Rules honoured:
- DB is opened strictly read-only (``mode=ro`` URI); only SELECT/PRAGMA run.
- No LLM, no network; total runtime well under 5s.
- The whole module skips cleanly when the bibliographic DB is absent (CI
  without data). The chat-sessions DB (only used by C1) skips per-case.

SQL is the audit's verbatim violation-count SQL where the audit gave it; the
elided E2/E3/E4 joins were reconstructed to match the audit's stated 0 result
and verified against the live DB.
"""
import sqlite3
from pathlib import Path

import pytest

DB_PATH = Path("data/index/bibliographic.db")
SESSIONS_DB_PATH = Path("data/chat/sessions.db")

# Marked `integration` (so the batch's `-m 'not integration'` gate skips it) and
# skipped wholesale when there is no data to audit (CI without the DB).
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not DB_PATH.exists(),
        reason="Bibliographic database not available",
    ),
]


def _ro_connect(path: Path) -> sqlite3.Connection:
    """Open ``path`` strictly read-only — any write attempt raises."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


@pytest.fixture(scope="module")
def conn():
    """One read-only connection to the bibliographic DB, reused across cases."""
    c = _ro_connect(DB_PATH)
    yield c
    c.close()


@pytest.fixture(scope="module")
def sessions_conn():
    """Read-only connection to the chat-sessions DB (only C1 needs it)."""
    if not SESSIONS_DB_PATH.exists():
        pytest.skip("Chat sessions database not available")
    c = _ro_connect(SESSIONS_DB_PATH)
    yield c
    c.close()


def _count(conn: sqlite3.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()[0]


# All four original audit violations (I1/N1 via fix_30, P3/E1 via fix_31) are
# repaired and now enforce strictly — a regression fails the battery loudly.

# --- All invariants that currently hold at 0 (~27) --------------------------
# (invariant_id, description, sql). Audit SQL used verbatim where given.
INVARIANTS = [
    # --- agent_aliases / agent_authorities -------------------------------
    pytest.param(
        "I1",
        "Every authority-linked agent_norm has an alias row (fix_29 contract)",
        "SELECT COUNT(*) FROM (SELECT DISTINCT ag.agent_norm FROM agents ag "
        "JOIN agent_authorities aa ON aa.authority_uri=ag.authority_uri "
        "WHERE ag.agent_norm NOT IN (SELECT alias_form_lower FROM agent_aliases))",
        "#58/D1 (fixed by fix_30)",
        id="I1-authority_linked_norm_has_alias",
    ),
    pytest.param(
        "I2",
        "No primary alias is a comma-fragment of its own authority's norm",
        "SELECT COUNT(*) FROM (SELECT DISTINCT al.id FROM agent_aliases al "
        "JOIN agent_authorities aa ON aa.id=al.authority_id "
        "JOIN agents ag ON ag.authority_uri=aa.authority_uri "
        "WHERE al.alias_type='primary' AND ag.agent_norm LIKE '%,%' "
        "AND (','||REPLACE(ag.agent_norm,', ',',')||',') "
        "LIKE ('%,'||al.alias_form_lower||',%') "
        "AND al.alias_form_lower<>ag.agent_norm "
        "AND al.alias_form_lower NOT IN "
        "(SELECT ag2.agent_norm FROM agents ag2 "
        "WHERE ag2.authority_uri=aa.authority_uri))",
        "fix_29",
        id="I2-no_comma_fragment_primary_aliases",
    ),
    pytest.param(
        "I3",
        "Every alias row references an existing agent_authorities row",
        "SELECT COUNT(*) FROM agent_aliases al "
        "LEFT JOIN agent_authorities aa ON aa.id=al.authority_id "
        "WHERE aa.id IS NULL",
        "audit-I3",
        id="I3-alias_authority_fk_valid",
    ),
    pytest.param(
        "I4",
        "For ASCII forms, alias_form_lower = lower(alias_form)",
        "SELECT COUNT(*) FROM agent_aliases "
        "WHERE alias_form NOT GLOB '*[^ -~]*' "
        "AND alias_form_lower <> lower(alias_form)",
        "audit-I4",
        id="I4-alias_form_lower_ascii_canonical",
    ),
    pytest.param(
        "I5",
        "For ASCII names, canonical_name_lower = lower(canonical_name)",
        "SELECT COUNT(*) FROM agent_authorities "
        "WHERE canonical_name NOT GLOB '*[^ -~]*' "
        "AND canonical_name_lower <> lower(canonical_name)",
        "audit-I5",
        id="I5-canonical_name_lower_ascii_canonical",
    ),
    pytest.param(
        "A1",
        "alias_form_lower is globally unique (resolution determinism)",
        "SELECT COUNT(*) FROM (SELECT alias_form_lower FROM agent_aliases "
        "GROUP BY alias_form_lower HAVING COUNT(*)>1)",
        "audit-A1",
        id="A1-alias_form_lower_globally_unique",
    ),
    # --- publisher_variants / publisher_authorities ----------------------
    pytest.param(
        "P1",
        "Every variant references an existing publisher_authorities row",
        "SELECT COUNT(*) FROM publisher_variants pv "
        "LEFT JOIN publisher_authorities pa ON pa.id=pv.authority_id "
        "WHERE pa.id IS NULL",
        "audit-P1",
        id="P1-variant_authority_fk_valid",
    ),
    pytest.param(
        "P2",
        "Every multi-record publisher_norm is a canonical or variant form",
        "SELECT COUNT(*) FROM (SELECT i.publisher_norm pn FROM imprints i "
        "WHERE i.publisher_norm IS NOT NULL GROUP BY i.publisher_norm "
        "HAVING COUNT(DISTINCT i.record_id)>1) p "
        "WHERE p.pn NOT IN (SELECT canonical_name_lower FROM publisher_authorities) "
        "AND p.pn NOT IN (SELECT variant_form_lower FROM publisher_variants)",
        "audit-P2",
        id="P2-multi_record_publisher_norm_linked",
    ),
    pytest.param(
        "P3",
        "No variant_form_lower equals the canonical of a *different* authority",
        "SELECT COUNT(*) FROM publisher_variants pv "
        "JOIN publisher_authorities pa "
        "ON pa.canonical_name_lower=pv.variant_form_lower AND pa.id<>pv.authority_id",
        "#58/D2 (fixed by fix_31)",
        id="P3-variant_never_shadows_foreign_canonical",
    ),
    pytest.param(
        "P6",
        "Divergent variant_form_lower resolves to a real imprints.publisher_norm",
        "SELECT COUNT(*) FROM publisher_variants pv "
        "WHERE pv.variant_form_lower <> lower(pv.variant_form) "
        "AND NOT EXISTS (SELECT 1 FROM imprints i "
        "WHERE i.publisher_norm = pv.variant_form_lower)",
        "audit-P4/P6",
        id="P6-divergent_variant_lower_resolves_to_imprint_norm",
    ),
    # --- FTS rowcount + rowid parity (F1–F4) -----------------------------
    pytest.param(
        "F1",
        "titles_fts row-count parity with titles",
        "SELECT (SELECT COUNT(*) FROM titles) - (SELECT COUNT(*) FROM titles_fts)",
        "audit-F1",
        id="F1-titles_fts_rowcount_parity",
    ),
    pytest.param(
        "F2",
        "Every titles.id is present as a titles_fts rowid",
        "SELECT COUNT(*) FROM titles t "
        "WHERE t.id NOT IN (SELECT rowid FROM titles_fts)",
        "audit-F2",
        id="F2-titles_id_in_fts_rowid",
    ),
    pytest.param(
        "F2r",
        "Every titles_fts rowid has a backing titles row",
        "SELECT COUNT(*) FROM titles_fts f "
        "WHERE f.rowid NOT IN (SELECT id FROM titles)",
        "audit-F2",
        id="F2-fts_rowid_has_title_row",
    ),
    pytest.param(
        "F3",
        "subjects_fts row-count parity with subjects",
        "SELECT (SELECT COUNT(*) FROM subjects) - (SELECT COUNT(*) FROM subjects_fts)",
        "audit-F3",
        id="F3-subjects_fts_rowcount_parity",
    ),
    pytest.param(
        "F4",
        "Every subjects.id is present as a subjects_fts rowid",
        "SELECT COUNT(*) FROM subjects s "
        "WHERE s.id NOT IN (SELECT rowid FROM subjects_fts)",
        "audit-F4",
        id="F4-subjects_id_in_fts_rowid",
    ),
    pytest.param(
        "F4r",
        "Every subjects_fts rowid has a backing subjects row",
        "SELECT COUNT(*) FROM subjects_fts f "
        "WHERE f.rowid NOT IN (SELECT id FROM subjects)",
        "audit-F4",
        id="F4-fts_rowid_has_subject_row",
    ),
    # --- network_agents / network_edges ----------------------------------
    pytest.param(
        "N1",
        "Both edge endpoints resolve to existing network_agents nodes",
        "SELECT COUNT(*) FROM network_edges e "
        "WHERE e.source_agent_norm NOT IN (SELECT agent_norm FROM network_agents) "
        "OR e.target_agent_norm NOT IN (SELECT agent_norm FROM network_agents)",
        "#58/D3 (fixed by fix_30)",
        id="N1-network_edge_endpoints_resolve",
    ),
    pytest.param(
        "N2",
        "Every person node's agent_norm exists in agents.agent_norm",
        "SELECT COUNT(*) FROM network_agents na WHERE na.node_type='person' "
        "AND na.agent_norm NOT IN (SELECT DISTINCT agent_norm FROM agents)",
        "audit-N2",
        id="N2-person_node_provenance",
    ),
    pytest.param(
        "N3",
        "Every publisher node's pub:-stripped key is a publisher canonical",
        "SELECT COUNT(*) FROM network_agents na WHERE na.node_type='publisher' "
        "AND substr(na.agent_norm,5) NOT IN "
        "(SELECT canonical_name_lower FROM publisher_authorities)",
        "audit-N3",
        id="N3-publisher_node_provenance",
    ),
    pytest.param(
        "N4",
        "connection_count equals edges touching the node",
        "SELECT COUNT(*) FROM network_agents na "
        "WHERE na.connection_count <> (SELECT COUNT(*) FROM network_edges e "
        "WHERE e.source_agent_norm=na.agent_norm OR e.target_agent_norm=na.agent_norm)",
        "audit-N4",
        id="N4-connection_count_matches_edges",
    ),
    pytest.param(
        "N5",
        "Person record_count equals COUNT(DISTINCT record_id) in agents",
        "SELECT COUNT(*) FROM network_agents na WHERE na.node_type='person' "
        "AND na.record_count <> (SELECT COUNT(DISTINCT a.record_id) FROM agents a "
        "WHERE a.agent_norm=na.agent_norm)",
        "audit-N5",
        id="N5-record_count_matches_agents",
    ),
    pytest.param(
        "N6self",
        "No self-loop edges",
        "SELECT COUNT(*) FROM network_edges WHERE source_agent_norm=target_agent_norm",
        "audit-N6",
        id="N6-no_self_loop_edges",
    ),
    pytest.param(
        "N6bounds",
        "Edge confidence within [0,1]",
        "SELECT COUNT(*) FROM network_edges WHERE confidence < 0 OR confidence > 1",
        "audit-N6",
        id="N6-confidence_in_bounds",
    ),
    # --- wikipedia_connections -> network_edges --------------------------
    pytest.param(
        "W1",
        "Every in-network wikipedia_connection is projected as a network_edge",
        "SELECT COUNT(*) FROM wikipedia_connections wc "
        "WHERE wc.source_agent_norm IN (SELECT agent_norm FROM network_agents) "
        "AND wc.target_agent_norm IN (SELECT agent_norm FROM network_agents) "
        "AND NOT EXISTS (SELECT 1 FROM network_edges e "
        "WHERE e.source_agent_norm=wc.source_agent_norm "
        "AND e.target_agent_norm=wc.target_agent_norm "
        "AND e.connection_type=wc.source_type)",
        "audit-W1",
        id="W1-wikipedia_connections_projected",
    ),
    # --- enrichment seam (E1–E4) -----------------------------------------
    pytest.param(
        "E1",
        "agent_authorities and authority_enrichment agree on wikidata_id",
        "SELECT COUNT(*) FROM agent_authorities aa "
        "JOIN authority_enrichment ae ON ae.authority_uri=aa.authority_uri "
        "WHERE aa.wikidata_id IS NOT NULL AND ae.wikidata_id IS NOT NULL "
        "AND aa.wikidata_id <> ae.wikidata_id",
        "#58/D4",
        id="E1-enrichment_wikidata_agreement",
    ),
    pytest.param(
        "E2",
        "Person birth_year is backed by enrichment person_info.birth_year",
        "SELECT COUNT(*) FROM network_agents na WHERE na.node_type='person' "
        "AND na.birth_year IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM agents a "
        "JOIN authority_enrichment ae ON ae.authority_uri=a.authority_uri "
        "WHERE a.agent_norm=na.agent_norm "
        "AND CAST(json_extract(ae.person_info,'$.birth_year') AS INTEGER)=na.birth_year)",
        "audit-E2",
        id="E2-birth_year_backed_by_enrichment",
    ),
    pytest.param(
        "E3",
        "has_wikipedia=1 implies an enrichment wikidata_id with a cache row",
        "SELECT COUNT(*) FROM network_agents na WHERE na.has_wikipedia=1 "
        "AND NOT EXISTS (SELECT 1 FROM agents a "
        "JOIN authority_enrichment ae ON ae.authority_uri=a.authority_uri "
        "JOIN wikipedia_cache wpc ON wpc.wikidata_id=ae.wikidata_id "
        "WHERE a.agent_norm=na.agent_norm)",
        "audit-E3",
        id="E3-has_wikipedia_backed_by_cache",
    ),
    pytest.param(
        "E4",
        "Non-null community implies the norm reaches wikipedia_cache categories",
        "SELECT COUNT(*) FROM network_agents na WHERE na.community IS NOT NULL "
        "AND na.node_type='person' AND NOT EXISTS "
        "(SELECT 1 FROM agents a "
        "JOIN authority_enrichment ae ON ae.authority_uri=a.authority_uri "
        "JOIN wikipedia_cache wpc ON wpc.wikidata_id=ae.wikidata_id "
        "WHERE a.agent_norm=na.agent_norm AND wpc.categories IS NOT NULL)",
        "audit-E4",
        id="E4-community_backed_by_categories",
    ),
    # --- subjects.value_he integrity (S3; coverage floors are separate) --
    pytest.param(
        "S3mojibake",
        "No U+FFFD mojibake in value_he (fix_25 contract)",
        "SELECT COUNT(*) FROM subjects "
        "WHERE value_he LIKE '%'||char(65533)||'%'",
        "audit-S3",
        id="S3-no_value_he_mojibake",
    ),
    pytest.param(
        "S3empty",
        "No empty-string value_he",
        "SELECT COUNT(*) FROM subjects WHERE value_he=''",
        "audit-S3",
        id="S3-no_empty_value_he",
    ),
    # --- imprints reversibility / sanity (M1–M3) -------------------------
    pytest.param(
        "M1",
        "No normalized imprint value without its preserved raw counterpart",
        "SELECT COUNT(*) FROM imprints WHERE "
        "(publisher_norm IS NOT NULL AND publisher_raw IS NULL) "
        "OR (place_norm IS NOT NULL AND place_raw IS NULL) "
        "OR ((date_start IS NOT NULL OR date_end IS NOT NULL) AND date_raw IS NULL)",
        "audit-M1",
        id="M1-normalized_never_without_raw",
    ),
    pytest.param(
        "M2",
        "date_start <= date_end when both present",
        "SELECT COUNT(*) FROM imprints WHERE date_start>date_end",
        "audit-M2",
        id="M2-date_start_le_date_end",
    ),
    pytest.param(
        "M3",
        "country_name never present without its source country_code",
        "SELECT COUNT(*) FROM imprints "
        "WHERE country_name IS NOT NULL AND country_code IS NULL",
        "audit-M3",
        id="M3-country_name_backed_by_code",
    ),
    # --- referential integrity (R1) --------------------------------------
    pytest.param(
        "R1",
        "Every record_scope_flags row references an existing record",
        "SELECT COUNT(*) FROM record_scope_flags f "
        "LEFT JOIN records r ON r.id=f.record_id WHERE r.id IS NULL",
        "audit-R1",
        id="R1-scope_flags_referential",
    ),
]


@pytest.mark.parametrize("invariant_id,description,sql,issue_ref", INVARIANTS)
def test_derived_invariant(conn, invariant_id, description, sql, issue_ref):
    """Each derived-artifact invariant's violation count must be zero."""
    violations = _count(conn, sql)
    assert violations == 0, (
        f"{invariant_id} [{issue_ref}] violated ({violations} rows): {description}"
    )


# --- C1: cross-DB referential integrity (sessions.db) ----------------------
def test_chat_messages_referential(sessions_conn):
    """C1 — every chat message's session_id resolves to a chat_sessions row."""
    violations = _count(
        sessions_conn,
        "SELECT COUNT(*) FROM chat_messages m "
        "WHERE m.session_id NOT IN (SELECT session_id FROM chat_sessions)",
    )
    assert violations == 0, f"C1 violated: {violations} orphan chat_messages"


# --- S1/S2: value_he coverage floors (assertions, not violation counts) ----
def test_value_he_coverage_floor(conn):
    """S1/S2 — value_he coverage must not drop below the documented floors.

    docs/current/data-quality.md:261 — row-level 83.6%, unique-heading 78.4%.
    """
    row_cov = conn.execute(
        "SELECT ROUND(100.0*SUM(value_he IS NOT NULL)/COUNT(*),1) FROM subjects"
    ).fetchone()[0]
    unique_cov = conn.execute(
        "SELECT ROUND(100.0*(SELECT COUNT(DISTINCT value) FROM subjects "
        "WHERE value_he IS NOT NULL)/(SELECT COUNT(DISTINCT value) FROM subjects),1)"
    ).fetchone()[0]
    assert row_cov >= 83.6, f"S1: row-level value_he coverage dropped to {row_cov}%"
    assert unique_cov >= 78.4, (
        f"S2: unique-heading value_he coverage dropped to {unique_cov}%"
    )
