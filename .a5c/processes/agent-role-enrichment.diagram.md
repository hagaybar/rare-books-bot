# Agent Role Enrichment — Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE 0: BACKUP & ANALYSIS                       │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐  │
│  │ Backup DB    │───>│ Analyze scope: count per tier,           │  │
│  │ (timestamped)│    │ extract all Wikidata occupation labels   │  │
│  └──────────────┘    └──────────────────────────────────────────┘  │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                PHASE 1: BUILD OCCUPATION → ROLE MAPPING             │
│                                                                     │
│  ┌─────────────────────┐    ┌──────────────────────────────────┐   │
│  │ Read all unique      │───>│ Map each to role_norm:           │   │
│  │ Wikidata occupations │    │  • Direct: printer → printer     │   │
│  │ (~200+ labels)       │    │  • Semantic: poet → author       │   │
│  └─────────────────────┘    │  • Unmapped: sovereign → skip    │   │
│                              │  + Priority order for multi-role │   │
│                              └──────────────────────────────────┘   │
│                                          │                          │
│                                          ▼                          │
│                              ┌──────────────────────┐              │
│                              │ 🛑 BREAKPOINT:       │              │
│                              │ Review mapping table  │              │
│                              └──────────────────────┘              │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│          PHASE 2: TIER 1 — CACHED WIKIDATA OCCUPATIONS             │
│          (~684 agents — already have occupations in DB)             │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ For each agent with cached occupations:                      │  │
│  │  1. Extract occupations from authority_enrichment.person_info│  │
│  │  2. Look up each in occupation_role_map.json                 │  │
│  │  3. Update primary row with highest-priority role            │  │
│  │  4. INSERT additional rows for secondary roles               │  │
│  │  5. Log every change to tier1_role_changes.jsonl             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│                              ▼                                      │
│                    ┌──────────────────┐                             │
│                    │ Verify Tier 1    │                             │
│                    │ (spot-check 5)   │                             │
│                    └──────────────────┘                             │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│          PHASE 3: TIER 2 — WIKIDATA/VIAF RE-FETCH                  │
│          (~298 agents — have authority URI, no occupations)         │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ For each agent:                                              │  │
│  │  1. Extract NLI ID from authority_uri                        │  │
│  │  2. Query Wikidata SPARQL (P8189) for QID                   │  │
│  │  3. Fetch occupations (P106) from Wikidata                  │  │
│  │  4. Fallback: try VIAF if Wikidata has no occupations       │  │
│  │  5. Apply mapping → update/insert rows                      │  │
│  │  Rate limit: 1 req/sec                                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│                              ▼                                      │
│                    ┌──────────────────┐                             │
│                    │ Verify Tier 2    │                             │
│                    │ (spot-check 5)   │                             │
│                    └──────────────────┘                             │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│          PHASE 4: TIER 3 — WEB SEARCH (HIGH-FREQUENCY)             │
│          (~40 agents — no authority URI, freq >= 3)                 │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ For each agent:                                              │  │
│  │  1. Web search: "{name} role occupation printer publisher"   │  │
│  │  2. Score confidence by source quality & agreement:          │  │
│  │     • 0.85+ : Multiple authoritative sources agree           │  │
│  │     • 0.70-0.84: 2-3 sources or one authoritative           │  │
│  │     • 0.55-0.69: Single source, uncertain                   │  │
│  │     • <0.55: Skip, leave as "other"                          │  │
│  │  3. Save to tier3_web_search_results.json (DO NOT APPLY)    │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│                              ▼                                      │
│                    ┌──────────────────────┐                        │
│                    │ 🛑 BREAKPOINT:       │                        │
│                    │ Review web search    │                        │
│                    │ results before apply │                        │
│                    └──────────────────────┘                        │
│                              │                                      │
│                              ▼                                      │
│                    ┌──────────────────────┐                        │
│                    │ Apply approved       │                        │
│                    │ Tier 3 results       │                        │
│                    └──────────────────────┘                        │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│          PHASE 5: FINAL VERIFICATION & TESTS                       │
│                                                                     │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────┐ │
│  │ Before/After      │    │ Test case:       │    │ Run pytest   │ │
│  │ comparison        │    │ Aldus Manutius   │    │ (regression) │ │
│  │ + confidence dist │    │ now = printer?   │    │              │ │
│  └──────────────────┘    └──────────────────┘    └──────────────┘ │
│                                                                     │
│  Output: data/normalization/role_enrichment_final_report.json      │
└─────────────────────────────────────────────────────────────────────┘
```
