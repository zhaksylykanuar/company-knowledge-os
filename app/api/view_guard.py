"""Shared audience/view gating for the protected API.

The ``view`` query param selects the audience; the backend decides what
that audience may see. A single source of truth so every router (inbox,
share packs, …) gates identically.
"""

from fastapi import HTTPException, status

from app.services.visibility import SCOPE_FOUNDER, SCOPES


def validated_view(view: str) -> str:
    if view not in SCOPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown view: {view}",
        )
    return view


def require_founder(view: str) -> None:
    if validated_view(view) != SCOPE_FOUNDER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="founder view required",
        )


def require_scope(view: str, allowed: set[str]) -> str:
    viewer = validated_view(view)
    if viewer not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"view '{viewer}' is not allowed for this resource",
        )
    return viewer
