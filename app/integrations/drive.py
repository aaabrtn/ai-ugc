"""Google Drive integration. Used for two things:

1. Hosting reference images (setting/garment photos) at a public URL before
   submitting a video task to KIE, since KIE's servers can't reach anything
   on localhost.
2. (Phase 4) Saving finished videos to a dated folder.

A service account is used rather than interactive OAuth, since this is a
backend service with no browser-based consent flow to run. Share the target
Drive folder with the service account's email address (found inside the key
JSON file) so it has somewhere to write.
"""

from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.config import GOOGLE_DRIVE_INPUT_FOLDER_ID, GOOGLE_SERVICE_ACCOUNT_FILE

SCOPES = ["https://www.googleapis.com/auth/drive"]
INPUT_FOLDER_NAME = "AI UGC Inputs"

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_service = None
_input_folder_id_cache: str | None = None


class DriveNotConfigured(Exception):
    """No Google Drive service account is set up."""


class DriveError(Exception):
    """The Drive API call ran but failed."""


def _get_service():
    global _service
    if _service is not None:
        return _service
    if not GOOGLE_SERVICE_ACCOUNT_FILE:
        raise DriveNotConfigured(
            "No Google Drive service account is configured. Set GOOGLE_SERVICE_ACCOUNT_FILE in your "
            "environment (see .env.example) to enable video generation — KIE needs reference photos "
            "hosted at a public URL, and Drive is how this app provides that."
        )
    key_path = Path(GOOGLE_SERVICE_ACCOUNT_FILE)
    if not key_path.exists():
        raise DriveNotConfigured(f"GOOGLE_SERVICE_ACCOUNT_FILE is set but no file exists at {key_path}.")
    try:
        creds = service_account.Credentials.from_service_account_file(str(key_path), scopes=SCOPES)
        _service = build("drive", "v3", credentials=creds, cache_discovery=False)
    except (ValueError, OSError) as e:
        raise DriveNotConfigured(f"Couldn't load the Google service account key: {e}") from e
    return _service


def _ensure_input_folder(service) -> str:
    global _input_folder_id_cache
    if GOOGLE_DRIVE_INPUT_FOLDER_ID:
        return GOOGLE_DRIVE_INPUT_FOLDER_ID
    if _input_folder_id_cache:
        return _input_folder_id_cache

    try:
        results = (
            service.files()
            .list(
                q=f"name = '{INPUT_FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                fields="files(id, name)",
                pageSize=1,
            )
            .execute()
        )
        existing = results.get("files", [])
        if existing:
            _input_folder_id_cache = existing[0]["id"]
            return _input_folder_id_cache

        folder = (
            service.files()
            .create(body={"name": INPUT_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}, fields="id")
            .execute()
        )
        _input_folder_id_cache = folder["id"]
        return _input_folder_id_cache
    except HttpError as e:
        raise DriveError(f"Couldn't find or create the '{INPUT_FOLDER_NAME}' Drive folder: {e}") from e


def upload_public_image(path: Path) -> str:
    """Uploads a local image to Drive, makes it publicly viewable, and returns
    a URL KIE's servers can fetch the raw image bytes from."""
    service = _get_service()
    folder_id = _ensure_input_folder(service)
    mime_type = MIME_TYPES.get(path.suffix.lower(), "image/jpeg")

    try:
        media = MediaFileUpload(str(path), mimetype=mime_type, resumable=False)
        file = (
            service.files()
            .create(body={"name": path.name, "parents": [folder_id]}, media_body=media, fields="id")
            .execute()
        )
        file_id = file["id"]
        service.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
    except HttpError as e:
        raise DriveError(f"Couldn't upload {path.name} to Drive: {e}") from e

    return f"https://drive.google.com/uc?export=view&id={file_id}"
