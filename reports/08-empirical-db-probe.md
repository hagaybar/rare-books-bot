# Report 08: Empirical Database Probe

**Date**: 2026-03-23
**Database**: `data/index/bibliographic.db`
**Method**: Direct SQL queries against production SQLite database

---

## 1. Table Row Counts

| Table | Row Count |
|-------|-----------|
| records | 2,796 |
| imprints | 2,773 |
| titles | 4,791 |
| subjects | 5,415 |
| agents | 4,366 |
| languages | 3,197 |
| notes | 8,037 |
| publisher_authorities | 227 |
| publisher_variants | 265 |
| authority_enrichment | 0 |

**Key observations**:
- 38 records have no imprints (manuscripts from the Faitlovitch collection)
- 0 records have no titles (100% title coverage)
- 15 records have multiple imprints (2 imprints each)
- `authority_enrichment` table exists but is empty (unused)

---

## 2. Imprints Coverage Rates

| Field | Non-Null Count | Coverage |
|-------|---------------|----------|
| date_start | 2,704 | 97.5% |
| place_norm | 2,754 | 99.3% |
| publisher_norm | 2,740 | 98.8% |

**Raw field null rates** (out of 2,773 imprints):

| Raw Field | Null Count | Null Rate |
|-----------|-----------|-----------|
| date_raw | 8 | 0.3% |
| place_raw | 19 | 0.7% |
| publisher_raw | 33 | 1.2% |
| manufacturer_raw | 2,744 | 98.9% |

**Notes**: `manufacturer_raw` is almost entirely null -- only 29 records have manufacturer data. This is expected since MARC 264$b with second indicator = 3 (manufacturer) is rarely used.

Only 1 imprint has ALL normalized fields null (`mms_id = 990009449560204146`, `date_raw = "198-"`, empty place and publisher).

---

## 3. Confidence Distributions

### Date Confidence

| Bucket | Count | % |
|--------|-------|---|
| 0-0.5 | 69 | 2.5% |
| 0.8-0.95 | 1,306 | 47.1% |
| 0.95-1.0 | 1,398 | 50.4% |

**No date records in the null or 0.5-0.8 buckets.** All dated records have either low confidence (<0.5, likely unparsed) or high confidence (>=0.8).

### Place Confidence

| Bucket | Count | % |
|--------|-------|---|
| 0-0.5 | 19 | 0.7% |
| 0.95-1.0 | 2,754 | 99.3% |

**Binary distribution**: Places are either unresolvable (19 records) or high-confidence alias-mapped (2,754 records). No records in the 0.5-0.95 range.

### Publisher Confidence

| Bucket | Count | % |
|--------|-------|---|
| 0-0.5 | 33 | 1.2% |
| 0.95-1.0 | 2,740 | 98.8% |

**Same binary pattern as places**: Publishers are either unresolvable (33) or high-confidence (2,740).

---

## 4. Method Distributions

### Date Methods

| Method | Count | % |
|--------|-------|---|
| year_exact | 1,279 | 46.1% |
| year_embedded | 364 | 13.1% |
| hebrew_gematria_bracketed | 336 | 12.1% |
| hebrew_gematria | 219 | 7.9% |
| year_bracketed_gregorian | 167 | 6.0% |
| year_bracketed | 119 | 4.3% |
| year_circa_pm5 | 79 | 2.8% |
| year_range | 78 | 2.8% |
| unparsed | 61 | 2.2% |
| year_embedded_range | 41 | 1.5% |
| year_bracketed_range | 22 | 0.8% |
| missing | 8 | 0.3% |

**Notable**: 20% of dates are Hebrew gematria (555 records combined). This is a distinctive feature of this collection.

### Place Methods

| Method | Count | % |
|--------|-------|---|
| place_alias_map | 2,754 | 99.3% |
| missing | 19 | 0.7% |

Only 2 methods exist -- alias map lookup or missing. There is no `base_clean` method in production.

