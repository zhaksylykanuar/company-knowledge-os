from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

GITHUB_API_BASE_URL = "https://api.github.com"


class GitHubIssueClientError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def create_issue(
    *,
    access_token: str,
    repository_full_name: str,
    title: str,
    body: str | None = None,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"title": title}
    if body is not None:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    if assignees:
        payload["assignees"] = assignees

    url = f"{GITHUB_API_BASE_URL}/repos/{repository_full_name}/issues"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "founderOS",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise GitHubIssueClientError("github issue request failed") from exc

    if response.status_code < 200 or response.status_code >= 300:
        detail = _safe_response_detail(response)
        raise GitHubIssueClientError(detail)

    data = response.json()
    if not isinstance(data, dict):
        raise GitHubIssueClientError("github issue response was not an object")
    return data


def _safe_response_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, Mapping):
        message = data.get("message")
        if isinstance(message, str) and message.strip():
            return f"github issue request failed: {message.strip()[:300]}"
    return f"github issue request failed: http_{response.status_code}"
