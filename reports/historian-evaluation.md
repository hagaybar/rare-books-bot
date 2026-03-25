# Historian Evaluation Report: Rare Books Bot

**Date**: 2026-03-24
**Evaluator Persona**: Professor of Jewish Book History & Early Modern Print Culture
**System Under Test**: Rare Books Bot conversational interface (Phase 2 API)
**Collection**: 2,796 MARC XML records of rare books (primarily Hebraica and Judaica)

---

## Section 1: Professor Persona & Methodology

### Persona

The evaluator represents a senior university professor specializing in the history of Hebrew printing and early modern Jewish intellectual culture. This scholar regularly teaches courses on book history, uses rare book collections for research, and advises graduate students. The professor expects a discovery tool to support not just retrieval but also contextualization, comparison across printing centers, and pedagogical narrative construction.

### Methodology

Twenty questions were crafted across four scholarly domains to test the system's ability to serve as a research and teaching assistant. Each question was designed to require capabilities beyond simple keyword retrieval: comparative analysis, cross-referencing of entities, aggregation of patterns, and narrative synthesis. Questions were submitted as natural language queries through the `/chat` endpoint. Results were evaluated on five dimensions (Accuracy, Richness, Cross-referencing, Narrative Quality, Pedagogical Value), each scored 0-5.

---

## Section 2: The 20 Questions

| # | Category | Question (Abbreviated) | Key Quality Criteria |
|---|----------|----------------------|---------------------|
| Q1 | A: Printing History | Books from Bragadin press in Venice | Identify press, compare with other Venetian printers |
| Q2 | A: Printing History | Hebrew books printed in Amsterdam 1620-1650 | Find Menasseh ben Israel, contextualize early Dutch Hebrew printing |
| Q3 | A: Printing History | Aldine Press editions in the collection | Match Latin publisher forms ("in aedibus Aldi"), assess humanist context |
| Q4 | A: Printing History | Incunabula (pre-1500 books) | Identify earliest items, printing centers, significance |
| Q5 | A: Printing History | Books from Constantinople/Istanbul | Compare with Venice as Hebrew printing center |
| Q6 | B: Intellectual Networks | Works by Johann Buxtorf | Match "Buxtorf, Johann" form, contextualize Christian Hebraism |
| Q7 | B: Intellectual Networks | Works by Moses Mendelssohn | Match Hebrew and Latin name forms, Haskalah context |
| Q8 | B: Intellectual Networks | Works by Maimonides | Match "Maimonides, Moses" AND Hebrew form, philosophy significance |
| Q9 | B: Intellectual Networks | Works by Josephus Flavius | Multilingual editions, reception history |
| Q10 | B: Intellectual Networks | Books on Jewish philosophy | Subject heading coverage, intellectual movements |
| Q11 | C: Collection Character | Books from Napoleonic era (1795-1815) | Period significance, emancipation context |
| Q12 | C: Collection Character | Materials about Ethiopia/Ethiopian Jews | Faitlovitch materials, Beta Israel scholarship |
| Q13 | C: Collection Character | Books about book collecting/bibliography | Meta-collection, bibliophilic tradition |
| Q14 | C: Collection Character | Chronological shape of collection | Temporal distribution analysis, collecting patterns |
| Q15 | C: Collection Character | Major Hebrew printing centers | Geographic analysis, comparative printing history |
| Q16 | D: Teaching Support | Biblical commentaries for teaching | Core texts, commentators, teaching utility |
| Q17 | D: Teaching Support | Hebrew grammar books | Pedagogical tradition, Christian Hebraists |
| Q18 | D: Teaching Support | Talmud editions for teaching | Print history of Talmud, key editions |
| Q19 | D: Teaching Support | Works by Joseph Karo (Shulchan Aruch) | Match Hebrew name, legal codification history |
| Q20 | D: Teaching Support | Curated selection for exhibit on Hebrew printing | Selection, curation, exhibit narrative |

---

## Section 3: Simulation Results

