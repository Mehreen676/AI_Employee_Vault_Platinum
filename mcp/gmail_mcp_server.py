"""
mcp/gmail_mcp_server.py — Gmail MCP Server (Gold Tier).

Exposes three tools registered in the MCP tool registry:

    draft_email    Create a Gmail draft (does NOT send).
    send_email     Send an email via Gmail API.
    search_email   Search Gmail inbox with a query string.

DRY_RUN mode (MCP_DRY_RUN=true, the default)
---------------------------------------------
No real Gmail API calls are made.  Full intent is logged via audit_logger
and written to Logs/<today>.json.  Safe for CI, staging, and demos.

Live mode (MCP_DRY_RUN=false)
------------------------------
Real calls via the Gmail v1 REST API authenticated with OAuth2.
Requires a valid token.json — run generate_gmail_token.py once to create it.

Environment variables
---------------------
    MCP_DRY_RUN             "false" to enable live calls (default: "true")
    GMAIL_CREDENTIALS_PATH  Path to OAuth2 credentials JSON (default: credentials.json)
    GMAIL_TOKEN_PATH        Path to saved OAuth2 token     (default: token.json)
    GMAIL_USER_ID           Gmail userId for API calls     (default: "me")
    GMAIL_DEFAULT_FROM      Display name on outgoing email (default: "AI Employee Vault")
    GMAIL_SCOPES            Comma-separated OAuth2 scopes  (default: compose+readonly)

See docs/GMAIL_SETUP.md for complete setup instructions.
"""

from __future__ import annotations

import base64
import email.mime.text
import os
from datetime import datetime, timezone

from audit_logger import log_action
from mcp.registry import DRY_RUN, register

SERVER_NAME  = "gmail_mcp_server"
_USER_ID     = os.getenv("GMAIL_USER_ID", "me")
_DEFAULT_FROM = os.getenv("GMAIL_DEFAULT_FROM", "AI Employee Vault")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_mime(to: str, subject: str, body: str, from_name: str = "") -> email.mime.text.MIMEText:
    """Assemble a plain-text MIME message."""
    msg = email.mime.text.MIMEText(body, "plain")
    msg["to"]      = to
    msg["subject"] = subject
    if from_name:
        msg["from"] = from_name
    return msg


def _mime_to_raw_b64(msg: email.mime.text.MIMEText) -> str:
    """Encode a MIME message as URL-safe base64 (required by Gmail API)."""
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _get_service():
    """Return an authenticated Gmail API service; raises GmailAuthError on failure."""
    from mcp.gmail_oauth import build_service
    return build_service()


def _error_result(action_type: str, dry_run: bool, message: str, task_file: str) -> dict:
    now = _now()
    log_action(
        SERVER_NAME, f"{action_type}_error",
        {"task_file": task_file, "error": message},
        success=False,
    )
    return {
        "server":      SERVER_NAME,
        "action_type": action_type,
        "dry_run":     dry_run,
        "result":      "error",
        "message":     message,
        "timestamp":   now,
    }


# ── Tool: draft_email ─────────────────────────────────────────────────────────

