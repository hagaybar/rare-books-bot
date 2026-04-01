# Security Audit Report

**Date:** 2026-03-29
**Application:** Rare Books Discovery API (FastAPI + React)
**Backend:** http://localhost:8000
**Auditor:** Automated penetration test + code review
**Scope:** Authentication, authorization, injection attacks, CORS, session management, error handling

---

## Executive Summary

The application has a solid security foundation with proper JWT validation, parameterized SQL queries, role-based access control, brute-force lockout, and content moderation. However, several vulnerabilities were identified that should be addressed before production deployment.

**Findings:** 2 Critical, 2 High, 5 Medium, 3 Low

---

## Critical Findings

### C1. CORS Misconfiguration: Wildcard Origin with Credentials

**Severity:** CRITICAL
**Location:** `app/api/main.py`, lines 127-134
**CVSS Score:** 8.1

**Description:**
The CORS middleware defaults to `allow_origins=["*"]` when the `CORS_ORIGIN` environment variable is not set, while simultaneously enabling `allow_credentials=True`. When a browser sends a request from any origin (e.g., `http://evil.attacker.com`), the server reflects that origin in `Access-Control-Allow-Origin` and includes `Access-Control-Allow-Credentials: true`.

This allows an attacker to craft a malicious webpage that makes authenticated API calls on behalf of any logged-in user, stealing session data and performing actions with the user's privileges.

**Reproduction:**
```bash
curl -D- -H "Origin: http://evil.attacker.com" http://localhost:8000/health
# Response includes:
# access-control-allow-origin: http://evil.attacker.com
# access-control-allow-credentials: true
```

**Evidence:**
```
access-control-allow-origin: http://evil.attacker.com
access-control-allow-credentials: true
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
```

**Recommendation:**
- Set `CORS_ORIGIN` environment variable explicitly (e.g., `http://localhost:5174`).
- Change the default from `"*"` to an empty list or a safe default.
- When `allow_credentials=True`, never use wildcard `*` -- always enumerate allowed origins.

```python
# Fix: Replace default
_cors_origins = os.getenv("CORS_ORIGIN", "http://localhost:5174").split(",")
# Or better: raise an error if not set in production
```

---

### C2. Unauthenticated Session Access (IDOR)

**Severity:** CRITICAL
**Location:** `app/api/main.py`, lines 670-718
**CVSS Score:** 7.5

**Description:**
The `GET /sessions/{session_id}` and `DELETE /sessions/{session_id}` endpoints have no authentication dependency. Any unauthenticated user who knows or can guess a session ID can read the full conversation history (including user queries and assistant responses) or delete sessions belonging to other users.

Session IDs are UUIDs, but they are not cryptographically secret -- they may be leaked in logs, URLs, or error messages.

**Reproduction:**
```bash
# No authentication required
curl http://localhost:8000/sessions/0ad93e06-9976-4f69-8c6f-441db7dbf86f
# Returns: full session data including all messages
```

**Evidence:**
```
Status: 200
Leaked fields: ['session_id', 'user_id', 'created_at', 'updated_at', 'messages', 'context', 'metadata']
First message: {'role': 'user', 'content': 'Does this collection contain books on philosophy', ...}
```

**Recommendation:**
- Add `Depends(require_role("limited"))` to both endpoints.
- Add ownership check: verify `session.user_id == current_user.user_id` (or allow admin override).

```python
@app.get("/sessions/{session_id}")
async def get_session(session_id: str, user=Depends(require_role("limited"))):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if str(session.user_id) != str(user["user_id"]) and user["role"] != "admin":
        raise HTTPException(403, "Access denied")
    return session.model_dump()
```

---

## High Findings

### H1. Cleartext Password Logged in Audit Trail

**Severity:** HIGH
**Location:** `app/api/auth_routes.py`, line 191
**CVSS Score:** 6.5

