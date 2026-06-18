"""Read-only Company Brain preview endpoints (Stage 23.2).

These endpoints expose the local Stage 22 preview read models to the founder
UI. They are GET-only and side-effect free: no DB writes, no external calls,
no raw email. They reuse the same ``require_api_key`` protection as the other
founder views (wired in ``app/main.py``); no write path is exposed here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.company_brain_preview import (
    load_company_brain_preview,
    load_overview,
    load_people,
    load_second_opinion,
    load_unresolved_questions,
)

router = APIRouter(prefix="/v1/founder/company-brain", tags=["company-brain"])


@router.get("/preview")
async def get_company_brain_preview() -> dict:
    """Full Company Brain preview bundle (overview + people + feed + questions)."""

    return load_company_brain_preview()


@router.get("/overview")
async def get_company_brain_overview() -> dict:
    return load_overview()


@router.get("/people")
async def get_company_brain_people() -> dict:
    return load_people()


@router.get("/second-opinion")
async def get_company_brain_second_opinion() -> dict:
    return load_second_opinion()


@router.get("/unresolved-questions")
async def get_company_brain_unresolved_questions() -> dict:
    return load_unresolved_questions()
