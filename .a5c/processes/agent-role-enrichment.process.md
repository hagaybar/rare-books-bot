# Agent Role Enrichment — Process Description

## Goal

Enrich the `role_norm` field for 1,302 unique agents in the bibliographic database that currently have `role_norm='other'` and `role_source='unknown'` due to missing MARC relator terms.

## Strategy: Three-Tier Approach

### Tier 1: Cached Wikidata Occupations (684 agents, ~52%)
These agents already have Wikidata occupations stored in `authority_enrichment.person_info.occupations`. The occupations just need to be mapped to MARC-compatible `role_norm` values. Zero API calls needed.

### Tier 2: Authority URI Re-fetch (~298 agents, ~23%)
These agents have NLI authority URIs but the Wikidata enrichment returned no occupations (or wasn't fetched). Re-query Wikidata SPARQL for P106 (occupation). Fallback to VIAF if Wikidata fails.

### Tier 3: Web Search (~40 high-frequency agents, ~3%)
Agents with no authority URI that appear 3+ times in the collection. Use web search to determine role with confidence scoring based on source agreement.

### Remaining (~280 agents, ~22%)
Low-frequency agents with no authority data. Remain as `role_norm='other'` — not worth the search effort for single-occurrence agents.

## Multi-Role Handling

When an agent has multiple matching occupations (e.g., "printer, bookseller, cartographer"), ALL matching roles are stored — one row per role in the agents table. The highest-priority role (book-production roles first) becomes the primary row.

## Key Artifacts

| File | Purpose |
|------|---------|
| `data/normalization/occupation_role_map.json` | Wikidata occupation → role_norm mapping |
| `data/normalization/wikidata_occupations_raw.txt` | All unique Wikidata occupation labels |
| `data/normalization/tier{1,2,3}_role_changes.jsonl` | Change logs per tier |
| `data/normalization/tier3_web_search_results.json` | Web search results for review |
| `data/normalization/role_enrichment_final_report.json` | Final before/after report |
| `scripts/normalization/apply_wikidata_roles.py` | Tier 1 application script |
| `scripts/normalization/fetch_tier2_occupations.py` | Tier 2 fetch + apply script |

## Breakpoints

1. **After Phase 1**: Review the occupation → role mapping table before applying to any data
2. **After Tier 3 search**: Review web search results before applying to database

## Success Criteria

- Aldus Manutius (`manuzio, aldo`) has `role_norm = 'printer'`
- Role distribution shifts significantly from `other` to specific roles
- No test regressions
- All changes are logged and auditable
