"""Tests for scripts.utils.redaction.redact_secrets (DL-3).

Verifies secret-shaped substrings are redacted before persistence: API keys,
bearer tokens, JWT secret references, password_hash references, and credentials
embedded in connection/URL strings.
"""
from scripts.utils.redaction import redact_secrets


def test_redacts_openai_style_api_key():
    text = "key is sk-abcdefghijklmnopqrstuvwxyz0123456789 end"
    out = redact_secrets(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in out
    assert "[REDACTED]" in out


def test_redacts_bearer_token():
    text = "Authorization: Bearer abcDEF123456._-token"
    out = redact_secrets(text)
    assert "abcDEF123456._-token" not in out
    assert "[REDACTED]" in out


def test_redacts_jwt_secret_reference():
    assert "[REDACTED]" in redact_secrets("the JWT_SECRET env var")
    assert "JWT_SECRET" not in redact_secrets("JWT_SECRET")


def test_redacts_password_hash_reference():
    assert "password_hash" not in redact_secrets("row.password_hash value")


def test_redacts_credentials_in_connection_string():
    text = "postgres://admin:s3cretPass@db.internal:5432/app"
    out = redact_secrets(text)
    assert "admin:s3cretPass" not in out
    assert "[REDACTED]" in out
    # host/scheme remain so the string is still recognizable as a conn string
    assert out.startswith("postgres://")


def test_leaves_ordinary_text_untouched():
    text = "Find books about cartography printed in Amsterdam in 1714."
    assert redact_secrets(text) == text
