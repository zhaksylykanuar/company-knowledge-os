from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.services.github_provider_error import safe_github_response_detail

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


async def get_issue(
    *,
    access_token: str,
    repository_full_name: str,
    issue_number: int,
) -> dict[str, Any]:
    url = f"{GITHUB_API_BASE_URL}/repos/{repository_full_name}/issues/{issue_number}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "founderOS",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise GitHubIssueClientError("github issue read request failed") from exc

    if response.status_code < 200 or response.status_code >= 300:
        detail = _safe_response_detail(response)
        raise GitHubIssueClientError(detail.replace("github issue request", "github issue read request"))

    data = response.json()
    if not isinstance(data, dict):
        raise GitHubIssueClientError("github issue read response was not an object")
    return data


async def list_issues(
    *,
    access_token: str,
    repository_full_name: str,
    state: str = "all",
    per_page: int = 100,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    if state not in {"open", "closed", "all"}:
        raise GitHubIssueClientError("github issue read request failed: invalid state")
    if per_page < 1 or per_page > 100:
        raise GitHubIssueClientError("github issue read request failed: invalid page size")
    if max_pages < 1:
        raise GitHubIssueClientError("github issue read request failed: invalid page limit")

    url = f"{GITHUB_API_BASE_URL}/repos/{repository_full_name}/issues"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "founderOS",
    }
    issues: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(1, max_pages + 1):
                response = await client.get(
                    url,
                    headers=headers,
                    params={
                        "state": state,
                        "per_page": per_page,
                        "page": page,
                    },
                )
                if response.status_code < 200 or response.status_code >= 300:
                    detail = _safe_response_detail(response)
                    raise GitHubIssueClientError(
                        detail.replace(
                            "github issue request",
                            "github issue read request",
                        )
                    )
                data = response.json()
                if not isinstance(data, list):
                    raise GitHubIssueClientError(
                        "github issue read response was not a list"
                    )
                page_items = [item for item in data if isinstance(item, Mapping)]
                issues.extend(dict(item) for item in page_items)
                if len(data) < per_page:
                    return issues
    except GitHubIssueClientError:
        raise
    except httpx.HTTPError as exc:
        raise GitHubIssueClientError("github issue read request failed") from exc

    raise GitHubIssueClientError("github issue read request failed: pagination limit reached")


def _safe_response_detail(response: httpx.Response) -> str:
    return safe_github_response_detail(
        response,
        operation="github issue request",
    )