**Description:**
When an admin updates a user's password via `PUT /auth/users/{user_id}`, the `body.model_dump(exclude_none=True)` output is written to the audit log, which includes the `new_password` field in cleartext.

Anyone with read access to the `audit_log` table (or database file) can recover plaintext passwords.

**Reproduction:**
```bash
# After updating a user's password:
sqlite3 data/auth/auth.db "SELECT details FROM audit_log WHERE action='user_updated' ORDER BY id DESC LIMIT 1;"
# Output: Updated user 4: {'new_password': 'NewPassword123!'}
```

**Recommendation:**
Exclude sensitive fields from audit log:
```python
audit_details = body.model_dump(exclude_none=True, exclude={"new_password"})
if body.new_password:
    audit_details["password_changed"] = True
audit_log("user_updated", ..., details=f"Updated user {user_id}: {audit_details}")
```

---

### H2. User Enumeration via Timing Side Channel

**Severity:** HIGH
**Location:** `app/api/auth_service.py`, lines 120-168
**CVSS Score:** 5.3

**Description:**
The `authenticate_user` function returns immediately when a username does not exist (no bcrypt comparison), but takes ~165ms when the user exists (bcrypt verification). This timing difference allows attackers to enumerate valid usernames.

**Reproduction:**
```
Existing user "admin": ~187ms average
Non-existing user: ~10ms average
Difference: ~178ms (easily measurable)
```

**Recommendation:**
Perform a dummy bcrypt comparison when the user does not exist:
```python
DUMMY_HASH = bcrypt.hash("dummy")  # Pre-computed at module load

def authenticate_user(username, password):
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user:
        bcrypt.verify(password, DUMMY_HASH)  # Constant-time rejection
        return None
    # ... rest of logic
```

---

## Medium Findings

### M1. Missing Secure Flag on Cookies

**Severity:** MEDIUM
**Location:** `app/api/auth_routes.py`, lines 18-22
**CVSS Score:** 4.8

**Description:**
Auth cookies (`access_token`, `refresh_token`) are set with `HttpOnly` and `SameSite=lax` but without the `Secure` flag. This means cookies will be transmitted over unencrypted HTTP connections, allowing network-level interception.

**Evidence:**
```
set-cookie: access_token=...; HttpOnly; Max-Age=900; Path=/; SameSite=lax
# Missing: Secure
```

**Recommendation:**
Add `secure=True` to `COOKIE_KWARGS` for production (or conditionally based on environment):
```python
COOKIE_KWARGS = {
    "httponly": True,
    "samesite": "lax",
    "secure": os.getenv("ENVIRONMENT", "production") != "development",
    "path": "/",
}
```

---

### M2. Internal Error Messages Leaked to Clients

**Severity:** MEDIUM
**Location:** `app/api/main.py`, lines 528-532 and 965-968
**CVSS Score:** 4.3

**Description:**
The catch-all exception handler in both the HTTP `/chat` endpoint and WebSocket `/ws/chat` endpoint returns `str(e)` to the client. This can leak internal implementation details such as file paths, database schema information, Python module names, and stack trace fragments.

**Evidence:**
```python
# HTTP endpoint (line 531)
error=f"Internal server error: {str(e)}"

# WebSocket endpoint (line 967)
"message": f"Internal error: {str(e)}"
```

**Recommendation:**
Return a generic error message to clients and log the details server-side:
```python
return ChatResponseAPI(
    success=False,
    response=None,
    error="Internal server error. Please try again later.",
)
```

---

### M3. Dead Code in Input Validation (Control Characters Not Cleaned)

**Severity:** MEDIUM
**Location:** `app/api/security.py`, lines 145-155
**CVSS Score:** 3.7

**Description:**
The `validate_input` function detects control characters and creates a `cleaned` variable, but never returns or uses it. The original uncleaned text (with null bytes, Unicode control characters, etc.) passes through to the LLM and database.

