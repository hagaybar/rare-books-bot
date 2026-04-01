# Pydantic Model Index

> Comprehensive model reference. 117 models (5 Enums + 112 BaseModels) across 12 files.

---

## Cross-Module (`scripts/shared_models.py`)

| Model | Type | Description |
|-------|------|-------------|
| `ExternalLink` | BaseModel | Unified external reference link (Primo, Wikipedia, Wikidata, VIAF, NLI, ISNI, LoC) |

---

## Chat Domain

### Session & Messages (`scripts/chat/models.py`)

| Model | Type | Description |
|-------|------|-------------|
| `ConversationPhase` | Enum | Current conversation phase: `QUERY_DEFINITION` or `CORPUS_EXPLORATION` |
| `ExplorationIntent` | Enum | Phase 2 intent classification (9 values): `METADATA_QUESTION`, `AGGREGATION`, `ENRICHMENT_REQUEST`, `RECOMMENDATION`, `COMPARISON`, `REFINEMENT`, `CROSS_REFERENCE`, `CURATION`, `NEW_QUERY` |
| `ActiveSubgroup` | BaseModel | Currently defined CandidateSet being explored, with defining query and record IDs |
| `UserGoal` | BaseModel | Elicited user goal for corpus exploration (goal_type + description) |
| `Message` | BaseModel | Single conversation message with role, content, optional QueryPlan/CandidateSet |
| `ChatSession` | BaseModel | Conversation session with message history, context, and metadata |
| `ChatResponse` | BaseModel | Response from chatbot: message, candidate_set, followups, clarification, phase, confidence |
| `Connection` | BaseModel | Discovered relationship between two agents with evidence and confidence |
| `AgentNode` | BaseModel | Node in agent relationship graph with biographical data and connections |
| `ComparisonFacets` | BaseModel | Multi-faceted comparison data: counts, date ranges, language/agent/subject distributions |
| `ComparisonResult` | BaseModel | Result of comparing field values (e.g., Venice vs Amsterdam) with faceted data |

### Execution Pipeline (`scripts/chat/plan_models.py`)

#### Enums & Typed Params

| Model | Type | Description |
|-------|------|-------------|
| `StepAction` | Enum | Executor action types (7 values): `RESOLVE_AGENT`, `RESOLVE_PUBLISHER`, `RETRIEVE`, `AGGREGATE`, `FIND_CONNECTIONS`, `ENRICH`, `SAMPLE` |
| `ResolveAgentParams` | BaseModel | Params for `resolve_agent`: name + optional LLM-proposed variants |
| `ResolvePublisherParams` | BaseModel | Params for `resolve_publisher`: name + optional variants |
| `RetrieveParams` | BaseModel | Params for `retrieve`: list of Filters + scope (`full_collection` or `$step_N`) |
| `AggregateParams` | BaseModel | Params for `aggregate`: field, scope, limit |
| `FindConnectionsParams` | BaseModel | Params for `find_connections`: agent list + depth |
| `EnrichParams` | BaseModel | Params for `enrich`: targets + fields to fetch (bio, links) |
| `SampleParams` | BaseModel | Params for `sample`: scope, n, strategy |

#### Step Output Types

| Model | Type | Description |
|-------|------|-------------|
| `ResolvedEntity` | BaseModel | Output of resolve actions: matched values, match method, confidence |
| `RecordSet` | BaseModel | Output of retrieve/sample: mms_ids, total count, filters applied |
| `AggregationResult` | BaseModel | Output of aggregate: field, facet list, total records |
| `ConnectionGraph` | BaseModel | Output of find_connections: connection list + isolated agents |
| `GroundingLink` | BaseModel | Single external reference link for evidence grounding (Primo, Wikipedia, etc.) |
| `AgentSummary` | BaseModel | Enriched agent profile: canonical name, variants, dates, occupations, links, Wikipedia context |
| `EnrichmentBundle` | BaseModel | Output of enrich: wraps one or more AgentSummary profiles |

#### Plan Models (Interpreter Output)

| Model | Type | Description |
|-------|------|-------------|
| `ExecutionStep` | BaseModel | Single plan step: action, typed params, label, dependencies |
| `ScholarlyDirective` | BaseModel | Free-form narrator instruction with params and label |
| `InterpretationPlan` | BaseModel | Complete interpreter output: intents, reasoning, steps, directives, confidence, optional clarification |

