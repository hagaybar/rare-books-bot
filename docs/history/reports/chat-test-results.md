# Chat Bot Test Results

**Date**: 2026-03-24 12:40
**Database**: data/index/bibliographic.db (13924KB)
**Queries**: 10

## Summary

- PASS: 8
- FAIL: 0
- PARTIAL: 2
- ERROR: 0
- Narrative generated: 8 of 10

## Results

| # | Query | Count | Time | Narrative | Assessment | Explanation | Improvements |
|---|-------|-------|------|-----------|------------|-------------|--------------|
| 1 | Hebrew books printed in Venice in the 16th century | 44 | 3381.5ms | Yes | PASS | Filters: FilterField.LANGUAGE FilterOp.EQUALS heb-, FilterField.IMPRINT_PLACE Fi... | Narrative enrichment working well. |
| 2 | books about Jewish law | 77 | 2973.8ms | Yes | PASS | Filters: FilterField.SUBJECT FilterOp.CONTAINS Jewish law- | Narrative enrichment working well. |
| 3 | Latin texts published in Paris | 29 | 2594.1ms | Yes | PASS | Filters: FilterField.LANGUAGE FilterOp.EQUALS lat-, FilterField.IMPRINT_PLACE Fi... | Narrative enrichment working well. |
| 4 | books on book collecting | 26 | 1671.5ms | Yes | PASS | Filters: FilterField.SUBJECT FilterOp.CONTAINS Book collecting- | Narrative enrichment working well. |
| 5 | German books from the 18th century | 319 | 3877.3ms | No | PASS | Filters: FilterField.COUNTRY FilterOp.EQUALS germany-, FilterField.YEAR FilterOp... |  |
| 6 | books by Josephus | 30 | 4.7ms | Yes | PASS | Filters: FilterField.AGENT_NORM FilterOp.CONTAINS josephus- | Narrative enrichment working well. |
| 7 | books printed by Elsevier | 1 | 2297.4ms | Yes | PASS | Filters: FilterField.PUBLISHER FilterOp.CONTAINS elsevier- | Narrative enrichment working well. |
| 8 | books about astronomy | 4 | 2311.9ms | Yes | PASS | Filters: FilterField.SUBJECT FilterOp.CONTAINS Astronomy- | Narrative enrichment working well. |
| 9 | Tell me about Italian print houses | 7 | 2849.4ms | Yes | PARTIAL | Filters: FilterField.COUNTRY FilterOp.EQUALS italy-, FilterField.AGENT_ROLE Filt... | Results returned but the query asks for analysis/narrative, not a list. Need Phase 2 exploration or ... |
| 10 | Who is the most published author in this collec... | 2796 | 2070.4ms | No | PARTIAL | Filters: none | Results returned but the query asks for analysis/narrative, not a list. Need Phase 2 exploration or ... |

## Detailed Results

### Query 1: "Hebrew books printed in Venice in the 16th century"
- **Category**: Should work
- **Why**: Multi-filter (language+place+date). Venice=164, Hebrew=806.
- **Result Count**: 44
- **Execution Time**: 3381.5ms
- **Assessment**: PASS
- **Answer**: Found 44 results. First: ספר ידי משה : והוא פירוש חמש מגלות / אשר חבר ... משה אלמושנינו; משפטי שמואל / שמואל לבית קלעי; ספר הכוזרי / יסדו ... יצחק הסנגורי ... ; חברו בלשון ערבי ... ר' יהודה הלוי הספרדי : והעתיק אותו ... ...
- **Explanation**: Filters: FilterField.LANGUAGE FilterOp.EQUALS heb-, FilterField.IMPRINT_PLACE FilterOp.EQUALS venice-, FilterField.YEAR FilterOp.RANGE 1501-1600
- **Narrative**: Yes
  ```
  **Notable figures in these results**:
  - Moshe ben Maimon (1135–1204), Egypt rabbi, appears in 4 records in this set. [Wikidata Q127398]
  - Gershon, Isaac (1550–1631), appears in 4 records in this set. [Wikidata Q118916451]
  - Joseph ben Ephraim Karo (1488–1575), Ottoman Empire rabbi, appears in 4 reco...
  ```
- **Improvements**: Narrative enrichment working well.

