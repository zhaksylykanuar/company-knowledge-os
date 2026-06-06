from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.core.config import settings
from app.services.provider_execution_guard import require_live_provider_execution_ack

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service(
    *,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
):
    require_live_provider_execution_ack(
        provider="gmail",
        boundary="gmail_service",
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )

    token_path = Path(settings.google_gmail_token_file)
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(settings.google_client_secrets_file, SCOPES)
        creds = flow.run_local_server(port=8080)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def list_messages(
    query: str = "in:inbox OR in:sent",
    max_results: int = 20,
    *,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> list[dict]:
    service = get_gmail_service(
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )
    result = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    return result.get("messages", [])


def get_message(
    message_id: str,
    *,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> dict:
    service = get_gmail_service(
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )
    return service.users().messages().get(userId="me", id=message_id, format="full").execute()
