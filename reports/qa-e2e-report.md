# E2E QA Test Report — Rare Books Bot

**Date**: 2026-03-27
**Branch**: feature/network-map-explorer
**Tested by**: Automated Playwright + manual verification

---

## 1. Application Areas Tested

| Screen | URL | Status | Data |
|--------|-----|--------|------|
| Chat | / | PASS | Rich query responses with evidence |
| Network Map | /network | PASS | 2,757 agents, 32,300 edges, all controls work |
| Coverage | /operator/coverage | PASS with bugs | Charts render but coverage scores incorrect |
| Workbench | /operator/workbench | PASS | 4 field tabs, table, pagination, inline edit |
| Agent Chat | /operator/agent | PASS with bugs | Loads but coverage sidebar shows zeros |
| Review | /operator/review | PASS | Clean empty state |
| Query Debugger | /diagnostics/query | PASS | Ready for queries |
| DB Explorer | /diagnostics/db | PASS | 17 tables browsable |
| Publishers | /admin/publishers | PASS | 227 authorities |
| Enrichment | /admin/enrichment | PASS (fixed) | 1,924 agents with Wikipedia links |
| Health | /admin/health | PASS | Healthy |

**Total**: 11 screens tested, all load and render

---

## 2. Test Flows Executed

### Chat (8 tests, all passed)
- Happy path query ("books published in Amsterdam") — 30 results with Primo links
- Follow-up query in same session — context preserved
- Vague query ("books") — clarification triggered
- Hebrew input ("ספרים בירושלים") — RTL renders correctly, 30 results
- Long query (176 chars) — textarea auto-resize, correct parsing
- Empty submit — send button correctly disabled
- Network requests — all POST /chat return 200
- DB persistence — session and messages saved to sessions.db

### Network Map (12 tests, all passed)
- Map renders with OpenFreeMap tiles
- 150 agents shown with colored dots at correct cities
- Connection arcs visible, color-coded by type
- All 5 connection type toggles work (multi-select)
- Century and role dropdowns filter correctly
- Agent slider (50-500) dynamically updates
- Agent click opens detail panel with Wikipedia summary + connections
- Empty state message shown when no results match filters
- API endpoints return valid JSON
- Console: only WebGL environment warnings (headless browser)

### Operator Screens (4 screens tested)
- Coverage: charts render, normalization insights cards present
- Workbench: all 4 field tabs work, pagination, filtering
- Agent Chat: loads with agent selector and quick actions
- Review: clean empty state

### Admin Screens (4 screens tested)
- DB Explorer: 17 tables, pagination, search
- Publishers: 227 authorities with type filter
- Enrichment: 1,924 agent cards with portraits, filters by occupation/century/role
- Health: all systems healthy, 39.1 MB DB

---

## 3. Bugs Found (10 total)

### BUG-001 — SPA Routing Broken for Direct URLs
- **Severity**: HIGH
- **Steps**: Navigate directly to http://localhost:5173/network (or any non-root URL)
- **Expected**: Page loads via React Router
- **Actual**: 404/405 error — Vite proxies to FastAPI instead of serving index.html
- **Root cause**: Vite dev server config missing SPA fallback
- **Fix**: Add historyApiFallback to vite.config.ts

### BUG-002 — Coverage Dashboard: Place/Publisher Show "0% resolved"
- **Severity**: HIGH
- **Steps**: Navigate to Coverage via sidebar
- **Expected**: Place shows ~99.3%, Publisher shows ~98.8%
- **Actual**: Both show "0% resolved (2,773 remaining)"
- **Root cause**: Frontend component not mapping backend confidence data to resolved/unresolved correctly
- **Affects**: `/operator/coverage`

### BUG-003 — Data Quality Score Shows 0%
- **Severity**: HIGH
- **Steps**: View Coverage dashboard Data Quality Score card
- **Expected**: ~98% (weighted average of normalization coverage)
- **Actual**: 0%
- **Root cause**: Scoring formula disconnected from real data

