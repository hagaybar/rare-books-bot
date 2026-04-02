"""Shared fixtures for app-level tests.

Provides auth helpers so that test clients pass JWT authentication.
"""
import pytest

from app.api.auth_service import create_access_token


def make_test_token(role: str = "admin", user_id: int = 1, username: str = "testadmin") -> str:
    """Generate a valid JWT access token for testing.

    Uses the same secret/algorithm as auth_service so tokens validate correctly.
    Default role is 'admin' to pass all role checks.
    """
    return create_access_token(user_id=user_id, username=username, role=role)


@pytest.fixture()
def auth_cookies() -> dict[str, str]:
    """Return a cookies dict with a valid admin JWT for test requests."""
    return {"access_token": make_test_token()}
