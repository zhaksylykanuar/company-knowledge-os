from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.services.github_provider_error import safe_github_response_detail

GITHUB_API_BASE_URL = "https://api.github.com"


class GitHubRepositoryClientError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def list_installation_repositories(
    *,
    access_token: str,
    per_page: int = 100,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    """Read repositories visible to a GitHub App installation.

    This client is read-only: it only performs GET requests to GitHub's
    installation repositories API and returns object-shaped dictionaries.
    """

    if per_page < 1 or per_page > 100:
        raise GitHubRepositoryClientError(
            "github repository read request failed: invalid page size"
        )
    if max_pages < 1:
        raise GitHubRepositoryClientError(
            "github repository read request failed: invalid page limit"
        )

    url = f"{GITHUB_API_BASE_URL}/installation/repositories"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "founderOS",
    }
    repositories: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(1, max_pages + 1):
                response = await client.get(
                    url,
                    headers=headers,
                    params={
                        "per_page": per_page,
                        "page": page,
                    },
                )
                if response.status_code < 200 or response.status_code >= 300:
                    raise GitHubRepositoryClientError(_safe_response_detail(response))
                data = response.json()
                if not isinstance(data, Mapping):
                    raise GitHubRepositoryClientError(
                        "github repository read response was not an object"
                    )
                raw_repositories = data.get("repositories")
                if not isinstance(raw_repositories, list):
                    raise GitHubRepositoryClientError(
                        "github repository read response did not include repositories"
                    )
                page_items = [
                    item for item in raw_repositories if isinstance(item, Mapping)
                ]
                repositories.extend(dict(item) for item in page_items)
                if len(raw_repositories) < per_page:
                    return repositories
    except GitHubRepositoryClientError:
        raise
    except httpx.HTTPError as exc:
        raise GitHubRepositoryClientError(
            "github repository read request failed"
        ) from exc

    raise GitHubRepositoryClientError(
        "github repository read request failed: pagination limit reached"
    )


def _safe_response_detail(response: httpx.Response) -> str:
    return safe_github_response_detail(
        response,
        operation="github repository read request",
    )