| # | Query Sent | Filters Applied | Count | Narrative | Key Observation |
|---|-----------|----------------|-------|-----------|----------------|
| Q1 | "books printed by Bragadin press in Venice" | publisher CONTAINS "bragadin", place EQUALS "venice" | 16 | Yes | Good retrieval; no comparison with rival Venetian presses |
| Q2 | "Hebrew books printed in Amsterdam between 1620 and 1650" | place EQUALS "amsterdam", language EQUALS "heb", year RANGE 1620-1650 | 13 | Yes | Found Menasseh ben Israel; narrative agent provided bio |
| Q3 | "books published by the Aldine Press" | publisher CONTAINS "aldine" | 0 | No | ZERO results: "aldine" does not match "in aedibus Aldi" Latin forms |
| Q4 | "incunabula in the collection (books printed before 1500)" | year RANGE 1400-1499 | 13 | Yes | Good pre-1500 coverage; narrative identified early printers |
| Q5 | "books printed in Constantinople" | place EQUALS "constantinople" | 11 | Yes | Found Ottoman Hebrew printing; no Venice comparison |
| Q6 | "works by Johann Buxtorf" | agent_norm EQUALS "johann buxtorf" | 0 | No | ZERO results: DB has "buxtorf, johann" (surname-first); LIKE "johann buxtorf" fails on word order |
| Q7 | "works by Moses Mendelssohn" | agent_norm EQUALS "moses mendelssohn" | 0 | No | ZERO results: some records in Hebrew form only; word-order mismatch on Latin form |
| Q8 | "works by Maimonides" | agent_norm CONTAINS "maimonides" | 7 | Yes | Partial: found 7 of ~20; missed Hebrew form records |
| Q9 | "works by Josephus Flavius" | subject CONTAINS "josephus" | 30 | Yes | Good multilingual coverage via subject headings |
| Q10 | "books on Jewish philosophy" | subject CONTAINS "jewish philosophy" | 21 | Yes | Good subject coverage; meaningful results |
| Q11 | "books from the Napoleonic era 1795-1815" | year RANGE 1795-1815 | 40 | Yes | Good retrieval; no contextual analysis of emancipation impact |
| Q12 | "materials about Ethiopia or Ethiopian Jews" | subject CONTAINS "ethiopia" | 17 | Yes | Found some; missed ~40 Faitlovitch records not tagged with "Ethiopia" subject |
| Q13 | "books about book collecting or bibliography" | subject CONTAINS "bibliography" | 26 | Yes | Good subject match; includes bibliophilic materials |
| Q14 | "chronological distribution of the collection" | (none -- entire collection) | 2796 | No | ALL records returned; no temporal analysis capability |
| Q15 | "major Hebrew printing centers represented" | language EQUALS "heb" | 806 | No | Large result set; no geographic aggregation presented |
| Q16 | "biblical commentaries" | subject CONTAINS "bible commentaries" | 11 | Yes | Found core texts; limited pedagogical framing |
| Q17 | "Hebrew grammar books" | subject CONTAINS "hebrew language grammar" | 47 | Yes | Found Buxtorf via subject (not via agent); good coverage |
| Q18 | "Talmud editions" | subject CONTAINS "talmud" | 42 | Yes | Good coverage of Talmud materials |
| Q19 | "works by Joseph Karo" | agent_norm EQUALS "joseph karo" | 0 | No | ZERO results: DB stores Hebrew form only |
| Q20 | "curated selection for Hebrew printing exhibit" | subject CONTAINS "hebrew printing" OR "printing history" | 120 | No | Large set; no curation or selection capability |

**Summary**: 15/20 queries returned results (75%). 4 returned zero results due to name form mismatch. 3 had narrative agent skipped due to result set size exceeding the 100-record threshold.

---

## Section 4: Gap Analysis

### Scoring Dimensions (0-5 each)

