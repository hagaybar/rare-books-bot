# Data Model

> Last verified: 2026-04-12
> Source of truth for: End-to-end data flow from MARC XML ingestion through chat user interface, including all intermediate schemas, transformations, and database structures

## 1. Overview

The rare-books-bot processes bibliographic MARC XML records through a 9-stage pipeline, each producing typed artifacts that feed the next stage. The pipeline is deterministic except for two LLM-assisted stages (Interpret and Narrate), which use structured output schemas to remain verifiable.

```
 MARC XML
    |
    v
 M1: Parse -----> CanonicalRecord (JSONL)
    |
    v
 M2: Normalize --> M2Enrichment (dates, places, publishers, agents)
    |
    v
 M3: Index ------> bibliographic.db (SQLite)
    |
    v
 Enrichment -----> authority_enrichment, wikipedia_cache, wikipedia_connections,
    |               publisher_authorities, publisher_variants,
    |               agent_authorities, agent_aliases, network tables
    v
 M4: Query ------> QueryPlan -> CandidateSet + Evidence
    |
    v
 Scholar Pipeline:
    |   Stage 1: Interpret ---> InterpretationPlan (execution steps + directives)
    |   Stage 2: Execute -----> ExecutionResult (step results + GroundingData)
    |   Stage 3: Narrate -----> ScholarResponse (markdown + grounding)
    |
    v
 API Layer -------> ChatResponse (HTTP/WebSocket)
    |
    v
 Frontend --------> ChatMessage, GroundingData, StreamingState (React)
```

**Source files by stage:**

| Stage | Key source files |
|-------|-----------------|
| M1 | `scripts/marc/models.py`, `scripts/marc/parse.py` |
| M2 | `scripts/marc/m2_models.py`, `scripts/marc/m2_normalize.py` |
| M3 | `scripts/marc/m3_schema.sql`, `scripts/marc/m3_index.py` |
| Enrichment | `scripts/enrichment/models.py`, `scripts/enrichment/wikipedia_schema.sql` |
| M4 | `scripts/schemas/query_plan.py`, `scripts/schemas/candidate_set.py` |
| Scholar | `scripts/chat/plan_models.py`, `scripts/chat/interpreter.py`, `scripts/chat/executor.py`, `scripts/chat/narrator.py` |
| API | `app/api/models.py`, `app/api/main.py` |
| Frontend | `frontend/src/types/chat.ts` |

---

## 2. M1: MARC XML Parsing

**Module:** `scripts/marc/models.py`

Parsing extracts raw values from MARC XML into typed Pydantic models. All values are preserved exactly as found in the source; no normalization occurs at this stage.

### SourcedValue

The fundamental building block -- a value with its MARC provenance.

| Field | Type | Description |
|-------|------|-------------|
| `value` | `Any` | Extracted raw value |
| `source` | `List[str]` | MARC field$subfield paths (e.g., `["260$a", "260$b"]`) |

### CanonicalRecord

Top-level record extracted from one MARC XML `<record>` element.

| Field | Type | Description |
|-------|------|-------------|
| `source` | `SourceMetadata` | `source_file: str`, `control_number: SourcedValue` (MARC 001) |
| `title` | `Optional[SourcedValue]` | Full title from 245$a$b$c |
| `uniform_title` | `Optional[SourcedValue]` | Uniform title from 240 |
| `variant_titles` | `List[SourcedValue]` | Variant titles from 246 |
| `imprints` | `List[ImprintData]` | Publication info from 260/264 (multiple per record) |
| `languages` | `List[SourcedValue]` | Language codes from 041$a |
| `language_fixed` | `Optional[SourcedValue]` | Fixed language from 008/35-37 |
| `country_code_fixed` | `Optional[SourcedValue]` | Country code from 008/15-17 |
| `subjects` | `List[SubjectData]` | Subject headings from 6XX |
| `agents` | `List[AgentData]` | Authors/contributors from 1XX/7XX |
| `notes` | `List[NoteData]` | Notes from 5XX |
| `physical_description` | `List[SourcedValue]` | Physical description from 300 |
| `acquisition` | `List[SourcedValue]` | Acquisition/provenance from 541 |

### ImprintData

One publication statement (rare books often have multiple imprints).

| Field | Type | Description |
|-------|------|-------------|
| `place` | `Optional[SourcedValue]` | Place of publication |
| `publisher` | `Optional[SourcedValue]` | Publisher name |
| `date` | `Optional[SourcedValue]` | Publication date |
| `manufacturer` | `Optional[SourcedValue]` | Manufacturer |
| `source_tags` | `List[str]` | MARC tags used (e.g., `["260"]` or `["264"]`) |

### AgentData

Author/contributor with structural and bibliographic roles separated.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `SourcedValue` | Agent name with source |
| `entry_role` | `str` | `"main"` or `"added"` |
| `function` | `Optional[SourcedValue]` | Bibliographic function (printer, editor, etc.) |
| `dates` | `Optional[SourcedValue]` | Life dates |
| `source_tags` | `List[str]` | MARC tags used (e.g., `["100"]` or `["700"]`) |
| `agent_type` | `str` | `"personal"`, `"corporate"`, or `"meeting"` |
| `agent_index` | `Optional[int]` | Stable ordering index within record |
| `role_source` | `Optional[str]` | `"relator_code"`, `"relator_term"`, `"inferred_from_tag"`, `"unknown"` |
| `authority_uri` | `Optional[SourcedValue]` | Authority URI from $0 subfield |

### SubjectData

| Field | Type | Description |
|-------|------|-------------|
| `value` | `str` | Display string (e.g., `"Rare books -- Bibliography -- Catalogs"`) |
| `source` | `List[str]` | MARC sources with occurrence (e.g., `["650[0]$a"]`) |
| `parts` | `Dict[str, Any]` | Structured parts by subfield code |
| `source_tag` | `str` | MARC tag (`"650"`, `"651"`, etc.) |
| `scheme` | `Optional[SourcedValue]` | Subject scheme from $2 |
| `heading_lang` | `Optional[SourcedValue]` | Heading language from $9 |
| `authority_uri` | `Optional[SourcedValue]` | Authority URI from $0 |

### NoteData

| Field | Type | Description |
|-------|------|-------------|
| `tag` | `str` | MARC tag (`"500"`, `"590"`, etc.) |
| `value` | `str` | Note text |
| `source` | `List[str]` | MARC field$subfield sources |

---

## 3. M2: Normalization