**Evidence:**
```python
cleaned = ''.join(c for c in text if c.isprintable() or c in '\n\t')
if cleaned != text:
    return True, None  # BUG: cleaned is never used, original text passes through
```

**Recommendation:**
Either reject input with control characters or return the cleaned version:
```python
if cleaned != text:
    # Option A: Reject
    return False, "Input contains invalid characters"
    # Option B: Replace text with cleaned version (requires API change)
```

---

### M4. Refresh Token Not Rotated on Use

**Severity:** MEDIUM
**Location:** `app/api/auth_routes.py`, lines 54-65
**CVSS Score:** 4.0

**Description:**
When a refresh token is used at `POST /auth/refresh`, a new access token is issued but the same refresh token remains valid. This means a stolen refresh token can be used repeatedly for the full 7-day lifetime without the legitimate user being aware.

Industry best practice is to rotate refresh tokens on each use (issue a new one and invalidate the old one).

**Recommendation:**
Implement refresh token rotation:
```python
@router.post("/refresh")
async def refresh(request, response):
    old_token = request.cookies.get("refresh_token")
    user = validate_refresh_token(old_token)
    # Revoke old token
    revoke_single_refresh_token(old_token)
    # Issue new refresh token
    new_refresh = create_refresh_token(user["user_id"])
    # Issue new access token
    access_token = create_access_token(...)
    _set_auth_cookies(response, access_token, new_refresh)
```

---

### M5. Moderation Check Fails Open

**Severity:** MEDIUM
**Location:** `app/api/security.py`, lines 82-108
**CVSS Score:** 3.5

**Description:**
The `check_moderation` function returns `(True, None)` (allowing content through) when:
1. No `OPENAI_API_KEY` is set
2. The moderation API returns a non-200 status
3. Any exception occurs (timeout, network error, etc.)

This means an attacker could potentially bypass moderation by causing the API call to fail (e.g., via slowloris, DNS poisoning, or if the OpenAI API is temporarily down).

**Recommendation:**
Consider fail-closed for production, or at least log when moderation is bypassed:
```python
except Exception as e:
    logger.warning("Moderation check failed, allowing content through: %s", e)
    # For production, consider: return False, "moderation_unavailable"
    return True, None
```

---

## Low Findings

### L1. JWT Secret Auto-Generated in Development

**Severity:** LOW
**Location:** `app/api/auth_service.py`, lines 20-24
**CVSS Score:** 2.1

**Description:**
When `JWT_SECRET` is not set, a random secret is auto-generated. While a warning is printed, this means all sessions are invalidated on server restart. This is acceptable for development but could cause confusion in staging/production.

**Recommendation:**
Consider refusing to start without `JWT_SECRET` in production mode:
```python
if not JWT_SECRET:
    if os.getenv("ENVIRONMENT") == "production":
        raise ValueError("JWT_SECRET must be set in production")
    JWT_SECRET = secrets.token_hex(32)
```

---

### L2. No Rate Limiting on Auth Endpoints

**Severity:** LOW
**Location:** `app/api/auth_routes.py`
**CVSS Score:** 2.5

**Description:**
While the `/chat` endpoint has rate limiting (30/minute) and brute force protection locks accounts after 5 failed attempts, the login endpoint itself has no rate limit. An attacker can rapidly probe different usernames without hitting a rate limit (only account lockout per username).

**Recommendation:**
Add IP-based rate limiting to the login endpoint:
```python
@router.post("/login")
@limiter.limit("10/minute")
async def login(...):
```

---

### L3. Audit Log Contains Query Text

**Severity:** LOW (informational)
**Location:** `app/api/main.py`, line 511
**CVSS Score:** 1.5

**Description:**
User queries are stored in the audit log (truncated to 200 chars). While useful for debugging, this could be a privacy concern if users submit sensitive queries. The PII masking in `mask_pii` only catches emails and phone numbers -- other PII patterns (SSN, addresses, etc.) would be preserved.