| # | Question | Accuracy | Richness | Cross-Ref | Narrative | Pedagogical | Total (/25) | Root Causes |
|---|----------|----------|----------|-----------|-----------|-------------|-------------|-------------|
| Q1 | Bragadin Venice | 4 | 2 | 1 | 3 | 2 | 12 | NO_COMPARISON, THIN_NARRATIVE |
| Q2 | Amsterdam Hebrew 1620-1650 | 4 | 3 | 2 | 3 | 3 | 15 | MISSING_CROSS_REF |
| Q3 | Aldine Press | 0 | 0 | 0 | 0 | 0 | 0 | NAME_FORM_MISMATCH |
| Q4 | Incunabula | 4 | 3 | 1 | 3 | 3 | 14 | NO_COMPARISON, THIN_NARRATIVE |
| Q5 | Constantinople | 4 | 2 | 1 | 3 | 2 | 12 | NO_COMPARISON |
| Q6 | Buxtorf | 0 | 0 | 0 | 0 | 0 | 0 | NAME_FORM_MISMATCH |
| Q7 | Mendelssohn | 0 | 0 | 0 | 0 | 0 | 0 | NAME_FORM_MISMATCH |
| Q8 | Maimonides | 2 | 2 | 1 | 2 | 2 | 9 | NAME_FORM_MISMATCH (partial) |
| Q9 | Josephus | 4 | 3 | 1 | 3 | 3 | 14 | MISSING_CROSS_REF |
| Q10 | Jewish philosophy | 4 | 3 | 1 | 3 | 3 | 14 | MISSING_CROSS_REF |
| Q11 | Napoleon era | 3 | 2 | 0 | 2 | 2 | 9 | NO_AGGREGATION, THIN_NARRATIVE |
| Q12 | Ethiopia | 2 | 2 | 1 | 2 | 2 | 9 | NAME_FORM_MISMATCH (subject variant) |
| Q13 | Book collecting | 4 | 2 | 1 | 3 | 2 | 12 | MISSING_CROSS_REF |
| Q14 | Chronological shape | 1 | 0 | 0 | 0 | 0 | 1 | NO_AGGREGATION, LARGE_SET_SILENT |
| Q15 | Printing centers | 1 | 0 | 0 | 0 | 0 | 1 | NO_AGGREGATION, LARGE_SET_SILENT |
| Q16 | Biblical commentary | 3 | 2 | 1 | 3 | 2 | 11 | THIN_NARRATIVE |
| Q17 | Hebrew grammar | 4 | 3 | 2 | 3 | 3 | 15 | MISSING_CROSS_REF |
| Q18 | Talmud | 4 | 2 | 1 | 3 | 2 | 12 | THIN_NARRATIVE |
| Q19 | Joseph Karo | 0 | 0 | 0 | 0 | 0 | 0 | NAME_FORM_MISMATCH |
| Q20 | Curated exhibit | 1 | 0 | 0 | 0 | 0 | 1 | NO_CURATION, LARGE_SET_SILENT |

### Root Cause Detail

**Q1 (Bragadin Venice)**: Retrieval is accurate (16 records). However, the response does not compare Bragadin with di Gara, Bomberg, or Giustiniani -- rival Venetian printers whose output would contextualize the Bragadin holdings. The narrative exists but lacks depth on the significance of the Bragadin family in the history of Hebrew censorship and the Council of Trent.

**Q3 (Aldine Press)**: The publisher normalization maps "aldine" to a CONTAINS search on `publisher_norm`. However, the actual stored forms are Latin phrases like "in aedibus aldi", "apud aldum", "apud paulum manutium aldi filium". The word "aldine" appears only in the composite form "aldine press, venice" (which is itself a publisher authority mapping), and a CONTAINS search for "aldine" should match this. The actual query compiled an EQUALS filter (not CONTAINS), causing zero matches since no `publisher_norm` value equals exactly "aldine".

**Q6 (Buxtorf)**: The DB stores `buxtorf, johann` (surname-first MARC convention). The LLM compiler generates an AGENT_NORM EQUALS filter with value `johann buxtorf` (given-name-first). The `normalize_filter_value` removes commas but the LIKE/EQUALS comparison fails because "buxtorf johann" != "johann buxtorf" -- word order matters in string comparison.

**Q7 (Mendelssohn)**: Same word-order issue as Q6. Additionally, some records exist only in Hebrew form, which a Latin-alphabet query cannot match without a cross-script alias map.

**Q8 (Maimonides)**: Partial success: CONTAINS "maimonides" matches 7 records with `maimonides, moses` in agent_norm. But 13+ additional records use the Hebrew form only. No cross-script bridge exists.

