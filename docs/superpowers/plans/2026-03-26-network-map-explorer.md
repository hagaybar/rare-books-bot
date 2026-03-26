# Network Map Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a map-based interactive network explorer that shows ~3,100 historical agents on a geographic map with connection arcs, filtering controls, and an agent detail panel.

**Architecture:** A build script materializes `network_edges` and `network_agents` tables from existing data. A FastAPI router serves filtered nodes/edges. A React page renders the map using MapLibre GL + deck.gl ArcLayer, with a Zustand-managed control bar and a slide-in agent detail panel.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, React 19, MapLibre GL JS, deck.gl, react-map-gl, Zustand, Tailwind CSS, OpenFreeMap tiles

**Spec:** `docs/superpowers/specs/2026-03-26-network-map-explorer-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `scripts/network/build_network_tables.py` | Build script: materialize `network_edges` and `network_agents` tables |
| `scripts/network/__init__.py` | Package marker |
| `data/normalization/place_geocodes.json` | Static lat/lon for top places by frequency |
| `app/api/network.py` | FastAPI router: `GET /network/map`, `GET /network/agent/{agent_norm}` |
| `app/api/network_models.py` | Pydantic models for API request/response |
| `tests/app/test_network_api.py` | API endpoint unit tests |
| `tests/scripts/network/test_build_network_tables.py` | Build script unit tests |
| `frontend/src/types/network.ts` | TypeScript interfaces |
| `frontend/src/api/network.ts` | API client functions |
| `frontend/src/stores/networkStore.ts` | Zustand store for filter state |
| `frontend/src/pages/Network.tsx` | Main page component |
| `frontend/src/components/network/MapView.tsx` | MapLibre + deck.gl map |
| `frontend/src/components/network/ControlBar.tsx` | Filter controls |
| `frontend/src/components/network/AgentPanel.tsx` | Agent detail side panel |

### Modified files

| File | Change |
|------|--------|
| `app/api/main.py` | Mount `/network` router |
| `frontend/src/App.tsx` | Add `/network` route |
| `frontend/src/components/Sidebar.tsx` | Add Network nav item to Primary section |
| `frontend/package.json` | Add maplibre-gl, react-map-gl, deck.gl dependencies |
| `frontend/vite.config.ts` | Add `/network` proxy entry for API calls |

---

## Task Dependency Graph

```
Task 1 (geocodes) ──→ Task 2 (build script) ──→ Task 3 (run build)
                                                      ↓
                      Task 4 (API models) ──→ Task 5 (API router) ──→ Task 6 (mount + test)
                                                                           ↓
Task 7 (frontend deps) ──→ Task 8 (types + API client + store)
                                    ↓
                           Task 9 (Network page + routing + sidebar)
                                    ↓
                           Task 10 (MapView component)
                                    ↓
                           Task 11 (ControlBar component)
                                    ↓
                           Task 12 (AgentPanel component)
                                    ↓
                           Task 13 (Integration + manual test)
```

Tasks 1 and 4 can run in parallel. Tasks 7 can run in parallel with Tasks 2-6.

---

### Task 1: Generate Place Geocodes File

**Files:**
- Create: `data/normalization/place_geocodes.json`

This is a static lookup mapping ~100 `place_norm` values to lat/lon coordinates. These are well-known historical cities. The top 80 places by frequency cover ~84% of all agent-place associations.

- [ ] **Step 1: Generate the geocodes file**

Write a Python script that:
1. Queries `SELECT DISTINCT place_norm FROM imprints WHERE place_norm IS NOT NULL` from `data/index/bibliographic.db`
2. Uses the OpenAI API (gpt-4o-mini) to geocode each place — these are well-known cities so accuracy is high
3. Writes the result to `data/normalization/place_geocodes.json`

The JSON format:
```json
{
  "amsterdam": {"lat": 52.3676, "lon": 4.9041, "display_name": "Amsterdam"},
  "venice": {"lat": 45.4408, "lon": 12.3155, "display_name": "Venice"}
}
```

If the OpenAI API is unavailable, manually create the file with at minimum the top 30 places:
- paris (48.8566, 2.3522), london (51.5074, -0.1278), amsterdam (52.3676, 4.9041)
- venice (45.4408, 12.3155), berlin (52.5200, 13.4050), leipzig (51.3397, 12.3731)
- jerusalem (31.7683, 35.2137), leiden (52.1601, 4.4970), frankfurt (50.1109, 8.6821)
- basel (47.5596, 7.5886), tel aviv (32.0853, 34.7818), vienna (48.2082, 16.3738)
- hamburg (53.5511, 9.9937), frankfurt am main (50.1109, 8.6821), munich (48.1351, 11.5820)
- rome (41.9028, 12.4964), halle (51.4969, 11.9688), mantua (45.1564, 10.7914)
- new york (40.7128, -74.0060), the hague (52.0705, 4.3007), prague (50.0755, 14.4378)
- geneva (46.2044, 6.1432), nuremberg (49.4521, 11.0767), cologne (50.9375, 6.9603)
- wittenberg (51.8671, 12.6484), antwerp (51.2194, 4.4025), constantinople (41.0082, 28.9784)
- safed (32.9646, 35.4960), livorno (43.5485, 10.3106), lyon (45.7640, 4.8357)

- [ ] **Step 2: Verify the file**

Run: `python3 -c "import json; d=json.load(open('data/normalization/place_geocodes.json')); print(f'{len(d)} places geocoded'); assert len(d) >= 30"`

Expected: At least 30 places geocoded, no errors.

- [ ] **Step 3: Commit**

```bash
git add data/normalization/place_geocodes.json
git commit -m "feat: add place geocodes for network map"
```

---

### Task 2: Build Script for Materialized Tables

**Files:**
- Create: `scripts/network/__init__.py`
- Create: `scripts/network/build_network_tables.py`
- Create: `tests/scripts/network/test_build_network_tables.py`
- Create: `tests/scripts/network/__init__.py`
- Create: `tests/scripts/__init__.py` (if not exists)

The build script materializes `network_edges` and `network_agents` from existing data in `bibliographic.db`.

- [ ] **Step 1: Create package markers**

Create empty `__init__.py` files for `scripts/network/`, `tests/scripts/network/`, and `tests/scripts/` (if not exists).

- [ ] **Step 2: Write the build script**

Create `scripts/network/build_network_tables.py`:

```python
"""Build materialized network_edges and network_agents tables for the Network Map Explorer.

Usage:
    python -m scripts.network.build_network_tables data/index/bibliographic.db data/normalization/place_geocodes.json
"""
import argparse
import json
import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def title_case_agent_norm(agent_norm: str) -> str:
    """Convert 'maimonides, moses' to 'Maimonides, Moses'."""
    return ", ".join(part.strip().title() for part in agent_norm.split(","))


def resolve_display_name(conn: sqlite3.Connection, agent_norm: str) -> str:
    """Resolve display name using 3-level fallback chain."""
    # Level 1: agent_authorities via agent_aliases
    row = conn.execute(
        """SELECT aa.canonical_name FROM agent_authorities aa
           JOIN agent_aliases al ON al.authority_id = aa.id
           WHERE al.alias_form_lower = ?
           LIMIT 1""",
        (agent_norm,),
    ).fetchone()
    if row and row[0]:
        return row[0]

    # Level 2: authority_enrichment.label via agents.authority_uri
    row = conn.execute(
        """SELECT DISTINCT ae.label FROM authority_enrichment ae
           JOIN agents a ON a.authority_uri = ae.authority_uri
           WHERE a.agent_norm = ? AND ae.label IS NOT NULL
           LIMIT 1""",
        (agent_norm,),
    ).fetchone()
    if row and row[0]:
        # Strip disambiguation suffixes like "(DNB12)"
        label = re.sub(r"\s*\([^)]*\)\s*$", "", row[0]).strip()
        if label:
            return label

    # Level 3: title-cased agent_norm
    return title_case_agent_norm(agent_norm)


