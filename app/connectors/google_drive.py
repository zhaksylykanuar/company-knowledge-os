from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.core.config import settings

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def get_drive_service():
    token_path = Path(settings.google_token_file)

    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            settings.google_client_secrets_file, SCOPES
        )
        creds = flow.run_local_server(port=8080)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds)


def list_ai_inbox_files(page_size: int = 50) -> list[dict]:
    if not settings.google_drive_ai_inbox_folder_id:
        raise RuntimeError("GOOGLE_DRIVE_AI_INBOX_FOLDER_ID is empty")

    service = get_drive_service()

    query = f"'{settings.google_drive_ai_inbox_folder_id}' in parents and trashed=false"

    response = service.files().list(
        q=query,
        pageSize=page_size,
        fields="files(id,name,mimeType,modifiedTime,webViewLink)",
    ).execute()

    return response.get("files", [])