---

## 5. Top 20 Values

### Top 20 Places of Publication

| Place | Count |
|-------|-------|
| paris | 356 |
| london | 230 |
| amsterdam | 196 |
| venice | 164 |
| berlin | 123 |
| leipzig | 111 |
| jerusalem | 109 |
| leiden | 53 |
| frankfurt | 48 |
| basel | 45 |
| tel aviv | 43 |
| [sine loco] | 41 |
| vienna | 41 |
| hamburg | 36 |
| frankfurt am main | 30 |
| munich | 27 |
| rome | 27 |
| halle | 26 |
| mantua | 24 |
| new york | 23 |

**Observation**: "frankfurt" (48) and "frankfurt am main" (30) exist as separate normalized values -- potential deduplication target. "[sine loco]" (41) represents records where place of publication is unknown.

### Top 20 Publishers

| Publisher | Count |
|-----------|-------|
| [publisher unknown] | 115 |
| [sine nomine] | 100 |
| insel verlag | 16 |
| verdiere, paris | 16 |
| bragadin press, venice | 12 |
| a.a.m. stols | 10 |
| house of elzevir | 9 |
| ferdinand dummler, berlin | 8 |
| francke orphanage press, halle | 8 |
| aldine press, venice | 7 |
| vendramin press, venice | 7 |
| j. murray | 6 |
| committee of the palestine exploration fund | 5 |
| daniel bomberg, venice | 5 |
| h. colburn | 5 |
| printed for t. egerton | 5 |
| university press | 5 |
| בדפוס ובבית שלמה בן יוסף פרופס | 5 |
| ambrosius froben, basel | 4 |
| blaeu, amsterdam | 4 |

**Key findings**:
- 215 imprints (7.9%) have unknown publishers ("[publisher unknown]" + "[sine nomine]")
- The long tail is very long -- publishers are highly fragmented
- 553 publisher_norm values contain only non-Latin characters (Hebrew/Yiddish) -- 20.2% of all publisher records. These have not been normalized to English canonical forms.

---

## 6. Date Range

| Metric | Value |
|--------|-------|
| Earliest date_start | 1244 |
| Latest date_end | 2025 |

The collection spans ~780 years, from 13th-century manuscripts to modern publications.

### Distribution by Century

| Century | Count |
|---------|-------|
| 1200s | 1 |
| 1300s | 1 |
| 1400s (incunabula) | 11 |
| 1500s | 212 |
| 1600s | 351 |
| 1700s | 874 |
| 1800s | 524 |
| 1900s | 728 |
| 2000s | 2 |

**Peak**: The 1700s (18th century) is the most represented period with 874 records (32.3%). The collection is heavily concentrated in the 1500-1900 range (2,689 records, 99.4%).

---

## 7. Subjects Distribution (Top 20)

| Subject | Count |
|---------|-------|
| Manuscripts, Ethiopic. | 39 |
| Hiddushim (Jewish law) | 30 |
| Hebrew language -- Grammar -- Early works to 1800. | 27 |
| Book collecting | 24 |
| Bible. -- Pentateuch -- Commentaries. | 20 |
| Ethiopic literature -- Jewish authors | 20 |
| Jews, Ethiopian | 20 |
| Napoleon I, Emperor of the French, 1769-1821. | 20 |
| Rare books -- Bibliography | 18 |
| Bibliomania | 17 |
| Hebrew language -- Grammar | 17 |
| Talmud Bavli. | 17 |
| Incunabula -- Facsimiles | 16 |
| Jewish ethics -- 14th century | 15 |
| Peninsular War, 1807-1814 | 15 |
| Printing -- Specimens | 15 |
| Jewish philosophy -- Middle Ages, 500-1500. | 14 |
| Apocrypha. -- Ethiopic -- Versions. | 12 |
| Ethiopian literature | 12 |
| Jews -- History -- Sources. | 12 |

