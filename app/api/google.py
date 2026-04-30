from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.drive import DRIVE_BACKFILL_DEFAULT_MAX_RESULTS, DRIVE_BACKFILL_MAX_RESULTS
from app.api.gmail import (
    BROAD_GMAIL_BACKFILL_QUERY,
    GMAIL_BACKFILL_DEFAULT_MAX_RESULTS,
    GMAIL_BACKFILL_MAX_RESULTS,
    _normalize_gmail_query,
)
from app.core.config import settings

router = APIRouter(prefix="/v1/google", tags=["google"])

QuerySource = Literal["none", "request", "config"]

GMAIL_BLOCKER_DISABLED = "gmail_backfill_disabled"
GMAIL_BLOCKER_QUERY_MISSING = "gmail_query_missing"
GMAIL_BLOCKER_QUERY_TOO_BROAD = "gmail_query_too_broad"
GMAIL_BLOCKER_MAX_RESULTS_INVALID = "gmail_max_results_invalid"

DRIVE_BLOCKER_DISABLED = "drive_backfill_disabled"
DRIVE_BLOCKER_FOLDER_BOUNDARY_MISSING = "drive_folder_boundary_missing"
DRIVE_BLOCKER_MAX_RESULTS_INVALID = "drive_max_results_invalid"

GOOGLE_CREDENTIAL_BLOCKER_CLIENT_SECRETS_NOT_CONFIGURED = (
    "google_client_secrets_not_configured"
)
GOOGLE_CREDENTIAL_BLOCKER_CLIENT_SECRETS_FILE_MISSING = (
    "google_client_secrets_file_missing"
)
GOOGLE_CREDENTIAL_BLOCKER_GMAIL_TOKEN_PATH_NOT_CONFIGURED = (
    "google_gmail_token_path_not_configured"
)
GOOGLE_CREDENTIAL_BLOCKER_DRIVE_TOKEN_PATH_NOT_CONFIGURED = (
    "google_drive_token_path_not_configured"
)


class GmailBackfillPreflight(BaseModel):
    enabled: bool
    query_source: QuerySource
    query_configured: bool
    query_allowed: bool
    max_results: int
    max_results_allowed: bool
    ready: bool
    blockers: list[str]


class DriveBackfillPreflight(BaseModel):
    enabled: bool
    folder_boundary_configured: bool
    max_results: int
    max_results_allowed: bool
    ready: bool
    blockers: list[str]


class GoogleCredentialsPreflight(BaseModel):
    client_secrets_configured: bool
    client_secrets_file_present: bool
    gmail_token_configured: bool
    gmail_token_file_present: bool
    drive_token_configured: bool
    drive_token_file_present: bool
    ready: bool
    blockers: list[str]
    notes: list[str]


class GoogleBackfillPreflightResponse(BaseModel):
    overall_ready: bool
    gmail: GmailBackfillPreflight
    drive: DriveBackfillPreflight
    google_credentials: GoogleCredentialsPreflight
    notes: list[str]


def _configured_path_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _configured_file_present(path_value: str) -> bool:
    return Path(path_value).is_file() if path_value else False


def _select_gmail_query(gmail_query: str | None) -> tuple[QuerySource, str]:
    if gmail_query is not None:
        return "request", gmail_query.strip()

    configured_query = settings.google_gmail_backfill_query
    if isinstance(configured_query, str):
        return "config", configured_query.strip()

    return "none", ""


def _build_gmail_preflight(gmail_query: str | None, max_results: int) -> GmailBackfillPreflight:
    query_source, cleaned_query = _select_gmail_query(gmail_query)
    query_configured = bool(cleaned_query)
    query_allowed = (
        query_configured
        and _normalize_gmail_query(cleaned_query) != _normalize_gmail_query(BROAD_GMAIL_BACKFILL_QUERY)
    )
    max_results_allowed = 1 <= max_results <= GMAIL_BACKFILL_MAX_RESULTS

    blockers: list[str] = []
    if not settings.google_gmail_backfill_enabled:
        blockers.append(GMAIL_BLOCKER_DISABLED)
    if not query_configured:
        blockers.append(GMAIL_BLOCKER_QUERY_MISSING)
    elif not query_allowed:
        blockers.append(GMAIL_BLOCKER_QUERY_TOO_BROAD)
    if not max_results_allowed:
        blockers.append(GMAIL_BLOCKER_MAX_RESULTS_INVALID)

    return GmailBackfillPreflight(
        enabled=settings.google_gmail_backfill_enabled,
        query_source=query_source,
        query_configured=query_configured,
        query_allowed=query_allowed,
        max_results=max_results,
        max_results_allowed=max_results_allowed,
        ready=not blockers,
        blockers=blockers,
    )


