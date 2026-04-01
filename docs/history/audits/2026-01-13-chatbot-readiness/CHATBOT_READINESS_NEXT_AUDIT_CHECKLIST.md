# Next Audit Checklist: Chatbot UI Readiness
**Purpose:** Reusable playbook for tracking chatbot implementation progress
**Initial Audit:** 2026-01-13
**Next Audit Recommended:** After Phase 1 completion (Week 1)

---

## Pre-Audit Preparation

### 1. Gather Updated Context
```bash
# Update git status
git status
git log --oneline -10

# Check new files in chat module
find scripts/chat app/api -name "*.py" 2>/dev/null

# Check test coverage
pytest tests/scripts/chat tests/app/api --cov=scripts.chat --cov=app.api

# Check database schema changes
sqlite3 data/chat/sessions.db ".schema" 2>/dev/null

# Check API endpoints
curl http://localhost:8000/docs 2>/dev/null  # FastAPI auto-docs
```

### 2. Review Completed Tasks
- [ ] Read git commit messages since last audit
- [ ] Check closed issues/PRs related to chatbot
- [ ] Review test results from CI
- [ ] Check deployment status (staging/production)

### 3. Collect Metrics
```bash
# Query performance (if metrics endpoint exists)
curl http://localhost:8000/metrics | grep query_

# Session statistics (if implemented)
sqlite3 data/chat/sessions.db "SELECT COUNT(*) FROM chat_sessions;"
sqlite3 data/chat/sessions.db "SELECT COUNT(*) FROM chat_messages;"

# Error rates (if logging implemented)
grep "ERROR" logs/api.log | wc -l
```

---

## Audit Execution

### Phase 1 Verification: Conversational Foundation

**Finding CB-001: Session Management**
- [ ] `scripts/chat/models.py` exists with ChatSession, Message, ChatResponse
- [ ] Unit tests pass: `pytest tests/scripts/chat/test_models.py`
- [ ] Schema validation works (invalid data rejected)

**Finding CB-002: API Layer**
- [ ] `app/api/main.py` exists with FastAPI app
- [ ] `/chat` POST endpoint responds to requests
- [ ] Integration tests pass: `pytest tests/app/api/test_chat.py`
- [ ] Error responses return appropriate HTTP codes

**Finding CB-003: Response Formatting**
- [ ] `scripts/chat/formatter.py` exists with `format_for_chat()`
- [ ] Zero-results message is user-friendly
- [ ] Multiple results formatted with count + sample
- [ ] Unit tests pass: `pytest tests/scripts/chat/test_formatter.py`

**Session Storage**
- [ ] SQLite schema created for chat_sessions and chat_messages
- [ ] `SessionStore` class implements CRUD operations
- [ ] Sessions persist across API restarts
- [ ] Messages ordered chronologically in database

**Integration Test:**
```bash
# Start API server
uvicorn app.api.main:app --reload &

# Send test query
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-123", "message": "books by Oxford"}'

# Verify response
# Expected: JSON with {message, candidate_set}

# Send follow-up in same session
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-123", "message": "filter by 16th century"}'

# Verify session persistence
sqlite3 data/chat/sessions.db "SELECT * FROM chat_messages WHERE session_id='test-123';"
```

**Phase 1 Completion Criteria:**
- [ ] All P0 findings (CB-001, CB-002, CB-003) resolved
- [ ] Basic multi-turn conversation works
- [ ] Sessions persist correctly
- [ ] No regressions in M4 query pipeline

---

### Phase 2 Verification: UX Enhancements

**Finding CB-004: Clarification Flow**
- [ ] `scripts/chat/clarification.py` exists with ambiguity detection
- [ ] Empty filters trigger clarification request
- [ ] `/chat` endpoint returns `clarification_needed` field
- [ ] Retry logic works with user-provided clarification

**Test Ambiguous Queries:**
```bash
# Test 1: No filters extracted
curl -X POST http://localhost:8000/chat \
  -d '{"session_id": "test-ambig", "message": "I need a book"}'
# Expected: clarification_needed != null

# Test 2: Provide clarification
curl -X POST http://localhost:8000/chat \
  -d '{"session_id": "test-ambig", "message": "Books about astronomy in Latin"}'
# Expected: QueryPlan with subject + language filters
```

