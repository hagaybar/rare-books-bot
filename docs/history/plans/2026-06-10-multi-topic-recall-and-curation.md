# Multi-Topic Recall & Curatorial Routing Implementation Plan (Issue #2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the "0 records at 65% confidence" failure for multi-concept curatorial queries (issue #2) by adding a deterministic relaxation ladder, a curated concept→vocabulary bridge, a physical-description search field, and curatorial routing — while preserving the CandidateSet + Evidence contract.

**Architecture:** All recall fixes are deterministic and LLM-free (executor + db_adapter + a curated JSON concept map), testable without API calls. The LLM interpreter is only re-prompted to decompose coordinate topics and route curatorial intent; even if it still emits a bad AND-plan, the executor's relaxation ladder recovers. No DB writes, no re-ingestion, no embeddings (B7 explicitly out of scope).

**Tech Stack:** Python 3.12, Pydantic, SQLite (FTS5), pytest, existing scholar pipeline (`scripts/chat/`), existing query layer (`scripts/query/`, `scripts/schemas/query_plan.py`).

---

## Verified research facts (do not re-derive)

- `scripts/query/db_adapter.py:471` joins ALL filter conditions with `" AND "`. `subject CONTAINS art AND maps AND cartography` → 0 records (mathematically forced).
- The three ChatGPT-cited works **exist in our DB with different, real MMS IDs** (ChatGPT fabricated the IDs but the titles are real):
  - Reland, *Palaestina ex monumentis veteribus illustrata* (1714) = `9933749415904146` — subject contains "Bible -- Geography"
  - *Survey of Western Palestine* = `990014484230204146` (+ sibling volumes) — subject contains "Israel -- Geography"
  - *Bilder-Geographie* (1736) = `990020368010204146` — subject contains "Human geography"
  - All three are caught by `subject CONTAINS "geography"` (FTS token match).
- DB signal counts (2,796 records): subject FTS token `geography`=18, `art`=47, `engraving`=27, `illustration`=12, `maps`=1, `cartography`=1; subject phrase `"description and travel"`=65; title FTS `atlas`=3, `geographie`=7; `physical_descriptions.value LIKE '%map%'`=**106** (strongest cartography signal; table already exists — MARC 300; no re-ingest needed).
- Raw MARC export has **no 655 fields** (`grep -c '"655"' data/canonical/records.jsonl` = 0) → genre/form indexing (issue item B6) is moot for current data; physical_descriptions covers it. Re-check at next MARC export.
- `M3Tables.PHYSICAL_DESCRIPTIONS` already exists in `scripts/marc/m3_contract.py:29`; check `M3Columns.PhysicalDescriptions` (~line 160) for exact column constants.
- The interpreter prompt **already has a `curation` intent** and the executor has a `sample` action with `strategy="notable"` wired to `curation_engine.score_for_curation` (`scripts/chat/executor.py:1083`).
- `_resolve_scope` (`scripts/chat/executor.py:274`) supports only `full_collection` / `$step_N` / `$previous_results` — **no union of steps** (needed so `sample` can curate over several retrieve steps).
- `RecordSet` model: `scripts/chat/plan_models.py:152` (`mms_ids`, `total_count`, `filters_applied`). Additive field is backward-compatible.
- Real FTS schemas (needed for the test fixture): `titles_fts` = fts5(content=titles, content_rowid=id, value + mms_id/title_type UNINDEXED); `subjects_fts` = contentless fts5(mms_id, value, content='') with rowid = subjects.id.
- Tests: `tests/scripts/chat/test_executor.py` has a `test_db` fixture (full schema, **no FTS tables yet**). Integration tests use `DB_PATH = Path("data/index/bibliographic.db")` + skip-if-missing (`tests/integration/test_publisher_authority.py:20`).
- Eval queries end at `q30` in `data/eval/queries.json`.
- ⚠️ Ladder design constraint: concept expansion must run **inside** the OR-union rung (per-topic: direct hits ∪ expanded hits). A separate "OR first, expand only if still 0" ladder would stop at noisy `art` OR-hits and never reach the geography expansion — targets would be missed.
- 💰 Cost rule (user memory): no live LLM calls without explicit approval. All tests below are LLM-free. Live end-to-end `/chat` verification is a separate, user-approved step.

## File structure

| File | Action | Responsibility |
|---|---|---|
| `data/normalization/concept_maps/concept_map.json` | Create | Curated concept→vocabulary expansions (en+he keys), every term validated against the DB |
| `scripts/query/concept_bridge.py` | Create | Load map, `expand_concept(term)` lookup (pure, deterministic) |
| `tests/scripts/query/test_concept_bridge.py` | Create | Unit + DB-validation tests |
| `scripts/schemas/query_plan.py` | Modify | Add `FilterField.PHYSICAL_DESC` |
| `scripts/query/db_adapter.py` | Modify | EXISTS-subquery condition for physical_desc CONTAINS |
| `tests/scripts/query/test_db_adapter.py` | Modify | physical_desc filter tests |
| `scripts/chat/plan_models.py` | Modify | `RecordSet.relaxations: list[str]` |
| `scripts/chat/executor.py` | Modify | Extract `_run_filter_query`, add relaxation ladder, scope union (`$step_0+$step_1`) |
| `tests/scripts/chat/test_executor.py` | Modify | FTS fixture + ladder + scope-union tests |
| `scripts/chat/interpreter.py` | Modify | Prompt: coordinate-topics rule, physical_desc field, curatorial worked example |
| `tests/scripts/chat/test_interpreter.py` | Modify | Prompt integrity tests |
| `tests/integration/test_multi_topic_recall.py` | Create | THE acceptance test for issue #2 (real DB, LLM-free) |
| `data/eval/queries.json` | Modify | Add q31 (the Hebrew query) |
| `scripts/qa/verify_external_citations.py` | Create | Harness: check externally-claimed (title, mms_id) pairs against DB |
| `tests/scripts/qa/test_verify_external_citations.py` | Create | Harness tests (uses the real fabricated-ID example) |
| `data/qa/external_claims/2026-06-10-chatgpt-cartography.json` | Create | The ChatGPT answer's claims as a claims file |
| `docs/current/query-engine.md` | Modify | Document ladder, concept bridge, physical_desc, scope union |
| `docs/current/qa-framework.md` | Modify | Document the verification harness |