**Module:** `scripts/marc/m2_models.py`

M2 enriches M1 records with deterministic, reversible normalization. Every normalized field carries confidence and method provenance. Raw values are never modified.

### M2Enrichment (top-level container)

| Field | Type | Description |
|-------|------|-------------|
| `imprints_norm` | `List[ImprintNormalization]` | Parallel to M1 `imprints` array (index-aligned) |
| `agents_norm` | `List[Tuple[int, AgentNormalization, RoleNormalization]]` | `(agent_index, agent_norm, role_norm)` tuples |

### DateNormalization

| Field | Type | Description |
|-------|------|-------------|
| `start` | `Optional[int]` | Start year (inclusive) |
| `end` | `Optional[int]` | End year (inclusive) |
| `label` | `str` | Human-readable date label |
| `confidence` | `float` | 0.0--1.0 |
| `method` | `str` | Rule ID: `"exact"`, `"bracketed"`, `"circa"`, `"range"`, `"embedded"`, `"unparsed"` |
| `evidence_paths` | `List[str]` | M1 JSON paths used as evidence |
| `warnings` | `List[str]` | Normalization warnings |

### PlaceNormalization

| Field | Type | Description |
|-------|------|-------------|
| `value` | `Optional[str]` | Normalized key (casefolded, cleaned) |
| `display` | `str` | Best display form |
| `confidence` | `float` | 0.95 (alias map match) or tagged `"missing"` |
| `method` | `str` | `"place_alias_map"` or `"missing"` |
| `evidence_paths` | `List[str]` | M1 JSON paths |
| `warnings` | `List[str]` | Normalization warnings |

### PublisherNormalization

| Field | Type | Description |
|-------|------|-------------|
| `value` | `Optional[str]` | Normalized key (casefolded, cleaned) |
| `display` | `str` | Best display form |
| `confidence` | `float` | 0.80 (base) or 0.95 (alias map) |
| `method` | `str` | `"base_clean"` or `"publisher_alias_map"` |
| `evidence_paths` | `List[str]` | M1 JSON paths |
| `warnings` | `List[str]` | Normalization warnings |

### AgentNormalization

| Field | Type | Description |
|-------|------|-------------|
| `agent_raw` | `str` | Original agent name (traceability) |
| `agent_norm` | `str` | Canonical normalized name (lowercase, no punctuation) |
| `agent_confidence` | `float` | 0.0--1.0 |
| `agent_method` | `str` | `"base_clean"`, `"alias_map"`, or `"ambiguous"` |
| `agent_notes` | `Optional[str]` | Warnings or ambiguity flags |

### RoleNormalization

| Field | Type | Description |
|-------|------|-------------|
| `role_raw` | `Optional[str]` | Original role string |
| `role_norm` | `str` | Normalized role from controlled vocabulary |
| `role_confidence` | `float` | 0.0--1.0 |
| `role_method` | `str` | `"relator_code"`, `"relator_term"`, `"inferred"`, or `"manual_map"` |

---

## 4. M3: SQLite Indexing

**Schema:** `scripts/marc/m3_schema.sql`
**Database:** `data/index/bibliographic.db`

M3 flattens M1+M2 into a relational schema optimized for fielded queries. Raw and normalized values are stored side by side.

### Core Tables

#### records

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `mms_id` | `TEXT UNIQUE NOT NULL` | MARC 001 control number |
| `source_file` | `TEXT NOT NULL` | Source MARC XML filename |
| `created_at` | `TEXT NOT NULL` | ISO 8601 |
| `jsonl_line_number` | `INTEGER` | Line number in source JSONL |

#### titles

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `record_id` | `INTEGER FK -> records(id)` | CASCADE DELETE |
| `title_type` | `TEXT NOT NULL` | `"main"`, `"uniform"`, `"variant"` |
| `value` | `TEXT NOT NULL` | Title text |
| `source` | `TEXT NOT NULL` | JSON array of MARC sources |

#### imprints

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `record_id` | `INTEGER FK -> records(id)` | CASCADE DELETE |
| `occurrence` | `INTEGER NOT NULL` | 0-indexed position in imprints array |
| `date_raw` | `TEXT` | M1 raw date |
| `place_raw` | `TEXT` | M1 raw place |
| `publisher_raw` | `TEXT` | M1 raw publisher |
| `manufacturer_raw` | `TEXT` | M1 raw manufacturer |
| `source_tags` | `TEXT NOT NULL` | JSON array of MARC tags |
| `date_start` | `INTEGER` | M2 normalized start year |
| `date_end` | `INTEGER` | M2 normalized end year |
| `date_label` | `TEXT` | M2 display label |
| `date_confidence` | `REAL` | M2 confidence |
| `date_method` | `TEXT` | M2 method tag |
| `place_norm` | `TEXT` | M2 normalized place key |
| `place_display` | `TEXT` | M2 display form |
| `place_confidence` | `REAL` | M2 confidence |
| `place_method` | `TEXT` | M2 method tag |
| `publisher_norm` | `TEXT` | M2 normalized publisher key |
| `publisher_display` | `TEXT` | M2 display form |
| `publisher_confidence` | `REAL` | M2 confidence |
| `publisher_method` | `TEXT` | M2 method tag |
| `country_code` | `TEXT` | MARC country code from 008/15-17 |
| `country_name` | `TEXT` | Normalized country name |

Indexes: `record_id`, `(date_start, date_end)`, `place_norm`, `publisher_norm`, `date_confidence`, `country_code`, `country_name`.

#### subjects

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `record_id` | `INTEGER FK -> records(id)` | CASCADE DELETE |
| `value` | `TEXT NOT NULL` | Display string |
| `source_tag` | `TEXT NOT NULL` | MARC tag (650, 651, etc.) |
| `scheme` | `TEXT` | Subject scheme from $2 |
| `heading_lang` | `TEXT` | Heading language from $9 |
| `authority_uri` | `TEXT` | Authority URI from $0 |
| `parts` | `TEXT NOT NULL` | JSON object of structured parts |
| `source` | `TEXT NOT NULL` | JSON array of MARC sources |

