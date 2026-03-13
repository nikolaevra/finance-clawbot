"""
Google Workspace API client helpers.

Supports OAuth URL generation + code exchange and common Drive/Docs/Sheets
operations for read/write/create/update workflows.
"""
from __future__ import annotations

import io
import json
import logging
import secrets
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from config import Config
from services.gmail_service import build_oauth_state, parse_oauth_state

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/userinfo.email",
]


def _client_config() -> dict[str, Any]:
    return {
        "web": {
            "client_id": Config.GOOGLE_CLIENT_ID,
            "client_secret": Config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [Config.GOOGLE_WORKSPACE_REDIRECT_URI],
        }
    }


def get_auth_url(user_id: str) -> str:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = Config.GOOGLE_WORKSPACE_REDIRECT_URI
    code_verifier = secrets.token_urlsafe(64)
    flow.code_verifier = code_verifier
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=build_oauth_state(user_id, code_verifier),
        code_challenge_method="S256",
    )
    return url


def exchange_code(code: str, code_verifier: str | None = None) -> str:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = Config.GOOGLE_WORKSPACE_REDIRECT_URI
    if code_verifier:
        flow.code_verifier = code_verifier
        flow.fetch_token(code=code, code_verifier=code_verifier)
    else:
        flow.fetch_token(code=code)
    return flow.credentials.to_json()


def get_user_profile(credentials_json: str) -> tuple[dict[str, Any], str | None]:
    oauth, updated = _build_service("oauth2", "v2", credentials_json)
    profile = oauth.userinfo().get().execute()
    return profile, updated


def _build_credentials(credentials_json: str) -> tuple[Credentials, str | None]:
    info = json.loads(credentials_json)
    # Do not force scopes here. Google can return a superset of scopes when
    # include_granted_scopes=true is used, and overriding scopes on refresh can
    # trigger "Scope has changed" errors.
    creds = Credentials.from_authorized_user_info(info)
    original_token = creds.token
    updated_json: str | None = None
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        if creds.token != original_token:
            updated_json = creds.to_json()
    return creds, updated_json


def _build_service(
    api_name: str,
    api_version: str,
    credentials_json: str,
):
    creds, updated = _build_credentials(credentials_json)
    service = build(api_name, api_version, credentials=creds, cache_discovery=False)
    return service, updated


def _extract_document_text(doc: dict[str, Any]) -> str:
    chunks: list[str] = []
    body = (doc.get("body") or {}).get("content") or []
    for structural_element in body:
        para = structural_element.get("paragraph")
        if not para:
            continue
        for elem in para.get("elements", []) or []:
            text_run = (elem.get("textRun") or {}).get("content")
            if text_run:
                chunks.append(text_run)
    return "".join(chunks).strip()


def drive_list_files(
    credentials_json: str,
    query: str = "",
    page_size: int = 20,
) -> tuple[dict[str, Any], str | None]:
    drive, updated = _build_service("drive", "v3", credentials_json)
    page_size = min(max(page_size, 1), 100)
    kwargs: dict[str, Any] = {
        "pageSize": page_size,
        "fields": "files(id,name,mimeType,modifiedTime,createdTime,webViewLink,parents),nextPageToken",
        "orderBy": "modifiedTime desc",
        "spaces": "drive",
    }
    if query:
        kwargs["q"] = query
    result = drive.files().list(**kwargs).execute()
    return {
        "files": result.get("files", []),
        "next_page_token": result.get("nextPageToken"),
    }, updated


def drive_get_file_metadata(
    credentials_json: str,
    file_id: str,
) -> tuple[dict[str, Any], str | None]:
    drive, updated = _build_service("drive", "v3", credentials_json)
    result = drive.files().get(
        fileId=file_id,
        fields="id,name,mimeType,modifiedTime,createdTime,webViewLink,parents,size",
    ).execute()
    return result, updated


def drive_get_text_content(
    credentials_json: str,
    file_id: str,
) -> tuple[dict[str, Any], str | None]:
    metadata, updated = drive_get_file_metadata(credentials_json, file_id)
    mime_type = metadata.get("mimeType", "")

    if mime_type == "application/vnd.google-apps.document":
        doc, doc_updated = docs_get_document(credentials_json, file_id)
        return {
            "file": metadata,
            "content": doc.get("text", ""),
            "source": "google_docs",
        }, (doc_updated or updated)

    if mime_type == "application/vnd.google-apps.spreadsheet":
        return {
            "file": metadata,
            "content": "",
            "source": "google_sheets",
            "note": "Use Sheets endpoints to read cell values.",
        }, updated

    drive, fresh_update = _build_service("drive", "v3", credentials_json)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, drive.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    content = fh.getvalue().decode("utf-8", errors="replace")
    return {
        "file": metadata,
        "content": content,
        "source": "drive_file",
    }, (fresh_update or updated)


