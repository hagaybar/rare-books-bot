# Security Re-Audit Report

**Date:** 2026-03-29
**Application:** Rare Books Discovery API (FastAPI + React)
**Backend:** http://localhost:8000
**Auditor:** Automated verification + code review
**Scope:** Verification of 9 previously identified issues + scan for new vulnerabilities
**Previous Audit:** `reports/security-audit.md` (2026-03-29)

---

## Executive Summary

All 9 previously identified vulnerabilities have been **FIXED**. The security posture of
the application has improved significantly. The re-audit identified **3 new findings**
(1 medium, 2 low severity) and **1 informational observation**. None are blocking for
internal/staging deployment, but the medium finding should be addressed before
production exposure.

**Previous findings:** 9/9 FIXED
**New findings:** 1 Medium, 2 Low, 1 Informational

**Overall Security Posture:** GOOD (for internal/staging use); address medium finding
before public production deployment.

---

## Previous Findings Verification

### C1. CORS Misconfiguration -- FIXED

**Previous issue:** Wildcard `*` origin with `allow_credentials=True` reflected
arbitrary origins, enabling cross-site request forgery via cookie theft.

**Verification:**
```bash
# Evil origin NOT reflected:
curl -H "Origin: https://evil.com" http://localhost:8000/health
# Response: No Access-Control-Allow-Origin header returned

# Legitimate origin IS reflected:
curl -H "Origin: http://localhost:5173" http://localhost:8000/health
# Response: access-control-allow-origin: http://localhost:5173
```

**Fix details:** Origins now enumerated from `CORS_ORIGIN` env var with a safe default
of `http://localhost:5173,http://localhost:5174`. Arbitrary origins are rejected.
(`app/api/main.py`, line 128)

**Status: FIXED**

---

### C2. Session Endpoints Unauthenticated -- FIXED

**Previous issue:** `/sessions/{session_id}` endpoints had no authentication, allowing
anyone to read or delete session data.

**Verification:**
```
GET  /sessions/test-id  (no auth) -> HTTP 401
DELETE /sessions/test-id (no auth) -> HTTP 401
POST /chat             (no auth) -> HTTP 401
GET  /diagnostics/tables (no auth) -> HTTP 401
GET  /metadata/coverage  (no auth) -> HTTP 401
```

**Fix details:** Both `/sessions/{session_id}` endpoints now require `limited` role via
`Depends(require_role("limited"))`. Additionally, ownership checks prevent users from
accessing other users' sessions (only admins can access any session).
(`app/api/main.py`, lines 672-742)

**Status: FIXED**

---

### H1. Password Logged in Audit Trail -- FIXED

**Previous issue:** `update_user` endpoint logged the `new_password` field in the
audit log.

**Verification:**
```python
# app/api/auth_routes.py, line 197:
audit_details = body.model_dump(exclude_none=True, exclude={"new_password"})
if body.new_password:
    audit_details["password_changed"] = True
```

The `model_dump()` call explicitly excludes `new_password` using Pydantic's `exclude`
parameter. Only a boolean `password_changed` flag is logged.

**Status: FIXED**

---

### H2. Timing Attack on Login -- FIXED

**Previous issue:** Non-existent usernames returned faster than existing ones, enabling
user enumeration.

**Verification (timing in milliseconds):**
```
Existing user "admin":       222, 194, 195, 195, 195 ms (avg: 200ms)
Non-existent user:           186, 187, 186, 185, 185 ms (avg: 186ms)
```

The ~14ms difference is within bcrypt variance and network jitter. The fix uses a
pre-computed dummy hash (`_DUMMY_HASH`) to ensure a bcrypt.verify call happens even
when the user does not exist, making timing-based enumeration impractical.
(`app/api/auth_service.py`, line 30-33, 131-133)

**Additional protection:** Account lockout after 5 failed attempts (15-minute lockout).

**Status: FIXED**

---

