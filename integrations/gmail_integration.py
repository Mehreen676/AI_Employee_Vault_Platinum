"""
AI Employee Vault – Platinum Tier
Gmail Integration  |  integrations/gmail_integration.py

Real Gmail API watcher with OAuth 2.0 + stub fallback.

Behaviour:
  - If credentials.json + google-auth-oauthlib are available → real Gmail API
  - Otherwise → stub mode (generates synthetic email tasks)
  - Writes each email as a vault task to: vault/Needs_Action/email/
  - Appends evidence to: Evidence/GMAIL_INTEGRATION_LOG.md

Usage (standalone):
    python -m integrations.gmail_integration --poll 30
    python -m integrations.gmail_integration --once
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Path helpers ───────────────────────────────────────────────────────────────

def _vault_dir() -> Path:
    return Path(os.getenv("VAULT_DIR", str(Path(__file__).resolve().parent.parent / "vault")))

def _evidence_dir() -> Path:
    vd = _vault_dir()
    return Path(os.getenv("EVIDENCE_OUT_DIR", str(Path(__file__).resolve().parent.parent / "Evidence")))

def _credentials_path() -> Path:
    return Path(__file__).resolve().parent.parent / "credentials.json"

def _token_path() -> Path:
    return Path(__file__).resolve().parent.parent / "token.json"


# ── Gmail OAuth client ─────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def _build_gmail_service():
    """Return an authenticated Gmail API service, or None if unavailable."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        log.info("[gmail] google-auth-oauthlib not installed; using stub mode")
        return None

    creds_path = _credentials_path()
    token_path = _token_path()

    if not creds_path.exists():
        log.info("[gmail] credentials.json not found; using stub mode")
        return None

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                log.warning("[gmail] token refresh failed: %s", exc)
                return None
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as exc:
                log.warning("[gmail] OAuth flow failed: %s", exc)
                return None
        try:
            token_path.write_text(creds.to_json(), encoding="utf-8")
        except OSError:
            pass

    try:
        return build("gmail", "v1", credentials=creds)
    except Exception as exc:
        log.warning("[gmail] API build failed: %s", exc)
        return None


# ── Email → task conversion ────────────────────────────────────────────────────

_ALLOWED_DOMAINS = {"gmail.com", "outlook.com", "company.com", "hotmail.com"}

def _is_allowed_sender(sender: str) -> bool:
    domain = sender.lower().split("@")[-1].split(">")[0].strip()
    return domain in _ALLOWED_DOMAINS


def _email_to_task(subject: str, sender: str, body: str, msg_id: str) -> dict[str, Any]:
    return {
        "id":        str(uuid.uuid4()),
        "task_type": "email_processing",
        "source":    "gmail_watcher",
        "msg_id":    msg_id,
        "from":      sender,
        "subject":   subject,
        "body":      body[:2000],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status":    "pending",
    }


def _write_vault_task(task: dict[str, Any]) -> Path:
    """Write a task JSON to vault/Needs_Action/email/ using atomic tmp→rename."""
    email_dir = _vault_dir() / "Needs_Action" / "email"
    email_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"email_{ts}_{task['id'][:8]}.json"
    dest = email_dir / filename
    tmp  = email_dir / f".tmp_{filename}"

    tmp.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.rename(dest)
    return dest


# ── Evidence log ───────────────────────────────────────────────────────────────

def _log_evidence(event: str, detail: str) -> None:
    ev_dir = _evidence_dir()
    ev_dir.mkdir(parents=True, exist_ok=True)
    log_path = ev_dir / "GMAIL_INTEGRATION_LOG.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(f"\n### {ts} — {event}\n{detail}\n")


# ── Real Gmail polling ─────────────────────────────────────────────────────────

_processed_ids: set[str] = set()


