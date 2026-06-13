"""Contract test: full FilterField x FilterOp support matrix (issue #56).

The 2026-06-12 seam audit (audits/2026-06-12-seam-audit/cross-layer-seams.md,
Seam B) found six planner-reachable field/op combinations that always raised
an unhandled ValueError inside build_where_clause, dying as honest-looking
empty results. This test pins the contract for all 12 fields x 4 ops = 48
cells so any future drift (new prompt wording, new coercion, removed SQL arm)
fails the build immediately.

Each cell is classified as exactly one of:

- supported     build_where_clause has a native arm. The generated SQL must
                EXECUTE against a representative schema without error, both
                negated and non-negated.
- coerced       The interpreter conversion layer (_convert_filter_dict)
                rewrites the cell into a supported shape before the Filter is
                built. The coerced filter must execute. Values it cannot
                coerce must be rejected by Filter validation, never reach SQL.
- rejected      Filter validation refuses the combination loudly with a clear
                message (pydantic ValidationError, a ValueError subclass).
- never_emitted The deprecated raw `agent` field is absent from the
                interpreter prompt's field list; its non-CONTAINS cells are
                additionally rejected by validation (defense in depth).

Invariant: NO cell may reach SQL generation as an unhandled ValueError.
"""

import sqlite3

import pytest

from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp
from scripts.query.db_adapter import build_full_query, reset_agent_alias_cache


SUPPORTED = "supported"
COERCED = "coerced"
REJECTED = "rejected"
NEVER_EMITTED = "never_emitted"

EQ, CO, RA, IN = FilterOp.EQUALS, FilterOp.CONTAINS, FilterOp.RANGE, FilterOp.IN

# The contract. One entry per (field, op) cell.
MATRIX = {
    FilterField.PUBLISHER:     {EQ: SUPPORTED, CO: SUPPORTED, RA: REJECTED, IN: SUPPORTED},
    FilterField.IMPRINT_PLACE: {EQ: SUPPORTED, CO: SUPPORTED, RA: REJECTED, IN: SUPPORTED},
    FilterField.COUNTRY:       {EQ: SUPPORTED, CO: SUPPORTED, RA: REJECTED, IN: SUPPORTED},
    # year EQUALS/CONTAINS: parseable single years are coerced to a degenerate
    # RANGE by _convert_filter_dict (#44); unparseable values and $step_N refs
    # are rejected by Filter validation (#56 B3).
    FilterField.YEAR:          {EQ: COERCED, CO: COERCED, RA: SUPPORTED, IN: SUPPORTED},
    FilterField.LANGUAGE:      {EQ: SUPPORTED, CO: SUPPORTED, RA: REJECTED, IN: SUPPORTED},
    FilterField.TITLE:         {EQ: SUPPORTED, CO: SUPPORTED, RA: REJECTED, IN: SUPPORTED},
    FilterField.SUBJECT:       {EQ: SUPPORTED, CO: SUPPORTED, RA: REJECTED, IN: SUPPORTED},
    # physical_desc has no exact-match representation (MARC 300 strings are
    # free text); only substring semantics are supported.
    FilterField.PHYSICAL_DESC: {EQ: REJECTED, CO: SUPPORTED, RA: REJECTED, IN: SUPPORTED},
    FilterField.AGENT:         {EQ: NEVER_EMITTED, CO: SUPPORTED, RA: NEVER_EMITTED, IN: NEVER_EMITTED},
    FilterField.AGENT_NORM:    {EQ: SUPPORTED, CO: SUPPORTED, RA: REJECTED, IN: SUPPORTED},
    FilterField.AGENT_ROLE:    {EQ: SUPPORTED, CO: SUPPORTED, RA: REJECTED, IN: SUPPORTED},
    FilterField.AGENT_TYPE:    {EQ: SUPPORTED, CO: SUPPORTED, RA: REJECTED, IN: SUPPORTED},
}

# Representative single values per field (match the fixture data below).
SCALAR_VALUE = {
    FilterField.PUBLISHER: "bragadin",
    FilterField.IMPRINT_PLACE: "venice",
    FilterField.COUNTRY: "italy",
    FilterField.YEAR: "1565",
    FilterField.LANGUAGE: "heb",
    FilterField.TITLE: "Shulchan Aruch",
    FilterField.SUBJECT: "Jewish law",
    FilterField.PHYSICAL_DESC: "map",
    FilterField.AGENT: "bomberg",
    FilterField.AGENT_NORM: "bomberg, daniel",
    FilterField.AGENT_ROLE: "printer",
    FilterField.AGENT_TYPE: "personal",
}