#### agents

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `record_id` | `INTEGER FK -> records(id)` | CASCADE DELETE |
| `agent_index` | `INTEGER NOT NULL` | Stable ordering within record |
| `agent_raw` | `TEXT NOT NULL` | Original agent name (M1) |
| `agent_type` | `TEXT NOT NULL` | CHECK: `personal`, `corporate`, `meeting` |
| `role_raw` | `TEXT` | Raw role from MARC |
| `role_source` | `TEXT` | Source of role |
| `authority_uri` | `TEXT` | Authority URI from $0 |
| `agent_norm` | `TEXT NOT NULL` | Canonical normalized name (M2) |
| `agent_confidence` | `REAL NOT NULL` | CHECK: 0--1 |
| `agent_method` | `TEXT NOT NULL` | `"base_clean"`, `"alias_map"`, `"ambiguous"` |
| `agent_notes` | `TEXT` | Warnings |
| `role_norm` | `TEXT NOT NULL` | Normalized role |
| `role_confidence` | `REAL NOT NULL` | CHECK: 0--1 |
| `role_method` | `TEXT NOT NULL` | Role normalization method |
| `provenance_json` | `TEXT NOT NULL` | JSON array of source metadata |

Indexes: `record_id`, `agent_norm`, `role_norm`, `(agent_norm, role_norm)`, `agent_type`, `authority_uri`.

#### languages

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `record_id` | `INTEGER FK -> records(id)` | CASCADE DELETE |
| `code` | `TEXT NOT NULL` | ISO 639-2 language code |
| `source` | `TEXT NOT NULL` | MARC source |

#### notes

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `record_id` | `INTEGER FK -> records(id)` | CASCADE DELETE |
| `tag` | `TEXT NOT NULL` | MARC tag (500, 502, 505, etc.) |
| `value` | `TEXT NOT NULL` | Note text |
| `source` | `TEXT NOT NULL` | JSON array of MARC sources |

#### physical_descriptions

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `record_id` | `INTEGER FK -> records(id)` | CASCADE DELETE |
| `value` | `TEXT NOT NULL` | Description text |
| `source` | `TEXT NOT NULL` | JSON array of MARC sources |

### FTS5 Virtual Tables

| Table | Content Table | Indexed Columns | Unindexed Columns |
|-------|--------------|-----------------|-------------------|
| `titles_fts` | `titles` | `value` | `mms_id`, `title_type` |
| `subjects_fts` | `subjects` | `value` | `mms_id` |

Both FTS tables use sync triggers (INSERT/UPDATE/DELETE) on their content tables.

---

## 5. Enrichment

### authority_enrichment

External authority data fetched from Wikidata, VIAF, NLI.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `authority_uri` | `TEXT UNIQUE NOT NULL` | Original $0 URI |
| `nli_id` | `TEXT` | NLI authority ID |
| `wikidata_id` | `TEXT` | Wikidata QID |
| `viaf_id` | `TEXT` | VIAF ID |
| `isni_id` | `TEXT` | ISNI |
| `loc_id` | `TEXT` | Library of Congress ID |
| `label` | `TEXT` | Display label |
| `description` | `TEXT` | Wikidata description |
| `person_info` | `TEXT` | JSON: birth/death years, occupations, nationality, teachers, students |
| `place_info` | `TEXT` | JSON: coordinates, country |
| `image_url` | `TEXT` | Wikidata image |
| `wikipedia_url` | `TEXT` | Wikipedia article URL |
| `source` | `TEXT NOT NULL` | `"wikidata"`, `"viaf"`, `"nli"` |
| `confidence` | `REAL` | 0--1 |
| `fetched_at` | `TEXT NOT NULL` | ISO 8601 |
| `expires_at` | `TEXT NOT NULL` | ISO 8601 |

### publisher_authorities

Canonical publisher identities (227 records).

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `canonical_name` | `TEXT NOT NULL` | Display name |
| `canonical_name_lower` | `TEXT NOT NULL` | Casefolded unique key |
| `type` | `TEXT NOT NULL` | CHECK: `printing_house`, `private_press`, `modern_publisher`, `bibliophile_society`, `unknown_marker`, `unresearched` |
| `dates_active` | `TEXT` | Active period description |
| `date_start` | `INTEGER` | Earliest known year |
| `date_end` | `INTEGER` | Latest known year |
| `location` | `TEXT` | Primary location |
| `notes` | `TEXT` | Free-text notes |
| `sources` | `TEXT` | Source citations |
| `confidence` | `REAL NOT NULL` | Default 0.5 |
| `is_missing_marker` | `INTEGER NOT NULL` | 0 or 1 |
| `viaf_id` | `TEXT` | VIAF ID |
| `wikidata_id` | `TEXT` | Wikidata QID |
| `cerl_id` | `TEXT` | CERL Thesaurus ID |
| `branch` | `TEXT` | Publishing branch/family |
| `primary_language` | `TEXT` | Primary language |
| `created_at` | `TEXT NOT NULL` | ISO 8601 |
| `updated_at` | `TEXT NOT NULL` | ISO 8601 |

### publisher_variants

Name forms linking to publisher authorities (265 variants).

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `authority_id` | `INTEGER FK -> publisher_authorities(id)` | CASCADE DELETE |
| `variant_form` | `TEXT NOT NULL` | Display form |
| `variant_form_lower` | `TEXT NOT NULL` | Casefolded unique key |
| `script` | `TEXT` | Default `"latin"` |
| `language` | `TEXT` | Language of variant |
| `is_primary` | `INTEGER NOT NULL` | 0 or 1 |
| `priority` | `INTEGER NOT NULL` | Sort priority |
| `notes` | `TEXT` | |
| `created_at` | `TEXT NOT NULL` | ISO 8601 |

### agent_authorities

Canonical agent identities.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `canonical_name` | `TEXT NOT NULL` | Display name |
| `canonical_name_lower` | `TEXT NOT NULL` | Casefolded unique key |
| `agent_type` | `TEXT NOT NULL` | CHECK: `personal`, `corporate`, `meeting` |
| `dates_active` | `TEXT` | |
| `date_start` | `INTEGER` | |
| `date_end` | `INTEGER` | |
| `notes` | `TEXT` | |
| `sources` | `TEXT` | |
| `confidence` | `REAL NOT NULL` | Default 0.5 |
| `authority_uri` | `TEXT` | |
| `wikidata_id` | `TEXT` | |
| `viaf_id` | `TEXT` | |
| `nli_id` | `TEXT` | |
| `created_at` | `TEXT NOT NULL` | ISO 8601 |
| `updated_at` | `TEXT NOT NULL` | ISO 8601 |

### agent_aliases

