# Derived-Artifact Invariant Audit

Date: 2026-06-12 | DB: `data/index/bibliographic.db` (+ `data/chat/sessions.db`) | Branch: dev | Mode: read-only (SELECT/PRAGMA via `sqlite3 -readonly`)

Preliminaries: `PRAGMA integrity_check` = ok; `PRAGMA foreign_key_check` = empty (both DBs).

Derivation sources consulted: `scripts/marc/m3_contract.py` (table/column registry), `scripts/marc/m3_schema.sql` (FTS triggers, embedded in DB schema), `scripts/network/build_network_tables.py` (network_agents/edges, `PUBLISHER_PREFIX='pub:'` at line 519; orphan-edge removal at lines 880–886), `scripts/metadata/seed_agent_authorities.py` (alias seeding, per fix_29 docstring), `scripts/qa/fixes/fix_19/20/21/22/23/25/26/27/28/29`.

## Invariant table

| # | Artifact | Invariant (one sentence) | SQL (violation count) | Count | Verdict |
|---|----------|--------------------------|------------------------|-------|---------|
| I1 | agent_aliases ← agents/agent_authorities | Every agent_norm linked to an authority via authority_uri has an alias row (fix_29 contract) | `SELECT COUNT(*) FROM (SELECT DISTINCT ag.agent_norm FROM agents ag JOIN agent_authorities aa ON aa.authority_uri=ag.authority_uri WHERE ag.agent_norm NOT IN (SELECT alias_form_lower FROM agent_aliases))` | 26 | VIOLATION |
| I2 | agent_aliases | No primary alias is a comma-fragment of one of its own authority's expected norms without being an expected norm itself | `SELECT COUNT(*) FROM (SELECT DISTINCT al.id FROM agent_aliases al JOIN agent_authorities aa ON aa.id=al.authority_id JOIN agents ag ON ag.authority_uri=aa.authority_uri WHERE al.alias_type='primary' AND ag.agent_norm LIKE '%,%' AND (','||REPLACE(ag.agent_norm,', ',',')||',') LIKE ('%,'||al.alias_form_lower||',%') AND al.alias_form_lower<>ag.agent_norm AND al.alias_form_lower NOT IN (SELECT ag2.agent_norm FROM agents ag2 WHERE ag2.authority_uri=aa.authority_uri))` | 0 | OK |
| I3 | agent_aliases | Every alias row references an existing agent_authorities row | `SELECT COUNT(*) FROM agent_aliases al LEFT JOIN agent_authorities aa ON aa.id=al.authority_id WHERE aa.id IS NULL` | 0 | OK |
| I4 | agent_aliases | For ASCII forms, alias_form_lower = lower(alias_form) | `SELECT COUNT(*) FROM agent_aliases WHERE alias_form NOT GLOB '*[^ -~]*' AND alias_form_lower <> lower(alias_form)` | 0 | OK |
| I5 | agent_authorities | For ASCII names, canonical_name_lower = lower(canonical_name); no duplicate canonical_name_lower | `SELECT COUNT(*) FROM agent_authorities WHERE canonical_name NOT GLOB '*[^ -~]*' AND canonical_name_lower <> lower(canonical_name)` (+ dup-group count A2) | 0 | OK |
| A1 | agent_aliases | alias_form_lower is globally unique (resolution determinism) | `SELECT COUNT(*) FROM (SELECT alias_form_lower FROM agent_aliases GROUP BY alias_form_lower HAVING COUNT(*)>1)` | 0 | OK |
| P1 | publisher_variants | Every variant references an existing publisher_authorities row | `SELECT COUNT(*) FROM publisher_variants pv LEFT JOIN publisher_authorities pa ON pa.id=pv.authority_id WHERE pa.id IS NULL` | 0 | OK |
| P2 | publisher_variants/authorities ← imprints | Every publisher_norm appearing on >1 record is a canonical form, or a variant form, of some authority | `SELECT COUNT(*) FROM (SELECT i.publisher_norm pn FROM imprints i WHERE i.publisher_norm IS NOT NULL GROUP BY i.publisher_norm HAVING COUNT(DISTINCT i.record_id)>1) p WHERE p.pn NOT IN (SELECT canonical_name_lower FROM publisher_authorities) AND p.pn NOT IN (SELECT variant_form_lower FROM publisher_variants)` | 0 | OK |
| P3 | publisher_variants vs publisher_authorities | No variant_form_lower equals the canonical_name_lower of a *different* authority (resolution must be unambiguous) | `SELECT COUNT(*) FROM publisher_variants pv JOIN publisher_authorities pa ON pa.canonical_name_lower=pv.variant_form_lower AND pa.id<>pv.authority_id` | 3 | VIOLATION |
| P4/P6 | publisher_variants | variant_form_lower equals lower(variant_form) or, when intentionally divergent (orthographic mapping), resolves to an actual imprints.publisher_norm | strict-ASCII check = 5; restated: `SELECT COUNT(*) FROM publisher_variants pv WHERE pv.variant_form_lower <> lower(pv.variant_form) AND NOT EXISTS (SELECT 1 FROM imprints i WHERE i.publisher_norm = pv.variant_form_lower)` | 0 | OK (note) |
| F1 | titles_fts | Row count parity with titles (external-content FTS5 kept in sync by triggers; fix_20 rebuild) | `SELECT (SELECT COUNT(*) FROM titles) - (SELECT COUNT(*) FROM titles_fts)` | 0 (4791 = 4791) | OK |
| F2 | titles_fts | Every titles.id is present as a titles_fts rowid | `SELECT COUNT(*) FROM titles t WHERE t.id NOT IN (SELECT rowid FROM titles_fts)` | 0 | OK |
| F3 | subjects_fts | Row count parity with subjects (contentless FTS5, triggers feed value + value_he) | `SELECT (SELECT COUNT(*) FROM subjects) - (SELECT COUNT(*) FROM subjects_fts)` | 0 (6226 = 6226) | OK |
| F4 | subjects_fts | Every subjects.id is a subjects_fts rowid, and no FTS rowid lacks a subject row | `SELECT COUNT(*) FROM subjects s WHERE s.id NOT IN (SELECT rowid FROM subjects_fts)` (+ reverse) | 0 / 0 | OK |
| N1 | network_edges → network_agents | Both edge endpoints resolve to existing network_agents nodes (build removes orphans, build_network_tables.py:880–886) | `SELECT COUNT(*) FROM network_edges e WHERE e.source_agent_norm NOT IN (SELECT agent_norm FROM network_agents) OR e.target_agent_norm NOT IN (SELECT agent_norm FROM network_agents)` | 2 | VIOLATION |
| N2 | network_agents (person) → agents | Every person node's agent_norm exists in agents.agent_norm | `SELECT COUNT(*) FROM network_agents na WHERE na.node_type='person' AND na.agent_norm NOT IN (SELECT DISTINCT agent_norm FROM agents)` | 0 | OK |
| N3 | network_agents (publisher) → publisher_authorities | Every publisher node's key minus the `pub:` prefix is a canonical_name_lower in publisher_authorities | `SELECT COUNT(*) FROM network_agents na WHERE na.node_type='publisher' AND substr(na.agent_norm,5) NOT IN (SELECT canonical_name_lower FROM publisher_authorities)` | 0 | OK |
| N4 | network_agents.connection_count | connection_count equals the number of network_edges touching the node | `SELECT COUNT(*) FROM network_agents na WHERE na.connection_count <> (SELECT COUNT(*) FROM network_edges e WHERE e.source_agent_norm=na.agent_norm OR e.target_agent_norm=na.agent_norm)` | 0 | OK |
| N5 | network_agents.record_count | For person nodes, record_count equals COUNT(DISTINCT record_id) in agents for that norm | `SELECT COUNT(*) FROM network_agents na WHERE na.node_type='person' AND na.record_count <> (SELECT COUNT(DISTINCT a.record_id) FROM agents a WHERE a.agent_norm=na.agent_norm)` | 0 | OK |
| N6 | network_edges | No self-loop edges; confidence in [0,1] | `SELECT COUNT(*) FROM network_edges WHERE source_agent_norm=target_agent_norm` (+ bounds) | 0 / 0 | OK |
| W1 | network_edges ← wikipedia_connections | Every wikipedia_connections row whose endpoints are both network nodes is projected as a network_edge of connection_type = source_type | `SELECT COUNT(*) FROM wikipedia_connections wc WHERE wc.source_agent_norm IN (SELECT agent_norm FROM network_agents) AND wc.target_agent_norm IN (SELECT agent_norm FROM network_agents) AND NOT EXISTS (SELECT 1 FROM network_edges e WHERE e.source_agent_norm=wc.source_agent_norm AND e.target_agent_norm=wc.target_agent_norm AND e.connection_type=wc.source_type)` | 0 | OK |
| E1 | agent_authorities ← authority_enrichment | When both sides carry a wikidata_id for the same authority_uri, they agree | `SELECT COUNT(*) FROM agent_authorities aa JOIN authority_enrichment ae ON ae.authority_uri=aa.authority_uri WHERE aa.wikidata_id IS NOT NULL AND ae.wikidata_id IS NOT NULL AND aa.wikidata_id <> ae.wikidata_id` | 1 | VIOLATION |
| E2 | network_agents.birth_year ← authority_enrichment | Every non-null person birth_year is backed by person_info.birth_year of an enrichment row reachable via agents.authority_uri | `... NOT EXISTS (SELECT 1 FROM agents a JOIN authority_enrichment ae ON ae.authority_uri=a.authority_uri WHERE a.agent_norm=na.agent_norm AND CAST(json_extract(ae.person_info,'$.birth_year') AS INTEGER)=na.birth_year)` | 0 | OK |
| E3 | network_agents.has_wikipedia | has_wikipedia=1 implies an enrichment wikidata_id with a wikipedia_cache row exists for the norm | `... NOT EXISTS (agents→authority_enrichment→wikipedia_cache join)` | 0 | OK |
| E4 | network_agents.community | Non-null community implies the norm reaches wikipedia_cache categories via enrichment (assign_communities source, build_network_tables.py:58–116) | `... NOT EXISTS (agents→authority_enrichment→wikipedia_cache WHERE categories IS NOT NULL)` | 0 | OK |
| S1 | subjects.value_he | Row-level Hebrew coverage matches documented 83.6% (docs/current/data-quality.md:261) | `SELECT ROUND(100.0*SUM(value_he IS NOT NULL)/COUNT(*),1) FROM subjects` | 83.6% (5,207/6,226) | OK — drift 0.0 |
| S2 | subjects.value_he | Unique-heading coverage matches documented 78.4% | `SELECT ROUND(100.0*(SELECT COUNT(DISTINCT value) FROM subjects WHERE value_he IS NOT NULL)/(SELECT COUNT(DISTINCT value) FROM subjects),1)` | 78.4% | OK — drift 0.0 |
| S3 | subjects.value_he | No U+FFFD mojibake (fix_25 contract); no empty-string value_he | `SELECT COUNT(*) FROM subjects WHERE value_he LIKE '%'||char(65533)||'%'` (+ `=''`) | 0 / 0 | OK |
| M1 | imprints normalized columns | No normalized value without its preserved raw counterpart (reversibility rule) | `SELECT COUNT(*) FROM imprints WHERE (publisher_norm IS NOT NULL AND publisher_raw IS NULL) OR (place_norm IS NOT NULL AND place_raw IS NULL) OR ((date_start IS NOT NULL OR date_end IS NOT NULL) AND date_raw IS NULL)` | 0 | OK |
| M2 | imprints dates | date_start <= date_end when both present | `SELECT COUNT(*) FROM imprints WHERE date_start>date_end` | 0 | OK |
| M3 | imprints.country_name ← country_code | country_name (fix_10 derived) never present without its source country_code | `SELECT COUNT(*) FROM imprints WHERE country_name IS NOT NULL AND country_code IS NULL` | 0 | OK |
| R1 | record_scope_flags → records | Every flag references an existing record | `SELECT COUNT(*) FROM record_scope_flags f LEFT JOIN records r ON r.id=f.record_id WHERE r.id IS NULL` | 0 | OK |
| C1 | sessions.db chat_messages → chat_sessions | Every message's session_id resolves to a chat_sessions row | `SELECT COUNT(*) FROM chat_messages m WHERE m.session_id NOT IN (SELECT session_id FROM chat_sessions)` | 0 | OK |