LIST_VALUE = {
    FilterField.PUBLISHER: ["bragadin", "proops"],
    FilterField.IMPRINT_PLACE: ["venice", "amsterdam"],
    FilterField.COUNTRY: ["italy", "netherlands"],
    FilterField.YEAR: ["1520", "1698"],
    FilterField.LANGUAGE: ["heb", "lat"],
    FilterField.TITLE: ["Shulchan Aruch", "Beit Yosef"],
    FilterField.SUBJECT: ["Jewish law", "Talmud"],
    FilterField.PHYSICAL_DESC: ["map", "ill"],
    FilterField.AGENT: ["bomberg", "karo"],
    FilterField.AGENT_NORM: ["bomberg, daniel", "karo, yosef"],
    FilterField.AGENT_ROLE: ["printer", "author"],
    FilterField.AGENT_TYPE: ["personal", "corporate"],
}


def _filter_kwargs(field: FilterField, op: FilterOp) -> dict:
    """Build constructor kwargs for one matrix cell."""
    if op == FilterOp.RANGE:
        return {"field": field, "op": op, "start": 1500, "end": 1600}
    if op == FilterOp.IN:
        return {"field": field, "op": op, "value": LIST_VALUE[field]}
    return {"field": field, "op": op, "value": SCALAR_VALUE[field]}


def _raw_filter_dict(field: FilterField, op: FilterOp) -> dict:
    """Same cell as a raw LLM-style dict (input to _convert_filter_dict)."""
    kwargs = _filter_kwargs(field, op)
    raw = {"field": field.value, "op": op.value}
    for key in ("value", "start", "end"):
        if key in kwargs:
            raw[key] = kwargs[key]
    return raw


