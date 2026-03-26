# Full Ingestion Pipeline — Flow Diagram

```
MARC XML (rare_book_bibs.xml)
│
├─ Phase 1: Backup + Core Rebuild (~2 min)
│  │
│  ├─ [backup] Auto-backup existing bibliographic.db
│  │
│  ├─ [M1] Parse MARC XML ──→ data/canonical/records.jsonl
│  │   └─ Extract: records, agents ($0 URIs), imprints, subjects, titles
│  │
│  ├─ [M2] Normalize ──→ data/m2/records_m1m2.jsonl
│  │   ├─ Dates: 12 patterns + Hebrew calendar
│  │   ├─ Places: 196+ aliases (99.3% coverage)
│  │   ├─ Publishers: 2,152 aliases (98.8% coverage)
│  │   └─ Agents: name normalization
│  │
│  └─ [M3] Build SQLite index ──→ bibliographic.db
│      └─ 8 core tables + FTS5 indexes
│
├─ Phase 2: Authority Systems (~1 min)
│  │
│  ├─ Seed agent_authorities + agent_aliases
│  │   └─ primary, variant_spelling, cross_script, word_reorder
│  │
│  └─ Populate publisher_authorities + publisher_variants
│      └─ (if publisher_research.json exists)
│
├─ [BREAKPOINT] ── User confirms enrichment ──
│
├─ Phase 3: Wikidata Enrichment (~10-60 min)
│  │
│  ├─ [$0 exists?] ──yes──→ NLI → Wikidata lookup (~2,600 agents)
│  │                 └─no──→ Name-based search (~200-400 agents)
│  │
│  ├─ Populate authority_enrichment
│  │   └─ wikidata_id, viaf_id, person_info (birth/death, occupations)
│  │
│  └─ Re-enrich with relationships
│      └─ teachers, students, notable_works, hebrew_labels
│
├─ Phase 4: Wikipedia Enrichment (~1-4 hours)
│  │
│  ├─ Pass 1: Links + categories (~1 min)
│  │   └─ MediaWiki API → wikipedia_cache
│  │
│  ├─ Pass 2: Summaries (~45 min)
│  │   └─ Wikipedia REST API → summary_extract + name_variants
│  │
│  ├─ Pass 3: LLM extraction (~$0.50)
│  │   └─ gpt-4.1-nano → wikipedia_connections (llm_extraction)
│  │
│  └─ Connection discovery
│      └─ Cross-reference wikilinks → wikipedia_connections (wikilink, category)
│
├─ Phase 5: Network Tables (~1 min)
│  │
│  ├─ network_edges (5 types unified)
│  │   ├─ wikilink, llm_extraction, category (from wikipedia_connections)
│  │   ├─ teacher_student (from authority_enrichment.person_info)
│  │   └─ co_publication (from agents sharing records)
│  │
│  └─ network_agents (geocoded, display names, connection counts)
│
└─ Phase 6: Final Verification
    └─ Report: table counts, coverage metrics, DB size
```

## Data Flow

```
MARC XML ──→ JSONL ──→ Normalized JSONL ──→ SQLite
                                              │
                              ┌────────────────┤
                              │                │
                         Authorities      Wikidata API
                              │                │
                              │           Wikipedia API
                              │                │
                              │           gpt-4.1-nano
                              │                │
                              └───── Network Tables
```
