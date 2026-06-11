"""Issue #22: the display-name resolver must never label a person with one of
their book titles, and must prefer the most-frequent (person) authority entity."""
import sqlite3

import pytest

from scripts.network.build_network_tables import resolve_display_name


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE agent_authorities (id INTEGER PRIMARY KEY, canonical_name TEXT);
        CREATE TABLE agent_aliases (id INTEGER PRIMARY KEY, authority_id INTEGER, alias_form_lower TEXT);
        CREATE TABLE agents (id INTEGER PRIMARY KEY, record_id INTEGER, agent_norm TEXT, authority_uri TEXT);
        CREATE TABLE authority_enrichment (id INTEGER PRIMARY KEY, authority_uri TEXT, wikidata_id TEXT, label TEXT);
        CREATE TABLE wikipedia_cache (id INTEGER PRIMARY KEY, wikidata_id TEXT, wikipedia_title TEXT);
        CREATE TABLE titles (id INTEGER PRIMARY KEY, record_id INTEGER, value TEXT);
    """)
    # Karo: 3 records point to the PERSON entity, 1 to the BOOK entity.
    c.executescript("""
        INSERT INTO agents VALUES (1,10,'karo, joseph','uri:person');
        INSERT INTO agents VALUES (2,11,'karo, joseph','uri:person');
        INSERT INTO agents VALUES (3,12,'karo, joseph','uri:person');
        INSERT INTO agents VALUES (4,13,'karo, joseph','uri:book');
        INSERT INTO authority_enrichment VALUES (1,'uri:person','Q467148',NULL);
        INSERT INTO authority_enrichment VALUES (2,'uri:book','Q23498022','Kessef Mishneh');
        INSERT INTO wikipedia_cache VALUES (1,'Q467148','Joseph Karo');
        INSERT INTO wikipedia_cache VALUES (2,'Q23498022','Kessef Mishneh');
    """)
    yield c
    c.close()


def test_prefers_most_frequent_person_entity_not_the_book(conn):
    assert resolve_display_name(conn, "karo, joseph") == "Joseph Karo"


def test_rejects_label_that_is_a_title_on_the_agents_records(conn):
    # Make the person entity itself carry a work-title label and zero wiki title;
    # that title also appears in the agent's records → must fall through.
    conn.execute("UPDATE wikipedia_cache SET wikipedia_title=NULL WHERE wikidata_id='Q467148'")
    conn.execute("UPDATE authority_enrichment SET label='Shulchan Aruch' WHERE authority_uri='uri:person'")
    conn.execute("INSERT INTO titles VALUES (1,10,'Shulchan Aruch')")
    name = resolve_display_name(conn, "karo, joseph")
    assert name != "Shulchan Aruch"
