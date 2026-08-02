"""Email+password login endpoints (browser session cookie).

Coexists with operator API-key auth: these routes manage the browser session
cookie; machine/admin/CI keep using the API key. The raw session token is set as
an httpOnly + SameSite=Lax cookie (Secure outside local). Login failures return a
generic 401 that never reveals whether the email exists.
"""

from __future__ import annotations

import ipaddress
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from app.api.auth import is_local_like_env, require_session
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import USER_STATUS_ACTIVE, User
from app.services.account_setup_service import (
    AccountSetupTokenError,
    complete_account_setup_token,
)
from app.services.identity_service import get_user_by_email, list_workspaces_for_user
from app.services.founder_enrollment_service import (
    FOUNDER_ENROLLMENT_CONFLICT,
    INVALID_FOUNDER_INVITE,
    FounderEnrollmentConflictError,
    InvalidFounderInviteError,
    consume_founder_invite,
)
from app.services.login_throttle_service import (
    locked_until as login_locked_until,
    record_failure as record_login_failure,
    reset as reset_login_throttle,
)
from app.services.login_rate_limit_service import (
    AdmissionLease,
    LoginAdmissionUnavailable,
    acquire_login_admission,
    release_login_admission,
)
from app.services.password_service import hash_password, verify_password
from app.services.session_service import (
    create_session,
    revoke_other_sessions,
    revoke_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

GENERIC_LOGIN_FAILURE = "invalid email or password"
LOGIN_LOCKED_FAILURE = "too many failed login attempts; try again later"
AUTH_ADMISSION_UNAVAILABLE = "authentication is temporarily unavailable"
WRONG_CURRENT_PASSWORD = "current password is incorrect"
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_WORKSPACE_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ENROLLMENT_CONFLICT_CONSTRAINTS = {"uq_users_email", "uq_workspaces_slug"}
_SESSION_USER_AGENT_MAX_LENGTH = 512
# Precomputed Argon2id hash used only to equalize invalid-login work. Keeping a
# stable hash avoids spending an extra Argon2 hash operation on every request.
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$BJbighoHNeK9SBF0uWfk6w$"
    "GB1lF1jTYXfxgWRUJzdqTreH5naYOnHKNVh1BuYs+mU"
)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class SetupPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=8, max_length=256)


class FounderEnrollmentRequest(BaseModel):
    token: str = Field(min_length=1, max_length=1024)
    email: str = Field(max_length=320)
    name: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=256)
    workspace_name: str = Field(min_length=1, max_length=255)
    workspace_slug: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("email must be a valid address")
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("workspace_name")
    @classmethod
    def validate_workspace_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("workspace_name must not be blank")
        return normalized

    @field_validator("workspace_slug")
    @classmethod
    def validate_workspace_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _WORKSPACE_SLUG_PATTERN.fullmatch(normalized):
            raise ValueError(
                "workspace_slug must contain lowercase letters, numbers, and single hyphens"
            )
        return normalized


def _trusted_proxy_networks() -> tuple[
    ipaddress.IPv4Network | ipaddress.IPv6Network,
    ...,
]:
    raw = settings.trusted_proxy_cidrs
    if not raw:
        return ()
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for candidate in raw.replace("\n", ",").split(","):
        stripped = candidate.strip()
        if not stripped:
            continue
        try:
            networks.append(ipaddress.ip_network(stripped, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _client_ip(request: Request) -> str | None:
    direct_host = request.client.host if request.client is not None else None
    if direct_host is None:
        return None
    try:
        direct_ip = ipaddress.ip_address(direct_host)
    except ValueError:
        return direct_host[:64] if len(direct_host) <= 64 else None

    if not settings.trust_proxy_headers:
        return direct_ip.compressed
    networks = _trusted_proxy_networks()
    if not networks or not any(direct_ip in network for network in networks):
        return direct_ip.compressed

    forwarded_for = request.headers.get("x-forwarded-for")
    if not forwarded_for:
        return direct_ip.compressed
    candidate = forwarded_for.split(",", 1)[0].strip()
    try:
        return ipaddress.ip_address(candidate).compressed
    except ValueError:
        return direct_ip.compressed


async def _acquire_public_auth_admission(
    request: Request,
) -> AdmissionLease | None:
    if is_local_like_env(settings):
        return None
    try:
        admission = await acquire_login_admission(_client_ip(request))
    except LoginAdmissionUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=AUTH_ADMISSION_UNAVAILABLE,
            headers={"Retry-After": "5"},
        ) from exc
    if admission is None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=LOGIN_LOCKED_FAILURE,
            headers={
                "Retry-After": str(settings.login_rate_limit_window_seconds)
            },
        )
    return admission