#### Execution Models (Executor Output)

| Model | Type | Description |
|-------|------|-------------|
| `StepResult` | BaseModel | Result of one executed step: status (`ok`/`empty`/`partial`/`error`), typed data |
| `RecordSummary` | BaseModel | Bibliographic record summary for narrator: title, date, place, agents, subjects, Primo URL |
| `GroundingData` | BaseModel | Aggregated grounding evidence: records, agents, aggregations, links |
| `SessionContext` | BaseModel | Follow-up context from previous turn: session_id, messages, record IDs |
| `ExecutionResult` | BaseModel | Complete executor output: step results, directives, grounding, original query |

#### Response Model (Narrator Output)

| Model | Type | Description |
|-------|------|-------------|
| `ScholarResponse` | BaseModel | Final scholarly response: narrative markdown, followups, grounding, confidence |

#### LLM-Facing Models (OpenAI Responses API)

| Model | Type | Description |
|-------|------|-------------|
| `ExecutionStepLLM` | BaseModel | Simplified step for LLM: string action + JSON-encoded params string |
| `ScholarlyDirectiveLLM` | BaseModel | LLM-facing directive: string params for `additionalProperties: false` compatibility |
| `InterpretationPlanLLM` | BaseModel | LLM output schema: uses `ExecutionStepLLM` / `ScholarlyDirectiveLLM` |

---

## Query Domain

### Query Plan (`scripts/schemas/query_plan.py`)

| Model | Type | Description |
|-------|------|-------------|
| `FilterField` | Enum | Supported filter fields (12 values): `PUBLISHER`, `IMPRINT_PLACE`, `COUNTRY`, `YEAR`, `LANGUAGE`, `TITLE`, `SUBJECT`, `AGENT`, `AGENT_NORM`, `AGENT_ROLE`, `AGENT_TYPE` |
| `FilterOp` | Enum | Filter operations (4 values): `EQUALS`, `CONTAINS`, `RANGE`, `IN` |
| `Filter` | BaseModel | Single filter condition: field, op, value/start/end, negate, confidence, notes |
| `QueryPlan` | BaseModel | Structured query plan: filters, soft_filters, limit, debug (intermediate between NL and SQL) |

### Candidate Set (`scripts/schemas/candidate_set.py`)

| Model | Type | Description |
|-------|------|-------------|
| `Evidence` | BaseModel | Why a record matched: field, value, operator, matched_against, source, confidence |
| `Candidate` | BaseModel | Single matched record with rationale and evidence list, plus display fields |
| `CandidateSet` | BaseModel | Complete query result: query text, plan hash, SQL, candidates, total count |

### Query Execution (`scripts/query/models.py`)

| Model | Type | Description |
|-------|------|-------------|
| `QueryWarning` | BaseModel | Warning from execution: code, message, field, confidence |
| `FacetCounts` | BaseModel | Facet aggregations: by place, year, language, publisher, century |
| `QueryOptions` | BaseModel | Execution options: compute_facets, facet_limit, include_warnings, limit |
| `QueryResult` | BaseModel | Unified result from QueryService: plan, SQL, params, candidate_set, facets, warnings |

---

## MARC Domain

### Canonical Records -- M1 (`scripts/marc/models.py`)

| Model | Type | Description |
|-------|------|-------------|
| `SourcedValue` | BaseModel | Value with MARC source provenance (field$subfield list) |
| `ImprintData` | BaseModel | Raw imprint from MARC 260/264: place, publisher, date, manufacturer |
| `AgentData` | BaseModel | Author/contributor: name, entry_role, function, dates, agent_type, authority_uri |
| `SubjectData` | BaseModel | Subject heading: display string, structured parts, scheme, heading_lang, authority_uri |
| `NoteData` | BaseModel | Note with explicit MARC tag (500, 590, etc.) |
| `SourceMetadata` | BaseModel | Record-level source: source_file, control_number |
| `CanonicalRecord` | BaseModel | Full canonical bibliographic record: title, imprints, languages, subjects, agents, notes, physical description |
| `ExtractionReport` | BaseModel | MARC extraction summary: counts, field coverage stats, missing field details |

### Normalization -- M2 (`scripts/marc/m2_models.py`)

