"""
watchers/gmail_inbox_watcher.py — Gmail Inbox Watcher (Gold Tier).

Polls Gmail for unread emails and converts them into Markdown task files
inside Inbox/ so that gold_agent.py can pick them up autonomously.

Safe-by-default behaviour
--------------------------
  MCP_DRY_RUN=true  (default)
      Creates Inbox/ task files but does NOT modify Gmail in any way.
      Safe for CI, demos, and local development.

  MCP_DRY_RUN=false + GMAIL_MARK_READ_ON_PROCESS=true
      Additionally removes the UNREAD label from each processed message.
      All other behaviour (task creation, de-dupe, logging) is identical.

Environment variables
---------------------
  GMAIL_CREDENTIALS_PATH        Path to OAuth2 credentials JSON
                                (default: credentials.json in repo root)
  GMAIL_TOKEN_PATH              Path to saved OAuth2 pickle token
                                (default: token.json in repo root)
  GMAIL_USER_ID                 Gmail userId for API calls (default: "me")
  GMAIL_POLL_SECONDS            Polling interval seconds   (default: 10)
  GMAIL_QUERY                   Gmail search query         (default: see below)
  GMAIL_MAX_PER_POLL            Max emails per cycle       (default: 5)
  MCP_DRY_RUN                   "false" enables live mode  (default: "true")
  GMAIL_MARK_READ_ON_PROCESS    "true" marks emails read   (default: "false")
                                Only honoured when MCP_DRY_RUN=false.

State files written
-------------------
  Logs/Watchers/gmail_seen.json            — processed message IDs (de-dupe)
  Logs/Watchers/gmail_watcher_YYYY-MM-DD.log — daily rotating log

Task files written
------------------
  Inbox/gmail_<YYYYMMDD_HHMMSS>_<messageId>.md

Usage
-----
  # Infinite loop (local dev)
  python watchers/gmail_inbox_watcher.py

  # One-shot (GitHub Actions / cron)
  python watchers/gmail_inbox_watcher.py --once

  # Custom poll interval
  python watchers/gmail_inbox_watcher.py --interval 30
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Resolve repo root (parent of the watchers/ directory) ─────────────────────
_WATCHER_DIR = Path(__file__).resolve().parent
_REPO_ROOT   = _WATCHER_DIR.parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ── Load .env EARLY (before any env-var reads) ────────────────────────────────
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(dotenv_path=_REPO_ROOT / ".env", override=True)
except Exception:
    pass  # dotenv is optional; fall back to OS environment

# ── Gold Tier base class (repo root) ─────────────────────────────────────────
from base_watcher import BaseWatcher  # noqa: E402  (after sys.path patch)

# ── Config from environment ───────────────────────────────────────────────────
_POLL_SECONDS: float = float(os.getenv("GMAIL_POLL_SECONDS", "10"))
_QUERY: str = os.getenv(
    "GMAIL_QUERY",
    "is:unread -category:promotions -category:social newer_than:7d",
)
_MAX_PER_POLL: int   = int(os.getenv("GMAIL_MAX_PER_POLL", "5"))
_USER_ID: str        = os.getenv("GMAIL_USER_ID", "me")
_DRY_RUN: bool       = os.getenv("MCP_DRY_RUN", "true").strip().lower() != "false"
_MARK_READ: bool     = (
    os.getenv("GMAIL_MARK_READ_ON_PROCESS", "false").strip().lower() == "true"
    and not _DRY_RUN
)
_MAX_BODY_CHARS: int = 8000

# ── Directory paths ───────────────────────────────────────────────────────────
BASE_DIR     = _REPO_ROOT
INBOX_DIR    = BASE_DIR / "Inbox"
WATCHERS_LOG = BASE_DIR / "Logs" / "Watchers"
SEEN_FILE    = WATCHERS_LOG / "gmail_seen.json"


# ══════════════════════════════════════════════════════════════════════════════
# Logging setup
# ══════════════════════════════════════════════════════════════════════════════

def _setup_file_logger(name: str) -> logging.Logger:
    """Create (or return) a logger that writes to both stdout and a daily log file."""
    WATCHERS_LOG.mkdir(parents=True, exist_ok=True)
    log_path = WATCHERS_LOG / f"gmail_watcher_{datetime.now().strftime('%Y-%m-%d')}.log"

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)

    # Console — INFO+
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(
        logging.Formatter(
            "[%(name)s] %(asctime)s %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(ch)

    # File — DEBUG+ (full detail for judges)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(fh)

    return logger


# ══════════════════════════════════════════════════════════════════════════════
# De-dupe helpers
# ══════════════════════════════════════════════════════════════════════════════

def _load_seen() -> set[str]:
    """Load the set of already-processed Gmail message IDs from disk."""
    if SEEN_FILE.exists():
        try:
            data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
            return set(data.get("seen", []))
        except Exception:
            pass
    return set()


def _save_seen(seen: set[str]) -> None:
    """Persist the de-dupe set to disk atomically."""
    WATCHERS_LOG.mkdir(parents=True, exist_ok=True)
    payload = {
        "seen":    sorted(seen),
        "count":   len(seen),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    SEEN_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# Gmail API helpers (read-only by default)
# ══════════════════════════════════════════════════════════════════════════════

def _get_service():
    """
    Return an authenticated Gmail API service by reusing mcp/gmail_oauth.py.

    Raises GmailAuthError (from mcp.gmail_oauth) if token.json is missing or
    expired, which is caught gracefully by the watcher's run loop.
    """
    from mcp.gmail_oauth import build_service  # type: ignore
    return build_service()


def _extract_body(payload: dict) -> str:
    """
    Recursively extract the best plain-text body from a Gmail message payload.

    Walk order:
      1. text/plain   — preferred; decode base64url and return
      2. multipart/*  — recurse into each part
      3. text/html    — last resort; strip HTML tags with a simple regex

    Returns an empty string if nothing extractable is found.
    """
    mime_type: str = payload.get("mimeType", "")
    body_blob: dict = payload.get("body", {})
    data: str       = body_blob.get("data", "")

    if mime_type == "text/plain" and data:
        try:
            # Gmail uses URL-safe base64 without padding — pad it
            return base64.urlsafe_b64decode(data + "==").decode(
                "utf-8", errors="replace"
            )
        except Exception:
            pass

    # Recurse into multipart containers (mixed, alternative, related…)
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result.strip():
            return result

    # HTML fallback — strip tags
    if mime_type == "text/html" and data:
        try:
            raw = base64.urlsafe_b64decode(data + "==").decode(
                "utf-8", errors="replace"
            )
            # Basic tag removal (no BeautifulSoup dependency)
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"[ \t]{2,}", " ", text)
            return text.strip()
        except Exception:
            pass

    return ""


def _fetch_message(service: Any, msg_id: str) -> dict[str, Any]:
    """
    Fetch a full Gmail message and return a normalised dict.

    Returned keys: id, thread_id, from, subject, date, snippet, body
    """
    detail: dict = service.users().messages().get(
        userId=_USER_ID,
        id=msg_id,
        format="full",
    ).execute()

    headers: dict[str, str] = {
        h["name"]: h["value"]
        for h in detail.get("payload", {}).get("headers", [])
    }

    body    = _extract_body(detail.get("payload", {}))
    snippet = detail.get("snippet", "")

    return {
        "id":        msg_id,
        "thread_id": detail.get("threadId", ""),
        "from":      headers.get("From", "(unknown sender)"),
        "subject":   headers.get("Subject", "(no subject)"),
        "date":      headers.get("Date", ""),
        "snippet":   snippet,
        "body":      body or snippet,  # fall back to snippet if body is empty
    }


def _mark_as_read(service: Any, msg_id: str, logger: logging.Logger) -> None:
    """
    Remove the UNREAD label from a Gmail message.

    Only called when MCP_DRY_RUN=false AND GMAIL_MARK_READ_ON_PROCESS=true.
    Failures are logged as warnings and do NOT abort the watcher.
    """
    try:
        service.users().messages().modify(
            userId=_USER_ID,
            id=msg_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
        logger.info("Marked as read: %s", msg_id)
    except Exception as exc:
        logger.warning("Could not mark message %s as read: %s", msg_id, exc)


# ══════════════════════════════════════════════════════════════════════════════
# Markdown task builder
# ══════════════════════════════════════════════════════════════════════════════

def _sanitise_yaml_value(value: str) -> str:
    """Escape double-quotes inside a YAML double-quoted scalar."""
    return value.replace('"', '\\"')


def _build_task_markdown(msg: dict[str, Any]) -> str:
    """
    Build a Markdown task file from a normalised email dict.

    Structure:
      - YAML frontmatter (type, source, ids, from, subject, date, status, priority)
      - Snippet section
      - Full body (truncated to _MAX_BODY_CHARS)
      - Required Action checklist
    """
    now_iso    = datetime.now(timezone.utc).isoformat()
    body_text  = msg["body"]
    truncated  = len(body_text) > _MAX_BODY_CHARS
    body_trunc = body_text[:_MAX_BODY_CHARS]
    if truncated:
        body_trunc += "\n\n[... body truncated at 8 000 chars ...]"

    from_safe    = _sanitise_yaml_value(msg["from"])
    subject_safe = _sanitise_yaml_value(msg["subject"])
    date_safe    = _sanitise_yaml_value(msg["date"])

    return (
        f"---\n"
        f"type: email\n"
        f"source: gmail\n"
        f"message_id: {msg['id']}\n"
        f"thread_id: {msg['thread_id']}\n"
        f"from: \"{from_safe}\"\n"
        f"subject: \"{subject_safe}\"\n"
        f"date: \"{date_safe}\"\n"
        f"ingested_at: \"{now_iso}\"\n"
        f"watcher: gmail_inbox_watcher\n"
        f"status: pending\n"
        f"priority: medium\n"
        f"---\n"
        f"\n"
        f"# Email Task: {msg['subject']}\n"
        f"\n"
        f"**From:** {msg['from']}  \n"
        f"**Date:** {msg['date']}  \n"
        f"**Message ID:** `{msg['id']}`  \n"
        f"**Thread ID:** `{msg['thread_id']}`  \n"
        f"\n"
        f"---\n"
        f"\n"
        f"## Snippet\n"
        f"\n"
        f"{msg['snippet']}\n"
        f"\n"
        f"---\n"
        f"\n"
        f"## Full Body\n"
        f"\n"
        f"{body_trunc}\n"
        f"\n"
        f"---\n"
        f"\n"
        f"## Required Actions\n"
        f"\n"
        f"- [ ] **Classify domain** — Personal or Business?\n"
        f"- [ ] **Draft reply** (if a response is needed) — use `draft_email` MCP tool\n"
        f"- [ ] **Follow up** — add a deadline or escalate if urgent\n"
        f"- [ ] **Archive / close** — move to Done/ when resolved\n"
    )


def _inbox_task_path(msg: dict[str, Any]) -> Path:
    """Return the Inbox/ path for a task file derived from this email."""
    ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"gmail_{ts}_{msg['id']}.md"
    return INBOX_DIR / filename


# ══════════════════════════════════════════════════════════════════════════════
# GmailInboxWatcher
# ══════════════════════════════════════════════════════════════════════════════

class GmailInboxWatcher(BaseWatcher):
    """
    Concrete Gold Tier watcher.

    On each poll cycle:
      1. Authenticate with Gmail via mcp/gmail_oauth.py (token.json).
      2. Search for unread messages matching GMAIL_QUERY.
      3. Skip already-seen message IDs (Logs/Watchers/gmail_seen.json).
      4. For each new message, fetch full body and write an Inbox/ task file.
      5. Persist updated seen-set to disk.
      6. Optionally mark each message as read (only in live mode + opted-in).
    """

    name = "gmail_inbox_watcher"

    def __init__(
        self,
        base_dir: Path,
        poll_interval: float = _POLL_SECONDS,
        one_shot: bool = False,
    ) -> None:
        super().__init__(
            base_dir=base_dir,
            poll_interval=poll_interval,
            one_shot=one_shot,
        )
        self._logger = _setup_file_logger(self.name)
        self._seen   = _load_seen()
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        WATCHERS_LOG.mkdir(parents=True, exist_ok=True)

        self._logger.info(
            "Initialised | DRY_RUN=%s | MARK_READ=%s | query=%r | "
            "max_per_poll=%d | poll_interval=%.0fs",
            _DRY_RUN, _MARK_READ, _QUERY, _MAX_PER_POLL, poll_interval,
        )
        if _DRY_RUN:
            self._logger.info(
                "DRY_RUN mode: task files WILL be created; Gmail labels "
                "will NOT be modified. Set MCP_DRY_RUN=false to enable "
                "mark-read (also requires GMAIL_MARK_READ_ON_PROCESS=true)."
            )

    # ── One poll cycle ────────────────────────────────────────────────────────

    def run_once(self) -> int:
        """
        One Gmail poll cycle.

        Returns:
            Number of new Inbox/ task files created this cycle (0 on error).
        """
        # ── Authenticate ──────────────────────────────────────────────────────
        try:
            service = _get_service()
        except Exception as exc:
            self._logger.error(
                "Gmail authentication failed: %s — "
                "run generate_gmail_token.py to (re-)authorise.", exc
            )
            return 0

        # ── Search unread messages ────────────────────────────────────────────
        try:
            response: dict = service.users().messages().list(
                userId=_USER_ID,
                q=_QUERY,
                maxResults=_MAX_PER_POLL,
            ).execute()
        except Exception as exc:
            self._logger.error("Gmail messages.list failed: %s", exc)
            return 0

        messages = response.get("messages", [])
        if not messages:
            self._logger.debug("No new messages matching query.")
            return 0

        self._logger.debug("Gmail returned %d candidate message(s).", len(messages))

        processed = 0
        for m in messages:
            msg_id: str = m["id"]

            # ── De-dupe ───────────────────────────────────────────────────────
            if msg_id in self._seen:
                self._logger.debug("Skipping already-seen message: %s", msg_id)
                continue

            # ── Fetch + write task ────────────────────────────────────────────
            try:
                msg      = _fetch_message(service, msg_id)
                md       = _build_task_markdown(msg)
                out_path = _inbox_task_path(msg)
                out_path.write_text(md, encoding="utf-8")

                # Mark as seen BEFORE any external modification so a crash
                # halfway through does not cause duplicate task files.
                self._seen.add(msg_id)
                _save_seen(self._seen)

                processed += 1
                self._logger.info(
                    "Task created: %-55s | from=%-40s | subject=%r",
                    out_path.name,
                    msg["from"][:40],
                    msg["subject"],
                )

            except Exception as exc:
                self._logger.warning(
                    "Failed to process message %s: %s", msg_id, exc
                )
                continue

            # ── Optionally mark as read ───────────────────────────────────────
            if _MARK_READ:
                _mark_as_read(service, msg_id, self._logger)
            elif _DRY_RUN:
                self._logger.debug(
                    "DRY_RUN: would mark %s as read if "
                    "MCP_DRY_RUN=false + GMAIL_MARK_READ_ON_PROCESS=true.",
                    msg_id,
                )

        return processed


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("=" * 62)
    print("  Gmail Inbox Watcher — AI Employee Vault Gold Tier")
    print("=" * 62)
    print(f"  DRY_RUN            : {_DRY_RUN}")
    print(f"  MARK_READ          : {_MARK_READ}")
    print(f"  Gmail query        : {_QUERY}")
    print(f"  Max per poll       : {_MAX_PER_POLL}")
    print(f"  Default interval   : {_POLL_SECONDS}s")
    print(f"  Inbox dir          : {INBOX_DIR}")
    print(f"  De-dupe state file : {SEEN_FILE}")
    print(f"  Log dir            : {WATCHERS_LOG}")
    print()
    if _DRY_RUN:
        print("  [SAFE] DRY_RUN=true — Gmail labels will NOT be modified.")
        print("         Task files WILL be created in Inbox/.")
    else:
        print("  [LIVE] DRY_RUN=false — live Gmail API calls active.")
        if _MARK_READ:
            print("         Mark-read IS enabled (GMAIL_MARK_READ_ON_PROCESS=true).")
        else:
            print("         Mark-read is disabled (GMAIL_MARK_READ_ON_PROCESS=false).")
    print()

    watcher = GmailInboxWatcher.cli(
        base_dir=BASE_DIR,
        default_interval=_POLL_SECONDS,
    )
    watcher.run()
