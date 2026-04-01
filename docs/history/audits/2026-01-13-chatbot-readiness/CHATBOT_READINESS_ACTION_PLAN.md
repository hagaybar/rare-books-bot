# Action Plan: Chatbot UI Implementation
**Generated:** 2026-01-13
**Target:** Build conversational interface (M6) on top of existing M4 query pipeline
**Estimated Duration:** 3-4 weeks
**Approach:** Progressive enhancement - preserve M4, add conversation layer

---

## Overview

This plan addresses findings from the Chatbot Readiness Audit. It focuses on **building new capabilities** rather than modifying the existing query pipeline, which is already excellent.

**Key Principle:** M4 (query pipeline) is the foundation. M6 (conversational layer) sits on top.

---

## Phase 1: Conversational Foundation (Week 1)
**Goal:** Enable basic multi-turn conversations with session persistence

### Step 1.1: Define Conversation Schemas (1 day)
**Addresses:** CB-001 (Session Management)
**Priority:** P0 (Blocker)

**Tasks:**
1. Create `scripts/chat/models.py` with Pydantic schemas:
   ```python
   class ChatSession(BaseModel):
       session_id: str = Field(default_factory=uuid4)
       user_id: Optional[str] = None
       created_at: datetime
       updated_at: datetime
       messages: List[Message] = []
       context: Dict[str, Any] = {}  # Carry-forward state
       metadata: Dict[str, Any] = {}

   class Message(BaseModel):
       role: Literal["user", "assistant", "system"]
       content: str
       query_plan: Optional[QueryPlan] = None
       candidate_set: Optional[CandidateSet] = None
       timestamp: datetime = Field(default_factory=datetime.utcnow)

   class ChatResponse(BaseModel):
       message: str  # Natural language response
       candidate_set: Optional[CandidateSet]
       suggested_followups: List[str] = []
       clarification_needed: Optional[str] = None
   ```

2. Add schemas to `scripts/schemas/__init__.py`
3. Write unit tests for schema validation

**Deliverables:**
- `scripts/chat/models.py` with ChatSession, Message, ChatResponse
- Unit tests in `tests/scripts/chat/test_models.py`

**Acceptance:**
- [ ] All schemas JSON-serializable via Pydantic
- [ ] Validation tests pass (invalid data rejected)

---

### Step 1.2: Implement Session Storage (2 days)
**Addresses:** CB-001 (Session Management)
**Priority:** P0 (Blocker)

**Tasks:**
1. Create SQLite schema for sessions:
   ```sql
   CREATE TABLE chat_sessions (
       session_id TEXT PRIMARY KEY,
       user_id TEXT,
       created_at TEXT,
       updated_at TEXT,
       context TEXT,  -- JSON
       metadata TEXT  -- JSON
   );

   CREATE TABLE chat_messages (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       session_id TEXT,
       role TEXT,
       content TEXT,
       query_plan TEXT,  -- JSON
       candidate_set TEXT,  -- JSON
       timestamp TEXT,
       FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
   );
   ```

2. Implement `scripts/chat/session_store.py`:
   ```python
   class SessionStore:
       def create_session(user_id: Optional[str]) -> ChatSession
       def get_session(session_id: str) -> ChatSession
       def add_message(session_id: str, message: Message) -> None
       def update_context(session_id: str, context: Dict) -> None
       def expire_session(session_id: str) -> None
   ```

3. Add database migrations (or use Alembic)
4. Write integration tests with test database

**Deliverables:**
- `scripts/chat/session_store.py` with CRUD operations
- SQLite schema in `scripts/chat/schema.sql`
- Integration tests in `tests/scripts/chat/test_session_store.py`

**Acceptance:**
- [ ] Sessions persist across restarts
- [ ] Messages ordered chronologically
- [ ] Context updates work correctly

---

### Step 1.3: Build Response Formatter (1 day)
**Addresses:** CB-003 (Response Formatting)
**Priority:** P0 (Blocker)

**Tasks:**
1. Implement `scripts/chat/formatter.py`:
   ```python
   def format_for_chat(candidate_set: CandidateSet, query_text: str) -> str:
       """Convert CandidateSet to natural language response."""
       if candidate_set.total_count == 0:
           return f"I couldn't find any books matching '{query_text}'."

       summary = f"Found {candidate_set.total_count} books"
       # Add filter summary from QueryPlan
       # Format top 3 candidates with evidence
       return summary
   ```