Name variants linking to agent authorities.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `authority_id` | `INTEGER FK -> agent_authorities(id)` | CASCADE DELETE |
| `alias_form` | `TEXT NOT NULL` | Display form |
| `alias_form_lower` | `TEXT NOT NULL` | Casefolded unique key |
| `alias_type` | `TEXT NOT NULL` | CHECK: `primary`, `variant_spelling`, `cross_script`, `patronymic`, `acronym`, `word_reorder`, `historical` |
| `script` | `TEXT` | Default `"latin"` |
| `language` | `TEXT` | |
| `is_primary` | `INTEGER NOT NULL` | 0 or 1 |
| `priority` | `INTEGER NOT NULL` | Sort priority |
| `notes` | `TEXT` | |
| `created_at` | `TEXT NOT NULL` | ISO 8601 |

### wikipedia_cache

Cached Wikipedia article data.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `wikidata_id` | `TEXT NOT NULL` | Wikidata QID |
| `wikipedia_title` | `TEXT` | Article title |
| `summary_extract` | `TEXT` | Article extract |
| `categories` | `TEXT` | JSON array |
| `see_also_titles` | `TEXT` | JSON array |
| `article_wikilinks` | `TEXT` | JSON array |
| `sections_json` | `TEXT` | JSON object |
| `name_variants` | `TEXT` | JSON array |
| `page_id` | `INTEGER` | Wikipedia page ID |
| `revision_id` | `INTEGER` | Wikipedia revision ID |
| `language` | `TEXT` | Default `"en"` |
| `fetched_at` | `TEXT NOT NULL` | ISO 8601 |
| `expires_at` | `TEXT NOT NULL` | ISO 8601 |

UNIQUE constraint: `(wikidata_id, language)`.

### wikipedia_connections

Relationships discovered from Wikipedia article analysis.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `source_agent_norm` | `TEXT NOT NULL` | Source agent |
| `target_agent_norm` | `TEXT NOT NULL` | Target agent |
| `source_wikidata_id` | `TEXT` | Source Wikidata QID |
| `target_wikidata_id` | `TEXT` | Target Wikidata QID |
| `relationship` | `TEXT` | Relationship type |
| `tags` | `TEXT` | JSON tags |
| `confidence` | `REAL NOT NULL` | 0--1 |
| `source_type` | `TEXT NOT NULL` | `"wikipedia_see_also"`, `"wikipedia_wikilink"`, etc. |
| `evidence` | `TEXT` | Evidence description |
| `bidirectional` | `INTEGER` | Default 0 |
| `created_at` | `TEXT NOT NULL` | ISO 8601 |

UNIQUE constraint: `(source_agent_norm, target_agent_norm, source_type)`.

### Network Tables (inline DDL)

Created by `scripts/network/build_network_tables.py` using inline `DROP TABLE IF EXISTS` + `CREATE TABLE` (not in `m3_schema.sql`).

#### network_edges

| Column | Type | Notes |
|--------|------|-------|
| `source_agent_norm` | `TEXT NOT NULL` | |
| `target_agent_norm` | `TEXT NOT NULL` | |
| `connection_type` | `TEXT NOT NULL` | |
| `confidence` | `REAL NOT NULL` | |
| `relationship` | `TEXT` | |
| `bidirectional` | `INTEGER` | Default 0 |
| `evidence` | `TEXT` | |

UNIQUE constraint: `(source_agent_norm, target_agent_norm, connection_type)`.

#### network_agents

| Column | Type | Notes |
|--------|------|-------|
| `agent_norm` | `TEXT PK` | |
| `display_name` | `TEXT NOT NULL` | |
| `place_norm` | `TEXT` | |
| `lat` | `REAL` | |
| `lon` | `REAL` | |
| `birth_year` | `INTEGER` | |
| `death_year` | `INTEGER` | |
| `occupations` | `TEXT` | JSON array |
| `primary_role` | `TEXT` | |
| `has_wikipedia` | `INTEGER` | Default 0 |
| `record_count` | `INTEGER` | Default 0 |
| `connection_count` | `INTEGER` | Default 0 |

### EnrichmentResult (Pydantic model)

**Module:** `scripts/enrichment/models.py`

| Field | Type | Description |
|-------|------|-------------|
| `entity_type` | `EntityType` | `"agent"`, `"place"`, `"publisher"`, `"subject"`, `"work"` |
| `entity_value` | `str` | Name or identifier |
| `normalized_key` | `str` | Normalized lookup key |
| `external_ids` | `List[ExternalIdentifier]` | `(source, identifier, url)` tuples |
| `wikidata_id` | `Optional[str]` | Wikidata QID |
| `viaf_id` | `Optional[str]` | VIAF ID |
| `isni_id` | `Optional[str]` | ISNI |
| `loc_id` | `Optional[str]` | Library of Congress ID |
| `nli_id` | `Optional[str]` | NLI ID |
| `person_info` | `Optional[PersonInfo]` | Birth/death years, occupations, teachers, students, notable_works |
| `place_info` | `Optional[PlaceInfo]` | Country, coordinates, modern_name |
| `label` | `Optional[str]` | Display label |
| `description` | `Optional[str]` | Entity description |
| `image_url` | `Optional[str]` | |
| `wikipedia_url` | `Optional[str]` | |
| `sources_used` | `List[EnrichmentSource]` | `"nli"`, `"wikidata"`, `"viaf"`, `"loc"`, `"isni"`, `"cache"` |
| `confidence` | `float` | 0.0--1.0 |
| `fetched_at` | `datetime` | UTC timestamp |

---

## 6. M4: Query Planning & Execution

**Modules:** `scripts/schemas/query_plan.py`, `scripts/schemas/candidate_set.py`, `scripts/query/models.py`

### QueryPlan

Structured plan compiled from natural language via LLM (OpenAI Responses API with Pydantic schema enforcement).

| Field | Type | Description |
|-------|------|-------------|
| `version` | `str` | Default `"1.0"` |
| `query_text` | `str` | Original natural language query |
| `filters` | `List[Filter]` | AND-combined filter conditions |
| `soft_filters` | `List[Filter]` | Optional filters (ignored in M4) |
| `limit` | `Optional[int]` | Result limit |
| `debug` | `Dict[str, Any]` | Added post-LLM, not part of LLM schema |

### Filter