def drive_create_text_file(
    credentials_json: str,
    name: str,
    content: str,
    mime_type: str = "text/plain",
    parent_folder_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    drive, updated = _build_service("drive", "v3", credentials_json)
    metadata: dict[str, Any] = {"name": name}
    if parent_folder_id:
        metadata["parents"] = [parent_folder_id]
    media = MediaIoBaseUpload(
        io.BytesIO(content.encode("utf-8")),
        mimetype=mime_type,
        resumable=False,
    )
    created = drive.files().create(
        body=metadata,
        media_body=media,
        fields="id,name,mimeType,modifiedTime,webViewLink,parents",
    ).execute()
    return created, updated


def drive_update_text_file(
    credentials_json: str,
    file_id: str,
    content: str,
    mime_type: str = "text/plain",
) -> tuple[dict[str, Any], str | None]:
    drive, updated = _build_service("drive", "v3", credentials_json)
    media = MediaIoBaseUpload(
        io.BytesIO(content.encode("utf-8")),
        mimetype=mime_type,
        resumable=False,
    )
    updated_file = drive.files().update(
        fileId=file_id,
        media_body=media,
        fields="id,name,mimeType,modifiedTime,webViewLink,parents",
    ).execute()
    return updated_file, updated


def docs_create_document(
    credentials_json: str,
    title: str,
    content: str = "",
) -> tuple[dict[str, Any], str | None]:
    docs, updated = _build_service("docs", "v1", credentials_json)
    created = docs.documents().create(body={"title": title}).execute()
    doc_id = created.get("documentId")
    if content and doc_id:
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": content,
                        }
                    }
                ]
            },
        ).execute()
    return created, updated


def docs_get_document(
    credentials_json: str,
    document_id: str,
) -> tuple[dict[str, Any], str | None]:
    docs, updated = _build_service("docs", "v1", credentials_json)
    document = docs.documents().get(documentId=document_id).execute()
    return {
        "document_id": document.get("documentId"),
        "title": document.get("title", ""),
        "revision_id": document.get("revisionId"),
        "text": _extract_document_text(document),
    }, updated


def docs_replace_all_text(
    credentials_json: str,
    document_id: str,
    replacements: list[dict[str, str]],
) -> tuple[dict[str, Any], str | None]:
    docs, updated = _build_service("docs", "v1", credentials_json)
    requests: list[dict[str, Any]] = []
    for item in replacements:
        old_text = (item.get("old_text") or "").strip()
        new_text = item.get("new_text") or ""
        if not old_text:
            continue
        requests.append(
            {
                "replaceAllText": {
                    "containsText": {"text": old_text, "matchCase": True},
                    "replaceText": new_text,
                }
            }
        )
    if not requests:
        raise ValueError("At least one replacement with old_text is required")
    result = docs.documents().batchUpdate(
        documentId=document_id,
        body={"requests": requests},
    ).execute()
    return result, updated


def docs_append_text(
    credentials_json: str,
    document_id: str,
    text: str,
) -> tuple[dict[str, Any], str | None]:
    docs, updated = _build_service("docs", "v1", credentials_json)
    current = docs.documents().get(documentId=document_id).execute()
    end_index = 1
    body_content = (current.get("body") or {}).get("content") or []
    if body_content:
        end_index = max((body_content[-1].get("endIndex") or 1) - 1, 1)
    result = docs.documents().batchUpdate(
        documentId=document_id,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": end_index},
                        "text": text,
                    }
                }
            ]
        },
    ).execute()
    return result, updated


def sheets_create_spreadsheet(
    credentials_json: str,
    title: str,
    sheet_title: str = "Sheet1",
) -> tuple[dict[str, Any], str | None]:
    sheets, updated = _build_service("sheets", "v4", credentials_json)
    created = sheets.spreadsheets().create(
        body={
            "properties": {"title": title},
            "sheets": [{"properties": {"title": sheet_title}}],
        }
    ).execute()
    return {
        "spreadsheet_id": created.get("spreadsheetId"),
        "spreadsheet_url": created.get("spreadsheetUrl"),
        "title": (created.get("properties") or {}).get("title", title),
    }, updated


def sheets_read_values(
    credentials_json: str,
    spreadsheet_id: str,
    range_a1: str,
) -> tuple[dict[str, Any], str | None]:
    sheets, updated = _build_service("sheets", "v4", credentials_json)
    values = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
    ).execute()
    return {
        "range": values.get("range"),
        "major_dimension": values.get("majorDimension"),
        "values": values.get("values", []),
    }, updated


def sheets_update_values(
    credentials_json: str,
    spreadsheet_id: str,
    range_a1: str,
    values: list[list[Any]],
    value_input_option: str = "USER_ENTERED",
) -> tuple[dict[str, Any], str | None]:
    sheets, updated = _build_service("sheets", "v4", credentials_json)
    result = sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        valueInputOption=value_input_option,
        body={"values": values},
    ).execute()
    return result, updated


def sheets_append_values(
    credentials_json: str,
    spreadsheet_id: str,
    range_a1: str,
    values: list[list[Any]],
    value_input_option: str = "USER_ENTERED",
) -> tuple[dict[str, Any], str | None]:
    sheets, updated = _build_service("sheets", "v4", credentials_json)
    result = sheets.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        valueInputOption=value_input_option,
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()
    return result, updated