---

### Task 1: Concept→vocabulary bridge

**Files:**
- Create: `data/normalization/concept_maps/concept_map.json`
- Create: `scripts/query/concept_bridge.py`
- Create: `tests/scripts/query/test_concept_bridge.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the concept→vocabulary bridge (issue #2, item B5).

The bridge maps user concepts (e.g. "cartography", "מפות") to catalog
vocabulary that actually exists in this collection. Deterministic, no LLM.
"""
import sqlite3
from pathlib import Path

import pytest

from scripts.query.concept_bridge import Expansion, expand_concept, load_concept_map

DB_PATH = Path("data/index/bibliographic.db")


def test_expand_known_english_concept():
    expansions = expand_concept("cartography")
    assert Expansion(field="subject", value="geography") in expansions
    assert Expansion(field="physical_desc", value="map") in expansions


def test_expand_hebrew_alias():
    assert expand_concept("מפות") == expand_concept("cartography")


def test_expand_is_case_insensitive():
    assert expand_concept("Cartography") == expand_concept("cartography")


def test_unknown_term_returns_empty():
    assert expand_concept("astronomy-of-the-incas") == []


def test_expansion_fields_are_valid_filter_fields():
    from scripts.schemas.query_plan import FilterField
    valid = {f.value for f in FilterField}
    for expansions in load_concept_map().values():
        for exp in expansions:
            assert exp.field in valid


@pytest.mark.integration
def test_every_expansion_term_hits_the_db():
    """Issue requirement: expansions must be validated against headings
    that actually exist in the DB. A zero-hit term is vocabulary drift."""
    if not DB_PATH.exists():
        pytest.skip("Bibliographic database not available")
    conn = sqlite3.connect(str(DB_PATH))
    try:
        seen: set[tuple[str, str]] = set()
        for expansions in load_concept_map().values():
            for exp in expansions:
                key = (exp.field, exp.value)
                if key in seen:
                    continue
                seen.add(key)
                if exp.field == "subject":
                    n = conn.execute(
                        "SELECT COUNT(*) FROM subjects_fts WHERE subjects_fts MATCH ?",
                        (f'"{exp.value}"',),
                    ).fetchone()[0]
                elif exp.field == "title":
                    n = conn.execute(
                        "SELECT COUNT(*) FROM titles_fts WHERE titles_fts MATCH ?",
                        (f'"{exp.value}"',),
                    ).fetchone()[0]
                else:  # physical_desc
                    n = conn.execute(
                        "SELECT COUNT(*) FROM physical_descriptions "
                        "WHERE LOWER(value) LIKE LOWER(?)",
                        (f"%{exp.value}%",),
                    ).fetchone()[0]
                assert n >= 1, f"zero-hit expansion {key} — remove or fix it"
    finally:
        conn.close()
```

- [ ] **Step 2: Run tests, verify they fail with ModuleNotFoundError**

Run: `poetry run pytest tests/scripts/query/test_concept_bridge.py -q`
Expected: collection error `No module named 'scripts.query.concept_bridge'`

- [ ] **Step 3: Create the concept map JSON**

`data/normalization/concept_maps/concept_map.json` — every term below was pre-validated against the DB (counts in research facts). Do NOT add terms without checking them.

```json
{
  "version": 1,
  "description": "Curated concept-to-catalog-vocabulary expansions. Every expansion term must match >=1 record in bibliographic.db (enforced by tests/scripts/query/test_concept_bridge.py). Fields: subject (FTS token/phrase), title (FTS token), physical_desc (substring LIKE).",
  "concepts": [
    {
      "canonical": "cartography",
      "aliases": ["maps", "map", "atlas", "atlases", "mapping", "קרטוגרפיה", "מפות", "מפה", "אטלס", "אטלסים"],
      "expansions": [
        {"field": "subject", "value": "geography"},
        {"field": "subject", "value": "maps"},
        {"field": "subject", "value": "cartography"},
        {"field": "subject", "value": "description and travel"},
        {"field": "title", "value": "atlas"},
        {"field": "title", "value": "geographie"},
        {"field": "physical_desc", "value": "map"}
      ]
    },
    {
      "canonical": "art",
      "aliases": ["arts", "אמנות", "אומנות"],
      "expansions": [
        {"field": "subject", "value": "art"},
        {"field": "subject", "value": "engraving"},
        {"field": "subject", "value": "illustration"}
      ]
    },
    {
      "canonical": "geography",
      "aliases": ["גאוגרפיה", "גיאוגרפיה"],
      "expansions": [
        {"field": "subject", "value": "geography"},
        {"field": "subject", "value": "description and travel"},
        {"field": "title", "value": "geographie"}
      ]
    }
  ]
}
```

- [ ] **Step 4: Implement `scripts/query/concept_bridge.py`**

```python
"""Concept→vocabulary bridge for query relaxation (issue #2, item B5).

Maps user concepts ("cartography", "מפות") to catalog vocabulary that
actually exists in this collection ("Geography", "description and travel",
physical_desc "map"). The map is a curated, deterministic JSON file —
data/normalization/concept_maps/concept_map.json — validated against the
DB by tests. No LLM involvement.
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_MAP_PATH = Path("data/normalization/concept_maps/concept_map.json")


@dataclass(frozen=True)
class Expansion:
    """One concept expansion: a (filter field, value) probe."""

    field: str  # "subject" | "title" | "physical_desc"
    value: str


@lru_cache(maxsize=1)
def _load_raw(path_str: str) -> dict:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def load_concept_map(path: Path = DEFAULT_MAP_PATH) -> dict[str, list[Expansion]]:
    """Load the concept map as {casefolded term -> expansions}.

    Canonical names and all aliases map to the same expansion list.
    Returns {} if the map file is missing (bridge disabled, not an error).
    """
    if not path.exists():
        return {}
    raw = _load_raw(str(path))
    result: dict[str, list[Expansion]] = {}
    for concept in raw.get("concepts", []):
        expansions = [
            Expansion(field=e["field"], value=e["value"])
            for e in concept.get("expansions", [])
        ]
        for term in [concept["canonical"], *concept.get("aliases", [])]:
            result[term.casefold()] = expansions
    return result


def expand_concept(term: str, path: Path = DEFAULT_MAP_PATH) -> list[Expansion]:
    """Return the catalog-vocabulary expansions for a user concept.

    Unknown terms return [] — the caller falls back to the literal term.
    """
    return load_concept_map(path).get(term.casefold(), [])
```