The collection has strong thematic clusters: Judaica (Hebrew grammar, Jewish law, Talmud), Ethiopic manuscripts, bibliography/book collecting, and Napoleonic era.

---

## 8. Agents Distribution

### By Type

| Agent Type | Count |
|-----------|-------|
| personal | 4,082 |
| corporate | 277 |
| meeting | 7 |

### By Role

| Role | Count |
|------|-------|
| author | 2,164 |
| other | 1,924 |
| creator | 75 |
| collector | 40 |
| printer | 38 |
| editor | 36 |
| translator | 36 |
| illustrator | 16 |
| artist | 14 |
| former_owner | 6 |
| compiler | 5 |
| writer_of_preface | 4 |
| dedicatee | 3 |
| engraver | 2 |
| annotator | 1 |
| book_designer | 1 |
| publisher | 1 |

**Issue**: "other" role has 1,924 entries (44.1%) -- nearly half of all agent roles are uncategorized. This represents a significant normalization gap.

### Agent Normalization

- **Method**: ALL 4,366 agents use `base_clean` method only (no alias map)
- **Confidence**: ALL agents have confidence in the 0.8-0.95 range
- No agents have been upgraded to alias_map normalization

### Top 20 Agents

| Agent | Count |
|-------|-------|
| faitlovitch, jacques | 40 |
| wurmbrand, max | 38 |
| faitlovitch collection. ancient ethiopic manuscripts collection | 30 |
| josephus, flavius | 30 |
| buxtorf, johann | 26 |
| schwerin, ludwig | 17 |
| buchon, j. a. c | 16 |
| משה בן מימון (Maimonides) | 15 |
| schwencke, johan | 13 |
| אברבנאל, יצחק בן יהודה (Abarbanel) | 13 |
| קארו, יוסף בן אפרים (Karo) | 13 |
| ludolf, hiob | 11 |
| mendelssohn, moses | 11 |
| cicero, marcus tullius | 10 |
| אבן גבירול, שלמה בן יהודה (Ibn Gabirol) | 10 |
| אסף פיטלוביץ'. אוסף המסמכים | 10 |
| amzalak, moses bensabat | 9 |
| גרשון, יצחק בן מרדכי | 9 |
| קמחי, דוד בן יוסף (Kimhi) | 9 |
| clausewitz, carl von | 8 |

---

## 9. Publisher Authorities

| Metric | Value |
|--------|-------|
| Total authorities | 227 |
| Total variants | 265 |

### By Type

| Type | Count |
|------|-------|
| unresearched | 202 |
| printing_house | 18 |
| bibliophile_society | 3 |
| unknown_marker | 2 |
| modern_publisher | 1 |
| private_press | 1 |

**89% of publisher authorities are "unresearched"** -- they have been created as stubs but not yet classified or enriched.

---

## 10. Languages

| Code | Count | Language |
|------|-------|----------|
| heb | 806 | Hebrew |
| lat | 505 | Latin |
| fre | 500 | French |
| ger | 496 | German |
| eng | 366 | English |
| ita | 103 | Italian |
| dut | 70 | Dutch |
| gez | 58 | Ge'ez (Ethiopic) |
| yid | 55 | Yiddish |
| ara | 42 | Arabic |
| spa | 38 | Spanish |
| gre | 21 | Greek (modern) |
| arc | 18 | Aramaic |
| grc | 18 | Greek (ancient) |
| por | 14 | Portuguese |

Hebrew is the dominant language (25.2%), followed by Latin (15.8%), French (15.6%), and German (15.5%).

---

## 11. Notes Distribution

| Tag | Count | Description |
|-----|-------|-------------|
| 500 | 4,316 | General notes |
| 590 | 2,813 | Local notes |
| 505 | 585 | Contents notes |
| 504 | 146 | Bibliography notes |
| 501 | 95 | "With" notes |
| 520 | 80 | Summary notes |
| 502 | 2 | Dissertation notes |

