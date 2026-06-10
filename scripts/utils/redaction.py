"""Secret redaction for data written to logs and persisted artifacts (DL-3).

A single, low-level redactor shared by the LLM logger (before prompts are
persisted to ``logs/llm_calls.jsonl``) and by ``app.api.security.validate_output``
(before LLM output is returned to the user). Lives under ``scripts/utils`` so both
the ``app`` and ``scripts`` layers can depend on it without a layering inversion.

Redacts secret-shaped substrings only. It is best-effort defense-in-depth, not a
guarantee — inputs that legitimately must carry a secret should never be logged.
"""
import re

# (pattern, replacement) pairs. Each pattern matches the sensitive substring;
# the replacement preserves enough surrounding structure to stay readable.
_REDACTIONS = [
    # OpenAI / Anthropic style API keys (sk-..., sk-ant-...).
    (re.compile(r"sk-[A-Za-z0-9._-]{20,}"), "[REDACTED]"),
    # Bearer tokens in Authorization headers.
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer [REDACTED]"),
    # Literal references to the JWT secret / a password hash column.
    (re.compile(r"(?i)jwt_secret"), "[REDACTED]"),
    (re.compile(r"(?i)password_hash"), "[REDACTED]"),
    # Credentials embedded in a connection/URL string: scheme://user:pass@host.
    (re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://)[^\s:/@]+:[^\s:/@]+@"), r"\1[REDACTED]@"),
]


def redact_secrets(text: str) -> str:
    """Return ``text`` with secret-shaped substrings replaced by ``[REDACTED]``."""
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text
