# Skill: Google Drive Folder Navigation for Client Documents

## When to Use
Programmatically navigating a structured Google Drive folder hierarchy to find specific client documents (reservation agreements, contracts, etc.).

## Folder Structure
```
Customers/
├── [Project Name]/          # e.g., "קריופיגי", "פראיה"
│   ├── [Client Name]/       # e.g., "נילי שטרן ביבר"
│   │   ├── טופס הצטרפות.pdf
│   │   ├── הסכם רכישה.docx
│   │   └── ...
│   ├── [Client Name 2]/
│   └── ...
└── [Project Name 2]/
```

## Strategy

### Step 1: Auth Setup (One-Time)
```python
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CONFIG_DIR = os.path.expanduser('~/.contract-verifier')
TOKEN_PATH = os.path.join(CONFIG_DIR, 'token.json')
CREDS_PATH = os.path.join(CONFIG_DIR, 'credentials.json')

def get_drive_service():
    """Get authenticated Drive API service."""
    from googleapiclient.discovery import build
    
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    
    return build('drive', 'v3', credentials=creds)
```

### Step 2: Folder-by-Folder Navigation
```python
def find_folder_id(service, name: str, parent_id: str = None) -> str:
    """
    Find a folder by name within a parent folder.
    Uses CONTAINS for fuzzy Hebrew matching, then exact-matches results.
    """
    query = f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    # Drive API handles Hebrew in name queries
    query += f" and name = '{name}'"
    
    results = service.files().list(
        q=query,
        fields="files(id, name)",
        pageSize=10
    ).execute()
    
    files = results.get('files', [])
    
    if not files:
        # Try fuzzy: strip extra spaces, try partial match
        query_fuzzy = (
            f"mimeType = 'application/vnd.google-apps.folder' "
            f"and trashed = false "
            f"and name contains '{name.split()[0]}'"
        )
        if parent_id:
            query_fuzzy += f" and '{parent_id}' in parents"
        
        results = service.files().list(
            q=query_fuzzy,
            fields="files(id, name)",
            pageSize=20
        ).execute()
        files = results.get('files', [])
        
        # Score matches by similarity
        if files:
            from difflib import SequenceMatcher
            scored = [(f, SequenceMatcher(None, name, f['name']).ratio()) for f in files]
            scored.sort(key=lambda x: x[1], reverse=True)
            if scored[0][1] > 0.6:
                return scored[0][0]['id']
        
        raise FileNotFoundError(f"Folder '{name}' not found" + 
                                (f" in parent {parent_id}" if parent_id else ""))
    
    return files[0]['id']


def navigate_to_client(service, project_name: str, client_name: str) -> str:
    """
    Navigate: Customers → [Project] → [Client] and return the folder ID.
    """
    customers_id = find_folder_id(service, "Customers")
    project_id = find_folder_id(service, project_name, customers_id)
    client_id = find_folder_id(service, client_name, project_id)
    return client_id
```

### Step 3: Find Reservation PDF in Client Folder
```python
def find_reservation_pdf(service, client_folder_id: str) -> dict:
    """
    Find the reservation agreement PDF in a client folder.
    Looks for files matching common Hebrew names.
    """
    RESERVATION_KEYWORDS = ["טופס הצטרפות", "הצטרפות", "שריון", "reservation"]
    
    # List all PDFs in the folder
    query = (
        f"'{client_folder_id}' in parents "
        f"and mimeType = 'application/pdf' "
        f"and trashed = false"
    )
    results = service.files().list(
        q=query,
        fields="files(id, name, modifiedTime)",
        orderBy="modifiedTime desc",
        pageSize=20
    ).execute()
    
    files = results.get('files', [])
    if not files:
        raise FileNotFoundError("No PDF files found in client folder")
    
    # Try to match by keyword
    for keyword in RESERVATION_KEYWORDS:
        for f in files:
            if keyword in f['name']:
                return f
    
    # If no keyword match, warn and return most recent PDF
    print(f"⚠️  No file matching reservation keywords. Using most recent PDF: {files[0]['name']}")
    return files[0]


def download_file(service, file_id: str, destination: str):
    """Download a file from Google Drive."""
    from googleapiclient.http import MediaIoBaseDownload
    import io
    
    request = service.files().get_media(fileId=file_id)
    with open(destination, 'wb') as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
```

## Critical Rules

1. **Navigate folder-by-folder.** Don't try to search by full path — Drive API doesn't support path queries.
2. **Hebrew folder names work.** The Drive API handles Hebrew in `name = '...'` queries. Don't URL-encode manually.
3. **Use `name = 'exact'` first, fallback to `name contains 'partial'`.** Avoids false matches.
4. **Always filter `trashed = false`.** Deleted files still appear in queries otherwise.
5. **Cache downloaded files.** Store in `~/.contract-verifier/cache/{file_id}.pdf` to avoid re-downloading.
6. **Read-only scope.** Only request `drive.readonly`. This tool should NEVER modify Drive contents.
7. **Fuzzy matching for client names.** Hebrew names may have variations (with/without middle name, different spacing). Use `SequenceMatcher` with a 0.6 threshold.

## Setup Instructions for User

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use existing)
3. Enable the Google Drive API
4. Create OAuth 2.0 credentials (Desktop application)
5. Download `credentials.json` to `~/.contract-verifier/credentials.json`
6. First run will open a browser for authorization
7. Token is saved to `~/.contract-verifier/token.json` for subsequent runs

## Common Failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Folder not found" | Hebrew name mismatch (spacing, ״ vs ") | Use fuzzy matching fallback |
| 403 Forbidden | Wrong OAuth scope or no Drive API enabled | Re-check console setup |
| Token expired | Refresh token revoked by user | Delete token.json, re-auth |
| Wrong PDF returned | Multiple PDFs in folder, keyword not in filename | Sort by modifiedTime, pick newest matching |