| Field | Type | Description |
|-------|------|-------------|
| `field` | `FilterField` | Enum: `publisher`, `imprint_place`, `country`, `year`, `language`, `title`, `subject`, `agent`, `agent_norm`, `agent_role`, `agent_type` |
| `op` | `FilterOp` | Enum: `EQUALS`, `CONTAINS`, `RANGE`, `IN` |
| `value` | `Optional[Union[str, List[str]]]` | For EQUALS/CONTAINS/IN |
| `start` | `Optional[int]` | For RANGE |
| `end` | `Optional[int]` | For RANGE |
| `negate` | `bool` | Default `False` |
| `confidence` | `Optional[float]` | 0.0--1.0 |
| `notes` | `Optional[str]` | |

### CandidateSet

Primary output of M4. Every candidate includes evidence.

| Field | Type | Description |
|-------|------|-------------|
| `query_text` | `str` | Original query |
| `plan_hash` | `str` | SHA256 of canonicalized plan JSON |
| `sql` | `str` | Exact SQL executed (reproducibility) |
| `sql_parameters` | `Dict[str, Any]` | SQL parameter values |
| `generated_at` | `str` | ISO 8601 UTC |
| `candidates` | `List[Candidate]` | Matched records |
| `total_count` | `int` | Total match count |

### Candidate

| Field | Type | Description |
|-------|------|-------------|
| `record_id` | `str` | MMS ID |
| `match_rationale` | `str` | Template-generated deterministic string |
| `evidence` | `List[Evidence]` | Per-filter evidence |
| `title` | `Optional[str]` | Display title |
| `author` | `Optional[str]` | Primary author |
| `date_start` | `Optional[int]` | Publication start year |
| `date_end` | `Optional[int]` | Publication end year |
| `place_norm` | `Optional[str]` | Canonical place |
| `place_raw` | `Optional[str]` | Raw bibliographic place |
| `publisher` | `Optional[str]` | Publisher name |
| `subjects` | `List[str]` | First 3 subject headings |
| `description` | `Optional[str]` | From MARC 500/520 notes |

### Evidence

| Field | Type | Description |
|-------|------|-------------|
| `field` | `str` | DB column (e.g., `"publisher_norm"`, `"date_start"`) |
| `value` | `Any` | Record's matched value |
| `operator` | `str` | `"="`, `"BETWEEN"`, `"LIKE"`, `"OVERLAPS"` |
| `matched_against` | `Any` | Plan value(s) that matched |
| `source` | `str` | `"db.imprints.publisher_norm"` or `"marc:264$b"` |
| `confidence` | `Optional[float]` | 0.0--1.0 |
| `extraction_error` | `Optional[str]` | Error message if extraction failed |

### QueryResult (unified service result)

| Field | Type | Description |
|-------|------|-------------|
| `query_plan` | `QueryPlan` | |
| `sql` | `str` | |
| `params` | `List[Any]` | |
| `candidate_set` | `CandidateSet` | |
| `facets` | `Optional[FacetCounts]` | `by_place`, `by_year`, `by_language`, `by_publisher`, `by_century` |
| `warnings` | `List[QueryWarning]` | `code`, `message`, `field`, `confidence` |
| `execution_time_ms` | `float` | |

---

## 7. Scholar Pipeline

**Module:** `scripts/chat/plan_models.py`

Three-stage pipeline: Interpret (LLM) -> Execute (deterministic) -> Narrate (LLM). Each stage has typed input/output contracts. The executor cannot access the LLM; the narrator cannot access the database.

### Stage 1: InterpretationPlan (Interpreter output)

| Field | Type | Description |
|-------|------|-------------|
| `intents` | `list[str]` | `"retrieval"`, `"entity_exploration"`, `"analytical"`, `"comparison"`, `"curation"`, `"topical"`, `"follow_up"`, `"overview"`, `"out_of_scope"` |
| `reasoning` | `str` | LLM's reasoning chain |
| `execution_steps` | `list[ExecutionStep]` | Steps for the executor |
| `directives` | `list[ScholarlyDirective]` | Instructions for the narrator |
| `confidence` | `float` | 0.0--1.0 |
| `clarification` | `str | None` | Short-circuits pipeline if set |

### ExecutionStep

| Field | Type | Description |
|-------|------|-------------|
| `action` | `StepAction` | Enum: `resolve_agent`, `resolve_publisher`, `retrieve`, `aggregate`, `find_connections`, `enrich`, `sample` |
| `params` | `StepParams` | Union of typed params (see below) |
| `label` | `str` | Human-readable step description |
| `depends_on` | `list[int]` | Step indices that must complete first |

**Typed params per action:**

| Action | Params model | Key fields |
|--------|-------------|------------|
| `resolve_agent` | `ResolveAgentParams` | `name: str`, `variants: list[str]` |
| `resolve_publisher` | `ResolvePublisherParams` | `name: str`, `variants: list[str]` |
| `retrieve` | `RetrieveParams` | `filters: list[Filter]`, `scope: str` |
| `aggregate` | `AggregateParams` | `field: str`, `scope: str`, `limit: int` |
| `find_connections` | `FindConnectionsParams` | `agents: list[str]`, `depth: int` |
| `enrich` | `EnrichParams` | `targets: str`, `fields: list[str]` |
| `sample` | `SampleParams` | `scope: str`, `n: int`, `strategy: str` |

### ScholarlyDirective

| Field | Type | Description |
|-------|------|-------------|
| `directive` | `str` | Free-form instruction (not enum-gated) |
| `params` | `dict` | Directive-specific parameters |
| `label` | `str` | Human-readable label |

### Stage 2: ExecutionResult (Executor output)

| Field | Type | Description |
|-------|------|-------------|
| `steps_completed` | `list[StepResult]` | Ordered results |
| `directives` | `list[ScholarlyDirective]` | Passed through from plan |
| `grounding` | `GroundingData` | Aggregated evidence for narrator |
| `original_query` | `str` | Echo of user query |
| `session_context` | `SessionContext | None` | Follow-up context |
| `truncated` | `bool` | Whether grounding was truncated |

### StepResult

| Field | Type | Description |
|-------|------|-------------|
| `step_index` | `int` | |
| `action` | `str` | |
| `label` | `str` | |
| `status` | `str` | `"ok"`, `"empty"`, `"partial"`, `"error"` |
| `data` | `StepOutputData` | Union: `ResolvedEntity`, `RecordSet`, `AggregationResult`, `ConnectionGraph`, `EnrichmentBundle` |
| `record_count` | `int | None` | |
| `error_message` | `str | None` | |

### Step Output Types