2. Add templates for common scenarios:
   - Zero results
   - Single result
   - Multiple results (with preview)
   - Error states

3. Write unit tests with fixture CandidateSets

**Deliverables:**
- `scripts/chat/formatter.py` with formatting functions
- Unit tests in `tests/scripts/chat/test_formatter.py`

**Acceptance:**
- [ ] Zero-results message is friendly
- [ ] Multiple results show count + sample (top 3)
- [ ] Evidence formatted as bullet points

---

### Step 1.4: Create Chat API Endpoint (2 days)
**Addresses:** CB-002 (API Layer)
**Priority:** P0 (Blocker)
**Dependencies:** Steps 1.1, 1.2, 1.3

**Tasks:**
1. Add FastAPI to dependencies: `poetry add fastapi uvicorn[standard]`

2. Create `app/api/main.py`:
   ```python
   from fastapi import FastAPI, HTTPException
   from scripts.chat.models import ChatRequest, ChatResponse
   from scripts.chat.session_store import SessionStore
   from scripts.query.compile import compile_query
   from scripts.query.execute import execute_plan
   from scripts.chat.formatter import format_for_chat

   app = FastAPI(title="Rare Books Chat API")
   store = SessionStore()

   @app.post("/chat")
   async def chat(request: ChatRequest) -> ChatResponse:
       # 1. Get or create session
       session = store.get_session(request.session_id)

       # 2. Compile query
       plan = compile_query(request.message)

       # 3. Execute query
       candidate_set = execute_plan(plan, db_path)

       # 4. Format response
       message = format_for_chat(candidate_set, request.message)

       # 5. Save to session
       store.add_message(session.session_id, Message(
           role="user", content=request.message
       ))
       store.add_message(session.session_id, Message(
           role="assistant", content=message,
           query_plan=plan, candidate_set=candidate_set
       ))

       return ChatResponse(message=message, candidate_set=candidate_set)
   ```

3. Add error handling middleware
4. Write integration tests with TestClient

**Deliverables:**
- `app/api/main.py` with `/chat` endpoint
- Integration tests in `tests/app/api/test_chat.py`
- README update with API usage

**Acceptance:**
- [ ] `POST /chat` returns ChatResponse
- [ ] Session ID persists across calls
- [ ] Errors return HTTP 400/500 with details

---

## Phase 2: UX Enhancements (Week 2)
**Goal:** Improve conversational quality and responsiveness

### Step 2.1: Add Clarification Flow (2 days)
**Addresses:** CB-004 (Disambiguation)
**Priority:** P1 (Critical)
**Dependencies:** Phase 1 complete

**Tasks:**
1. Implement ambiguity detection in `scripts/chat/clarification.py`:
   ```python
   def detect_ambiguity(plan: QueryPlan, query_text: str) -> Optional[str]:
       # No filters extracted
       if not plan.filters:
           return "I'm not sure what you're looking for. Could you be more specific?"

       # Date ambiguity
       year_filters = [f for f in plan.filters if f.field == FilterField.YEAR]
       if year_filters and len(query_text.split()) > 10:
           # User gave verbose query but only date extracted
           return "I found a date range. Are you also filtering by place, publisher, or subject?"

       # Subject with low confidence
       # ... more heuristics
   ```

2. Modify `/chat` endpoint to return clarification_needed
3. Add retry logic when user provides clarification
4. Write test cases for common ambiguities

**Deliverables:**
- `scripts/chat/clarification.py` with detection logic
- Updated `/chat` endpoint handling clarifications
- Test cases in `tests/scripts/chat/test_clarification.py`

**Acceptance:**
- [ ] Empty filters trigger clarification
- [ ] User can respond to clarification
- [ ] Retry uses original query + clarification

---

### Step 2.2: Implement Streaming Responses (3 days)
**Addresses:** CB-005 (Progressive Results)
**Priority:** P1 (Critical)
**Dependencies:** Phase 1 complete

**Tasks:**
1. Add WebSocket support to FastAPI:
   ```python
   from fastapi import WebSocket

   @app.websocket("/ws/chat")
   async def chat_stream(websocket: WebSocket):
       await websocket.accept()
       # 1. Receive query
       # 2. Send progress: "Compiling query..."
       # 3. Send progress: "Executing SQL..."
       # 4. Stream results in batches of 10
   ```