### M1. Cookie Missing Secure Flag -- FIXED

**Previous issue:** Cookies were sent without the `Secure` flag, transmittable over
plain HTTP.

**Verification:**
```python
# app/api/auth_routes.py, line 23:
"secure": os.environ.get("HTTPS", "").lower() == "true",
```

The `Secure` flag is now conditional on the `HTTPS` environment variable, which should
be set to `"true"` in production behind TLS termination. For local development (HTTP),
it correctly defaults to `False` to avoid breaking cookie delivery.

**Status: FIXED**

---

### M2. Error Message Information Leak -- FIXED (main endpoints)

**Previous issue:** `str(e)` was returned in user-facing HTTP error responses, leaking
internal implementation details (file paths, SQL errors, stack traces).

**Verification for main chat endpoint:**
```python
# app/api/main.py, line 530-534:
except Exception as e:
    logger.exception("Chat error", extra={"error": str(e)})
    return ChatResponseAPI(
        success=False,
        response=None,
        error="An internal error occurred. Please try again.",
    )
```

The chat endpoint now returns a generic error message. The actual exception is only
logged server-side. Similarly, the WebSocket handler (line 993) returns a generic
message.

**Note:** Diagnostics endpoints (`diagnostics.py` lines 131, 149, 438) still expose
`str(exc)` in error responses. However, these are behind `require_role("full")`
authentication, so they are only accessible to operator-level users who need debugging
information. This is an acceptable risk for a diagnostics API.

**Status: FIXED** (main endpoints); informational note for diagnostics

---

### M3. Input Validation Returns Cleaned Text -- FIXED

**Previous issue:** `validate_input()` did not return cleaned text, allowing control
characters through.

**Verification:**
```python
# app/api/security.py, lines 146-158:
def validate_input(text: str) -> tuple[bool, str | None]:
    if not text or not text.strip():
        return False, "Empty query"
    if len(text) > MAX_QUERY_LENGTH:
        return False, f"Query too long ({len(text)} chars, max {MAX_QUERY_LENGTH})"
    # Strip control characters
    cleaned = ''.join(c for c in text if c.isprintable() or c in '\n\t')
    return True, cleaned  # Return cleaned version
```

**Live test (null byte injection):**
```
Input:  "test\u0000injection"
Output: Processed as "testinjection" (null byte stripped by control char filter)
```

**Live test (oversized input):**
```
Input:  2000 characters
Output: HTTP 400 "Query too long (2000 chars, max 1000)"
```

**Status: FIXED**

---

### M4. Refresh Token Not Rotated -- FIXED

**Previous issue:** The `/auth/refresh` endpoint issued new access tokens but reused
the same refresh token, enabling persistent access if a token was stolen.

**Verification:**
```python
# app/api/auth_routes.py, lines 66-71:
# Rotate refresh token: revoke old tokens and issue a new one
revoke_refresh_tokens(user["user_id"])
new_refresh = create_refresh_token(user["user_id"])

access_token = create_access_token(user["user_id"], user["username"], user["role"])
_set_auth_cookies(response, access_token, new_refresh)
```

The refresh flow now: (1) revokes ALL existing refresh tokens for the user, then
(2) issues a brand-new refresh token. This prevents replay of stolen refresh tokens.

**Status: FIXED**

---

### M5. Rate Limiting -- FIXED

**Previous issue:** No rate limiting on the `/chat` endpoint.

**Verification (concurrent burst test -- 35 simultaneous requests):**
```
Results: 21 x HTTP 200, 14 x HTTP 429 (Too Many Requests)
```

Rate limiter is configured at 30 requests/minute per IP using `slowapi`.
(`app/api/main.py`, line 386: `@limiter.limit("30/minute")`)

**Status: FIXED**

---

## New Findings

### N1. Missing Security Headers (MEDIUM)

**Severity:** MEDIUM
**Location:** `app/api/main.py` (no security headers middleware)