@pytest.fixture
def matrix_db(tmp_path):
    """Representative schema covering every table build_where_clause touches.

    Mirrors the test_db fixture in tests/scripts/chat/test_executor.py
    (records 990001234 / 990005678 / 990009999).
    """
    db_path = tmp_path / "matrix.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE records (
            id INTEGER PRIMARY KEY, mms_id TEXT UNIQUE, source_file TEXT,
            created_at TEXT, jsonl_line_number INTEGER
        );
        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY, record_id INTEGER, occurrence INTEGER,
            date_raw TEXT, place_raw TEXT, publisher_raw TEXT,
            manufacturer_raw TEXT, source_tags TEXT,
            date_start INTEGER, date_end INTEGER, date_label TEXT,
            date_confidence REAL, date_method TEXT,
            place_norm TEXT, place_display TEXT, place_confidence REAL,
            place_method TEXT,
            publisher_norm TEXT, publisher_display TEXT,
            publisher_confidence REAL, publisher_method TEXT,
            country_code TEXT, country_name TEXT
        );
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY, record_id INTEGER, agent_index INTEGER,
            agent_raw TEXT, agent_type TEXT, role_raw TEXT, role_source TEXT,
            authority_uri TEXT,
            agent_norm TEXT, agent_confidence REAL, agent_method TEXT,
            agent_notes TEXT,
            role_norm TEXT, role_confidence REAL, role_method TEXT,
            provenance_json TEXT
        );
        CREATE TABLE subjects (
            id INTEGER PRIMARY KEY, record_id INTEGER, value TEXT,
            source_tag TEXT, scheme TEXT, heading_lang TEXT,
            authority_uri TEXT, parts TEXT, source TEXT, value_he TEXT
        );
        CREATE TABLE titles (
            id INTEGER PRIMARY KEY, record_id INTEGER,
            title_type TEXT, value TEXT, source TEXT
        );
        CREATE TABLE languages (
            id INTEGER PRIMARY KEY, record_id INTEGER, code TEXT, source TEXT
        );
        CREATE TABLE physical_descriptions (
            id INTEGER PRIMARY KEY, record_id INTEGER, value TEXT, source TEXT
        );
        CREATE TABLE agent_authorities (
            id INTEGER PRIMARY KEY, canonical_name TEXT,
            canonical_name_lower TEXT,
            agent_type TEXT, dates_active TEXT, date_start INTEGER,
            date_end INTEGER, notes TEXT, sources TEXT, confidence REAL,
            authority_uri TEXT, wikidata_id TEXT, viaf_id TEXT, nli_id TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE agent_aliases (
            id INTEGER PRIMARY KEY, authority_id INTEGER,
            alias_form TEXT, alias_form_lower TEXT,
            alias_type TEXT, script TEXT, language TEXT, is_primary INTEGER,
            priority INTEGER, notes TEXT, created_at TEXT
        );
        CREATE VIRTUAL TABLE subjects_fts USING fts5(mms_id, value, content='');
        CREATE VIRTUAL TABLE titles_fts USING fts5(
            title_type UNINDEXED, value,
            content=titles, content_rowid=id
        );

        INSERT INTO records VALUES (1, '990001234', 't.xml', '2024-01-01', 1);
        INSERT INTO records VALUES (2, '990005678', 't.xml', '2024-01-01', 2);
        INSERT INTO records VALUES (3, '990009999', 't.xml', '2024-01-01', 3);

        INSERT INTO imprints VALUES
            (1, 1, 0, '1565', 'Venice', 'Bragadin', NULL, '["264"]',
             1565, 1565, '1565', 0.99, 'exact',
             'venice', 'Venice', 0.95, 'place_alias_map',
             'bragadin', 'Bragadin', 0.95, 'publisher_authority',
             'it', 'italy');
        INSERT INTO imprints VALUES
            (2, 2, 0, '1698', 'Amsterdam', 'Proops', NULL, '["264"]',
             1698, 1698, '1698', 0.99, 'exact',
             'amsterdam', 'Amsterdam', 0.95, 'place_alias_map',
             'proops', 'Proops', 0.95, 'publisher_authority',
             'ne', 'netherlands');
        INSERT INTO imprints VALUES
            (3, 3, 0, '1520', 'Venice', 'Bomberg', NULL, '["264"]',
             1520, 1520, '1520', 0.99, 'exact',
             'venice', 'Venice', 0.95, 'place_alias_map',
             'bomberg', 'Bomberg', 0.95, 'publisher_authority',
             'it', 'italy');

        INSERT INTO agents VALUES
            (1, 3, 0, 'Daniel Bomberg', 'personal', 'printer',
             'relator_code', 'http://nli.org/auth/2',
             'bomberg, daniel', 0.95, 'base_clean', NULL,
             'printer', 0.95, 'relator_code', '[]');
        INSERT INTO agents VALUES
            (2, 1, 0, 'Joseph Karo', 'personal', 'author',
             'relator_code', 'http://nli.org/auth/1',
             'karo, yosef', 0.95, 'base_clean', NULL,
             'author', 0.95, 'relator_code', '[]');

        INSERT INTO agent_authorities VALUES
            (1, 'Daniel Bomberg', 'daniel bomberg', 'personal', NULL,
             NULL, NULL, NULL, '[]', 0.95, 'http://nli.org/auth/2',
             NULL, NULL, NULL, '2024-01-01', '2024-01-01');
        INSERT INTO agent_aliases VALUES
            (1, 1, 'Bombergi, Daniel', 'bombergi, daniel', 'variant',
             'latin', NULL, 0, 0, NULL, '2024-01-01');

        INSERT INTO subjects VALUES
            (1, 1, 'Jewish law', '650', 'lcsh', 'eng', NULL, '{}', '[]', NULL);
        INSERT INTO subjects VALUES
            (2, 3, 'Talmud', '650', 'lcsh', 'eng', NULL, '{}', '[]', NULL);

        INSERT INTO titles VALUES (1, 1, 'main', 'Shulchan Aruch', '["245"]');
        INSERT INTO titles VALUES (2, 2, 'main', 'Beit Yosef', '["245"]');

        INSERT INTO languages VALUES (1, 1, 'heb', '008/35-37');
        INSERT INTO languages VALUES (2, 2, 'lat', '008/35-37');

        INSERT INTO physical_descriptions VALUES
            (1, 2, '2 v. : ill., 10 folded maps', '["300"]');

        INSERT INTO subjects_fts(rowid, mms_id, value)
            SELECT s.id, r.mms_id, s.value
            FROM subjects s JOIN records r ON s.record_id = r.id;
        INSERT INTO titles_fts(titles_fts) VALUES('rebuild');
    """)
    conn.commit()
    conn.row_factory = sqlite3.Row

    reset_agent_alias_cache()
    yield conn
    conn.close()
    reset_agent_alias_cache()


def _execute(conn: sqlite3.Connection, filt: Filter) -> list:
    """Run one filter through build_full_query against the matrix schema."""
    plan = QueryPlan(query_text="matrix", filters=[filt])
    sql, params = build_full_query(plan, conn=conn)
    rows = conn.execute(sql, params).fetchall()
    return [row[0] for row in rows]


ALL_CELLS = [
    (field, op)
    for field in FilterField
    for op in FilterOp
]


def test_matrix_covers_all_48_cells():
    """Every FilterField x FilterOp combination must be classified."""
    assert len(ALL_CELLS) == 48
    for field, op in ALL_CELLS:
        assert field in MATRIX, f"unclassified field {field}"
        assert op in MATRIX[field], f"unclassified cell {field} x {op}"


@pytest.mark.parametrize(
    "field,op",
    ALL_CELLS,
    ids=[f"{f.value}-{o.value}" for f, o in ALL_CELLS],
)
@pytest.mark.parametrize("negate", [False, True], ids=["plain", "negated"])
def test_matrix_cell(matrix_db, field, op, negate):
    """Each cell behaves exactly as classified — no unhandled ValueError
    may ever reach SQL generation."""
    classification = MATRIX[field][op]

    if classification == SUPPORTED:
        filt = Filter(**_filter_kwargs(field, op), negate=negate)
        _execute(matrix_db, filt)  # must not raise

    elif classification == COERCED:
        from scripts.chat.interpreter import _convert_filter_dict

        raw = _raw_filter_dict(field, op)
        raw["negate"] = negate
        filt = _convert_filter_dict(raw)
        assert MATRIX[filt.field][filt.op] == SUPPORTED, (
            f"coercion of {field.value} x {op.value} produced "
            f"{filt.field.value} x {filt.op.value}, which is not supported"
        )
        assert filt.negate is negate
        _execute(matrix_db, filt)  # must not raise

    elif classification in (REJECTED, NEVER_EMITTED):
        with pytest.raises(ValueError):
            Filter(**_filter_kwargs(field, op), negate=negate)

    else:  # pragma: no cover - defensive
        pytest.fail(f"unknown classification {classification!r}")


class TestSupportedCellSemantics:
    """Spot checks that the new arms match the right records (issue #56)."""

    def test_subject_equals_exact_value_match(self, matrix_db):
        """B1: subject EQUALS is an exact heading match."""
        hits = _execute(
            matrix_db,
            Filter(field=FilterField.SUBJECT, op=FilterOp.EQUALS, value="Jewish law"),
        )
        assert hits == ["990001234"]

    def test_year_in_is_per_year_not_min_max_range(self, matrix_db):
        """B2: year IN [1520, 1698] must NOT match the 1565 record (a
        min-max RANGE coercion would wrongly include it)."""
        hits = _execute(
            matrix_db,
            Filter(field=FilterField.YEAR, op=FilterOp.IN, value=["1520", "1698"]),
        )
        assert set(hits) == {"990005678", "990009999"}

    def test_year_equals_parseable_coerced_and_matches(self, matrix_db):
        """#44 / B3: year EQUALS '1565' is coerced to RANGE 1565-1565."""
        from scripts.chat.interpreter import _convert_filter_dict

        filt = _convert_filter_dict(
            {"field": "year", "op": "EQUALS", "value": "1565"}
        )
        assert filt.op == FilterOp.RANGE
        assert (filt.start, filt.end) == (1565, 1565)
        assert _execute(matrix_db, filt) == ["990001234"]

    def test_year_equals_unparseable_rejected_loudly(self):
        """B3: an unparseable year EQUALS must fail validation with a clear
        message, not die later in SQL generation."""
        with pytest.raises(ValueError, match="year"):
            Filter(field=FilterField.YEAR, op=FilterOp.EQUALS, value="uncertain")

    def test_year_equals_step_ref_rejected_loudly(self):
        """B3: no step produces years — a $step_N year EQUALS is nonsense
        and must be rejected at validation."""
        with pytest.raises(ValueError, match="year"):
            Filter(field=FilterField.YEAR, op=FilterOp.EQUALS, value="$step_0")

    def test_year_in_non_integer_rejected_loudly(self):
        """B2: year IN with a non-integer member must fail validation."""
        with pytest.raises(ValueError, match="year"):
            Filter(
                field=FilterField.YEAR, op=FilterOp.IN, value=["1520", "circa"]
            )

    def test_title_in_promoted_list_executes(self, matrix_db):
        """B4: the interpreter promotes EQUALS lists to IN for any field —
        title IN must execute as exact membership."""
        from scripts.chat.interpreter import _convert_filter_dict

        filt = _convert_filter_dict(
            {
                "field": "title",
                "op": "EQUALS",
                "value": ["Shulchan Aruch", "Beit Yosef"],
            }
        )
        assert filt.op == FilterOp.IN
        assert set(_execute(matrix_db, filt)) == {"990001234", "990005678"}

    def test_negated_place_in_excludes_listed_cities(self, matrix_db):
        """B5: negated multi-value place IN must execute as NOT IN."""
        hits = _execute(
            matrix_db,
            Filter(
                field=FilterField.IMPRINT_PLACE,
                op=FilterOp.IN,
                value=["venice"],
                negate=True,
            ),
        )
        assert set(hits) == {"990005678"}

    def test_language_contains_matches_substring(self, matrix_db):
        """B6: language CONTAINS must execute (LIKE on the code column)."""
        hits = _execute(
            matrix_db,
            Filter(field=FilterField.LANGUAGE, op=FilterOp.CONTAINS, value="he"),
        )
        assert hits == ["990001234"]

    def test_agent_role_contains_matches_substring(self, matrix_db):
        """B6: agent_role CONTAINS must execute."""
        hits = _execute(
            matrix_db,
            Filter(field=FilterField.AGENT_ROLE, op=FilterOp.CONTAINS, value="print"),
        )
        assert hits == ["990009999"]

    def test_agent_norm_in_resolves_aliases(self, matrix_db):
        """agent_norm IN keeps the alias-resolution branch of EQUALS."""
        hits = _execute(
            matrix_db,
            Filter(
                field=FilterField.AGENT_NORM,
                op=FilterOp.IN,
                value=["bombergi daniel"],  # alias form, comma-stripped
            ),
        )
        assert hits == ["990009999"]

    def test_physical_desc_in_is_any_of_substring(self, matrix_db):
        """physical_desc IN is any-of CONTAINS (the field's only match mode)."""
        hits = _execute(
            matrix_db,
            Filter(
                field=FilterField.PHYSICAL_DESC,
                op=FilterOp.IN,
                value=["map", "atlas"],
            ),
        )
        assert hits == ["990005678"]

    def test_in_list_of_ints_stringified_at_conversion(self, matrix_db):
        """LLMs emit year lists as JSON ints; conversion must stringify."""
        from scripts.chat.interpreter import _convert_filter_dict

        filt = _convert_filter_dict(
            {"field": "year", "op": "IN", "value": [1520, 1698]}
        )
        assert filt.value == ["1520", "1698"]
        assert set(_execute(matrix_db, filt)) == {"990005678", "990009999"}


class TestDeprecatedAgentField:
    """The raw `agent` field is deprecated: CONTAINS-only, never emitted."""

    def test_agent_absent_from_interpreter_prompt_field_list(self):
        import re
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT

        field_lines = [
            line
            for line in INTERPRETER_SYSTEM_PROMPT.splitlines()
            if "`field`: one of" in line
        ]
        assert field_lines, "prompt no longer documents the filter field list"
        for line in field_lines:
            assert "agent_norm" in line
            assert not re.search(r"\bagent\b(?!_)", line), (
                "deprecated raw `agent` field must not be offered to the LLM"
            )

    def test_agent_non_contains_rejected_with_pointer_to_agent_norm(self):
        with pytest.raises(ValueError, match="agent_norm"):
            Filter(field=FilterField.AGENT, op=FilterOp.EQUALS, value="bomberg")