def build_network_edges(conn: sqlite3.Connection) -> int:
    """Materialize all connection types into network_edges table."""
    conn.execute("DROP TABLE IF EXISTS network_edges")
    conn.execute("""
        CREATE TABLE network_edges (
            source_agent_norm TEXT NOT NULL,
            target_agent_norm TEXT NOT NULL,
            connection_type TEXT NOT NULL,
            confidence REAL NOT NULL,
            relationship TEXT,
            bidirectional INTEGER DEFAULT 0,
            evidence TEXT,
            UNIQUE(source_agent_norm, target_agent_norm, connection_type)
        )
    """)

    # 1. Wikipedia connections (wikilink, llm_extraction, category)
    conn.execute("""
        INSERT OR IGNORE INTO network_edges
            (source_agent_norm, target_agent_norm, connection_type, confidence,
             relationship, bidirectional, evidence)
        SELECT source_agent_norm, target_agent_norm, source_type, confidence,
               relationship, bidirectional, evidence
        FROM wikipedia_connections
    """)
    wiki_count = conn.execute("SELECT changes()").fetchone()[0]
    logger.info("Inserted %d wikipedia connections", wiki_count)

    # 2. Teacher/student from authority_enrichment.person_info
    ts_count = _build_teacher_student_edges(conn)
    logger.info("Inserted %d teacher/student connections", ts_count)

    # 3. Co-publication (agents sharing >= 2 records)
    copub_count = _build_co_publication_edges(conn)
    logger.info("Inserted %d co-publication connections", copub_count)

    # Create indexes
    conn.execute("CREATE INDEX idx_network_edges_source ON network_edges(source_agent_norm)")
    conn.execute("CREATE INDEX idx_network_edges_target ON network_edges(target_agent_norm)")
    conn.execute("CREATE INDEX idx_network_edges_type ON network_edges(connection_type)")

    total = conn.execute("SELECT count(*) FROM network_edges").fetchone()[0]
    logger.info("Total network_edges: %d", total)
    return total


def _build_teacher_student_edges(conn: sqlite3.Connection) -> int:
    """Extract teacher/student relationships from authority_enrichment.person_info."""
    rows = conn.execute(
        "SELECT authority_uri, person_info FROM authority_enrichment WHERE person_info IS NOT NULL"
    ).fetchall()

    count = 0
    for authority_uri, person_info_str in rows:
        try:
            person_info = json.loads(person_info_str)
        except (json.JSONDecodeError, TypeError):
            continue

        # Resolve this authority's agent_norm
        agent_row = conn.execute(
            "SELECT DISTINCT agent_norm FROM agents WHERE authority_uri = ? LIMIT 1",
            (authority_uri,),
        ).fetchone()
        if not agent_row:
            continue
        source_norm = agent_row[0]

        # Teachers
        for teacher_name in person_info.get("teachers", []):
            target_norm = _resolve_name_to_agent_norm(conn, teacher_name)
            if target_norm and target_norm != source_norm:
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO network_edges
                           (source_agent_norm, target_agent_norm, connection_type,
                            confidence, relationship, bidirectional)
                           VALUES (?, ?, 'teacher_student', 0.85, 'student of', 0)""",
                        (source_norm, target_norm),
                    )
                    count += conn.execute("SELECT changes()").fetchone()[0]
                except sqlite3.IntegrityError:
                    pass

        # Students
        for student_name in person_info.get("students", []):
            target_norm = _resolve_name_to_agent_norm(conn, student_name)
            if target_norm and target_norm != source_norm:
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO network_edges
                           (source_agent_norm, target_agent_norm, connection_type,
                            confidence, relationship, bidirectional)
                           VALUES (?, ?, 'teacher_student', 0.85, 'teacher of', 0)""",
                        (source_norm, target_norm),
                    )
                    count += conn.execute("SELECT changes()").fetchone()[0]
                except sqlite3.IntegrityError:
                    pass

    return count


def _resolve_name_to_agent_norm(conn: sqlite3.Connection, name: str) -> str | None:
    """Try to resolve a free-text name to an agent_norm in our collection."""
    # Try direct match on agent_norm
    name_lower = name.lower().strip()
    row = conn.execute(
        "SELECT DISTINCT agent_norm FROM agents WHERE agent_norm = ? LIMIT 1",
        (name_lower,),
    ).fetchone()
    if row:
        return row[0]

    # Try alias lookup: find alias matching name → get authority_id → find agent_norm via sibling alias
    row = conn.execute(
        """SELECT DISTINCT a.agent_norm FROM agents a
           JOIN agent_aliases al2 ON al2.alias_form_lower = a.agent_norm
           JOIN agent_aliases al1 ON al1.authority_id = al2.authority_id
           WHERE al1.alias_form_lower = ?
           LIMIT 1""",
        (name_lower,),
    ).fetchone()
    if row:
        return row[0]

    # Try partial match: "last, first" format
    parts = name_lower.split()
    if len(parts) >= 2:
        # Try "last, first"
        candidate = f"{parts[-1]}, {parts[0]}"
        row = conn.execute(
            "SELECT DISTINCT agent_norm FROM agents WHERE agent_norm = ? LIMIT 1",
            (candidate,),
        ).fetchone()
        if row:
            return row[0]

    return None


def _build_co_publication_edges(conn: sqlite3.Connection) -> int:
    """Find agent pairs sharing >= 2 records."""
    conn.execute("""
        INSERT OR IGNORE INTO network_edges
            (source_agent_norm, target_agent_norm, connection_type,
             confidence, relationship, bidirectional)
        SELECT norm1, norm2, 'co_publication',
               MIN(CAST(count_shared AS REAL) / 5.0, 1.0),
               NULL, 1
        FROM (
            SELECT a1.agent_norm as norm1, a2.agent_norm as norm2,
                   count(DISTINCT a1.record_id) as count_shared
            FROM agents a1
            JOIN agents a2 ON a1.record_id = a2.record_id
                AND a1.agent_norm < a2.agent_norm
            GROUP BY a1.agent_norm, a2.agent_norm
            HAVING count(DISTINCT a1.record_id) >= 2
        )
    """)
    return conn.execute("SELECT changes()").fetchone()[0]


