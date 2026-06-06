import io
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.core.config import settings
from app.services.provider_execution_guard import require_live_provider_execution_ack

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDES_MIME = "application/vnd.google-apps.presentation"


def get_drive_service(
    *,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
):
    require_live_provider_execution_ack(
        provider="google_drive",
        boundary="drive_service",
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )

    token_path = Path(settings.google_token_file)
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(settings.google_client_secrets_file, SCOPES)
        creds = flow.run_local_server(port=8080)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds)


def list_ai_inbox_files(
    page_size: int = 50,
    *,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> list[dict]:
    if not settings.google_drive_ai_inbox_folder_id:
        raise RuntimeError("GOOGLE_DRIVE_AI_INBOX_FOLDER_ID is empty")

    service = get_drive_service(
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )
    query = f"'{settings.google_drive_ai_inbox_folder_id}' in parents and trashed=false"
    response = service.files().list(
        q=query,
        pageSize=page_size,
        fields="files(id,name,mimeType,modifiedTime,webViewLink,md5Checksum,size)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return response.get("files", [])


def _download_request(service, file_id: str, mime_type: str | None):
    if mime_type == GOOGLE_DOC_MIME:
        return service.files().export_media(fileId=file_id, mimeType="text/plain")
    if mime_type == GOOGLE_SHEET_MIME:
        return service.files().export_media(fileId=file_id, mimeType="text/csv")
    if mime_type == GOOGLE_SLIDES_MIME:
        return service.files().export_media(fileId=file_id, mimeType="text/plain")
    return service.files().get_media(fileId=file_id)


def download_file_text(
    file_id: str,
    mime_type: str | None = None,
    *,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> str:
    service = get_drive_service(
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )
    request = _download_request(service, file_id, mime_type)

    file = io.BytesIO()
    downloader = MediaIoBaseDownload(file, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    content = file.getvalue()
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""