def handle_draft_email(payload: dict, dry_run: bool = True) -> dict:
    """
    Create a Gmail draft (does NOT send the email).

    Required payload keys:
        to          Recipient email address

    Optional payload keys:
        subject     Email subject line
        body        Plain-text email body
        task_file   Originating task filename (for audit logging)
        domain      "business" or "personal"
    """
    now       = _now()
    task_file = payload.get("task_file", payload.get("task_name", "unknown"))
    to        = payload.get("to", "").strip()
    subject   = payload.get("subject", f"AI Vault — Draft for {task_file}")
    body      = payload.get("body", "(No body provided)")

    if not to:
        return _error_result("draft_email", dry_run, "draft_email requires a 'to' address.", task_file)

    # ── DRY RUN ───────────────────────────────────────────────────────────────
    if dry_run:
        result: dict = {
            "server":      SERVER_NAME,
            "action_type": "draft_email",
            "dry_run":     True,
            "result":      "dry_run_logged",
            "message":     f"[DRY RUN] Would create Gmail draft — to: {to!r}, subject: {subject!r}",
            "timestamp":   now,
            "intent": {
                "to":           to,
                "subject":      subject,
                "body_preview": body[:120],
                "task_file":    task_file,
            },
        }
        log_action(SERVER_NAME, "draft_email_dry_run", {
            "task_file": task_file,
            "to":        to,
            "subject":   subject,
            "dry_run":   True,
            "note":      "Set MCP_DRY_RUN=false to create real Gmail drafts.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would create Gmail draft")
        print(f"  [{SERVER_NAME}]   To:      {to}")
        print(f"  [{SERVER_NAME}]   Subject: {subject}")
        print(f"  [{SERVER_NAME}]   Task:    {task_file}")
        print(f"  [{SERVER_NAME}]   -> Set env MCP_DRY_RUN=false to enable.")
        return result

    # ── LIVE: Gmail API call ──────────────────────────────────────────────────
    try:
        service   = _get_service()
        mime_msg  = _build_mime(to, subject, body, _DEFAULT_FROM)
        raw       = _mime_to_raw_b64(mime_msg)
        draft     = service.users().drafts().create(
            userId=_USER_ID,
            body={"message": {"raw": raw}},
        ).execute()
        draft_id  = draft.get("id", "unknown")

        result = {
            "server":      SERVER_NAME,
            "action_type": "draft_email",
            "dry_run":     False,
            "result":      "success",
            "message":     f"Gmail draft created — id: {draft_id}",
            "draft_id":    draft_id,
            "timestamp":   now,
        }
        log_action(SERVER_NAME, "draft_email_success", {
            "task_file": task_file,
            "to":        to,
            "subject":   subject,
            "draft_id":  draft_id,
        })
        print(f"  [{SERVER_NAME}] Draft created: id={draft_id}")

    except Exception as exc:
        result = _error_result("draft_email", False, str(exc), task_file)
        print(f"  [{SERVER_NAME}] ERROR creating draft: {exc}")

    return result


# ── Tool: send_email ──────────────────────────────────────────────────────────

def handle_send_email(payload: dict, dry_run: bool = True) -> dict:
    """
    Send an email via the Gmail API.

    Required payload keys:
        to          Recipient email address

    Optional payload keys:
        subject     Email subject line
        body        Plain-text email body
        task_file   Originating task filename (for audit logging)
        domain      "business" or "personal"
    """
    now       = _now()
    task_file = payload.get("task_file", payload.get("task_name", "unknown"))
    to        = payload.get("to", "").strip()
    subject   = payload.get("subject", f"AI Vault — Message for {task_file}")
    body      = payload.get("body", "(No body provided)")

    if not to:
        return _error_result("send_email", dry_run, "send_email requires a 'to' address.", task_file)

    # ── DRY RUN ───────────────────────────────────────────────────────────────
    if dry_run:
        result: dict = {
            "server":      SERVER_NAME,
            "action_type": "send_email",
            "dry_run":     True,
            "result":      "dry_run_logged",
            "message":     f"[DRY RUN] Would send Gmail — to: {to!r}, subject: {subject!r}",
            "timestamp":   now,
            "intent": {
                "to":           to,
                "subject":      subject,
                "body_preview": body[:120],
                "task_file":    task_file,
            },
        }
        log_action(SERVER_NAME, "send_email_dry_run", {
            "task_file": task_file,
            "to":        to,
            "subject":   subject,
            "dry_run":   True,
            "note":      "Set MCP_DRY_RUN=false to send real emails.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would send Gmail")
        print(f"  [{SERVER_NAME}]   To:      {to}")
        print(f"  [{SERVER_NAME}]   Subject: {subject}")
        print(f"  [{SERVER_NAME}]   Task:    {task_file}")
        print(f"  [{SERVER_NAME}]   -> Set env MCP_DRY_RUN=false to enable.")
        return result

    # ── LIVE: Gmail API call ──────────────────────────────────────────────────
    try:
        service  = _get_service()
        mime_msg = _build_mime(to, subject, body, _DEFAULT_FROM)
        raw      = _mime_to_raw_b64(mime_msg)
        sent     = service.users().messages().send(
            userId=_USER_ID,
            body={"raw": raw},
        ).execute()
        msg_id   = sent.get("id", "unknown")

        result = {
            "server":      SERVER_NAME,
            "action_type": "send_email",
            "dry_run":     False,
            "result":      "success",
            "message":     f"Gmail sent — message id: {msg_id}",
            "message_id":  msg_id,
            "timestamp":   now,
        }
        log_action(SERVER_NAME, "send_email_success", {
            "task_file":  task_file,
            "to":         to,
            "subject":    subject,
            "message_id": msg_id,
        })
        print(f"  [{SERVER_NAME}] Email sent: id={msg_id}")

    except Exception as exc:
        result = _error_result("send_email", False, str(exc), task_file)
        print(f"  [{SERVER_NAME}] ERROR sending email: {exc}")

    return result


# ── Tool: search_email ────────────────────────────────────────────────────────

def handle_search_email(payload: dict, dry_run: bool = True) -> dict:
    """
    Search the Gmail inbox using Gmail's standard query syntax.

    Required payload keys:
        query       Gmail search query (same syntax as the Gmail search box)

    Optional payload keys:
        max_results Maximum messages to return (default: 10, max: 500)
        task_file   Originating task filename (for audit logging)

    Query examples:
        "from:boss@company.com is:unread"
        "subject:invoice after:2024/01/01"
        "has:attachment label:inbox"
    """
    now         = _now()
    task_file   = payload.get("task_file", payload.get("task_name", "unknown"))
    query       = payload.get("query", "").strip()
    max_results = min(int(payload.get("max_results", 10)), 500)

    if not query:
        return _error_result("search_email", dry_run, "search_email requires a 'query' string.", task_file)

    # ── DRY RUN ───────────────────────────────────────────────────────────────
    if dry_run:
        simulated = [
            {
                "id":       "sim_dry_run_001",
                "threadId": "thread_dry_run_001",
                "from":     "example@domain.com",
                "subject":  f"[SIMULATED] Match for query: {query}",
                "date":     now,
                "snippet":  "This is a simulated search result. Set MCP_DRY_RUN=false for real results.",
            }
        ]
        result: dict = {
            "server":            SERVER_NAME,
            "action_type":       "search_email",
            "dry_run":           True,
            "result":            "dry_run_logged",
            "message":           f"[DRY RUN] Would search Gmail — query: {query!r}",
            "timestamp":         now,
            "simulated_results": simulated,
            "intent": {
                "query":       query,
                "max_results": max_results,
                "task_file":   task_file,
            },
        }
        log_action(SERVER_NAME, "search_email_dry_run", {
            "task_file":   task_file,
            "query":       query,
            "max_results": max_results,
            "dry_run":     True,
            "note":        "Set MCP_DRY_RUN=false to run real Gmail searches.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would search Gmail")
        print(f"  [{SERVER_NAME}]   Query:       {query}")
        print(f"  [{SERVER_NAME}]   Max results: {max_results}")
        print(f"  [{SERVER_NAME}]   -> Set env MCP_DRY_RUN=false to enable.")
        return result

    # ── LIVE: Gmail API call ──────────────────────────────────────────────────
    try:
        service  = _get_service()
        response = service.users().messages().list(
            userId=_USER_ID,
            q=query,
            maxResults=max_results,
        ).execute()
        messages = response.get("messages", [])

        # Fetch per-message metadata (From, Subject, Date) + snippet
        results = []
        for m in messages:
            detail = service.users().messages().get(
                userId=_USER_ID,
                id=m["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {
                h["name"]: h["value"]
                for h in detail.get("payload", {}).get("headers", [])
            }
            results.append({
                "id":       m["id"],
                "threadId": m.get("threadId", ""),
                "from":     headers.get("From", ""),
                "subject":  headers.get("Subject", ""),
                "date":     headers.get("Date", ""),
                "snippet":  detail.get("snippet", ""),
            })

        result = {
            "server":      SERVER_NAME,
            "action_type": "search_email",
            "dry_run":     False,
            "result":      "success",
            "message":     f"Found {len(results)} message(s) for query: {query!r}",
            "count":       len(results),
            "messages":    results,
            "timestamp":   now,
        }
        log_action(SERVER_NAME, "search_email_success", {
            "task_file": task_file,
            "query":     query,
            "count":     len(results),
        })
        print(f"  [{SERVER_NAME}] Search returned {len(results)} result(s) for: {query!r}")

    except Exception as exc:
        result = _error_result("search_email", False, str(exc), task_file)
        print(f"  [{SERVER_NAME}] ERROR searching email: {exc}")

    return result


# ── Self-registration (runs at import time) ───────────────────────────────────
# Loading gmail_mcp_server after email_mcp_stub (see router.py _STUB_MODULES)
# means "send_email" here supersedes the simpler stub alias — intentional.

register("draft_email",   SERVER_NAME, handle_draft_email)
register("send_email",    SERVER_NAME, handle_send_email)
register("search_email",  SERVER_NAME, handle_search_email)