UNVERIFIED (read-only constraint): token-level content parity of `titles_fts` with `titles` text (the FTS5 `'integrity-check'` command is an INSERT and was not run). Rowcount + rowid-set parity (F1–F4) were verified instead.

## Violation details

### I1 — 26 authority-linked agent_norms have no alias row (VIOLATION, n=26)

Samples (agent_norm → linked authority):
- `adam` → Adam de la Halle
- `rené` → René of Anjou (the fix_09 "bare René" case)
- `מנשה` (and 23 more mononyms: `august`, `eusebius`, `giovanni` → John of Procida, `thomas` → Antoine Léonard Thomas, `יהודה` → Judah Halevi, ...)

Root cause (diagnosed, code-verified): these are all bare mononym norms. In `scripts/qa/fixes/fix_29_repair_agent_alias_fragments.py:84-93`, the collision check (`SELECT authority_id FROM agent_aliases WHERE alias_form_lower = ? AND authority_id != ?`) ran against the **pre-deletion** alias state. A mononym like `adam` was at plan time still held by another authority as a comma-split fragment (e.g. of `smith, adam`), so it was classified a collision and skipped — and then the fragment row itself was deleted by that other authority's cleanup. Net result: the form now exists nowhere (verified: 0 of the 26 forms appear in agent_aliases under any authority). The fix's own closing report only counted *comma*-norms as residual orphans (fix_29 lines 148–153), so these mononyms were invisible to it. Cross-script/name resolution through `agent_aliases` will miss these 26 agents.

