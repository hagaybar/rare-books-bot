# tests/scripts/feedback/test_github_client.py
import httpx
import pytest

from scripts.feedback.github_client import (
    FeedbackSyncDisabled, FeedbackSyncError, create_issue,
)


def test_missing_token_raises_disabled(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(FeedbackSyncDisabled):
        create_issue("t", "b", ["user-reported"])


def test_create_issue_success(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_dummy_token_for_test")

    def fake_post(url, **kwargs):
        assert url.endswith("/repos/owner/repo/issues")
        assert kwargs["json"]["labels"] == ["user-reported"]
        return httpx.Response(201, json={"html_url": "https://github.com/owner/repo/issues/7",
                                         "number": 7},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    url, number = create_issue("title", "body", ["user-reported"], repo="owner/repo")
    assert number == 7 and url.endswith("/7")


def test_http_error_raises_without_token_leak(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_supersecret123")

    def fake_post(url, **kwargs):
        return httpx.Response(401, json={"message": "Bad credentials"},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(FeedbackSyncError) as exc:
        create_issue("t", "b", [], repo="owner/repo")
    assert "ghp_supersecret123" not in str(exc.value)
