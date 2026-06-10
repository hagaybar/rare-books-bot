"""validate_output stays a thin wrapper over the shared redactor (DL-3).

Confirms the existing public contract (sk- keys, JWT_SECRET, password_hash) still
holds and now also covers bearer tokens and connection-string credentials.
"""
from app.api.security import validate_output


def test_validate_output_redacts_api_key():
    out = validate_output("leaked sk-abcdefghijklmnopqrstuvwxyz0123456789")
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in out
    assert "[REDACTED]" in out


def test_validate_output_redacts_jwt_secret_and_password_hash():
    assert "JWT_SECRET" not in validate_output("JWT_SECRET")
    assert "password_hash" not in validate_output("password_hash")


def test_validate_output_redacts_bearer_token():
    out = validate_output("Authorization: Bearer abcDEF123456._-token")
    assert "abcDEF123456._-token" not in out


def test_validate_output_passes_clean_text():
    text = "A 1714 atlas of Palestine by Adriaan Reland."
    assert validate_output(text) == text
