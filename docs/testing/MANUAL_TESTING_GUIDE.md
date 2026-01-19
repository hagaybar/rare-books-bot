# Manual Testing Guide - Rare Books Chatbot

This document provides structured manual test scenarios for the rare books discovery chatbot. Each test includes the query to execute, inspection points at multiple levels, and criteria for success.

---

## Prerequisites

### Start the Server
```bash
export OPENAI_API_KEY="sk-..."
uvicorn app.api.main:app --reload
```

### Verify Health
```bash
curl http://localhost:8000/health
```
Expected: `{"status": "healthy", "database_connected": true, "session_store_ok": true}`

### Tools You'll Need
- **curl** or **httpie** for HTTP requests
- **wscat** for WebSocket testing: `npm install -g wscat`
- **sqlite3** for database inspection: `sqlite3 data/index/bibliographic.db`
- **jq** for JSON parsing (optional but helpful)

---

## Test Categories

| Category | Purpose |
|----------|---------|
| [A. Basic Query Execution](#a-basic-query-execution) | Verify core query → result pipeline |
| [B. Filter Type Coverage](#b-filter-type-coverage) | Test all supported filter types |
| [C. Ambiguity & Clarification](#c-ambiguity--clarification) | Test clarification prompts |
| [D. Session Management](#d-session-management) | Multi-turn conversations |
| [E. Evidence & Traceability](#e-evidence--traceability) | MARC field citation accuracy |
| [F. Edge Cases & Error Handling](#f-edge-cases--error-handling) | Robustness testing |
| [G. WebSocket Streaming](#g-websocket-streaming) | Real-time response testing |

---

## A. Basic Query Execution

### A1. Simple Publisher + Date Query

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books published by Oxford between 1500 and 1599"}' | jq .
```

**Inspect:**

1. **Response Structure**
   - `success` should be `true`
   - `response.session_id` should be a UUID
   - `response.candidate_set.candidates` should be an array
   - `response.followup_questions` should contain suggestions

2. **Query Plan (in logs or cache)**
   ```bash
   # Check query plan cache
   tail -1 data/query_plan_cache.jsonl | jq .
   ```
   Expected filters:
   - `field: "publisher"`, `value: "oxford"`, `operation: "EQUALS"` or `"CONTAINS"`
   - `field: "year"`, `operation: "RANGE"`, `value: {start: 1500, end: 1599}`

3. **Database Verification**
   ```sql
   -- In sqlite3 data/index/bibliographic.db
   SELECT DISTINCT r.mms_id, i.publisher_raw, i.publisher_norm, i.date_start, i.date_end
   FROM records r
   JOIN imprints i ON r.mms_id = i.mms_id
   WHERE i.publisher_norm LIKE '%oxford%'
     AND i.date_start >= 1500 AND i.date_end <= 1599
   LIMIT 10;
   ```

4. **Evidence Check**
   Each candidate should have evidence entries like:
   ```json
   {
     "field": "publisher_norm",
     "value": "oxford",
     "source": "marc:264$b[0]",
     "confidence": 0.95
   }
   ```

**Good Result:**
- Returns matching records with publisher containing "oxford"
- Date range correctly interpreted as 1500-1599
- Evidence cites MARC 264$b for publisher, 264$c for date
- Response formatted as natural language with record count

---

### A2. Place + Century Query

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books printed in Paris in the 17th century"}' | jq .
```

**Inspect:**

1. **Century Conversion**
   - Query plan should have date range 1600-1699 (17th century)
   - NOT 1700-1799

2. **Place Normalization**
   ```sql
   -- Check place normalization
   SELECT DISTINCT place_raw, place_norm
   FROM imprints
   WHERE place_norm LIKE '%paris%'
   LIMIT 5;
   ```

3. **SQL Join Strategy**
   The query should join `records` with `imprints` table

**Good Result:**
- Century correctly parsed to 1600-1699
- Place matched against `place_norm` column
- Results include Paris publications from 17th century
- Evidence shows place confidence (typically 0.80-0.95)

---

### A3. Subject + Language Query

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Latin books on astronomy"}' | jq .
```

**Inspect:**

1. **Language Code Conversion**
   - "Latin" should be converted to ISO 639-2 code "lat"
   ```sql
   SELECT DISTINCT language_code FROM languages WHERE language_code = 'lat';
   ```

2. **Subject Matching**
   ```sql
   SELECT s.heading, s.authority_source
   FROM subjects s
   WHERE s.heading LIKE '%astronomy%'
   LIMIT 10;
   ```

3. **Multi-Table Join**
   The query should join `records` → `languages` AND `records` → `subjects`

**Good Result:**
- Language filter uses "lat" code (not "latin")
- Subject matched via FTS or LIKE on subjects table
- Results are Latin-language astronomy texts
- Evidence cites MARC 008/35-37 for language, 6XX for subject

---

## B. Filter Type Coverage

### B1. Title Search

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Does The Descent of Man exist in the collection?"}' | jq .
```

**Inspect:**

1. **Title Normalization**
   - Should search for normalized version (lowercase, stripped punctuation)
   - May use FTS5 `titles_fts` table

2. **FTS Verification**
   ```sql
   SELECT mms_id, main_title FROM titles
   WHERE titles MATCH 'descent man'
   LIMIT 5;
   ```

**Good Result:**
- Finds Darwin's "The Descent of Man" if in collection
- Case-insensitive matching works
- Evidence cites MARC 245$a

---

### B2. Agent (Author/Printer) Search

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books printed by Aldus Manutius"}' | jq .
```

**Inspect:**

1. **Agent Normalization**
   ```sql
   SELECT DISTINCT agent_raw, agent_norm, agent_role
   FROM agents
   WHERE agent_norm LIKE '%aldus%' OR agent_norm LIKE '%manutius%'
   LIMIT 10;
   ```

2. **Role Detection**
   - Should match agents with role "printer" if specified
   - Or match any agent if role not specified

**Good Result:**
- Finds books with Aldus as printer/publisher
- Agent name normalized consistently
- Evidence cites MARC 100/700 fields

---

### B3. Country vs Place Distinction

**Query 1 (Country):**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books from Germany"}' | jq .
```

**Query 2 (Place):**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books printed in Berlin"}' | jq .
```

**Inspect:**

1. **Country Code Mapping**
   ```sql
   -- For Germany
   SELECT DISTINCT country_code FROM imprints
   WHERE country_code IN ('gw', 'ge');  -- MARC codes for Germany
   ```

2. **Field Distinction**
   - "from Germany" should use `country_code` column
   - "printed in Berlin" should use `place_norm` column

**Good Result:**
- Country queries use MARC 008/15-17 country codes
- Place queries use normalized imprint place
- Results are correctly scoped

---

### B4. Hebrew Language Query

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hebrew texts from the 16th century"}' | jq .
```

**Inspect:**

1. **Language Code**
   - "Hebrew" → "heb" (ISO 639-2)

2. **Script Detection**
   ```sql
   SELECT DISTINCT language_code, COUNT(*) as cnt
   FROM languages
   WHERE language_code = 'heb'
   GROUP BY language_code;
   ```

**Good Result:**
- Correct language code "heb" used
- Date range 1500-1599 for 16th century
- Hebrew texts from that period returned

---

## C. Ambiguity & Clarification

### C1. Empty Filter Query

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books"}' | jq .
```

**Inspect:**

1. **Clarification Triggered**
   - `response.clarification_needed` should be `true`
   - `response.clarification_message` should suggest refinements

2. **No Execution**
   - `response.candidate_set` should be empty or null
   - Query should NOT execute against full database

**Good Result:**
- System asks for more details
- Suggests: topic, publisher, date, place
- Does NOT return all books in collection

---

### C2. Broad Date Range

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books from 1400 to 1800"}' | jq .
```

**Inspect:**

1. **Warning Detection**
   - Date range is 400 years (> 200 year threshold)
   - Should trigger `BROAD_DATE_RANGE` warning

2. **Response Behavior**
   - May still execute but warn about broad results
   - OR may ask for clarification

**Good Result:**
- System notes the broad range
- Suggests narrowing to specific century or period
- If executed, notes high result count

---

### C3. Single-Word Subject

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Philosophy"}' | jq .
```

**Inspect:**

1. **Vague Query Detection**
   - Single-word subject with no context
   - Should trigger `VAGUE_QUERY` warning

**Good Result:**
- Asks for more specific criteria
- Suggests time period, place, or subtopic
- NOT returning all philosophy books

---

### C4. Low Confidence Parse

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "find me something interesting about old maps"}' | jq .
```

**Inspect:**

1. **Confidence Scores**
   - Check query plan for filter confidence < 0.7
   ```bash
   tail -1 data/query_plan_cache.jsonl | jq '.plan.filters[].confidence'
   ```

**Good Result:**
- If confidence < 0.7, asks for clarification
- Interprets "old maps" as subject or requests specifics
- Does not guess wildly

---

## D. Session Management

### D1. Create and Reuse Session

**Step 1: Create Session**
```bash
RESPONSE=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books about History"}')

SESSION_ID=$(echo $RESPONSE | jq -r '.response.session_id')
echo "Session ID: $SESSION_ID"
```

**Step 2: Continue Conversation**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"only from Paris\", \"session_id\": \"$SESSION_ID\"}" | jq .
```

**Inspect:**

1. **Session Database**
   ```bash
   sqlite3 data/chat/sessions.db "SELECT * FROM chat_sessions WHERE session_id = '$SESSION_ID';"
   ```

2. **Message History**
   ```bash
   sqlite3 data/chat/sessions.db "SELECT role, content FROM chat_messages WHERE session_id = '$SESSION_ID';"
   ```

3. **Active Subgroup**
   - Second query should filter the first result set
   - Not start fresh search

**Good Result:**
- Same session_id in both responses
- Second query narrows results (History books → History books from Paris)
- Message history preserved

---

### D2. Session Retrieval

**Query:**
```bash
curl -s http://localhost:8000/sessions/$SESSION_ID | jq .
```

**Inspect:**
- Returns session metadata
- Includes message history
- Shows conversation phase

**Good Result:**
- Session exists and is retrievable
- All messages in correct order
- Phase transitions logged

---

### D3. Session Expiry

**Query:**
```bash
curl -s -X DELETE http://localhost:8000/sessions/$SESSION_ID | jq .
```

**Inspect:**
```bash
sqlite3 data/chat/sessions.db "SELECT expired_at FROM chat_sessions WHERE session_id = '$SESSION_ID';"
```

**Good Result:**
- Session marked as expired
- Cannot be reused for new queries

---

## E. Evidence & Traceability

### E1. Evidence Field Accuracy

**Query:** Use any successful query result

**Inspect Each Candidate's Evidence:**

1. **MARC Source Tags**
   - Publisher evidence should cite `marc:264$b` or `marc:260$b`
   - Date evidence should cite `marc:264$c` or `marc:260$c`
   - Subject evidence should cite `marc:650$a`, `marc:651$a`, etc.
   - Language evidence should cite `marc:008/35-37`

2. **Verify Against Raw MARC**
   ```sql
   -- Get raw values for a specific record
   SELECT mms_id, publisher_raw, place_raw, date_raw
   FROM imprints
   WHERE mms_id = '<mms_id_from_result>';
   ```

3. **Confidence Scores**
   - Should be between 0.0 and 1.0
   - Higher for exact matches, lower for fuzzy

**Good Result:**
- Every evidence entry has a source tag
- Source tags are accurate MARC field references
- Confidence scores are reasonable (0.80-0.99 typically)
- Can trace back from evidence to raw MARC value

---

### E2. Match Rationale String

**Inspect:**
- Each candidate should have `match_rationale`
- Format: `"field='value' AND field='value'"`

**Good Result:**
- Rationale is human-readable
- Matches the applied filters
- Boolean logic is correct (AND/OR)

---

## F. Edge Cases & Error Handling

### F1. Empty Results

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books published by Imaginary Press in Antarctica"}' | jq .
```

**Inspect:**
- `response.candidate_set.candidates` should be empty `[]`
- Should NOT error
- May suggest broadening the search

**Good Result:**
- Graceful handling of zero results
- Helpful message about no matches
- Suggests alternative queries

---

### F2. SQL Injection Attempt

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books by Oxford\"; DROP TABLE records; --"}' | jq .
```

**Inspect:**
```sql
-- Verify table still exists
SELECT COUNT(*) FROM records;
```

**Good Result:**
- Query fails safely or sanitized
- Database NOT affected
- Error message does NOT expose SQL

---

### F3. Very Long Query

**Query:**
```bash
LONG_QUERY=$(python -c "print('books about ' + 'history ' * 500)")
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"$LONG_QUERY\"}" | jq .
```

**Inspect:**
- Should handle gracefully (truncate or error)
- Should NOT crash server

**Good Result:**
- Handled without crash
- Returns error or truncated processing
- Logs the issue

---

### F4. Special Characters

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books with title containing \"&\" or apostrophe'\'s"}' | jq .
```

**Inspect:**
- Special characters handled in JSON parsing
- SQL query properly escaped

**Good Result:**
- No parsing errors
- Query executes or fails gracefully

---

### F5. Non-ASCII Characters (Hebrew/Arabic)

**Query:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books printed in אמשטרדם"}' | jq .
```

**Inspect:**
```sql
SELECT DISTINCT place_raw, place_norm FROM imprints
WHERE place_raw LIKE '%אמשטרדם%' OR place_norm = 'amsterdam';
```

**Good Result:**
- Hebrew text handled correctly
- Normalized to English equivalent if alias exists
- Results match Amsterdam publications

---

## G. WebSocket Streaming

### G1. Basic Streaming

**Setup:**
```bash
wscat -c ws://localhost:8000/ws/chat
```

**Send:**
```json
{"message": "books published by Oxford"}
```

**Inspect Message Sequence:**

1. `{"type": "session_created", "session_id": "..."}` - Session UUID
2. `{"type": "progress", "message": "Compiling query..."}` - Compilation started
3. `{"type": "progress", "message": "Executing query with N filters..."}` - Execution
4. `{"type": "progress", "message": "Found X results..."}` - Results count
5. `{"type": "batch", "candidates": [...], "batch_num": 1, ...}` - First 10 results
6. (Additional batches if > 10 results)
7. `{"type": "complete", "response": {...}}` - Final response

**Good Result:**
- All message types received in order
- Progress updates appear before results
- Batches contain up to 10 candidates each
- Complete message has full response

---

### G2. Session Reuse via WebSocket

**Send with existing session:**
```json
{"message": "only from Paris", "session_id": "<session_id_from_previous>"}
```

**Inspect:**
- Should NOT create new session
- Should filter previous results

**Good Result:**
- No `session_created` message
- Results narrowed from previous query

---

### G3. Error Handling in WebSocket

**Send invalid JSON:**
```
not json
```

**Inspect:**
- Should receive error message
- Connection should close gracefully

**Good Result:**
- `{"type": "error", "message": "..."}` received
- Connection closes after error
- Server stays running

---

## Database Inspection Cheat Sheet

### Quick Record Lookup
```sql
-- Get full record details
SELECT r.mms_id, t.main_title, i.publisher_norm, i.place_norm,
       i.date_start, i.date_end, i.country_code
FROM records r
LEFT JOIN titles t ON r.mms_id = t.mms_id
LEFT JOIN imprints i ON r.mms_id = i.mms_id
WHERE r.mms_id = '<mms_id>';
```

### Check Normalization Coverage
```sql
-- How many records have normalized publishers?
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN publisher_norm IS NOT NULL THEN 1 ELSE 0 END) as with_norm
FROM imprints;
```

### Subject Distribution
```sql
SELECT heading, COUNT(*) as cnt
FROM subjects
GROUP BY heading
ORDER BY cnt DESC
LIMIT 20;
```

### Language Distribution
```sql
SELECT language_code, COUNT(*) as cnt
FROM languages
GROUP BY language_code
ORDER BY cnt DESC;
```

### Date Range Distribution
```sql
SELECT
  CASE
    WHEN date_start < 1500 THEN 'Before 1500'
    WHEN date_start BETWEEN 1500 AND 1599 THEN '16th Century'
    WHEN date_start BETWEEN 1600 AND 1699 THEN '17th Century'
    WHEN date_start BETWEEN 1700 AND 1799 THEN '18th Century'
    WHEN date_start >= 1800 THEN '19th Century+'
    ELSE 'Unknown'
  END as period,
  COUNT(*) as cnt
FROM imprints
GROUP BY period;
```

---

## Logging Inspection

### API Server Logs
Watch the terminal running `uvicorn` for request logs.

### Query Plan Cache
```bash
# View recent query plans
tail -5 data/query_plan_cache.jsonl | jq .

# Search for specific query
grep "Oxford" data/query_plan_cache.jsonl | jq .
```

### Session Database
```bash
# All sessions
sqlite3 data/chat/sessions.db "SELECT session_id, created_at, phase FROM chat_sessions ORDER BY created_at DESC LIMIT 10;"

# Messages for session
sqlite3 data/chat/sessions.db "SELECT role, substr(content, 1, 50) as preview FROM chat_messages WHERE session_id = '<id>';"
```

---

## Summary: What Can the Bot Do?

### Current Capabilities
| Feature | Status | Notes |
|---------|--------|-------|
| Publisher search | ✅ | Normalized matching |
| Place search | ✅ | Normalized with alias map |
| Date/Year range | ✅ | Century conversion works |
| Language filter | ✅ | ISO 639-2 codes |
| Subject search | ✅ | FTS5 indexed |
| Title search | ✅ | FTS5 indexed |
| Agent/Author search | ✅ | Normalized names |
| Country filter | ✅ | MARC country codes |
| Multi-filter queries | ✅ | AND logic |
| Session continuity | ✅ | Multi-turn conversations |
| Clarification prompts | ✅ | For ambiguous queries |
| WebSocket streaming | ✅ | Real-time results |
| Evidence tracing | ✅ | MARC field citations |

### Known Limitations
| Limitation | Impact | Workaround |
|------------|--------|------------|
| No OR logic in filters | Cannot search "Paris OR London" | Make separate queries |
| No negation | Cannot exclude ("NOT French") | Filter results manually |
| No proximity search | Cannot search "printing near Venice" | Use exact place |
| No date approximation | "around 1550" may be too strict | Use range explicitly |
| Limited cross-collection | Single collection only | - |
| No recommendation ranking | Results not ranked by relevance | - |

### What to Test Next
1. **Boundary conditions**: Exact year matches, edge of date ranges
2. **Normalization accuracy**: Hebrew place names, variant spellings
3. **LLM interpretation robustness**: Same query phrased differently
4. **Performance**: Large result sets, complex joins
5. **Concurrent users**: Multiple sessions simultaneously

---

## Appendix: Quick Test Script

Save as `test_chatbot.sh`:
```bash
#!/bin/bash

BASE_URL="http://localhost:8000"

echo "=== Health Check ==="
curl -s "$BASE_URL/health" | jq .

echo -e "\n=== Test 1: Publisher + Date ==="
curl -s -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "books published by Oxford between 1500 and 1599"}' | jq '.response.candidate_set.total_count'

echo -e "\n=== Test 2: Clarification ==="
curl -s -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "books"}' | jq '.response.clarification_needed'

echo -e "\n=== Test 3: Language + Subject ==="
curl -s -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Latin books on astronomy"}' | jq '.response.candidate_set.total_count'

echo -e "\n=== All tests complete ==="
```

Run with: `chmod +x test_chatbot.sh && ./test_chatbot.sh`
