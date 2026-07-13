from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.services.github_provider_error import safe_github_response_detail

GITHUB_API_BASE_URL = "https://api.github.com"


class GitHubPullRequestClientError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def list_pull_requests(
    *,
    access_token: str,
    repository_full_name: str,
    state: str = "all",
    per_page: int = 100,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    """Read pull requests from a single GitHub repository.

    This client is intentionally read-only: it only performs GET requests to
    GitHub's pulls API and returns sanitized object-shaped dictionaries for the
    caller to normalize. It does not create, update, merge, close, or comment on
    pull requests.
    """

    if state not in {"open", "closed", "all"}:
        raise GitHubPullRequestClientError(
            "github pull request read request failed: invalid state"
        )
    if per_page < 1 or per_page > 100:
        raise GitHubPullRequestClientError(
            "github pull request read request failed: invalid page size"
        )
    if max_pages < 1:
        raise GitHubPullRequestClientError(
            "github pull request read request failed: invalid page limit"
        )

    url = f"{GITHUB_API_BASE_URL}/repos/{repository_full_name}/pulls"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "founderOS",
    }
    pull_requests: list[dict[str, Any]] = []
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
                    raise GitHubPullRequestClientError(_safe_response_detail(response))
                data = response.json()
                if not isinstance(data, list):
                    raise GitHubPullRequestClientError(
                        "github pull request read response was not a list"
                    )
                page_items = [item for item in data if isinstance(item, Mapping)]
                pull_requests.extend(dict(item) for item in page_items)
                if len(data) < per_page:
                    return pull_requests
    except GitHubPullRequestClientError:
        raise
    except httpx.HTTPError as exc:
        raise GitHubPullRequestClientError(
            "github pull request read request failed"
        ) from exc

    raise GitHubPullRequestClientError(
        "github pull request read request failed: pagination limit reached"
    )


def _safe_response_detail(response: httpx.Response) -> str:
    return safe_github_response_detail(
        response,
        operation="github pull request read request",
    )