### BUG-004 — Agent Chat Coverage Sidebar Shows All Zeros
- **Severity**: MEDIUM
- **Steps**: Navigate to Agent Chat
- **Expected**: Coverage breakdown (High/Medium/Low/Unmapped) matches real data
- **Actual**: All show 0
- **Root cause**: Coverage API may return data in unexpected format, or frontend mapping is wrong

### BUG-005 — Wikipedia URLs Were Broken (FIXED)
- **Severity**: CRITICAL (now fixed)
- **Steps**: Click Wikipedia link on any Enrichment card
- **Expected**: Opens correct Wikipedia article
- **Actual**: Was returning 404 (Special:GoToLinkedPage)
- **Fix applied**: Updated 1,337 URLs from wikipedia_cache, 581 fallback to Wikidata pages
- **Root cause**: `wikidata_client.py` generated non-functional redirect URLs. Fixed in source code.

### BUG-006 — Duplicate Clarification Message
- **Severity**: LOW
- **Steps**: Type "books" in chat
- **Expected**: Clarification appears once
- **Actual**: Same message appears twice (amber box + message bubble)
- **Root cause**: Backend sets both `clarification_needed` and `message` to same text

### BUG-007 — Textarea Height Not Reset After Send
- **Severity**: LOW
- **Steps**: Type long message, send, observe textarea
- **Expected**: Resets to single line
- **Actual**: Stays expanded
- **Root cause**: setInput('') doesn't trigger onChange resize

### BUG-008 — Coverage Bar Labels Show "undefined"
- **Severity**: LOW
- **Steps**: Inspect Coverage bar accessibility tree
- **Expected**: Band labels (High/Medium/Low)
- **Actual**: "undefined: 11 (0.4%)"

### BUG-009 — React Key Warning in CoverageBarFull
- **Severity**: LOW
- **Steps**: Open console on Coverage page
- **Actual**: "Each child in a list should have a unique key"

### BUG-010 — WebGL Error on Network Map (Headless)
- **Severity**: LOW (environment-specific)
- **Steps**: Load /network in headless browser
- **Actual**: TypeError on maxTextureDimension2D
- **Note**: Map still renders; only affects headless/CI environments

---

## 4. Data Integrity Findings

| Check | Result |
|-------|--------|
| Orphan imprints | 0 (PASS) |
| Orphan agents | 0 (PASS) |
| Orphan network agents | 0 (PASS) |
| Broken Wikipedia URLs | 0 (FIXED) |
| Date coverage >=0.9 | 97.9% (PASS) |
| Place coverage >=0.9 | 99.3% (PASS) |
| Publisher coverage >=0.8 | 98.8% (PASS) |
| All FK relationships valid | Yes (PASS) |

---

## 5. LLM Interaction Findings

- Query compilation via OpenAI works correctly
- Session state preserved across multi-turn conversations
- Hebrew input parsed and results returned correctly
- Clarification triggered for vague queries
- No streaming issues observed (using HTTP POST, not WebSocket)
- Response times: 4-20 seconds depending on query complexity

---

## 6. Recommended Fixes (Priority Order)

1. **HIGH**: Fix SPA routing in vite.config.ts (BUG-001) — affects all direct URL access
2. **HIGH**: Fix Coverage dashboard data mapping (BUG-002, BUG-003) — misleading quality metrics
3. **MEDIUM**: Fix Agent Chat coverage sidebar (BUG-004)
4. **LOW**: Deduplicate clarification message (BUG-006)
5. **LOW**: Reset textarea height after send (BUG-007)
6. **LOW**: Fix "undefined" bar labels (BUG-008)
7. **LOW**: Add React key props (BUG-009)

---

## 7. Coverage Gaps / Still Needs Testing

- WebSocket streaming (chat uses HTTP POST currently)
- Query Debugger with actual query execution
- Agent Chat with actual LLM agent interaction
- Workbench inline editing and correction submission
- Publisher authority CRUD operations
- Mobile/narrow viewport behavior
- Rate limiting behavior
- Concurrent user sessions
- Browser back/forward navigation within SPA
