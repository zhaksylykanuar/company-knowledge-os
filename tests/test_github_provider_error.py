import httpx

from app.services.github_provider_error import safe_github_response_detail


def test_safe_github_response_detail_includes_rate_limit_headers_without_secrets() -> None:
    request = httpx.Request(
        "GET",
        "https://api.github.com/installation/repositories",
        headers={"Authorization": "Bearer must-not-leak"},
    )
    response = httpx.Response(
        403,
        json={"message": "API rate limit exceeded for installation."},
        headers={
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": "1782912000",
            "x-ratelimit-resource": "core",
            "retry-after": "60",
        },
        request=request,
    )

    detail = safe_github_response_detail(
        response,
        operation="github repository read request",
    )

    assert detail == (
        "github repository read request failed; http_403; "
        "message=API rate limit exceeded for installation.; "
        "rate_limited=true; retry_after_seconds=60; "
        "rate_limit_reset_epoch=1782912000; rate_limit_remaining=0; "
        "rate_limit_resource=core"
    )
    assert "must-not-leak" not in detail
    assert "Authorization" not in detail


def test_safe_github_response_detail_bounds_provider_message() -> None:
    response = httpx.Response(
        500,
        json={"message": "x" * 500},
        request=httpx.Request("GET", "https://api.github.com/repos/example/repo"),
    )

    detail = safe_github_response_detail(
        response,
        operation="github issue request",
    )

    assert detail.startswith("github issue request failed; http_500; message=")
    assert len(detail) < 360
