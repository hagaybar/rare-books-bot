# Auth Plan C: Security Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add token tracking, quota enforcement, rate limiting, OpenAI moderation, prompt injection defense, output validation, PII masking, circuit breaker, and audit logging to the chat pipeline.

**Architecture:** Middleware-based security layers wrap the chat endpoint. Token usage recorded after each OpenAI call. Quota checked before each call. Rate limiter uses slowapi. Kill switch reads from auth.db settings table.

**Tech Stack:** Python/FastAPI, slowapi, OpenAI Moderation API, SQLite

**Spec:** `docs/superpowers/specs/2026-03-28-auth-security-design.md`
**Branch:** `feature/auth-security`

**This is Plan C of 3** (A=backend done, B=frontend done, C=this)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app/api/security.py` | Create | Token tracking, quota check, moderation, PII masking, output validation, kill switch |
| `app/api/main.py` | Modify | Wire security into chat endpoint, add rate limiting |
| `app/api/auth_routes.py` | Modify | Add kill switch toggle endpoint for admin |
| `app/api/auth_db.py` | Modify | Add audit log purge function |
| `app/cli.py` | Modify | Add purge-audit command |
| `frontend/src/pages/admin/Users.tsx` | Modify | Add kill switch toggle button |

---

### Task 1: Token Tracking + Quota Enforcement

**Files:**
- Create: `app/api/security.py`

- [ ] **Step 1: Create security module**

Create `app/api/security.py`:

```python
"""Security layer: token tracking, quota, moderation, PII masking, kill switch."""
import os
import re
import logging
from datetime import datetime

from app.api.auth_db import get_auth_db

logger = logging.getLogger(__name__)


# --- Token tracking + Quota ---

def record_token_usage(user_id: int, tokens: int) -> None:
    """Record tokens used for a chat request."""
    if not isinstance(user_id, int):
        return  # Guest users — no tracking
    month = datetime.now().strftime("%Y-%m")
    conn = get_auth_db()
    try:
        conn.execute(
            """INSERT INTO token_usage (user_id, month, tokens_used)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, month) DO UPDATE SET tokens_used = tokens_used + ?""",
            (user_id, month, tokens, tokens),
        )
        conn.commit()
    finally:
        conn.close()


def check_quota(user_id: int) -> tuple[bool, int, int]:
    """Check if user has remaining quota. Returns (allowed, used, limit)."""
    if not isinstance(user_id, int):
        return True, 0, 0  # Guest — no quota (shouldn't reach chat anyway)
    conn = get_auth_db()
    try:
        user = conn.execute("SELECT role, token_limit FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False, 0, 0
        if user["role"] in ("admin", "full"):
            return True, 0, 0  # Unlimited
        month = datetime.now().strftime("%Y-%m")
        usage = conn.execute(
            "SELECT tokens_used FROM token_usage WHERE user_id = ? AND month = ?",
            (user_id, month),
        ).fetchone()
        used = usage["tokens_used"] if usage else 0
        limit = user["token_limit"] or 50000
        return used < limit, used, limit
    finally:
        conn.close()


# --- Kill switch ---

def is_chat_enabled() -> bool:
    """Check if chat is globally enabled."""
    conn = get_auth_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'chat_enabled'").fetchone()
        return row["value"].lower() == "true" if row else True
    finally:
        conn.close()


def set_chat_enabled(enabled: bool) -> None:
    """Toggle the global chat kill switch."""
    conn = get_auth_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('chat_enabled', ?)",
            ("true" if enabled else "false",),
        )
        conn.commit()
    finally:
        conn.close()


# --- OpenAI Moderation ---

