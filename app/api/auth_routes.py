"""Email+password login endpoints (browser session cookie).

Coexists with operator API-key auth: these routes manage the browser session
cookie; machine/admin/CI keep using the API key. The raw session token is set as
an httpOnly + SameSite=Lax cookie (Secure outside local). Login failures return a
generic 401 that never reveals whether the email exists.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from uuid import UUID

from app.api.auth import is_local_like_env, require_session
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import USER_STATUS_ACTIVE, User
from app.services.identity_service import get_user_by_email, list_workspaces_for_user
from app.services.password_service import verify_password
from app.services.session_service import create_session, revoke_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

GENERIC_LOGIN_FAILURE = "invalid email or password"


class LoginRequest(BaseModel):
    email: str
    password: str


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=not is_local_like_env(settings),
        samesite=settings.session_cookie_samesite,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.session_cookie_name, path="/")


def _user_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "status": user.status,
    }


async def _workspaces_payload(user_id: UUID) -> list[dict]:
    async with AsyncSessionLocal() as session:
        memberships = await list_workspaces_for_user(session, user_id=user_id)
    return [
        {
            "id": str(membership.workspace.id),
            "name": membership.workspace.name,
            "slug": membership.workspace.slug,
            "role": membership.membership.role,
        }
        for membership in memberships
    ]


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    async with AsyncSessionLocal() as session:
        user = await get_user_by_email(session, email=payload.email)
        password_ok = (
            user is not None
            and user.status == USER_STATUS_ACTIVE
            and verify_password(payload.password, user.password_hash)
        )
        if not user or not password_ok:
            # Generic failure: never reveal whether the email exists.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_FAILURE
            )
        raw_token, _session_row = await create_session(
            session,
            user.id,
            user_agent=request.headers.get("user-agent"),
            ip_address=_client_ip(request),
        )
        user_payload = _user_payload(user)
        await session.commit()

    _set_session_cookie(response, raw_token)
    return {"status": "ok", "user": user_payload}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    _user: User = Depends(require_session),
) -> dict:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        async with AsyncSessionLocal() as session:
            await revoke_session(session, raw_token)
            await session.commit()
    _clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/me")
async def me(user: User = Depends(require_session)) -> dict:
    return {
        "user": _user_payload(user),
        "workspaces": await _workspaces_payload(user.id),
    }