| Type | Key fields |
|------|-----------|
| `ResolvedEntity` | `query_name: str`, `matched_values: list[str]`, `match_method: str`, `confidence: float` |
| `RecordSet` | `mms_ids: list[str]`, `total_count: int`, `filters_applied: list[dict]` |
| `AggregationResult` | `field: str`, `facets: list[dict]`, `total_records: int` |
| `ConnectionGraph` | `connections: list[dict]`, `isolated: list[str]` |
| `EnrichmentBundle` | `agents: list[AgentSummary]` |

### GroundingData

Aggregated evidence passed from executor to narrator. Deduplicated across all steps.

| Field | Type | Description |
|-------|------|-------------|
| `records` | `list[RecordSummary]` | Bibliographic record summaries (max 30) |
| `agents` | `list[AgentSummary]` | Enriched agent profiles |
| `aggregations` | `dict[str, list]` | Facet results by field |
| `links` | `list[GroundingLink]` | External reference links |
| `publishers` | `list[PublisherDetail]` | Publisher authority data (type, dates, location) |
| `connections` | `list[dict]` | Auto-discovered agent relationships (when 2-10 agents, no explicit find_connections step) |

### RecordSummary

| Field | Type | Description |
|-------|------|-------------|
| `mms_id` | `str` | |
| `title` | `str` | |
| `date_display` | `str | None` | |
| `place` | `str | None` | |
| `publisher` | `str | None` | |
| `language` | `str | None` | |
| `agents` | `list[str]` | Agent names |
| `subjects` | `list[str]` | Subject headings |
| `physical_description` | `str | None` | MARC 300 physical description |
| `notes` | `list[str]` | General/summary notes (tags 500/520, max 3, 200 chars) |
| `primo_url` | `str` | Link to Primo catalog |
| `source_steps` | `list[int]` | Steps that produced this record |
| `date_confidence` | `float | None` | Date normalization confidence (0.0-1.0) |
| `place_confidence` | `float | None` | Place normalization confidence |
| `publisher_confidence` | `float | None` | Publisher normalization confidence |
| `title_variants` | `list[str]` | Uniform and variant titles (skipped for >15 records) |
| `notes_structured` | `dict[str, list[str]]` | Notes grouped by MARC tag (500/504/505/520/590; skipped for >15 records) |
| `subjects_he` | `list[str]` | Hebrew subject heading translations |

### AgentSummary

| Field | Type | Description |
|-------|------|-------------|
| `canonical_name` | `str` | |
| `variants` | `list[str]` | Name variants |
| `birth_year` | `int | None` | |
| `death_year` | `int | None` | |
| `occupations` | `list[str]` | |
| `description` | `str | None` | |
| `record_count` | `int` | Records in collection |
| `links` | `list[GroundingLink]` | External reference links |
| `wikipedia_context` | `str | None` | Extended bio from Wikipedia cache |
| `image_url` | `str | None` | Wikipedia portrait/image URL |
| `authority_uri` | `str | None` | NLI/VIAF/LC authority record URI |
| `hebrew_aliases` | `list[str]` | Hebrew-script name variants |

### PublisherDetail

| Field | Type | Description |
|-------|------|-------------|
| `canonical_name` | `str` | Normalized publisher name |
| `type` | `str | None` | Publisher type (printing_house, private_press, etc.) |
| `dates_active` | `str | None` | Active period (e.g., "1495-1515") |
| `location` | `str | None` | Geographic location |
| `wikidata_id` | `str | None` | Wikidata identifier |
| `cerl_id` | `str | None` | CERL Thesaurus identifier |

### GroundingLink

| Field | Type | Description |
|-------|------|-------------|
| `entity_type` | `str` | `"record"`, `"agent"`, `"publisher"` |
| `entity_id` | `str` | MMS ID or authority ID |
| `label` | `str` | Display label |
| `url` | `str` | Full URL |
| `source` | `str` | `"primo"`, `"wikipedia"`, `"wikidata"`, `"viaf"`, `"nli"` |

### Stage 3: ScholarResponse (Narrator output)

| Field | Type | Description |
|-------|------|-------------|
| `narrative` | `str` | Markdown scholarly response |
| `suggested_followups` | `list[str]` | 2--4 follow-up questions |
| `grounding` | `GroundingData` | Passed through from executor |
| `confidence` | `float` | 0.0--1.0 |
| `metadata` | `dict` | Model name, streaming flag, etc. |

---

## 8. API Layer

**Module:** `app/api/models.py`, `app/api/main.py`

### ChatRequest (POST /chat)

| Field | Type | Description |
|-------|------|-------------|
| `message` | `str` | User's natural language query (min 1 char) |
| `session_id` | `Optional[str]` | Creates new session if omitted |
| `context` | `Dict[str, Any]` | Additional context to merge |
| `token_saving` | `bool` | Default `True` -- use lean prompt builder |

### ChatResponseAPI (POST /chat response)

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | |
| `response` | `Optional[ChatResponse]` | Inner response |
| `error` | `Optional[str]` | Error message if `success=False` |

### ChatResponse (inner response)

| Field | Type | Description |
|-------|------|-------------|
| `message` | `str` | Narrative text (markdown) |
| `candidate_set` | `Optional[CandidateSet]` | Currently `None` in scholar pipeline (grounding used instead) |
| `suggested_followups` | `List[str]` | |
| `clarification_needed` | `Optional[str]` | |
| `session_id` | `str` | |
| `phase` | `Optional[ConversationPhase]` | `"query_definition"` or `"corpus_exploration"` |
| `confidence` | `Optional[float]` | 0.0--1.0 |
| `thematic_context` | `Optional[str]` | |
| `metadata` | `Dict[str, Any]` | Contains `intents` and `grounding` from scholar pipeline |

### WebSocket Message Types (ws://host/ws/chat)

| Type | Direction | Key Fields |
|------|-----------|------------|
| `session_created` | server->client | `session_id: str` |
| `progress` | server->client | `message: str` |
| `stream_chunk` | server->client | `text: str` (narrative fragment) |
| `complete` | server->client | `response: ChatResponse` |
| `error` | server->client | `message: str` |

---

## 9. Frontend

**Module:** `frontend/src/types/chat.ts`

TypeScript interfaces mirror the backend Pydantic models.

### ChatMessage (UI-only)

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | UUID |
| `role` | `'user' | 'assistant'` | |
| `content` | `string` | Message text |
| `candidateSet` | `CandidateSet | null` | |
| `suggestedFollowups` | `string[]` | |
| `clarificationNeeded` | `string | null` | |
| `phase` | `ConversationPhase | null` | |
| `confidence` | `number | null` | |
| `metadata` | `Record<string, unknown>` | |
| `timestamp` | `Date` | |
| `streamingState?` | `StreamingState` | `'thinking'`, `'streaming'`, `'complete'` |
| `thinkingSteps?` | `string[]` | Progress messages during streaming |

