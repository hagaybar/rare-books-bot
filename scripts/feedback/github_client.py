"""Minimal GitHub issue creation for feedback sync.

GITHUB_TOKEN is read from the environment at call time and must never be
logged, echoed, or included in exception text.
"""
from __future__ import annotations

import os

import httpx

DEFAULT_REPO = "hagaybar/rare-books-bot"


class FeedbackSyncDisabled(Exception):
    """GITHUB_TOKEN not configured — reports stay pending."""


class FeedbackSyncError(Exception):
    """GitHub API call failed — reports stay pending."""


def create_issue(title: str, body: str, labels: list[str],
                 repo: str | None = None, timeout: float = 10.0) -> tuple[str, int]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise FeedbackSyncDisabled("GITHUB_TOKEN not set")
    repo = repo or os.environ.get("FEEDBACK_REPO", DEFAULT_REPO)
    resp = httpx.post(
        f"https://api.github.com/repos/{repo}/issues",
        json={"title": title, "body": body, "labels": labels},
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"},
        timeout=timeout,
    )
    if resp.status_code != 201:
        raise FeedbackSyncError(
            f"GitHub issue creation failed: HTTP {resp.status_code}")
    data = resp.json()
    return data["html_url"], data["number"]
