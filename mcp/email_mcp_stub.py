"""
mcp/email_mcp_stub.py — Email & Notification MCP Stub (Gold Tier).

Handles HITL-approved email and external notification actions.

DRY_RUN=true (default)
    Logs full intent (to, subject, payload) but sends nothing.
    Safe for CI, staging, and all non-production environments.

DRY_RUN=false
    Real implementation placeholder — replace the TODO blocks with your
    preferred email library (smtplib, SendGrid, SES, etc.).

Registered action_types
-----------------------
    email_send       — bulk or single email dispatch
    notify_external  — Slack message, webhook POST, etc.

Environment variables (all optional, only needed when DRY_RUN=false)
--------------------------------------------------------------------
    SMTP_HOST        SMTP server hostname
    SMTP_PORT        SMTP port (default 587)
    SMTP_USER        SMTP username / sender address
    SMTP_PASS        SMTP password / app token
    SENDGRID_API_KEY SendGrid API key (alternative to SMTP)
    SLACK_WEBHOOK_URL Slack incoming webhook URL
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from audit_logger import log_action
from mcp.registry import register

SERVER_NAME = "email_mcp_stub"


# ── Handlers ──────────────────────────────────────────────────────────────────

def handle_email_send(payload: dict, dry_run: bool = True) -> dict:
    """
    Execute or simulate an email_send action.

    Expected payload keys (all optional):
        task_file   — originating task filename
        domain      — "business" or "personal"
        run_id      — agent run identifier
        recipient   — override To: address
        subject     — override email subject
        body        — override email body text
    """
    now = datetime.now(timezone.utc).isoformat()
    task_file = payload.get("task_file", payload.get("task_name", "unknown"))
    recipient = payload.get("recipient", os.getenv("SMTP_USER", "<not configured>"))
    subject = payload.get("subject", f"AI Vault — Action for task: {task_file}")

    if dry_run:
        result: dict = {
            "server": SERVER_NAME,
            "action_type": "email_send",
            "dry_run": True,
            "result": "dry_run_logged",
            "message": f"[DRY RUN] Would send email — task: {task_file!r}, to: {recipient!r}",
            "timestamp": now,
            "intent": {
                "to": recipient,
                "subject": subject,
                "task_file": task_file,
            },
        }
        log_action(SERVER_NAME, "email_send_dry_run", {
            "task_file": task_file,
            "to": recipient,
            "subject": subject,
            "dry_run": True,
            "note": "Set MCP_DRY_RUN=false to enable real sends.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would send email")
        print(f"  [{SERVER_NAME}]   To:      {recipient}")
        print(f"  [{SERVER_NAME}]   Subject: {subject}")
        print(f"  [{SERVER_NAME}]   Task:    {task_file}")
        print(f"  [{SERVER_NAME}]   -> Set env MCP_DRY_RUN=false to enable.")

    else:
        # ── TODO: Replace with real email implementation ──────────────────────
        # Option A: smtplib
        #   import smtplib, ssl
        #   ctx = ssl.create_default_context()
        #   with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587"))) as s:
        #       s.starttls(context=ctx)
        #       s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
        #       s.sendmail(os.getenv("SMTP_USER"), recipient, body)
        #
        # Option B: SendGrid
        #   import sendgrid; sg = sendgrid.SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        #   ...
        # ─────────────────────────────────────────────────────────────────────
        result = {
            "server": SERVER_NAME,
            "action_type": "email_send",
            "dry_run": False,
            "result": "not_implemented",
            "message": "Real email send not yet implemented — replace TODO block in email_mcp_stub.py.",
            "timestamp": now,
        }
        log_action(SERVER_NAME, "email_send_not_implemented", {
            "task_file": task_file,
        }, success=False)
        print(f"  [{SERVER_NAME}] WARN: Real email send not implemented (see TODO in email_mcp_stub.py).")

    return result


def handle_notify_external(payload: dict, dry_run: bool = True) -> dict:
    """
    Execute or simulate an external notification (Slack, webhook, etc.).

    Expected payload keys (all optional):
        task_file    — originating task filename
        domain       — "business" or "personal"
        webhook_url  — override target URL
        message      — override notification text
    """
    now = datetime.now(timezone.utc).isoformat()
    task_file = payload.get("task_file", payload.get("task_name", "unknown"))
    webhook_url = payload.get("webhook_url", os.getenv("SLACK_WEBHOOK_URL", "<not configured>"))
    message = payload.get("message", f"AI Vault action completed for task: {task_file}")

    if dry_run:
        result: dict = {
            "server": SERVER_NAME,
            "action_type": "notify_external",
            "dry_run": True,
            "result": "dry_run_logged",
            "message": f"[DRY RUN] Would POST notification — task: {task_file!r}",
            "timestamp": now,
            "intent": {
                "webhook_url": webhook_url,
                "message": message,
                "task_file": task_file,
            },
        }
        log_action(SERVER_NAME, "notify_external_dry_run", {
            "task_file": task_file,
            "webhook_url": webhook_url,
            "dry_run": True,
            "note": "Set MCP_DRY_RUN=false to enable real notifications.",
        })
        print(f"  [{SERVER_NAME}] DRY RUN: Would notify external service")
        print(f"  [{SERVER_NAME}]   Webhook: {webhook_url}")
        print(f"  [{SERVER_NAME}]   Message: {message[:80]}...")
        print(f"  [{SERVER_NAME}]   -> Set env MCP_DRY_RUN=false to enable.")

    else:
        # ── TODO: Replace with real notification implementation ───────────────
        # Option A: Slack incoming webhook
        #   import urllib.request, json
        #   req = urllib.request.Request(
        #       webhook_url,
        #       data=json.dumps({"text": message}).encode(),
        #       headers={"Content-Type": "application/json"},
        #       method="POST",
        #   )
        #   urllib.request.urlopen(req)
        #
        # Option B: Generic HTTP webhook (requests)
        #   import requests
        #   requests.post(webhook_url, json={"text": message, "task": task_file})
        # ─────────────────────────────────────────────────────────────────────
        result = {
            "server": SERVER_NAME,
            "action_type": "notify_external",
            "dry_run": False,
            "result": "not_implemented",
            "message": "Real external notification not yet implemented — replace TODO in email_mcp_stub.py.",
            "timestamp": now,
        }
        log_action(SERVER_NAME, "notify_external_not_implemented", {
            "task_file": task_file,
        }, success=False)
        print(f"  [{SERVER_NAME}] WARN: Real external notify not implemented (see TODO in email_mcp_stub.py).")

    return result


# ── Self-registration (runs at import time) ───────────────────────────────────

register("email_send", SERVER_NAME, handle_email_send)
register("notify_external", SERVER_NAME, handle_notify_external)

# "send_email" is a HITL action-parser alias for email_send
register("send_email", SERVER_NAME, handle_email_send)
