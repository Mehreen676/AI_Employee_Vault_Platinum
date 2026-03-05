"""
AI Employee Vault – Platinum Tier
Slack Integration  |  integrations/slack_integration.py

Handles incoming Slack webhook payloads → vault tasks.

Used by the FastAPI backend endpoint: POST /slack/webhook
Also usable standalone for testing.

Each Slack message is converted to a task manifest and written to:
    vault/Needs_Action/

Activity logged to: Evidence/SLACK_INTEGRATION_LOG.md
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Path helpers ───────────────────────────────────────────────────────────────

def _vault_dir() -> Path:
    return Path(os.getenv("VAULT_DIR", str(Path(__file__).resolve().parent.parent / "vault")))

def _evidence_dir() -> Path:
    return Path(os.getenv("EVIDENCE_OUT_DIR", str(Path(__file__).resolve().parent.parent / "Evidence")))


# ── Slack payload parser ───────────────────────────────────────────────────────

def parse_slack_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    Parse a Slack Events API or webhook payload into a normalized message dict.
    Returns None if the payload is a URL verification challenge.
    """
    # Handle Slack URL verification challenge
    if payload.get("type") == "url_verification":
        return None

    # Events API: event.type == "message"
    event = payload.get("event", {})
    text  = event.get("text") or payload.get("text") or ""
    user  = event.get("user") or payload.get("user_name") or "unknown"
    channel = event.get("channel") or payload.get("channel_name") or "general"
    ts    = event.get("ts") or payload.get("timestamp") or datetime.now(timezone.utc).isoformat()

    # Strip Slack formatting (e.g., <@U123ABC>)
    text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    text = re.sub(r"<#[A-Z0-9]+\|([^>]+)>", r"#\1", text)

    if not text:
        return None

    return {"text": text, "user": user, "channel": channel, "ts": str(ts)}


# ── Message → task ─────────────────────────────────────────────────────────────

def slack_message_to_task(message: dict[str, Any]) -> dict[str, Any]:
    text = message["text"]

    # Simple intent detection
    task_type = "slack_message"
    zone      = "docs"
    if re.search(r"\b(invoice|payment|bill)\b", text, re.I):
        task_type, zone = "create_invoice", "finance"
    elif re.search(r"\b(email|send|message)\b", text, re.I):
        task_type, zone = "send_email", "email"
    elif re.search(r"\b(schedule|meeting|calendar)\b", text, re.I):
        task_type, zone = "schedule_meeting", "calendar"
    elif re.search(r"\b(post|publish|share|social)\b", text, re.I):
        task_type, zone = "social_post", "social"
    elif re.search(r"\b(crm|contact|client|partner)\b", text, re.I):
        task_type, zone = "crm_update", "docs"

    return {
        "id":         str(uuid.uuid4()),
        "task_type":  task_type,
        "zone":       zone,
        "source":     "slack_webhook",
        "slack_user": message["user"],
        "channel":    message["channel"],
        "content":    text[:1000],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status":     "pending",
    }


# ── Vault writer ───────────────────────────────────────────────────────────────

def write_vault_task(task: dict[str, Any]) -> Path:
    dest_dir = _vault_dir() / "Needs_Action"
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"slack_{ts}_{task['id'][:8]}.json"
    dest     = dest_dir / filename
    tmp      = dest_dir / f".tmp_{filename}"
    tmp.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.rename(dest)
    return dest


# ── Evidence log ───────────────────────────────────────────────────────────────

def log_evidence(message: dict, task: dict, dest: Path) -> None:
    ev_dir = _evidence_dir()
    ev_dir.mkdir(parents=True, exist_ok=True)
    log_path = ev_dir / "SLACK_INTEGRATION_LOG.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(
            f"\n### {ts} — Slack Message\n"
            f"- **User:** `{message.get('user', 'unknown')}`\n"
            f"- **Channel:** `{message.get('channel', 'unknown')}`\n"
            f"- **Text:** {message.get('text', '')[:200]}\n"
            f"- **Task ID:** `{task['id']}`\n"
            f"- **Task Type:** `{task['task_type']}`\n"
            f"- **Vault file:** `{dest.name}`\n"
        )


# ── Public API ─────────────────────────────────────────────────────────────────

def handle_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Process a Slack webhook payload.
    Returns a response dict suitable for the FastAPI endpoint.
    """
    # Handle challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    message = parse_slack_payload(payload)
    if message is None:
        return {"ok": True, "action": "ignored", "reason": "no actionable text"}

    task = slack_message_to_task(message)
    dest = write_vault_task(task)
    log_evidence(message, task, dest)
    log.info("[slack] task %s written → %s", task["id"], dest.name)

    return {
        "ok":        True,
        "task_id":   task["id"],
        "task_type": task["task_type"],
        "vault_file": dest.name,
    }