**Q14 (Chronological shape)**: This is an analytical question, not a retrieval question. The system returns all 2,796 records. What the professor wants is a decade-by-decade histogram showing collection density. The facet computation infrastructure exists (`_compute_facets` in `QueryService`) but is not surfaced in the Phase 1 response for collection-wide queries. The narrative agent skips sets >100 records.

**Q15 (Printing centers)**: Similar to Q14. The professor wants a geographic breakdown (Venice: N, Amsterdam: N, etc.). The aggregation engine exists in Phase 2 (`scripts/chat/aggregation.py`) but is not automatically invoked for analytical questions during Phase 1.

**Q19 (Joseph Karo)**: The DB stores only the Hebrew form: agent_norm = "קארו, יוסף בן אפרים". A Latin-alphabet query "joseph karo" cannot match. No agent alias map bridges the scripts.

**Q20 (Curated exhibit)**: The system has no selection/recommendation capability. It returns 120 records but cannot identify the 10-15 most historically significant, visually striking, or narratively compelling items for an exhibit.

---

## Section 5: Gap Pattern Analysis

### Pattern Frequency

| Root Cause | Questions Affected | Count | Impact |
|------------|-------------------|-------|--------|
| NAME_FORM_MISMATCH | Q3, Q6, Q7, Q8, Q12, Q19 | 6 | 4 total failures + 2 partial |
| MISSING_CROSS_REF | Q2, Q9, Q10, Q13, Q17 | 5 | Results found but connections unexplored |
| NO_AGGREGATION | Q11, Q14, Q15 | 3 | Analytical questions unanswerable |
| THIN_NARRATIVE | Q1, Q4, Q11, Q16, Q18 | 5 | Narrative exists but lacks scholarly depth |
| NO_COMPARISON | Q1, Q4, Q5 | 3 | Cannot juxtapose two sets |
| LARGE_SET_SILENT | Q14, Q15, Q20 | 3 | Narrative agent threshold (>100) blocks output |
| NO_CURATION | Q20 | 1 | Cannot select/recommend from results |

### Pattern Analysis

**1. NAME_FORM_MISMATCH is the most damaging pattern (6 questions, 4 total failures).**

This is a compound problem with three distinct sub-issues:

- **Word-order mismatch** (Q6, Q7): MARC stores names surname-first ("buxtorf, johann"). The query compiler generates given-name-first ("johann buxtorf"). After comma removal, the strings become "buxtorf johann" vs "johann buxtorf", which still fail string equality/LIKE comparison. The fix requires either (a) order-insensitive matching or (b) teaching the query compiler to emit surname-first format.

- **Cross-script mismatch** (Q7, Q8, Q19): Some agents exist only in Hebrew script in the database. A Latin-alphabet query cannot match without an alias/variant table that bridges script forms. The `publisher_variants` table demonstrates this pattern for publishers but no equivalent exists for agents.

- **Publisher synonym mismatch** (Q3): "Aldine Press" is a modern English name for a press known in MARC as "in aedibus Aldi" (Latin). The publisher authority system has a variant entry for "aldine press, venice" but the query compiler used EQUALS instead of CONTAINS, missing even this form.

**2. MISSING_CROSS_REF + THIN_NARRATIVE form a combined "depth" gap (8 questions).**

The narrative agent (`scripts/chat/narrative_agent.py`) produces biographical paragraphs from Wikidata enrichment data -- birth/death dates, occupations, teachers/students, notable works. This is valuable but insufficient for scholarly use. It does not connect agents across records (e.g., "Buxtorf appears in 10 records, his student Lightfoot in 3"), identify intellectual networks, or explain the significance of a result set in its historical context.

**3. NO_AGGREGATION blocks all analytical questions (3 questions).**

The aggregation engine in `scripts/chat/aggregation.py` is fully implemented for Phase 2 (corpus exploration). However, questions like Q14 ("chronological shape") and Q15 ("major printing centers") are analytical in nature and arrive during Phase 1 (query definition). The intent agent classifies them as retrieval queries, returns all records, and the narrative agent skips sets >100. The aggregation capability exists but is not routed correctly.