**Finding CB-005: Streaming Responses**
- [ ] `/ws/chat` WebSocket endpoint exists
- [ ] Clients receive progress updates during query execution
- [ ] Results stream in batches (configurable size)
- [ ] Connection closes gracefully after completion

**Test WebSocket:**
```python
# Use websockets library
import asyncio
import websockets
import json

async def test_streaming():
    async with websockets.connect("ws://localhost:8000/ws/chat") as ws:
        await ws.send(json.dumps({"message": "books by Oxford"}))
        async for message in ws:
            data = json.loads(message)
            print(f"Received: {data['type']} - {data['content']}")

asyncio.run(test_streaming())
```

**Finding CB-006: Rate Limiting**
- [ ] Rate limiter middleware configured (slowapi)
- [ ] Limit enforced: 10 queries/minute per session
- [ ] HTTP 429 returned when limit exceeded
- [ ] OpenAI API costs logged per session

**Test Rate Limiting:**
```bash
# Send 11 queries rapidly
for i in {1..11}; do
  curl -X POST http://localhost:8000/chat \
    -d '{"session_id": "rate-test", "message": "query '$i'"}' &
done

# Expected: 10 succeed (200), 1 fails (429)
```

**Phase 2 Completion Criteria:**
- [ ] All P1 findings (CB-004, CB-005, CB-006) resolved
- [ ] Clarifications reduce failed queries measurably
- [ ] Streaming improves perceived latency
- [ ] Rate limiting prevents abuse

---

### Phase 3 Verification: Production Hardening

**Finding CB-007: Authentication**
- [ ] `app/api/auth.py` exists with JWT functions
- [ ] `/login` and `/logout` endpoints work
- [ ] `/chat` requires Bearer token (401 without)
- [ ] Sessions isolated per user_id

**Test Authentication:**
```bash
# Test 1: No token (should fail)
curl -X POST http://localhost:8000/chat \
  -d '{"session_id": "auth-test", "message": "books"}'
# Expected: 401 Unauthorized

# Test 2: Login
TOKEN=$(curl -X POST http://localhost:8000/login \
  -d '{"username": "test", "password": "test"}' | jq -r .access_token)

# Test 3: With token (should succeed)
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"session_id": "auth-test", "message": "books"}'
# Expected: 200 OK
```

**Finding CB-008: Performance Metrics**
- [ ] `/metrics` endpoint returns Prometheus format
- [ ] Custom metrics tracked: query_latency, cache_hit_rate, llm_call_duration
- [ ] Slow queries logged (threshold > 5s)
- [ ] Grafana dashboard configured (optional)

**Test Metrics:**
```bash
curl http://localhost:8000/metrics | grep query_latency
# Expected: histogram with P50, P95, P99
```

**Finding CB-009: Multi-User Isolation**
- [ ] `user_id` field added to ChatSession model
- [ ] Session queries filtered by user_id
- [ ] Concurrent users don't interfere with each other

**Test Multi-User:**
```bash
# User 1
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN_USER1" \
  -d '{"message": "query from user 1"}'

# User 2
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN_USER2" \
  -d '{"message": "query from user 2"}'

# Verify isolation
sqlite3 data/chat/sessions.db \
  "SELECT user_id, COUNT(*) FROM chat_sessions GROUP BY user_id;"
```

**Load Testing:**
```bash
# Run locust load test
locust -f tests/load/locustfile.py --host=http://localhost:8000

# Test scenarios:
# 1. 10 concurrent users (baseline)
# 2. 50 concurrent users (target)
# 3. 100 concurrent users (stress)

# Check results:
# - P95 latency < 3s (cached queries)
# - P95 latency < 10s (uncached queries)
# - Error rate < 1%
```

**Phase 3 Completion Criteria:**
- [ ] All P2 findings (CB-007, CB-008, CB-009) resolved
- [ ] API handles 50 concurrent users
- [ ] Authentication protects endpoints
- [ ] Performance metrics within SLOs