def _build_drive_preflight(max_results: int) -> DriveBackfillPreflight:
    folder_id = settings.google_drive_ai_inbox_folder_id
    folder_boundary_configured = bool(folder_id.strip()) if isinstance(folder_id, str) else False
    max_results_allowed = 1 <= max_results <= DRIVE_BACKFILL_MAX_RESULTS

    blockers: list[str] = []
    if not settings.google_drive_backfill_enabled:
        blockers.append(DRIVE_BLOCKER_DISABLED)
    if not folder_boundary_configured:
        blockers.append(DRIVE_BLOCKER_FOLDER_BOUNDARY_MISSING)
    if not max_results_allowed:
        blockers.append(DRIVE_BLOCKER_MAX_RESULTS_INVALID)

    return DriveBackfillPreflight(
        enabled=settings.google_drive_backfill_enabled,
        folder_boundary_configured=folder_boundary_configured,
        max_results=max_results,
        max_results_allowed=max_results_allowed,
        ready=not blockers,
        blockers=blockers,
    )


def _build_google_credentials_preflight() -> GoogleCredentialsPreflight:
    client_secrets_path = _configured_path_value(settings.google_client_secrets_file)
    gmail_token_path = _configured_path_value(settings.google_gmail_token_file)
    drive_token_path = _configured_path_value(settings.google_token_file)

    client_secrets_configured = bool(client_secrets_path)
    client_secrets_file_present = _configured_file_present(client_secrets_path)
    gmail_token_configured = bool(gmail_token_path)
    gmail_token_file_present = _configured_file_present(gmail_token_path)
    drive_token_configured = bool(drive_token_path)
    drive_token_file_present = _configured_file_present(drive_token_path)

    blockers: list[str] = []
    if not client_secrets_configured:
        blockers.append(GOOGLE_CREDENTIAL_BLOCKER_CLIENT_SECRETS_NOT_CONFIGURED)
    elif not client_secrets_file_present:
        blockers.append(GOOGLE_CREDENTIAL_BLOCKER_CLIENT_SECRETS_FILE_MISSING)
    if not gmail_token_configured:
        blockers.append(GOOGLE_CREDENTIAL_BLOCKER_GMAIL_TOKEN_PATH_NOT_CONFIGURED)
    if not drive_token_configured:
        blockers.append(GOOGLE_CREDENTIAL_BLOCKER_DRIVE_TOKEN_PATH_NOT_CONFIGURED)

    return GoogleCredentialsPreflight(
        client_secrets_configured=client_secrets_configured,
        client_secrets_file_present=client_secrets_file_present,
        gmail_token_configured=gmail_token_configured,
        gmail_token_file_present=gmail_token_file_present,
        drive_token_configured=drive_token_configured,
        drive_token_file_present=drive_token_file_present,
        ready=not blockers,
        blockers=blockers,
        notes=[
            "credential_presence_only",
            "credential_contents_not_read",
            "file_presence_does_not_prove_credential_validity",
            "token_files_may_be_created_by_local_oauth",
            "production_oauth_storage_not_implemented",
        ],
    )


@router.get("/backfill/preflight")
async def google_backfill_preflight(
    gmail_query: str | None = Query(None),
    gmail_max_results: int = Query(
        GMAIL_BACKFILL_DEFAULT_MAX_RESULTS,
        ge=1,
        le=GMAIL_BACKFILL_MAX_RESULTS,
    ),
    drive_max_results: int = Query(
        DRIVE_BACKFILL_DEFAULT_MAX_RESULTS,
        ge=1,
        le=DRIVE_BACKFILL_MAX_RESULTS,
    ),
) -> GoogleBackfillPreflightResponse:
    gmail = _build_gmail_preflight(gmail_query, gmail_max_results)
    drive = _build_drive_preflight(drive_max_results)
    google_credentials = _build_google_credentials_preflight()
    return GoogleBackfillPreflightResponse(
        overall_ready=gmail.ready and drive.ready and google_credentials.ready,
        gmail=gmail,
        drive=drive,
        google_credentials=google_credentials,
        notes=[
            "preflight_only",
            "no_google_api_calls_made",
            "production_sync_not_implemented",
        ],
    )