**4. LARGE_SET_SILENT is an artificial limitation (3 questions).**

The `_MAX_RESULT_SET = 100` threshold in `narrative_agent.py` causes the narrative agent to return `None` for result sets above 100 records. For Q14 (2,796), Q15 (806), and Q20 (120), this means no narrative is generated at all. Raising or removing this limit would help, but the real fix is routing analytical questions to the aggregation engine.

---

## Section 6: Top 5 Enhancements

### Enhancement 1: Agent Name Alias Table with Order-Insensitive Matching

**Name**: Agent Name Resolution Layer

**Description**: Create an `agent_aliases` table (analogous to `publisher_variants`) that maps common name forms -- including cross-script variants, given-name-first vs surname-first, and common transliterations -- to canonical agent identifiers. Modify the query adapter to consult this table during agent searches, and implement order-insensitive matching as a fallback.

**Questions improved**: Q3, Q6, Q7, Q8, Q12, Q19

**Impact**: 4 questions go from ZERO results to full results. 2 questions (Q8, Q12) go from partial to complete. Estimated score improvement: +70 points across 6 questions.

**Priority**: CRITICAL

**Implementation Tasks**:

1. **Create `agent_aliases` table** (1d)
   - Schema: `(alias_id, authority_id, variant_form, script, source, confidence)`
   - Populate from existing `authority_enrichment` table (Wikidata labels, Hebrew labels)
   - Add manual entries for known gaps: "Johann Buxtorf" -> "buxtorf, johann", "Moses Mendelssohn" -> "mendelssohn, moses" / "מנדלסון, משה", "Joseph Karo" -> "קארו, יוסף בן אפרים"
   - File: new migration in `scripts/marc/` or `scripts/metadata/`
   - Depends on: `authority_enrichment` table already populated

2. **Implement order-insensitive agent matching** (1d)
   - Modify `normalize_filter_value()` in `scripts/query/db_adapter.py` (line 95-110)
   - Split agent name into tokens, sort alphabetically, rejoin for comparison
   - Apply same normalization to DB values: `REPLACE(agent_norm, ',', '')` already exists; add token sort
   - Alternative: use a set-intersection approach (all query tokens must appear in agent_norm)

3. **Modify `build_where_clause()` for alias lookup** (1d)
   - In `scripts/query/db_adapter.py`, AGENT_NORM handler (line 293-312)
   - Add subquery: `OR a.authority_uri IN (SELECT authority_id FROM agent_aliases WHERE LOWER(variant_form) LIKE ...)`
   - This allows "Aldine Press" to match publisher variants too

4. **Populate alias table from enrichment data** (0.5d)
   - Script: `scripts/metadata/build_agent_aliases.py`
   - Sources: `authority_enrichment.label`, `authority_enrichment.person_info` (hebrew_label field)
   - Generate surname-first and given-name-first variants automatically

**Estimated effort**: 3.5 developer-days

**Dependencies**: None (self-contained)

---

### Enhancement 2: Analytical Query Routing

**Name**: Auto-Aggregation for Analytical Questions

**Description**: Detect when a query is analytical (asking about distribution, patterns, "shape", "centers") rather than retrieval-oriented, and automatically route to the aggregation engine instead of the standard query pipeline. This surfaces the existing Phase 2 aggregation capabilities during Phase 1.

**Questions improved**: Q14, Q15, Q20

**Impact**: 3 questions go from POOR (score 1) to GOOD (score 12+). Estimated score improvement: +33 points.

**Priority**: CRITICAL

**Implementation Tasks**:

1. **Add analytical query detection to intent agent** (1d)
   - Modify `scripts/chat/intent_agent.py`
   - Add new intent type: `ANALYTICAL` alongside existing `QUERY_DEFINITION`
   - Pattern detection keywords: "distribution", "chronological shape", "printing centers", "how many by decade", "geographic breakdown", "most common", "overview of"
   - LLM classification already parses intent; add `analytical_field` to schema (e.g., "date_decade", "place", "publisher")

