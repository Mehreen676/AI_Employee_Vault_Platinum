"""
MCP Server 2 – Email Operations.

Handles email ingestion, classification, and notification drafting.
Wraps Gmail API for Gold tier cross-domain email integration.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from datetime import datetime, timezone
from audit_logger import log_action

SERVER_NAME = "mcp_email_ops"

# Domain classification rules
PERSONAL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"}
BUSINESS_DOMAINS = {"google.com", "github.com", "microsoft.com", "azure.com", "slack.com"}


def classify_sender(email_addr: str) -> str:
    """Classify email sender as 'personal' or 'business'."""
    match = re.search(r"@([\w.-]+)", email_addr)
    if not match:
        return "personal"
    domain = match.group(1).lower()
    if any(domain == d or domain.endswith("." + d) for d in BUSINESS_DOMAINS):
        return "business"
    return "personal"


def parse_email_headers(headers: list[dict]) -> dict:
    """Extract key headers from Gmail API header list."""
    result = {}
    for h in headers:
        name = h.get("name", "").lower()
        if name in ("from", "to", "subject", "date"):
            result[name] = h.get("value", "")
    return result


def create_task_from_email(
    sender: str,
    subject: str,
    date: str,
    snippet: str,
    msg_id: str,
    output_dir: str | Path,
) -> str | None:
    """Create a task markdown file from email data. Returns filename or None."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    domain_type = classify_sender(sender)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"email_{ts}_{msg_id}.md"

    content = (
        "# Email Task\n\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Date: {date}\n"
        f"Domain: {domain_type}\n"
        f"MessageID: {msg_id}\n\n"
        "## Content\n"
        f"{snippet}\n\n"
        "Source: Gmail\n"
        "Status: New\n"
    )

    try:
        (output_dir / filename).write_text(content, encoding="utf-8")
        log_action(SERVER_NAME, "create_task_from_email", {
            "filename": filename,
            "sender": sender,
            "domain_type": domain_type,
            "subject": subject,
        })
        return filename
    except Exception as e:
        log_action(SERVER_NAME, "create_task_error", {"error": str(e)}, success=False)
        return None


def draft_reply(subject: str, summary: str) -> str:
    """Generate a draft reply template."""
    reply = (
        f"Subject: Re: {subject}\n\n"
        f"Thank you for your message regarding: {subject}\n\n"
        f"Summary of action taken:\n{summary}\n\n"
        "Best regards,\n"
        "AI Employee (Gold Tier)\n"
    )
    log_action(SERVER_NAME, "draft_reply", {"subject": subject})
    return reply


if __name__ == "__main__":
    print(f"=== {SERVER_NAME} Server Ready ===")
    print("Tools: classify_sender, parse_email_headers, create_task_from_email, draft_reply")
