"""Google Drive integration for fetching reservation PDFs."""
from __future__ import annotations

import io
import os
import hashlib
import logging
from difflib import SequenceMatcher
from pathlib import Path

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
CONFIG_DIR = Path(os.path.expanduser("~/.contract-verifier"))
TOKEN_PATH = CONFIG_DIR / "token.json"
CREDS_PATH = CONFIG_DIR / "credentials.json"
CACHE_DIR = CONFIG_DIR / "cache"

RESERVATION_KEYWORDS = ["טופס הצטרפות", "הצטרפות", "שריון", "reservation"]


def fetch_reservation(project_name: str, client_name: str) -> str:
    """Fetch reservation PDF from Google Drive.

    Navigates: Customers → [Project] → [Client] → find PDF
    Returns local file path to downloaded PDF.
    """
    service = _get_drive_service()

    # Navigate folder hierarchy
    customers_id = _find_folder_id(service, "Customers")
    project_id = _find_folder_id(service, project_name, customers_id)
    client_id = _find_folder_id(service, client_name, project_id)

    # Find reservation PDF
    pdf_info = _find_reservation_pdf(service, client_id)

    # Check cache
    cache_path = CACHE_DIR / f"{pdf_info['id']}.pdf"
    if cache_path.exists():
        logger.info("Using cached PDF: %s", cache_path)
        return str(cache_path)

    # Download
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _download_file(service, pdf_info["id"], str(cache_path))
    logger.info("Downloaded: %s → %s", pdf_info["name"], cache_path)

    return str(cache_path)


def _get_drive_service():
    """Get authenticated Drive API service."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                raise FileNotFoundError(
                    f"Google OAuth credentials not found at {CREDS_PATH}. "
                    "See README.md for setup instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())

    return build("drive", "v3", credentials=creds)


def _find_folder_id(service, name: str, parent_id: str | None = None) -> str:
    """Find a folder by name, with fuzzy Hebrew matching fallback."""
    query = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    query += f" and name = '{name}'"

    results = service.files().list(
        q=query, fields="files(id, name)", pageSize=10
    ).execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # Fuzzy fallback: search by first word
    first_word = name.split()[0] if name.split() else name
    query_fuzzy = (
        f"mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false "
        f"and name contains '{first_word}'"
    )
    if parent_id:
        query_fuzzy += f" and '{parent_id}' in parents"

    results = service.files().list(
        q=query_fuzzy, fields="files(id, name)", pageSize=20
    ).execute()
    files = results.get("files", [])

    if files:
        scored = [
            (f, SequenceMatcher(None, name, f["name"]).ratio())
            for f in files
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        if scored[0][1] > 0.6:
            logger.info("Fuzzy matched folder '%s' → '%s'", name, scored[0][0]["name"])
            return scored[0][0]["id"]

    raise FileNotFoundError(
        f"Folder '{name}' not found"
        + (f" in parent folder" if parent_id else "")
    )


def _find_reservation_pdf(service, client_folder_id: str) -> dict:
    """Find the reservation PDF in a client folder."""
    query = (
        f"'{client_folder_id}' in parents "
        f"and mimeType = 'application/pdf' "
        f"and trashed = false"
    )
    results = service.files().list(
        q=query,
        fields="files(id, name, modifiedTime)",
        orderBy="modifiedTime desc",
        pageSize=20,
    ).execute()
    files = results.get("files", [])

    if not files:
        raise FileNotFoundError("No PDF files found in client folder")

    for keyword in RESERVATION_KEYWORDS:
        for f in files:
            if keyword in f["name"]:
                return f

    logger.warning("No file matching reservation keywords. Using most recent PDF: %s", files[0]["name"])
    return files[0]


def _download_file(service, file_id: str, destination: str) -> None:
    """Download a file from Google Drive."""
    from googleapiclient.http import MediaIoBaseDownload

    request = service.files().get_media(fileId=file_id)
    with open(destination, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
