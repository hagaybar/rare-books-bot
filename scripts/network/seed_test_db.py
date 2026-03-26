"""Create a seed database with prerequisite tables for build_network_tables.

This script creates a bibliographic.db with realistic test data in all the
tables that build_network_tables depends on: agents, imprints,
authority_enrichment, agent_authorities, agent_aliases, wikipedia_connections,
wikipedia_cache.

Usage:
    python -m scripts.network.seed_test_db data/index/bibliographic.db
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


# Realistic agent data for rare books collection
AGENTS = [
    # (agent_norm, agent_raw, authority_uri, roles_and_records)
    ("maimonides, moses", "Maimonides, Moses, 1138-1204", "uri:nli/000003188",
     [("author", [1, 2, 3, 4, 5])]),
    ("rashi", "Rashi, 1040-1105", "uri:nli/000004521",
     [("author", [6, 7, 8])]),
    ("ibn ezra, abraham", "Ibn Ezra, Abraham ben Meir, 1089-1167", "uri:nli/000005678",
     [("author", [9, 10, 11, 12])]),
    ("kimhi, david", "Kimhi, David, 1160-1235", "uri:nli/000006789",
     [("author", [13, 14, 15])]),
    ("judah ha-levi", "Judah, ha-Levi, 1075-1141", "uri:nli/000007890",
     [("author", [16, 17])]),
    ("nachmanides", "Nachmanides, 1194-1270", "uri:nli/000008901",
     [("author", [18, 19, 20, 21])]),
    ("gersonides", "Gersonides, 1288-1344", "uri:nli/000009012",
     [("author", [22, 23])]),
    ("joseph karo", "Karo, Joseph ben Ephraim, 1488-1575", "uri:nli/000010123",
     [("author", [24, 25, 26, 27, 28])]),
    ("isaac luria", "Luria, Isaac ben Solomon, 1534-1572", "uri:nli/000011234",
     [("author", [29, 30])]),
    ("moses isserles", "Isserles, Moses ben Israel, 1530-1572", "uri:nli/000012345",
     [("author", [25, 31, 32])]),  # Shares records with Karo

    # Printers
    ("daniel bomberg", "Bomberg, Daniel, -1553", "uri:nli/000020001",
     [("printer", [1, 6, 9, 13, 16, 24])]),
    ("soncino, gershom", "Soncino, Gershom ben Moses, active 1489-1534", "uri:nli/000020002",
     [("printer", [2, 7, 10, 14, 22])]),
    ("eliezer toledano", "Toledano, Eliezer, active 16th century", "uri:nli/000020003",
     [("printer", [3, 17, 18])]),
    ("marco antonio giustiniani", "Giustiniani, Marco Antonio", "uri:nli/000020004",
     [("printer", [4, 8, 11, 15, 19])]),
    ("bragadin, alvise", "Bragadin, Alvise, active 1550-1574", "uri:nli/000020005",
     [("printer", [5, 12, 20, 23, 26])]),
    ("plantin, christophe", "Plantin, Christophe, 1520-1589", "uri:nli/000020006",
     [("printer", [27, 28, 29])]),
    ("elzevir, louis", "Elzevir, Louis, 1540-1617", "uri:nli/000020007",
     [("printer", [30, 31, 32])]),
    ("manasseh ben israel", "Manasseh ben Israel, 1604-1657", "uri:nli/000020008",
     [("printer", [33, 34, 35]), ("author", [33])]),
    ("uri phoebus", "Uri Phoebus ben Aaron ha-Levi", "uri:nli/000020009",
     [("printer", [36, 37, 38, 39])]),
    ("athias, joseph", "Athias, Joseph, 1635-1700", "uri:nli/000020010",
     [("printer", [40, 41, 42])]),

    # More authors
    ("saadia gaon", "Saadia Gaon, 882-942", "uri:nli/000030001",
     [("author", [6, 43])]),
    ("bahya ibn paquda", "Bahya ibn Paquda, active 11th century", "uri:nli/000030002",
     [("author", [44, 45])]),
    ("solomon ibn gabirol", "Ibn Gabirol, Solomon ben Judah, 1021-1058", "uri:nli/000030003",
     [("author", [46, 47])]),
    ("hasdai crescas", "Crescas, Hasdai, 1340-1410", "uri:nli/000030004",
     [("author", [48, 49])]),
    ("isaac abravanel", "Abravanel, Isaac, 1437-1508", "uri:nli/000030005",
     [("author", [50, 51, 52])]),
    ("obadiah bertinoro", "Bertinoro, Obadiah ben Abraham, active 15th century", "uri:nli/000030006",
     [("author", [53, 54])]),
    ("moses almosnino", "Almosnino, Moses ben Baruch, 1515-1580", "uri:nli/000030007",
     [("author", [55, 56])]),
    ("abraham zacuto", "Zacuto, Abraham ben Samuel, 1452-1515", "uri:nli/000030008",
     [("author", [57])]),
    ("david gans", "Gans, David, 1541-1613", "uri:nli/000030009",
     [("author", [58, 59])]),
    ("leone modena", "Modena, Leone, 1571-1648", "uri:nli/000030010",
     [("author", [60, 61, 33])]),  # Shares record 33 with Manasseh

    # More printers/publishers
    ("johannes froben", "Froben, Johannes, 1460-1527", "uri:nli/000040001",
     [("printer", [43, 44, 48])]),
    ("aldus manutius", "Manutius, Aldus, 1449-1515", "uri:nli/000040002",
     [("printer", [45, 46, 49, 50])]),
    ("proops, solomon", "Proops, Solomon ben Joseph, 1658-1734", "uri:nli/000040003",
     [("printer", [51, 52, 53, 54, 55, 58, 59])]),
    ("foa, tobias", "Foa, Tobias, active 1550-1573", "uri:nli/000040004",
     [("printer", [47, 56])]),
    ("bak, israel", "Bak, Israel, 1797-1874", "uri:nli/000040005",
     [("printer", [57, 60])]),
    ("widow of johannes jansson", "Widow of Jansson, Johannes", "uri:nli/000040006",
     [("printer", [61])]),
]

# Record-to-place mappings with realistic distribution
IMPRINTS = {
    # Venice - major Hebrew printing center
    1: ("venice", 1520), 2: ("venice", 1490), 4: ("venice", 1530),
    5: ("venice", 1548), 6: ("venice", 1525), 8: ("venice", 1545),
    9: ("venice", 1488), 11: ("venice", 1540), 12: ("venice", 1555),
    13: ("venice", 1521), 15: ("venice", 1532), 19: ("venice", 1549),
    20: ("venice", 1560), 23: ("venice", 1550), 26: ("venice", 1565),
    # Amsterdam - second major center
    30: ("amsterdam", 1590), 31: ("amsterdam", 1595), 32: ("amsterdam", 1600),
    33: ("amsterdam", 1632), 34: ("amsterdam", 1635), 35: ("amsterdam", 1640),
    36: ("amsterdam", 1645), 37: ("amsterdam", 1650), 38: ("amsterdam", 1655),
    39: ("amsterdam", 1660), 40: ("amsterdam", 1665), 41: ("amsterdam", 1670),
    42: ("amsterdam", 1675), 51: ("amsterdam", 1510), 58: ("amsterdam", 1612),
    59: ("amsterdam", 1615), 61: ("amsterdam", 1638),
    # Constantinople/Istanbul
    3: ("constantinople", 1510), 17: ("constantinople", 1505),
    18: ("constantinople", 1512), 55: ("constantinople", 1570),
    56: ("constantinople", 1575),
    # Soncino/Italy
    7: ("soncino", 1485), 10: ("soncino", 1488), 14: ("soncino", 1490),
    22: ("soncino", 1492),
    # Other places
    16: ("fez", 1520), 24: ("venice", 1565), 25: ("krakow", 1580),
    27: ("antwerp", 1570), 28: ("antwerp", 1572), 29: ("safed", 1575),
    43: ("basel", 1515), 44: ("basel", 1490), 45: ("venice", 1498),
    46: ("venice", 1505), 47: ("sabbioneta", 1555), 48: ("basel", 1500),
    49: ("ferrara", 1555), 50: ("venice", 1505), 52: ("amsterdam", 1515),
    53: ("venice", 1548), 54: ("venice", 1550), 57: ("lisbon", 1496),
    60: ("safed", 1832),
}

# Authority enrichment with person_info
ENRICHMENTS = [
    ("uri:nli/000003188", "Maimonides", "Q188772",
     {"birth_year": 1138, "death_year": 1204, "occupations": ["philosopher", "rabbi", "physician"],
      "teachers": ["Joseph ibn Migash"], "students": ["Abraham ben Moses ben Maimon"]}),
    ("uri:nli/000004521", "Rashi", "Q172253",
     {"birth_year": 1040, "death_year": 1105, "occupations": ["rabbi", "commentator"],
      "teachers": [], "students": ["Samuel ben Meir"]}),
    ("uri:nli/000005678", "Abraham ibn Ezra", "Q313195",
     {"birth_year": 1089, "death_year": 1167, "occupations": ["poet", "grammarian", "astronomer"],
      "teachers": [], "students": []}),
    ("uri:nli/000006789", "David Kimhi", "Q311313",
     {"birth_year": 1160, "death_year": 1235, "occupations": ["grammarian", "rabbi"],
      "teachers": [], "students": []}),
    ("uri:nli/000007890", "Judah ha-Levi", "Q312516",
     {"birth_year": 1075, "death_year": 1141, "occupations": ["poet", "philosopher"],
      "teachers": ["Isaac Alfasi"], "students": []}),
    ("uri:nli/000008901", "Nachmanides", "Q233265",
     {"birth_year": 1194, "death_year": 1270, "occupations": ["rabbi", "philosopher", "physician"],
      "teachers": [], "students": ["Solomon ben Adret"]}),
    ("uri:nli/000009012", "Gersonides", "Q316232",
     {"birth_year": 1288, "death_year": 1344, "occupations": ["philosopher", "mathematician", "astronomer"],
      "teachers": [], "students": []}),
    ("uri:nli/000010123", "Joseph Karo", "Q362332",
     {"birth_year": 1488, "death_year": 1575, "occupations": ["rabbi", "posek"],
      "teachers": [], "students": ["Moses Isserles"]}),
    ("uri:nli/000011234", "Isaac Luria", "Q315513",
     {"birth_year": 1534, "death_year": 1572, "occupations": ["rabbi", "kabbalist"],
      "teachers": [], "students": ["Hayim Vital"]}),
    ("uri:nli/000012345", "Moses Isserles", "Q313543",
     {"birth_year": 1530, "death_year": 1572, "occupations": ["rabbi", "posek"],
      "teachers": ["Joseph Karo"], "students": []}),
    ("uri:nli/000020001", "Daniel Bomberg", "Q437882",
     {"birth_year": None, "death_year": 1553, "occupations": ["printer"],
      "teachers": [], "students": []}),
    ("uri:nli/000020002", "Gershom Soncino", "Q464432",
     {"birth_year": None, "death_year": 1534, "occupations": ["printer"],
      "teachers": [], "students": []}),
    ("uri:nli/000020004", "Marco Antonio Giustiniani", None,
     {"occupations": ["printer"], "teachers": [], "students": []}),
    ("uri:nli/000020005", "Alvise Bragadin", None,
     {"occupations": ["printer"], "teachers": [], "students": []}),
    ("uri:nli/000020006", "Christophe Plantin", "Q380360",
     {"birth_year": 1520, "death_year": 1589, "occupations": ["printer", "publisher"],
      "teachers": [], "students": []}),
    ("uri:nli/000020007", "Louis Elzevir", "Q477888",
     {"birth_year": 1540, "death_year": 1617, "occupations": ["printer", "publisher"],
      "teachers": [], "students": []}),
    ("uri:nli/000020008", "Manasseh ben Israel", "Q353695",
     {"birth_year": 1604, "death_year": 1657, "occupations": ["rabbi", "printer", "author"],
      "teachers": [], "students": []}),
    ("uri:nli/000020010", "Joseph Athias", "Q2414990",
     {"birth_year": 1635, "death_year": 1700, "occupations": ["printer"],
      "teachers": [], "students": []}),
    ("uri:nli/000030001", "Saadia Gaon", "Q314127",
     {"birth_year": 882, "death_year": 942, "occupations": ["rabbi", "philosopher"],
      "teachers": [], "students": []}),
    ("uri:nli/000030002", "Bahya ibn Paquda", "Q314855",
     {"birth_year": None, "death_year": None, "occupations": ["philosopher", "rabbi"],
      "teachers": [], "students": []}),
    ("uri:nli/000030003", "Solomon ibn Gabirol", "Q317143",
     {"birth_year": 1021, "death_year": 1058, "occupations": ["poet", "philosopher"],
      "teachers": [], "students": []}),
    ("uri:nli/000030004", "Hasdai Crescas", "Q327843",
     {"birth_year": 1340, "death_year": 1410, "occupations": ["philosopher", "rabbi"],
      "teachers": [], "students": ["Joseph Albo"]}),
    ("uri:nli/000030005", "Isaac Abravanel", "Q355312",
     {"birth_year": 1437, "death_year": 1508, "occupations": ["statesman", "philosopher", "commentator"],
      "teachers": [], "students": []}),
    ("uri:nli/000030007", "Moses Almosnino", None,
     {"birth_year": 1515, "death_year": 1580, "occupations": ["rabbi", "author"],
      "teachers": [], "students": []}),
    ("uri:nli/000030008", "Abraham Zacuto", "Q310832",
     {"birth_year": 1452, "death_year": 1515, "occupations": ["astronomer", "historian"],
      "teachers": [], "students": []}),
    ("uri:nli/000030009", "David Gans", "Q1174432",
     {"birth_year": 1541, "death_year": 1613, "occupations": ["historian", "astronomer"],
      "teachers": [], "students": []}),
    ("uri:nli/000030010", "Leone Modena", "Q967321",
     {"birth_year": 1571, "death_year": 1648, "occupations": ["rabbi", "poet", "author"],
      "teachers": [], "students": []}),
    ("uri:nli/000040001", "Johannes Froben", "Q216048",
     {"birth_year": 1460, "death_year": 1527, "occupations": ["printer"],
      "teachers": [], "students": []}),
    ("uri:nli/000040002", "Aldus Manutius", "Q212972",
     {"birth_year": 1449, "death_year": 1515, "occupations": ["printer", "humanist"],
      "teachers": [], "students": []}),
    ("uri:nli/000040003", "Solomon Proops", None,
     {"birth_year": 1658, "death_year": 1734, "occupations": ["printer"],
      "teachers": [], "students": []}),
    ("uri:nli/000040005", "Israel Bak", None,
     {"birth_year": 1797, "death_year": 1874, "occupations": ["printer"],
      "teachers": [], "students": []}),
]

# Wikipedia connections (cross-references found by enrichment pipeline)
WIKI_CONNECTIONS = [
    ("maimonides, moses", "judah ha-levi", "wikilink", 0.80, "contemporary reference", 0),
    ("maimonides, moses", "ibn ezra, abraham", "wikilink", 0.75, "cited in article", 0),
    ("maimonides, moses", "nachmanides", "wikilink", 0.85, "philosophical debate", 0),
    ("maimonides, moses", "gersonides", "wikilink", 0.70, "philosophical tradition", 0),
    ("maimonides, moses", "joseph karo", "wikilink", 0.65, "legal tradition", 0),
    ("maimonides, moses", "saadia gaon", "wikilink", 0.75, "philosophical lineage", 0),
    ("maimonides, moses", "bahya ibn paquda", "wikilink", 0.60, "mentioned together", 0),
    ("maimonides, moses", "hasdai crescas", "wikilink", 0.70, "critic of Maimonides", 0),
    ("maimonides, moses", "isaac abravanel", "wikilink", 0.65, "commentator on Maimonides", 0),
    ("rashi", "kimhi, david", "wikilink", 0.70, "exegetical tradition", 0),
    ("rashi", "nachmanides", "wikilink", 0.75, "commentary tradition", 0),
    ("rashi", "obadiah bertinoro", "wikilink", 0.65, "commentary tradition", 0),
    ("ibn ezra, abraham", "solomon ibn gabirol", "wikilink", 0.80, "Andalusian poetry", 0),
    ("ibn ezra, abraham", "judah ha-levi", "wikilink", 0.85, "personal connection", 0),
    ("judah ha-levi", "solomon ibn gabirol", "wikilink", 0.80, "poetry tradition", 0),
    ("nachmanides", "kimhi, david", "wikilink", 0.60, "contemporaries", 0),
    ("nachmanides", "joseph karo", "wikilink", 0.70, "legal tradition", 0),
    ("joseph karo", "moses isserles", "wikilink", 0.95, "Shulchan Aruch", 1),
    ("joseph karo", "isaac luria", "wikilink", 0.75, "Safed circle", 0),
    ("isaac luria", "joseph karo", "category", 0.80, "Safed kabbalists", 1),
    ("daniel bomberg", "soncino, gershom", "wikilink", 0.75, "rival printers", 0),
    ("daniel bomberg", "marco antonio giustiniani", "wikilink", 0.70, "Venetian printers", 0),
    ("daniel bomberg", "bragadin, alvise", "category", 0.65, "Hebrew printers Venice", 0),
    ("soncino, gershom", "aldus manutius", "wikilink", 0.60, "Italian printers", 0),
    ("plantin, christophe", "elzevir, louis", "wikilink", 0.70, "Low Countries printers", 0),
    ("manasseh ben israel", "leone modena", "wikilink", 0.75, "contemporary rabbis", 0),
    ("manasseh ben israel", "athias, joseph", "wikilink", 0.70, "Amsterdam printers", 0),
    ("athias, joseph", "uri phoebus", "wikilink", 0.65, "Amsterdam Hebrew printers", 0),
    ("proops, solomon", "athias, joseph", "wikilink", 0.60, "Amsterdam printers succession", 0),
    ("hasdai crescas", "gersonides", "wikilink", 0.75, "philosophical tradition", 0),
    ("hasdai crescas", "isaac abravanel", "wikilink", 0.70, "Spanish Jewish philosophy", 0),
    ("isaac abravanel", "solomon ibn gabirol", "category", 0.55, "Spanish Jewish thinkers", 0),
    ("david gans", "leone modena", "wikilink", 0.55, "Renaissance Jewish scholars", 0),
    ("moses almosnino", "joseph karo", "wikilink", 0.60, "Ottoman Jewish scholars", 0),
    ("abraham zacuto", "isaac abravanel", "wikilink", 0.70, "Portuguese Jewish scholars", 0),
    # LLM extraction connections
    ("maimonides, moses", "rashi", "llm_extraction", 0.90, "Both major medieval commentators", 0),
    ("joseph karo", "moses isserles", "llm_extraction", 0.95, "Shulchan Aruch and Mappah", 1),
    ("daniel bomberg", "soncino, gershom", "llm_extraction", 0.85, "Competing Hebrew presses", 0),
    ("manasseh ben israel", "athias, joseph", "llm_extraction", 0.80, "Amsterdam Hebrew printing", 0),
    ("isaac luria", "moses isserles", "llm_extraction", 0.65, "16th century rabbis", 0),
]

# Agent authorities and aliases
AGENT_AUTHORITIES = [
    (1, "Moses Maimonides", "moses maimonides", "personal",
     [("maimonides, moses", "primary"), ("moses maimonides", "variant_spelling"),
      ("rambam", "acronym"), ("musa ibn maymun", "cross_script")]),
    (2, "Rashi", "rashi", "personal",
     [("rashi", "primary"), ("solomon ben isaac", "variant_spelling"),
      ("shlomo yitzhaki", "cross_script")]),
    (3, "Abraham ibn Ezra", "abraham ibn ezra", "personal",
     [("ibn ezra, abraham", "primary"), ("abraham ibn ezra", "variant_spelling")]),
    (4, "David Kimhi", "david kimhi", "personal",
     [("kimhi, david", "primary"), ("david kimhi", "variant_spelling"),
      ("radak", "acronym")]),
    (5, "Judah ha-Levi", "judah ha-levi", "personal",
     [("judah ha-levi", "primary"), ("yehuda halevi", "cross_script")]),
    (6, "Nachmanides", "nachmanides", "personal",
     [("nachmanides", "primary"), ("moses ben nahman", "variant_spelling"),
      ("ramban", "acronym")]),
    (7, "Joseph Karo", "joseph karo", "personal",
     [("joseph karo", "primary"), ("yosef karo", "cross_script")]),
    (8, "Moses Isserles", "moses isserles", "personal",
     [("moses isserles", "primary"), ("rema", "acronym")]),
    (9, "Daniel Bomberg", "daniel bomberg", "personal",
     [("daniel bomberg", "primary")]),
    (10, "Gershom Soncino", "gershom soncino", "personal",
     [("soncino, gershom", "primary"), ("gershom soncino", "variant_spelling")]),
]


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all prerequisite tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mms_id TEXT NOT NULL UNIQUE,
            source_file TEXT NOT NULL,
            created_at TEXT NOT NULL,
            jsonl_line_number INTEGER
        );

        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            agent_index INTEGER NOT NULL DEFAULT 0,
            agent_raw TEXT NOT NULL,
            agent_type TEXT NOT NULL DEFAULT 'personal',
            role_raw TEXT,
            role_source TEXT,
            authority_uri TEXT,
            agent_norm TEXT NOT NULL,
            agent_confidence REAL NOT NULL DEFAULT 0.9,
            agent_method TEXT NOT NULL DEFAULT 'base_clean',
            agent_notes TEXT,
            role_norm TEXT NOT NULL DEFAULT 'author',
            role_confidence REAL NOT NULL DEFAULT 0.9,
            role_method TEXT NOT NULL DEFAULT 'relator_code',
            provenance_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_agents_agent_norm ON agents(agent_norm);
        CREATE INDEX IF NOT EXISTS idx_agents_record_id ON agents(record_id);
        CREATE INDEX IF NOT EXISTS idx_agents_authority_uri ON agents(authority_uri);

        CREATE TABLE IF NOT EXISTS imprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            occurrence INTEGER NOT NULL DEFAULT 0,
            date_raw TEXT,
            place_raw TEXT,
            publisher_raw TEXT,
            manufacturer_raw TEXT,
            source_tags TEXT NOT NULL DEFAULT '[]',
            date_start INTEGER,
            date_end INTEGER,
            date_label TEXT,
            date_confidence REAL,
            date_method TEXT,
            place_norm TEXT,
            place_display TEXT,
            place_confidence REAL,
            place_method TEXT,
            publisher_norm TEXT,
            publisher_display TEXT,
            publisher_confidence REAL,
            publisher_method TEXT,
            country_code TEXT,
            country_name TEXT,
            FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_imprints_record_id ON imprints(record_id);
        CREATE INDEX IF NOT EXISTS idx_imprints_place_norm ON imprints(place_norm);

        CREATE TABLE IF NOT EXISTS authority_enrichment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            authority_uri TEXT NOT NULL UNIQUE,
            nli_id TEXT,
            wikidata_id TEXT,
            viaf_id TEXT,
            isni_id TEXT,
            loc_id TEXT,
            label TEXT,
            description TEXT,
            person_info TEXT,
            place_info TEXT,
            image_url TEXT,
            wikipedia_url TEXT,
            source TEXT NOT NULL DEFAULT 'wikidata',
            confidence REAL DEFAULT 0.9,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_enrichment_authority_uri ON authority_enrichment(authority_uri);
        CREATE INDEX IF NOT EXISTS idx_enrichment_wikidata ON authority_enrichment(wikidata_id);

        CREATE TABLE IF NOT EXISTS agent_authorities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL,
            canonical_name_lower TEXT NOT NULL,
            agent_type TEXT NOT NULL DEFAULT 'personal',
            dates_active TEXT,
            date_start INTEGER,
            date_end INTEGER,
            notes TEXT,
            sources TEXT,
            confidence REAL NOT NULL DEFAULT 0.5,
            authority_uri TEXT,
            wikidata_id TEXT,
            viaf_id TEXT,
            nli_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_auth_canonical_lower ON agent_authorities(canonical_name_lower);

        CREATE TABLE IF NOT EXISTS agent_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            authority_id INTEGER NOT NULL REFERENCES agent_authorities(id) ON DELETE CASCADE,
            alias_form TEXT NOT NULL,
            alias_form_lower TEXT NOT NULL,
            alias_type TEXT NOT NULL DEFAULT 'primary',
            script TEXT DEFAULT 'latin',
            language TEXT,
            is_primary INTEGER NOT NULL DEFAULT 0,
            priority INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_agent_alias_authority ON agent_aliases(authority_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_alias_form_lower ON agent_aliases(alias_form_lower);

        CREATE TABLE IF NOT EXISTS wikipedia_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_agent_norm TEXT NOT NULL,
            target_agent_norm TEXT NOT NULL,
            source_wikidata_id TEXT,
            target_wikidata_id TEXT,
            relationship TEXT,
            tags TEXT,
            confidence REAL NOT NULL,
            source_type TEXT NOT NULL,
            evidence TEXT,
            bidirectional INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(source_agent_norm, target_agent_norm, source_type)
        );

        CREATE TABLE IF NOT EXISTS wikipedia_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wikidata_id TEXT NOT NULL,
            wikipedia_title TEXT,
            summary_extract TEXT,
            categories TEXT,
            see_also_titles TEXT,
            article_wikilinks TEXT,
            sections_json TEXT,
            name_variants TEXT,
            page_id INTEGER,
            revision_id INTEGER,
            language TEXT DEFAULT 'en',
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            UNIQUE(wikidata_id, language)
        );
    """)


