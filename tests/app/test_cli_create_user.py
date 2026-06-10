"""Tests for the create-user CLI command's secret-safe password input (DL-1).

The admin password must not have to be passed on argv (visible in the process
list). --password-stdin reads it from stdin instead.
"""
from unittest.mock import patch

from typer.testing import CliRunner

from app.cli import app

runner = CliRunner()


def test_create_user_reads_password_from_stdin():
    """--password-stdin reads the password from stdin, not argv."""
    with patch("app.api.auth_db.init_auth_db"), patch(
        "app.api.auth_service.create_user", return_value=42
    ) as mock_create:
        result = runner.invoke(
            app,
            ["create-user", "alice", "--role", "admin", "--password-stdin"],
            input="Secret123\n",
        )
    assert result.exit_code == 0, result.output
    mock_create.assert_called_once_with("alice", "Secret123", "admin")


def test_create_user_errors_without_any_password():
    """No positional password and no --password-stdin is a usage error."""
    with patch("app.api.auth_db.init_auth_db"), patch(
        "app.api.auth_service.create_user"
    ) as mock_create:
        result = runner.invoke(app, ["create-user", "alice", "--role", "admin"])
    assert result.exit_code != 0
    mock_create.assert_not_called()


def test_create_user_positional_password_still_works():
    """Back-compat: positional password is still accepted (discouraged)."""
    with patch("app.api.auth_db.init_auth_db"), patch(
        "app.api.auth_service.create_user", return_value=7
    ) as mock_create:
        result = runner.invoke(
            app, ["create-user", "bob", "Secret123", "--role", "full"]
        )
    assert result.exit_code == 0, result.output
    mock_create.assert_called_once_with("bob", "Secret123", "full")