- [ ] **Step 5: Run tests, verify all pass**

Run: `poetry run pytest tests/scripts/query/test_concept_bridge.py -q`
Expected: all pass (DB-validation test runs if `data/index/bibliographic.db` exists)

- [ ] **Step 6: Commit**

```bash
git add data/normalization/concept_maps/concept_map.json scripts/query/concept_bridge.py tests/scripts/query/test_concept_bridge.py
git commit -m "feat(query): add concept→vocabulary bridge for recall expansion (issue #2 B5)"
```

---

### Task 2: `physical_desc` filter field

**Files:**
- Modify: `scripts/schemas/query_plan.py` (FilterField enum, ~line 12-26)
- Modify: `scripts/query/db_adapter.py` (new branch in `build_where_clause`, before `where_clause = " AND ".join(conditions)` at ~line 471)
- Modify: `tests/scripts/query/test_db_adapter.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/scripts/query/test_db_adapter.py`, following its existing conventions — read its imports/fixtures first)

```python
class TestPhysicalDescFilter:
    """physical_desc CONTAINS searches MARC 300 via EXISTS subquery (issue #2 B6)."""

    def test_physical_desc_contains_builds_exists_subquery(self):
        plan = QueryPlan(
            query_text="test",
            filters=[Filter(field=FilterField.PHYSICAL_DESC, op=FilterOp.CONTAINS, value="map")],
        )
        where_clause, params, needed_joins = build_where_clause(plan)
        assert "EXISTS" in where_clause
        assert "physical_descriptions" in where_clause
        assert "map" in params.values()
        # No join needed: EXISTS correlates on record id
        assert "physical_descriptions" not in needed_joins

    def test_physical_desc_equals_raises(self):
        plan = QueryPlan(
            query_text="test",
            filters=[Filter(field=FilterField.PHYSICAL_DESC, op=FilterOp.EQUALS, value="map")],
        )
        with pytest.raises(ValueError, match="physical_desc"):
            build_where_clause(plan)

    def test_physical_desc_negate_wraps_not(self):
        plan = QueryPlan(
            query_text="test",
            filters=[
                Filter(field=FilterField.PHYSICAL_DESC, op=FilterOp.CONTAINS, value="map", negate=True)
            ],
        )
        where_clause, _, _ = build_where_clause(plan)
        assert where_clause.strip().startswith("NOT (")
```

- [ ] **Step 2: Run tests, verify they fail** (`'physical_desc' is not a valid FilterField` / AttributeError)

Run: `poetry run pytest tests/scripts/query/test_db_adapter.py -k PhysicalDesc -q`

- [ ] **Step 3: Add the enum value** in `scripts/schemas/query_plan.py` inside `FilterField` (after `SUBJECT = "subject"`):

```python
    PHYSICAL_DESC = "physical_desc"  # MARC 300 — physical form ("maps", "plates")
```

- [ ] **Step 4: Add the db_adapter branch** in `build_where_clause`, as the last `elif` before `where_clause = " AND ".join(conditions)` (~line 470). Use the column constants from `M3Columns.PhysicalDescriptions` (check `scripts/marc/m3_contract.py:160-166` for exact names; they correspond to `record_id` and `value`):

```python
        elif filter.field == FilterField.PHYSICAL_DESC:
            # MARC 300 physical description — substring match via EXISTS
            # (no FTS table for physical_descriptions; table is small).
            if filter.op == FilterOp.CONTAINS:
                param_name = f"{param_prefix}_phys"
                condition = (
                    f"EXISTS (SELECT 1 FROM {M3Tables.PHYSICAL_DESCRIPTIONS} pd "
                    f"WHERE pd.record_id = {M3Aliases.RECORDS}.id "
                    f"AND LOWER(pd.value) LIKE '%' || LOWER(:{param_name}) || '%')"
                )
                params[param_name] = filter.value
            else:
                raise ValueError(f"Unsupported operation {filter.op} for physical_desc")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)
```

- [ ] **Step 5: Run tests, verify they pass; run the full db_adapter + schema test files**

Run: `poetry run pytest tests/scripts/query/test_db_adapter.py tests/scripts/query/test_query_plan.py -q`

- [ ] **Step 6: Commit**

```bash
git add scripts/schemas/query_plan.py scripts/query/db_adapter.py tests/scripts/query/test_db_adapter.py
git commit -m "feat(query): physical_desc filter field over MARC 300 (issue #2 B6)"
```

---

### Task 3: Relaxation ladder + scope union in the executor

**Files:**
- Modify: `scripts/chat/plan_models.py:152-162` (RecordSet)
- Modify: `scripts/chat/executor.py` (`_handle_retrieve` ~line 628, `_resolve_scope` ~line 274)
- Modify: `tests/scripts/chat/test_executor.py` (fixture + new tests)

- [ ] **Step 1: Add FTS tables to the `test_db` fixture** in `tests/scripts/chat/test_executor.py` (the fixture creates the schema at line ~50; subject/title CONTAINS requires FTS). Append to the `executescript` SQL, after the base tables:

```sql
        CREATE VIRTUAL TABLE subjects_fts USING fts5(mms_id, value, content='');
        CREATE VIRTUAL TABLE titles_fts USING fts5(
            mms_id UNINDEXED, title_type UNINDEXED, value,
            content=titles, content_rowid=id
        );
```

And after all sample-data INSERTs, populate them:

```sql
        INSERT INTO subjects_fts(rowid, mms_id, value)
            SELECT s.id, r.mms_id, s.value FROM subjects s JOIN records r ON s.record_id = r.id;
        INSERT INTO titles_fts(titles_fts) VALUES('rebuild');
```

Also add two themed records to the sample data (use the next free ids; check existing INSERTs first):

