"""
Gmail Watcher – ingests unread inbox emails into Inbox/ as task files.

Reads UNREAD INBOX emails via Gmail API, filters to allowed senders,
creates markdown task files in Inbox/, and logs to run_log.md.
Skips duplicates if a file for the same messageId exists in Inbox/ or Done/.

Optional: can mark processed emails as READ (requires gmail.modify scope).
Run locally only (requires OAuth credentials). Not used in cloud workflow.

Usage:
    C:\\Users\\Zohair\\AppData\\Local\\Programs\\Python\\Python314\\python.exe gmail_watcher.py
"""

from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime, timezone

# --------------- Gmail API imports ---------------
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    print("Gmail API libraries not installed. Run:")
    print("  python -m pip install google-auth google-auth-oauthlib google-api-python-client")
    raise SystemExit(1)

# --------------- Config ---------------
# Safe default (read-only). If you want auto-mark-as-read, change to gmail.modify.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
# SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]  # <-- enable if you want mark-as-read

MARK_AS_READ = False  # set True only if using gmail.modify scope

ALLOWED_DOMAINS = {"google.com", "github.com", "microsoft.com", "azure.com"}

BASE_DIR = Path(__file__).resolve().parent
INBOX = BASE_DIR / "Inbox"
DONE = BASE_DIR / "Done"
RUN_LOG = BASE_DIR / "run_log.md"


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def utc_file_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def append_log(text: str) -> None:
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(RUN_LOG, "a", encoding="utf-8") as f:
        f.write(text)


def extract_domain(email_addr: str) -> str:
    """Extract domain from 'Name <user@domain.com>' or 'user@domain.com'."""
    match = re.search(r"@([\w.-]+)", email_addr)
    return match.group(1).lower() if match else ""


def domain_allowed(email_addr: str) -> bool:
    domain = extract_domain(email_addr)
    return any(domain == d or domain.endswith("." + d) for d in ALLOWED_DOMAINS)


def get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def file_exists_for_id(msg_id: str) -> bool:
    """Check if a file for this messageId already exists in Inbox/ or Done/."""
    suffix = f"_{msg_id}.md"
    for folder in [INBOX, DONE]:
        if folder.is_dir():
            for f in folder.glob(f"*{suffix}"):
                return True
    return False


def auth_gmail():
    """Authorize and return Gmail service."""
    creds = None
    token_path = BASE_DIR / "token.json"
    creds_path = BASE_DIR / "credentials.json"

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                print("ERROR: credentials.json not found.")
                print("Download OAuth JSON and rename to credentials.json in repo root.")
                raise SystemExit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def mark_read(service, msg_id: str) -> None:
    """Remove UNREAD label (requires gmail.modify)."""
    if not MARK_AS_READ:
        return
    try:
        service.users().messages().modify(
            userId="me",
            id=msg_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
    except Exception as e:
        append_log(f"{utc_ts()} - Gmail: mark_read_failed | id={msg_id} | err={e}\n")


def main() -> None:
    print("=== Gmail Watcher Running ===")

    INBOX.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)

    service = auth_gmail()

    results = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        q="is:unread",
        maxResults=10,
    ).execute()

    messages = results.get("messages", [])

    if not messages:
        print("No unread inbox messages found.")
        append_log(f"{utc_ts()} - Gmail: no_unread\n")
        return

    ingested = 0
    for msg in messages:
        msg_id = msg["id"]
        detail = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        headers = detail.get("payload", {}).get("headers", [])

        sender = get_header(headers, "From")
        subject = get_header(headers, "Subject")
        date = get_header(headers, "Date")
        snippet = detail.get("snippet", "")

        # Filter by allowed domains
        if not domain_allowed(sender):
            append_log(f"{utc_ts()} - Gmail: skipped_domain | id={msg_id} | from={sender}\n")
            continue

        # Duplicate check
        if file_exists_for_id(msg_id):
            append_log(f"{utc_ts()} - Gmail: duplicate_skipped | id={msg_id} | subject={subject}\n")
            continue

        filename = f"email_{utc_file_ts()}_{msg_id}.md"
        content = (
            "# Email Task\n\n"
            f"From: {sender}\n"
            f"Subject: {subject}\n"
            f"Date: {date}\n\n"
            "## Snippet\n"
            f"{snippet}\n\n"
            "Source: Gmail\n"
            "Status: New\n"
        )

        (INBOX / filename).write_text(content, encoding="utf-8")

        append_log(f"{utc_ts()} - Gmail ingested: {filename} | from={sender} | subject={subject}\n")
        ingested += 1

        # Optional: mark email as read so it won't reappear
        mark_read(service, msg_id)

    print(f"=== Gmail Watcher Done ({ingested} ingested) ===")


if __name__ == "__main__":
    main()