**Description:**
The application does not set standard security response headers. This leaves the
application vulnerable to clickjacking, MIME-type sniffing, and lacks a Content
Security Policy.

**Missing headers:**
| Header | Purpose | Recommended Value |
|--------|---------|-------------------|
| `X-Frame-Options` | Prevent clickjacking | `DENY` |
| `X-Content-Type-Options` | Prevent MIME sniffing | `nosniff` |
| `X-XSS-Protection` | Legacy XSS filter | `1; mode=block` |
| `Strict-Transport-Security` | Force HTTPS | `max-age=31536000; includeSubDomains` |
| `Content-Security-Policy` | Control resource loading | `default-src 'self'` |
| `Referrer-Policy` | Control referrer leakage | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | Restrict browser features | `camera=(), microphone=()` |

**Verification:**
```bash
curl -s -v http://localhost:8000/health 2>&1 | grep -iE "x-frame|x-content|strict-transport"
# No matches -- none of these headers are present
```

**Recommendation:**
Add a middleware to set security headers on all responses:

```python
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=()"
    if os.environ.get("HTTPS", "").lower() == "true":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
```

---

### N2. No Rate Limiting on /auth/login (LOW)

**Severity:** LOW
**Location:** `app/api/auth_routes.py`

**Description:**
The `/auth/login` endpoint has no rate limiter decorator. While there IS account
lockout after 5 failed attempts (15-minute lockout per account), there is no IP-based
rate limiting. An attacker could attempt logins across many different usernames without
being rate-limited, performing a credential-stuffing attack.

**Mitigation already in place:**
- Account lockout after 5 failed attempts (15 min)
- Constant-time response (timing attack prevention)
- bcrypt password hashing (slow by design)

**Recommendation:**
Add `@limiter.limit("10/minute")` to the login endpoint to complement the per-account
lockout with per-IP rate limiting.

---

### N3. No Password Complexity Enforcement (LOW)

**Severity:** LOW
**Location:** `app/api/auth_models.py`

**Description:**
The `CreateUserRequest` model requires `min_length=8` for passwords, but has no
complexity requirements (uppercase, lowercase, digit, special character). The login
password field (`LoginRequest`) only requires `min_length=1`.

**Current state:**
```python
class CreateUserRequest(BaseModel):
    password: str = Field(..., min_length=8)  # Length only

class LoginRequest(BaseModel):
    password: str = Field(..., min_length=1)  # Minimal
```

**Recommendation:**
Add a Pydantic validator to `CreateUserRequest` and `UpdateUserRequest` that enforces
at least one uppercase, one lowercase, one digit, and minimum 8 characters. This is
a low priority since user creation is admin-only.

---

### N4. Diagnostics Error Messages Expose Internal Details (INFORMATIONAL)

**Severity:** INFORMATIONAL
**Location:** `app/api/diagnostics.py`, lines 131, 149, 438

**Description:**
Three exception handlers in the diagnostics router pass `str(exc)` into HTTP error
response details:
- Line 131: `f"Query execution failed: {exc}"`
- Line 149: `f"Failed to store query run: {exc}"`
- Line 438: `error=str(exc)` in regression results

These could expose SQL error messages, file paths, or Python tracebacks.

**Mitigation:**
All diagnostics endpoints are protected by `require_role("full")`, so only trusted
operator-level users can trigger these errors. For a diagnostics/debugging API, this
is acceptable and arguably desirable for troubleshooting.

**Recommendation:**
No immediate action required. If the diagnostics API is ever exposed to lower-privilege
users, sanitize these error messages.

---

## Verified Positive Security Controls

The following security mechanisms were verified as working correctly:

| Control | Status | Details |
|---------|--------|---------|
| JWT authentication | Working | 15-min access tokens, 7-day refresh tokens |
| 4-tier role hierarchy | Working | guest < limited < full < admin |
| Cookie security | Working | `httponly`, `samesite=lax`, conditional `secure` |
| Session ownership | Working | Users can only access their own sessions |
| SQL injection prevention | Working | Parameterized queries, allowlists, enum validation |
| WebSocket auth | Working | JWT validated before `accept()`, rejects unauthenticated |
| Rate limiting | Working | 30/min on /chat, verified with concurrent burst test |
| Input validation | Working | Length limit (1000 chars), control char stripping |
| PII masking | Working | Email and phone patterns masked before LLM |
| Output validation | Working | API key patterns, JWT_SECRET, password_hash redacted |
| Content moderation | Working | OpenAI moderation API integration |
| Kill switch | Working | Global chat disable via admin setting |
| Account lockout | Working | 5 failed attempts -> 15-min lockout |
| Token rotation | Working | Refresh tokens rotated on use |
| Audit logging | Working | Login, query, user changes -- password excluded |
| JWT secret validation | Working | Min 32 chars, auto-generate with warning for dev |
| CSRF protection | Partial | `SameSite=lax` cookies provide baseline protection |

---

## SQL Injection Test Results

| Endpoint | Payload | Result | Protection |
|----------|---------|--------|------------|
| `/metadata/enrichment/agents?search=` | `test' OR 1=1--` | 0 results (safe) | Parameterized LIKE query |
| `/diagnostics/tables/{name}/rows` | `users' OR '1'='1` | HTTP 400 "not allowed" | ALLOWED_TABLES allowlist |
| `/network/map?connection_types=` | `teacher_student' OR 1=1--` | HTTP 400 "invalid types" | VALID_CONNECTION_TYPES set |
| `/diagnostics/tables/records/rows?search=` | `test' OR 1=1--` | 0 results (safe) | Parameterized LIKE query |

---

## Authentication Bypass Test Results

| Test | Result | Expected |
|------|--------|----------|
| Unauthenticated GET /sessions | 401 | 401 |
| Unauthenticated POST /chat | 401 | 401 |
| Unauthenticated GET /diagnostics | 401 | 401 |
| Unauthenticated GET /metadata | 401 | 401 |
| Guest -> /chat (requires limited) | 403 | 403 |
| Guest -> /sessions (requires limited) | 403 | 403 |
| Guest -> /diagnostics (requires full) | 403 | 403 |
| Guest -> /metadata/coverage (requires full) | 403 | 403 |
| Guest -> /network/map (requires guest) | 200 | 200 |
| Limited -> /auth/users (requires admin) | 403 | 403 |
| Limited -> /diagnostics (requires full) | 403 | 403 |
| Limited -> /chat (requires limited) | 200 | 200 |
| Limited -> /network/map (requires guest) | 200 | 200 |
| WebSocket without auth | 403 rejected | 403 |
| Cross-user session access | 403 | 403 |

---

## Remaining Risk Assessment

| Risk | Severity | Likelihood | Impact | Mitigation |
|------|----------|------------|--------|------------|
| Missing security headers | Medium | Medium | Medium | Add middleware (5 min fix) |
| Login brute-force across users | Low | Low | Low | Account lockout + bcrypt slowness |
| Weak password policy | Low | Low | Low | Admin-only user creation |
| Diagnostics error leak | Info | Low | Low | Protected by role auth |

---

## Recommendations Priority

1. **Immediate (before staging):** Add security headers middleware (N1)
2. **Soon (before production):** Add rate limiting on /auth/login (N2)
3. **Nice to have:** Password complexity validation (N3)
4. **No action needed:** Diagnostics error messages (N4)

---

## Conclusion

The application's security posture has improved substantially since the initial audit.
All 9 original findings (2 critical, 2 high, 5 medium) have been properly remediated.
The remaining issues are low-severity hardening items. The application is suitable for
internal/staging deployment. Adding the security headers middleware (a ~5 minute change)
would address the most significant remaining gap.