---

## Regression Checks

### M4 Query Pipeline (Must Not Break)

```bash
# Test M4 still works via CLI
python -m app.cli query "books by Oxford between 1500 and 1599" \
  --db data/index/bibliographic.db

# Expected: CandidateSet with evidence

# Run M4 regression tests
pytest tests/scripts/query/ -v

# Run QA regression suite
python -m app.qa regress \
  --gold data/qa/gold.json \
  --db data/index/bibliographic.db

# Expected: All tests pass
```

### Evidence Extraction (Must Preserve Traceability)

```bash
# Query via API
RESULT=$(curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "books by Oxford"}')

# Check evidence structure
echo $RESULT | jq '.candidate_set.candidates[0].evidence'

# Expected: Each evidence has:
# - field, value, operator, matched_against, source, confidence
```

---

## Metrics Comparison

| Metric | Baseline (Week 0) | Week 1 | Week 2 | Week 3 | Week 4 |
|--------|------------------|--------|--------|--------|--------|
| **Session Management** | 0% | TARGET: 100% | | | |
| **API Layer** | 0% | TARGET: 100% | | | |
| **Response Formatting** | 30% | TARGET: 100% | | | |
| **Clarification Flow** | 0% | | TARGET: 100% | | |
| **Streaming** | 0% | | TARGET: 100% | | |
| **Rate Limiting** | 0% | | TARGET: 100% | | |
| **Authentication** | 0% | | | TARGET: 100% | |
| **Performance Metrics** | 0% | | | TARGET: 100% | |
| **Multi-User Isolation** | 0% | | | TARGET: 100% | |
| **Web UI** | 0% | | | | TARGET: 100% |
| **Overall Readiness** | 60% | 75% | 85% | 95% | 100% |

---

## Issue Tracking Template

For each finding that's NOT yet resolved:

```yaml
- finding_id: CB-XXX
  status: in_progress | blocked | not_started
  assigned_to: developer_name
  blocked_by: [dependency findings or external factors]
  progress:
    - date: 2026-01-XX
      update: "Implemented ChatSession model"
    - date: 2026-01-YY
      update: "Added unit tests, 80% coverage"
  remaining_work:
    - "Integration tests"
    - "API endpoint"
  estimated_completion: 2026-01-ZZ
```

---

## Questions for Next Audit

### Technical
1. Has query latency been profiled? (Median, P95, P99)
2. Are there any new bottlenecks in the chat layer?
3. Have any M4 query pipeline changes impacted chat?
4. Is the LLM cache hit rate acceptable? (Target: >50%)

### Product
1. Have users tested the chat interface?
2. What's the most common failure mode?
3. Are clarifications effective at reducing errors?
4. What features are users requesting?

### Operations
1. What's the actual OpenAI API cost per query?
2. How many active sessions are typical?
3. What's the database size growth rate?
4. Have there been any security incidents?

---

## Diff Against Previous Audit

```bash
# Compare findings
diff CHATBOT_READINESS_FINDINGS.yaml CHATBOT_READINESS_FINDINGS_UPDATED.yaml

# Count resolved findings
grep "status: resolved" CHATBOT_READINESS_FINDINGS_UPDATED.yaml | wc -l

# Identify new findings
grep "severity: P0" CHATBOT_READINESS_FINDINGS_UPDATED.yaml
```

---

## Next Audit Date

**Schedule Next Audit:**
- **After Phase 1:** Week 1 (2026-01-20) - Verify conversational foundation
- **After Phase 2:** Week 2 (2026-01-27) - Verify UX enhancements
- **After Phase 3:** Week 3 (2026-02-03) - Verify production hardening
- **After Phase 4:** Week 4 (2026-02-10) - Final verification before launch

**Exit Criteria (Audit Complete):**
- [ ] All P0 findings resolved
- [ ] All P1 findings resolved
- [ ] All P2 findings resolved or deferred
- [ ] Overall readiness ≥ 95%
- [ ] No regressions in M4 query pipeline
- [ ] Load tests pass with 50 concurrent users
- [ ] User acceptance testing completed

---

**End of Checklist**