### P3 — 3 publisher variant forms shadow other authorities' canonical names (VIOLATION, n=3)

| variant (authority 229 = "Proops Press, Amsterdam", printing_house) | shadowed authority | shadowed type | records on shadowed canonical |
|---|---|---|---|
| `בדפוס ובבית שלמה בן יוסף פרופס` | id 33 | unknown_marker | 5 |
| `בבית ובדפוס שלמה בן יוסף כ"ץ פרופס` | id 41 | unknown_marker | 4 |
| `בדפוס ובבית שלמה בן יוסף כ"ץ פרופס` | id 78 | unknown_marker | 3 |

The same imprint form resolves to two authorities at once: as the canonical name of a raw-form placeholder (`unknown_marker`, 0 variants of its own) and as a curated variant of the Proops Press authority (added by the fix_27/fix_28 Hebrew-press work). Any resolver that checks canonicals before variants (or vice versa) will give different answers; the placeholder authorities 33/41/78 are superseded duplicates that were never retired.

### N1 — 2 network edges with a non-existent endpoint (VIOLATION, n=2)

| source | target | type | missing endpoint |
|---|---|---|---|
| `דרוקר, חיים בן יעקב` | `מנשה בן ישראל` | same_place_period | target |
| `מנשה בן ישראל` | `קארו, יוסף בן אפרים` | same_place_period | source |