def build_network_agents(
    conn: sqlite3.Connection, geocodes: dict[str, dict]
) -> int:
    """Materialize network_agents table with pre-computed place assignments."""
    conn.execute("DROP TABLE IF EXISTS network_agents")
    conn.execute("""
        CREATE TABLE network_agents (
            agent_norm TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            place_norm TEXT,
            lat REAL,
            lon REAL,
            birth_year INTEGER,
            death_year INTEGER,
            occupations TEXT,
            has_wikipedia INTEGER DEFAULT 0,
            record_count INTEGER DEFAULT 0,
            connection_count INTEGER DEFAULT 0
        )
    """)

    # Get all distinct agent_norms from agents table
    agent_norms = [
        r[0]
        for r in conn.execute("SELECT DISTINCT agent_norm FROM agents").fetchall()
    ]

    inserted = 0
    excluded_no_geocode = 0

    for agent_norm in agent_norms:
        display_name = resolve_display_name(conn, agent_norm)

        # Place assignment: most frequent, tiebreak by earliest date, then alpha
        place_row = conn.execute(
            """SELECT place_norm, count(*) as cnt, min(date_start) as earliest
               FROM imprints i
               JOIN agents a ON a.record_id = i.record_id
               WHERE a.agent_norm = ? AND i.place_norm IS NOT NULL
                 AND i.place_norm != '[sine loco]'
               GROUP BY i.place_norm
               ORDER BY cnt DESC, earliest ASC, i.place_norm ASC
               LIMIT 10""",
            (agent_norm,),
        ).fetchall()

        place_norm = None
        lat = None
        lon = None
        for p_row in place_row:
            pn = p_row[0]
            if pn in geocodes:
                place_norm = pn
                lat = geocodes[pn]["lat"]
                lon = geocodes[pn]["lon"]
                break

        # Get person info
        person_row = conn.execute(
            """SELECT ae.person_info, ae.wikidata_id
               FROM authority_enrichment ae
               JOIN agents a ON a.authority_uri = ae.authority_uri
               WHERE a.agent_norm = ?
               LIMIT 1""",
            (agent_norm,),
        ).fetchone()

        birth_year = None
        death_year = None
        occupations = "[]"
        has_wikipedia = 0

        if person_row and person_row[0]:
            try:
                pi = json.loads(person_row[0])
                birth_year = pi.get("birth_year")
                death_year = pi.get("death_year")
                occs = pi.get("occupations", [])
                occupations = json.dumps(occs) if occs else "[]"
            except (json.JSONDecodeError, TypeError):
                pass

            # Check if this agent has a Wikipedia article
            if person_row[1]:
                wiki_row = conn.execute(
                    "SELECT 1 FROM wikipedia_cache WHERE wikidata_id = ? LIMIT 1",
                    (person_row[1],),
                ).fetchone()
                if wiki_row:
                    has_wikipedia = 1

        # Record count
        record_count = conn.execute(
            "SELECT count(DISTINCT record_id) FROM agents WHERE agent_norm = ?",
            (agent_norm,),
        ).fetchone()[0]

        # Connection count (from network_edges)
        connection_count = conn.execute(
            """SELECT count(*) FROM network_edges
               WHERE source_agent_norm = ? OR target_agent_norm = ?""",
            (agent_norm, agent_norm),
        ).fetchone()[0]

        if place_norm is None:
            excluded_no_geocode += 1
            continue

        conn.execute(
            """INSERT OR REPLACE INTO network_agents
               (agent_norm, display_name, place_norm, lat, lon,
                birth_year, death_year, occupations, has_wikipedia,
                record_count, connection_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_norm, display_name, place_norm, lat, lon,
                birth_year, death_year, occupations, has_wikipedia,
                record_count, connection_count,
            ),
        )
        inserted += 1

    logger.info("Inserted %d agents, excluded %d (no geocode + no connections)", inserted, excluded_no_geocode)
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Build network tables")
    parser.add_argument("db_path", type=Path, help="Path to bibliographic.db")
    parser.add_argument("geocodes_path", type=Path, help="Path to place_geocodes.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with open(args.geocodes_path) as f:
        geocodes = json.load(f)
    logger.info("Loaded %d geocodes", len(geocodes))

    conn = sqlite3.connect(str(args.db_path))
    try:
        edge_count = build_network_edges(conn)
        agent_count = build_network_agents(conn, geocodes)
        conn.commit()
        logger.info("Done. %d edges, %d agents", edge_count, agent_count)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write tests**

Create `tests/scripts/network/test_build_network_tables.py`:

```python
"""Tests for network table build script."""
import json
import sqlite3
import pytest
from scripts.network.build_network_tables import (
    title_case_agent_norm,
    resolve_display_name,
    build_network_edges,
    build_network_agents,
)


@pytest.fixture
def db():
    """In-memory SQLite with minimal schema for testing."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY, record_id INTEGER, agent_norm TEXT,
            agent_raw TEXT, authority_uri TEXT, role_norm TEXT
        );
        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY, record_id INTEGER, place_norm TEXT,
            date_start INTEGER
        );
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY, authority_uri TEXT UNIQUE, label TEXT,
            person_info TEXT, wikidata_id TEXT
        );
        CREATE TABLE agent_authorities (
            id INTEGER PRIMARY KEY, canonical_name TEXT, canonical_name_lower TEXT
        );
        CREATE TABLE agent_aliases (
            id INTEGER PRIMARY KEY, authority_id INTEGER, alias_form_lower TEXT
        );
        CREATE TABLE wikipedia_connections (
            id INTEGER PRIMARY KEY, source_agent_norm TEXT, target_agent_norm TEXT,
            source_type TEXT, confidence REAL, relationship TEXT,
            bidirectional INTEGER DEFAULT 0, evidence TEXT
        );
        CREATE TABLE wikipedia_cache (
            id INTEGER PRIMARY KEY, wikidata_id TEXT, summary_extract TEXT
        );
    """)

    # Insert test data
    conn.executescript("""
        INSERT INTO agents VALUES (1, 100, 'smith, john', 'John Smith', 'uri:smith', 'author');
        INSERT INTO agents VALUES (2, 100, 'jones, mary', 'Mary Jones', 'uri:jones', 'printer');
        INSERT INTO agents VALUES (3, 101, 'smith, john', 'John Smith', 'uri:smith', 'author');
        INSERT INTO agents VALUES (4, 101, 'jones, mary', 'Mary Jones', 'uri:jones', 'printer');
        INSERT INTO agents VALUES (5, 102, 'doe, jane', 'Jane Doe', 'uri:doe', 'author');

        INSERT INTO imprints VALUES (1, 100, 'amsterdam', 1550);
        INSERT INTO imprints VALUES (2, 101, 'amsterdam', 1560);
        INSERT INTO imprints VALUES (3, 102, 'venice', 1570);

        INSERT INTO authority_enrichment VALUES
            (1, 'uri:smith', 'John Smith', '{"birth_year":1500,"death_year":1570,"occupations":["author"],"teachers":["Jones, Mary"],"students":[]}', 'Q111');
        INSERT INTO authority_enrichment VALUES
            (2, 'uri:jones', 'Mary Jones', '{"birth_year":1480,"death_year":1550,"occupations":["printer"],"teachers":[],"students":[]}', 'Q222');

        INSERT INTO wikipedia_connections VALUES
            (1, 'smith, john', 'doe, jane', 'wikilink', 0.75, NULL, 0, 'linked');
        INSERT INTO wikipedia_cache VALUES (1, 'Q111', 'John Smith was a scholar.');
    """)
    yield conn
    conn.close()


def test_title_case_agent_norm():
    assert title_case_agent_norm("maimonides, moses") == "Maimonides, Moses"
    assert title_case_agent_norm("smith, john") == "Smith, John"


def test_resolve_display_name_fallback(db):
    # No authority match, has enrichment label
    name = resolve_display_name(db, "smith, john")
    assert name == "John Smith"


def test_resolve_display_name_title_case(db):
    # No authority, no enrichment
    name = resolve_display_name(db, "unknown, agent")
    assert name == "Unknown, Agent"


def test_build_network_edges(db):
    count = build_network_edges(db)
    assert count >= 1  # At least the wikipedia_connection
    # Check wikilink was imported
    row = db.execute(
        "SELECT * FROM network_edges WHERE connection_type='wikilink'"
    ).fetchone()
    assert row is not None
    # Check co-publication (smith+jones share 2 records)
    copub = db.execute(
        "SELECT * FROM network_edges WHERE connection_type='co_publication'"
    ).fetchall()
    assert len(copub) >= 1


def test_build_network_agents(db):
    geocodes = {
        "amsterdam": {"lat": 52.37, "lon": 4.90, "display_name": "Amsterdam"},
        "venice": {"lat": 45.44, "lon": 12.32, "display_name": "Venice"},
    }
    build_network_edges(db)
    count = build_network_agents(db, geocodes)
    assert count >= 2  # smith and jones at least

    # Check smith is in amsterdam (2 imprints there)
    row = db.execute(
        "SELECT place_norm, lat, has_wikipedia FROM network_agents WHERE agent_norm='smith, john'"
    ).fetchone()
    assert row[0] == "amsterdam"
    assert row[1] == pytest.approx(52.37)
    assert row[2] == 1  # has wikipedia cache entry
```

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/scripts/network/test_build_network_tables.py -v`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/network/ tests/scripts/network/
git commit -m "feat: add build script for network_edges and network_agents tables"
```

---

### Task 3: Run Build Script to Populate Tables

**Files:**
- Modify: `data/index/bibliographic.db` (adds `network_edges` and `network_agents` tables)

- [ ] **Step 1: Run the build script**

```bash
poetry run python -m scripts.network.build_network_tables \
    data/index/bibliographic.db \
    data/normalization/place_geocodes.json
```

Expected: Log output showing edge and agent counts. Should produce ~45,000+ edges and ~2,000+ agents.

- [ ] **Step 2: Verify the tables**

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/index/bibliographic.db')
edges = conn.execute('SELECT count(*) FROM network_edges').fetchone()[0]
agents = conn.execute('SELECT count(*) FROM network_agents').fetchone()[0]
types = conn.execute('SELECT connection_type, count(*) FROM network_edges GROUP BY connection_type').fetchall()
placed = conn.execute('SELECT count(*) FROM network_agents WHERE lat IS NOT NULL').fetchone()[0]
print(f'Edges: {edges}')
print(f'Agents: {agents} (placed on map: {placed})')
for t, c in types:
    print(f'  {t}: {c}')
conn.close()
"
```

Expected: Edges > 40,000. Agents > 2,000. All 5 connection types present.

- [ ] **Step 3: Commit**

```bash
git add scripts/network/
git commit -m "feat: populate network tables with materialized data"
```

---

### Task 4: API Pydantic Models

**Files:**
- Create: `app/api/network_models.py`

- [ ] **Step 1: Create the models file**

Create `app/api/network_models.py`:

```python
"""Pydantic models for Network Map Explorer API."""
from pydantic import BaseModel, Field


class MapNode(BaseModel):
    agent_norm: str
    display_name: str
    lat: float | None = None
    lon: float | None = None
    place_norm: str | None = None
    birth_year: int | None = None
    death_year: int | None = None
    occupations: list[str] = Field(default_factory=list)
    connection_count: int = 0
    has_wikipedia: bool = False


class MapEdge(BaseModel):
    source: str
    target: str
    type: str
    confidence: float
    relationship: str | None = None
    bidirectional: bool = False


class MapMeta(BaseModel):
    total_agents: int
    showing: int
    total_edges: int


class MapResponse(BaseModel):
    nodes: list[MapNode]
    edges: list[MapEdge]
    meta: MapMeta


class AgentConnection(BaseModel):
    agent_norm: str
    display_name: str
    type: str
    relationship: str | None = None
    confidence: float


class AgentDetail(BaseModel):
    agent_norm: str
    display_name: str
    lat: float | None = None
    lon: float | None = None
    place_norm: str | None = None
    birth_year: int | None = None
    death_year: int | None = None
    occupations: list[str] = Field(default_factory=list)
    wikipedia_summary: str | None = None
    connections: list[AgentConnection] = Field(default_factory=list)
    record_count: int = 0
    primo_url: str | None = None
    external_links: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 2: Verify import**

Run: `poetry run python -c "from app.api.network_models import MapResponse, AgentDetail; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/api/network_models.py
git commit -m "feat: add Pydantic models for network API"
```

---

### Task 5: API Router

**Files:**
- Create: `app/api/network.py`

- [ ] **Step 1: Create the router**

Create `app/api/network.py`:

```python
"""FastAPI router for Network Map Explorer."""
import json
import logging
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.api.network_models import (
    AgentConnection,
    AgentDetail,
    MapEdge,
    MapMeta,
    MapNode,
    MapResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network", tags=["network"])

DB_PATH = Path("data/index/bibliographic.db")

VALID_CONNECTION_TYPES = {
    "teacher_student", "wikilink", "llm_extraction", "category", "co_publication"
}


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/map", response_model=MapResponse)
async def get_network_map(
    connection_types: str = Query("teacher_student", description="Comma-separated connection types"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    century: int | None = Query(None, description="Filter by century (e.g., 16 for 1500s)"),
    place: str | None = Query(None, description="Filter by place_norm"),
    role: str | None = Query(None, description="Filter by agent role"),
    limit: int = Query(150, ge=1, le=500),
) -> MapResponse:
    """Return filtered nodes and edges for the network map."""
    types = [t.strip() for t in connection_types.split(",") if t.strip()]
    invalid = set(types) - VALID_CONNECTION_TYPES
    if invalid:
        raise HTTPException(400, f"Invalid connection types: {invalid}")

    conn = _get_db()
    try:
        # Build agent filter query
        where_clauses = ["na.lat IS NOT NULL"]
        params: list = []

        if century:
            year_start = (century - 1) * 100
            year_end = year_start + 99
            where_clauses.append("""na.agent_norm IN (
                SELECT DISTINCT a.agent_norm FROM agents a
                JOIN imprints i ON a.record_id = i.record_id
                WHERE i.date_start >= ? AND i.date_start <= ?)""")
            params.extend([year_start, year_end])

        if place:
            where_clauses.append("na.place_norm = ?")
            params.append(place)

        if role:
            where_clauses.append("""na.agent_norm IN (
                SELECT DISTINCT agent_norm FROM agents WHERE role_norm = ?)""")
            params.append(role)

        where_sql = " AND ".join(where_clauses)

        # Get top agents by connection count within selected types
        type_placeholders = ",".join("?" for _ in types)
        agents_sql = f"""
            SELECT na.*, COALESCE(ec.edge_count, 0) as filtered_count
            FROM network_agents na
            LEFT JOIN (
                SELECT agent_norm, count(*) as edge_count FROM (
                    SELECT source_agent_norm as agent_norm FROM network_edges
                    WHERE connection_type IN ({type_placeholders}) AND confidence >= ?
                    UNION ALL
                    SELECT target_agent_norm FROM network_edges
                    WHERE connection_type IN ({type_placeholders}) AND confidence >= ?
                ) GROUP BY agent_norm
            ) ec ON ec.agent_norm = na.agent_norm
            WHERE {where_sql}
            ORDER BY filtered_count DESC
            LIMIT ?
        """
        agent_params = [*types, min_confidence, *types, min_confidence, *params, limit]
        rows = conn.execute(agents_sql, agent_params).fetchall()

        agent_norms = {r["agent_norm"] for r in rows}

        nodes = []
        for r in rows:
            occupations = []
            try:
                occupations = json.loads(r["occupations"]) if r["occupations"] else []
            except (json.JSONDecodeError, TypeError):
                pass
            nodes.append(MapNode(
                agent_norm=r["agent_norm"],
                display_name=r["display_name"],
                lat=r["lat"],
                lon=r["lon"],
                place_norm=r["place_norm"],
                birth_year=r["birth_year"],
                death_year=r["death_year"],
                occupations=occupations,
                connection_count=r["connection_count"],
                has_wikipedia=bool(r["has_wikipedia"]),
            ))

        # Get edges between returned agents
        if len(agent_norms) < 2:
            edges = []
        else:
            norm_list = list(agent_norms)
            norm_placeholders = ",".join("?" for _ in norm_list)
            edge_sql = f"""
                SELECT source_agent_norm, target_agent_norm, connection_type,
                       confidence, relationship, bidirectional
                FROM network_edges
                WHERE connection_type IN ({type_placeholders})
                  AND confidence >= ?
                  AND source_agent_norm IN ({norm_placeholders})
                  AND target_agent_norm IN ({norm_placeholders})
            """
            edge_params = [*types, min_confidence, *norm_list, *norm_list]
            edge_rows = conn.execute(edge_sql, edge_params).fetchall()
            edges = [
                MapEdge(
                    source=r["source_agent_norm"],
                    target=r["target_agent_norm"],
                    type=r["connection_type"],
                    confidence=r["confidence"],
                    relationship=r["relationship"],
                    bidirectional=bool(r["bidirectional"]),
                )
                for r in edge_rows
            ]

        total_agents = conn.execute(
            "SELECT count(*) FROM network_agents WHERE lat IS NOT NULL"
        ).fetchone()[0]

        return MapResponse(
            nodes=nodes,
            edges=edges,
            meta=MapMeta(
                total_agents=total_agents,
                showing=len(nodes),
                total_edges=len(edges),
            ),
        )
    finally:
        conn.close()


@router.get("/agent/{agent_norm:path}", response_model=AgentDetail)
async def get_agent_detail(agent_norm: str) -> AgentDetail:
    """Return full detail for a single agent."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM network_agents WHERE agent_norm = ?", (agent_norm,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Agent not found: {agent_norm}")

        occupations = []
        try:
            occupations = json.loads(row["occupations"]) if row["occupations"] else []
        except (json.JSONDecodeError, TypeError):
            pass

        # Wikipedia summary
        wikipedia_summary = None
        wiki_row = conn.execute(
            """SELECT wc.summary_extract FROM wikipedia_cache wc
               JOIN authority_enrichment ae ON ae.wikidata_id = wc.wikidata_id
               JOIN agents a ON a.authority_uri = ae.authority_uri
               WHERE a.agent_norm = ?
               LIMIT 1""",
            (agent_norm,),
        ).fetchone()
        if wiki_row:
            wikipedia_summary = wiki_row[0]

        # Connections
        edge_rows = conn.execute(
            """SELECT source_agent_norm, target_agent_norm, connection_type,
                      confidence, relationship
               FROM network_edges
               WHERE source_agent_norm = ? OR target_agent_norm = ?""",
            (agent_norm, agent_norm),
        ).fetchall()

        connections = []
        for er in edge_rows:
            other_norm = er["target_agent_norm"] if er["source_agent_norm"] == agent_norm else er["source_agent_norm"]
            other_row = conn.execute(
                "SELECT display_name FROM network_agents WHERE agent_norm = ?",
                (other_norm,),
            ).fetchone()
            other_display = other_row["display_name"] if other_row else other_norm
            connections.append(AgentConnection(
                agent_norm=other_norm,
                display_name=other_display,
                type=er["connection_type"],
                relationship=er["relationship"],
                confidence=er["confidence"],
            ))

        # Primo URL: link to the first record by this agent in the catalog
        primo_url = None
        try:
            from scripts.utils.primo import generate_primo_url
            first_record = conn.execute(
                "SELECT DISTINCT record_id FROM agents WHERE agent_norm = ? LIMIT 1",
                (agent_norm,),
            ).fetchone()
            if first_record:
                # record_id is the MMS ID
                primo_url = generate_primo_url(str(first_record[0]))
        except ImportError:
            pass

        # External links
        external_links = {}
        ae_row = conn.execute(
            """SELECT ae.wikidata_id, ae.wikipedia_url, ae.viaf_id
               FROM authority_enrichment ae
               JOIN agents a ON a.authority_uri = ae.authority_uri
               WHERE a.agent_norm = ?
               LIMIT 1""",
            (agent_norm,),
        ).fetchone()
        if ae_row:
            if ae_row["wikidata_id"]:
                external_links["wikidata"] = f"https://www.wikidata.org/wiki/{ae_row['wikidata_id']}"
            if ae_row["wikipedia_url"]:
                external_links["wikipedia"] = ae_row["wikipedia_url"]
            if ae_row["viaf_id"]:
                external_links["viaf"] = f"https://viaf.org/viaf/{ae_row['viaf_id']}"

        return AgentDetail(
            agent_norm=agent_norm,
            display_name=row["display_name"],
            lat=row["lat"],
            lon=row["lon"],
            place_norm=row["place_norm"],
            birth_year=row["birth_year"],
            death_year=row["death_year"],
            occupations=occupations,
            wikipedia_summary=wikipedia_summary,
            connections=connections,
            record_count=row["record_count"],
            primo_url=primo_url,
            external_links=external_links,
        )
    finally:
        conn.close()
```

- [ ] **Step 2: Verify import**

Run: `poetry run python -c "from app.api.network import router; print(f'Routes: {len(router.routes)}')"`

Expected: `Routes: 2`

- [ ] **Step 3: Commit**

```bash
git add app/api/network.py
git commit -m "feat: add network API router with map and agent detail endpoints"
```

---

### Task 6: Mount Router and Write API Tests

**Files:**
- Modify: `app/api/main.py` (add router import and mount)
- Create: `tests/app/test_network_api.py`

- [ ] **Step 1: Mount the router in main.py**

In `app/api/main.py`, add the import near the existing router imports:

```python
from app.api.network import router as network_router
```

And add the mount near the existing `include_router` calls:

```python
app.include_router(network_router)
```

- [ ] **Step 2: Write API tests**

Create `tests/app/test_network_api.py`:

```python
"""Tests for network API endpoints."""
import json
import sqlite3
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def mock_db(tmp_path):
    """Create a temporary DB with network tables for testing."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE network_agents (
            agent_norm TEXT PRIMARY KEY, display_name TEXT NOT NULL,
            place_norm TEXT, lat REAL, lon REAL,
            birth_year INTEGER, death_year INTEGER, occupations TEXT,
            has_wikipedia INTEGER DEFAULT 0, record_count INTEGER DEFAULT 0,
            connection_count INTEGER DEFAULT 0
        );
        CREATE TABLE network_edges (
            source_agent_norm TEXT, target_agent_norm TEXT,
            connection_type TEXT, confidence REAL, relationship TEXT,
            bidirectional INTEGER DEFAULT 0, evidence TEXT,
            UNIQUE(source_agent_norm, target_agent_norm, connection_type)
        );
        CREATE INDEX idx_network_edges_source ON network_edges(source_agent_norm);
        CREATE INDEX idx_network_edges_target ON network_edges(target_agent_norm);
        CREATE INDEX idx_network_edges_type ON network_edges(connection_type);
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY, record_id INTEGER, agent_norm TEXT,
            authority_uri TEXT, role_norm TEXT
        );
        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY, record_id INTEGER, place_norm TEXT,
            date_start INTEGER
        );
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY, authority_uri TEXT, wikidata_id TEXT,
            wikipedia_url TEXT, viaf_id TEXT, person_info TEXT, label TEXT
        );
        CREATE TABLE wikipedia_cache (
            id INTEGER PRIMARY KEY, wikidata_id TEXT, summary_extract TEXT
        );

        INSERT INTO network_agents VALUES
            ('smith, john', 'John Smith', 'amsterdam', 52.37, 4.90,
             1500, 1570, '["author"]', 1, 5, 10);
        INSERT INTO network_agents VALUES
            ('jones, mary', 'Mary Jones', 'venice', 45.44, 12.32,
             1480, 1550, '["printer"]', 0, 3, 5);
        INSERT INTO network_edges VALUES
            ('smith, john', 'jones, mary', 'teacher_student', 0.85,
             'teacher of', 0, NULL);
        INSERT INTO agents VALUES (1, 100, 'smith, john', 'uri:smith', 'author');
        INSERT INTO imprints VALUES (1, 100, 'amsterdam', 1550);
        INSERT INTO authority_enrichment VALUES
            (1, 'uri:smith', 'Q111', 'https://en.wikipedia.org/wiki/John_Smith',
             'V123', '{"birth_year":1500}', 'John Smith');
        INSERT INTO wikipedia_cache VALUES (1, 'Q111', 'John Smith was a scholar.');
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(mock_db):
    """Create test client with mocked DB path."""
    import app.api.network as network_mod
    from app.api.main import app

    original_path = network_mod.DB_PATH
    network_mod.DB_PATH = mock_db
    client = TestClient(app)
    yield client
    network_mod.DB_PATH = original_path


def test_get_map_default(client):
    resp = client.get("/network/map")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert "meta" in data
    assert len(data["nodes"]) <= 150


def test_get_map_with_types(client):
    resp = client.get("/network/map?connection_types=teacher_student")
    assert resp.status_code == 200
    data = resp.json()
    for edge in data["edges"]:
        assert edge["type"] == "teacher_student"


def test_get_map_invalid_type(client):
    resp = client.get("/network/map?connection_types=invalid_type")
    assert resp.status_code == 400


def test_get_agent_detail(client):
    resp = client.get("/network/agent/smith, john")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_norm"] == "smith, john"
    assert data["display_name"] == "John Smith"
    assert data["wikipedia_summary"] == "John Smith was a scholar."
    assert len(data["connections"]) >= 1
    assert "wikidata" in data["external_links"]


def test_get_agent_not_found(client):
    resp = client.get("/network/agent/nonexistent, agent")
    assert resp.status_code == 404
```

- [ ] **Step 3: Run tests**

Run: `poetry run python -m pytest tests/app/test_network_api.py -v`

Expected: All 5 tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/api/main.py app/api/network.py tests/app/test_network_api.py
git commit -m "feat: mount network router and add API tests"
```

---

### Task 7: Install Frontend Dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install map and visualization packages**

```bash
cd frontend && npm install maplibre-gl react-map-gl @deck.gl/core @deck.gl/layers @deck.gl/react
```

- [ ] **Step 2: Add Vite proxy for `/network` API routes**

In `frontend/vite.config.ts`, add a `/network` proxy entry alongside the existing proxies (e.g., `/metadata`, `/chat`):

```typescript
'/network': {
  target: 'http://localhost:8000',
  changeOrigin: true,
},
```

- [ ] **Step 3: Verify installation**

```bash
cd frontend && node -e "require('maplibre-gl'); require('react-map-gl'); require('@deck.gl/core'); console.log('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts
git commit -m "feat: add maplibre-gl, react-map-gl, deck.gl deps and Vite proxy"
```

---

### Task 8: Frontend Types, API Client, and Store

**Files:**
- Create: `frontend/src/types/network.ts`
- Create: `frontend/src/api/network.ts`
- Create: `frontend/src/stores/networkStore.ts`

- [ ] **Step 1: Create TypeScript types**

Create `frontend/src/types/network.ts`:

```typescript
export interface MapNode {
  agent_norm: string;
  display_name: string;
  lat: number | null;
  lon: number | null;
  place_norm: string | null;
  birth_year: number | null;
  death_year: number | null;
  occupations: string[];
  connection_count: number;
  has_wikipedia: boolean;
}

export interface MapEdge {
  source: string;
  target: string;
  type: string;
  confidence: number;
  relationship: string | null;
  bidirectional: boolean;
}

export interface MapMeta {
  total_agents: number;
  showing: number;
  total_edges: number;
}

export interface MapResponse {
  nodes: MapNode[];
  edges: MapEdge[];
  meta: MapMeta;
}

export interface AgentConnection {
  agent_norm: string;
  display_name: string;
  type: string;
  relationship: string | null;
  confidence: number;
}

export interface AgentDetail {
  agent_norm: string;
  display_name: string;
  lat: number | null;
  lon: number | null;
  place_norm: string | null;
  birth_year: number | null;
  death_year: number | null;
  occupations: string[];
  wikipedia_summary: string | null;
  connections: AgentConnection[];
  record_count: number;
  primo_url: string | null;
  external_links: Record<string, string>;
}

export type ConnectionType =
  | 'teacher_student'
  | 'wikilink'
  | 'llm_extraction'
  | 'category'
  | 'co_publication';

export const CONNECTION_TYPE_CONFIG: Record<ConnectionType, {
  label: string;
  color: [number, number, number];
  width: number;
}> = {
  teacher_student: { label: 'Teacher/Student', color: [59, 130, 246], width: 3 },
  wikilink: { label: 'Wikipedia Link', color: [245, 158, 11], width: 2 },
  llm_extraction: { label: 'LLM Extracted', color: [139, 92, 246], width: 2 },
  category: { label: 'Category', color: [156, 163, 175], width: 1 },
  co_publication: { label: 'Co-Publication', color: [16, 185, 129], width: 2 },
};
```

- [ ] **Step 2: Create API client**

Create `frontend/src/api/network.ts`:

```typescript
import type { MapResponse, AgentDetail } from '../types/network';

const BASE = '/network';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error ${response.status}: ${text}`);
  }
  return response.json() as Promise<T>;
}

export interface MapParams {
  connectionTypes: string[];
  minConfidence?: number;
  century?: number | null;
  place?: string | null;
  role?: string | null;
  limit?: number;
}

export async function fetchMapData(params: MapParams): Promise<MapResponse> {
  const qs = new URLSearchParams();
  qs.set('connection_types', params.connectionTypes.join(','));
  if (params.minConfidence !== undefined) qs.set('min_confidence', String(params.minConfidence));
  if (params.century) qs.set('century', String(params.century));
  if (params.place) qs.set('place', params.place);
  if (params.role) qs.set('role', params.role);
  if (params.limit) qs.set('limit', String(params.limit));

  const res = await fetch(`${BASE}/map?${qs}`);
  return handleResponse<MapResponse>(res);
}

export async function fetchAgentDetail(agentNorm: string): Promise<AgentDetail> {
  const res = await fetch(`${BASE}/agent/${encodeURIComponent(agentNorm)}`);
  return handleResponse<AgentDetail>(res);
}
```

- [ ] **Step 3: Create Zustand store**

Create `frontend/src/stores/networkStore.ts`:

```typescript
import { create } from 'zustand';
import type { ConnectionType } from '../types/network';

interface NetworkState {
  connectionTypes: ConnectionType[];
  minConfidence: number;
  century: number | null;
  place: string | null;
  role: string | null;
  agentLimit: number;

  setConnectionTypes: (types: ConnectionType[]) => void;
  toggleConnectionType: (type: ConnectionType) => void;
  setMinConfidence: (val: number) => void;
  setCentury: (val: number | null) => void;
  setPlace: (val: string | null) => void;
  setRole: (val: string | null) => void;
  setAgentLimit: (val: number) => void;
  resetFilters: () => void;
}

const DEFAULT_STATE = {
  connectionTypes: ['teacher_student'] as ConnectionType[],
  minConfidence: 0.5,
  century: null as number | null,
  place: null as string | null,
  role: null as string | null,
  agentLimit: 150,
};

export const useNetworkStore = create<NetworkState>((set) => ({
  ...DEFAULT_STATE,

  setConnectionTypes: (types) => set({ connectionTypes: types }),
  toggleConnectionType: (type) =>
    set((state) => {
      const exists = state.connectionTypes.includes(type);
      if (exists && state.connectionTypes.length === 1) return state; // keep at least one
      return {
        connectionTypes: exists
          ? state.connectionTypes.filter((t) => t !== type)
          : [...state.connectionTypes, type],
      };
    }),
  setMinConfidence: (val) => set({ minConfidence: val }),
  setCentury: (val) => set({ century: val }),
  setPlace: (val) => set({ place: val }),
  setRole: (val) => set({ role: val }),
  setAgentLimit: (val) => set({ agentLimit: val }),
  resetFilters: () => set(DEFAULT_STATE),
}));
```

- [ ] **Step 4: Verify TypeScript compilation**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/network.ts frontend/src/api/network.ts frontend/src/stores/networkStore.ts
git commit -m "feat: add network types, API client, and Zustand store"
```

---

### Task 9: Network Page, Routing, and Sidebar Navigation

**Files:**
- Create: `frontend/src/pages/Network.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Create the Network page (skeleton)**

Create `frontend/src/pages/Network.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fetchMapData, fetchAgentDetail } from '../api/network';
import { useNetworkStore } from '../stores/networkStore';
import MapView from '../components/network/MapView';
import ControlBar from '../components/network/ControlBar';
import AgentPanel from '../components/network/AgentPanel';
import type { MapNode } from '../types/network';

export default function Network() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const { connectionTypes, minConfidence, century, place, role, agentLimit } =
    useNetworkStore();

  const {
    data: mapData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['network-map', connectionTypes, minConfidence, century, place, role, agentLimit],
    queryFn: () =>
      fetchMapData({
        connectionTypes,
        minConfidence,
        century,
        place,
        role,
        limit: agentLimit,
      }),
    placeholderData: (prev) => prev, // keep previous data while loading (avoids flash)
  });

  const { data: agentDetail } = useQuery({
    queryKey: ['network-agent', selectedAgent],
    queryFn: () => fetchAgentDetail(selectedAgent!),
    enabled: !!selectedAgent,
  });

  // Show toast on API error (map retains last successful data via placeholderData)
  useEffect(() => {
    if (error) toast.error(`Map data error: ${String(error)}`);
  }, [error]);

  const handleAgentClick = (node: MapNode) => {
    setSelectedAgent(node.agent_norm);
  };

  const handleClosePanel = () => {
    setSelectedAgent(null);
  };

  return (
    <div className="flex flex-col h-full">
      <ControlBar />

      <div className="flex flex-1 relative overflow-hidden">
        <div className="flex-1 relative">
          <MapView
            nodes={mapData?.nodes ?? []}
            edges={mapData?.edges ?? []}
            selectedAgent={selectedAgent}
            onAgentClick={handleAgentClick}
            onBackgroundClick={handleClosePanel}
            isLoading={isLoading}
          />
          {/* Empty results overlay */}
          {!isLoading && mapData && mapData.nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
              <p className="text-gray-500 bg-white/80 px-4 py-2 rounded shadow">
                No agents match these filters. Try broadening your search.
              </p>
            </div>
          )}
        </div>

        {selectedAgent && agentDetail && (
          <AgentPanel agent={agentDetail} onClose={handleClosePanel} onAgentClick={(norm) => setSelectedAgent(norm)} />
        )}
      </div>

      <div className="px-4 py-2 bg-gray-50 border-t text-sm text-gray-500 flex justify-between">
        <span>
          {mapData
            ? `Showing ${mapData.meta.showing} of ${mapData.meta.total_agents} agents \u00B7 ${mapData.meta.total_edges} connections`
            : 'Loading...'}
        </span>
        {isLoading && <span className="text-blue-500">Updating...</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add route to App.tsx**

In `frontend/src/App.tsx`, add the import:

```typescript
import Network from './pages/Network';
```

Add the route inside the `<Route element={<Layout />}>` block, after the Chat route:

```tsx
<Route path="/network" element={<Network />} />
```

- [ ] **Step 3: Add to Sidebar**

In `frontend/src/components/Sidebar.tsx`:

1. Add a `network` icon to the `ICONS` constant (GlobeAlt from Heroicons outline):
```typescript
network: 'M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418',
```

2. Add the nav item to the `Primary` section, after Chat:
```typescript
{ to: '/network', label: 'Network', icon: ICONS.network },
```

- [ ] **Step 4: Verify the app compiles**

```bash
cd frontend && npx tsc --noEmit
```

Note: This may show errors for the not-yet-created components (MapView, ControlBar, AgentPanel). That's expected — they will be created in the next tasks. If only those imports cause errors, proceed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Network.tsx frontend/src/App.tsx frontend/src/components/Sidebar.tsx
git commit -m "feat: add Network page with routing and sidebar navigation"
```

---

### Task 10: MapView Component

**Files:**
- Create: `frontend/src/components/network/MapView.tsx`

This is the core component — renders the MapLibre map with deck.gl ArcLayer and ScatterplotLayer.

- [ ] **Step 1: Create the MapView component**

Create `frontend/src/components/network/MapView.tsx`:

```tsx
import { useMemo, useCallback, useRef } from 'react';
import MapGL, { NavigationControl } from 'react-map-gl/maplibre';
import { DeckGL } from '@deck.gl/react';
import { ArcLayer, ScatterplotLayer } from '@deck.gl/layers';
import type { MapNode, MapEdge } from '../../types/network';
import { CONNECTION_TYPE_CONFIG } from '../../types/network';
import 'maplibre-gl/dist/maplibre-gl.css';

interface Props {
  nodes: MapNode[];
  edges: MapEdge[];
  selectedAgent: string | null;
  onAgentClick: (node: MapNode) => void;
  onBackgroundClick: () => void;
  isLoading: boolean;
}

const INITIAL_VIEW_STATE = {
  latitude: 40,
  longitude: 15,
  zoom: 4,
  pitch: 0,
  bearing: 0,
};

const MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron';

export default function MapView({
  nodes,
  edges,
  selectedAgent,
  onAgentClick,
  onBackgroundClick,
  isLoading,
}: Props) {
  // Track whether a deck.gl object was picked on this click
  const pickedRef = useRef(false);

  // Build a lookup for node positions (use JavaScript's built-in Map, not the react-map-gl component)
  const nodeMap = useMemo(() => {
    const m = new globalThis.Map<string, MapNode>();
    for (const n of nodes) m.set(n.agent_norm, n);
    return m;
  }, [nodes]);

  // Determine which agents are connected to the selected agent
  const connectedAgents = useMemo(() => {
    if (!selectedAgent) return new Set<string>();
    const connected = new Set<string>();
    for (const e of edges) {
      if (e.source === selectedAgent) connected.add(e.target);
      if (e.target === selectedAgent) connected.add(e.source);
    }
    return connected;
  }, [edges, selectedAgent]);

  const scatterLayer = useMemo(
    () =>
      new ScatterplotLayer<MapNode>({
        id: 'agents',
        data: nodes,
        getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
        getRadius: (d) => {
          if (d.agent_norm === selectedAgent) return 12;
          if (selectedAgent && connectedAgents.has(d.agent_norm)) return 8;
          return 6;
        },
        getFillColor: (d) => {
          if (d.agent_norm === selectedAgent) return [59, 130, 246, 255];
          if (selectedAgent && connectedAgents.has(d.agent_norm))
            return [59, 130, 246, 200];
          if (selectedAgent) return [156, 163, 175, 60];
          return [59, 130, 246, 180];
        },
        radiusUnits: 'pixels',
        pickable: true,
        onClick: (info) => {
          if (info.object) {
            pickedRef.current = true;
            onAgentClick(info.object);
          }
        },
        updateTriggers: {
          getRadius: selectedAgent,
          getFillColor: selectedAgent,
        },
      }),
    [nodes, selectedAgent, connectedAgents, onAgentClick]
  );

  const arcLayer = useMemo(
    () =>
      new ArcLayer<MapEdge>({
        id: 'connections',
        data: edges,
        getSourcePosition: (d) => {
          const n = nodeMap.get(d.source);
          return [n?.lon ?? 0, n?.lat ?? 0];
        },
        getTargetPosition: (d) => {
          const n = nodeMap.get(d.target);
          return [n?.lon ?? 0, n?.lat ?? 0];
        },
        getSourceColor: (d) => {
          const config = CONNECTION_TYPE_CONFIG[d.type as keyof typeof CONNECTION_TYPE_CONFIG];
          const baseColor = config?.color ?? [156, 163, 175];
          const isHighlighted =
            selectedAgent &&
            (d.source === selectedAgent || d.target === selectedAgent);
          const opacity = selectedAgent
            ? isHighlighted
              ? Math.round(d.confidence * 255)
              : 25
            : Math.round(d.confidence * 200);
          return [...baseColor, opacity] as [number, number, number, number];
        },
        getTargetColor: (d) => {
          const config = CONNECTION_TYPE_CONFIG[d.type as keyof typeof CONNECTION_TYPE_CONFIG];
          const baseColor = config?.color ?? [156, 163, 175];
          const isHighlighted =
            selectedAgent &&
            (d.source === selectedAgent || d.target === selectedAgent);
          const opacity = selectedAgent
            ? isHighlighted
              ? Math.round(d.confidence * 255)
              : 25
            : Math.round(d.confidence * 200);
          return [...baseColor, opacity] as [number, number, number, number];
        },
        getWidth: (d) => {
          const config = CONNECTION_TYPE_CONFIG[d.type as keyof typeof CONNECTION_TYPE_CONFIG];
          const base = config?.width ?? 1;
          if (
            selectedAgent &&
            (d.source === selectedAgent || d.target === selectedAgent)
          )
            return base * 2;
          return base;
        },
        pickable: false,
        updateTriggers: {
          getSourceColor: selectedAgent,
          getTargetColor: selectedAgent,
          getWidth: selectedAgent,
        },
      }),
    [edges, nodeMap, selectedAgent]
  );

  // Handle background clicks via the MapGL onClick (fires for all map clicks).
  // We use pickedRef to distinguish: if deck.gl picked an object, skip the background handler.
  const handleMapClick = useCallback(() => {
    if (pickedRef.current) {
      pickedRef.current = false;
      return;
    }
    onBackgroundClick();
  }, [onBackgroundClick]);

  return (
    <div className="w-full h-full relative">
      {isLoading && nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center z-10 bg-white/50">
          <div className="text-gray-500">Loading map data...</div>
        </div>
      )}
      <DeckGL
        initialViewState={INITIAL_VIEW_STATE}
        controller={true}
        layers={[arcLayer, scatterLayer]}
        getTooltip={({ object }: any) => {
          if (!object) return null;
          if ('agent_norm' in object) {
            const n = object as MapNode;
            const years =
              n.birth_year || n.death_year
                ? ` (${n.birth_year ?? '?'}\u2013${n.death_year ?? '?'})`
                : '';
            return {
              text: `${n.display_name}${years}\n${n.place_norm ?? ''}\n${n.connection_count} connections`,
            };
          }
          return null;
        }}
      >
        <MapGL mapStyle={MAP_STYLE} onClick={handleMapClick}>
          <NavigationControl position="top-left" />
        </MapGL>
      </DeckGL>
    </div>
  );
}
```

Note: MapLibre's built-in clustering is an advanced feature that can be added incrementally after the base map works. The ScatterplotLayer provides agent rendering with selection highlighting. Clustering (showing "Amsterdam (47)" badges that expand on zoom) can be layered on top using a MapLibre GeoJSON source with `cluster: true` as an enhancement once the base visualization is validated.

- [ ] **Step 2: Verify compilation**

```bash
cd frontend && npx tsc --noEmit
```

May still show errors for ControlBar and AgentPanel. If only those, proceed.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/network/MapView.tsx
git commit -m "feat: add MapView component with deck.gl ArcLayer and ScatterplotLayer"
```

---

### Task 11: ControlBar Component

**Files:**
- Create: `frontend/src/components/network/ControlBar.tsx`

- [ ] **Step 1: Create the ControlBar component**

Create `frontend/src/components/network/ControlBar.tsx`:

```tsx
import { useState, useEffect, useRef } from 'react';
import { useNetworkStore } from '../../stores/networkStore';
import { CONNECTION_TYPE_CONFIG } from '../../types/network';
import type { ConnectionType } from '../../types/network';

function useDebouncedCallback(callback: (val: number) => void, delay: number) {
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  return (val: number) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => callback(val), delay);
  };
}

const CENTURIES = [
  { value: null, label: 'All' },
  { value: 15, label: '15th (1400s)' },
  { value: 16, label: '16th (1500s)' },
  { value: 17, label: '17th (1600s)' },
  { value: 18, label: '18th (1700s)' },
  { value: 19, label: '19th (1800s)' },
  { value: 20, label: '20th (1900s)' },
];

const ROLES = [
  { value: null, label: 'All Roles' },
  { value: 'author', label: 'Author' },
  { value: 'printer', label: 'Printer' },
  { value: 'publisher', label: 'Publisher' },
  { value: 'editor', label: 'Editor' },
  { value: 'translator', label: 'Translator' },
];

export default function ControlBar() {
  const {
    connectionTypes,
    toggleConnectionType,
    century,
    setCentury,
    role,
    setRole,
    agentLimit,
    setAgentLimit,
  } = useNetworkStore();

  return (
    <div className="px-4 py-3 bg-white border-b flex flex-wrap items-center gap-4">
      {/* Connection type toggles */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-700">Connections:</span>
        {(Object.entries(CONNECTION_TYPE_CONFIG) as [ConnectionType, typeof CONNECTION_TYPE_CONFIG[ConnectionType]][]).map(
          ([type, config]) => {
            const active = connectionTypes.includes(type);
            const [r, g, b] = config.color;
            return (
              <button
                key={type}
                onClick={() => toggleConnectionType(type)}
                className={`px-2 py-1 text-xs rounded border transition-colors ${
                  active
                    ? 'text-white border-transparent'
                    : 'text-gray-500 border-gray-300 bg-white hover:bg-gray-50'
                }`}
                style={active ? { backgroundColor: `rgb(${r},${g},${b})` } : undefined}
              >
                {config.label}
              </button>
            );
          }
        )}
      </div>

      {/* Century filter */}
      <div className="flex items-center gap-1">
        <span className="text-sm text-gray-600">Century:</span>
        <select
          value={century ?? ''}
          onChange={(e) => setCentury(e.target.value ? Number(e.target.value) : null)}
          className="text-sm border border-gray-300 rounded px-2 py-1"
        >
          {CENTURIES.map((c) => (
            <option key={c.label} value={c.value ?? ''}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      {/* Role filter */}
      <div className="flex items-center gap-1">
        <span className="text-sm text-gray-600">Role:</span>
        <select
          value={role ?? ''}
          onChange={(e) => setRole(e.target.value || null)}
          className="text-sm border border-gray-300 rounded px-2 py-1"
        >
          {ROLES.map((r) => (
            <option key={r.label} value={r.value ?? ''}>
              {r.label}
            </option>
          ))}
        </select>
      </div>

      {/* Agent count slider (debounced to avoid rapid API calls while dragging) */}
      <AgentSlider />
    </div>
  );
}

function AgentSlider() {
  const { agentLimit, setAgentLimit } = useNetworkStore();
  const [localValue, setLocalValue] = useState(agentLimit);
  const debouncedSet = useDebouncedCallback(setAgentLimit, 300);

  // Sync local value when store changes externally (e.g., reset)
  useEffect(() => { setLocalValue(agentLimit); }, [agentLimit]);

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-gray-600">Agents:</span>
      <input
        type="range"
        min={50}
        max={500}
        step={10}
        value={localValue}
        onChange={(e) => {
          const val = Number(e.target.value);
          setLocalValue(val);
          debouncedSet(val);
        }}
        className="w-24"
      />
      <span className="text-sm text-gray-500 w-8">{localValue}</span>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/network/ControlBar.tsx
git commit -m "feat: add ControlBar component with connection type toggles and filters"
```

---

### Task 12: AgentPanel Component

**Files:**
- Create: `frontend/src/components/network/AgentPanel.tsx`

- [ ] **Step 1: Create the AgentPanel component**

Create `frontend/src/components/network/AgentPanel.tsx`:

```tsx
import { useState } from 'react';
import type { AgentDetail } from '../../types/network';
import { CONNECTION_TYPE_CONFIG } from '../../types/network';

interface Props {
  agent: AgentDetail;
  onClose: () => void;
  onAgentClick: (agentNorm: string) => void;
}

export default function AgentPanel({ agent, onClose, onAgentClick }: Props) {
  const [expandedSummary, setExpandedSummary] = useState(false);

  const years =
    agent.birth_year || agent.death_year
      ? `${agent.birth_year ?? '?'}–${agent.death_year ?? '?'}`
      : null;

  // Group connections by type
  const groupedConnections = agent.connections.reduce(
    (acc, conn) => {
      if (!acc[conn.type]) acc[conn.type] = [];
      acc[conn.type].push(conn);
      return acc;
    },
    {} as Record<string, typeof agent.connections>
  );

  const summaryText = agent.wikipedia_summary ?? '';
  const truncatedSummary =
    summaryText.length > 500 && !expandedSummary
      ? summaryText.slice(0, 500) + '...'
      : summaryText;

  return (
    <div className="w-80 bg-white border-l shadow-lg overflow-y-auto flex-shrink-0">
      {/* Header */}
      <div className="p-4 border-b">
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {agent.display_name}
            </h2>
            {years && (
              <p className="text-sm text-gray-500">
                {years} &middot; {agent.place_norm ?? 'Unknown'}
              </p>
            )}
            {agent.occupations.length > 0 && (
              <p className="text-sm text-gray-400 mt-1">
                {agent.occupations.join(', ')}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
          >
            &times;
          </button>
        </div>
      </div>

      {/* Wikipedia Summary */}
      {summaryText && (
        <div className="p-4 border-b">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Wikipedia</h3>
          <p className="text-sm text-gray-600 leading-relaxed">
            {truncatedSummary}
          </p>
          {summaryText.length > 500 && (
            <button
              onClick={() => setExpandedSummary(!expandedSummary)}
              className="text-xs text-blue-500 hover:text-blue-700 mt-1"
            >
              {expandedSummary ? 'Show less' : 'Read more'}
            </button>
          )}
        </div>
      )}

      {/* Connections */}
      <div className="p-4 border-b">
        <h3 className="text-sm font-medium text-gray-700 mb-2">
          Connections ({agent.connections.length})
        </h3>
        {Object.entries(groupedConnections).map(([type, conns]) => {
          const config =
            CONNECTION_TYPE_CONFIG[type as keyof typeof CONNECTION_TYPE_CONFIG];
          const [r, g, b] = config?.color ?? [156, 163, 175];
          return (
            <div key={type} className="mb-3">
              <div className="flex items-center gap-2 mb-1">
                <span
                  className="w-3 h-3 rounded-full inline-block"
                  style={{ backgroundColor: `rgb(${r},${g},${b})` }}
                />
                <span className="text-xs font-medium text-gray-500 uppercase">
                  {config?.label ?? type}
                </span>
              </div>
              {conns.slice(0, 20).map((conn) => (
                <button
                  key={`${conn.agent_norm}-${type}`}
                  onClick={() => onAgentClick(conn.agent_norm)}
                  className="block w-full text-left px-2 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded truncate"
                >
                  {conn.relationship ? `${conn.relationship}: ` : ''}
                  {conn.display_name}
                </button>
              ))}
              {conns.length > 20 && (
                <p className="text-xs text-gray-400 px-2">
                  +{conns.length - 20} more
                </p>
              )}
            </div>
          );
        })}
        {agent.connections.length === 0 && (
          <p className="text-sm text-gray-400">No connections found</p>
        )}
      </div>

      {/* Catalog */}
      <div className="p-4">
        <h3 className="text-sm font-medium text-gray-700 mb-2">In Catalog</h3>
        <p className="text-sm text-gray-600 mb-2">
          {agent.record_count} record{agent.record_count !== 1 ? 's' : ''}
        </p>
        <a
          href={`/chat?q=${encodeURIComponent(`books by ${agent.display_name}`)}`}
          className="text-sm text-blue-500 hover:text-blue-700 block mb-1"
        >
          View in Chat &rarr;
        </a>
        {Object.entries(agent.external_links).map(([name, url]) => (
          <a
            key={name}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-blue-500 hover:text-blue-700 block mb-1 capitalize"
          >
            {name} &rarr;
          </a>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify full compilation**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors. All components are now created.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/network/AgentPanel.tsx
git commit -m "feat: add AgentPanel component with bio, connections, and catalog links"
```

---

### Task 13: Integration Test and Manual Verification

**Files:** None new — this task verifies everything works together.

- [ ] **Step 1: Run all backend tests**

```bash
poetry run python -m pytest tests/app/test_network_api.py tests/scripts/network/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Start the backend**

```bash
cd /home/hagaybar/projects/rare-books-bot && poetry run uvicorn app.api.main:app --reload --port 8000 &
sleep 3
```

- [ ] **Step 3: Test API endpoints**

```bash
# Test map endpoint
curl -s 'http://localhost:8000/network/map?connection_types=teacher_student&limit=10' | python3 -m json.tool | head -30

# Test agent detail endpoint (URL-encode the comma+space)
curl -s 'http://localhost:8000/network/agent/maimonides%2C%20moses' | python3 -m json.tool | head -30

# Test with multiple connection types
curl -s 'http://localhost:8000/network/map?connection_types=teacher_student,wikilink&limit=5' | python3 -m json.tool | head -20
```

Expected: JSON responses with nodes, edges, and agent details. If `maimonides, moses` doesn't exist, try any agent from the map response.

- [ ] **Step 4: Build and start frontend**

```bash
cd frontend && npm run dev &
sleep 5
```

- [ ] **Step 5: Manual verification checklist**

Open `http://localhost:5173/network` in a browser and verify:
1. Map renders with OpenFreeMap tiles centered on Europe
2. Agent dots appear on the map at their cities
3. Connection arcs visible between cities
4. Control bar shows connection type toggles, century/role dropdowns, and agent slider
5. Clicking an agent dot highlights their connections and opens the side panel
6. Side panel shows display name, dates, Wikipedia summary, connections, and catalog links
7. Clicking a connection in the panel navigates to that agent
8. Clicking the map background closes the panel
9. Changing filters in the control bar updates the map
10. Sidebar shows the "Network" item with globe icon

- [ ] **Step 6: Kill background processes and commit any fixes**

```bash
kill %1 %2 2>/dev/null  # kill uvicorn and vite
git add -A
git commit -m "feat: Network Map Explorer - integration verified"
```

---

## Rollback

If anything goes wrong, the `network_edges` and `network_agents` tables can be dropped without affecting any existing functionality:

```sql
DROP TABLE IF EXISTS network_edges;
DROP TABLE IF EXISTS network_agents;
```

All frontend changes are additive (new files + minor additions to App.tsx and Sidebar.tsx). The existing system is unaffected.