**Recommendation:**
Consider whether query text needs to be in the audit log, or if a hash/session reference would suffice.

---

## Passed Checks

| Check | Result | Details |
|-------|--------|---------|
| JWT Algorithm Confusion ("none") | PASS | PyJWT 2.12.1 correctly rejects `alg: none` when `algorithms=["HS256"]` |
| JWT Forged Signature | PASS | Forged tokens are rejected |
| JWT Expired Token | PASS | Expired tokens are rejected |
| SQL Injection (Auth Login) | PASS | Username/password use parameterized queries |
| SQL Injection (Diagnostics Table) | PASS | Table name validated against ALLOWED_TABLES allowlist |
| SQL Injection (Diagnostics Search) | PASS | Search uses parameterized LIKE queries |
| SQL Injection (Network Map) | PASS | Connection types validated against VALID_CONNECTION_TYPES |
| SQL Injection (Metadata Issues) | PASS | Field validated via MetadataField enum; column names from hardcoded map |
| SQL Injection (Metadata Search) | PASS | Search uses parameterized queries via `_build_enrichment_where` |
| Role Escalation (Limited -> Admin) | PASS | `require_role` dependency correctly enforces hierarchy |
| Role Escalation (Guest -> Limited) | PASS | Guest cannot access /chat or /chat/history |
| Role Escalation (Limited -> Full) | PASS | Limited cannot access /diagnostics or /metadata (non-enrichment) |
| Brute Force Lockout | PASS | Account locks after 5 failed attempts for 15 minutes |
| Account Lockout Bypass | PASS | Correct password rejected while account is locked |
| Password Hashing | PASS | bcrypt with proper rounds |
| Timing Attack (Password) | PASS | bcrypt comparison is constant-time |
| Prompt Injection | PASS | LLM stayed in character, did not leak system prompt or API key |
| XSS (Script Tag) | PASS | Script tags not reflected in responses |
| Output Validation | PASS | API keys, JWT_SECRET, password_hash patterns are redacted |
| Input Length Validation | PASS | Messages > 1000 chars rejected |
| WebSocket Auth | PASS | Unauthenticated WebSocket connections rejected |
| Refresh Token Revocation | PASS | Refresh tokens properly revoked on logout |
| Session Store Unavailable | PASS | Returns 503 when session store not initialized |
| Database Not Found | PASS | Returns 503 with appropriate message |
| Metadata Middleware Auth | PASS | Correctly enforces role per path prefix |

---

## Risk Assessment

| Category | Rating | Notes |
|----------|--------|-------|
| Authentication | Good | Solid JWT + bcrypt, lockout works. Fix timing side channel. |
| Authorization | Good | Role hierarchy is properly enforced. Fix session endpoint auth. |
| Injection (SQL) | Excellent | All queries use parameterized statements or validated allowlists. |
| Injection (Prompt) | Good | LLM stayed in character during testing. Output validation present. |
| CORS | Critical | Wildcard origin with credentials is exploitable from any website. |
| Session Security | Medium | Sessions accessible without auth. No refresh token rotation. |
| Error Handling | Medium | Internal errors leak to clients. |
| Cookie Security | Medium | Missing Secure flag. |

**Overall Risk: MEDIUM-HIGH** -- The CORS misconfiguration and unauthenticated session endpoints are the primary concerns. SQL injection protection is excellent throughout.

---

## Remediation Priority

1. **Immediate (before any external access):** Fix CORS configuration (C1)
2. **Immediate:** Add auth to session endpoints (C2)
3. **Short-term:** Remove password from audit log (H1), fix timing side channel (H2)
4. **Medium-term:** Add Secure flag to cookies (M1), fix error message leakage (M2), fix input validation (M3)
5. **Backlog:** Refresh token rotation (M4), moderation fail-closed (M5), rate limiting on auth (L2)