def _session_user_agent(request: Request) -> str | None:
    raw_user_agent = request.headers.get("user-agent")
    if raw_user_agent is None:
        return None
    sanitized = "".join(character for character in raw_user_agent if character.isprintable())
    sanitized = sanitized.strip()[:_SESSION_USER_AGENT_MAX_LENGTH]
    return sanitized or None


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


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    candidates = (exc.orig, getattr(exc.orig, "__cause__", None))
    for candidate in candidates:
        constraint_name = getattr(candidate, "constraint_name", None)
        if isinstance(constraint_name, str):
            return constraint_name
    return None


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
    admission = await _acquire_public_auth_admission(request)

    try:
        async with AsyncSessionLocal() as session:
            # Always perform one real-or-dummy verification under the admission
            # budget. A third party cannot lock the real owner out: a correct
            # credential succeeds and resets the email throttle even while locked.
            email_locked = await login_locked_until(session, payload.email) is not None
            user = await get_user_by_email(session, email=payload.email)
            real_hash = (
                user.password_hash
                if user is not None
                and user.status == USER_STATUS_ACTIVE
                and user.password_hash is not None
                else None
            )
            password_ok = verify_password(
                payload.password,
                real_hash or _DUMMY_PASSWORD_HASH,
            )
            if user is None or real_hash is None or not password_ok:
                if email_locked:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=LOGIN_LOCKED_FAILURE,
                    )
                await record_login_failure(session, payload.email)
                await session.commit()
                # Generic failure: never reveal whether the email exists.
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=GENERIC_LOGIN_FAILURE,
                )

            raw_token, _session_row = await create_session(
                session,
                user.id,
                user_agent=_session_user_agent(request),
                ip_address=_client_ip(request),
            )
            await reset_login_throttle(session, payload.email)
            user_payload = _user_payload(user)
            await session.commit()
    finally:
        await release_login_admission(admission)

    _set_session_cookie(response, raw_token)
    return {"status": "ok", "user": user_payload}


@router.post("/enroll", status_code=status.HTTP_201_CREATED)
async def enroll_founder(
    payload: FounderEnrollmentRequest,
    request: Request,
    response: Response,
) -> dict:
    """Consume an operator-issued invite and create the first founder workspace."""

    admission = await _acquire_public_auth_admission(request)
    try:
        async with AsyncSessionLocal() as session:
            try:
                enrollment = await consume_founder_invite(
                    session,
                    raw_token=payload.token,
                    email=payload.email,
                    name=payload.name,
                    plaintext_password=payload.password,
                    workspace_name=payload.workspace_name,
                    workspace_slug=payload.workspace_slug,
                )
                raw_session_token, _session_row = await create_session(
                    session,
                    enrollment.user.id,
                    user_agent=_session_user_agent(request),
                    ip_address=_client_ip(request),
                )
                user_payload = _user_payload(enrollment.user)
                workspace_payload = {
                    "id": str(enrollment.workspace.id),
                    "name": enrollment.workspace.name,
                    "slug": enrollment.workspace.slug,
                    "role": enrollment.membership.role,
                }
                await session.commit()
            except InvalidFounderInviteError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=INVALID_FOUNDER_INVITE,
                ) from exc
            except FounderEnrollmentConflictError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=FOUNDER_ENROLLMENT_CONFLICT,
                ) from exc
            except IntegrityError as exc:
                await session.rollback()
                if _integrity_constraint_name(exc) in _ENROLLMENT_CONFLICT_CONSTRAINTS:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=FOUNDER_ENROLLMENT_CONFLICT,
                    ) from exc
                raise
    finally:
        await release_login_admission(admission)

    _set_session_cookie(response, raw_session_token)
    return {"status": "ok", "user": user_payload, "workspace": workspace_payload}


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


@router.post("/setup-password")
async def setup_password(
    payload: SetupPasswordRequest,
    request: Request,
    response: Response,
) -> dict:
    admission = await _acquire_public_auth_admission(request)
    try:
        async with AsyncSessionLocal() as session:
            try:
                user = await complete_account_setup_token(
                    session,
                    raw_token=payload.token,
                    plaintext_password=payload.new_password,
                )
                raw_token, _session_row = await create_session(
                    session,
                    user.id,
                    user_agent=_session_user_agent(request),
                    ip_address=_client_ip(request),
                )
                user_payload = _user_payload(user)
                await session.commit()
            except AccountSetupTokenError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
    finally:
        await release_login_admission(admission)

    _set_session_cookie(response, raw_token)
    return {"status": "ok", "user": user_payload}


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(require_session),
) -> dict:
    raw_token = request.cookies.get(settings.session_cookie_name)
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        if db_user is None or not verify_password(
            payload.current_password, db_user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=WRONG_CURRENT_PASSWORD
            )
        db_user.password_hash = hash_password(payload.new_password)
        await session.flush()
        # Log out other devices; keep the current session valid.
        await revoke_other_sessions(
            session, user_id=db_user.id, keep_raw_token=raw_token
        )
        await session.commit()
    return {"status": "ok"}