### Query 2: "books about Jewish law"
- **Category**: Should work
- **Why**: Subject search. 'Hiddushim (Jewish law)' has 30 records.
- **Result Count**: 77
- **Execution Time**: 2973.8ms
- **Assessment**: PASS
- **Answer**: Found 77 results. First: ספר שני לוחות הברית : ... חבור על שתי התורות, בכתב ובפה ... / מהגבור ... ישעיה במהור"ר אברהם הלוי ממ...; ספר זבח שמואל : על דיני והלכות שחיטות ובדיקות מהגאון מהרי"ו / והוא תוספת הגהות ... דברי חכמים ... שק...; כלי מחזיק ברכה / חיברו ישראל ב"ר משה נאג'ארה ; נדפס בויניציאה בשנת שע"ח ועתה יצא לאור על-פי שלושה עו...
- **Explanation**: Filters: FilterField.SUBJECT FilterOp.CONTAINS Jewish law-
- **Narrative**: Yes
  ```
  **Notable figures in these results**:
  - Shlomo ben Aderet (1235–1310), Crown of Aragon rabbi, appears in 4 records in this set. [Wikidata Q982170]
  - Joseph ben Ephraim Karo (1488–1575), Ottoman Empire rabbi, appears in 4 records in this set. [Wikidata Q467148]
  - Solomon Luria (1510–1573), rabbi, app...
  ```
- **Improvements**: Narrative enrichment working well.