2. **Route analytical queries to aggregation in Phase 1** (1d)
   - Modify `handle_query_definition_phase()` in `app/api/main.py` (line 424-688)
   - After intent classification, if analytical: execute full-collection aggregation via `execute_aggregation()` from `scripts/chat/aggregation.py`
   - Use `format_aggregation_response()` to build natural language summary
   - Skip candidate set return for pure analytical queries

3. **Add collection-level aggregation endpoints** (0.5d)
   - Modify `scripts/chat/aggregation.py` to accept `record_ids=None` as "all records"
   - Currently requires explicit record ID list; add path for full-table aggregation
   - Much faster SQL (no IN clause with thousands of IDs)

4. **Raise or contextualize narrative agent threshold** (0.5d)
   - In `scripts/chat/narrative_agent.py` line 22: `_MAX_RESULT_SET = 100`
   - For analytical queries, generate a statistical summary instead of per-agent bios
   - New function: `generate_analytical_summary()` that produces "This set spans 1470-1920, with peaks in the 1550s and 1780s"

**Estimated effort**: 3 developer-days

**Dependencies**: None

---

### Enhancement 3: Cross-Reference and Comparison Engine

**Name**: Entity Cross-Reference and Set Comparison

**Description**: Enable the system to surface connections between entities in a result set (e.g., teacher-student relationships, shared publishers across cities) and compare two result sets side-by-side (e.g., Venice vs Amsterdam printing).

**Questions improved**: Q1, Q2, Q4, Q5, Q9, Q10, Q13, Q17

**Impact**: 8 questions gain meaningful cross-referencing scores. Estimated score improvement: +24 points (average +3 per question on Cross-Ref dimension).

**Priority**: HIGH

**Implementation Tasks**:

1. **Build relationship extraction from enrichment data** (1.5d)
   - New module: `scripts/chat/cross_reference.py`
   - Query `authority_enrichment.person_info` for teacher/student/notable_works relationships
   - Build in-memory graph of agent relationships within a result set
   - Function: `find_connections(record_ids, db_path) -> List[Connection]`
   - `Connection` model: `(agent_a, agent_b, relationship_type, evidence)`

2. **Add comparison query support** (1.5d)
   - Modify `scripts/chat/exploration_agent.py` to handle `COMPARISON` intent
   - Function: `execute_comparison()` in `scripts/chat/aggregation.py` (already partially stubbed)
   - Input: two sets of filters (e.g., place=venice vs place=amsterdam)
   - Output: side-by-side facet comparison (dates, languages, publishers, agents)
   - Format as comparison table in response

3. **Integrate cross-references into narrative agent** (1d)
   - Modify `generate_agent_narrative()` in `scripts/chat/narrative_agent.py`
   - After generating individual bios, call `find_connections()`
   - Append a "Connections" section: "Buxtorf taught Lightfoot, both represented in this set"
   - Use `PersonInfo.teachers` and `PersonInfo.students` fields (already populated)

4. **Add "compare with" follow-up suggestion** (0.5d)
   - In `scripts/chat/formatter.py`, `generate_followups()`
   - For place-filtered results, suggest "Compare with [other major center]"
   - For agent results, suggest "Show related authors"

**Estimated effort**: 4.5 developer-days

**Dependencies**: Enhancement 1 (agent aliases) improves the quality of cross-references

---

### Enhancement 4: Scholarly Narrative Enrichment

**Name**: Contextual Narrative Depth Layer

**Description**: Enhance the narrative agent to produce scholarly-quality prose that contextualizes results within printing history, intellectual movements, and bibliographic significance. Move beyond biographical templates to thematic narratives.

**Questions improved**: Q1, Q2, Q4, Q5, Q11, Q16, Q18

**Impact**: 7 questions gain narrative and pedagogical depth. Estimated score improvement: +21 points (average +3 per question on Narrative + Pedagogical dimensions).

**Priority**: HIGH

**Implementation Tasks**:

1. **Create thematic context templates** (2d)
   - New module: `scripts/chat/thematic_context.py`
   - Pre-authored context paragraphs for major themes:
     - Venetian Hebrew printing and censorship
     - Amsterdam as "Dutch Jerusalem"
     - Christian Hebraism movement
     - Haskalah and Jewish Enlightenment
     - Incunabula and the spread of printing
     - Talmud printing controversies
   - Each template keyed by (subject, place, date_range) tuples
   - Function: `get_thematic_context(filters, result_set) -> Optional[str]`