| Model | Type | Description |
|-------|------|-------------|
| `DateNormalization` | BaseModel | Normalized date: start/end year, label, confidence, method, evidence_paths |
| `PlaceNormalization` | BaseModel | Normalized place: canonical key, display form, confidence, method |
| `PublisherNormalization` | BaseModel | Normalized publisher: canonical key, display form, confidence, method |
| `ImprintNormalization` | BaseModel | Normalized imprint: combines date/place/publisher normalization |
| `AgentNormalization` | BaseModel | Normalized agent name: raw, norm, confidence, method, notes |
| `RoleNormalization` | BaseModel | Normalized role: raw, norm, confidence, method |
| `M2Enrichment` | BaseModel | M2 enrichment container: normalized imprints + agents (appended to M1 records) |

---

## Enrichment Domain (`scripts/enrichment/models.py`)

| Model | Type | Description |
|-------|------|-------------|
| `EntityType` | Enum | Entity types (5 values): `AGENT`, `PLACE`, `PUBLISHER`, `SUBJECT`, `WORK` |
| `EnrichmentSource` | Enum | External sources (6 values): `NLI`, `WIKIDATA`, `VIAF`, `LOC`, `ISNI`, `CACHE` |
| `ExternalIdentifier` | BaseModel | External identifier: source, identifier, URL |
| `EnrichmentRequest` | BaseModel | Request to enrich an entity: type, value, NLI authority, preferred sources, priority |
| `PersonInfo` | BaseModel | Biographical info: birth/death, nationality, occupations, teachers, students, notable works |
| `PlaceInfo` | BaseModel | Geographic info: country, coordinates, modern name, historical names |
| `EnrichmentResult` | BaseModel | Complete enrichment result: external IDs, person/place info, metadata, confidence |
| `NLIAuthorityIdentifiers` | BaseModel | Identifiers from NLI/Wikidata: NLI, Wikidata, VIAF, ISNI, LoC IDs + fetch method |
| `CacheEntry` | BaseModel | Enrichment cache entry: entity type, key, source, data, confidence, expiration |

---

## API Layer

### Core API (`app/api/models.py`)

| Model | Type | Description |
|-------|------|-------------|
| `ChatRequest` | BaseModel | Request to `/chat`: message, session_id, context, token_saving flag |
| `ChatResponseAPI` | BaseModel | Response wrapper for `/chat`: success, ChatResponse, error |
| `HealthResponse` | BaseModel | Response from `/health`: status, database/session/executor readiness |
| `HealthExtendedResponse` | BaseModel | Extended health: DB file size, last modified, QA DB status |

### Authentication (`app/api/auth_models.py`)

| Model | Type | Description |
|-------|------|-------------|
| `LoginRequest` | BaseModel | Login credentials: username, password |
| `TokenResponse` | BaseModel | Login response: message, username, role |
| `UserInfo` | BaseModel | User profile: ID, username, role, activity, token usage, cost |
| `CreateUserRequest` | BaseModel | Create user: username, password (with complexity validation), role, token_limit |
| `UpdateUserRequest` | BaseModel | Update user: role, is_active, token_limit, new_password |
| `UserListItem` | BaseModel | User list entry: ID, username, role, activity, token usage |

### Metadata Quality (`app/api/metadata_models.py`)

#### Coverage

| Model | Type | Description |
|-------|------|-------------|
| `ConfidenceBandResponse` | BaseModel | Single confidence band with label, bounds, and record count |
| `MethodBreakdownResponse` | BaseModel | Count of records by normalization method |
| `FlaggedItemResponse` | BaseModel | Low-confidence value with raw/norm value, confidence, frequency |
| `FieldCoverageResponse` | BaseModel | Coverage stats for one field: totals, confidence distribution, method distribution, flagged items |
| `CoverageResponse` | BaseModel | Full coverage report: date/place/publisher/agent_name/agent_role coverage |

#### Issues

| Model | Type | Description |
|-------|------|-------------|
| `IssueRecord` | BaseModel | Single low-confidence record: mms_id, raw/norm value, confidence, method |
| `IssuesResponse` | BaseModel | Paginated issue list with field, threshold, total, and items |

#### Unmapped & Methods

| Model | Type | Description |
|-------|------|-------------|
| `UnmappedValue` | BaseModel | Raw value without canonical mapping: value, frequency, confidence, method |
| `MethodDistribution` | BaseModel | Distribution entry: method name, count, percentage |

#### Clusters

