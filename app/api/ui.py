"""Local founder UI: static panel page plus founder view endpoints.

The page is a data-free static shell; every data call goes through the
protected API. Founder views reuse the same read models as the Telegram
bot plus the composed overview document. No write paths are exposed.
"""

import html
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from app.core.config import settings
from app.services.digest import DEFAULT_DIGEST_ENTRY_LIMIT, MAX_DIGEST_ENTRY_LIMIT
from app.services.founder_overview import build_founder_overview
from app.services.telegram_founder_bot import (
    DEFAULT_STATUS_WINDOW_HOURS,
    build_dev_reply_text,
    build_status_reply_text,
)

MAX_STATUS_WINDOW_HOURS = 24 * 14
MAX_ATTENTION_LIMIT = 50

DEFAULT_API_AUTH_HEADER_NAME = "X-FounderOS-API-Key"
_API_HEADER_NAME_PLACEHOLDER = "__FOS_API_HEADER_NAME__"

_UI_PAGE_PATH = Path(__file__).resolve().parent.parent / "static" / "founder_ui.html"

page_router = APIRouter(tags=["ui"])
views_router = APIRouter(prefix="/v1/founder", tags=["founder"])


def _configured_api_header_name() -> str:
    header_name = settings.api_auth_header_name
    if not isinstance(header_name, str) or not header_name.strip():
        return DEFAULT_API_AUTH_HEADER_NAME
    return header_name.strip()


@page_router.get("/", include_in_schema=False)
async def redirect_root_to_ui() -> RedirectResponse:
    return RedirectResponse(url="/ui", status_code=307)


@page_router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def get_founder_ui_page() -> HTMLResponse:
    # The auth header NAME (not the key) is injected so the page works
    # out of the box with a custom api_auth_header_name.
    page = _UI_PAGE_PATH.read_text(encoding="utf-8").replace(
        _API_HEADER_NAME_PLACEHOLDER,
        html.escape(_configured_api_header_name(), quote=True),
    )
    return HTMLResponse(page)


@views_router.get("/overview")
async def get_founder_overview(
    attention_limit: int = Query(default=20, ge=1, le=MAX_ATTENTION_LIMIT),
) -> dict:
    return await build_founder_overview(attention_limit=attention_limit)


@views_router.get("/status", response_class=PlainTextResponse)
async def get_founder_status_text(
    q: str | None = Query(default=None, max_length=300),
    window_hours: int = Query(
        default=DEFAULT_STATUS_WINDOW_HOURS,
        ge=1,
        le=MAX_STATUS_WINDOW_HOURS,
    ),
    limit: int = Query(
        default=DEFAULT_DIGEST_ENTRY_LIMIT,
        ge=1,
        le=MAX_DIGEST_ENTRY_LIMIT,
    ),
) -> PlainTextResponse:
    text = await build_status_reply_text(
        window_hours=window_hours,
        limit=limit,
        question_text=q or None,
    )
    return PlainTextResponse(text or "")


@views_router.get("/dev", response_class=PlainTextResponse)
async def get_founder_dev_overview_text() -> PlainTextResponse:
    return PlainTextResponse(await build_dev_reply_text())