2. Modify `execute_plan()` to support batching:
   ```python
   def execute_plan_batched(plan, db_path, batch_size=10):
       # Yield candidates in batches
       for batch in fetch_candidates_batched(conn, sql, batch_size):
           yield batch
   ```

3. Add progress messages to chat formatter
4. Write WebSocket test client

**Deliverables:**
- `/ws/chat` WebSocket endpoint
- Batched query execution in `execute.py`
- Test cases in `tests/app/api/test_websocket.py`

**Acceptance:**
- [ ] Client receives progress updates
- [ ] Results stream in batches (10 per batch)
- [ ] Connection closes gracefully after completion

---

### Step 2.3: Add Rate Limiting (1 day)
**Addresses:** CB-006 (Quota Management)
**Priority:** P1 (Critical)
**Dependencies:** Phase 1 complete

**Tasks:**
1. Add `slowapi` to dependencies: `poetry add slowapi`

2. Configure rate limiter in `app/api/main.py`:
   ```python
   from slowapi import Limiter, _rate_limit_exceeded_handler
   from slowapi.util import get_remote_address

   limiter = Limiter(key_func=get_remote_address)
   app.state.limiter = limiter

   @app.post("/chat")
   @limiter.limit("10/minute")
   async def chat(request: ChatRequest):
       # ...
   ```

3. Add session-based rate limiting (per session_id)
4. Track OpenAI API costs in logs
5. Write rate limit test cases

**Deliverables:**
- Rate limiter middleware configured
- Per-session query counter in database
- Test cases in `tests/app/api/test_rate_limit.py`

**Acceptance:**
- [ ] 10 queries/minute limit enforced
- [ ] HTTP 429 returned when exceeded
- [ ] OpenAI costs logged per session

---

## Phase 3: Production Hardening (Week 3)
**Goal:** Security, observability, scalability

### Step 3.1: Add Authentication (2 days)
**Addresses:** CB-007 (Auth/Authz)
**Priority:** P2 (Important)

**Tasks:**
1. Add `python-jose[cryptography]` and `passlib` to dependencies

2. Implement JWT auth in `app/api/auth.py`:
   ```python
   from fastapi.security import HTTPBearer
   from jose import jwt

   security = HTTPBearer()

   def create_access_token(user_id: str) -> str:
       # Generate JWT

   def verify_token(token: str) -> str:
       # Validate JWT, return user_id
   ```

3. Add `/login` and `/logout` endpoints
4. Protect `/chat` endpoint with auth dependency
5. Add user_id to ChatSession model

**Deliverables:**
- `app/api/auth.py` with JWT functions
- `/login` and `/logout` endpoints
- Protected `/chat` requiring Bearer token

**Acceptance:**
- [ ] `/chat` returns 401 without valid token
- [ ] Token includes user_id in claims
- [ ] Sessions isolated per user

---

### Step 3.2: Add Performance Metrics (2 days)
**Addresses:** CB-008 (Observability)
**Priority:** P2 (Important)

**Tasks:**
1. Add `prometheus-fastapi-instrumentator` to dependencies

2. Configure metrics in `app/api/main.py`:
   ```python
   from prometheus_fastapi_instrumentator import Instrumentator

   instrumentator = Instrumentator()
   instrumentator.instrument(app).expose(app)
   ```

3. Add custom metrics for query pipeline:
   - Query compilation time
   - SQL execution time
   - LLM API call duration
   - Cache hit rate

4. Set up Grafana dashboard (optional)

**Deliverables:**
- `/metrics` endpoint exposing Prometheus metrics
- Custom query pipeline metrics
- Grafana dashboard JSON (optional)

**Acceptance:**
- [ ] `/metrics` returns Prometheus format
- [ ] Query latency P50/P95/P99 tracked
- [ ] Slow queries logged (>5s threshold)

---

### Step 3.3: Load Testing & Optimization (2 days)
**Addresses:** CB-005, CB-008 (Performance)
**Priority:** P2 (Important)

**Tasks:**
1. Write load test script using `locust`:
   ```python
   from locust import HttpUser, task

   class ChatUser(HttpUser):
       @task
       def send_query(self):
           self.client.post("/chat", json={
               "session_id": self.session_id,
               "message": "books by Oxford"
           })
   ```