def _fetch_real_emails(service) -> list[dict[str, Any]]:
    """Fetch unread messages from Gmail inbox."""
    tasks: list[dict[str, Any]] = []
    try:
        result = service.users().messages().list(
            userId="me", q="is:unread in:inbox", maxResults=10
        ).execute()
        messages = result.get("messages", [])
    except Exception as exc:
        log.warning("[gmail] list messages failed: %s", exc)
        return tasks

    for msg_meta in messages:
        msg_id = msg_meta["id"]
        if msg_id in _processed_ids:
            continue
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
        except Exception as exc:
            log.warning("[gmail] fetch message %s failed: %s", msg_id, exc)
            continue

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "(no subject)")
        sender  = headers.get("From", "unknown@unknown.com")

        if not _is_allowed_sender(sender):
            log.info("[gmail] skipping sender %s (domain not allowed)", sender)
            _processed_ids.add(msg_id)
            continue

        # Extract plain-text body
        body = ""
        payload = msg.get("payload", {})
        parts = payload.get("parts", [payload])
        for part in parts:
            if part.get("mimeType") == "text/plain":
                import base64
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                break

        task = _email_to_task(subject, sender, body, msg_id)
        tasks.append(task)
        _processed_ids.add(msg_id)

        # Mark as read
        try:
            service.users().messages().modify(
                userId="me", id=msg_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
        except Exception:
            pass

    return tasks


# ── Stub mode ──────────────────────────────────────────────────────────────────

_stub_templates = [
    ("Invoice approval needed",   "accounts@company.com",  "Please approve the attached invoice #INV-2026-001 for $4,500 before end of day."),
    ("Meeting request: Q2 review", "ceo@company.com",       "Can we schedule a Q2 business review for next Tuesday at 2 PM?"),
    ("CRM update required",        "sales@company.com",     "Please update the CRM entry for client Acme Corp with the latest deal status."),
    ("Social media post approval", "marketing@company.com", "Reviewing the draft LinkedIn post about our new AI features. Please approve."),
    ("Urgent: Support ticket",     "support@company.com",   "Customer #2045 has reported a critical issue with the payment gateway. Please investigate."),
]

_stub_idx: int = 0


def _fetch_stub_emails() -> list[dict[str, Any]]:
    global _stub_idx
    template = _stub_templates[_stub_idx % len(_stub_templates)]
    _stub_idx += 1
    subject, sender, body = template
    return [_email_to_task(subject, sender, body, f"stub_{uuid.uuid4().hex[:8]}")]


# ── Main loop ──────────────────────────────────────────────────────────────────

def run_once(service=None) -> int:
    """Process one batch. Returns count of tasks written."""
    if service is None:
        service = _build_gmail_service()

    if service is not None:
        emails = _fetch_real_emails(service)
        mode = "real"
    else:
        emails = _fetch_stub_emails()
        mode = "stub"

    count = 0
    for task in emails:
        dest = _write_vault_task(task)
        log.info("[gmail/%s] wrote task %s → %s", mode, task["id"], dest.name)
        _log_evidence(
            f"Email task ingested ({mode})",
            f"- **Subject:** {task.get('subject')}\n"
            f"- **From:** {task.get('from')}\n"
            f"- **Task ID:** `{task['id']}`\n"
            f"- **Vault file:** `{dest.name}`\n"
            f"- **Mode:** {mode}"
        )
        count += 1
    return count


def run_loop(interval: float = 30.0) -> None:
    """Infinite polling loop."""
    log.info("[gmail] starting poll loop (interval=%.0fs)", interval)
    service = _build_gmail_service()
    if service:
        log.info("[gmail] Real Gmail API authenticated — live mode")
    else:
        log.info("[gmail] Stub mode — no credentials.json found")

    _log_evidence(
        "Gmail watcher started",
        f"- **Mode:** {'real' if service else 'stub'}\n"
        f"- **Poll interval:** {interval}s\n"
        f"- **Vault target:** `vault/Needs_Action/email/`"
    )

    while True:
        try:
            run_once(service)
        except Exception as exc:
            log.warning("[gmail] cycle error: %s", exc)
        time.sleep(interval)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-8s %(message)s")
    parser = argparse.ArgumentParser(description="AI Vault Gmail Integration")
    parser.add_argument("--poll",    type=float, default=30.0, metavar="SECS",
                        help="Polling interval in seconds (default: 30)")
    parser.add_argument("--once",    action="store_true",
                        help="Run one cycle and exit")
    args = parser.parse_args()

    if args.once:
        n = run_once()
        print(f"[gmail] Processed {n} email(s)")
    else:
        run_loop(interval=args.poll)