def populate_data(conn: sqlite3.Connection) -> None:
    """Insert realistic test data."""
    now = datetime.utcnow().isoformat() + "Z"
    expires = (datetime.utcnow() + timedelta(days=90)).isoformat() + "Z"

    # Create records (61 bibliographic records)
    for rec_id in range(1, 62):
        conn.execute(
            "INSERT INTO records (id, mms_id, source_file, created_at) VALUES (?, ?, ?, ?)",
            (rec_id, f"99000{rec_id:04d}", "records.xml", now),
        )

    # Create agents
    agent_id = 0
    for agent_norm, agent_raw, authority_uri, roles_records in AGENTS:
        for role, record_ids in roles_records:
            for rec_id in record_ids:
                agent_id += 1
                conn.execute(
                    """INSERT INTO agents
                       (id, record_id, agent_index, agent_raw, agent_type, authority_uri,
                        agent_norm, agent_confidence, agent_method, role_norm,
                        role_confidence, role_method, provenance_json)
                       VALUES (?, ?, 0, ?, 'personal', ?, ?, 0.9, 'base_clean', ?, 0.9, 'relator_code', '[]')""",
                    (agent_id, rec_id, agent_raw, authority_uri, agent_norm, role),
                )

    # Create imprints
    for rec_id, (place, year) in IMPRINTS.items():
        conn.execute(
            """INSERT INTO imprints
               (record_id, occurrence, place_norm, place_display, place_confidence,
                place_method, date_start, date_end, date_confidence, date_method, source_tags)
               VALUES (?, 0, ?, ?, 0.95, 'place_alias_map', ?, ?, 0.99, 'exact', '["264"]')""",
            (rec_id, place, place.title(), year, year),
        )

    # Create authority enrichment
    for auth_uri, label, wikidata_id, person_info in ENRICHMENTS:
        conn.execute(
            """INSERT INTO authority_enrichment
               (authority_uri, label, wikidata_id, person_info, source, confidence, fetched_at, expires_at)
               VALUES (?, ?, ?, ?, 'wikidata', 0.9, ?, ?)""",
            (auth_uri, label, wikidata_id, json.dumps(person_info), now, expires),
        )

    # Create agent authorities and aliases
    for auth_id, canonical, canonical_lower, agent_type, aliases in AGENT_AUTHORITIES:
        conn.execute(
            """INSERT INTO agent_authorities
               (id, canonical_name, canonical_name_lower, agent_type, confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, 0.9, ?, ?)""",
            (auth_id, canonical, canonical_lower, agent_type, now, now),
        )
        for alias_form, alias_type in aliases:
            conn.execute(
                """INSERT INTO agent_aliases
                   (authority_id, alias_form, alias_form_lower, alias_type, is_primary, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (auth_id, alias_form.title(), alias_form.lower(), alias_type,
                 1 if alias_type == "primary" else 0, now),
            )

    # Create wikipedia connections
    for src, tgt, src_type, conf, evidence, bidir in WIKI_CONNECTIONS:
        conn.execute(
            """INSERT OR IGNORE INTO wikipedia_connections
               (source_agent_norm, target_agent_norm, source_type, confidence,
                evidence, bidirectional, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (src, tgt, src_type, conf, evidence, bidir, now),
        )

    # Create wikipedia cache entries for agents with wikidata_id
    for auth_uri, label, wikidata_id, person_info in ENRICHMENTS:
        if wikidata_id:
            conn.execute(
                """INSERT OR IGNORE INTO wikipedia_cache
                   (wikidata_id, wikipedia_title, summary_extract, fetched_at, expires_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (wikidata_id, label, f"{label} was a notable figure.", now, expires),
            )

    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Create seed database for network tables")
    parser.add_argument("db_path", type=Path, help="Path to create bibliographic.db")
    args = parser.parse_args()

    args.db_path.parent.mkdir(parents=True, exist_ok=True)

    # Safety: refuse to overwrite production database
    PRODUCTION_DB = Path("data/index/bibliographic.db")
    if args.db_path.resolve() == (Path.cwd() / PRODUCTION_DB).resolve() or \
       args.db_path.name == "bibliographic.db" and "index" in str(args.db_path):
        print("ERROR: Cannot seed the production database path.")
        print(f"  Refused: {args.db_path}")
        print("  Use a different path, e.g.: data/index/test_seed.db")
        sys.exit(1)

    # Remove existing if present
    if args.db_path.exists():
        args.db_path.unlink()

    conn = sqlite3.connect(str(args.db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        create_schema(conn)
        populate_data(conn)

        # Print summary
        agents = conn.execute("SELECT count(*) FROM agents").fetchone()[0]
        records = conn.execute("SELECT count(*) FROM records").fetchone()[0]
        imprints = conn.execute("SELECT count(*) FROM imprints").fetchone()[0]
        enrichments = conn.execute("SELECT count(*) FROM authority_enrichment").fetchone()[0]
        wiki_conn = conn.execute("SELECT count(*) FROM wikipedia_connections").fetchone()[0]
        wiki_cache = conn.execute("SELECT count(*) FROM wikipedia_cache").fetchone()[0]
        auth = conn.execute("SELECT count(*) FROM agent_authorities").fetchone()[0]
        aliases = conn.execute("SELECT count(*) FROM agent_aliases").fetchone()[0]

        print(f"Seed database created: {args.db_path}")
        print(f"  Records:          {records}")
        print(f"  Agent rows:       {agents}")
        print(f"  Imprints:         {imprints}")
        print(f"  Enrichments:      {enrichments}")
        print(f"  Wiki connections: {wiki_conn}")
        print(f"  Wiki cache:       {wiki_cache}")
        print(f"  Authorities:      {auth}")
        print(f"  Aliases:          {aliases}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
