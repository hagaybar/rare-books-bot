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
