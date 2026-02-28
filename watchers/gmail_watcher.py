"""
AI Employee Vault – Platinum Tier
Gmail Watcher — Needs_Action Feed

Module:   watchers/gmail_watcher.py
Version:  1.0.0

Responsibility:
    Polls the user's Gmail inbox for unread messages from allowed domains.
    Each qualifying email is converted to a structured .md file with YAML
    frontmatter and written atomically to vault/Needs_Action/email/.

    The Cloud Agent subsequently claims these files using the claim-by-move
    protocol (atomic rename to vault/In_Progress/cloud/) before processing
    them into task manifests in vault/Pending_Approval/.

YAML frontmatter written to each .md file:
    type:     email
    from:     <sender address or display name>
    subject:  <subject line>
    received: <ISO-8601 UTC>
    status:   pending

Graceful fallback (stub mode):
    If google-auth-oauthlib is not installed OR credentials.json is absent,
    the watcher logs the configuration gap and continues in stub mode —
    writing one synthetic "test" email per interval so the downstream vault
    pipeline can still be demonstrated end-to-end without live Gmail access.

CLI Usage (from project root):
    python -m watchers.gmail_watcher --daemon --interval 30
    python -m watchers.gmail_watcher --once
    python -m watchers.gmail_watcher --help
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import sys as _sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Bootstrap prompt_logger via direct file load.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent

_pl_spec = importlib.util.spec_from_file_location(
    "prompt_logger",
    _PROJECT_ROOT / "logging" / "prompt_logger.py",
)
_pl_mod = importlib.util.module_from_spec(_pl_spec)
_sys.modules.setdefault("prompt_logger", _pl_mod)
_pl_spec.loader.exec_module(_pl_mod)

PromptLogger = _pl_mod.PromptLogger
EventType    = _pl_mod.EventType
Component    = _pl_mod.Component

# ---------------------------------------------------------------------------
# Vault path
# ---------------------------------------------------------------------------

_VAULT_ROOT         = _PROJECT_ROOT / "vault"
_NEEDS_ACTION_EMAIL = _VAULT_ROOT / "Needs_Action" / "email"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CREDENTIALS_PATH = _PROJECT_ROOT / "credentials.json"
_TOKEN_PATH       = _PROJECT_ROOT / "token.json"
_SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly"]
_MAX_RESULTS      = 20

ALLOWED_DOMAINS: list[str] = [
    "gmail.com",
    "outlook.com",
    "company.com",
    "hotmail.com",
]

# ---------------------------------------------------------------------------
# Gmail API helpers (graceful import)
# ---------------------------------------------------------------------------


def _try_import_google() -> bool:
    """Return True if google-auth-oauthlib and googleapiclient are available."""
    try:
        import google.auth.transport.requests   # noqa: F401
        import google.oauth2.credentials        # noqa: F401
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
        from googleapiclient.discovery import build              # noqa: F401
        return True
    except ImportError:
        return False


def _build_gmail_service():
    """Authenticate and return a Gmail API service object."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(
                str(_CREDENTIALS_PATH), _SCOPES
            )
            creds = flow.run_local_server(port=0)
        _TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode(
                "utf-8", errors="replace"
            )
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return ""


def _sender_domain(sender: str) -> str:
    """Extract domain from 'Display Name <email@domain.com>' or 'email@domain.com'."""
    if "<" in sender and ">" in sender:
        sender = sender.split("<")[1].rstrip(">")
    return sender.split("@")[-1].lower().strip()


# ---------------------------------------------------------------------------
# GmailWatcher
# ---------------------------------------------------------------------------