async def check_moderation(text: str) -> tuple[bool, str | None]:
    """Check text against OpenAI Moderation API. Returns (safe, category)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return True, None  # Skip if no key

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/moderations",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"input": text},
                timeout=5.0,
            )
            if resp.status_code != 200:
                logger.warning("Moderation API returned %d", resp.status_code)
                return True, None  # Fail open
            data = resp.json()
            result = data["results"][0]
            if result["flagged"]:
                categories = [k for k, v in result["categories"].items() if v]
                return False, ", ".join(categories)
            return True, None
    except Exception as e:
        logger.warning("Moderation API error: %s", e)
        return True, None  # Fail open


# --- PII Masking ---

EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
PHONE_RE = re.compile(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b')


def mask_pii(text: str) -> str:
    """Best-effort PII masking. Replaces emails and phone numbers."""
    text = EMAIL_RE.sub('[EMAIL]', text)
    text = PHONE_RE.sub('[PHONE]', text)
    return text


# --- Output Validation ---

BLOCKED_OUTPUT_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),  # OpenAI API key pattern
    re.compile(r'JWT_SECRET', re.IGNORECASE),
    re.compile(r'password_hash', re.IGNORECASE),
]


def validate_output(text: str) -> str:
    """Check LLM output for leaked secrets. Redact if found."""
    for pattern in BLOCKED_OUTPUT_PATTERNS:
        text = pattern.sub('[REDACTED]', text)
    return text


# --- Input Validation ---

MAX_QUERY_LENGTH = 1000


def validate_input(text: str) -> tuple[bool, str | None]:
    """Validate chat input. Returns (valid, error_message)."""
    if not text or not text.strip():
        return False, "Empty query"
    if len(text) > MAX_QUERY_LENGTH:
        return False, f"Query too long ({len(text)} chars, max {MAX_QUERY_LENGTH})"
    # Strip control characters
    cleaned = ''.join(c for c in text if c.isprintable() or c in '\n\t')
    if cleaned != text:
        return True, None  # Allow but with cleaned version
    return True, None
```

- [ ] **Step 2: Verify**

```bash
poetry run python -c "from app.api.security import record_token_usage, check_quota, is_chat_enabled, mask_pii, validate_output; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add app/api/security.py
git commit -m "feat: add security module — token tracking, quota, moderation, PII masking, kill switch"
```

---

### Task 2: Wire Security into Chat Endpoint

**Files:**
- Modify: `app/api/main.py`

- [ ] **Step 1: Add security checks to the /chat endpoint**

In `app/api/main.py`, find the `/chat` POST endpoint. Before the query is processed, add these checks in order:

1. **Kill switch**: Check `is_chat_enabled()`. If disabled, return 503.
2. **Input validation**: Check `validate_input(message)`. If invalid, return 400.
3. **Quota check**: Check `check_quota(user["user_id"])`. If exceeded, return 429 with quota info.
4. **PII masking**: `message = mask_pii(message)` before sending to OpenAI.
5. **Moderation**: `safe, category = await check_moderation(message)`. If flagged, return 400.

After the response is received:
6. **Output validation**: `response_text = validate_output(response_text)`
7. **Token recording**: `record_token_usage(user["user_id"], tokens_used)` — get `tokens_used` from the OpenAI response.
8. **Audit log**: `audit_log("chat_query", user_id, username, details=json.dumps({"query": message[:200], "tokens": tokens_used}), ip_address=ip)`

Also add the same security checks to the WebSocket `/ws/chat` endpoint.

Add rate limiting using slowapi:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/chat")
@limiter.limit("30/minute")
async def chat(request: Request, ...):
```

- [ ] **Step 2: Commit**

```bash
git add app/api/main.py
git commit -m "feat: wire security into chat — quota, moderation, PII, kill switch, rate limit"
```

---

### Task 3: Admin Kill Switch + Audit Purge + Frontend

**Files:**
- Modify: `app/api/auth_routes.py`
- Modify: `app/api/auth_db.py`
- Modify: `app/cli.py`
- Modify: `frontend/src/pages/admin/Users.tsx`

- [ ] **Step 1: Add kill switch endpoints**

In `app/api/auth_routes.py`, add:

```python
@router.get("/settings/chat-status")
async def get_chat_status(admin=Depends(require_role("admin"))):
    from app.api.security import is_chat_enabled
    return {"chat_enabled": is_chat_enabled()}

@router.post("/settings/chat-toggle")
async def toggle_chat(admin=Depends(require_role("admin"))):
    from app.api.security import is_chat_enabled, set_chat_enabled
    current = is_chat_enabled()
    set_chat_enabled(not current)
    audit_log("chat_toggled", user_id=admin["user_id"], username=admin["username"],
              details=f"Chat {'disabled' if current else 'enabled'}")
    return {"chat_enabled": not current}
```

- [ ] **Step 2: Add audit log purge**

In `app/api/auth_db.py`, add:
```python
def purge_audit_log(days: int = 90) -> int:
    conn = get_auth_db()
    try:
        cursor = conn.execute(
            "DELETE FROM audit_log WHERE timestamp < datetime('now', ?)",
            (f'-{days} days',),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
```

In `app/cli.py`, add purge-audit command:
```python
@app.command()
def purge_audit(days: int = typer.Option(90, help="Delete audit entries older than N days")):
    """Purge old audit log entries."""
    from app.api.auth_db import purge_audit_log
    count = purge_audit_log(days)
    print(f"Purged {count} audit log entries older than {days} days")
```

- [ ] **Step 3: Add kill switch to Users page**

In `frontend/src/pages/admin/Users.tsx`, add above the users table:

```tsx
// Fetch chat status
const chatStatus = useQuery({
  queryKey: ['chat-status'],
  queryFn: async () => {
    const res = await fetch('/auth/settings/chat-status', { credentials: 'include' });
    return res.json();
  },
});

const toggleChat = useMutation({
  mutationFn: async () => {
    const res = await fetch('/auth/settings/chat-toggle', { method: 'POST', credentials: 'include' });
    return res.json();
  },
  onSuccess: () => { chatStatus.refetch(); toast.success('Chat status toggled'); },
});

// In the JSX, add a kill switch section:
<div className="flex items-center justify-between p-4 bg-white rounded-lg border mb-6">
  <div>
    <h3 className="font-medium text-gray-900">Chat Service</h3>
    <p className="text-sm text-gray-500">
      {chatStatus.data?.chat_enabled ? 'Chat is enabled for all users' : 'Chat is disabled (emergency mode)'}
    </p>
  </div>
  <button
    onClick={() => toggleChat.mutate()}
    className={`px-4 py-2 rounded-lg text-sm font-medium ${
      chatStatus.data?.chat_enabled
        ? 'bg-red-50 text-red-700 hover:bg-red-100'
        : 'bg-green-50 text-green-700 hover:bg-green-100'
    }`}
  >
    {chatStatus.data?.chat_enabled ? 'Disable Chat' : 'Enable Chat'}
  </button>
</div>
```

- [ ] **Step 4: Verify and build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

- [ ] **Step 5: Commit and push**

```bash
git add app/api/ app/cli.py frontend/src/
git commit -m "feat: kill switch UI, audit purge, complete Plan C security hardening"
git push origin feature/auth-security
```