`מנשה בן ישראל` exists in `agents` (2 rows) but its network node was merged into the cross-script node `manasseh ben israel` (duplicate-merge step, `_merge_duplicate_agents` in build_network_tables.py); the two `same_place_period` edges were neither remapped to the surviving norm nor swept by the orphan-edge cleanup (build_network_tables.py:880–886), which runs *before* later additive steps. Frontend graph queries joining edges to nodes will silently drop these connections.

### E1 — 1 wikidata_id disagreement between agent_authorities and authority_enrichment (VIOLATION, n=1)

- Authority: `Alembert, Jean le Rond d'` — `agent_authorities.wikidata_id = Q106599741` vs `authority_enrichment.wikidata_id = Q153232` (same `authority_uri` .../987007257513805171.jsonld). Q153232 is the well-known d'Alembert item; Q106599741 looks like a wrong or duplicate QID on the authority row. Whichever side is wrong, the seam contract (both derived from the same NLI URI) is broken for this row.

### P4 note (OK, but invariant restated)

5 publisher_variants rows have `variant_form_lower <> lower(variant_form)` (e.g. `Apud Danielem Elzevirium` → `apud danielem elzevirivm`, u/v orthography; two rows carry a trailing `'` artifact). All 5 lower forms match actual `imprints.publisher_norm` values, so they are functional resolution mappings, not corruption — the column is used as "imprint-norm key", not strictly lowercase display. The restated invariant (P6: divergent lower forms must resolve to a real imprint norm) holds with 0 violations. The trailing-apostrophe norms are themselves upstream normalization artifacts worth a separate look.