### GroundingData (TS)

| Field | Type |
|-------|------|
| `records` | `GroundingRecord[]` |
| `agents` | `GroundingAgent[]` |
| `aggregations` | `Record<string, unknown[]>` |
| `links` | `GroundingLink[]` |
| `publishers?` | `PublisherDetail[]` |
| `connections?` | `Record<string, unknown>[]` |

### GroundingRecord (TS)

Mirrors `RecordSummary` from the backend.

| Field | Type |
|-------|------|
| `mms_id` | `string` |
| `title` | `string` |
| `date_display` | `string | null` |
| `place` | `string | null` |
| `publisher` | `string | null` |
| `language` | `string | null` |
| `agents` | `string[]` |
| `subjects` | `string[]` |
| `primo_url` | `string` |
| `source_steps` | `number[]` |
| `date_confidence?` | `number | null` |
| `place_confidence?` | `number | null` |
| `publisher_confidence?` | `number | null` |
| `title_variants?` | `string[]` |
| `notes_structured?` | `Record<string, string[]>` |
| `subjects_he?` | `string[]` |

### GroundingAgent (TS)

Mirrors `AgentSummary` from the backend.

| Field | Type |
|-------|------|
| `canonical_name` | `string` |
| `variants` | `string[]` |
| `birth_year` | `number | null` |
| `death_year` | `number | null` |
| `occupations` | `string[]` |
| `description` | `string | null` |
| `record_count` | `number` |
| `links` | `GroundingLink[]` |
| `image_url?` | `string | null` |
| `authority_uri?` | `string | null` |
| `hebrew_aliases?` | `string[]` |

### PublisherDetail (TS)

| Field | Type |
|-------|------|
| `canonical_name` | `string` |
| `type?` | `string | null` |
| `dates_active?` | `string | null` |
| `location?` | `string | null` |
| `wikidata_id?` | `string | null` |
| `cerl_id?` | `string | null` |

---

## 10. Auth & Session

### Auth Database

**Path:** `data/auth/auth.db`
**Module:** `app/api/auth_db.py`

#### users

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | |
| `username` | `TEXT UNIQUE NOT NULL` | |
| `password_hash` | `TEXT NOT NULL` | bcrypt hash |
| `role` | `TEXT NOT NULL` | CHECK: `admin`, `full`, `limited`, `guest` |
| `token_limit` | `INTEGER` | Default 50000 |
| `is_active` | `BOOLEAN` | Default 1 |
| `locked_until` | `TEXT` | Account lockout timestamp |
| `failed_login_attempts` | `INTEGER` | Default 0 |
| `created_at` | `TEXT NOT NULL` | Default `datetime('now')` |
| `created_by` | `INTEGER FK -> users(id)` | |
| `last_login` | `TEXT` | |

#### refresh_tokens

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | |
| `user_id` | `INTEGER FK -> users(id)` | |
| `token_hash` | `TEXT UNIQUE NOT NULL` | |
| `expires_at` | `TEXT NOT NULL` | |
| `created_at` | `TEXT NOT NULL` | Default `datetime('now')` |

#### token_usage

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | |
| `user_id` | `INTEGER FK -> users(id)` | |
| `month` | `TEXT NOT NULL` | YYYY-MM format |
| `tokens_used` | `INTEGER` | Default 0 |
| `input_tokens` | `INTEGER` | Default 0 |
| `output_tokens` | `INTEGER` | Default 0 |
| `cost_usd` | `REAL` | Default 0.0 |
| `model` | `TEXT` | Default `""` |

UNIQUE constraint: `(user_id, month)`.

#### settings

| Column | Type | Notes |
|--------|------|-------|
| `key` | `TEXT PK` | |
| `value` | `TEXT NOT NULL` | |

Initial settings: `chat_enabled = "true"`, `monthly_cost_cap_usd = "50"`.

#### audit_log

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | |
| `timestamp` | `TEXT NOT NULL` | Default `datetime('now')` |
| `user_id` | `INTEGER` | |
| `username` | `TEXT` | |
| `action` | `TEXT NOT NULL` | |
| `details` | `TEXT` | |
| `ip_address` | `TEXT` | |

### Session Database

**Path:** `data/chat/sessions.db`
**Schema:** `scripts/chat/schema.sql`

#### chat_sessions

| Column | Type | Notes |
|--------|------|-------|
| `session_id` | `TEXT PK` | UUID |
| `user_id` | `TEXT` | |
| `created_at` | `TEXT NOT NULL` | ISO 8601 |
| `updated_at` | `TEXT NOT NULL` | ISO 8601 |
| `context` | `TEXT` | JSON-serialized dict |
| `metadata` | `TEXT` | JSON-serialized dict |
| `expired_at` | `TEXT` | NULL if active |
| `phase` | `TEXT` | Default `"query_definition"` |

#### chat_messages

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `session_id` | `TEXT FK -> chat_sessions` | CASCADE DELETE |
| `role` | `TEXT NOT NULL` | CHECK: `user`, `assistant`, `system` |
| `content` | `TEXT NOT NULL` | |
| `query_plan` | `TEXT` | JSON-serialized QueryPlan |
| `candidate_set` | `TEXT` | JSON-serialized CandidateSet |
| `timestamp` | `TEXT NOT NULL` | ISO 8601 |

#### active_subgroups

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `session_id` | `TEXT UNIQUE FK -> chat_sessions` | One per session, CASCADE DELETE |
| `defining_query` | `TEXT NOT NULL` | |
| `filter_summary` | `TEXT NOT NULL` | |
| `record_ids` | `TEXT NOT NULL` | JSON array of MMS IDs |
| `candidate_count` | `INTEGER NOT NULL` | |
| `candidate_set` | `TEXT` | JSON-serialized (optional) |
| `created_at` | `TEXT NOT NULL` | ISO 8601 |