---

## 12. Titles Distribution

| Titles per Record | Record Count |
|-------------------|-------------|
| 1 | 1,584 |
| 2 | 758 |
| 3 | 272 |
| 4 | 104 |
| 5 | 42 |
| 6 | 19 |
| 7 | 8 |
| 8 | 3 |
| 9 | 5 |
| 10 | 1 |

56.7% of records have a single title; 43.3% have multiple titles (variant titles, parallel titles, etc.).

---

## 13. Sample Records

### Record 1: `990012160290204146`
- **Title**: Constitutiones et decreta Provincialis Synodi Mediol. sextae...
- **Date**: 1583 (exact, confidence 0.99)
- **Place**: Mediolani → milan (alias map, confidence 0.95)
- **Publisher**: Apud M. Tinum → apud m. tinum (confidence 0.95)

### Record 2: `990012162110204146`
- **Title**: הדור (Hebrew periodical from Krakow)
- **Date**: תרס"א 1900-תרס"ה 1904 → 1900-1904 (embedded range, confidence 0.9)
- **Place**: קראקא → krakow (alias map, confidence 0.95)
- **Publisher**: אחיאסף → אחיאסף (Hebrew, not transliterated, confidence 0.95)

### Record 3: `990012162750204146`
- **Title**: קורטוב מדינה (plan for settlement work in Eretz Israel)
- **Date**: תשל"ט → 1979 (Hebrew gematria, confidence 0.9)
- **Place**: תל-אביב → tel aviv (alias map, confidence 0.95)
- **Publisher**: י' רובינזון → י' רובינזון (Hebrew, not transliterated, confidence 0.95)

---

## 14. Data Anomalies Summary

| Anomaly | Count | Notes |
|---------|-------|-------|
| Records with no imprints | 38 | All are Faitlovitch Ethiopic manuscripts |
| Records with no titles | 0 | 100% title coverage |
| Imprints with all-null norms | 1 | mms_id 990009449560204146, date_raw="198-" |
| "frankfurt" vs "frankfurt am main" | 78 | Potential deduplication (48 + 30) |
| Non-Latin publisher_norm values | 553 | 20.2% of publishers are in Hebrew script |
| "other" agent role | 1,924 | 44.1% of agents have uncategorized roles |
| No agent alias map normalization | 4,366 | 100% of agents use base_clean only |
| Unresearched publisher authorities | 202 | 89% of authorities are stubs |
| authority_enrichment table empty | 0 rows | Table exists but unused |
| Unparsed dates | 61 | 2.2% of date records |

---

## 15. Key Findings

1. **High coverage overall**: Date (97.5%), place (99.3%), and publisher (98.8%) normalization coverage is excellent.

2. **Binary confidence model**: Place and publisher confidences show a binary distribution (either <0.5 or >=0.95) with no middle ground. Date confidence has a split between 0.8-0.95 (gematria, embedded) and 0.95-1.0 (exact years).

3. **Hebrew character gap in publishers**: 553 publisher_norm values (20.2%) remain in Hebrew script without transliteration or mapping to canonical English forms. These technically have 0.95 confidence but are not truly "normalized" for cross-lingual querying.

4. **Agent normalization gap**: No agents have been normalized beyond base_clean. No alias map exists for agent names. 44.1% of agent roles are classified as "other".

5. **Manuscript records lack imprints**: 38 Faitlovitch Ethiopic manuscript records have no publication data, which is expected for manuscript materials.

6. **Place deduplication needed**: "frankfurt" (48) and "frankfurt am main" (30) should be consolidated.

7. **Strong Hebraica/Judaica signal**: Hebrew is the most common language (25.2%), 20% of dates use Hebrew gematria, and top subjects are Jewish law, Hebrew grammar, and Talmud.

8. **Publisher long tail**: After the 215 "unknown" markers, publishers are extremely fragmented with most appearing only 1-5 times.