2. **Integrate thematic context into response formatting** (0.5d)
   - Modify `handle_query_definition_phase()` in `app/api/main.py`
   - After query execution, call `get_thematic_context()` with the query plan filters
   - Append thematic paragraph after agent narrative
   - Clearly label as "[Historical Context]" with citation to reference works

3. **Add significance scoring for records** (1d)
   - New function in `scripts/chat/narrative_agent.py`
   - Score records by: (a) agent enrichment richness, (b) date (earlier = more significant for rare books), (c) place rarity, (d) edition number (first editions)
   - Surface top-3 "notable items" in response
   - Useful for Q20 (exhibit curation) as well

4. **Enhance pedagogical framing** (0.5d)
   - In `scripts/chat/formatter.py`, add pedagogical wrappers
   - "Teaching note: This set illustrates the transition from..."
   - "For further reading: [reference]"
   - Triggered when query matches a known teaching topic

**Estimated effort**: 4 developer-days

**Dependencies**: Enhancement 3 (cross-references) enriches the narratives further

---

### Enhancement 5: Curation and Recommendation Engine

**Name**: Intelligent Selection and Exhibit Curation

**Description**: Enable the system to select, rank, and recommend items from a result set based on scholarly significance, visual interest, narrative value, or representativeness. Supports exhibit planning, teaching packet creation, and "best of" queries.

**Questions improved**: Q20 (directly), Q4, Q11, Q14, Q15 (indirectly via representative sampling)

**Impact**: Q20 goes from POOR (score 1) to GOOD (score 12+). Other questions gain partial benefit from representative sampling of large sets. Estimated score improvement: +15 points.

**Priority**: MEDIUM

**Implementation Tasks**:

1. **Build significance scoring model** (1.5d)
   - New module: `scripts/chat/curator.py`
   - Multi-factor scoring: (a) date rarity (pre-1500 = high), (b) enrichment data richness, (c) provenance indicators, (d) place rarity, (e) first edition markers, (f) illustration indicators
   - Function: `score_candidates(candidates, db_path) -> List[ScoredCandidate]`
   - ScoredCandidate: `(record_id, significance_score, reasons: List[str])`

2. **Add curation intent to exploration agent** (0.5d)
   - Modify `scripts/chat/exploration_agent.py`
   - Handle `RECOMMENDATION` intent type (already stubbed but not implemented)
   - Parse user request: "select 10 for exhibit", "most important items", "representative sample"

3. **Implement diverse selection algorithm** (1d)
   - In `scripts/chat/curator.py`
   - Select top-N items maximizing both significance and diversity
   - Diversity dimensions: date spread, place spread, language spread, agent spread
   - Greedy selection: pick highest-scoring, then highest-scoring that adds new dimension value

4. **Format curated selection as exhibit narrative** (0.5d)
   - In `scripts/chat/formatter.py`
   - "Exhibit: The Story of Hebrew Printing"
   - "Item 1 (1475, Rome): [Title] -- [significance note]"
   - Each item with a one-sentence curatorial note explaining its inclusion

**Estimated effort**: 3.5 developer-days

**Dependencies**: Enhancement 4 (significance scoring is shared), Enhancement 2 (analytical routing)

---

## Section 7: Score Summary

### Scores by Question

