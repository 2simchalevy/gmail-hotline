"""
gmail_helper.py

Handles Google OAuth authentication and fetching the newest unread
email from the user's Gmail inbox (subject, sender, and a short snippet).

This version supports two storage modes for the OAuth token, chosen by
the GCS_BUCKET environment variable:

  - Local mode (GCS_BUCKET not set): credentials.json and token.json
    are read from/written to the local filesystem, next to this file.
    Use this for running on your own computer.

  - Cloud Storage mode (GCS_BUCKET set): credentials.json and token.json
    are read from/written to the named Cloud Storage bucket. Use this
    when running on Cloud Run, where the local filesystem does not
    persist across restarts.

Usage:
    from gmail_helper import get_latest_unread_email

    email = get_latest_unread_email()
    if email:
        print(email["subject"], email["sender"], email["snippet"])
    else:
        print("No unread email.")
"""

import os
import json
from email.utils import parseaddr

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from googleapiclient.discovery import build

# Read-only scope: we only need to read messages, never send or modify.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILENAME = "credentials.json"
TOKEN_FILENAME = "token.json"

LOCAL_CREDENTIALS_PATH = os.path.join(BASE_DIR, CREDENTIALS_FILENAME)
LOCAL_TOKEN_PATH = os.path.join(BASE_DIR, TOKEN_FILENAME)

GCS_BUCKET = os.environ.get("GCS_BUCKET")  # e.g. "gmail-hotline-tokens"


# ---------------------------------------------------------------------
# Storage backend: local filesystem or Google Cloud Storage
# ---------------------------------------------------------------------

def _gcs_bucket():
    from google.cloud import storage
    client = storage.Client()
    return client.bucket(GCS_BUCKET)


def _read_text(filename: str):
    """Return the file's text content, or None if it doesn't exist."""
    if GCS_BUCKET:
        blob = _gcs_bucket().blob(filename)
        if not blob.exists():
            return None
        return blob.download_as_text()
    else:
        path = os.path.join(BASE_DIR, filename)
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            return f.read()


def _write_text(filename: str, content: str):
    if GCS_BUCKET:
        blob = _gcs_bucket().blob(filename)
        blob.upload_from_string(content)
    else:
        path = os.path.join(BASE_DIR, filename)
        with open(path, "w") as f:
            f.write(content)


# ---------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------

def _load_cached_credentials():
    """Return valid cached credentials (refreshing if needed), or None."""
    creds = None

    token_text = _read_text(TOKEN_FILENAME)
    if token_text:
        creds = Credentials.from_authorized_user_info(
            json.loads(token_text), SCOPES
        )

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _write_text(TOKEN_FILENAME, creds.to_json())
        return creds

    return None


def _get_credentials():
    """Load cached credentials, refreshing as needed.

    This NEVER launches an interactive login flow itself — on a server
    (Cloud Run or otherwise) that must instead go through the web-based
    /authorize and /oauth2callback routes in server.py, which is the
    one-time step that creates token.json. If no valid token exists,
    this raises an error rather than trying to open a browser.
    """
    creds = _load_cached_credentials()
    if creds:
        return creds

    raise RuntimeError(
        "No valid Gmail token found. Visit /authorize on this server "
        "once to complete the one-time Gmail login."
    )


def _redirect_uri():
    """The OAuth redirect URI for the web-based authorization flow.

    Must exactly match a redirect URI registered on the 'Web application'
    OAuth client in Google Cloud Console, e.g.
    https://your-service-xyz.a.run.app/oauth2callback
    """
    uri = os.environ.get("OAUTH_REDIRECT_URI")
    if not uri:
        raise RuntimeError(
            "OAUTH_REDIRECT_URI environment variable is not set. It must be "
            "set to this service's own URL + /oauth2callback, e.g. "
            "https://your-service-xyz.a.run.app/oauth2callback"
        )
    return uri


PKCE_VERIFIER_FILENAME = "pkce_verifier.txt"


def build_auth_flow(state=None, code_verifier=None):
    """Build a google_auth_oauthlib Flow for the web-based OAuth dance.

    Reads the OAuth client config from CREDENTIALS_FILENAME (a 'Web
    application' type client JSON, downloaded from Google Cloud Console),
    stored the same way as token.json (locally or in the GCS bucket).

    google_auth_oauthlib uses PKCE by default, which means a random
    code_verifier is generated when the Flow object is created. Since
    /authorize and /oauth2callback are two separate HTTP requests (and on
    Cloud Run, quite possibly two separate Flow objects / even container
    instances), that verifier must be persisted somewhere in between and
    passed back in here on the callback, or Google will reject the token
    exchange with "Missing code verifier".
    """
    credentials_text = _read_text(CREDENTIALS_FILENAME)
    if not credentials_text:
        raise FileNotFoundError(
            f"Missing {CREDENTIALS_FILENAME}. Upload your OAuth 'Web "
            "application' client JSON (downloaded from Google Cloud "
            "Console) to the same place token.json is stored."
        )

    client_config = json.loads(credentials_text)
    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, state=state
    )
    flow.redirect_uri = _redirect_uri()
    if code_verifier:
        flow.code_verifier = code_verifier
    return flow


def save_pkce_verifier(code_verifier: str):
    """Persist the PKCE code_verifier generated in /authorize."""
    _write_text(PKCE_VERIFIER_FILENAME, code_verifier)


def load_pkce_verifier():
    """Retrieve the PKCE code_verifier saved by save_pkce_verifier()."""
    return _read_text(PKCE_VERIFIER_FILENAME)


def save_credentials_from_flow(flow):
    """After the OAuth callback, fetch and persist the token."""
    creds = flow.credentials
    _write_text(TOKEN_FILENAME, creds.to_json())
    return creds


def is_authorized():
    """True if a valid (or refreshable) Gmail token is already stored."""
    return _load_cached_credentials() is not None


def _get_service():
    creds = _get_credentials()
    return build("gmail", "v1", credentials=creds)


def _decode_snippet(snippet: str) -> str:
    """Gmail already HTML-unescapes snippets; just trim whitespace."""
    return " ".join(snippet.split())


def get_latest_unread_email():
    """
    Return a dict with 'id', 'subject', 'sender', and 'snippet' for the
    most recent unread message in the inbox, or None if there are no
    unread messages.
    """
    service = _get_service()

    results = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=1)
        .execute()
    )
    messages = results.get("messages", [])
    if not messages:
        return None

    msg_id = messages[0]["id"]
    message = (
        service.users()
        .messages()
        .get(userId="me", id=msg_id, format="metadata",
             metadataHeaders=["Subject", "From"])
        .execute()
    )

    headers = {h["name"]: h["value"] for h in message["payload"]["headers"]}
    subject = headers.get("Subject", "(no subject)")
    raw_sender = headers.get("From", "(unknown sender)")
    sender_name, sender_email = parseaddr(raw_sender)
    sender = sender_name or sender_email

    snippet = _decode_snippet(message.get("snippet", ""))

    return {
        "id": msg_id,
        "subject": subject,
        "sender": sender,
        "snippet": snippet,
    }


def mark_as_read(message_id: str):
    """Optionally remove the UNREAD label after it's been read aloud."""
    service = _get_service()
    service.users().messages().modify(
        userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()


if __name__ == "__main__":
    # Quick manual test: run `python gmail_helper.py`
    email = get_latest_unread_email()
    if email:
        print("Subject:", email["subject"])
        print("From:", email["sender"])
        print("Snippet:", email["snippet"])
    else:
        print("No unread emails found.")
    def save_pkce_verifier(code_verifier: str):  