## Proposed test encodings

1. **test_every_authority_linked_norm_has_alias** — assert I1 SQL returns 0 against bibliographic.db (currently xfail, n=26, fix_29 collision-ordering residue).
2. **test_no_comma_fragment_primary_aliases** — assert I2 SQL returns 0 (regression guard for the fix_29 seeding bug).
3. **test_alias_form_lower_globally_unique_and_fk_valid** — assert A1, I3, I4 all return 0.
4. **test_multi_record_publisher_norm_is_authority_linked** — assert P2 SQL returns 0 (every >1-record publisher_norm resolves to a canonical or variant form).
5. **test_variant_form_never_shadows_foreign_canonical** — assert P3 SQL returns 0 (currently xfail, n=3, Proops placeholders to retire).
6. **test_divergent_variant_lower_resolves_to_imprint_norm** — assert P6 SQL returns 0.
7. **test_fts_rowcount_and_rowid_parity** — assert titles/titles_fts and subjects/subjects_fts counts equal and rowid sets match (F1–F4 = 0).
8. **test_network_edge_endpoints_resolve** — assert N1 SQL returns 0 (currently xfail, n=2; also encode "orphan sweep runs after merge/additive steps" in the build).
9. **test_network_node_provenance** — assert N2 (person→agents) and N3 (`pub:` key → publisher_authorities canonical) return 0.
10. **test_network_counts_match_sources** — assert N4 (connection_count) and N5 (record_count) drift queries return 0.
11. **test_wikipedia_connections_projected_to_edges** — assert W1 SQL returns 0.
12. **test_enrichment_wikidata_agreement** — assert E1 SQL returns 0 (currently xfail, n=1, d'Alembert QID).
13. **test_network_derived_person_fields_backed_by_enrichment** — assert E2/E3/E4 (birth_year, has_wikipedia, community provenance) return 0.
14. **test_value_he_coverage_floor_and_no_mojibake** — assert unique-heading coverage >= 78.4%, row coverage >= 83.6%, and S3 (U+FFFD / empty string) returns 0.
15. **test_normalized_never_without_raw** — assert M1 (imprints norm-without-raw), M2 (date order), M3 (country_name without code) return 0 (encodes the reversibility rule from CLAUDE.md).
16. **test_scope_flags_and_chat_messages_referential** — assert R1 (bibliographic.db) and C1 (sessions.db) return 0.

SWEEP-COMPLETE