class GmailWatcher:
    """
    Polls Gmail for unread messages and writes them to vault/Needs_Action/email/.

    Stub mode activates automatically when:
        - google-auth-oauthlib is not installed, OR
        - credentials.json is absent from the project root.

    In stub mode one synthetic email .md is written per cycle so the vault
    pipeline can be demonstrated without live Gmail credentials.

    Args:
        interval:   Seconds between polls. Default: 30.
        max_emails: Max emails to fetch per poll cycle. Default: 20.
    """

    def __init__(
        self,
        interval: float = 30.0,
        max_emails: int = _MAX_RESULTS,
    ) -> None:
        _NEEDS_ACTION_EMAIL.mkdir(parents=True, exist_ok=True)

        self._interval   = interval
        self._max_emails = max_emails
        self._seen: set[str] = set()   # message IDs seen this session
        self._google_ok  = _try_import_google()
        self._service    = None

        self._logger = PromptLogger(component=Component.CLOUD_AGENT)

        self._logger.log(
            event_type=EventType.SYSTEM_STARTUP,
            summary="Gmail Watcher initialised (v1.0.0)",
            detail=(
                f"Output: {_NEEDS_ACTION_EMAIL} | "
                f"Interval: {interval}s | "
                f"Google libs available: {self._google_ok} | "
                f"Credentials present: {_CREDENTIALS_PATH.exists()}"
            ),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def watch(self) -> None:
        """Poll continuously. Blocks until CTRL+C."""
        _print_banner(self._interval, self._google_ok)
        try:
            while True:
                self._poll()
                time.sleep(self._interval)
        except KeyboardInterrupt:
            print()
            print("[GmailWatcher] Interrupted. Shutting down.")
            self._logger.log(
                event_type=EventType.SYSTEM_SHUTDOWN,
                summary="Gmail Watcher shutdown via KeyboardInterrupt",
                detail="",
            )

    def poll_once(self) -> int:
        """Run one poll cycle. Returns number of .md files written."""
        return self._poll()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _poll(self) -> int:
        """One poll cycle — dispatches to live or stub mode."""
        if self._google_ok and _CREDENTIALS_PATH.exists():
            return self._poll_gmail()
        return self._poll_stub()

    def _poll_gmail(self) -> int:
        """Fetch unread Gmail messages and write .md files to Needs_Action/email/."""
        try:
            if self._service is None:
                self._service = _build_gmail_service()

            results = (
                self._service.users()
                .messages()
                .list(
                    userId="me",
                    labelIds=["INBOX", "UNREAD"],
                    maxResults=self._max_emails,
                )
                .execute()
            )
            messages = results.get("messages", [])
            written  = 0

            for msg_ref in messages:
                msg_id = msg_ref["id"]
                if msg_id in self._seen:
                    continue

                msg = (
                    self._service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                    .execute()
                )
                headers = {
                    h["name"].lower(): h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }
                sender  = headers.get("from", "unknown@unknown.com")
                subject = headers.get("subject", "(no subject)")
                body    = _extract_body(msg.get("payload", {}))[:1000]

                if _sender_domain(sender) not in ALLOWED_DOMAINS:
                    self._seen.add(msg_id)
                    continue

                received = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                self._write_email_file(
                    sender=sender,
                    subject=subject,
                    received=received,
                    body=body,
                    msg_id=msg_id,
                )
                self._seen.add(msg_id)
                written += 1

            return written

        except Exception as exc:
            self._logger.log(
                event_type=EventType.TASK_FAILED,
                summary="Gmail API error during poll",
                detail=str(exc),
            )
            print(f"[GmailWatcher] API error: {exc}")
            return 0

    def _poll_stub(self) -> int:
        """
        Stub mode: write one synthetic email file per cycle.

        Activated when google-auth-oauthlib is missing or credentials.json
        is absent. Allows the full vault pipeline to be demonstrated without
        live Gmail access.
        """
        received = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        stub_id  = str(uuid.uuid4())[:8]
        self._write_email_file(
            sender=f"stub-sender-{stub_id}@gmail.com",
            subject=f"[STUB] Synthetic email — {received}",
            received=received,
            body=(
                "This is a synthetic stub email generated because Gmail API "
                "credentials are not configured. Place credentials.json in the "
                "project root and install google-auth-oauthlib to enable live "
                "Gmail polling."
            ),
            msg_id=stub_id,
        )
        print(f"  [STUB] {received}  wrote synthetic email (no credentials.json)")
        return 1

    def _write_email_file(
        self,
        sender: str,
        subject: str,
        received: str,
        body: str,
        msg_id: str,
    ) -> Path:
        """
        Write a .md file with YAML frontmatter to vault/Needs_Action/email/.

        Uses write-tmp then atomic rename — the Cloud Agent will never see a
        partially-written file when scanning Needs_Action/.
        """
        safe_id    = msg_id.replace("/", "_").replace("\\", "_")[:32]
        filename   = f"email_{safe_id}.md"
        final_path = _NEEDS_ACTION_EMAIL / filename
        tmp_path   = _NEEDS_ACTION_EMAIL / (filename + ".tmp")

        # YAML frontmatter + body
        content = (
            f"---\n"
            f"type: email\n"
            f"from: {sender}\n"
            f"subject: {subject}\n"
            f"received: {received}\n"
            f"status: pending\n"
            f"---\n"
            f"\n"
            f"{body}\n"
        )

        tmp_path.write_text(content, encoding="utf-8")
        if final_path.exists():
            final_path.unlink()
        tmp_path.rename(final_path)

        self._logger.log(
            event_type=EventType.TASK_SUBMITTED,
            summary=f"Email file written to Needs_Action/email/: {subject[:60]}",
            detail=(
                f"From: {sender} | "
                f"File: {filename} | "
                f"Received: {received}"
            ),
            metadata_extra={
                "msg_id":  msg_id,
                "sender":  sender,
                "subject": subject[:120],
                "output":  str(final_path),
            },
        )
        print(
            f"  [EMAIL] {received}  "
            f"from={sender[:40]:<40}  "
            f"-> Needs_Action/email/{filename}"
        )
        return final_path


# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------


def _print_banner(interval: float, google_ok: bool) -> None:
    creds_status = (
        "configured" if _CREDENTIALS_PATH.exists()
        else "MISSING — stub mode active"
    )
    libs_status  = (
        "installed" if google_ok
        else "NOT installed — stub mode active"
    )
    print()
    print("=" * 64)
    print("  AI Employee Vault - Platinum Tier")
    print("  Gmail Watcher v1.0.0 — Needs_Action Feed")
    print("=" * 64)
    print(f"  Output       : vault/Needs_Action/email/")
    print(f"  Interval     : {interval}s")
    print(f"  Google libs  : {libs_status}")
    print(f"  Credentials  : {creds_status}")
    print(f"  Allowed domains: {', '.join(ALLOWED_DOMAINS)}")
    print("=" * 64)
    print("  Press CTRL+C to stop.")
    print()


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="watchers.gmail_watcher",
        description=(
            "AI Employee Vault - Platinum Tier: Gmail Watcher.\n"
            "Polls Gmail and writes emails to vault/Needs_Action/email/.\n"
            "Cloud Agent claims files from Needs_Action/ using atomic rename.\n"
            "Falls back to stub mode when credentials.json is absent."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Poll continuously (blocks until CTRL+C).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="Seconds between polls (default: 30).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one poll cycle and exit.",
    )

    args    = parser.parse_args()
    watcher = GmailWatcher(interval=args.interval)

    if args.once:
        count = watcher.poll_once()
        print(f"[GmailWatcher] Single poll complete. Files written: {count}")
    elif args.daemon:
        watcher.watch()
    else:
        parser.print_help()
        print()
        print("Hint: use --daemon or --once to run.")