```sql
        INSERT INTO records VALUES (4, '990111111', 'test.xml', '2024-01-01', 4);
        INSERT INTO records VALUES (5, '990222222', 'test.xml', '2024-01-01', 5);
        INSERT INTO subjects VALUES (101, 4, 'Bible -- Geography -- Early works to 1800', '650', NULL, 'en', NULL, NULL, '["650"]', NULL);
        INSERT INTO subjects VALUES (102, 5, 'Art -- History', '650', NULL, 'en', NULL, NULL, '["650"]', NULL);
        INSERT INTO physical_descriptions VALUES (201, 4, '2 v. : ill., 10 folded maps', '["300"]');
        INSERT INTO titles VALUES (301, 4, 'main', 'Palaestina illustrata', '["245"]');
        INSERT INTO titles VALUES (302, 5, 'main', 'De arte pingendi', '["245"]');
```

(Column order must match the fixture's CREATE TABLE statements — verify against the fixture, not the real DB.)

- [ ] **Step 2: Write the failing tests** (append to `tests/scripts/chat/test_executor.py`)

```python
class TestRetrieveRelaxationLadder:
    """0-hit multi-topic AND queries are relaxed to OR-union + concept
    expansion, with every relaxation recorded as evidence (issue #2 A1/A2)."""

    def _plan(self, filters):
        return InterpretationPlan(
            intents=["retrieval"],
            reasoning="t",
            confidence=0.9,
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=filters),
                    label="t",
                )
            ],
        )

    def test_strict_match_does_not_relax(self, test_db):
        plan = self._plan([
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="geography"),
        ])
        result = execute_plan(plan, test_db)
        data = result.steps_completed[0].data
        assert "990111111" in data.mms_ids
        assert data.relaxations == []

    def test_multi_topic_zero_relaxes_to_or_union_with_expansion(self, test_db):
        # art AND maps AND cartography → 0 strict; ladder must recover both
        # the art record (direct OR) and the geography record (concept map:
        # cartography→subject geography / physical_desc map).
        plan = self._plan([
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art"),
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="maps"),
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="cartography"),
        ])
        result = execute_plan(plan, test_db)
        step = result.steps_completed[0]
        data = step.data
        assert "990222222" in data.mms_ids  # art (direct OR-union)
        assert "990111111" in data.mms_ids  # cartography via expansion
        assert step.status == "ok"
        assert data.relaxations, "relaxation must be recorded as evidence"
        assert any("0" in r or "relax" in r.lower() or "broaden" in r.lower() for r in data.relaxations)

    def test_non_topical_filters_stay_hard(self, test_db):
        # year constraint must remain AND even during relaxation:
        # records 4/5 have no imprints rows → a 1500-1510 RANGE excludes them.
        plan = self._plan([
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art"),
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="cartography"),
            Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1510),
        ])
        result = execute_plan(plan, test_db)
        data = result.steps_completed[0].data
        assert data.mms_ids == []
        assert data.relaxations == []

    def test_zero_with_no_expansion_stays_honest_empty(self, test_db):
        plan = self._plan([
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="xyzzy"),
        ])
        result = execute_plan(plan, test_db)
        step = result.steps_completed[0]
        assert step.status == "empty"
        assert step.data.mms_ids == []


class TestScopeUnion:
    """sample/retrieve scope may union steps: "$step_0+$step_1" (issue #2 C8)."""

    def test_union_scope_merges_step_results(self, test_db):
        plan = InterpretationPlan(
            intents=["curation"],
            reasoning="t",
            confidence=0.9,
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=[
                        Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="geography"),
                    ]),
                    label="geo",
                ),
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=[
                        Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art"),
                    ]),
                    label="art",
                ),
                ExecutionStep(
                    action=StepAction.SAMPLE,
                    params=SampleParams(scope="$step_0+$step_1", n=10, strategy="earliest"),
                    label="curate",
                    depends_on=[0, 1],
                ),
            ],
        )
        result = execute_plan(plan, test_db)
        sample = result.steps_completed[2].data
        assert set(sample.mms_ids) == {"990111111", "990222222"}
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `poetry run pytest tests/scripts/chat/test_executor.py -k "Relaxation or ScopeUnion" -q`
Expected: FAIL — `RecordSet` has no `relaxations`; union scope warns and queries full collection.

- [ ] **Step 4: Add `relaxations` to RecordSet** (`scripts/chat/plan_models.py:152`):

```python
class RecordSet(BaseModel):
    """Output of ``retrieve`` / ``sample``.

    ``mms_ids`` may be truncated; ``total_count`` always reflects
    the full match count. ``relaxations`` records every query-broadening
    step the executor applied after a 0-hit strict match (evidence of
    how the result set was obtained — empty when no relaxation ran).
    """

    mms_ids: list[str]
    total_count: int
    filters_applied: list[dict]
    relaxations: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: Refactor `_handle_retrieve` and add the ladder** in `scripts/chat/executor.py`. First ensure the module-level import `from scripts.schemas.query_plan import Filter, FilterField, FilterOp` exists in `executor.py` (check its current imports; add it if the names are only imported locally). Then extract the query-building/execution body (currently lines ~667-727) into a module-level helper, keeping the multi-value IN replacement intact:

```python
_TOPICAL_CONTAINS_FIELDS = {FilterField.SUBJECT, FilterField.TITLE, FilterField.PHYSICAL_DESC}


def _is_topical_contains(f: Filter) -> bool:
    """Topical filters are subject/title/physical_desc CONTAINS (not negated).
    These are recall constraints; everything else (year, place, language,
    agent…) is a hard constraint that relaxation must never loosen."""
    return f.field in _TOPICAL_CONTAINS_FIELDS and f.op == FilterOp.CONTAINS and not f.negate


def _run_filter_query(
    conn: sqlite3.Connection,
    filters: List[Filter],
    scope_ids: Optional[List[str]],
    multi_value_map: Optional[Dict[int, List[str]]] = None,
) -> List[str]:
    """Build and run one filter query; returns matching mms_ids (sorted)."""
    from scripts.query.db_adapter import build_where_clause, build_join_clauses
    from scripts.schemas.query_plan import QueryPlan

    if not filters:
        return []
    plan = QueryPlan(query_text="executor_retrieve", filters=filters)
    where_clause, sql_params, needed_joins = build_where_clause(plan, conn=conn)

    if multi_value_map:
        for filter_idx, all_values in multi_value_map.items():
            f = filters[filter_idx]
            param_key = f"filter_{filter_idx}_{f.field.value}"
            if param_key in sql_params:
                old_cond = f"LOWER(:{param_key})"
                mv_keys = [f"mv_{filter_idx}_{i}" for i in range(len(all_values))]
                multi_placeholders = ", ".join(f"LOWER(:{k})" for k in mv_keys)
                where_clause = where_clause.replace(
                    f"= {old_cond}", f"IN ({multi_placeholders})"
                )
                del sql_params[param_key]
                for k, v in zip(mv_keys, all_values):
                    sql_params[k] = v

    scope_clause = ""
    if scope_ids is not None:
        scope_keys = [f"scope_{i}" for i in range(len(scope_ids))]
        scope_placeholders = ",".join(f":{k}" for k in scope_keys)
        scope_clause = f" AND r.mms_id IN ({scope_placeholders})"
        for k, mms in zip(scope_keys, scope_ids):
            sql_params[k] = mms

    join_clauses = build_join_clauses(needed_joins)
    sql = "SELECT DISTINCT r.mms_id\nFROM records r"
    if join_clauses:
        sql += f"\n{join_clauses}"
    sql += f"\nWHERE {where_clause}{scope_clause}"
    sql += "\nORDER BY r.mms_id"
    rows = conn.execute(sql, sql_params).fetchall()
    return [row["mms_id"] for row in rows]


def _relax_and_retry(
    conn: sqlite3.Connection,
    filters: List[Filter],
    scope_ids: Optional[List[str]],
) -> tuple[List[str], List[str]]:
    """Relaxation ladder for 0-hit retrieves (issue #2 A2).

    Per topical filter: direct hits (OR-union when >=2 topics) plus
    concept-map expansion hits. Non-topical filters stay ANDed in every
    probe. Returns (mms_ids, relaxation_notes); ([], []) when nothing
    could be recovered — honest empty.
    """
    from scripts.query.concept_bridge import expand_concept
    from scripts.schemas.query_plan import Filter as QPFilter

    topical = [f for f in filters if _is_topical_contains(f)]
    others = [f for f in filters if not _is_topical_contains(f)]
    if not topical:
        return [], []

    union: set = set()
    notes: List[str] = []
    for tf in topical:
        topic_hits: set = set()
        if len(topical) >= 2:
            direct = _run_filter_query(conn, others + [tf], scope_ids)
            if direct:
                notes.append(
                    f"'{tf.value}' matched {len(direct)} records on its own (OR-union)"
                )
                topic_hits |= set(direct)
        for exp in expand_concept(str(tf.value)):
            probe = QPFilter(
                field=FilterField(exp.field), op=FilterOp.CONTAINS, value=exp.value
            )
            exp_hits = _run_filter_query(conn, others + [probe], scope_ids)
            if exp_hits:
                notes.append(
                    f"'{tf.value}' expanded to {exp.field} CONTAINS "
                    f"'{exp.value}' ({len(exp_hits)} records)"
                )
                topic_hits |= set(exp_hits)
        union |= topic_hits

    if not union:
        return [], []
    header = (
        f"Strict AND of {len(filters)} filter(s) returned 0 records; "
        f"broadened to OR-union with concept expansion across "
        f"{len(topical)} topic(s)"
    )
    logger.info("Retrieve relaxation: %s", header)
    return sorted(union), [header] + notes
```

Then `_handle_retrieve` keeps its step-ref resolution, scope resolution, and empty-scope early return unchanged, and its body becomes:

```python
    conn = _get_conn(db_path)
    try:
        mms_ids = _run_filter_query(conn, resolved_filters, scope_ids, multi_value_map)
        relaxations: List[str] = []
        if not mms_ids:
            mms_ids, relaxations = _relax_and_retry(conn, resolved_filters, scope_ids)
        return RecordSet(
            mms_ids=mms_ids,
            total_count=len(mms_ids),
            filters_applied=[f.model_dump() for f in resolved_filters],
            relaxations=relaxations,
        )
    finally:
        conn.close()
```

- [ ] **Step 6: Add scope union to `_resolve_scope`** (`scripts/chat/executor.py:274`), inserted after the `$previous_results` branch and before the single-ref match:

```python
    # Union of step references: "$step_0+$step_1" (deduplicated, order kept)
    if "+" in scope:
        parts = [p.strip() for p in scope.split("+")]
        if parts and all(_STEP_REF_RE.match(p) for p in parts):
            merged: List[str] = []
            seen: set = set()
            for part in parts:
                for mms in _resolve_step_ref(part, step_results, context="scope"):
                    if mms not in seen:
                        seen.add(mms)
                        merged.append(mms)
            return merged
```

- [ ] **Step 7: Run the new tests, then the whole executor + plan-models files**

Run: `poetry run pytest tests/scripts/chat/test_executor.py tests/scripts/chat/test_plan_models.py -q`
Expected: all pass (pre-existing retrieve tests must still pass — the refactor must be behavior-preserving for non-zero results)

- [ ] **Step 8: Commit**

```bash
git add scripts/chat/plan_models.py scripts/chat/executor.py tests/scripts/chat/test_executor.py
git commit -m "feat(executor): relaxation ladder + scope union for multi-topic recall (issue #2 A2/C8)"
```

---

### Task 4: Interpreter prompt — coordinate topics, physical_desc, curatorial routing

**Files:**
- Modify: `scripts/chat/interpreter.py` (INTERPRETER_SYSTEM_PROMPT, line 66+)
- Modify: `tests/scripts/chat/test_interpreter.py`

- [ ] **Step 1: Write the failing prompt-integrity tests** (append to `tests/scripts/chat/test_interpreter.py`)

```python
class TestPromptCoordinateTopics:
    """The system prompt must teach multi-topic decomposition, the
    physical_desc field, and curatorial routing (issue #2 A3/C8)."""

    def test_prompt_forbids_anding_coordinate_topics(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "COORDINATE TOPICS" in INTERPRETER_SYSTEM_PROMPT

    def test_prompt_documents_physical_desc_field(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "physical_desc" in INTERPRETER_SYSTEM_PROMPT

    def test_prompt_has_curatorial_example_with_sample_step(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "מה תציע לי להראות" in INTERPRETER_SYSTEM_PROMPT
        # NB: no surrounding quotes in the assertion — inside the prompt the
        # scope value sits in an escaped-JSON params string (\"...\").
        assert "$step_0+$step_1+$step_2" in INTERPRETER_SYSTEM_PROMPT

    def test_convert_filter_dict_accepts_physical_desc(self):
        from scripts.chat.interpreter import _convert_filter_dict
        f = _convert_filter_dict(
            {"field": "physical_desc", "op": "CONTAINS", "value": "map"}
        )
        assert f.field.value == "physical_desc"
```

- [ ] **Step 2: Run, verify failures** (`poetry run pytest tests/scripts/chat/test_interpreter.py -k Coordinate -q`)

Note: if `_convert_filter_dict` already passes (it converts via the FilterField enum extended in Task 2), that single test passing early is fine — the prompt tests must fail.

- [ ] **Step 3: Edit INTERPRETER_SYSTEM_PROMPT** — three edits:

(a) In the filter-field list (line ~108), change to include the new field:

```
  - `field`: one of publisher, imprint_place, country, year, language, title, subject, agent_norm, agent_role, agent_type, physical_desc
```

(b) In the retrieval guidance section (after the subject guidance around line 181-196), add:

```
- physical_desc: Physical form search over MARC 300 (partial match, CONTAINS only).
  Use for physical/form concepts: "maps" → physical_desc CONTAINS "map" finds books
  *containing* maps and atlases even when no subject heading mentions them.

# COORDINATE TOPICS — NEVER AND THEM

When a query lists coordinate topics ("art, maps and cartography"; "X, Y וגם Z"),
do NOT put them as multiple subject filters in ONE retrieve step — that ANDs them
and almost always returns 0 records in a 2,796-record collection. Instead create
ONE retrieve step PER topic (translating each topic to catalog vocabulary), then
operate on the union via scope "$step_0+$step_1+...". Reserve multiple filters in
one step for genuinely conjunctive constraints (e.g. subject + year + place).

Catalog vocabulary hints: this collection's subject headings rarely contain modern
concept words. Prefer headings that exist: cartography/maps → subject "geography",
subject "description and travel", physical_desc "map", title "atlas"; art →
subject "art", "engraving", "illustration".
```

(c) Add a worked example after the existing Hebrew prayer-books example (~line 357-365), using the exact failing query:

```
Query: "שיעור שעוסק באמנות, מפות וקרטוגרפיה. מה תציע לי להראות מהאוסף?"
{
  "intents": ["curation", "topical"],
  "reasoning": "Curatorial request (מה תציע לי להראות) for a lesson on three coordinate topics: art, maps, cartography. One retrieve step per concept using catalog vocabulary, then curate a notable sample over the union.",
  "confidence": 0.85,
  "execution_steps": [
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"subject\", \"op\": \"CONTAINS\", \"value\": \"art\"}]}", "label": "Books on art", "depends_on": []},
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"subject\", \"op\": \"CONTAINS\", \"value\": \"geography\"}]}", "label": "Geography & cartography", "depends_on": []},
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"physical_desc\", \"op\": \"CONTAINS\", \"value\": \"map\"}]}", "label": "Items physically containing maps", "depends_on": []},
    {"action": "sample", "params": "{\"scope\": \"$step_0+$step_1+$step_2\", \"n\": 12, \"strategy\": \"notable\"}", "label": "Curate notable items for the lesson", "depends_on": [0, 1, 2]}
  ],
  "directives": [
    {"directive": "synthesize", "params": "{\"sets\": [\"$step_3\"], \"note\": \"Present as a curated lesson set: why each item serves a lesson on art, maps and cartography\"}", "label": "Lesson framing"}
  ]
}
```

- [ ] **Step 4: Run tests, verify they pass; run the full interpreter test file**

Run: `poetry run pytest tests/scripts/chat/test_interpreter.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/interpreter.py tests/scripts/chat/test_interpreter.py
git commit -m "feat(interpreter): coordinate-topic decomposition + curatorial routing prompt (issue #2 A3/C8)"
```

---

### Task 5: Acceptance regression test + eval entry

**Files:**
- Create: `tests/integration/test_multi_topic_recall.py`
- Modify: `data/eval/queries.json` (append q31 after q30)

- [ ] **Step 1: Write the acceptance test** (this encodes issue #2's acceptance criteria, LLM-free, against the real DB)

```python
"""Acceptance regression for issue #2: multi-concept Hebrew curatorial query.

"שיעור שעוסק באמנות, מפות וקרטוגרפיה. מה תציע לי להראות מהאוסף?"
previously returned 0 records because three coordinate topics were ANDed
and the catalog's vocabulary never says "cartography". These tests run the
deterministic executor directly (no LLM) against the real DB.
"""
from pathlib import Path

import pytest

from scripts.chat.executor import execute_plan
from scripts.chat.plan_models import (
    ExecutionStep,
    InterpretationPlan,
    RetrieveParams,
    SampleParams,
    StepAction,
)
from scripts.schemas.query_plan import Filter, FilterField, FilterOp

pytestmark = pytest.mark.integration

DB_PATH = Path("data/index/bibliographic.db")

# Real records ChatGPT referenced by (fabricated ID but) real title — they
# exist in our collection and MUST be recoverable (issue #2 acceptance).
RELAND_PALAESTINA_1714 = "9933749415904146"
SURVEY_OF_WESTERN_PALESTINE = "990014484230204146"
BILDER_GEOGRAPHIE_1736 = "990020368010204146"


@pytest.fixture(autouse=True)
def _require_db():
    if not DB_PATH.exists():
        pytest.skip("Bibliographic database not available")


def test_worst_case_anded_plan_recovers_via_ladder():
    """Even if the interpreter still emits the bad single-step AND plan,
    the executor ladder must recover a non-empty, relevant CandidateSet."""
    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="issue #2 regression: worst-case AND plan",
        confidence=0.9,
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(filters=[
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art"),
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="maps"),
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="cartography"),
                ]),
                label="art maps cartography (ANDed)",
            )
        ],
    )
    result = execute_plan(plan, DB_PATH)
    step = result.steps_completed[0]
    assert step.status == "ok"
    assert step.data.total_count >= 10
    for target in (RELAND_PALAESTINA_1714, SURVEY_OF_WESTERN_PALESTINE, BILDER_GEOGRAPHIE_1736):
        assert target in step.data.mms_ids
    assert step.data.relaxations, "ladder must record its evidence"


def test_good_curatorial_plan_returns_curated_sample():
    """The plan shape the re-prompted interpreter should emit: one retrieve
    per concept, curated sample over the union."""
    plan = InterpretationPlan(
        intents=["curation", "topical"],
        reasoning="issue #2 regression: decomposed curatorial plan",
        confidence=0.9,
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(filters=[
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art"),
                ]),
                label="art",
            ),
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(filters=[
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="geography"),
                ]),
                label="geography/cartography",
            ),
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(filters=[
                    Filter(field=FilterField.PHYSICAL_DESC, op=FilterOp.CONTAINS, value="map"),
                ]),
                label="contains maps",
            ),
            ExecutionStep(
                action=StepAction.SAMPLE,
                params=SampleParams(scope="$step_0+$step_1+$step_2", n=12, strategy="notable"),
                label="curate",
                depends_on=[0, 1, 2],
            ),
        ],
    )
    result = execute_plan(plan, DB_PATH)
    geo = result.steps_completed[1].data
    phys = result.steps_completed[2].data
    sample = result.steps_completed[3].data
    assert RELAND_PALAESTINA_1714 in geo.mms_ids
    assert phys.total_count >= 50  # 106 records have maps in MARC 300
    assert 1 <= len(sample.mms_ids) <= 12
    union = set(result.steps_completed[0].data.mms_ids) | set(geo.mms_ids) | set(phys.mms_ids)
    assert set(sample.mms_ids) <= union, "no fabricated identifiers — sample ⊆ retrieved union"
```

- [ ] **Step 2: Run** — both must pass already if Tasks 1-3 are done (this is an acceptance gate, not strict TDD; if either fails, fix the prior tasks, not the test)

Run: `poetry run pytest tests/integration/test_multi_topic_recall.py -q`

- [ ] **Step 3: Append q31 to `data/eval/queries.json`** (after q30, inside the array):

```json
  {
    "id": "q31",
    "query": "שיעור שעוסק באמנות, מפות וקרטוגרפיה. מה תציע לי להראות מהאוסף?",
    "intent": "curation",
    "difficulty": "hard",
    "expected_filters": {"topics_decomposed_or": ["art", "geography", "maps"], "physical_desc": "map"},
    "notes": "Issue #2 regression: multi-concept Hebrew curatorial query. Must NOT collapse to ANDed 0-result; expect >=10 candidates incl. 9933749415904146 (Reland 1714), 990014484230204146 (Survey of W. Palestine), 990020368010204146 (Bilder-Geographie). Coordinate topics -> one retrieve step per concept + sample notable over scope union."
  }
```

Validate: `poetry run python -c "import json; json.load(open('data/eval/queries.json')); print('valid')"`

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_multi_topic_recall.py data/eval/queries.json
git commit -m "test: acceptance regression for issue #2 multi-topic curatorial recall (D9)"
```

---

### Task 6: External-citation verification harness

**Files:**
- Create: `scripts/qa/verify_external_citations.py`
- Create: `tests/scripts/qa/test_verify_external_citations.py` (check `tests/scripts/qa/__init__.py` exists; create empty if not)
- Create: `data/qa/external_claims/2026-06-10-chatgpt-cartography.json`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the external-citation verification harness (issue #2 D10).

Cross-checks externally-claimed (title, mms_id) pairs — e.g. from a ChatGPT
answer — against bibliographic.db to flag fabricated identifiers.
"""
from pathlib import Path

import pytest

from scripts.qa.verify_external_citations import verify_claim, verify_claims

DB_PATH = Path("data/index/bibliographic.db")

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_db():
    if not DB_PATH.exists():
        pytest.skip("Bibliographic database not available")


def test_fabricated_id_with_real_title_is_flagged():
    # The actual ChatGPT fabrication from issue #2: real title, invented MMS ID.
    result = verify_claim(
        title="Palaestina ex monumentis veteribus illustrata",
        mms_id="9933433384704146",
        db_path=DB_PATH,
    )
    assert result["status"] == "id_fabricated_title_real"
    assert "9933749415904146" in result["real_mms_ids"]


def test_correct_pair_verifies():
    result = verify_claim(
        title="Palaestina ex monumentis veteribus illustrata",
        mms_id="9933749415904146",
        db_path=DB_PATH,
    )
    assert result["status"] == "verified"


def test_unknown_title_and_id_not_found():
    result = verify_claim(
        title="A Totally Invented Treatise of Nowhere",
        mms_id="9999999999999999",
        db_path=DB_PATH,
    )
    assert result["status"] == "not_found"


def test_verify_claims_batch_summarizes():
    report = verify_claims(
        [
            {"title": "Palaestina ex monumentis veteribus illustrata", "mms_id": "9933433384704146"},
            {"title": "A Totally Invented Treatise of Nowhere", "mms_id": "9999999999999999"},
        ],
        db_path=DB_PATH,
    )
    assert report["summary"]["total"] == 2
    assert report["summary"]["id_fabricated_title_real"] == 1
    assert report["summary"]["not_found"] == 1
```

- [ ] **Step 2: Run, verify ModuleNotFoundError** (`poetry run pytest tests/scripts/qa/test_verify_external_citations.py -q`)

- [ ] **Step 3: Implement `scripts/qa/verify_external_citations.py`**

```python
"""Verify externally-claimed citations against bibliographic.db (issue #2 D10).

External tools (ChatGPT etc.) may cite real titles with fabricated MMS IDs.
This harness cross-checks each claimed (title, mms_id) pair:

  verified                 — the mms_id exists AND one of its titles matches
  id_fabricated_title_real — the title exists in the collection but under
                             different mms_id(s); the claimed id does not
                             match it (fabricated or wrong)
  id_real_title_mismatch   — the mms_id exists but none of its titles match
  not_found                — neither the id nor the title is in the collection

Usage:
    python scripts/qa/verify_external_citations.py \
        --claims data/qa/external_claims/2026-06-10-chatgpt-cartography.json \
        --db data/index/bibliographic.db [--out report.json]

Claims file format: [{"title": "...", "mms_id": "..."}, ...]
"""
import argparse
import json
import sqlite3
from pathlib import Path

_TITLE_PROBE_LEN = 40


def _norm_title(title: str) -> str:
    """Whitespace-collapsed, LIKE-escaped probe prefix of a claimed title."""
    collapsed = " ".join(title.split())
    probe = collapsed[:_TITLE_PROBE_LEN]
    return probe.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _title_match_ids(conn: sqlite3.Connection, title: str) -> list:
    probe = _norm_title(title)
    rows = conn.execute(
        "SELECT DISTINCT r.mms_id FROM records r "
        "JOIN titles t ON t.record_id = r.id "
        "WHERE LOWER(t.value) LIKE '%' || LOWER(?) || '%' ESCAPE '\\' "
        "ORDER BY r.mms_id",
        (probe,),
    ).fetchall()
    return [row[0] for row in rows]


def verify_claim(title: str, mms_id: str, db_path: Path) -> dict:
    """Verify a single (title, mms_id) claim. Returns a result dict."""
    conn = sqlite3.connect(str(db_path))
    try:
        id_exists = (
            conn.execute(
                "SELECT 1 FROM records WHERE mms_id = ?", (mms_id,)
            ).fetchone()
            is not None
        )
        title_ids = _title_match_ids(conn, title)

        if id_exists and mms_id in title_ids:
            status = "verified"
        elif title_ids:
            status = "id_fabricated_title_real"
        elif id_exists:
            status = "id_real_title_mismatch"
        else:
            status = "not_found"

        return {
            "claimed_title": title,
            "claimed_mms_id": mms_id,
            "status": status,
            "id_exists": id_exists,
            "real_mms_ids": title_ids,
        }
    finally:
        conn.close()


def verify_claims(claims: list, db_path: Path) -> dict:
    """Verify a batch of claims; returns {results: [...], summary: {...}}."""
    results = [verify_claim(c["title"], c["mms_id"], db_path) for c in claims]
    summary: dict = {"total": len(results)}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    return {"results": results, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=Path("data/index/bibliographic.db"))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    claims = json.loads(args.claims.read_text(encoding="utf-8"))
    report = verify_claims(claims, args.db)

    for r in report["results"]:
        print(f"[{r['status']:>26}] {r['claimed_mms_id']}  {r['claimed_title'][:60]}")
        if r["status"] == "id_fabricated_title_real":
            print(f"{'':>30}real id(s): {', '.join(r['real_mms_ids'])}")
    print(f"\nSummary: {json.dumps(report['summary'], ensure_ascii=False)}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests, verify pass** (`poetry run pytest tests/scripts/qa/test_verify_external_citations.py -q`)

- [ ] **Step 5: Build the claims file from the ChatGPT answer.** Read `docs/testing/uesrs_feedbacks/10_06_26/chat_gpt_answer.txt` (bounded: it's ~11KB, grep for `MMS ID` lines) and extract EVERY cited item's title + MMS ID into `data/qa/external_claims/2026-06-10-chatgpt-cartography.json` (same `[{"title", "mms_id"}]` format as below). Two entries are already known from research and must be present:

```json
[
  {"title": "Hadriani Relandi Palaestina ex monumentis veteribus illustrata", "mms_id": "9933433384704146"},
  {"title": "Kanaan en d'Omleggende Landen", "mms_id": "9933433393004146"}
]
```

Then run the harness once and eyeball the report:

```bash
poetry run python scripts/qa/verify_external_citations.py \
  --claims data/qa/external_claims/2026-06-10-chatgpt-cartography.json \
  --out data/qa/external_claims/2026-06-10-chatgpt-cartography.report.json
```

Expected: the Reland claim → `id_fabricated_title_real` with real id `9933749415904146`.

- [ ] **Step 6: Commit**

```bash
git add scripts/qa/verify_external_citations.py tests/scripts/qa/ data/qa/external_claims/
git commit -m "feat(qa): external-citation verification harness (issue #2 D10)"
```

---

### Task 7: Docs, full suite, issue closure

**Files:**
- Modify: `docs/current/query-engine.md`
- Modify: `docs/current/qa-framework.md`

- [ ] **Step 1: Document in `docs/current/query-engine.md`** (set `Last verified: <today>`): add a "Relaxation ladder & concept bridge" section covering: topical vs hard filters, the 0-hit ladder (strict AND → per-topic OR-union ∪ concept expansion → honest empty), `RecordSet.relaxations` as evidence, `FilterField.PHYSICAL_DESC` (MARC 300, CONTAINS only, EXISTS subquery), scope union syntax `"$step_0+$step_1"`, and `data/normalization/concept_maps/concept_map.json` (curated; every term DB-validated by test).

- [ ] **Step 2: Document the harness in `docs/current/qa-framework.md`** (set `Last verified`): one section — purpose, usage command, the four statuses, claims-file format, and the 2026-06-10 ChatGPT report as the first example.

- [ ] **Step 3: Run the FULL test suite + lint**

```bash
poetry run pytest -q
poetry run ruff check scripts/ app/ tests/ && poetry run ruff format --check scripts/query/concept_bridge.py scripts/qa/verify_external_citations.py
```

Expected: everything green (baseline was 1443 passed, 21 skipped).

- [ ] **Step 4: Commit docs**

```bash
git add docs/current/query-engine.md docs/current/qa-framework.md
git commit -m "docs: relaxation ladder, concept bridge, citation harness (issue #2)"
```

- [ ] **Step 5: Issue #2 wrap-up — with the user.** Post a summary comment (what was implemented per A/B/C/D item, what was deferred: B6 655/008 absent from export, B7 embeddings consciously not done). ⚠️ Two things require explicit user approval first: (a) running a **live** end-to-end `/chat` with the Hebrew query costs LLM money — ask before running; (b) closing the issue.

---

## Deferred / out of scope (state in the issue comment)

- **B6 (655/008 indexing):** raw export contains no 655 fields; `physical_descriptions` (MARC 300) provides the deterministic form signal. Revisit at the next MARC export.
- **B7 (embedding recall booster):** contradicts the project's "no embedding retrieval" rule; flagged as a conscious design discussion, not implemented.
- **Live interpreter behavior:** prompt changes are tested for integrity, not live LLM output. A live `/chat` run (paid) + adding q31 to a future eval run will verify end-to-end — only with user approval.