| # | Question | Accuracy | Richness | Cross-Ref | Narrative | Pedagogical | Total (/25) | Grade |
|---|----------|----------|----------|-----------|-----------|-------------|-------------|-------|
| Q1 | Bragadin Venice | 4 | 2 | 1 | 3 | 2 | 12 | FAIR |
| Q2 | Amsterdam Hebrew | 4 | 3 | 2 | 3 | 3 | 15 | FAIR |
| Q3 | Aldine Press | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| Q4 | Incunabula | 4 | 3 | 1 | 3 | 3 | 14 | FAIR |
| Q5 | Constantinople | 4 | 2 | 1 | 3 | 2 | 12 | FAIR |
| Q6 | Buxtorf | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| Q7 | Mendelssohn | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| Q8 | Maimonides | 2 | 2 | 1 | 2 | 2 | 9 | POOR |
| Q9 | Josephus | 4 | 3 | 1 | 3 | 3 | 14 | FAIR |
| Q10 | Jewish philosophy | 4 | 3 | 1 | 3 | 3 | 14 | FAIR |
| Q11 | Napoleon era | 3 | 2 | 0 | 2 | 2 | 9 | POOR |
| Q12 | Ethiopia | 2 | 2 | 1 | 2 | 2 | 9 | POOR |
| Q13 | Book collecting | 4 | 2 | 1 | 3 | 2 | 12 | FAIR |
| Q14 | Chronological shape | 1 | 0 | 0 | 0 | 0 | 1 | FAIL |
| Q15 | Printing centers | 1 | 0 | 0 | 0 | 0 | 1 | FAIL |
| Q16 | Biblical commentary | 3 | 2 | 1 | 3 | 2 | 11 | FAIR |
| Q17 | Hebrew grammar | 4 | 3 | 2 | 3 | 3 | 15 | FAIR |
| Q18 | Talmud | 4 | 2 | 1 | 3 | 2 | 12 | FAIR |
| Q19 | Joseph Karo | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| Q20 | Curated exhibit | 1 | 0 | 0 | 0 | 0 | 1 | FAIL |

### Dimension Averages

| Dimension | Average (/5) | Percentage |
|-----------|-------------|------------|
| Accuracy | 2.45 | 49% |
| Richness | 1.45 | 29% |
| Cross-referencing | 0.55 | 11% |
| Narrative Quality | 1.60 | 32% |
| Pedagogical Value | 1.30 | 26% |
| **Overall Average** | **7.55 /25** | **30.2%** |

### Grade Distribution

| Grade | Range | Count | Questions |
|-------|-------|-------|-----------|
| GOOD (18-25) | 72-100% | 0 | -- |
| FAIR (11-17) | 44-68% | 10 | Q1, Q2, Q4, Q5, Q9, Q10, Q13, Q16, Q17, Q18 |
| POOR (6-10) | 24-40% | 3 | Q8, Q11, Q12 |
| FAIL (0-5) | 0-20% | 7 | Q3, Q6, Q7, Q14, Q15, Q19, Q20 |

### Projected Scores After Enhancements

| Enhancement | Questions | Score Change | New Average |
|-------------|-----------|-------------|-------------|
| Baseline | -- | -- | 7.55 |
| +E1 (Agent Aliases) | Q3, Q6, Q7, Q8, Q12, Q19 | +70 | 11.05 |
| +E2 (Analytical Routing) | Q14, Q15, Q20 | +33 | 12.70 |
| +E3 (Cross-Reference) | Q1-Q5, Q9, Q10, Q13, Q17 | +24 | 13.90 |
| +E4 (Scholarly Narrative) | Q1, Q2, Q4, Q5, Q11, Q16, Q18 | +21 | 14.95 |
| +E5 (Curation) | Q4, Q11, Q14, Q15, Q20 | +15 | 15.70 |
| **All Enhancements** | -- | **+163** | **15.70 (/25)** |

**Projected improvement**: Overall average from 7.55/25 (30%) to 15.70/25 (63%), a doubling of evaluation scores. The number of FAIL questions drops from 7 to 0. Implementation effort: approximately 18.5 developer-days total across all five enhancements.

### Implementation Priority Sequence

1. **E1 (Agent Aliases)** -- 3.5d, CRITICAL. Fixes 4 total failures immediately.
2. **E2 (Analytical Routing)** -- 3d, CRITICAL. Unlocks 3 currently impossible query types.
3. **E3 (Cross-Reference)** -- 4.5d, HIGH. Broadens scholarly value of all results.
4. **E4 (Scholarly Narrative)** -- 4d, HIGH. Deepens pedagogical utility.
5. **E5 (Curation)** -- 3.5d, MEDIUM. Enables new use case (exhibit planning).

E1 and E2 together (6.5d) would move the system from 30% to 51% -- the highest ROI investment.