2. Run load test with 10/50/100 concurrent users
3. Identify bottlenecks (likely database or LLM calls)
4. Optimize:
   - Add database connection pooling
   - Expand LLM cache
   - Add result caching (query hash → CandidateSet)

**Deliverables:**
- Load test script in `tests/load/locustfile.py`
- Load test report with latency percentiles
- Optimization PRs if bottlenecks found

**Acceptance:**
- [ ] API handles 50 concurrent users
- [ ] P95 latency < 3s for cached queries
- [ ] P95 latency < 10s for uncached queries

---

## Phase 4: Web UI Integration (Week 4)
**Goal:** Build simple web-based chat interface

### Step 4.1: Build Frontend (3-4 days)
**Priority:** P2 (Important)
**Dependencies:** Phases 1-3 complete

**Tasks:**
1. Choose framework (React, Vue, or simple HTML+JS)

2. Implement chat UI:
   - Message list (user + assistant)
   - Input box with Send button
   - Display CandidateSet results (expandable)
   - Show evidence on click
   - Loading indicators

3. Integrate with `/chat` API endpoint

4. Add WebSocket support for streaming (optional)

**Deliverables:**
- Frontend code in `app/web/` or separate repo
- Dockerized deployment (frontend + API)
- User documentation

**Acceptance:**
- [ ] User can send queries and see responses
- [ ] Conversation history visible
- [ ] Results clickable to show evidence

---

## Rollback Strategy

Each phase is designed to be independently testable and deployable:

**Phase 1 Rollback:**
- Remove `/chat` endpoint
- Drop chat_sessions and chat_messages tables
- Revert to CLI-only usage

**Phase 2 Rollback:**
- Disable WebSocket endpoint (use HTTP POST only)
- Disable rate limiting (development mode)
- Remove clarification logic (simple error messages)

**Phase 3 Rollback:**
- Disable authentication (local-only deployment)
- Remove metrics collection
- Skip load testing (manual QA only)

---

## Testing Strategy

### Unit Tests
- All new schemas (Pydantic validation)
- Session CRUD operations
- Response formatter (template rendering)
- Clarification detection heuristics

### Integration Tests
- `/chat` endpoint with test database
- Session persistence across requests
- Error handling (missing API key, invalid queries)

### End-to-End Tests
- Multi-turn conversation flow
- Clarification → retry flow
- WebSocket streaming

### Load Tests
- Concurrent users (10/50/100)
- Sustained load (1 hour at 10 QPS)
- Spike test (burst to 100 users)

---

## Success Metrics

**Phase 1 (MVP):**
- [ ] `/chat` endpoint functional
- [ ] Sessions persist conversation history
- [ ] Natural language responses generated

**Phase 2 (UX):**
- [ ] Clarifications reduce failed queries by 30%
- [ ] Streaming improves perceived latency by 50%
- [ ] Rate limiting prevents abuse

**Phase 3 (Production):**
- [ ] Authentication protects API
- [ ] P95 latency < 3s (cached) / < 10s (uncached)
- [ ] Handles 50 concurrent users

**Phase 4 (Web UI):**
- [ ] Users complete multi-turn conversations
- [ ] 80% of queries result in displayed results
- [ ] Zero critical security vulnerabilities

---

## Risk Mitigation

**Risk:** LLM API costs spiral out of control
**Mitigation:** Rate limiting (10/min), aggressive caching, cost alerts

**Risk:** Query latency too high for chat UX
**Mitigation:** Streaming responses, background execution, result caching

**Risk:** Session storage grows unbounded
**Mitigation:** Expire sessions after 24 hours, archive old sessions

**Risk:** Multi-user concurrency breaks SQLite
**Mitigation:** Use PostgreSQL for production, or Redis for sessions

---

## Next Steps After This Plan

**M7 - Advanced Conversational Features:**
- Context carry-forward ("show me more", "filter by Paris")
- Query refinement ("too many results? narrow by year")
- Conversation summaries ("you asked about 5 topics today")

**M8 - Enrichment Layer:**
- Web search for missing records
- External API integration (WorldCat, OCLC)
- Cached enrichment with citations

**M9 - Admin Dashboard:**
- Query analytics (popular searches)
- Error tracking (failed queries)
- User management (quotas, permissions)

---

**End of Action Plan**