### Query 3: "Latin texts published in Paris"
- **Category**: Should work
- **Why**: Language+place. Paris=356, Latin=505.
- **Result Count**: 29
- **Execution Time**: 2594.1ms
- **Assessment**: PASS
- **Answer**: Found 29 results. First: Le Triumphe de Cesar; [Alberti Dureri ... versus E Germanica lingua in Latinam ... adeo exacte Quator his Suarum Instituti...; De l'esprit / [Helvetius]
- **Explanation**: Filters: FilterField.LANGUAGE FilterOp.EQUALS lat-, FilterField.IMPRINT_PLACE FilterOp.EQUALS paris-
- **Narrative**: Yes
  ```
  **Notable figures in these results**:
  - Philo of Alexandria (-14–50), Ancient Rome philosopher, appears in 2 records in this set. [Wikidata Q189597]
  - Fédéric Morel (1552–1630), France printer, appears in 2 records in this set. [Wikidata Q1479401]
  - Robert Estienne (1503–1559), Republic of Geneva pr...
  ```
- **Improvements**: Narrative enrichment working well.

### Query 4: "books on book collecting"
- **Category**: Should work
- **Why**: Niche subject. 'Book collecting' has 24 records.
- **Result Count**: 26
- **Execution Time**: 1671.5ms
- **Assessment**: PASS
- **Answer**: Found 26 results. First: Philologicarum epistolarum centuria una... : Richardi de Buri Episcopi Dunelmensis Philobiblion & Be...; The book-hunter, etc. / by John Hill Burton; Christiani Liberii ... Bibliophilia : sive, de Scribendis, Legendis & Aestimandis libris ...
- **Explanation**: Filters: FilterField.SUBJECT FilterOp.CONTAINS Book collecting-
- **Narrative**: Yes
  ```
  **Notable figures in these results**:
  - Richard de Bury (1287–1345), Kingdom of England writer, appears in 5 records in this set. [Wikidata Q268453]
  - Paul Lacroix (1806–1884), France historian, appears in 2 records in this set. [Wikidata Q1607626]
  - Fedor von Zobeltitz (1857–1934), Germany writer, ...
  ```
- **Improvements**: Narrative enrichment working well.

### Query 5: "German books from the 18th century"
- **Category**: Should work
- **Why**: Country+date. Germany=700, 1700s=874.
- **Result Count**: 319
- **Execution Time**: 3877.3ms
- **Assessment**: PASS
- **Answer**: Found 319 results. First: Die Verschworung des Fiesko zu Genua : ein Republikanisches Trauerspiel / von Friederich Schiller; Phadon, oder, uber die Unsterblichkeit der Seele, in Drey Gesprachen / von Moses Mendelssohn; Versuch einer neuen Logik oder Theorie des Denkens : nebst angehangten Briefen des Philaletes An Aen...
- **Explanation**: Filters: FilterField.COUNTRY FilterOp.EQUALS germany-, FilterField.YEAR FilterOp.RANGE 1701-1800

### Query 6: "books by Josephus"
- **Category**: Should work but might not
- **Why**: Already failed in live test. 21 records exist for josephus, flavius.
- **Result Count**: 30
- **Execution Time**: 4.7ms
- **Assessment**: PASS
- **Answer**: Found 30 results. First: Flavii Josephi quae reperiri potuerunt, opera omnia Graece et Latine : cum notis & nova versione Joa...; Flavij Josephe Historien und Bucher ... / Alles auss dem Griechischen exemplar von Newm Verteuscht u...; Flauij Josephi ... alle Bucher. Namlich Zwentzig von den alten Geschichten der Juden : Syben vom jud...
- **Explanation**: Filters: FilterField.AGENT_NORM FilterOp.CONTAINS josephus-
- **Narrative**: Yes
  ```
  **Notable figures in these results**:
  - Josephus (37–100), Ancient Rome historian, appears in 21 records in this set. [Wikidata Q134461]
  - Lautenbach, Conrad (1534–1595), philosopher, appears in 4 records in this set. [Wikidata Q1126870]
  - Siwart Haverkamp (1684–1742), Netherlands historian, appears...
  ```
- **Improvements**: Narrative enrichment working well.

### Query 7: "books printed by Elsevier"
- **Category**: Should work but might not
- **Why**: Publisher variant gap. 'house of elzevir' won't match 'elsevier'.
- **Result Count**: 1
- **Execution Time**: 2297.4ms
- **Assessment**: PASS
- **Answer**: Found 1 results. First: S. Johannis Apostoli et Evangelistæ Epistolæ Catholicæ tres : Arabicæ & Æthiopicæ / omnes ad verbum ...
- **Explanation**: Filters: FilterField.PUBLISHER FilterOp.CONTAINS elsevier-
- **Narrative**: Yes
  ```
  **Notable figures in these results**:
  - Johann Georg Nissel (1621–1662), printer. [Wikidata Q55125772]
  - Théodore Peeters (1567–1640), Germany theologian. [Wikidata Q3526478]
  
  This set includes works by a printer and a theologian.
  ```
- **Improvements**: Narrative enrichment working well.

### Query 8: "books about astronomy"
- **Category**: Should work but might not
- **Why**: Subject may not exist in LCSH. Tests subject retry/broadening.
- **Result Count**: 4
- **Execution Time**: 2311.9ms
- **Assessment**: PASS
- **Answer**: Found 4 results. First: אילם : ... שאלות ... שאל זרח בר נתן ... מהרב ... יוסף שלמה דילמידגו ... איש קנדיאה. ועוד נתוספו כתבי...; ספר התכונה : [לדעת ... התקופו' והמולדו' לקבוע את השנה ומועדיה עפ"י מהלך השמש] / אשר חיבר ... מוהרח"ו...; ספר נחמד ונעים : ... חבור נאה ... על כללות חכמות התכונה וקדוש החודש ומדידות הכוכבים ... / חברו ... ד...
- **Explanation**: Filters: FilterField.SUBJECT FilterOp.CONTAINS Astronomy-
- **Narrative**: Yes
  ```
  **Notable figures in these results**:
  - Joseph Solomon Delmedigo (1591–1655), rabbi. [Wikidata Q969675]
  - David Gans (1541–1613), theologian. [Wikidata Q1174512]
  - Phinehas Elijah Hurwitz (1765–1821), rabbi. [Wikidata Q18017237]
  - Hayyim ben Joseph Vital (1542–1620), Ottoman Empire rabbi. [Wikidata ...
  ```
- **Improvements**: Narrative enrichment working well.

### Query 9: "Tell me about Italian print houses"
- **Category**: Known edge case
- **Why**: Analytical/narrative query, not a specific book search.
- **Result Count**: 7
- **Execution Time**: 2849.4ms
- **Assessment**: PARTIAL
- **Answer**: Found 7 results. First: Provvisioni, gride, ordini, e decreti da osservarsi negli stati di Sua Altezza Serenissima; Septem linguarum Calepinus : Hoc est Lexicon latinum, variarum linguarum interpretatione adjecta in ...; De inscriptione quadam Ægyptiaca Taurini inventa : et characteribus Ægyptiis olim et sinis communibu...
- **Explanation**: Filters: FilterField.COUNTRY FilterOp.EQUALS italy-, FilterField.AGENT_ROLE FilterOp.EQUALS printer-
- **Narrative**: Yes
  ```
  **Notable figures in these results**:
  - Francesco III d'Este, Duke of Modena (1698–1780), aristocrat. [Wikidata Q506514]
  - Ambrogio Calepino (1435–1510), linguist. [Wikidata Q458742]
  - Jacopo Facciolati (1682–1769), Republic of Venice linguist. [Wikidata Q3157640]
  - Egidio Forcellini (1688–1768), wr...
  ```
- **Improvements**: Results returned but the query asks for analysis/narrative, not a list. Need Phase 2 exploration or narrative agent to provide meaningful answer.

### Query 10: "Who is the most published author in this collection?"
- **Category**: Known edge case
- **Why**: Aggregation question. No filter — wants metadata analysis.
- **Result Count**: 2796
- **Execution Time**: 2070.4ms
- **Assessment**: PARTIAL
- **Answer**: Found 2796 results. First: Die Verschworung des Fiesko zu Genua : ein Republikanisches Trauerspiel / von Friederich Schiller; Flaques de sel / Claude Quillateau, ill. de Gil Torro; Il Patito di Roma / di Giuseppe Valentini
- **Explanation**: Filters: none
- **Improvements**: Results returned but the query asks for analysis/narrative, not a list. Need Phase 2 exploration or narrative agent to provide meaningful answer.