| Model | Type | Description |
|-------|------|-------------|
| `ClusterValueResponse` | BaseModel | Single value within a cluster: raw value, frequency, confidence, method |
| `ClusterResponse` | BaseModel | Cluster of related values: ID, field, type, values, proposed canonical, evidence, priority |

#### Corrections

| Model | Type | Description |
|-------|------|-------------|
| `CorrectionRequest` | BaseModel | Submit correction: field, raw_value, canonical_value, evidence, source |
| `CorrectionResponse` | BaseModel | Correction result: success, alias map path, records affected |
| `CorrectionHistoryEntry` | BaseModel | Audit trail entry: timestamp, field, raw/canonical, evidence, source, action |
| `CorrectionHistoryResponse` | BaseModel | Paginated correction history |
| `BatchCorrectionRequest` | BaseModel | Multiple corrections in one request |
| `BatchCorrectionResult` | BaseModel | Per-correction result within a batch: raw/canonical, success, records affected, error |
| `BatchCorrectionResponse` | BaseModel | Batch result summary: applied, skipped, total records affected, per-correction results |

#### Primo URLs

| Model | Type | Description |
|-------|------|-------------|
| `PrimoUrlRequest` | BaseModel | Request: list of MMS IDs + optional base URL override |
| `PrimoUrlEntry` | BaseModel | Single MMS ID to Primo URL mapping |
| `PrimoUrlResponse` | BaseModel | Response: list of URL entries |

#### Agent Chat

| Model | Type | Description |
|-------|------|-------------|
| `AgentChatRequest` | BaseModel | Request: field, message, optional session_id |
| `AgentProposal` | BaseModel | LLM-proposed canonical mapping: raw/canonical, confidence, reasoning, evidence sources |
| `AgentClusterSummary` | BaseModel | Cluster summary for chat: ID, type, value count, total records, priority |
| `AgentChatResponse` | BaseModel | Agent response: text, proposals, clusters, field, action |

#### Publisher Authorities

| Model | Type | Description |
|-------|------|-------------|
| `PublisherVariantResponse` | BaseModel | Name variant: form, script, language, is_primary |
| `PublisherAuthorityResponse` | BaseModel | Publisher identity: canonical name, type, confidence, dates, location, variants, external IDs |
| `PublisherAuthorityListResponse` | BaseModel | Paginated list of publisher authorities |
| `CreatePublisherRequest` | BaseModel | Create publisher: canonical_name, type, confidence, location, dates_active, notes |
| `UpdatePublisherRequest` | BaseModel | Update publisher: all fields optional |
| `CreateVariantRequest` | BaseModel | Add variant: variant_form, script, language |
| `MatchPreviewResponse` | BaseModel | Preview: variant form + number of matching imprints |
| `DeleteResponse` | BaseModel | Generic deletion confirmation: success, message |

---

## Type Aliases

These union types are defined in `scripts/chat/plan_models.py` for discriminated dispatch:

| Alias | Definition | Used By |
|-------|------------|---------|
| `StepParams` | `Union[ResolveAgentParams, ResolvePublisherParams, RetrieveParams, AggregateParams, FindConnectionsParams, EnrichParams, SampleParams]` | `ExecutionStep.params` |
| `StepOutputData` | `Union[ResolvedEntity, RecordSet, AggregationResult, ConnectionGraph, EnrichmentBundle]` | `StepResult.data` |

---

## File Summary

| File | BaseModels | Enums | Total |
|------|-----------|-------|-------|
| `scripts/shared_models.py` | 1 | 0 | 1 |
| `scripts/chat/models.py` | 9 | 2 | 11 |
| `scripts/chat/plan_models.py` | 26 | 1 | 27 |
| `scripts/schemas/query_plan.py` | 2 | 2 | 4 |
| `scripts/schemas/candidate_set.py` | 3 | 0 | 3 |
| `scripts/enrichment/models.py` | 7 | 2 | 9 |
| `scripts/marc/models.py` | 8 | 0 | 8 |
| `scripts/marc/m2_models.py` | 7 | 0 | 7 |
| `scripts/query/models.py` | 4 | 0 | 4 |
| `app/api/models.py` | 4 | 0 | 4 |
| `app/api/auth_models.py` | 6 | 0 | 6 |
| `app/api/metadata_models.py` | 33 | 0 | 33 |
| **Total** | **110** | **7** | **117** |
