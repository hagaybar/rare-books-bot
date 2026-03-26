# Full Ingestion Pipeline — Flow Diagram

```
MARC XML (rare_book_bibs.xml)
│
├─ Phase 1: Backup + Core Rebuild (~2 min)
│  ├─ [backup] Auto-backup existing bibliographic.db
│  ├─ [M1] Parse MARC XML ──→ data/canonical/records.jsonl
│  │   └─ Extract: records, agents ($0 URIs), imprints, subjects, titles
│  ├─ [M2] Normalize ──→ data/m2/records_m1m2.jsonl
│  │   ├─ Dates: 12 patterns + Hebrew calendar
│  │   ├─ Places: 196+ aliases (99.3% coverage)
│  │   ├─ Publishers: 2,152 aliases (98.8% coverage)
│  │   └─ Agents: name normalization
│  └─ [M3] Build SQLite index ──→ bibliographic.db
│
├─ Phase 2: QA Audit & Correction Loop (~5-15 min)
│  │
│  ├─ [audit] Scan all normalization gaps
│  │   └─ Output: data/qa/norm_audit.json
│  │
│  ├─ [date-fix] Categorize + propose date fixes
│  │   ├─ hebrew_unparsed, complex_range, circa_variant, etc.
│  │   └─ Output: data/qa/date_fixes_proposed.json
│  │
│  ├─ [place-fix] Categorize + propose place fixes
│  │   ├─ latin_toponym, hebrew_place, historical_rename, etc.
│  │   └─ Output: data/qa/place_fixes_proposed.json
│  │
│  ├─ [pub-fix] Categorize + propose publisher fixes
│  │   └─ Output: data/qa/publisher_fixes_proposed.json
│  │
│  ├─ [BREAKPOINT] ── User reviews proposed fixes ──
│  │
│  ├─ [apply] Update alias maps + add normalize.py patterns
│  ├─ [re-run] M2+M3 with updated maps
│  └─ [verify] Confirm coverage improved
│
├─ Phase 3: Authority Systems (~1 min)
│  ├─ Seed agent_authorities + agent_aliases
│  └─ Populate publisher_authorities + publisher_variants
│
├─ [BREAKPOINT] ── User confirms enrichment ──
│
├─ Phase 4: Wikidata Enrichment (~10-60 min)
│  ├─ [$0 exists?] ──yes──→ NLI → Wikidata lookup (~2,600 agents)
│  │                 └─no──→ Name-based search (~200-400 agents)
│  ├─ Populate authority_enrichment
│  └─ Re-enrich with relationships (teachers, students, works)
│
├─ Phase 5: Wikipedia Enrichment (~1-4 hours)
│  ├─ Pass 1: Links + categories (~1 min)
│  ├─ Pass 2: Summaries (~45 min)
│  ├─ Pass 3: LLM extraction (~$0.50)
│  └─ Connection discovery (wikilink, category, llm_extraction)
│
├─ Phase 6: Network Tables (~1 min)
│  ├─ network_edges (5 types unified)
│  └─ network_agents (geocoded, display names)
│
└─ Phase 7: Final Verification Report
```