#### user_goals

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PK` | Auto-increment |
| `session_id` | `TEXT FK -> chat_sessions` | CASCADE DELETE |
| `goal_type` | `TEXT NOT NULL` | `"find_specific"`, `"analyze_corpus"`, `"compare"`, `"discover"` |
| `description` | `TEXT NOT NULL` | |
| `elicited_at` | `TEXT NOT NULL` | ISO 8601 |

---

## 11. Database Map

| Database | Path | Tables |
|----------|------|--------|
| **bibliographic.db** | `data/index/bibliographic.db` | `records`, `titles`, `imprints`, `subjects`, `agents`, `languages`, `notes`, `physical_descriptions`, `titles_fts`, `subjects_fts`, `authority_enrichment`, `publisher_authorities`, `publisher_variants`, `agent_authorities`, `agent_aliases`, `wikipedia_cache`, `wikipedia_connections`, `network_edges`, `network_agents` |
| **sessions.db** | `data/chat/sessions.db` | `chat_sessions`, `chat_messages`, `active_subgroups`, `user_goals` |
| **auth.db** | `data/auth/auth.db` | `users`, `refresh_tokens`, `token_usage`, `settings`, `audit_log` |
| **qa.db** | `data/qa/qa.db` | `qa_queries`, `qa_candidate_labels`, `qa_query_gold`, `qa_sessions` |
| **query_plan_cache** | `data/query_plan_cache.jsonl` | N/A (append-only JSONL, `query_text -> QueryPlan`) |

---

## 12. Provenance Chain

A concrete example of how a value traces from MARC XML to frontend display:

```
MARC XML  <datafield tag="264" ind1=" " ind2="1">
            <subfield code="b">apud C. Plantinum,</subfield>
          </datafield>
    |
    v
M1 CanonicalRecord.imprints[0].publisher:
    SourcedValue(value="apud C. Plantinum,", source=["264$b"])
    |
    v
M2 M2Enrichment.imprints_norm[0].publisher_norm:
    PublisherNormalization(
        value="christophe plantin",
        display="Christophe Plantin",
        confidence=0.95,
        method="publisher_alias_map",
        evidence_paths=["imprints[0].publisher"]
    )
    |
    v
M3 imprints row:
    publisher_raw = "apud C. Plantinum,"
    publisher_norm = "christophe plantin"
    publisher_display = "Christophe Plantin"
    publisher_confidence = 0.95
    publisher_method = "publisher_alias_map"
    |
    v
M4 Filter(field="publisher", op="EQUALS", value="christophe plantin")
    -> SQL: WHERE i.publisher_norm = :publisher_0
    -> Evidence(field="publisher_norm", value="christophe plantin",
                source="marc:264$b[0]", confidence=0.95)
    |
    v
Scholar pipeline:
    RecordSummary(publisher="Christophe Plantin", ...)
    GroundingLink(label="Christophe Plantin", url="https://primo.example/...", source="primo")
    |
    v
API ChatResponse.metadata.grounding.records[N].publisher = "Christophe Plantin"
    |
    v
Frontend GroundingRecord.publisher = "Christophe Plantin"
```

At every stage the raw value `"apud C. Plantinum,"` is preserved alongside the normalized `"christophe plantin"`, ensuring reversibility and auditability.

---

## 13. Strengths

1. **Raw-value preservation alongside normalization.** Every normalized field (date, place, publisher, agent) stores both raw and normalized forms with confidence and method tags. Normalization is fully reversible.

2. **Comprehensive confidence and provenance metadata.** Every transformation carries a `confidence` score (0.0--1.0), `method` tag, and `evidence_paths` back to M1 JSON paths. This enables quality filtering and debugging.

3. **Clean three-stage scholar pipeline with immutable handoffs.** Interpreter produces a typed `InterpretationPlan`, Executor returns `ExecutionResult` with `GroundingData`, Narrator receives only verified data. No stage can bypass the contract.

4. **Rich authority model with variant forms and cross-script support.** Both `publisher_variants` and `agent_aliases` support Latin, Hebrew, and other scripts with typed alias categories (`variant_spelling`, `cross_script`, `patronymic`, etc.).

5. **FTS5 integration with sync triggers.** Full-text search on titles and subjects stays in sync with the content tables via INSERT/UPDATE/DELETE triggers, avoiding manual reindexing.

6. **Effective batching in grounding collection.** The executor batches DB lookups for titles, imprints, agents, and subjects across all step results using `WHERE mms_id IN (...)`, minimizing round-trips.

7. **Deterministic execution with dependency resolution (Kahn's algorithm).** Execution steps declare `depends_on` indices. The executor resolves order via topological sort and validates against circular dependencies before running any step.

8. **Graceful fallback when narrator LLM fails.** `_fallback_response()` builds a structured summary from `ExecutionResult` data without any LLM call, ensuring the user always receives a response.

---

## 14. Weaknesses

### Resolved

1. ~~**Foreign keys not enforced in m3_index.py or db_adapter.py.**~~ **FIXED** — `PRAGMA foreign_keys = ON` added to m3_index.py, db_adapter.py, service.py, m3_query.py, executor.py.

2. ~~**Silent exception swallowing in `fetch_display_info`.**~~ **FIXED** — 5 bare `except Exception: pass` blocks replaced with `logger.warning()` calls.

3. ~~**CandidateSet always None in scholar pipeline.**~~ **FIXED** — `_build_candidate_set()` in app/api/main.py builds CandidateSet from ExecutionResult for both HTTP and WebSocket paths.

4. ~~**RecordSummary omits physical description and notes.**~~ **FIXED** — Added `physical_description` and `notes` fields to RecordSummary. Executor batch-fetches MARC 300 (physical), 500/520 (general notes/summary) — capped at 3 notes per record, 200 chars each. Additionally, `notes_structured` groups notes by MARC tag (500/504/505/520/590) for records sets of 15 or fewer.

5. ~~**Grounding truncation at 30 records loses total count.**~~ **FIXED** — Added `total_record_count: int` to ExecutionResult, set before truncation.

6. ~~**M2 normalization alignment depends on array index matching.**~~ **FIXED** — Warning logged when M1 imprint count differs from M2 imprints_norm count during indexing.

7. ~~**Streaming mode hardcodes confidence=0.85 and empty followups.**~~ **FIXED** — Post-streaming call via gpt-4.1-nano extracts real followups and confidence. Falls back to defaults on failure.

### Open (accepted risk)

8. **Network tables not in m3_schema.sql (inline DROP+CREATE).** Cosmetic — network tables are computed/derived data. Accepted.

9. **No composite indexes for common multi-filter queries.** Not needed at current scale (~2,800 records). Revisit if collection grows 10x+.

10. **No imprint-level agent association.** MARC agent fields (100/700) are record-level, not imprint-level. Would require inference logic. Deferred — most records have a single imprint.
